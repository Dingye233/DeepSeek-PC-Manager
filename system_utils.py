import os
import asyncio
import re
import time
import locale
import uuid
import json
from console_utils import print_color, print_success, print_error, print_warning, print_info
from openai import OpenAI

# 读取用户信息
def user_information_read() -> str:
    # 使用用户文档目录作为存储位置
    try:
        user_docs = os.path.join(os.path.expanduser("~"), "Documents", "DeepSeek-PC-Manager")
        if not os.path.exists(user_docs):
            os.makedirs(user_docs)
        
        file_path = os.path.join(user_docs, "user_information.txt")
        
        # 尝试打开文件并读取内容
        if not os.path.exists(file_path):
            # 如果文件不存在，创建一个带默认内容的文件
            with open(file_path, "w", encoding="utf-8") as file:
                file.write("用户关键信息表:user_information.txt\n")
            print(f"已创建用户信息文件: {file_path}")
            
        with open(file_path, "r", encoding="utf-8") as file:
            content = file.read()
        return content
    except FileNotFoundError:
        # 如果文件不存在，捕获异常并返回提示信息
        return f"错误：找不到文件 '{file_path}'，请检查路径是否正确。"
    except Exception as e:
        # 捕获其他可能的异常（如编码错误）
        return f"读取文件时发生错误：{e}"

# 异步获取用户输入
async def get_user_input_async(prompt: str, timeout: int = 30):
    """
    异步获取用户输入，支持超时
    
    Args:
        prompt: 提示用户的文本
        timeout: 等待用户输入的最大秒数，默认30秒
        
    Returns:
        用户输入的文本，如果超时则返回None
    """
    print(f"\n{prompt}")
    print(f"(等待用户输入，{timeout}秒后自动继续...)")
    
    try:
        # 首先尝试使用当前事件循环
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            # 如果没有运行中的循环，创建一个新的
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        # 使用run_in_executor执行阻塞的input函数
        input_task = loop.run_in_executor(None, input, "")
        
        # 等待任务完成，设置超时
        result = await asyncio.wait_for(input_task, timeout=timeout)
        return result
    except asyncio.TimeoutError:
        print(f"\n输入超时，继续执行...")
        return None
    except Exception as e:
        # 直接返回None，不再尝试备用输入方法
        print(f"\n获取用户输入时出错: {str(e)}")
        print(f"系统将继续执行...")
        return None

