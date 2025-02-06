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
import keyboard
import threading
import get_email
import speech_recognition as sr
import keyboard
import time
import subprocess
import re
from queue import Queue, Empty
from threading import Thread
import python_tools
import send_email
import ssh_controller
from dotenv import load_dotenv
from R1_optimize import r1_optimizer as R1
import pyaudio
import wave
import uuid

load_dotenv()
# 1. TTS 功能实现
async def text_to_speech(text: str, voice: str = "zh-CN-XiaoxiaoNeural"):
    try:
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.mp3')
        temp_file_path = temp_file.name
        temp_file.close()

        communicate = edge_tts.Communicate(text, voice)
        await communicate.save(temp_file_path)
        playsound(temp_file_path)

        if os.path.exists(temp_file_path):
            os.unlink(temp_file_path)
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

async def powershell_command(command: str) -> str:
    """改进后的交互式命令执行函数"""
    interaction_pattern = re.compile(
        r'(?:Overwrite|确认|Enter|输入|密码|passphrase|file name|\[Y/N\]|是否继续)',
        re.IGNORECASE
    )

    proc = await asyncio.create_subprocess_exec(
        "powershell.exe", "-Command", command,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        limit=1024 * 1024  # 1MB缓冲区
    )

    output = []
    error = []
    buffer = ''
    timeout = 240
    last_active = time.time()

    async def watch_output(stream, is_stderr=False):
        """异步读取输出流"""
        nonlocal buffer, last_active
        while True:
            try:
                chunk = await stream.read(100)
                if not chunk:
                    break
                decoded = chunk.decode('utf-8', errors='replace')

                # 实时输出到控制台
                print(decoded, end='', flush=True)

                buffer += decoded
                if is_stderr:
                    error.append(decoded)
                else:
                    output.append(decoded)

                # 检测到交互提示
                if interaction_pattern.search(buffer):
                    # 挂起当前协程，等待用户输入
                    user_input = await get_user_input_async("\n需要确认，请输入响应后回车：")
                    proc.stdin.write(f"{user_input}\n".encode())
                    await proc.stdin.drain()
                    buffer = ''
                    last_active = time.time()

            except Exception as e:
                print(f"读取错误: {str(e)}")
                break

    # 创建输出监控任务
    stdout_task = asyncio.create_task(watch_output(proc.stdout))
    stderr_task = asyncio.create_task(watch_output(proc.stderr, True))

    try:
        while True:
            # 检查超时
            if time.time() - last_active > timeout:
                raise asyncio.TimeoutError()

            # 检查进程状态
            if proc.returncode is not None:
                break

            await asyncio.sleep(0.1)

    except asyncio.TimeoutError:
        proc.terminate()
        return "错误：命令执行超时（超过240秒）"

    finally:
        await stdout_task
        await stderr_task

    # 收集最终输出
    stdout = ''.join(output).strip()
    stderr = ''.join(error).strip()

    if proc.returncode == 0:
        return f"执行成功:\n{stdout}" if stdout else "命令执行成功（无输出）"
    else:
        error_msg = stderr or "未知错误"
        return f"命令执行失败（错误码 {proc.returncode}）:\n{error_msg}"


# 2. 新增异步输入函数
async def get_user_input_async(prompt: str) -> str:
    """异步获取用户输入"""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, lambda: input(prompt))




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
def user_information_read()->str:
    try:
        # 尝试打开文件并读取内容
        with open("user_information.txt", "r", encoding="utf-8") as file:
            content = file.read()
        return content
    except FileNotFoundError:
        # 如果文件不存在，捕获异常并返回提示信息
        return f"错误：找不到文件 '{"user_information.txt"}'，请检查路径是否正确。"
    except Exception as e:
        # 捕获其他可能的异常（如编码错误）
        return f"读取文件时发生错误：{e}"
def ssh(command:str)->str:
    ip = "192.168.10.107"
    username = "ye"
    password = "147258"
    return ssh_controller.ssh_interactive_command(ip,username,password,command)
# 3. 工具描述
tools = [
    {
        "type":"function",
        "function":{
           "name":"ssh",
            "description":"通过ssh远程连接ubuntu服务器并且输入命令控制远程服务器",
            "parameters":{
                "type":"object",
                "properties":{
                    "command":{
                        "type":"string",
                        "description":"ubuntu服务器的命令"
                    }
                },
                "required": ["command"]
            }
        },
    },
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
                    },
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
            "description":"此工具维护，停止使用",
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
# messages = [{"role": "system",
#              "content": "你叫小美你乐于助人，心地善良，活泼聪明，不要像个ai工具那样说话 "},
#             {"role": "system","content": " 注意：1.文件操作必须使用绝对路径 2.危险操作要自动添加安全参数 "},
#             {"role": "system","content": " 这些是用户的一些关键信息，可能有用: "+user_information_read()}]

