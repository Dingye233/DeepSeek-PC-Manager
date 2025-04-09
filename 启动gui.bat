@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

:: 设置环境变量控制二次确认行为
set DISABLE_EXCESSIVE_CONFIRMATION=true
:: 设置环境变量控制工具调用确认行为
set DISABLE_TOOL_CONFIRMATION=true

:: 检查Python是否安装
python --version >nul 2>&1
if errorlevel 1 (
    echo Python未安装，请先安装Python 3.8或更高版本
    pause
    exit /b 1
)

:: 检查虚拟环境是否存在
if not exist "venv" (
    echo 正在创建虚拟环境...
    python -m venv venv
    if errorlevel 1 (
        echo 创建虚拟环境失败
        pause
        exit /b 1
    )
)

:: 激活虚拟环境
call venv\Scripts\activate.bat
if errorlevel 1 (
    echo 激活虚拟环境失败
    pause
    exit /b 1
)

:: 检查并安装依赖
echo 正在检查依赖...
python -m pip install --upgrade pip
if exist requirements.txt (
    echo 正在安装依赖...
    pip install -r requirements.txt
    if errorlevel 1 (
        echo 安装依赖失败
        pause
        exit /b 1
    )
) else (
    echo requirements.txt文件不存在
    pause
    exit /b 1
)

:: 运行主程序
echo 正在启动程序...
python deepseek_gui.py
if errorlevel 1 (
    echo 程序启动失败
    pause
    exit /b 1
)

:: 如果程序正常退出，则暂停显示结果
pause 