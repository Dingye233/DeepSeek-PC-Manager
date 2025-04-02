import os
import json
import requests
from datetime import datetime, timedelta
import speech_recognition as sr
import uuid
from R1_optimize import r1_optimizer as R1
from console_utils import print_error

# 获取当前时间
def get_current_time(timezone: str = "UTC") -> str:
    now = datetime.utcnow() if timezone == "UTC" else datetime.now()
    return now.strftime("%Y-%m-%d %H:%M:%S")

# 获取天气信息
def get_weather(city: str) -> str:
    """
    获取城市未来24小时天气信息
    :param city: 城市名称
    :return: 格式化的24小时天气信息字符串
    """
    try:
        key = os.environ.get("key")
        weather_url = "https://devapi.qweather.com/v7/weather/24h"
        location_url = "https://geoapi.qweather.com/v2/city/lookup"

        # 获取城市ID
        location_response = requests.get(f"{location_url}?location={city}&key={key}")
        location_data = location_response.json()

        if location_data.get("code") != "200":
            return f"抱歉，未能找到{city}的位置信息"

        location_id = location_data["location"][0]['id']

        # 获取天气信息
        weather_response = requests.get(f"{weather_url}?location={location_id}&key={key}")
        weather_data = weather_response.json()

        if weather_data.get("code") != "200":
            return f"抱歉，未能获取{city}的天气信息"

        now = datetime.now()
        end_time = now + timedelta(hours=24)

        # 直接返回未来24小时的天气数据
        hourly_forecasts = []
        hourly_forecasts.append(f"当前服务器查询时间是:{now}")
        for forecast in weather_data['hourly']:
            forecast_time = datetime.fromisoformat(forecast['fxTime'].replace('T', ' ').split('+')[0])
            if now <= forecast_time <= end_time:
                hourly_forecasts.append(forecast)

        return json.dumps(hourly_forecasts, ensure_ascii=False)

    except Exception as e:
        return f"获取天气信息时出错：{str(e)}"

# R1优化
def R1_opt(message: str) -> str:
    """
    调用深度思考模型DeepSeek Reasoner来解决复杂问题
    
    适用场景:
    1. 复杂代码生成与实现
    2. 多次尝试仍无法修复的bug
    3. 复杂算法设计与优化
    4. 需要多步推理的逻辑问题
    
    :param message: 包含完整问题描述和必要上下文的请求
    :return: reasoner模型的详细解决方案
    """
    return R1(message)

# 语音识别
def recognize_speech() -> str:
    url = "https://api.siliconflow.cn/v1/audio/transcriptions"
    api_key = os.getenv("sttkey")
    headers = {
        "Authorization": f"Bearer {api_key}"
    }

    r = sr.Recognizer()
    with sr.Microphone() as source:
        print("请开始说话...")
        try:
            audio = r.listen(source, timeout=5, phrase_time_limit=10)
            print("录音结束，正在识别...")
        except sr.WaitTimeoutError:
            print("超时未检测到语音输入")
            return ""

    temp_file = f"temp_audio_{uuid.uuid4().hex}.wav"  # 使用唯一文件名
    try:
        with open(temp_file, "wb") as f:
            f.write(audio.get_wav_data())

        with open(temp_file, 'rb') as f:
            files = {'file': (temp_file, f)}
            payload = {
                "model": "FunAudioLLM/SenseVoiceSmall",
                "response_format": "transcript"
            }
            response = requests.post(url, headers=headers, data=payload, files=files)
            response.raise_for_status()
            result = response.json()
            text = result['text']
            print(f"语音识别结果: {text}")
            return text
    except requests.exceptions.RequestException as e:
        print_error(f"请求错误: {e}")
        return ""
    except (KeyError, TypeError, ValueError) as e:
        print_error(f"响应格式错误: {e}")
        return ""
    finally:
        # 延迟删除，或者在下一次循环开始时删除
        try:
            os.remove(temp_file)
        except OSError as e:
            print_error(f"删除临时文件失败: {e}")

    return "" 