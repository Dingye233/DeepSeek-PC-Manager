from openai import OpenAI
import json
from datetime import datetime, timedelta
import asyncio
import edge_tts
from playsound import playsound
import os
import tempfile
import requests
import get_email
import speech_recognition as sr
import keyboard
import time

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
from tts_http_demo import tts_volcano
import uuid
import code_tools  # 导入新的代码工具模块
import tiktoken  # 添加tiktoken用于计算token

load_dotenv()
message_queue = Queue()

# 添加一个token计数函数
def num_tokens_from_messages(messages, model="deepseek-chat"):
    """
    计算消息列表中的token数量
    :param messages: 消息列表
    :param model: 模型名称
    :return: token数量
    """
    try:
        encoding = tiktoken.encoding_for_model("gpt-3.5-turbo")  # 使用兼容的编码方式
        
        num_tokens = 0
        for message in messages:
            # 每条消息的基础token数
            num_tokens += 4  # 每条消息有固定的开销
            
            for key, value in message.items():
                if key == "role" or key == "name":
                    num_tokens += len(encoding.encode(value)) + 1
                elif key == "content":
                    if value is not None:
                        num_tokens += len(encoding.encode(value))
                elif key == "tool_calls":
                    num_tokens += 4  # tool_calls字段的固定开销
                    for tool_call in value:
                        if isinstance(tool_call, dict):
                            # 处理工具调用的各个字段
                            for tc_key, tc_value in tool_call.items():
                                if tc_key == "function":
                                    # 处理函数字段
                                    for f_key, f_value in tc_value.items():
                                        if isinstance(f_value, str):
                                            num_tokens += len(encoding.encode(f_value))
                                else:
                                    if isinstance(tc_value, str):
                                        num_tokens += len(encoding.encode(tc_value))
        
        # 添加模型的基础token数
        num_tokens += 3  # 基础的token开销
        return num_tokens
    except Exception as e:
        print_warning(f"计算token数量时出错: {str(e)}")
        # 如果无法计算，返回一个估计值
        return sum(len(str(m.get("content", ""))) for m in messages) // 3

