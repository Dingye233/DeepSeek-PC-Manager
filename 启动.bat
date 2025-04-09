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

echo [INFO] 正在安装核心依赖...
python -m pip install numpy python-docx openpyxl python-pptx PyPDF2 tiktoken openai python-dotenv requests asyncio psutil PyQt5 markdown beautifulsoup4 --quiet
if errorlevel 1 (
    echo [WARNING] 部分核心依赖安装失败，程序可能无法正常运行
) else (
    echo [INFO] 核心依赖安装成功
)

echo [INFO] 正在安装可选依赖...
python -m pip install pyaudio --quiet
python -m pip install pydub --quiet
python -m pip install paramiko --quiet
python -m pip install bs4 lxml --quiet
REM python -m pip install playsound --quiet

echo [INFO] 正在优化系统性能...
powershell -Command "$Process = Get-Process -Id $PID; $Process.PriorityClass = 'AboveNormal'"

echo [INFO] 正在启动DeepSeek-PC-Manager...
python deepseekAPI.py

echo.
echo [INFO] 程序执行完毕
pause