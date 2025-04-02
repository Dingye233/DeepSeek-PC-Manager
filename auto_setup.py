#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
自动化安装脚本 - 一键安装和配置所有依赖
"""

import os
import sys
import platform
import subprocess
import json
import time
from pathlib import Path

def print_step(message):
    """打印带有格式的步骤信息"""
    print("\n" + "="*80)
    print(f">>> {message}")
    print("="*80)

def run_command(command, shell=True):
    """运行命令并实时输出结果"""
    print(f"执行命令: {command}")
    
    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        shell=shell,
        text=True,
        encoding='utf-8',
        errors='replace'
    )
    
    # 实时输出命令执行结果
    for line in process.stdout:
        print(line.strip())
    
    # 等待命令执行完成
    process.wait()
    return process.returncode

def detect_system():
    """检测操作系统和Python环境"""
    print_step("检测系统环境")
    
    system = platform.system()
    python_version = platform.python_version()
    
    print(f"操作系统: {system}")
    print(f"Python版本: {python_version}")
    
    if system == "Windows":
        print("在Windows系统上继续安装")
    else:
        print(f"警告: 此脚本主要为Windows系统设计，在{system}上可能不完全兼容")
    
    # 检查Python版本
    if float(python_version.split(".")[0]) + float(python_version.split(".")[1])/10 < 3.8:
        print("警告: 建议使用Python 3.8或更高版本")
    
    return system

def check_pip():
    """检查pip是否可用"""
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "--version"])
        return True
    except subprocess.CalledProcessError:
        return False

def install_requirements():
    """安装requirements.txt中的依赖"""
    print_step("正在安装Python依赖")
    
    if not os.path.exists("requirements.txt"):
        print("错误: 找不到requirements.txt文件")
        return False
    
    # 先尝试使用国内镜像源安装
    result = run_command(f"{sys.executable} -m pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple")
    
    # 如果失败，再尝试使用默认源
    if result != 0:
        print("使用清华源安装失败，尝试使用默认源")
        result = run_command(f"{sys.executable} -m pip install -r requirements.txt")
    
    return result == 0

def install_pyaudio():
    """单独安装pyaudio (Windows系统需要特殊处理)"""
    print_step("安装PyAudio")
    
    system = platform.system()
    if system == "Windows":
        try:
            # 先尝试直接安装
            result = run_command(f"{sys.executable} -m pip install pyaudio")
            if result != 0:
                # 如果直接安装失败，尝试使用预编译的wheel
                print("直接安装PyAudio失败，尝试下载预编译wheel...")
                python_version = f"{sys.version_info.major}.{sys.version_info.minor}"
                arch = "win_amd64" if platform.architecture()[0] == "64bit" else "win32"
                
                wheel_url = f"https://download.lfd.uci.edu/pythonlibs/archived/PyAudio-0.2.11-cp{python_version.replace('.', '')}-cp{python_version.replace('.', '')}{('m-' + arch) if sys.version_info < (3, 8) else ('-' + arch)}.whl"
                wheel_file = f"PyAudio-0.2.11-cp{python_version.replace('.', '')}-cp{python_version.replace('.', '')}{('m-' + arch) if sys.version_info < (3, 8) else ('-' + arch)}.whl"
                
                print(f"下载: {wheel_url}")
                import requests
                response = requests.get(wheel_url)
                if response.status_code == 200:
                    with open(wheel_file, "wb") as f:
                        f.write(response.content)
                    result = run_command(f"{sys.executable} -m pip install {wheel_file}")
                    if os.path.exists(wheel_file):
                        os.remove(wheel_file)
                    return result == 0
                else:
                    print(f"下载失败，HTTP状态码: {response.status_code}")
                    print("请手动安装PyAudio：https://people.csail.mit.edu/hubert/pyaudio/#download")
                    return False
        except Exception as e:
            print(f"安装PyAudio时出错: {str(e)}")
            print("请参考: https://people.csail.mit.edu/hubert/pyaudio/")
            return False
    else:
        # Linux/macOS安装
        if system == "Linux":
            run_command("sudo apt-get update && sudo apt-get install -y python3-pyaudio portaudio19-dev")
        elif system == "Darwin":  # macOS
            run_command("brew install portaudio")
        
        result = run_command(f"{sys.executable} -m pip install pyaudio")
        return result == 0

def setup_environment_variables():
    """设置环境变量"""
    print_step("配置环境变量")
    
    if not os.path.exists(".env"):
        # 创建示例.env文件
        env_content = """# API Keys