# 清理不重要的消息历史
def clean_message_history(messages, max_tokens=30000):
    """
    清理消息历史，保留重要信息并减少token数量
    :param messages: 消息列表
    :param max_tokens: 目标token数量
    :return: 清理后的消息列表
    """
    if num_tokens_from_messages(messages) <= max_tokens:
        return messages
    
    print_warning(f"\n===== Token数量超过阈值，正在清理消息历史 =====")
    
    # 保留system消息
    system_messages = [msg for msg in messages if msg["role"] == "system"]
    
    # 获取用户最后的消息
    recent_user_messages = [msg for msg in messages if msg["role"] == "user"][-2:]
    
    # 获取所有助手消息，并保留最近的回复
    assistant_messages = [msg for msg in messages if msg["role"] == "assistant"]
    recent_assistant = assistant_messages[-1:] if assistant_messages else []
    
    # 保留最重要的工具调用和结果
    tool_calls = []
    tool_results = []
    
    for i, msg in enumerate(messages):
        # 保留最近的工具调用
        if msg["role"] == "assistant" and msg.get("tool_calls") and i >= len(messages) - 10:
            tool_calls.append(msg)
        
        # 保留对应的结果
        if msg["role"] == "tool" and i >= len(messages) - 10:
            # 限制工具结果的长度
            if "content" in msg and isinstance(msg["content"], str) and len(msg["content"]) > 500:
                # 只保留前300个字符和后200个字符
                msg = msg.copy()
                msg["content"] = msg["content"][:300] + "\n...[内容已截断]...\n" + msg["content"][-200:]
            tool_results.append(msg)
    
    # 组合清理后的消息
    cleaned_messages = system_messages + recent_user_messages + recent_assistant + tool_calls + tool_results
    
    # 如果仍然超过限制，继续减少工具结果的内容
    if num_tokens_from_messages(cleaned_messages) > max_tokens:
        for i, msg in enumerate(cleaned_messages):
            if msg["role"] == "tool" and "content" in msg and isinstance(msg["content"], str):
                # 进一步限制内容
                cleaned_messages[i] = msg.copy()
                cleaned_messages[i]["content"] = msg["content"][:100] + "\n...[大部分内容已省略]...\n" + msg["content"][-100:]
    
    current_tokens = num_tokens_from_messages(cleaned_messages)
    print_info(f"清理后token数量: {current_tokens} (目标: {max_tokens})")
    
    return cleaned_messages

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
            "description":"管理远程ubuntu服务器",
            "parameters":{
                "type":"object",
                "properties":{
                    "command":{

                        "type":"string",
                        "description":"输入ubuntu服务器的命令"
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
            "description": "创建指定文件并写入内容，返回一个该文件的绝对路径",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_name": {
                        "type": "string",
                        "description": "输入要创建的文件的名字和后缀 如:xxx.txt xxxx.py"
                    },
                    "encoding": {
                        "type": "string",
                        "description": "输入文件的内容"
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
            "description":"调用深度思考模型r1来解决棘手问题",
            "parameters": {
                "type": "object",
                "properties": {
                    "message": {
                        "type": "string",
                        "description":"输入棘手的问题"
                    }
                },
                "required": ["message"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "clear_context",
            "description": "清除对话历史上下文，只保留系统消息",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "write_code",
            "description": "将代码写入指定文件，支持所有编程语言",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_name": {
                        "type": "string",
                        "description": "文件名，包括路径和扩展名，例如 'app.py' 或 'src/utils.js'"
                    },
                    "code": {
                        "type": "string",
                        "description": "要写入文件的代码内容"
                    }
                },
                "required": ["file_name", "code"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "verify_code",
            "description": "验证Python代码的语法是否正确",
            "parameters": {
                "type": "object",
                "properties": {
                    "code": {
                        "type": "string",
                        "description": "要验证的Python代码"
                    }
                },
                "required": ["code"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "append_code",
            "description": "向现有文件追加代码内容",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_name": {
                        "type": "string",
                        "description": "文件名，包括路径和扩展名"
                    },
                    "content": {
                        "type": "string",
                        "description": "要追加的代码内容"
                    }
                },
                "required": ["file_name", "content"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "read_code",
            "description": "读取代码文件内容",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_name": {
                        "type": "string",
                        "description": "文件名，包括路径和扩展名"
                    }
                },
                "required": ["file_name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "create_module",
            "description": "创建包含多个函数的Python模块",
            "parameters": {
                "type": "object",
                "properties": {
                    "module_name": {
                        "type": "string",
                        "description": "模块名称(不含.py)"
                    },
                    "functions_json": {
                        "type": "string",
                        "description": "函数定义的JSON字符串数组，每个函数包含name、params、body和docstring"
                    }
                },
                "required": ["module_name", "functions_json"]
            }
        }
    },
]

client = OpenAI(api_key=os.environ.get("api_key"), base_url="https://api.deepseek.com")


messages = [{"role": "system","content": " 你叫小美，是一个热情的ai助手，这些是用户的一些关键信息，可能有用: "+user_information_read()}, 
{"role": "system","content": " 注意：1.文件操作必须使用绝对路径 2.危险操作要自动添加安全参数 "}]

# 添加任务规划和错误修复
task_planning_system_message = {
    "role": "system",
    "content": """你现在是一个自主规划任务的智能体，请遵循以下原则：
1. 接收到任务后，首先分析任务需求并制定执行计划
2. 将复杂任务分解为可执行的子任务步骤
3. 执行每个步骤并观察结果
4. 如果执行过程中遇到错误或异常，分析错误原因并重新规划解决方案
5. 持续尝试不同方法直到任务成功完成或确定无法完成
6. 任务完成后总结执行过程和结果

执行方式：
- 对于复杂任务，独立思考并自主规划解决方案
- 根据用户输入或环境反馈调整计划
- 使用工具执行具体操作（如执行命令、创建文件等）
- 遇到错误时分析错误信息并自动修正
- 使用循环方式验证任务是否完成，直到成功或确认失败

关键能力：
- 任务分解与规划能力
- 错误检测与自动修复
- 持续尝试与备选方案
- 结果验证与确认
"""
}

# 添加错误处理和重试机制的函数
def parse_error_message(error_message):
    """
    解析错误信息，提取关键信息
    """
    # 常见错误类型及其解决方案
    error_patterns = {
        r'ModuleNotFoundError: No module named [\'\"]?(\w+)[\'\"]?': "缺少依赖模块 {}，需要安装",
        r'ImportError: (\w+)': "导入模块 {} 失败，检查模块名称是否正确",
        r'SyntaxError: (.+)': "代码语法错误: {}，需要修复",
        r'NameError: name [\'\"]?(\w+)[\'\"]? is not defined': "变量 {} 未定义",
        r'AttributeError: [\'\"]?(\w+)[\'\"]?': "属性或方法 {} 不存在",
        r'TypeError: (.+)': "类型错误: {}",
        r'ValueError: (.+)': "值错误: {}",
        r'PermissionError: (.+)': "权限错误: {}，可能需要管理员权限",
        r'FileNotFoundError: (.+)': "文件未找到: {}",
        r'ConnectionError: (.+)': "连接错误: {}，检查网络连接",
        r'Timeout': "操作超时，可能需要延长等待时间或检查连接",
    }
    
    for pattern, solution_template in error_patterns.items():
        match = re.search(pattern, error_message)
        if match:
            return solution_template.format(match.group(1))
    
    return "未能识别的错误: " + error_message

def task_error_analysis(result, task_context):
    """
    分析工具执行结果中的错误，生成修复建议
    """
    if "错误" in result or "Error" in result or "exception" in result.lower() or "failed" in result.lower():
        error_analysis = parse_error_message(result)
        return {
            "has_error": True,
            "error_message": result,
            "analysis": error_analysis,
            "context": task_context
        }
    return {"has_error": False}

async def execute_task_with_planning(user_input, messages_history):
    """
    使用任务规划执行用户请求
    """
    # 添加任务规划系统消息
    planning_messages = messages_history.copy()
    
    # 替换或添加任务规划系统消息
    system_message_index = next((i for i, msg in enumerate(planning_messages) if msg["role"] == "system"), None)
    if system_message_index is not None:
        combined_content = planning_messages[system_message_index]["content"] + "\n\n" + task_planning_system_message["content"]
        planning_messages[system_message_index]["content"] = combined_content
    else:
        planning_messages.insert(0, task_planning_system_message)
    
    # 添加用户输入
    planning_messages.append({"role": "user", "content": f"请完成以下任务，并详细规划执行步骤：{user_input}"})
    
    # 检查token数量
    token_count = num_tokens_from_messages(planning_messages)
    print_info(f"\n===== 初始token数量: {token_count} =====")
    if token_count > 30000:  # 设置30000作为预警阈值
        planning_messages = clean_message_history(planning_messages)
    
    # 获取任务规划
    try:
        planning_response = client.chat.completions.create(
            model="deepseek-chat",
            messages=planning_messages,
            temperature=0.3
        )
        
        task_plan = planning_response.choices[0].message.content
        print("\n===== 任务规划 =====")
        print(task_plan)
        print("====================\n")
        
        # 添加任务规划到对话历史
        planning_messages.append({"role": "assistant", "content": task_plan})
        
        # 执行任务（最多尝试5次）
        max_attempts = 5
        for attempt in range(max_attempts):
            try:
                # 添加执行提示
                execution_prompt = f"现在开始执行任务计划的第{attempt+1}次尝试。请调用适当的工具执行计划中的步骤。"
                if attempt > 0:
                    execution_prompt += f" 这是第{attempt+1}次尝试，前面{attempt}次尝试失败。请根据之前的错误调整策略。"
                
                planning_messages.append({"role": "user", "content": execution_prompt})
                
                # 初始化递归验证
                recursive_verify_count = 0
                max_recursive_verify = 10  # 最大递归验证次数
                is_task_complete = False
                current_execution_messages = planning_messages.copy()
                
                # 内部递归验证循环
                while recursive_verify_count < max_recursive_verify and not is_task_complete:
                    recursive_verify_count += 1
                    print(f"\n===== 任务执行迭代 {recursive_verify_count}/{max_recursive_verify} =====")
                    
                    # 检查当前token数量
                    token_count = num_tokens_from_messages(current_execution_messages)
                    print_info(f"当前token数量: {token_count}")
                    
                    # 如果token数量超过阈值，清理消息历史
                    if token_count > 30000:  # 设置30000作为预警阈值
                        print_warning("Token数量超过预警阈值，清理消息历史...")
                        current_execution_messages = clean_message_history(current_execution_messages)
                    
                    # 调用API执行任务步骤
                    execution_response = client.chat.completions.create(
                        model="deepseek-chat",
                        messages=current_execution_messages,
                        tools=tools,
                        tool_choice="auto",
                        temperature=0.3
                    )
                    
                    message_data = execution_response.choices[0].message
                    
                    # 处理工具调用
                    if hasattr(message_data, 'tool_calls') and message_data.tool_calls:
                        # 执行工具调用并收集结果
                        tool_calls = message_data.tool_calls
                        tool_outputs = []
                        step_success = True
                        
                        # 添加助手消息和工具调用
                        current_execution_messages.append({
                            "role": "assistant",
                            "content": None,
                            "tool_calls": [
                                {
                                    "id": tc.id,
                                    "type": "function",
                                    "function": {
                                        "name": tc.function.name,
                                        "arguments": tc.function.arguments
                                    }
                                } for tc in tool_calls
                            ]
                        })
                        
                        for tool_call in tool_calls:
                            func_name = tool_call.function.name
                            args = json.loads(tool_call.function.arguments)
                            print(f"\n正在执行工具: {func_name}")
                            print(f"参数: {args}")
                            
                            try:
                                # 执行工具函数
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
                                elif func_name == "clear_context":
                                    result = "上下文已清除"
                                    current_execution_messages = clear_context(current_execution_messages)
                                elif func_name == "write_code":
                                    result = code_tools.write_code(args["file_name"], args["code"])
                                elif func_name == "verify_code":
                                    result = code_tools.verify_code(args["code"])
                                elif func_name == "append_code":
                                    result = code_tools.append_code(args["file_name"], args["content"])
                                elif func_name == "read_code":
                                    result = code_tools.read_code(args["file_name"])
                                elif func_name == "create_module":
                                    result = code_tools.create_module(args["module_name"], args["functions_json"])
                                else:
                                    raise ValueError(f"未定义的工具调用: {func_name}")
                                
                                print_success(f"工具执行结果: {result}")
                                
                                # 分析执行结果是否有错误
                                error_info = task_error_analysis(result, {"tool": func_name, "args": args})
                                if error_info["has_error"]:
                                    print_warning(f"\n检测到错误: {error_info['analysis']}")
                                    step_success = False
                                    
                                    # 将错误信息添加到结果中
                                    result = f"{result}\n\n分析: {error_info['analysis']}"
                                    
                                    # 发送错误信息到GUI
                                    if 'message_queue' in globals():
                                        message_queue.put({
                                            "type": "error",
                                            "text": f"工具 {func_name} 执行出错: {error_info['analysis']}"
                                        })
                                
                            except Exception as e:
                                error_msg = f"工具执行失败: {str(e)}"
                                print_error(f"\n===== 工具执行错误 =====")
                                print_error(f"工具名称: {func_name}")
                                print_error(f"错误类型: {type(e)}")
                                print_error(f"错误信息: {str(e)}")
                                print_error("========================\n")
                                result = error_msg
                                step_success = False
                                
                                # 发送错误到GUI
                                if 'message_queue' in globals():
                                    message_queue.put({"type": "error", "text": error_msg})
                            
                            # 添加工具结果到消息历史
                            current_execution_messages.append({
                                "role": "tool",
                                "tool_call_id": tool_call.id,
                                "content": str(result)
                            })
                            
                            # 发送工具结果到GUI
                            if 'message_queue' in globals():
                                message_queue.put({
                                    "type": "tool_result",
                                    "text": f"{func_name} 执行完成"
                                })
                            
                            tool_outputs.append({
                                "tool_call_id": tool_call.id,
                                "output": str(result)
                            })
                        
                        # 验证当前步骤执行后，任务是否完成
                        verify_prompt = """
                        基于目前的执行情况，请分析当前任务的完成状态:
                        1. 任务是否已完全完成？如果完成，请详细说明完成的内容和结果。
                        2. 如果任务未完成，还需要执行哪些步骤？
                        3. 是否存在无法克服的障碍使任务无法继续？
                        
                        请严格按照以下格式回复:
                        {
                            "is_complete": true/false,  // 任务是否完成
                            "completion_status": "简短描述任务状态",
                            "next_steps": ["下一步1", "下一步2"],  // 若任务未完成，下一步需要执行的操作列表
                            "is_failed": true/false,  // 任务是否已失败且无法继续
                            "failure_reason": "若已失败，失败的原因",
                            "environment_status": {  // 当前环境状态
                                "key1": "value1",
                                "key2": "value2"
                            }
                        }
                        """
                        
                        # 在验证前检查token数量
                        token_count = num_tokens_from_messages(current_execution_messages)
                        print_info(f"验证前token数量: {token_count}")
                        if token_count > 30000:
                            print_warning("Token数量超过预警阈值，清理消息历史...")
                            current_execution_messages = clean_message_history(current_execution_messages)
                        
                        current_execution_messages.append({"role": "user", "content": verify_prompt})
                        
                        # 调用验证
                        verify_response = client.chat.completions.create(
                            model="deepseek-chat",
                            messages=current_execution_messages,
                            temperature=0.1
                        )
                        
                        verify_result = verify_response.choices[0].message.content
                        print_info("\n===== 任务验证结果 =====")
                        print(verify_result)
                        print_info("=========================\n")
                        
                        # 添加验证结果到消息历史
                        current_execution_messages.append({"role": "assistant", "content": verify_result})
                        
                        # 解析验证结果
                        try:
                            # 尝试提取JSON部分
                            json_match = re.search(r'({.*})', verify_result, re.DOTALL)
                            if json_match:
                                verify_json = json.loads(json_match.group(1))
                            else:
                                # 如果没有明确的JSON，尝试更灵活的解析
                                verify_json = {
                                    "is_complete": "true" in verify_result.lower() and "完成" in verify_result,
                                    "is_failed": "失败" in verify_result or "无法继续" in verify_result,
                                    "completion_status": verify_result[:100] + "..."  # 简短摘要
                                }
                            
                            # 检查任务是否完成或失败
                            if verify_json.get("is_complete", False) is True:
                                is_task_complete = True
                                print_success("\n✅ 任务已完成! 准备生成总结...")
                                break
                            
                            if verify_json.get("is_failed", False) is True:
                                print_error(f"\n❌ 任务无法继续: {verify_json.get('failure_reason', '未知原因')}")
                                break
                            
                            # 如果任务未完成也未失败，继续下一步
                            next_steps = verify_json.get("next_steps", ["请继续执行任务的下一步骤"])
                            if isinstance(next_steps, list):
                                next_step_text = "\n".join([f"- {step}" for step in next_steps])
                            else:
                                next_step_text = str(next_steps)
                            
                            print_info("\n===== 下一步计划 =====")
                            print_highlight(next_step_text)
                            print_info("======================\n")
                            
                            current_execution_messages.append({
                                "role": "user", 
                                "content": f"任务尚未完成。现在请执行下一步: {next_step_text}"
                            })
                            
                            # 发送验证进度到GUI
                            if 'message_queue' in globals():
                                message_queue.put({
                                    "type": "tool_result",
                                    "text": f"任务进度: {verify_json.get('completion_status', '进行中')}，准备下一步"
                                })
                            
                        except (json.JSONDecodeError, ValueError) as e:
                            print_error(f"验证结果解析失败: {str(e)}")
                            # 如果解析失败，简单继续
                            current_execution_messages.append({
                                "role": "user", 
                                "content": "请继续执行任务的下一步骤。"
                            })
                    else:
                        # 没有工具调用，可能是任务结束或需要进一步指导
                        content = message_data.content
                        current_execution_messages.append({"role": "assistant", "content": content})
                        
                        # 输出消息内容
                        print_info("\n===== 助手消息 =====")
                        print(content)
                        print_info("====================\n")
                        
                        # 检查是否包含完成信息
                        if "任务已完成" in content or "任务完成" in content:
                            is_task_complete = True
                            print_success("\n✅ 任务已完成! 准备生成总结...")
                            break
                        
                        # 如果模型未调用工具但也未完成，提示继续
                        if recursive_verify_count < max_recursive_verify:
                            current_execution_messages.append({
                                "role": "user", 
                                "content": "请继续执行任务，如果需要，请调用相应的工具。"
                            })
                
                # 内部递归结束后，更新外部消息历史
                planning_messages = current_execution_messages.copy()
                
                # 检查任务是否在递归内完成
                if is_task_complete:
                    # 任务成功，获取简洁总结回复
                    planning_messages.append({
                        "role": "user", 
                        "content": "任务执行完成，请简洁总结执行结果（不超过100字）。使用简短句子，避免复杂解释。"
                    })
                    
                    # 最后的总结回复
                    final_response = client.chat.completions.create(
                        model="deepseek-chat",
                        messages=planning_messages,
                        temperature=0.2,
                        max_tokens=150  # 限制token数量
                    )
                    
                    summary = final_response.choices[0].message.content
                    print_info("\n===== 任务执行总结 =====")
                    print_highlight(summary)
                    print_info("========================\n")
                    
                    # 添加到主对话历史
                    messages_history.append({"role": "user", "content": user_input})
                    messages_history.append({"role": "assistant", "content": summary})
                    
                    # 发送总结到GUI
                    if 'message_queue' in globals():
                        message_queue.put({"type": "assistant", "text": summary})
                        message_queue.put({"type": "complete"})
                    
                    return summary
                else:
                    # 任务在内部递归中未完成，添加错误反馈
                    if recursive_verify_count >= max_recursive_verify:
                        iteration_error = f"已达到最大内部验证次数({max_recursive_verify}次)，但任务仍未完成。"
                    else:
                        iteration_error = "执行过程中遇到无法克服的问题，任务未能完成。"
                    
                    planning_messages.append({
                        "role": "user", 
                        "content": f"执行任务时遇到错误。这是第{attempt+1}次尝试，{iteration_error}请分析错误原因并提出改进方案，以便下一次尝试。"
                    })
                    
                    error_analysis_response = client.chat.completions.create(
                        model="deepseek-chat",
                        messages=planning_messages,
                        temperature=0.2
                    )
                    
                    error_analysis = error_analysis_response.choices[0].message.content
                    print_info(f"\n===== 错误分析（尝试 {attempt+1}/{max_attempts}）=====")
                    print_error(error_analysis)
                    print_info("========================\n")
                    
                    # 添加错误分析到对话历史
                    planning_messages.append({"role": "assistant", "content": error_analysis})
                    
                    # 发送错误分析到GUI
                    if 'message_queue' in globals():
                        message_queue.put({
                            "type": "tool_result",
                            "text": f"分析错误并重试（尝试 {attempt+1}/{max_attempts}）"
                        })
                    
                    # 如果是最后一次尝试，返回失败
                    if attempt == max_attempts - 1:
                        failure_message = f"在{max_attempts}次尝试后，任务执行失败。以下是最终分析：\n\n{error_analysis}"
                        
                        # 添加到主对话历史
                        messages_history.append({"role": "user", "content": user_input})
                        messages_history.append({"role": "assistant", "content": failure_message})
                        
                        # 发送失败消息到GUI
                        if 'message_queue' in globals():
                            message_queue.put({"type": "assistant", "text": failure_message})
                            message_queue.put({"type": "complete"})
                        
                        return failure_message
                    
            except Exception as e:
                print_error(f"\n===== 执行错误 =====")
                print_error(f"错误类型: {type(e)}")
                print_error(f"错误信息: {str(e)}")
                print_error("===================\n")
                
                # 发送错误到GUI
                if 'message_queue' in globals():
                    message_queue.put({
                        "type": "error",
                        "text": f"执行错误: {str(e)}"
                    })
                
                # 如果是最后一次尝试，返回失败
                if attempt == max_attempts - 1:
                    error_message = f"执行任务时出现系统错误: {str(e)}"
                    
                    # 添加到主对话历史
                    messages_history.append({"role": "user", "content": user_input})
                    messages_history.append({"role": "assistant", "content": error_message})
                    
                    # 发送错误消息到GUI
                    if 'message_queue' in globals():
                        message_queue.put({"type": "assistant", "text": error_message})
                        message_queue.put({"type": "complete"})
                    
                    return error_message
        
    except Exception as e:
        error_message = f"任务规划失败: {str(e)}"
        print_error(f"\n===== 规划错误 =====")
        print_error(error_message)
        print_error("===================\n")
        
        # 添加到主对话历史
        messages_history.append({"role": "user", "content": user_input})
        messages_history.append({"role": "assistant", "content": error_message})
        
        # 发送规划错误到GUI
        if 'message_queue' in globals():
            message_queue.put({"type": "error", "text": error_message})
            message_queue.put({"type": "complete"})
        
        return error_message

# check_model_message=[{"role": "system",
#          "content": "你是任务审查模型，需要审查用户的任务是否被模型完成，如果没有完成则补充下一步该干什么，最后再让被审查模型继续执行"}]

def clear_context(messages: list) -> list:
    """
    清除对话上下文
    :param messages: 当前的对话历史
    :return: 清空后的对话历史，只保留系统消息
    """
    # 保留系统消息，清除其他消息
    system_messages = [msg for msg in messages if msg["role"] == "system"]
    return system_messages

async def main(input_message: str):
    global messages
    
    if input_message.lower() == 'quit':
        return False

    # 检查是否是清除上下文的命令
    if input_message.lower() in ["清除上下文", "清空上下文", "clear context", "reset context"]:
        messages = clear_context(messages)
        print_info("上下文已清除")
        return "上下文已清除，您可以开始新的对话了。"
        
    # 先尝试常规对话，检查是否需要调用工具
    messages.append({"role": "user", "content": input_message})

    try:
        response = client.chat.completions.create(
            
            model="deepseek-chat",
            messages=messages,
            tools=tools,
            tool_choice="auto",
            temperature=0.3
        )
        
        message_data = response.choices[0].message
        
        # 如果模型决定调用工具，则启动任务规划模式
        if hasattr(message_data, 'tool_calls') and message_data.tool_calls:
            # 回退消息历史，移除刚刚添加的用户消息，因为任务规划会重新添加
            messages.pop()
            print("检测到工具调用，启动任务规划系统...")
            return await execute_task_with_planning(input_message, messages)
        else:
            # 如果不需要调用工具，直接处理普通回复
            assistant_message = message_data.content
            print(assistant_message)
            messages.append({"role": "assistant", "content": assistant_message})
            
            # 发送到GUI队列
            if 'message_queue' in globals():
                message_queue.put({"type": "assistant", "text": assistant_message})
                message_queue.put({"type": "complete"})
            
            return assistant_message

    except Exception as e:
        # 将错误信息发送到GUI队列
        error_msg = f"API错误: {str(e)}"
        if 'message_queue' in globals():
            message_queue.put({"type": "error", "text": error_msg})
        
        # 使用任务规划作为备选方案
        messages.pop()  # 移除刚才添加的消息
        print("常规对话失败，切换到任务规划系统...")
        return await execute_task_with_planning(input_message, messages)


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

def reset_messages():
    """重置消息历史到初始状态"""
    global messages
    messages = [{"role": "system","content": " 你叫小美，是一个热情的ai助手，这些是用户的一些关键信息，可能有用: "+user_information_read()}] 

def tts(text:str):
    tts_volcano(text)

# 添加颜色打印函数
def print_color(text, color_code):
    """使用颜色代码打印文本"""
    print(f"\033[{color_code}m{text}\033[0m")

def print_success(text):
    """打印成功消息（绿色）"""
    print_color(text, "32")

def print_error(text):
    """打印错误消息（红色）"""
    print_color(text, "31")

def print_warning(text):
    """打印警告消息（黄色）"""
    print_color(text, "33")

def print_info(text):
    """打印信息消息（蓝色）"""
    print_color(text, "36")

def print_highlight(text):
    """打印高亮消息（紫色）"""
    print_color(text, "35")

if __name__ == "__main__":
    if not os.path.exists("user_information.txt"):
        with open("user_information.txt", "w", encoding="utf-8") as file:
            file.write("用户关键信息表:user_information.txt")
        print(f"文件 '{"user_information.txt"}' 已创建")

    print("程序启动成功")
    while True:
        try:
            input_message = input("\n输入消息: ")
            
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