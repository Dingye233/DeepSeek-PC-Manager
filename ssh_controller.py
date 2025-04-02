import paramiko
import sys
import time
import re
import asyncio
from typing import Optional


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


def ssh_interactive_command(ip, username, password, initial_command):
    """改进版交互式SSH命令执行"""
    try:
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect(ip, username=username, password=password, timeout=10)

        # 创建交互式shell
        shell = client.invoke_shell()
        shell.settimeout(240)  # 设置命令执行超时

        # 等待shell初始化
        time.sleep(1)
        _clear_buffer(shell)

        # 发送初始命令
        shell.send(initial_command + "\n")
        output = []
        start_time = time.time()
        timeout = 30  # 总超时时间

        # 创建事件循环用于处理用户输入
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        while time.time() - start_time < timeout:
            if shell.recv_ready():
                data = shell.recv(4096).decode('utf-8', errors='replace')
                output.append(data)
                print(data, end='', flush=True)

                # 新增命令结束检测（匹配 $, #, > 等提示符）
                if re.search(r'[\$#>\]]\s*$', data.split('\n')[-1]):
                    break
                
                if _need_user_input(data):
                    # 使用事件循环运行异步获取用户输入的函数
                    response = loop.run_until_complete(_get_user_response(data))
                    
                    # 如果用户没有输入（超时），使用默认值
                    if response is None:
                        if re.search(r'\[Y/n\]', data):
                            response = "y"  # 默认确认
                        elif re.search(r'password', data, re.I):
                            # 密码情况无法提供默认值，将终止操作
                            print("\n需要密码但用户未提供，终止操作")
                            break
                        else:
                            response = ""  # 其他情况提供空回车
                        print(f"用户未输入，使用默认值: {'[隐藏密码]' if re.search(r'password', data, re.I) else response}")
                        
                    shell.send(response + "\n")
                    start_time = time.time()

            elif shell.exit_status_ready():
                break

            # 延长检测间隔减少CPU占用
            time.sleep(0.5)

        # 获取最终输出
        final_output = ''.join(output).strip()
        shell.close()
        client.close()
        
        return final_output or "命令执行完成（无输出）"

    except Exception as e:
        return f"SSH错误: {str(e)}"

def _need_user_input(data: str) -> bool:
    """检测是否需要用户输入"""
    patterns = [
        r'password.*:',       # 密码提示
        r'\[Y/n\]',           # 确认提示
        r'\(yes/no\)',        # 确认提示
        r'Enter selection',   # 选择提示
        r'Please respond'     # 通用提示
    ]
    return any(re.search(p, data, re.I) for p in patterns)

async def _get_user_response(prompt: str) -> Optional[str]:
    """根据提示类型获取用户响应"""
    if re.search(r'password', prompt, re.I):
        return await get_user_input_async("检测到需要密码，请输入后回车: ")
    elif re.search(r'\[Y/n\]', prompt):
        return await get_user_input_async("需要确认 [Y/n]: ")
    return await get_user_input_async("需要输入响应: ")

def _clear_buffer(shell):
    """清空初始缓冲区"""
    while shell.recv_ready():
        shell.recv(1024)


if __name__ == "__main__":
    # 这些信息可由大模型传入参数
    ip = "192.168.10.107"
    username = "ye"
    password = "147258"

    # 大模型调用工具时，会指定一个初始命令
    command = input("请输入要执行的命令: ")

    output = ssh_interactive_command(ip, username, password, command)
    print("\n命令执行结果:")
    print(output)
