from openai import OpenAI
import json
from datetime import datetime, timedelta
import asyncio
import edge_tts
from playsound import playsound
import os
import tempfile
import requests
import geopy
import speech_recognition as sr
import keyboard
import threading
import time
import get_email
import subprocess
import speech_recognition as sr
import keyboard
import time
import python_tools
import send_email
from dotenv import load_dotenv
from R1_optimize import r1_optimizer as R1
load_dotenv()
# 1. TTS 功能实现
async def text_to_speech(text: str, voice: str = "zh-CN-XiaoxiaoNeural"):
    """
    将文本转换为语音并播放
    :param text: 要转换的文本
    :param voice: 声音选择，默认使用微软小晓声音
    """
    try:
        temp_file = None
        try:
            # 创建临时文件用于保存音频
            temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.mp3')
            temp_file_path = temp_file.name
            temp_file.close()

            # 使用 edge-tts 转换文本为语音
            communicate = edge_tts.Communicate(text, voice)
            await communicate.save(temp_file_path)

            # 播放音频
            playsound(temp_file_path)

        finally:
            # 确保在所有操作完成后删除临时文件
            if temp_file and os.path.exists(temp_file_path):
                try:
                    os.unlink(temp_file_path)
                except Exception as e:
                    print(f"删除临时文件失败: {str(e)}")

    except Exception as e:
        print(f"TTS 错误: {str(e)}")
def encoding(file_name:str,code:str)->str:

    return python_tools.encoding(code,file_name)

def email_check()-> list:
    return get_email.retrieve_emails()


def email_details(email_id:str)-> dict:
    return get_email.get_email_details(email_id)


# 2. 工具函数
def get_current_time(timezone: str = "UTC") -> str:
    now = datetime.utcnow() if timezone == "UTC" else datetime.now()
    return now.strftime("%Y-%m-%d %H:%M:%S")
def R1_opt(message:str)->str:

    return R1(message)

def powershell_command(command: str) -> str:

    try:

        result = subprocess.run(
            ["powershell.exe", "-Command", command],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            encoding='utf-8',
            errors='replace',
            timeout=60
        )

        output = result.stdout.strip()
        if not output:
            return "命令执行成功（无输出）"
        return f"执行成功:\n{output}"
    except subprocess.CalledProcessError as e:
        error_msg = e.stderr.strip() or "未知错误"
        return f"命令执行失败（错误码 {e.returncode}）:\n{error_msg}"
    except subprocess.TimeoutExpired:
        return "错误：命令执行超时（超过60秒），可能正在等待用户输入"

def get_weather(city: str) -> str:
    """
    获取城市未来24小时天气信息
    :param city: 城市名称
    :return: 格式化的24小时天气信息字符串
    """
    try:
        key =os.environ.get("key")
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
# def back_to_model(model_message: str):
#     main(model_message)
def send_mail(text:str,receiver:str,subject:str)->str:
    return send_email.main(text,receiver,subject)
