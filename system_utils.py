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
    """改进后的交互式命令执行函数，带LLM智能交互和自动响应功能"""
    # 获取系统默认编码
    system_encoding = locale.getpreferredencoding()

    # 创建更复杂的交互模式检测模式
    interaction_pattern = re.compile(
        r'(?:Overwrite|确认|Enter|输入|密码|passphrase|file name|\[Y/N\]|是否继续|确定要|请输入|Press any key|Press Enter|Confirm|\(y/n\))',
        re.IGNORECASE
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
    timeout = 240
    last_active = time.time()
    max_console_output = 500  # 限制控制台输出的最大字符数
    current_output_length = 0
    interaction_count = 0  # 跟踪交互次数

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
        
    async def get_llm_suggestion(prompt_text, context):
        """使用LLM分析交互提示并给出建议响应"""
        try:
            # 准备当前上下文信息
            context_str = "\n".join(context[-10:])  # 最近的10行上下文
            
            system_message = """分析PowerShell的交互提示，并给出最合适的响应。
            你的任务是：
            1. 理解当前命令执行的上下文
            2. 分析交互提示的含义和期望的输入
            3. 提供最合适的回应以继续执行任务
            4. 对于确认类操作(y/n)，根据上下文判断是否应该继续
            5. 对于文件操作确认，判断是否安全并给出合理建议
            
            以JSON格式返回：{"response": "建议的响应内容", "reasoning": "分析理由", "confidence": 0-1之间的数值}
            """
            
            llm_prompt = f"""
            当前执行的命令: {command}
            
            最近的命令输出上下文:
            {context_str}
            
            当前交互提示: {prompt_text}
            
            请分析这个交互提示，并根据上下文给出最佳的响应建议。
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
                    return result.get("response", "y"), result.get("reasoning", "无分析"), result.get("confidence", 0.5)
                else:
                    # 从文本响应中提取可能的回答
                    response_match = re.search(r'response":\s*"([^"]+)"', suggestion)
                    if response_match:
                        return response_match.group(1), "部分解析", 0.3
                    else:
                        return "y", "无法从LLM响应中提取JSON", 0.1
            except json.JSONDecodeError:
                # 如果JSON解析失败，尝试直接从文本中提取建议
                if "建议输入" in suggestion:
                    match = re.search(r'建议输入[：:]\s*(.+?)[\n\.]', suggestion)
                    return match.group(1) if match else "y", "文本提取", 0.2
                return "y", "JSON解析失败", 0.1
                
        except Exception as e:
            print(f"LLM分析失败: {str(e)}")
            return "y", f"LLM调用失败: {str(e)}", 0.0

    async def watch_output(stream, is_stderr=False):
        """异步读取输出流，限制控制台输出"""
        nonlocal buffer, last_active, current_output_length, context_buffer, interaction_count
        while True:
            try:
                chunk = await stream.read(100)
                if not chunk:
                    break

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

                # 检测到交互提示
                interaction_match = interaction_pattern.search(buffer)
                if interaction_match:
                    interaction_count += 1
                    # 提取交互提示上下文
                    interaction_context = buffer[-200:] if len(buffer) > 200 else buffer
                    
                    # 根据交互次数决定是否使用LLM智能响应
                    auto_respond = True
                    
                    if auto_respond:
                        print("\n检测到需要用户交互...", flush=True)
                        # 使用LLM分析并获取建议响应
                        response, reasoning, confidence = await get_llm_suggestion(interaction_context, context_buffer)
                        
                        if confidence > 0.4:  # 只有当LLM对答案有较高置信度时才自动响应
                            print(f"\n[AI自动响应] {response} (置信度: {confidence:.2f})")
                            print(f"分析: {reasoning}")
                            user_input = response
                        else:
                            # 置信度低，请求用户确认
                            print(f"\n[AI建议] 建议输入: {response} (置信度较低: {confidence:.2f})")
                            print(f"分析: {reasoning}")
                            print("\n是否接受此建议? (直接回车表示接受，或输入自定义响应): ", end='', flush=True)
                            
                            # 等待用户输入，超时使用建议值
                            loop = asyncio.get_running_loop()
                            try:
                                custom_input = await asyncio.wait_for(
                                    loop.run_in_executor(None, input), 
                                    timeout=15
                                )
                                user_input = custom_input.strip() if custom_input.strip() else response
                            except asyncio.TimeoutError:
                                print(f"\n输入超时，使用AI建议的值: {response}")
                                user_input = response
                    else:
                        # 直接请求用户输入
                        user_input = await get_user_input_async("\n请输入响应: ")
                        if user_input is None:
                            # 如果用户没有输入（超时），使用默认值
                            user_input = "y"  # 默认确认
                            print(f"用户未输入，使用默认值: {user_input}")

                    # 尝试使用多种编码发送
                    try:
                        proc.stdin.write(f"{user_input}\n".encode('utf-8'))
                    except:
                        proc.stdin.write(f"{user_input}\n".encode(system_encoding))

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

    # 只有在有实际输出且执行成功的情况下才调用LLM进行摘要
    if proc.returncode == 0 and stdout:
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
            # 返回完整的命令输出和LLM摘要
            return f"""
## 命令执行成功 (完整输出):
{stdout}

## LLM摘要:
{summary}
"""
        except Exception as e:
            # LLM调用失败时返回原始输出
            return f"执行成功 (LLM摘要失败: {str(e)}):\n{stdout}"
    elif proc.returncode == 0:
        return f"命令执行成功（无输出）{interaction_info}"
    else:
        error_msg = stderr or "未知错误"
        # 对错误信息也进行长度限制
        if len(error_msg) > 1000:
            error_msg = error_msg[:1000] + "..."
        return f"命令执行失败（错误码 {proc.returncode}）{interaction_info}:\n{error_msg}"

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
    """CMD控制台的交互式命令执行函数，带LLM智能交互和自动响应功能"""
    # 获取系统默认编码
    system_encoding = locale.getpreferredencoding()

    # 创建更复杂的交互模式检测模式
    interaction_pattern = re.compile(
        r'(?:Overwrite|确认|Enter|输入|密码|passphrase|file name|\[Y/N\]|是否继续|确定要|请输入|Press any key|Press Enter|Confirm|\(y/n\)|Are you sure|继续执行|\(Y/N\))',
        re.IGNORECASE
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
    timeout = 240
    last_active = time.time()
    max_console_output = 500  # 限制控制台输出的最大字符数
    current_output_length = 0
    interaction_count = 0  # 跟踪交互次数

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
        
    async def get_llm_suggestion(prompt_text, context):
        """使用LLM分析交互提示并给出建议响应"""
        try:
            # 准备当前上下文信息
            context_str = "\n".join(context[-10:])  # 最近的10行上下文
            
            system_message = """分析CMD控制台的交互提示，并给出最合适的响应。
            你的任务是：
            1. 理解当前命令执行的上下文
            2. 分析交互提示的含义和期望的输入
            3. 提供最合适的回应以继续执行任务
            4. 对于确认类操作(y/n)，根据上下文判断是否应该继续
            5. 对于文件操作确认，判断是否安全并给出合理建议
            
            以JSON格式返回：{"response": "建议的响应内容", "reasoning": "分析理由", "confidence": 0-1之间的数值}
            """
            
            llm_prompt = f"""
            当前执行的命令: {command}
            
            最近的命令输出上下文:
            {context_str}
            
            当前交互提示: {prompt_text}
            
            请分析这个交互提示，并根据上下文给出最佳的响应建议。
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
                    return result.get("response", "y"), result.get("reasoning", "无分析"), result.get("confidence", 0.5)
                else:
                    # 从文本响应中提取可能的回答
                    response_match = re.search(r'response":\s*"([^"]+)"', suggestion)
                    if response_match:
                        return response_match.group(1), "部分解析", 0.3
                    else:
                        return "y", "无法从LLM响应中提取JSON", 0.1
            except json.JSONDecodeError:
                # 如果JSON解析失败，尝试直接从文本中提取建议
                if "建议输入" in suggestion:
                    match = re.search(r'建议输入[：:]\s*(.+?)[\n\.]', suggestion)
                    return match.group(1) if match else "y", "文本提取", 0.2
                return "y", "JSON解析失败", 0.1
                
        except Exception as e:
            print(f"LLM分析失败: {str(e)}")
            return "y", f"LLM调用失败: {str(e)}", 0.0

    async def watch_output(stream, is_stderr=False):
        """异步读取输出流，限制控制台输出"""
        nonlocal buffer, last_active, current_output_length, context_buffer, interaction_count
        while True:
            try:
                chunk = await stream.read(100)
                if not chunk:
                    break

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

                # 检测到交互提示
                interaction_match = interaction_pattern.search(buffer)
                if interaction_match:
                    interaction_count += 1
                    # 提取交互提示上下文
                    interaction_context = buffer[-200:] if len(buffer) > 200 else buffer
                    
                    # 根据交互次数决定是否使用LLM智能响应
                    auto_respond = True
                    
                    if auto_respond:
                        print("\n检测到需要用户交互...", flush=True)
                        # 使用LLM分析并获取建议响应
                        response, reasoning, confidence = await get_llm_suggestion(interaction_context, context_buffer)
                        
                        if confidence > 0.4:  # 只有当LLM对答案有较高置信度时才自动响应
                            print(f"\n[AI自动响应] {response} (置信度: {confidence:.2f})")
                            print(f"分析: {reasoning}")
                            user_input = response
                        else:
                            # 置信度低，请求用户确认
                            print(f"\n[AI建议] 建议输入: {response} (置信度较低: {confidence:.2f})")
                            print(f"分析: {reasoning}")
                            print("\n是否接受此建议? (直接回车表示接受，或输入自定义响应): ", end='', flush=True)
                            
                            # 等待用户输入，超时使用建议值
                            loop = asyncio.get_running_loop()
                            try:
                                custom_input = await asyncio.wait_for(
                                    loop.run_in_executor(None, input), 
                                    timeout=15
                                )
                                user_input = custom_input.strip() if custom_input.strip() else response
                            except asyncio.TimeoutError:
                                print(f"\n输入超时，使用AI建议的值: {response}")
                                user_input = response
                    else:
                        # 直接请求用户输入
                        user_input = await get_user_input_async("\n请输入响应: ")
                        if user_input is None:
                            # 如果用户没有输入（超时），使用默认值
                            user_input = "y"  # 默认确认
                            print(f"用户未输入，使用默认值: {user_input}")

                    # 尝试使用多种编码发送
                    try:
                        proc.stdin.write(f"{user_input}\n".encode('utf-8'))
                    except:
                        proc.stdin.write(f"{user_input}\n".encode(system_encoding))

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

    # 只有在有实际输出且执行成功的情况下才调用LLM进行摘要
    if proc.returncode == 0 and stdout:
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
            # 返回完整的命令输出和LLM摘要
            return f"""
## 命令执行成功 (完整输出):
{stdout}

## LLM摘要:
{summary}
"""
        except Exception as e:
            # LLM调用失败时返回原始输出
            return f"执行成功 (LLM摘要失败: {str(e)}):\n{stdout}"
    elif proc.returncode == 0:
        return f"命令执行成功（无输出）{interaction_info}"
    else:
        error_msg = stderr or "未知错误"
        # 对错误信息也进行长度限制
        if len(error_msg) > 1000:
            error_msg = error_msg[:1000] + "..."
        return f"命令执行失败（错误码 {proc.returncode}）{interaction_info}:\n{error_msg}" 