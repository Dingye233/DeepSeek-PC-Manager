import paramiko
import sys
import time
import re


def ssh_interactive_command(ip, username, password, initial_command):
    """改进版交互式SSH命令执行"""
    try:
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect(ip, username=username, password=password, timeout=10)

        # 创建交互式shell
        shell = client.invoke_shell()
        shell.settimeout(5)  # 设置命令执行超时

        # 等待shell初始化
        time.sleep(1)
        _clear_buffer(shell)

        # 发送初始命令
        shell.send(initial_command + "\n")
        output = []
        start_time = time.time()
        timeout = 30  # 总超时时间

        while time.time() - start_time < timeout:
            if shell.recv_ready():
                data = shell.recv(4096).decode('utf-8', errors='replace')
                output.append(data)
                print(data, end='', flush=True)  # 实时输出

                # 检测交互提示
                if _need_user_input(data):
                    response = _get_user_response(data)
                    shell.send(response + "\n")
                    start_time = time.time()  # 重置超时计时

            elif shell.exit_status_ready():  # 命令已执行完成
                break

            time.sleep(0.1)

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

def _get_user_response(prompt: str) -> str:
    """根据提示类型获取用户响应"""
    if re.search(r'password', prompt, re.I):
        return input("\n检测到需要密码，请输入后回车: ")
    elif re.search(r'\[Y/n\]', prompt):
        return input("\n需要确认 [Y/n]: ") or "y"
    return input("\n需要输入响应: ")

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
