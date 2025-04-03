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
        # 创建一个任务来执行用户输入
        loop = asyncio.get_event_loop()
        input_task = loop.run_in_executor(None, input, "")
        
        # 等待任务完成，设置超时
        result = await asyncio.wait_for(input_task, timeout=timeout)
        return result
    except asyncio.TimeoutError:
        print(f"\n输入超时，继续执行...")
        return None
    except Exception as e:
        print(f"\n获取用户输入时出错: {str(e)}")
        return None

# PowerShell命令执行
async def powershell_command(command: str) -> str:
    """改进后的交互式命令执行函数，LLM直接以用户身份与控制台交互，支持动态超时"""
    # 获取系统默认编码
    system_encoding = locale.getpreferredencoding()

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

    # 创建OpenAI客户端
    client = OpenAI(api_key=os.environ.get("api_key"), base_url="https://api.deepseek.com")

    # 设置PowerShell使用UTF-8输出
    utf8_command = "$OutputEncoding = [System.Text.Encoding]::UTF8; [Console]::OutputEncoding = [System.Text.Encoding]::UTF8; " + command

    proc = await asyncio.create_subprocess_exec(
        "powershell.exe", "-Command", utf8_command,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        limit=1024 * 1024  # 1MB缓冲区
    )

    output = []
    error = []
    buffer = ''
    context_buffer = []  # 存储上下文信息，用于LLM分析
    
    # 动态超时机制
    base_timeout = 240  # 基础超时时间
    max_timeout = 600   # 最大超时时间
    timeout = base_timeout
    
    last_active = time.time()
    last_output_time = time.time()  # 记录最后一次有输出的时间
    
    max_console_output = 500  # 限制控制台输出的最大字符数
    current_output_length = 0
    interaction_count = 0  # 跟踪交互次数
    
    # 命令执行状态
    command_activity = {
        "has_output": False,       # 是否有输出
        "last_chunk_time": time.time(),  # 最后一次收到输出的时间
        "inactivity_threshold": 10,  # 无活动阈值（秒）
        "command_completed": False,  # 命令是否已完成
        "no_output_counter": 0      # 连续无输出计数
    }

    # 尝试多种编码的解码函数
    def try_decode(byte_data):
        encodings = ['utf-8', 'gbk', 'gb18030', 'cp936', system_encoding]
        for encoding in encodings:
            try:
                return byte_data.decode(encoding)
            except UnicodeDecodeError:
                continue
        # 如果所有编码都失败，使用latin-1（不会失败但可能显示不正确）
        return byte_data.decode('latin-1')

    async def get_user_input_async(prompt):
        """异步获取用户输入"""
        print(prompt, end='', flush=True)
        loop = asyncio.get_running_loop()
        user_input = await loop.run_in_executor(None, input)
        return user_input
        
    async def analyze_command_status(buffer_text):
        """使用LLM分析命令是否已完成执行"""
        try:
            # 检查是否有完成标志
            if completion_pattern.search(buffer_text[-100:] if len(buffer_text) > 100 else buffer_text):
                return True, "检测到PowerShell提示符", 0.9
            
            # 提取最近的输出内容进行分析
            recent_output = buffer_text[-500:] if len(buffer_text) > 500 else buffer_text
            
            system_message = """作为用户助手，你需要判断PowerShell命令是否已完成执行。
            你的任务是：
            1. 理解PowerShell命令的执行特征
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
            
            system_message = """你现在是用户的代理，直接代表用户与PowerShell交互。
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
                    # 从文本响应中提取可能的回答
                    response_match = re.search(r'response":\s*"([^"]+)"', suggestion)
                    needs_user = "needs_user_input.*?true" in suggestion or "缺少" in suggestion or "缺失" in suggestion
                    missing_info = ""
                    
                    if "missing_info" in suggestion:
                        info_match = re.search(r'missing_info":\s*"([^"]+)"', suggestion)
                        if info_match:
                            missing_info = info_match.group(1)
                    
                    if response_match:
                        return response_match.group(1), "部分解析", 0.3, needs_user, missing_info
                    else:
                        return "y", "无法提取明确的响应", 0.1, needs_user, missing_info
            except json.JSONDecodeError:
                # 如果JSON解析失败，尝试直接从文本中提取建议
                needs_user = "需要用户" in suggestion or "缺少信息" in suggestion or "缺失信息" in suggestion
                missing_info = ""
                
                if "缺少" in suggestion or "缺失" in suggestion:
                    info_match = re.search(r'(?:缺少|缺失)[：:]\s*(.+?)[\n\.]', suggestion)
                    if info_match:
                        missing_info = info_match.group(1)
                
                if "建议输入" in suggestion or "应该输入" in suggestion:
                    match = re.search(r'(?:建议|应该)输入[：:]\s*(.+?)[\n\.]', suggestion)
                    return match.group(1) if match else "y", "文本提取", 0.2, needs_user, missing_info
                return "y", "解析失败，使用默认确认", 0.1, needs_user, missing_info
                
        except Exception as e:
            print_warning("响应生成出错，使用默认回应")
            return "y", f"调用失败", 0.0, False, ""

    async def watch_output(stream, is_stderr=False):
        """异步读取输出流，限制控制台输出，实现智能命令完成检测"""
        nonlocal buffer, last_active, current_output_length, context_buffer, interaction_count, last_output_time
        
        # 定义一个计数器，用于跟踪连续空闲周期的数量
        idle_cycles = 0
        last_check_time = time.time()
        check_interval = 2  # 秒
        
        while True:
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
                                
                            # 如果空闲周期过多，增加无输出计数器
                            command_activity['no_output_counter'] += 1
                            
                            # 如果长时间无输出且无交互，可能是卡死
                            if command_activity['no_output_counter'] >= 10 and interaction_count == 0:
                                print_warning("\n命令长时间无响应，可能已卡死")
                                return
                    
                    # 继续下一个循环
                    continue
                
                # 重置空闲周期和无输出计数器
                idle_cycles = 0
                command_activity['no_output_counter'] = 0
                
                if not chunk:
                    break

                # 更新活动时间戳
                last_active = time.time()
                last_output_time = time.time()
                command_activity['last_chunk_time'] = time.time()
                command_activity['has_output'] = True

                # 使用多编码尝试解码
                decoded = try_decode(chunk)

                # 限制控制台输出
                if current_output_length < max_console_output:
                    # 计算可以打印的字符数量
                    printable_len = min(len(decoded), max_console_output - current_output_length)
                    print(decoded[:printable_len], end='', flush=True)
                    current_output_length += printable_len

                    # 如果这次输出导致达到了限制，打印提示信息
                    if current_output_length >= max_console_output and printable_len < len(decoded):
                        print("\n... (输出较多，已省略部分内容) ...", flush=True)

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
                        user_input = await get_user_input_async("请输入: ")
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
                    last_active = time.time()

            except Exception as e:
                print_warning(f"读取输出时出错: {str(e)}")
                break

    # 创建输出监控任务
    stdout_task = asyncio.create_task(watch_output(proc.stdout))
    stderr_task = asyncio.create_task(watch_output(proc.stderr, True))

    try:
        # 自适应超时检测循环
        while True:
            # 检查命令是否已完成
            if command_activity['command_completed']:
                # 给一点额外时间收集最后的输出
                await asyncio.sleep(1.0)
                break
                
            # 检查进程状态
            if proc.returncode is not None:
                break
                
            # 计算已运行时间
            elapsed_time = time.time() - last_active
            
            # 根据交互次数和输出情况动态调整超时
            if interaction_count > 0:
                # 有交互的命令，增加超时时间
                adjusted_timeout = min(base_timeout + (interaction_count * 60), max_timeout)
            else:
                adjusted_timeout = base_timeout
                
            # 如果长时间无输出，可能是卡死或需要额外处理
            if command_activity['has_output'] and (time.time() - last_output_time > 30):
                # 如果超过30秒无输出，询问LLM命令状态
                if len(buffer) > 20:  # 确保有足够内容进行分析
                    is_completed, reason, confidence = await analyze_command_status(buffer)
                    
                    if is_completed and confidence >= 0.7:
                        # 静默完成
                        await asyncio.sleep(2.0)
                        break
                        
            # 检查是否超时
            if elapsed_time > adjusted_timeout:
                print_warning(f"\n命令执行时间已超过 {adjusted_timeout} 秒")
                raise asyncio.TimeoutError()

            await asyncio.sleep(0.5)  # 减少检查频率，降低CPU使用

    except asyncio.TimeoutError:
        print_warning("\n命令执行超时，正在终止")
        proc.terminate()
        return f"错误：命令执行超时（超过{timeout}秒）"

    finally:
        # 取消输出监控任务
        if not stdout_task.done():
            stdout_task.cancel()
        if not stderr_task.done():
            stderr_task.cancel()
        
        try:
            await stdout_task
        except asyncio.CancelledError:
            pass
        try:
            await stderr_task
        except asyncio.CancelledError:
            pass

    # 收集最终输出
    stdout = ''.join(output).strip()
    stderr = ''.join(error).strip()

    # 检查是否有乱码
    def contains_garbled(text):
        # 检测常见乱码模式
        garbled_patterns = [
            r'\uFFFD+',  # 替换字符
            r'',  # 常见乱码模式
            r'([^\x00-\x7F])\1{3,}'  # 重复的非ASCII字符
        ]
        for pattern in garbled_patterns:
            if re.search(pattern, text):
                return True
        return False

    # 如果检测到乱码，添加一个特殊提示到LLM的输入中
    garbled_warning = ""
    if contains_garbled(stdout):
        garbled_warning = "注意：输出中可能包含中文乱码，请在总结中说明这一点。"
        
    interaction_info = f"命令执行过程中有{interaction_count}次交互" if interaction_count > 0 else ""

    # 只有在有实际输出且执行成功的情况下进行处理
    if proc.returncode == 0 and stdout:
        # 检查输出长度是否超过5000字符
        if len(stdout) > 5000:
            try:
                # 给LLM的提示语
                prompt = f"""
                请简洁总结以下命令执行结果，突出重要信息，忽略冗余内容：
                命令: {command}
                {garbled_warning}
                {interaction_info}
                输出:
                {stdout[:4000] if len(stdout) > 4000 else stdout}

                如果发现中文乱码，请在总结中明确指出，并尝试猜测可能的文件名或内容。
                """

                # 调用LLM进行摘要
                response = client.chat.completions.create(
                    model="deepseek-chat",
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.3
                )

                summary = response.choices[0].message.content
                # 返回LLM摘要，不包含完整输出
                return f"""
## 命令执行成功 (输出较多，已生成摘要):

{summary}
"""
            except Exception as e:
                # LLM调用失败时返回原始输出
                return f"执行成功 (输出较长):\n{stdout[:1000]}...(输出过长，已截断)"
        else:
            # 输出少于5000字符，直接返回原始输出
            return f"## 命令执行成功:\n{stdout}"
    elif proc.returncode == 0:
        return f"命令执行成功（无输出）"
    else:
        error_msg = stderr or "未知错误"
        # 对错误信息也进行长度限制
        if len(error_msg) > 1000:
            error_msg = error_msg[:1000] + "..."
        return f"命令执行失败（错误码 {proc.returncode}）:\n{error_msg}"

