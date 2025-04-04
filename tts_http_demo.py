#coding=utf-8

'''
requires Python 3.6 or later
pip install requests
'''
import base64
import json
import uuid
import requests
import os
import tempfile
import subprocess
from playsound import playsound

from dotenv import load_dotenv

load_dotenv()

# 填写平台申请的appid, access_token以及cluster
appid = os.environ.get('appid')
access_token= os.environ.get('access_token')
cluster = os.environ.get('cluster')

# 检查是否有必要的环境变量
if not appid or not access_token or not cluster:
    print("警告: 未找到火山引擎TTS必要的环境变量 (appid, access_token, cluster)")

voice_type1 = "BV064_streaming"
host = "openspeech.bytedance.com"
api_url = f"https://{host}/api/v1/tts"

header = {"Authorization": f"Bearer;{access_token}"}

request_json = {
    "app": {
        "appid": appid,
        "token": "access_token",
        "cluster": cluster
    },
    "user": {
        "uid": "388808087185088"
    },
    "audio": {
        "voice_type": voice_type1,
        "encoding": "mp3",
        "speed_ratio": 1.2,
        "volume_ratio": 1.0,
        "pitch_ratio": 1.0,
    },
    "request": {
        "reqid": str(uuid.uuid4()),
        "text": "字节跳动语音合成",
        "text_type": "plain",
        "operation": "query",
        "with_frontend": 1,
        "frontend_type": "unitTson"
    }
}

def tts_volcano(text: str, voice_type: str = voice_type1) -> bytes:
    """火山引擎TTS核心函数
    Args:
        text: 要合成的文本
        voice_type: 音色类型
    Returns:
        bytes: 音频二进制数据
    """
    if not appid or not access_token or not cluster:
        raise ValueError("缺少火山引擎TTS必要的环境变量，请检查.env文件")
        
    request_json["audio"]["voice_type"] = voice_type
    request_json["request"]["text"] = text
    request_json["request"]["reqid"] = str(uuid.uuid4())
    
    try:
        # 调试信息
        print(f"正在调用火山引擎TTS API，文本长度: {len(text)} 字符")
        
        resp = requests.post(api_url, json.dumps(request_json), headers=header)
        if resp.status_code != 200:
            error_msg = f"API请求失败，状态码：{resp.status_code}"
            try:
                error_data = resp.json()
                if "message" in error_data:
                    error_msg += f"，错误信息：{error_data['message']}"
            except:
                error_msg += f"，响应内容：{resp.text[:100]}"
            raise ValueError(error_msg)
        
        resp_data = resp.json()
        if "data" not in resp_data:
            error_msg = "API返回中未找到'data'字段"
            if "message" in resp_data:
                error_msg += f"，错误信息：{resp_data['message']}"
            raise ValueError(error_msg)
            
        audio_data = base64.b64decode(resp_data["data"])
        print(f"成功获取音频数据，大小: {len(audio_data)} 字节")
        return audio_data
    except requests.exceptions.RequestException as e:
        print(f"网络请求错误: {str(e)}")
        raise
    except ValueError as e:
        print(f"TTS合成失败: {str(e)}")
        raise
    except Exception as e:
        print(f"TTS合成未知错误: {str(e)}")
        raise

def tts_play(text: str, voice_type: str = voice_type1):
    """合成并直接播放语音
    Args:
        text: 要合成的文本
        voice_type: 音色类型
    """
    try:
        # 验证文本不为空
        if not text or len(text.strip()) == 0:
            print("警告: 文本为空，无法合成语音")
            return False
            
        # 使用火山引擎合成音频
        audio_data = tts_volcano(text, voice_type)
        
        # 验证音频数据
        if not audio_data or len(audio_data) == 0:
            print("错误: 未能获取有效的音频数据")
            return False
            
        # 保存到临时文件
        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as tmp:
            temp_file = tmp.name
            tmp.write(audio_data)
        
        # 直接播放 - 保持简单
        playsound(temp_file, block=True)
        
        # 播放完成后删除临时文件
        try:
            os.unlink(temp_file)
        except Exception as e:
            print(f"清理临时文件失败: {str(e)}")
        
        return True
    except Exception as e:
        print(f"语音播放失败: {str(e)}")
        return False

if __name__ == '__main__':
    try:
        # 测试文本
        test_text = "这是火山引擎语音合成的测试。"
        
        # 方法1: 获取音频数据并保存
        audio_data = tts_volcano(test_text)
        with open("test_submit.mp3", "wb") as file_to_save:
            file_to_save.write(audio_data)
        print("音频数据已保存到 test_submit.mp3")
        
        # 方法2: 直接播放
        print("正在播放合成的语音...")
        tts_play("播放测试成功。")
    except Exception as e:
        print(f"测试出错: {str(e)}")