# 3. 工具描述
tools = [
    {
        "type": "function",
        "function": {
            "name": "get_current_time",
            "description": "获取当前时间",
            "parameters": {
                "type": "object",
                "properties": {
                    "timezone": {
                        "type": "string",
                        "description": "时区",
                        "enum": ["UTC", "local"]
                    }
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "获取城市未来24小时的天气(请区分用户问的时间段是属于今天还是明天的天气)",
            "parameters": {
                "type": "object",
                "properties": {
                    "city": {
                        "type": "string",
                        "description": "城市名"
                    }
                },
                "required": ["city"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "powershell_command",
            "description": "通过PowerShell终端来控制系统的一切操作（文件管理/进程控制/系统设置等）",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "要执行的PowerShell命令（多条用;分隔），必须包含绕过确认的参数"
                    }
                },
                "required": ["command"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "email_check",
            "description":"查看邮箱收件箱邮件列表并且获取邮件id",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    },
{
        "type": "function",
        "function": {
            "name": "email_details",
            "description":"查看该id的邮件的详细内容",
            "parameters": {
                "type": "object",
                "properties": {
                    "email_id": {
                        "type":"string",
                        "description":"输入在email_check里面获取到的指定邮件id"
                    }
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "encoding",
            "description": "创建一个任意后缀的文件，并且填写内容进去然后保存，最后返回一个该文件的绝对路径",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_name": {
                        "type": "string",
                        "description": "输入要创建的文件的名字和后缀 如:xxx.txt xxxx.py"
                    },
                    "encoding": {
                        "type": "string",
                        "description": "输入进文件的内容，可以是一段话也可以是代码"
                    }
                },
                "required": ["file_name", "encoding"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "send_mail",
            "description":"发送一封邮件向指定邮箱",
            "parameters": {
                "type": "object",
                "properties": {
                    "receiver": {
                        "type": "string",
                        "description":"收件人邮箱，请严格查看收件人邮箱是否是正确的邮箱格式"
                    },
                    "subject":{
                        "type": "string",
                        "description":"邮件主题"
                    },
                    "text": {
                        "type": "string",
                        "description":"邮件的内容  (用html的模板编写以避免编码问题)"
                    }
                },
                "required": ["receiver","subject","text"]
            }
        }
    },{
        "type": "function",
        "function": {
            "name":"R1_opt",
            "description":"当问题解决不了时调用更强大的r1深度思考模型来获取内容和答案给模型参考(返回的输出是string)",
            "parameters": {
                "type": "object",
                "properties": {
                    "message": {
                        "type": "string",
                        "description":"需要解决的文本和代码或者其他内容"
                    }
                },
                "required": ["message"]
            }
        }
    }
]

client = OpenAI(api_key=os.environ.get("api_key"), base_url="https://api.deepseek.com")
messages = [{"role": "system",
             "content": "你叫小美你乐于助人，心地善良，活泼聪明，不要像个ai工具那样说话 "},
            {"role": "system","content": " 注意：1.文件操作必须使用绝对路径 2.危险操作要自动添加安全参数 "}]

check_model_message=[{"role": "system",
         "content": "你是任务审查模型，需要审查用户的任务是否被模型完成，如果没有完成则补充下一步该干什么，最后再让被审查模型继续执行"}]
async def main(input_message:str):

    if input_message.lower() == 'quit':
        return False

    messages.append({"role": "user", "content": input_message})
    # check_model_message.append({"role": "user", "content": "这是用户的输入: "+input_message})
    # messages.append({"role": "assistant","content": "r1模型的输出结果: "+R1(str(messages))})
    # 让模型自己决定是否需要使用工具
    response = client.chat.completions.create(
        model="deepseek-chat",
        messages=messages,
        tools=tools,
        tool_choice="auto",
        temperature=1.5
    )

    # 如果模型决定使用工具
    if response.choices[0].message.tool_calls:
        tool_calls = response.choices[0].message.tool_calls
        tool_outputs = []

        for tool_call in tool_calls:
            func_name = tool_call.function.name
            args = json.loads(tool_call.function.arguments)

            try:
                # 带错误处理的工具调用
                if func_name == "get_current_time":
                    result = get_current_time(args.get("timezone", "UTC"))
                elif func_name == "get_weather":
                    result = get_weather(args["city"])
                elif func_name == "powershell_command":
                    result = powershell_command(args["command"])
                elif func_name == "email_check":
                    result = email_check()
                elif func_name == "email_details":
                    result = email_details(args["email_id"])
                elif func_name == "encoding":
                    result = encoding(args["file_name"], args["encoding"])
                elif func_name == "send_mail":
                    result = send_mail(args["receiver"], args["subject"],args["text"])
                elif func_name == "R1_opt":
                    result = R1(args["message"])
                else:
                    raise ValueError(f"未定义的工具调用: {func_name}")

            except Exception as e:
                result = f"工具执行失败: {str(e)}"

            tool_outputs.append({
                "tool_call_id": tool_call.id,
                "output": str(result)
            })
        messages.append({
            "role": "assistant",
            "content": None,
            "tool_calls": response.choices[0].message.tool_calls
        })
        for output in tool_outputs:
            messages.append({
                "role": "tool",
                "tool_call_id": output["tool_call_id"],
                "content": output["output"]
            })
            check_model_message.append({
                "role": "tool",
                "tool_call_id": output["tool_call_id"],
                "content": "模型调用结果: "+output["output"]
            })

        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=messages,
            temperature=1.5
        )

    assistant_message = response.choices[0].message.content
    print("小美:", assistant_message)
    messages.append({"role": "assistant", "content": assistant_message})
    # 使用 TTS 播放回答
    # await text_to_speech(assistant_message)
    return True


if __name__ == "__main__":
    while True:
        user_message=input("输入消息: ")
        should_continue = asyncio.run(main(user_message))
        if not should_continue:
            break