messages = [{"role": "system","content": " 你叫小美，是一个热情的ai助手，这些是用户的一些关键信息，可能有用: "+user_information_read()}]


# check_model_message=[{"role": "system",
#          "content": "你是任务审查模型，需要审查用户的任务是否被模型完成，如果没有完成则补充下一步该干什么，最后再让被审查模型继续执行"}]


async def main(input_message: str):
    if input_message.lower() == 'quit':
        return False

    messages.append({"role": "user", "content": input_message})

    try:
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=messages,
            tools=tools,
            tool_choice="auto",
            temperature=1.3
        )
        print("API 调用成功")
        print("Raw Response:", response)

    except Exception as e:
        print("\n===== API 错误信息 =====")
        print(f"错误类型: {type(e)}")
        print(f"错误信息: {str(e)}")
        if hasattr(e, 'response'):
            print(f"响应状态码: {e.response.status_code}")
            print(f"响应内容: {e.response.text}")
        print("========================\n")
        return True

    try:
        # 如果模型决定使用工具
        if response.choices[0].message.tool_calls:
            tool_calls = response.choices[0].message.tool_calls
            tool_outputs = []

            for tool_call in tool_calls:
                try:
                    func_name = tool_call.function.name
                    args = json.loads(tool_call.function.arguments)
                    print(f"\n正在执行工具: {func_name}")
                    print(f"参数: {args}")
                    if func_name == "get_current_time":
                        result = get_current_time(args.get("timezone", "UTC"))
                    elif func_name == "get_weather":
                        result = get_weather(args["city"])
                    elif func_name == "powershell_command":
                        result = await powershell_command(args["command"])
                    elif func_name == "email_check":
                        result = email_check()
                    elif func_name == "email_details":
                        result = email_details(args["email_id"])
                    elif func_name == "encoding":
                        result = encoding(args["file_name"], args["encoding"])
                    elif func_name == "send_mail":
                        result = send_mail(args["text"], args["receiver"], args["subject"])
                    elif func_name == "R1_opt":
                        result = R1_opt(args["message"])
                    elif func_name == "ssh":
                        result = ssh(args["command"])
                    else:
                        raise ValueError(f"未定义的工具调用: {func_name}")

                    print(f"工具执行结果: {result}")

                except Exception as e:
                    error_msg = f"工具执行失败: {str(e)}"
                    print(f"\n===== 工具执行错误 =====")
                    print(f"工具名称: {func_name}")
                    print(f"错误类型: {type(e)}")
                    print(f"错误信息: {str(e)}")
                    print("========================\n")
                    result = error_msg

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

            try:
                print("\n正在获取最终响应...")
                response = client.chat.completions.create(
                    model="deepseek-chat",
                    messages=messages,
                    temperature=1.3
                )
                print("最终响应获取成功")

            except Exception as e:
                print("\n===== 最终响应错误 =====")
                print(f"错误类型: {type(e)}")
                print(f"错误信息: {str(e)}")
                if hasattr(e, 'response'):
                    print(f"响应状态码: {e.response.status_code}")
                    print(f"响应内容: {e.response.text}")
                print("========================\n")
                return True

        # 如果没有工具调用，直接添加模型的回复
        assistant_message = response.choices[0].message.content
        print("\n小美:", assistant_message)
        messages.append({"role": "assistant", "content": assistant_message})

        # 调用 TTS 函数
        await text_to_speech(assistant_message)

        return True

    except Exception as e:
        print("\n===== 程序执行错误 =====")
        print(f"错误类型: {type(e)}")
        print(f"错误信息: {str(e)}")
        print("========================\n")
        return True


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
        print(f"请求错误: {e}")
        return ""
    except (KeyError, TypeError, ValueError) as e:
        print(f"响应格式错误: {e}")
        return ""
    finally:
        # 延迟删除，或者在下一次循环开始时删除
        try:
            os.remove(temp_file)
        except OSError as e:
            print(f"删除临时文件失败: {e}")

    return ""


if __name__ == "__main__":
    if not os.path.exists("user_information.txt"):
        with open("user_information.txt", "w", encoding="utf-8") as file:
            file.write("用户关键信息表:user_information.txt")
        print(f"文件 '{"user_information.txt"}' 已创建")

    print("程序启动成功")
    while True:
        try:
            print("\n请选择输入方式:")
            print("1. 文本输入")
            print("2. 语音输入")
            choice = input("输入选项(1或2): ").strip()
            
            if choice == '1':
                input_message = input("\n输入消息: ")
            elif choice == '2':
                input_message = recognize_speech()
            else:
                print("无效的选项,请重新输入")
                continue
            
            if input_message:
                should_continue = asyncio.run(main(input_message))
            if not should_continue:
                break
        except KeyboardInterrupt:
            print("\n程序已被用户中断")
            break
        except Exception as e:
            print("\n===== 主程序错误 =====")
            print(f"错误类型: {type(e)}")
            print(f"错误信息: {str(e)}")
            print("=====================\n")