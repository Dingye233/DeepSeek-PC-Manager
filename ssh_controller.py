import paramiko
import sys
import time
import re
import asyncio
import json
from typing import Optional, Dict, Any, Tuple
from console_utils import print_color, print_success, print_error, print_warning, print_info
from openai import OpenAI

import os

# 获取API密钥
api_key = os.environ.get("api_key")

async def get_user_input_async(prompt: str, timeout: int = 30) -> Optional[str]:
    """
    异步获取用户输入，支持超时
    
    Args:
        prompt: 提示用户的文本
        timeout: 等待用户输入的最大秒数，默认30秒
        
    Returns:
        用户输入的文本，如果超时则返回None
    """
    print(f"\n{prompt}")
    print(f"(等待输入，{timeout}秒后自动继续...)")
    
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


def ssh_interactive_command(ip, username, password, initial_command):
    """
    交互式SSH命令执行函数，LLM直接以用户身份与远程系统交互，支持动态超时和自动系统识别
    
    Args:
        ip: 远程服务器IP
        username: SSH用户名
        password: SSH密码
        initial_command: 初始执行的命令
    
    Returns:
        命令执行结果或错误信息
    """
    try:
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        
        # 连接信息提示
        print_info(f"正在连接到 {username}@{ip}...")
        
        client.connect(ip, username=username, password=password, timeout=15)

        # 创建交互式shell
        shell = client.invoke_shell()
        shell.settimeout(180)  # 增加命令执行超时时间
        
        print_success("SSH连接成功")

        # 等待shell初始化
        time.sleep(1)
        _clear_buffer(shell)
        
        # 检测远程系统类型
        os_info = detect_remote_os(shell)
        print_info(f"远程系统: {os_info['os_type']} {os_info.get('version', '')}")
        
        # 创建OpenAI客户端用于LLM分析
        llm_client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")
        
        # 设置命令执行上下文
        context = {
            "remote_os": os_info,
            "interaction_count": 0,
            "buffer": [],
            "command_history": [],
            "command_completed": False,
            "last_active": time.time(),
            "last_output_time": time.time(),
            "no_output_counter": 0
        }
        
        # 定义命令提示符模式
        if os_info["os_type"].lower() in ["linux", "unix", "macos", "bsd"]:
            prompt_pattern = re.compile(r'[\$#]\s*$')
        elif os_info["os_type"].lower() == "windows":
            prompt_pattern = re.compile(r'[A-Za-z]:\\.*>\s*$')
        else:
            # 通用模式
            prompt_pattern = re.compile(r'[\$#>]\s*$')

        # 发送初始命令
        if initial_command:
            print(f"> {initial_command}")
            shell.send(initial_command + "\n")
        
        output = []
        context["command_history"].append(initial_command)
        
        # 设置超时机制
        base_timeout = 120  # 基础超时时间
        max_timeout = 600   # 最大超时时间
        timeout = base_timeout

        # 创建事件循环用于处理用户输入
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        start_time = time.time()
        last_check_time = time.time()
        check_interval = 5  # 命令完成检测间隔(秒)
        idle_cycles = 0     # 空闲周期计数
        
        max_console_output = 10000  # 提高控制台输出限制
        current_output_length = 0

        while time.time() - start_time < timeout:
            if shell.recv_ready():
                # 重置空闲周期
                idle_cycles = 0
                context["no_output_counter"] = 0
                
                # 接收数据
                data = shell.recv(4096).decode('utf-8', errors='replace')
                output.append(data)
                
                # 限制控制台输出
                if current_output_length < max_console_output:
                    printable_len = min(len(data), max_console_output - current_output_length)
                    print(data[:printable_len], end='', flush=True)
                    current_output_length += printable_len
                    
                    if current_output_length >= max_console_output and printable_len < len(data):
                        print("\n... (输出较多，已省略部分内容) ...", flush=True)
                
                # 更新上下文
                context["buffer"].append(data)
                if len(context["buffer"]) > 50:
                    context["buffer"] = context["buffer"][-50:]
                
                context["last_active"] = time.time()
                context["last_output_time"] = time.time()
                
                # 检测命令提示符，判断命令是否可能已完成
                if prompt_pattern.search(data.split('\n')[-1]):
                    # 命令可能已完成，但不立即退出，等待一段时间确认没有后续输出
                    context["command_completed"] = True
                
                # 检测是否需要用户输入
                if _need_user_input(data):
                    context["interaction_count"] += 1
                    
                    # 准备当前交互上下文
                    interaction_context = ''.join(context["buffer"][-3:])
                    
                    # 使用LLM分析并生成响应
                    response, reasoning, confidence, needs_user_input, missing_info = _get_llm_response(
                        llm_client, 
                        interaction_context, 
                        context["command_history"], 
                        os_info
                    )
                    
                    if needs_user_input:
                        # 需要用户提供特定信息
                        print_info(f"\n需要您提供：{missing_info}")
                        user_input = loop.run_until_complete(get_user_input_async("请输入: "))
                        if user_input is None:
                            # 如果用户未输入，尝试使用默认值
                            if re.search(r'password', data, re.I):
                                print_warning("\n需要密码但未提供，操作可能失败")
                                user_input = ""
                            elif re.search(r'\[Y/n\]', data, re.I) or re.search(r'\(yes/no\)', data, re.I):
                                user_input = "y"  # 默认确认
                                print(f"> {user_input} (默认)")
                            else:
                                user_input = ""
                                print("> [回车] (默认)")
                    elif confidence > 0.7:
                        # 高置信度，直接模拟用户输入
                        print(f"> {response}")
                        user_input = response
                    else:
                        # 置信度较低，请求用户确认
                        print_info(f"\n建议响应: {response}")
                        print("回车接受建议，或输入您的响应: ", end='', flush=True)
                        
                        try:
                            custom_input = loop.run_until_complete(asyncio.wait_for(
                                loop.run_in_executor(None, input), 
                                timeout=20
                            ))
                            user_input = custom_input.strip() if custom_input.strip() else response
                        except asyncio.TimeoutError:
                            print(f"\n> {response} (自动使用)")
                            user_input = response
                    
                    # 发送响应
                    shell.send(user_input + "\n")
                    
                    # 更新上下文
                    context["last_active"] = time.time()
                    start_time = time.time()  # 重置超时计时器
                
            elif shell.exit_status_ready():
                # SSH会话已结束
                break
            else:
                # 无数据可读，增加空闲周期
                idle_cycles += 1
                time.sleep(0.5)  # 延迟以减少CPU占用
                
                # 当前时间
                current_time = time.time()
                
                # 如果已经有一段时间没有输出
                if current_time - context["last_output_time"] > 10:
                    # 每隔check_interval秒检查一次命令是否完成
                    if current_time - last_check_time >= check_interval and idle_cycles >= 3:
                        last_check_time = current_time
                        
                        # 检查命令是否已完成
                        if context["command_completed"]:
                            # 命令已完成，可以退出循环
                            break
                        
                        # 如果有足够的输出内容，使用LLM分析命令状态
                        buffer_content = ''.join(context["buffer"][-5:])
                        if len(buffer_content) > 20:
                            is_completed, reason, confidence = check_command_completion(
                                llm_client, 
                                buffer_content,
                                initial_command,
                                os_info,
                                int(current_time - context["last_output_time"])
                            )
                            
                            if is_completed and confidence >= 0.7:
                                # 静默完成
                                context["command_completed"] = True
                                # 额外等待以确保没有更多输出
                                time.sleep(1.0)
                                break
                        
                        # 增加无输出计数
                        context["no_output_counter"] += 1
                        
                        # 如果长时间无输出且无交互，可能命令已卡死
                        if context["no_output_counter"] >= 10 and context["interaction_count"] == 0:
                            print_warning("\n命令长时间无响应，可能已卡死")
                            break
                
                # 计算已运行时间
                elapsed_time = time.time() - start_time
                
                # 根据交互次数动态调整超时时间
                if context["interaction_count"] > 0:
                    adjusted_timeout = min(base_timeout + (context["interaction_count"] * 60), max_timeout)
                else:
                    adjusted_timeout = base_timeout
                
                # 检查是否超时
                if elapsed_time > adjusted_timeout:
                    print_warning(f"\n命令执行时间已超过 {adjusted_timeout} 秒")
                    break

        # 获取最终输出
        final_output = ''.join(output).strip()
        
        shell.close()
        client.close()
        
        return final_output or "命令执行完成（无输出）"

    except paramiko.AuthenticationException:
        return "SSH错误: 认证失败，请检查用户名和密码"
    except paramiko.SSHException as e:
        return f"SSH错误: 连接问题 - {str(e)}"
    except Exception as e:
        return f"SSH错误: {str(e)}"


