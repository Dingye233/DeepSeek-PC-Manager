import paramiko
import sys
import time
import re
import getpass  # 用于隐藏密码输入

def ssh_interactive_command(ip, username, password, initial_command):
    """
    连接到 SSH 并执行初始命令。
    如果在命令执行过程中遇到需要二次输入的提示（例如包含英文提示 "Are you sure" 或 sudo 密码提示），
    则提示用户输入响应，并继续发送到远程主机。

    最后返回命令执行结束后的所有输出。
    """
    try:
        # 创建 SSH 客户端并建立连接
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect(ip, username=username, password=password)

        # 获取交互式 shell
        shell = client.invoke_shell()
        time.sleep(1)  # 等待欢迎信息、提示符出现

        # 清除初始缓冲区内容
        if shell.recv_ready():
            initial_output = shell.recv(65535).decode('utf-8')
            print(initial_output, end='')

        # 发送初始命令
        shell.send(initial_command + "\n")
        all_output = ""
        timeout_counter = 0  # 用于检测是否连续无输出

        # 循环读取输出，直到认为命令执行完毕（连续一段时间无输出）
        while True:
            time.sleep(1)
            if shell.recv_ready():
                output = shell.recv(65535).decode('utf-8')
                all_output += output
                print(output, end='')  # 实时反馈输出
                timeout_counter = 0

                # 检测是否出现 sudo 密码提示
                if re.search(r'\[sudo\] password for', output):
                    sudo_pw = getpass.getpass("检测到 sudo 提示，请输入 sudo 密码: ")
                    shell.send(sudo_pw + "\n")
                    time.sleep(1)
                    if shell.recv_ready():
                        resp_output = shell.recv(65535).decode('utf-8')
                        all_output += resp_output
                        print(resp_output, end='')

                # 检测其他需要用户交互的提示（中英文提示）
                elif re.search(r'(请输入|确认|Are you sure|confirm|\[y/?n\])', output, re.IGNORECASE):
                    user_response = input("检测到提示，请输入响应: ")
                    shell.send(user_response + "\n")
                    time.sleep(1)
                    if shell.recv_ready():
                        resp_output = shell.recv(65535).decode('utf-8')
                        all_output += resp_output
                        print(resp_output, end='')

            else:
                # 若连续3秒钟无输出，则认为命令执行完毕
                timeout_counter += 1
                if timeout_counter >= 3:
                    break

        client.close()
        return all_output

    except Exception as e:
        print(f"发生错误: {e}")
        sys.exit(1)


if __name__ == "__main__":
    # 这些信息可由大模型传入参数
    ip = "192.168.10.107"
    username = "ye"
    password = "147258"

    # 大模型调用工具时，会指定一个初始命令
    command = input("请输入初始命令: ")

    output = ssh_interactive_command(ip, username, password, command)
    print("\n最终命令输出如下：")
    print(output)
