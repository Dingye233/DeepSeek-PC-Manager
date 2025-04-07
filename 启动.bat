@echo off
chcp 65001 >nul
title DeepSeek-PC-Manager启动器
color 0A

REM 检查虚拟环境
if not exist "venv\Scripts\activate.bat" (
    echo [INFO] 正在创建虚拟环境...
    python -m venv venv
    if errorlevel 1 (
        echo [ERROR] 创建虚拟环境失败！
        pause
        exit /b 1
    )
)

REM 激活虚拟环境
call venv\Scripts\activate.bat

REM 安装核心依赖
echo [INFO] 正在安装依赖...
pip install numpy python-docx openpyxl python-pptx PyPDF2 tiktoken --quiet
if errorlevel 1 (
    echo [ERROR] 依赖安装失败！
    pause
    exit /b 1
)

REM 运行主程序
echo [INFO] 正在启动DeepSeek-PC-Manager...
python deepseekAPI.py

REM 保持窗口
echo.
echo [INFO] 程序执行完毕
pause