def detect_remote_os(shell) -> Dict[str, Any]:
    """
    检测远程系统类型和版本
    
    Args:
        shell: SSH交互式shell
    
    Returns:
        包含系统信息的字典
    """
    os_info = {"os_type": "Unknown", "version": ""}
    
    # 先尝试执行uname命令判断类型 (Linux/Unix/macOS)
    shell.send("uname -a\n")
    time.sleep(2)
    
    if shell.recv_ready():
        result = shell.recv(4096).decode('utf-8', errors='replace')
        
        if "Linux" in result:
            os_info["os_type"] = "Linux"
            
            # 尝试获取发行版信息
            shell.send("cat /etc/os-release 2>/dev/null || cat /etc/issue 2>/dev/null\n")
            time.sleep(2)
            if shell.recv_ready():
                distro_info = shell.recv(4096).decode('utf-8', errors='replace')
                
                # 提取发行版本信息
                version_match = re.search(r'VERSION="?([^"\n]+)', distro_info)
                name_match = re.search(r'NAME="?([^"\n]+)', distro_info)
                pretty_match = re.search(r'PRETTY_NAME="?([^"\n]+)', distro_info)
                
                if pretty_match:
                    os_info["version"] = pretty_match.group(1).strip()
                elif name_match and version_match:
                    os_info["version"] = f"{name_match.group(1).strip()} {version_match.group(1).strip()}"
                elif name_match:
                    os_info["version"] = name_match.group(1).strip()
            
        elif "Darwin" in result:
            os_info["os_type"] = "macOS"
            
            # 获取macOS版本
            shell.send("sw_vers\n")
            time.sleep(2)
            if shell.recv_ready():
                mac_info = shell.recv(4096).decode('utf-8', errors='replace')
                version_match = re.search(r'ProductVersion:\s*([^\n]+)', mac_info)
                if version_match:
                    os_info["version"] = version_match.group(1).strip()
                    
        elif "BSD" in result:
            os_info["os_type"] = "BSD"
            # FreeBSD, OpenBSD等，版本已包含在uname -a中
            version_match = re.search(r'([0-9]+\.[0-9]+)', result)
            if version_match:
                os_info["version"] = version_match.group(1)
    
    # 如果uname命令失败，尝试Windows命令
    if os_info["os_type"] == "Unknown":
        shell.send("ver\n")
        time.sleep(2)
        
        if shell.recv_ready():
            result = shell.recv(4096).decode('utf-8', errors='replace')
            
            if "Windows" in result:
                os_info["os_type"] = "Windows"
                # 提取Windows版本
                version_match = re.search(r'Microsoft Windows \[([^\]]+)\]', result)
                if version_match:
                    os_info["version"] = version_match.group(1).strip()
    
    # 清空残余输出
    _clear_buffer(shell)
    
    return os_info