# PowerShell命令执行
async def powershell_command(command: str, timeout: int = 60) -> str:
    """交互式命令执行函数，LLM直接以用户身份与控制台交互，支持超时设置"""
    # 获取系统默认编码
    system_encoding = locale.getpreferredencoding()
    
    # 命令开始执行时间
    start_time = time.time()

    # 创建更复杂的交互模式检测模式
    interaction_pattern = re.compile(
        r'(?:Overwrite|确认|Enter|输入|密码|passphrase|file name|\[Y/N\]|是否继续|确定要|请输入|Press any key|Press Enter|Confirm|\(y/n\))',
        re.IGNORECASE
    )

    # 创建常见命令结束标志的正则表达式
    completion_pattern = re.compile(
        r'(?:PS [A-Za-z]:\\.*>$|PS>$|PowerShell>$|PS \[.*\]>$|[A-Za-z]:\\.*>$|\$\s*$)',
        re.MULTILINE
    )

    # 只在有交互式提示时才创建OpenAI客户端
    client = None

    # 设置PowerShell使用UTF-8输出
    utf8_command = "$OutputEncoding = [System.Text.Encoding]::UTF8; [Console]::OutputEncoding = [System.Text.Encoding]::UTF8; chcp 65001 | Out-Null; " + command

    # 修改进程创建方式，确保使用UTF-8编码
    proc = await asyncio.create_subprocess_exec(
        "powershell.exe", "-Command", utf8_command,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        limit=1024 * 1024,  # 1MB缓冲区
        env={**os.environ, "PYTHONIOENCODING": "utf-8"}
    )

    output = []
    error = []
    buffer = ''
    context_buffer = []  # 存储上下文信息，用于LLM分析
    
    last_output_time = time.time()  # 记录最后一次有输出的时间
    
    max_console_output = 500  # 限制控制台输出的最大字符数
    current_output_length = 0
    interaction_count = 0  # 跟踪交互次数
    
    # 命令执行状态
    command_activity = {
        "has_output": False,       # 是否有输出
        "last_chunk_time": time.time(),  # 最后一次收到输出的时间
        "inactivity_threshold": 5,  # 无活动阈值（秒），减少等待时间
        "command_completed": False,  # 命令是否已完成
        "no_output_counter": 0,      # 连续无输出计数
        "is_timeout": False,         # 是否已超时
        "timeout_reason": ""         # 超时原因
    }

    # 尝试多种编码的解码函数 - 使用缓存减少重复解码尝试
    encoding_cache = {}
    def try_decode(byte_data):
        cache_key = hash(byte_data)
        if cache_key in encoding_cache:
            return encoding_cache[cache_key]
            
        # 优先尝试UTF-8和GBK编码
        encodings = ['utf-8', 'gbk', 'gb18030', 'cp936', system_encoding]
        
        # 先快速检查是否有编码问题标志
        tmp_result = None
        try:
            tmp_result = byte_data.decode('utf-8', errors='replace')
        except:
            pass
            
        # 如果检测到可能的乱码字符，使用特殊处理
        if tmp_result and any(pattern in tmp_result for pattern in ['å', 'ç', 'é', '™', 'è', 'æ', 'ÿ']):
            try:
                # 尝试双重转码修复
                result = byte_data.decode('latin-1').encode('latin-1').decode('utf-8', errors='replace')
                encoding_cache[cache_key] = result
                return result
            except:
                pass
                
        # 正常尝试各种编码
        for encoding in encodings:
            try:
                result = byte_data.decode(encoding)
                encoding_cache[cache_key] = result
                return result
            except UnicodeDecodeError:
                continue
                
        # 如果所有编码都失败，使用latin-1（不会失败但可能显示不正确）
        result = byte_data.decode('latin-1')
        encoding_cache[cache_key] = result
        return result

    async def analyze_command_status(buffer_text):
        """使用简单的正则表达式分析命令是否已完成执行"""
        # 首先使用正则表达式检查是否有完成标志
        if completion_pattern.search(buffer_text[-100:] if len(buffer_text) > 100 else buffer_text):
            return True, "检测到PowerShell提示符", 0.9
            
        # 检查是否长时间无输出 - 简化判断逻辑
        if time.time() - command_activity["last_chunk_time"] > command_activity["inactivity_threshold"]:
            # 检查命令输出是否以可能的结束字符串结尾
            last_lines = buffer_text.strip().split('\n')[-3:]
            for line in last_lines:
                line = line.strip()
                if line and not line.startswith('>') and not interaction_pattern.search(line):
                    # 最后一行不是提示符相关，可能是命令输出的结束
                    return True, "检测到可能的命令完成（长时间无输出）", 0.7
                    
        # 仅在有明确的交互式提示或特定情况下才使用LLM
        if interaction_pattern.search(buffer_text[-200:]):
            # 仅在需要时初始化客户端
            nonlocal client
            if not client:
                client = OpenAI(api_key=os.environ.get("api_key"), base_url="https://api.deepseek.com")
                
            # 提取最近的输出内容进行分析
            recent_output = buffer_text[-300:] if len(buffer_text) > 300 else buffer_text
            
            # 简化系统消息
            system_message = """判断PowerShell命令是否已完成执行。分析输出内容，寻找结束迹象或交互提示。
            以JSON格式返回：{"completed": true/false, "reasoning": "分析理由", "confidence": 0-1之间}"""
            
            llm_prompt = f"""
            命令: {command}
            最近输出:
            {recent_output}
            最后输出时间: {int(time.time() - command_activity['last_chunk_time'])}秒前
            请分析这个命令是否已经完成执行。
            """
            
            try:
                response = client.chat.completions.create(
                    model="deepseek-chat",
                    messages=[
                        {"role": "system", "content": system_message},
                        {"role": "user", "content": llm_prompt}
                    ],
                    temperature=0.1,
                    max_tokens=200
                )
                
                suggestion = response.choices[0].message.content
                
                # 尝试解析JSON响应
                try:
                    # 从响应中提取JSON部分
                    json_match = re.search(r'({.*})', suggestion, re.DOTALL)
                    if json_match:
                        result = json.loads(json_match.group(1))
                        return result.get("completed", False), result.get("reasoning", "无分析"), result.get("confidence", 0.5)
                    else:
                        # 从文本响应中提取可能的判断
                        if "命令已完成" in suggestion or "已完成执行" in suggestion:
                            return True, "文本分析显示命令可能已完成", 0.6
                        elif "命令仍在执行" in suggestion or "正在运行" in suggestion:
                            return False, "文本分析显示命令仍在运行", 0.6
                        else:
                            return False, "无法从LLM响应中提取明确结论", 0.3
                except json.JSONDecodeError:
                    # 如果JSON解析失败，根据文本内容进行简单判断
                    if "已完成" in suggestion or "完成执行" in suggestion:
                        return True, "文本分析显示命令可能已完成", 0.5
                    return False, "JSON解析失败，默认认为命令仍在执行", 0.3
                    
            except Exception as e:
                print_warning(f"命令状态分析出错，继续执行")
                return False, f"分析失败", 0.0
        
        # 默认情况下认为命令仍在执行
        return False, "默认继续执行", 0.5
        
    async def get_llm_suggestion(prompt_text, context):
        """使用LLM作为用户代理分析交互提示并给出响应"""
        # 只在需要时创建客户端
        nonlocal client
        if not client:
            client = OpenAI(api_key=os.environ.get("api_key"), base_url="https://api.deepseek.com")
            
        try:
            # 准备当前上下文信息，减少上下文长度
            context_str = "\n".join(context[-5:])  # 只使用最近的5行上下文
            
            # 简化系统消息
            system_message = """作为用户代理与PowerShell交互：1.理解命令上下文 2.分析交互提示 3.提供合适的用户响应
            以JSON格式返回：{"response": "响应内容", "confidence": 0-1之间, "needs_user_input": true/false}"""
            
            llm_prompt = f"""
            命令: {command}
            上下文:
            {context_str}
            当前提示: {prompt_text}
            请以用户身份分析并给出响应。
            """
            
            response = client.chat.completions.create(
                model="deepseek-chat",
                messages=[
                    {"role": "system", "content": system_message},
                    {"role": "user", "content": llm_prompt}
                ],
                temperature=0.2,
                max_tokens=300
            )
            
            suggestion = response.choices[0].message.content
            
            # 尝试解析JSON响应
            try:
                # 从响应中提取JSON部分
                json_match = re.search(r'({.*})', suggestion, re.DOTALL)
                if json_match:
                    result = json.loads(json_match.group(1))
                    needs_user = result.get("needs_user_input", False)
                    return (
                        result.get("response", "y"), 
                        result.get("confidence", 0.5),
                        needs_user
                    )
                else:
                    # 提取文本中的建议响应
                    return "y", 0.2, False
            except json.JSONDecodeError:
                # JSON解析失败，使用默认值
                return "y", 0.2, False
                
        except Exception as e:
            print_warning(f"获取LLM建议时出错")
            return "y", 0.0, False

    # 删除monitor_console_activity函数，不再使用多线程监控
    
    async def watch_output(stream, is_stderr=False):
        """异步读取输出流，不限制控制台输出，实时显示所有内容"""
        nonlocal buffer, current_output_length, context_buffer, last_output_time
        
        # 定义一个计数器，用于跟踪连续空闲周期的数量
        idle_cycles = 0
        last_check_time = time.time()
        check_interval = 2  # 秒
        
        while True:
            # 检查是否超时
            if (time.time() - start_time) > timeout:
                command_activity["is_timeout"] = True
                command_activity["timeout_reason"] = f"命令执行超过了设定的{timeout}秒超时时间"
                print_warning(f"\n命令执行超时（{timeout}秒）")
                break
            
            try:
                # 非阻塞读取，设置超时
                try:
                    chunk = await asyncio.wait_for(stream.read(100), timeout=1.0)
                except asyncio.TimeoutError:
                    # 无数据可读
                    idle_cycles += 1
                    
                    # 更新当前时间
                    current_time = time.time()
                    
                    # 检查是否已经有一段时间没有输出
                    if command_activity['has_output'] and (current_time - command_activity['last_chunk_time'] > command_activity['inactivity_threshold']):
                        # 每隔check_interval秒检查一次命令是否完成
                        if current_time - last_check_time >= check_interval and idle_cycles >= 3:
                            last_check_time = current_time
                            
                            # 如果有足够的输出内容，使用LLM分析命令是否已完成
                            if len(buffer) > 20:  # 至少有一些内容可以分析
                                is_completed, reason, confidence = await analyze_command_status(buffer)
                                
                                if is_completed and confidence >= 0.7:
                                    # 静默完成
                                    command_activity['command_completed'] = True
                                    return
                            
                    # 继续下一个循环
                    continue
                
                # 重置空闲周期和无输出计数器
                idle_cycles = 0
                command_activity['no_output_counter'] = 0
                
                if not chunk:
                    break

                # 更新活动时间戳
                last_output_time = time.time()
                command_activity['last_chunk_time'] = time.time()
                command_activity['has_output'] = True

                # 使用多编码尝试解码
                decoded = try_decode(chunk)

                # 直接输出所有内容，不做任何限制
                print(decoded, end='', flush=True)

                # 保存完整输出用于LLM摘要
                buffer += decoded
                if is_stderr:
                    error.append(decoded)
                else:
                    output.append(decoded)
                
                # 添加到上下文缓冲区
                context_lines = decoded.split('\n')
                for line in context_lines:
                    if line.strip():
                        context_buffer.append(line.strip())
                        if len(context_buffer) > 50:  # 保留最近50行上下文
                            context_buffer.pop(0)

                # 检测命令提示符，表示命令可能已完成
                if re.search(completion_pattern, decoded):
                    command_activity['command_completed'] = True
                    # 但不立即返回，继续处理一段时间，确保没有后续输出

                # 检测到交互提示
                interaction_match = interaction_pattern.search(buffer)
                if interaction_match:
                    interaction_count += 1
                    # 提取交互提示上下文
                    interaction_context = buffer[-200:] if len(buffer) > 200 else buffer
                    
                    # 获取LLM的响应建议
                    response, confidence, needs_user_input = await get_llm_suggestion(interaction_context, context_buffer)
                    
                    if needs_user_input:
                        # 需要用户提供特定信息
                        print_info(f"\n需要您提供：")
                        user_input = await get_user_input_async("请输入: ", 30)
                    elif confidence > 0.7:  # 提高置信度阈值
                        # 高置信度时，直接模拟用户输入
                        print(f"> {response}")
                        user_input = response
                    else:
                        # 置信度较低时，询问用户确认
                        print_info(f"\n建议响应: {response}")
                        print("\n回车接受建议，或输入您的响应: ", end='', flush=True)
                        
                        # 等待用户输入，超时则使用建议值
                        loop = asyncio.get_running_loop()
                        try:
                            custom_input = await asyncio.wait_for(
                                loop.run_in_executor(None, input), 
                                timeout=20  # 增加超时时间
                            )
                            user_input = custom_input.strip() if custom_input.strip() else response
                        except asyncio.TimeoutError:
                            print(f"\n> {response} (自动使用)")
                            user_input = response

                    # 尝试使用多种编码发送
                    try:
                        proc.stdin.write(f"{user_input}\n".encode('utf-8'))
                    except:
                        proc.stdin.write(f"{user_input}\n".encode(system_encoding))

                    await proc.stdin.drain()
                    buffer = ''  # 清空缓冲区，避免重复处理同一交互提示

            except Exception as e:
                print_warning(f"读取输出时出错: {str(e)}")
                break

    # 创建输出监控任务
    stdout_task = asyncio.create_task(watch_output(proc.stdout))
    stderr_task = asyncio.create_task(watch_output(proc.stderr, True))

    try:
        # 等待命令完成或超时
        while True:
            # 检查命令是否已完成或超时
            if command_activity['command_completed'] or command_activity['is_timeout']:
                # 给一点额外时间收集最后的输出
                await asyncio.sleep(1.0)
                break
                
            # 检查进程状态
            if proc.returncode is not None:
                break
                
            # 检查命令状态但不设置超时
            if command_activity['has_output'] and (time.time() - last_output_time > 30):
                # 如果超过30秒无输出，询问LLM命令状态
                if len(buffer) > 20:  # 确保有足够内容进行分析
                    is_completed, reason, confidence = await analyze_command_status(buffer)
                    
                    if is_completed and confidence >= 0.7:
                        print_info(f"\n分析结果: 命令可能已完成 ({reason})")
                        command_activity['command_completed'] = True
                        break
            
            # 避免频繁检查导致CPU使用率过高
            await asyncio.sleep(0.5)
        
    finally:
        # 取消监控任务
        stdout_task.cancel()
        stderr_task.cancel()
        
        try:
            await stdout_task
        except asyncio.CancelledError:
            pass
        
        try:
            await stderr_task
        except asyncio.CancelledError:
            pass
            
        # 如果进程仍在运行，杀掉它
        if proc.returncode is None:
            try:
                proc.terminate()
                await asyncio.wait_for(proc.wait(), timeout=5.0)
            except (asyncio.TimeoutError, ProcessLookupError):
                try:
                    proc.kill()
                except ProcessLookupError:
                    pass

    # 检查是否因超时而终止
    if command_activity['is_timeout']:
        # 分析可能的超时原因
        timeout_analysis = "超时原因: "
        
        if not command_activity['has_output']:
            timeout_analysis += "命令没有任何输出，可能是命令无效或需要更长时间才能开始产生输出。"
        elif time.time() - command_activity['last_chunk_time'] > 30:
            timeout_analysis += f"命令在{int(time.time() - command_activity['last_chunk_time'])}秒前停止输出，但未完成。可能是陷入了等待状态或处理大量数据。"
        elif interaction_count > 0:
            timeout_analysis += f"命令涉及{interaction_count}次交互，可能在等待某些无法自动处理的用户输入。"
        else:
            timeout_analysis += "命令执行时间超过预期，可能是处理大量数据或执行复杂计算。"
        
        # 将超时信息添加到结果中
        buffer += f"\n\n{'-'*50}\n[系统] 命令执行超时 ({timeout}秒)。{timeout_analysis}\n{'-'*50}\n"
    
    # 限制输出长度，避免token超限
    MAX_CHARS = 30000
    if len(buffer) > MAX_CHARS:
        # 生成输出摘要
        summary = generate_output_summary(buffer, client)
        
        # 截取最后的部分
        truncated_buffer = buffer[-MAX_CHARS:]
        # 找到第一个完整行的开始位置
        first_newline = truncated_buffer.find('\n')
        if first_newline > 0:
            truncated_buffer = truncated_buffer[first_newline+1:]
        
        # 添加截断提示和摘要
        truncated_buffer = f"\n===== 输出摘要 =====\n{summary}\n===================\n\n... [输出过长，已截断前面 {len(buffer) - MAX_CHARS} 个字符] ...\n" + truncated_buffer
        print_warning(f"输出过长（{len(buffer)} 字符），已自动截断并生成摘要")
        return truncated_buffer
        
    return buffer

