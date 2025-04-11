import sys
import os
import subprocess

def gui_mode():
    print("启动 GUI 模式 (deepseek_gui.py)...")
    subprocess.Popen(["python", "deepseek_gui.py"])

def voice_terminal_mode():
    print("启动语音终端控制台模式 (aaaa.py)...")
    subprocess.Popen(["python", "aaaa.py"])

def normal_terminal_mode():
    print("启动普通控制台模式 (deepseekAPI)...")
    subprocess.Popen(["python", "deepseekAPI.py"])

def main():
    print("请选择启动模式：")
    print("1. GUI 模式 (deepseek_gui.py)")
    print("2. 语音终端控制台模式 (aaaa.py)")
    print("3. 普通控制台模式 (deepseekAPI)")
    choice = input("请输入选项（1/2/3）：")

    if choice == "1":
        gui_mode()
    elif choice == "2":
        voice_terminal_mode()
    elif choice == "3":
        normal_terminal_mode()
    else:
        print("无效选项，请重新运行程序。")

if __name__ == "__main__":
    main()