api_key=your_deepseek_api_key
key=your_weather_api_key
sttkey=your_speech_to_text_api_key

# 邮件设置
sender=your_email@example.com
password=your_email_password
smtp_server=smtp.example.com
smtp_port=465

# 其他配置
TTS_DEVICE=cuda
"""
        with open(".env", "w", encoding="utf-8") as f:
            f.write(env_content)
        
        print("已创建.env文件模板，请编辑填入您的API密钥和其他配置")
    else:
        print(".env文件已存在，跳过创建")
    
    return True

def create_shortcuts():
    """创建快捷启动脚本"""
    print_step("创建启动脚本")
    
    # 创建Windows批处理文件
    with open("start_text_mode.bat", "w") as f:
        f.write('@echo off\n')
        f.write('echo 启动基础版本 (仅文本模式)...\n')
        f.write('python deepseekAPI.py\n')
        f.write('pause\n')
    
    with open("start_voice_mode.bat", "w") as f:
        f.write('@echo off\n')
        f.write('echo 启动完整版本 (包含语音功能)...\n')
        f.write('python aaaa.py\n')
        f.write('pause\n')
    
    # 创建示例代码生成器启动脚本
    with open("code_generator_demo.bat", "w") as f:
        f.write('@echo off\n')
        f.write('echo 代码生成器示例...\n')
        f.write('python -c "import code_tools; print(code_tools.write_code(\'hello_world.py\', \'print(\\\"Hello, AI generated World!\\\")\\n\'))"\n')
        f.write('pause\n')
    
    print("已创建以下启动脚本:")
    print("- start_text_mode.bat - 启动基础版本（仅文本功能）")
    print("- start_voice_mode.bat - 启动完整版本（包含语音功能）")
    print("- code_generator_demo.bat - 代码生成器示例")
    
    return True

def check_code_tools():
    """检查代码工具模块是否正常"""
    print_step("检查代码工具模块")
    
    if not os.path.exists("code_generator.py") or not os.path.exists("code_tools.py"):
        print("警告: 代码生成工具模块文件缺失")
        return False
    
    try:
        import code_tools
        import code_generator
        print("代码工具模块检查通过")
        return True
    except ImportError as e:
        print(f"导入代码工具模块失败: {e}")
        return False

def main():
    print("\n" + "*"*50)
    print("*      自动环境配置脚本 v1.0      *")
    print("*"*50 + "\n")
    
    # 检测系统
    system = detect_system()
    
    # 检查pip
    if not check_pip():
        print("错误: pip未正确安装或不可用")
        return False
    
    # 安装依赖
    success = install_requirements()
    if not success:
        print("警告: 安装依赖包时出现错误")
    
    # 单独处理PyAudio
    pyaudio_success = install_pyaudio()
    if not pyaudio_success:
        print("警告: PyAudio安装可能不完整，语音功能可能受限")
    
    # 设置环境变量
    setup_environment_variables()
    
    # 检查代码工具模块
    check_code_tools()
    
    # 创建快捷启动脚本
    create_shortcuts()
    
    print("\n" + "*"*50)
    print("*      安装和配置完成      *")
    print("*"*50)
    print("\n请按照以下步骤完成最终配置:")
    print("1. 编辑.env文件，填入您的API密钥和其他配置")
    print("2. 使用start_text_mode.bat启动基础版本")
    print("   或使用start_voice_mode.bat启动完整版本(含语音功能)")
    print("\n如需帮助，请参考README.md文档")

if __name__ == "__main__":
    main() 