# 生成命令输出摘要
def generate_output_summary(output, client):
    """使用LLM生成命令输出的摘要"""
    try:
        # 提取输出的前后部分用于分析
        head = output[:2000] if len(output) > 2000 else output
        tail = output[-2000:] if len(output) > 4000 else output[len(head):]
        
        # 构建提示
        prompt = f"""以下是一个控制台命令的输出内容，请简要总结其中的关键信息（200字以内）。
特别注意：
1. 错误信息和警告
2. 操作结果和成功状态
3. 重要的数据或统计信息
4. 任何异常情况

输出内容前部分:
```
{head}
```

{f"输出内容后部分(总长度约 {len(output)} 字符):" if len(output) > 4000 else ""}
{f"```\\n{tail}\\n```" if len(output) > 4000 else ""}

请提供简洁的摘要，重点关注关键信息和操作结果。
"""
        
        # 调用API生成摘要
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": "你是一个专业的命令输出分析助手，擅长提取和总结控制台输出中的关键信息。"},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,
            max_tokens=300
        )
        
        summary = response.choices[0].message.content
        return summary
    
    except Exception as e:
        print_error(f"生成输出摘要失败: {str(e)}")
        return "无法生成输出摘要，可能是由于文本过长或API错误。"

# CMD命令执行
async def cmd_command(command: str, timeout: int = 60) -> str:
    """命令行命令执行函数，支持超时设置"""
    # 获取系统默认编码
    system_encoding = locale.getpreferredencoding()
    
    # 命令开始执行时间
    start_time = time.time()

    # 创建命令行交互模式检测模式
    interaction_pattern = re.compile(
        r'(?:Overwrite|确认|Enter|输入|密码|passphrase|file name|\[Y/N\]|是否继续|确定要|请输入|Press any key|Press Enter|Confirm|\(y/n\))',
        re.IGNORECASE
    )

    # 创建常见命令结束标志的正则表达式
    completion_pattern = re.compile(
        r'(?:[A-Za-z]:\\.*>$|[\\/][a-zA-Z0-9_\.\-]*>$)',
        re.MULTILINE
    )

    # 只在有交互式提示时才创建OpenAI客户端
    client = None

    # 修改命令以设置UTF-8编码模式
    utf8_command = "chcp 65001 && " + command

    # 使用更好的进程创建设置
    proc = await asyncio.create_subprocess_exec(
        "cmd.exe", "/c", utf8_command,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        limit=1024 * 1024,  # 1MB缓冲区
        env={**os.environ, "PYTHONIOENCODING": "utf-8"}
    )

    output = []
    error = []
    buffer = ''
    context_buffer = []  # 存储上下文信息，用于LLM分析
    
    last_output_time = time.time()  # 记录最后一次有输出的时间
    
    max_console_output = 500  # 限制控制台输出的最大字符数
    current_output_length = 0
    
    # 命令执行状态
    command_activity = {
        "has_output": False,       # 是否有输出
        "last_chunk_time": time.time(),  # 最后一次收到输出的时间
        "inactivity_threshold": 5,  # 无活动阈值（秒）
        "command_completed": False,  # 命令是否已完成
    }

    # 使用增强版解码函数
    def try_decode(byte_data):
        cache_key = hash(byte_data)
        if hasattr(try_decode, 'cache') and cache_key in try_decode.cache:
            return try_decode.cache[cache_key]
            
        # 优先尝试UTF-8和GBK编码
        encodings = ['utf-8', 'gbk', 'gb18030', 'cp936', system_encoding]
        
        # 先快速检查是否有编码问题标志
        tmp_result = None
        try:
            tmp_result = byte_data.decode('utf-8', errors='replace')
        except:
            pass
            
        # 如果检测到可能的乱码字符，使用特殊处理
        if tmp_result and any(pattern in tmp_result for pattern in ['å', 'ç', 'é', '™', 'è', 'æ', 'ÿ']):
            try:
                # 尝试双重转码修复
                result = byte_data.decode('latin-1').encode('latin-1').decode('utf-8', errors='replace')
                if not hasattr(try_decode, 'cache'):
                    try_decode.cache = {}
                try_decode.cache[cache_key] = result
                return result
            except:
                pass
        
        for encoding in encodings:
            try:
                result = byte_data.decode(encoding)
                if not hasattr(try_decode, 'cache'):
                    try_decode.cache = {}
                try_decode.cache[cache_key] = result
                return result
            except UnicodeDecodeError:
                continue
                
        # 如果所有编码都失败，使用替换模式的UTF-8
        result = byte_data.decode('utf-8', errors='replace')
        if not hasattr(try_decode, 'cache'):
            try_decode.cache = {}
        try_decode.cache[cache_key] = result
        return result

    async def analyze_command_status(buffer_text):
        """使用LLM分析命令是否已完成执行"""
        try:
            # 检查是否有完成标志
            if completion_pattern.search(buffer_text[-100:] if len(buffer_text) > 100 else buffer_text):
                return True, "检测到CMD提示符", 0.9
            
            # 提取最近的输出内容进行分析
            recent_output = buffer_text[-500:] if len(buffer_text) > 500 else buffer_text
            
            system_message = """作为用户助手，你需要判断CMD命令是否已完成执行。
            你的任务是：
            1. 理解CMD命令的执行特征
            2. 分析输出内容，寻找表示命令已完成的迹象
            3. 判断是否还在等待更多输出或正在进行中的操作
            4. 对于长时间运行但有规律输出的命令，判断是否处于正常运行状态
            5. 识别可能的错误状态或卡死状态
            
            以JSON格式返回：{"completed": true/false, "reasoning": "分析理由", "confidence": 0-1之间的数值}
            """
            
            llm_prompt = f"""
            当前执行的命令: {command}
            
            最近的命令输出:
            {recent_output}
            
            最后输出时间: {int(time.time() - command_activity['last_chunk_time'])}秒前
            
            请分析这个命令是否已经完成执行，或者是否还在正常运行中。
            """
            
            response = client.chat.completions.create(
                model="deepseek-chat",
                messages=[
                    {"role": "system", "content": system_message},
                    {"role": "user", "content": llm_prompt}
                ],
                temperature=0.1,
                max_tokens=300
            )
            
            suggestion = response.choices[0].message.content
            
            # 尝试解析JSON响应
            try:
                # 从响应中提取JSON部分
                json_match = re.search(r'({.*})', suggestion, re.DOTALL)
                if json_match:
                    result = json.loads(json_match.group(1))
                    return result.get("completed", False), result.get("reasoning", "无分析"), result.get("confidence", 0.5)
                else:
                    # 从文本响应中提取可能的判断
                    if "命令已完成" in suggestion or "已完成执行" in suggestion:
                        return True, "文本分析显示命令可能已完成", 0.6
                    elif "命令仍在执行" in suggestion or "正在运行" in suggestion:
                        return False, "文本分析显示命令仍在运行", 0.6
                    else:
                        return False, "无法从LLM响应中提取明确结论", 0.3
            except json.JSONDecodeError:
                # 如果JSON解析失败，根据文本内容进行简单判断
                if "已完成" in suggestion or "完成执行" in suggestion:
                    return True, "文本分析显示命令可能已完成", 0.5
                return False, "JSON解析失败，默认认为命令仍在执行", 0.3
                
        except Exception as e:
            print_warning(f"命令状态分析出错，继续执行")
            return False, f"分析失败", 0.0
        
    async def get_llm_suggestion(prompt_text, context):
        """使用LLM作为用户代理分析交互提示并给出响应"""
        try:
            # 准备当前上下文信息
            context_str = "\n".join(context[-10:])  # 最近的10行上下文
            
            system_message = """你现在是用户的代理，直接代表用户与CMD控制台交互。
            你的任务是：
            1. 理解当前命令执行的上下文
            2. 分析控制台交互提示的含义
            3. 直接提供最合适的用户响应内容，就像你就是用户一样
            4. 对于确认类操作(y/n)，基于常识和安全性判断如何回应
            5. 对于文件操作确认，判断是否安全并给出回应
            6. 如果提示需要输入特定信息但无法从上下文推断，明确说明需要用户提供什么信息
            
            以JSON格式返回：{"response": "响应内容", "reasoning": "分析理由(仅内部参考)", "confidence": 0-1之间的数值, "needs_user_input": true/false, "missing_info": "缺失的信息描述"}
            """
            
            llm_prompt = f"""
            当前执行的命令: {command}
            
            最近的命令输出上下文:
            {context_str}
            
            当前控制台提示: {prompt_text}
            
            请以用户身份分析这个提示，并直接给出你会输入的响应。如果缺少关键信息无法回答，请明确说明需要用户提供什么信息。
            """
            
            response = client.chat.completions.create(
                model="deepseek-chat",
                messages=[
                    {"role": "system", "content": system_message},
                    {"role": "user", "content": llm_prompt}
                ],
                temperature=0.2,
                max_tokens=500
            )
            
            suggestion = response.choices[0].message.content
            
            # 尝试解析JSON响应
            try:
                # 从响应中提取JSON部分
                json_match = re.search(r'({.*})', suggestion, re.DOTALL)
                if json_match:
                    result = json.loads(json_match.group(1))
                    needs_user = result.get("needs_user_input", False)
                    missing_info = result.get("missing_info", "")
                    return (
                        result.get("response", "y"), 
                        result.get("reasoning", "无分析"), 
                        result.get("confidence", 0.5),
                        needs_user,
                        missing_info
                    )
                else:
                    # 提取文本中的建议响应
                    return "y", "无法解析JSON响应", 0.2, False, ""
            except json.JSONDecodeError:
                # JSON解析失败，使用默认值
                return "y", "JSON解析失败", 0.2, False, ""
                
        except Exception as e:
            print_warning(f"获取LLM建议时出错")
            return "y", f"错误: {str(e)}", 0.0, False, ""

    # 删除monitor_console_activity函数，不再使用多线程监控
    
    async def watch_output(stream, is_stderr=False):
        """异步读取输出流，不限制控制台输出，实时显示所有内容"""
        nonlocal buffer, current_output_length, context_buffer, last_output_time
        
        # 定义一个计数器，用于跟踪连续空闲周期的数量
        idle_cycles = 0
        last_check_time = time.time()
        check_interval = 2  # 秒
        
        while True:
            # 检查是否超时
            if (time.time() - start_time) > timeout:
                command_activity["is_timeout"] = True
                command_activity["timeout_reason"] = f"命令执行超过了设定的{timeout}秒超时时间"
                print_warning(f"\n命令执行超时（{timeout}秒）")
                break
            
            try:
                # 非阻塞读取，设置超时
                try:
                    chunk = await asyncio.wait_for(stream.read(100), timeout=1.0)
                except asyncio.TimeoutError:
                    # 无数据可读
                    idle_cycles += 1
                    
                    # 更新当前时间
                    current_time = time.time()
                    
                    # 检查是否已经有一段时间没有输出
                    if command_activity['has_output'] and (current_time - command_activity['last_chunk_time'] > command_activity['inactivity_threshold']):
                        # 每隔check_interval秒检查一次命令是否完成
                        if current_time - last_check_time >= check_interval and idle_cycles >= 3:
                            last_check_time = current_time
                            
                            # 如果有足够的输出内容，使用LLM分析命令是否已完成
                            if len(buffer) > 20:  # 至少有一些内容可以分析
                                is_completed, reason, confidence = await analyze_command_status(buffer)
                                
                                if is_completed and confidence >= 0.7:
                                    # 静默完成
                                    command_activity['command_completed'] = True
                                    return
                            
                    # 继续下一个循环
                    continue
                
                # 重置空闲周期和无输出计数器
                idle_cycles = 0
                command_activity['no_output_counter'] = 0
                
                if not chunk:
                    break

                # 更新活动时间戳
                last_output_time = time.time()
                command_activity['last_chunk_time'] = time.time()
                command_activity['has_output'] = True

                # 使用多编码尝试解码
                decoded = try_decode(chunk)

                # 直接输出所有内容，不做任何限制
                print(decoded, end='', flush=True)

                # 保存完整输出用于LLM摘要
                buffer += decoded
                if is_stderr:
                    error.append(decoded)
                else:
                    output.append(decoded)
                
                # 添加到上下文缓冲区
                context_lines = decoded.split('\n')
                for line in context_lines:
                    if line.strip():
                        context_buffer.append(line.strip())
                        if len(context_buffer) > 50:  # 保留最近50行上下文
                            context_buffer.pop(0)

                # 检测命令提示符，表示命令可能已完成
                if re.search(completion_pattern, decoded):
                    command_activity['command_completed'] = True
                    # 但不立即返回，继续处理一段时间，确保没有后续输出

                # 检测到交互提示
                interaction_match = interaction_pattern.search(buffer)
                if interaction_match:
                    interaction_count += 1
                    # 提取交互提示上下文
                    interaction_context = buffer[-200:] if len(buffer) > 200 else buffer
                    
                    # 获取LLM的响应建议
                    response, reasoning, confidence, needs_user_input, missing_info = await get_llm_suggestion(interaction_context, context_buffer)
                    
                    if needs_user_input:
                        # 需要用户提供特定信息
                        print_info(f"\n需要您提供：{missing_info}")
                        user_input = await get_user_input_async("请输入: ", 30)
                    elif confidence > 0.7:  # 提高置信度阈值
                        # 高置信度时，直接模拟用户输入
                        print(f"> {response}")
                        user_input = response
                    else:
                        # 置信度较低时，询问用户确认
                        print_info(f"\n建议响应: {response}")
                        print("\n回车接受建议，或输入您的响应: ", end='', flush=True)
                        
                        # 等待用户输入，超时则使用建议值
                        loop = asyncio.get_running_loop()
                        try:
                            custom_input = await asyncio.wait_for(
                                loop.run_in_executor(None, input), 
                                timeout=20  # 增加超时时间
                            )
                            user_input = custom_input.strip() if custom_input.strip() else response
                        except asyncio.TimeoutError:
                            print(f"\n> {response} (自动使用)")
                            user_input = response

                    # 尝试使用多种编码发送
                    try:
                        proc.stdin.write(f"{user_input}\n".encode('utf-8'))
                    except:
                        proc.stdin.write(f"{user_input}\n".encode(system_encoding))

                    await proc.stdin.drain()
                    buffer = ''  # 清空缓冲区，避免重复处理同一交互提示

            except Exception as e:
                print_warning(f"读取输出时出错: {str(e)}")
                break

    # 创建输出监控任务
    stdout_task = asyncio.create_task(watch_output(proc.stdout))
    stderr_task = asyncio.create_task(watch_output(proc.stderr, True))

    try:
        # 等待命令完成或超时
        while True:
            # 检查命令是否已完成或超时
            if command_activity['command_completed'] or command_activity['is_timeout']:
                # 给一点额外时间收集最后的输出
                await asyncio.sleep(1.0)
                break
                
            # 检查进程状态
            if proc.returncode is not None:
                break
                
            # 检查命令状态但不设置超时
            if command_activity['has_output'] and (time.time() - last_output_time > 30):
                # 如果超过30秒无输出，询问LLM命令状态
                if len(buffer) > 20:  # 确保有足够内容进行分析
                    is_completed, reason, confidence = await analyze_command_status(buffer)
                    
                    if is_completed and confidence >= 0.7:
                        print_info(f"\n分析结果: 命令可能已完成 ({reason})")
                        command_activity['command_completed'] = True
                        break
            
            # 避免频繁检查导致CPU使用率过高
            await asyncio.sleep(0.5)
        
    finally:
        # 取消监控任务
        stdout_task.cancel()
        stderr_task.cancel()
        
        try:
            await stdout_task
        except asyncio.CancelledError:
            pass
        
        try:
            await stderr_task
        except asyncio.CancelledError:
            pass
            
        # 如果进程仍在运行，杀掉它
        if proc.returncode is None:
            try:
                proc.terminate()
                await asyncio.wait_for(proc.wait(), timeout=5.0)
            except (asyncio.TimeoutError, ProcessLookupError):
                try:
                    proc.kill()
                except ProcessLookupError:
                    pass

    # 检查是否因超时而终止
    if command_activity['is_timeout']:
        # 分析可能的超时原因
        timeout_analysis = "超时原因: "
        
        if not command_activity['has_output']:
            timeout_analysis += "命令没有任何输出，可能是命令无效或需要更长时间才能开始产生输出。"
        elif time.time() - command_activity['last_chunk_time'] > 30:
            timeout_analysis += f"命令在{int(time.time() - command_activity['last_chunk_time'])}秒前停止输出，但未完成。可能是陷入了等待状态或处理大量数据。"
        elif interaction_count > 0:
            timeout_analysis += f"命令涉及{interaction_count}次交互，可能在等待某些无法自动处理的用户输入。"
        else:
            timeout_analysis += "命令执行时间超过预期，可能是处理大量数据或执行复杂计算。"
        
        # 将超时信息添加到结果中
        buffer += f"\n\n{'-'*50}\n[系统] 命令执行超时 ({timeout}秒)。{timeout_analysis}\n{'-'*50}\n"
    
    # 限制输出长度，避免token超限
    MAX_CHARS = 30000
    if len(buffer) > MAX_CHARS:
        # 生成输出摘要
        summary = generate_output_summary(buffer, client)
        
        # 截取最后的部分
        truncated_buffer = buffer[-MAX_CHARS:]
        # 找到第一个完整行的开始位置
        first_newline = truncated_buffer.find('\n')
        if first_newline > 0:
            truncated_buffer = truncated_buffer[first_newline+1:]
        
        # 添加截断提示和摘要
        truncated_buffer = f"\n===== 输出摘要 =====\n{summary}\n===================\n\n... [输出过长，已截断前面 {len(buffer) - MAX_CHARS} 个字符] ...\n" + truncated_buffer
        print_warning(f"输出过长（{len(buffer)} 字符），已自动截断并生成摘要")
        return truncated_buffer
        
    return buffer 