# 列出目录内容
async def list_directory(path="."):
    """特殊处理列出目录内容的函数，确保中文文件名正确显示"""
    # 使用专门的命令和编码设置来确保中文文件名正确显示
    command = f'''
    $OutputEncoding = [Console]::OutputEncoding = [System.Text.Encoding]::UTF8;
    Get-ChildItem -Path "{path}" | ForEach-Object {{
        [PSCustomObject]@{{
            Name = $_.Name
            Type = if($_.PSIsContainer) {{ "Directory" }} else {{ "File" }}
            Size = if(!$_.PSIsContainer) {{ $_.Length }} else {{ "N/A" }}
            LastModified = $_.LastWriteTime
        }}
    }} | ConvertTo-Json -Depth 1
    '''
    return await powershell_command(command)

# CMD命令执行
async def cmd_command(command: str) -> str:
    """CMD控制台的交互式命令执行函数，LLM直接以用户身份与控制台交互，支持动态超时"""
    # 获取系统默认编码
    system_encoding = locale.getpreferredencoding()

    # 创建更复杂的交互模式检测模式
    interaction_pattern = re.compile(
        r'(?:Overwrite|确认|Enter|输入|密码|passphrase|file name|\[Y/N\]|是否继续|确定要|请输入|Press any key|Press Enter|Confirm|\(y/n\)|Are you sure|继续执行|\(Y/N\))',
        re.IGNORECASE
    )
    
    # 创建常见命令结束标志的正则表达式
    completion_pattern = re.compile(
        r'(?:[A-Za-z]:\\.*>$|C:\\.*>$|D:\\.*>$|E:\\.*>$|F:\\.*>$|Microsoft Windows.*>$)',
        re.MULTILINE
    )

    # 创建OpenAI客户端
    client = OpenAI(api_key=os.environ.get("api_key"), base_url="https://api.deepseek.com")

    # 设置CMD使用UTF-8输出
    # 使用chcp 65001命令切换到UTF-8编码
    utf8_command = "chcp 65001 > nul && " + command

    proc = await asyncio.create_subprocess_exec(
        "cmd.exe", "/c", utf8_command,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        limit=1024 * 1024  # 1MB缓冲区
    )

    output = []
    error = []
    buffer = ''
    context_buffer = []  # 存储上下文信息，用于LLM分析
    
    # 动态超时机制
    base_timeout = 240  # 基础超时时间
    max_timeout = 600   # 最大超时时间
    timeout = base_timeout
    
    last_active = time.time()
    last_output_time = time.time()  # 记录最后一次有输出的时间
    
    max_console_output = 500  # 限制控制台输出的最大字符数
    current_output_length = 0
    interaction_count = 0  # 跟踪交互次数
    
    # 命令执行状态
    command_activity = {
        "has_output": False,       # 是否有输出
        "last_chunk_time": time.time(),  # 最后一次收到输出的时间
        "inactivity_threshold": 10,  # 无活动阈值（秒）
        "command_completed": False,  # 命令是否已完成
        "no_output_counter": 0      # 连续无输出计数
    }

    # 尝试多种编码的解码函数
    def try_decode(byte_data):
        encodings = ['utf-8', 'gbk', 'gb18030', 'cp936', system_encoding]
        for encoding in encodings:
            try:
                return byte_data.decode(encoding)
            except UnicodeDecodeError:
                continue
        # 如果所有编码都失败，使用latin-1（不会失败但可能显示不正确）
        return byte_data.decode('latin-1')

    async def get_user_input_async(prompt):
        """异步获取用户输入"""
        print(prompt, end='', flush=True)
        loop = asyncio.get_running_loop()
        user_input = await loop.run_in_executor(None, input)
        return user_input
    
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
                    # 从文本响应中提取可能的回答
                    response_match = re.search(r'response":\s*"([^"]+)"', suggestion)
                    needs_user = "needs_user_input.*?true" in suggestion or "缺少" in suggestion or "缺失" in suggestion
                    missing_info = ""
                    
                    if "missing_info" in suggestion:
                        info_match = re.search(r'missing_info":\s*"([^"]+)"', suggestion)
                        if info_match:
                            missing_info = info_match.group(1)
                    
                    if response_match:
                        return response_match.group(1), "部分解析", 0.3, needs_user, missing_info
                    else:
                        return "y", "无法提取明确的响应", 0.1, needs_user, missing_info
            except json.JSONDecodeError:
                # 如果JSON解析失败，尝试直接从文本中提取建议
                needs_user = "需要用户" in suggestion or "缺少信息" in suggestion or "缺失信息" in suggestion
                missing_info = ""
                
                if "缺少" in suggestion or "缺失" in suggestion:
                    info_match = re.search(r'(?:缺少|缺失)[：:]\s*(.+?)[\n\.]', suggestion)
                    if info_match:
                        missing_info = info_match.group(1)
                
                if "建议输入" in suggestion or "应该输入" in suggestion:
                    match = re.search(r'(?:建议|应该)输入[：:]\s*(.+?)[\n\.]', suggestion)
                    return match.group(1) if match else "y", "文本提取", 0.2, needs_user, missing_info
                return "y", "解析失败，使用默认确认", 0.1, needs_user, missing_info
                
        except Exception as e:
            print_warning("响应生成出错，使用默认回应")
            return "y", f"调用失败", 0.0, False, ""

    async def watch_output(stream, is_stderr=False):
        """异步读取输出流，限制控制台输出，实现智能命令完成检测"""
        nonlocal buffer, last_active, current_output_length, context_buffer, interaction_count, last_output_time
        
        # 定义一个计数器，用于跟踪连续空闲周期的数量
        idle_cycles = 0
        last_check_time = time.time()
        check_interval = 2  # 秒
        
        while True:
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
                                
                            # 如果空闲周期过多，增加无输出计数器
                            command_activity['no_output_counter'] += 1
                            
                            # 如果长时间无输出且无交互，可能是卡死
                            if command_activity['no_output_counter'] >= 10 and interaction_count == 0:
                                print_warning("\n命令长时间无响应，可能已卡死")
                                return
                    
                    # 继续下一个循环
                    continue
                
                # 重置空闲周期和无输出计数器
                idle_cycles = 0
                command_activity['no_output_counter'] = 0
                
                if not chunk:
                    break

                # 更新活动时间戳
                last_active = time.time()
                last_output_time = time.time()
                command_activity['last_chunk_time'] = time.time()
                command_activity['has_output'] = True

                # 使用多编码尝试解码
                decoded = try_decode(chunk)

                # 限制控制台输出
                if current_output_length < max_console_output:
                    # 计算可以打印的字符数量
                    printable_len = min(len(decoded), max_console_output - current_output_length)
                    print(decoded[:printable_len], end='', flush=True)
                    current_output_length += printable_len

                    # 如果这次输出导致达到了限制，打印提示信息
                    if current_output_length >= max_console_output and printable_len < len(decoded):
                        print("\n... (输出较多，已省略部分内容) ...", flush=True)

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
                        user_input = await get_user_input_async("请输入: ")
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
                    last_active = time.time()

            except Exception as e:
                print_warning(f"读取输出时出错: {str(e)}")
                break

    # 创建输出监控任务
    stdout_task = asyncio.create_task(watch_output(proc.stdout))
    stderr_task = asyncio.create_task(watch_output(proc.stderr, True))

    try:
        # 自适应超时检测循环
        while True:
            # 检查命令是否已完成
            if command_activity['command_completed']:
                # 给一点额外时间收集最后的输出
                await asyncio.sleep(1.0)
                break
                
            # 检查进程状态
            if proc.returncode is not None:
                break
                
            # 计算已运行时间
            elapsed_time = time.time() - last_active
            
            # 根据交互次数和输出情况动态调整超时
            if interaction_count > 0:
                # 有交互的命令，增加超时时间
                adjusted_timeout = min(base_timeout + (interaction_count * 60), max_timeout)
            else:
                adjusted_timeout = base_timeout
                
            # 如果长时间无输出，可能是卡死或需要额外处理
            if command_activity['has_output'] and (time.time() - last_output_time > 30):
                # 如果超过30秒无输出，询问LLM命令状态
                if len(buffer) > 20:  # 确保有足够内容进行分析
                    is_completed, reason, confidence = await analyze_command_status(buffer)
                    
                    if is_completed and confidence >= 0.7:
                        # 静默完成
                        await asyncio.sleep(2.0)
                        break
                        
            # 检查是否超时
            if elapsed_time > adjusted_timeout:
                print_warning(f"\n命令执行时间已超过 {adjusted_timeout} 秒")
                raise asyncio.TimeoutError()

            await asyncio.sleep(0.5)  # 减少检查频率，降低CPU使用

    except asyncio.TimeoutError:
        print_warning("\n命令执行超时，正在终止")
        proc.terminate()
        return f"错误：命令执行超时（超过{timeout}秒）"

    finally:
        # 取消输出监控任务
        if not stdout_task.done():
            stdout_task.cancel()
        if not stderr_task.done():
            stderr_task.cancel()
        
        try:
            await stdout_task
        except asyncio.CancelledError:
            pass
        try:
            await stderr_task
        except asyncio.CancelledError:
            pass

    # 收集最终输出
    stdout = ''.join(output).strip()
    stderr = ''.join(error).strip()

    # 检查是否有乱码
    def contains_garbled(text):
        # 检测常见乱码模式
        garbled_patterns = [
            r'\uFFFD+',  # 替换字符
            r'',  # 常见乱码模式
            r'([^\x00-\x7F])\1{3,}'  # 重复的非ASCII字符
        ]
        for pattern in garbled_patterns:
            if re.search(pattern, text):
                return True
        return False

    # 如果检测到乱码，添加一个特殊提示到LLM的输入中
    garbled_warning = ""
    if contains_garbled(stdout):
        garbled_warning = "注意：输出中可能包含中文乱码，请在总结中说明这一点。"
        
    interaction_info = f"命令执行过程中有{interaction_count}次交互" if interaction_count > 0 else ""

    # 只有在有实际输出且执行成功的情况下进行处理
    if proc.returncode == 0 and stdout:
        # 检查输出长度是否超过5000字符
        if len(stdout) > 5000:
            try:
                # 给LLM的提示语
                prompt = f"""
                请简洁总结以下命令执行结果，突出重要信息，忽略冗余内容：
                命令: {command}
                {garbled_warning}
                {interaction_info}
                输出:
                {stdout[:4000] if len(stdout) > 4000 else stdout}

                如果发现中文乱码，请在总结中明确指出，并尝试猜测可能的文件名或内容。
                """

                # 调用LLM进行摘要
                response = client.chat.completions.create(
                    model="deepseek-chat",
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.3
                )

                summary = response.choices[0].message.content
                # 返回LLM摘要，不包含完整输出
                return f"""
## 命令执行成功 (输出较多，已生成摘要):

{summary}
"""
            except Exception as e:
                # LLM调用失败时返回原始输出
                return f"执行成功 (输出较长):\n{stdout[:1000]}...(输出过长，已截断)"
        else:
            # 输出少于5000字符，直接返回原始输出
            return f"## 命令执行成功:\n{stdout}"
    elif proc.returncode == 0:
        return f"命令执行成功（无输出）"
    else:
        error_msg = stderr or "未知错误"
        # 对错误信息也进行长度限制
        if len(error_msg) > 1000:
            error_msg = error_msg[:1000] + "..."
        return f"命令执行失败（错误码 {proc.returncode}）:\n{error_msg}" 