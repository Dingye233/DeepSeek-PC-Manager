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

from dotenv import load_dotenv

load_dotenv()

# 填写平台申请的appid, access_token以及cluster
appid = os.environ.get('appid')
access_token= os.environ.get('access_token')
cluster = os.environ.get('cluster')


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
    request_json["audio"]["voice_type"] = voice_type
    request_json["request"]["text"] = text
    request_json["request"]["reqid"] = str(uuid.uuid4())
    
    try:
        resp = requests.post(api_url, json.dumps(request_json), headers=header)
        if resp.status_code != 200:
            raise ValueError(f"API请求失败，状态码：{resp.status_code}")
        
        resp_data = resp.json()
        if "data" not in resp_data:
            raise ValueError(f"API返回异常：{resp_data.get('message', '未知错误')}")
            
        return base64.b64decode(resp_data["data"])
    except Exception as e:
        print(f"TTS合成失败: {str(e)}")
        raise

if __name__ == '__main__':
    try:
        resp = requests.post(api_url, json.dumps(request_json), headers=header)
        print(f"resp body: \n{resp.json()}")
        if "data" in resp.json():
            data = resp.json()["data"]
            file_to_save = open("test_submit.mp3", "wb")
            file_to_save.write(base64.b64decode(data))
    except Exception as e:
        e.with_traceback()
