import os
import uuid
import requests
import speech_recognition as sr
from tts_http_demo import tts_volcano, tts_play
from playsound import playsound
import tempfile

def tts(text: str):
    """
    使用文本转语音功能
    :param text: 要转换为语音的文本
    """
    try:
        # 尝试使用tts_play函数(在tts_http_demo.py中定义)
        return tts_play(text)
    except Exception as e:
        print(f"文本转语音失败: {str(e)}")
        raise

def recognize_speech() -> str:
    """
    使用语音识别功能，将用户语音转为文本
    :return: 识别的文本，如果识别失败则返回空字符串
    """
    url = "https://api.siliconflow.cn/v1/audio/transcriptions"
    api_key = os.getenv("sttkey")
    
    if not api_key:
        print("错误: 未找到语音识别API密钥，请检查环境变量sttkey")
        return ""
        
    headers = {
        "Authorization": f"Bearer {api_key}"
    }

    r = sr.Recognizer()
    try:
        with sr.Microphone() as source:
            print("请开始说话...")
            try:
                # 调整噪声阈值
                r.adjust_for_ambient_noise(source, duration=0.5)
                audio = r.listen(source, timeout=5, phrase_time_limit=10)
                print("录音结束，正在识别...")
            except sr.WaitTimeoutError:
                print("超时未检测到语音输入")
                return ""
    except Exception as e:
        print(f"麦克风初始化错误: {str(e)}")
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
            if "text" not in result:
                print(f"API返回格式错误，未找到'text'字段: {result}")
                return ""
            text = result['text']
            print(f"语音识别结果: {text}")
            return text
    except requests.exceptions.RequestException as e:
        print(f"请求错误: {e}")
        return ""
    except (KeyError, TypeError, ValueError) as e:
        print(f"响应格式错误: {e}")
        return ""
    finally:
        # 延迟删除，或者在下一次循环开始时删除
        try:
            if os.path.exists(temp_file):
                os.remove(temp_file)
        except OSError as e:
            print(f"删除临时文件失败: {e}")

    return "" 