def check_command_completion(llm_client, buffer_text, command, os_info, idle_time) -> Tuple[bool, str, float]:
    """使用LLM分析命令是否已完成执行"""
    try:
        # 提取最近输出内容进行分析
        recent_output = buffer_text
        
        system_message = """作为用户助手，请分析SSH远程命令是否已完成执行。
        你的任务是：
        1. 理解不同操作系统下命令的执行特征
        2. 分析输出内容，判断命令是否已完成
        3. 识别命令提示符、完成标志或错误状态
        4. 区分正在运行的长时间命令和已完成的命令
        
        以JSON格式返回：{"completed": true/false, "reasoning": "分析理由", "confidence": 0-1之间的数值}
        """
        
        llm_prompt = f"""
        当前执行的命令: {command}
        远程系统类型: {os_info['os_type']} {os_info.get('version', '')}
        
        最近的命令输出:
        {recent_output}
        
        无输出时间: {idle_time}秒
        
        请分析这个命令是否已经完成执行，或者是否还在正常运行中。
        """
        
        response = llm_client.chat.completions.create(
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
                    return False, "无法提取明确结论", 0.3
        except json.JSONDecodeError:
            # 如果JSON解析失败，根据文本内容进行简单判断
            if "已完成" in suggestion or "完成执行" in suggestion:
                return True, "文本分析显示命令可能已完成", 0.5
            return False, "JSON解析失败，默认认为命令仍在执行", 0.3
            
    except Exception as e:
        print_warning("命令状态分析出错，继续执行")
        return False, "分析失败", 0.0


def _need_user_input(data: str) -> bool:
    """检测是否需要用户输入"""
    patterns = [
        r'password.*:',       # 密码提示
        r'\[Y/n\]',           # 确认提示
        r'\[y/N\]',           # 确认提示
        r'\(yes/no\)',        # SSH确认提示
        r'\(y/n\)',           # 一般确认提示
        r'Enter selection',   # 选择提示
        r'Please respond',    # 通用提示
        r'Press.*to continue', # 按键继续
        r'Press.*key',        # 按任意键
        r'Continue\?',        # 继续提示
        r'[\?:]\s*$'          # 一般问题提示
    ]
    return any(re.search(p, data, re.I) for p in patterns)


def _get_llm_response(llm_client, prompt_text, command_history, os_info) -> Tuple[str, str, float, bool, str]:
    """使用LLM作为用户代理分析交互提示并给出响应"""
    try:
        # 准备上下文信息
        system_message = f"""你现在是用户的代理，直接代表用户与远程{os_info['os_type']}系统交互。
        你的任务是：
        1. 理解当前命令执行的上下文
        2. 分析远程系统的交互提示
        3. 直接提供最合适的用户响应内容，就像你就是用户一样
        4. 对于确认类操作(y/n)，基于常识和安全性判断如何回应
        5. 对于文件操作确认，判断是否安全并给出回应
        6. 如果提示需要输入特定信息但无法从上下文推断，明确说明需要用户提供什么信息
        
        以JSON格式返回：{{"response": "响应内容", "reasoning": "分析理由(仅内部参考)", "confidence": 0-1之间的数值, "needs_user_input": true/false, "missing_info": "缺失的信息描述"}}
        """
        
        cmd_history = '\n'.join(command_history[-3:]) if command_history else "无"
        
        llm_prompt = f"""
        当前执行的命令历史: 
        {cmd_history}
        
        远程系统类型: {os_info['os_type']} {os_info.get('version', '')}
        
        当前控制台提示: 
        {prompt_text}
        
        请以用户身份分析这个提示，并直接给出你会输入的响应。如果缺少关键信息无法回答，请明确说明需要用户提供什么信息。
        """
        
        response = llm_client.chat.completions.create(
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
                    return "y", "无法提取明确响应", 0.1, needs_user, missing_info
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
        return "y", "调用失败", 0.0, False, ""


def _clear_buffer(shell):
    """清空初始缓冲区"""
    while shell.recv_ready():
        shell.recv(4096)


if __name__ == "__main__":
    import os
    # 设置API密钥环境变量
    os.environ["api_key"] = input("请输入API密钥: ")
    
    # 测试连接信息
    ip = input("请输入服务器IP: ")
    username = input("请输入用户名: ")
    password = input("请输入密码: ")
    command = input("请输入要执行的命令: ")

    output = ssh_interactive_command(ip, username, password, command)
    print("\n命令执行结果:")
    print(output)
