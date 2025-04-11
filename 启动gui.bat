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

:: 确保安装html2text模块
echo 正在安装html2text模块...
pip install html2text
if errorlevel 1 (
    echo 安装html2text模块失败
    pause
    exit /b 1
)

:: 直接启动GUI程序并捕获错误
echo 正在启动程序...
start "" venv\Scripts\pythonw.exe deepseek_gui.py

:: 创建监视器脚本，检查程序是否正常运行
echo @echo off > monitor.bat
echo :check >> monitor.bat
echo timeout /t 60 /nobreak > nul >> monitor.bat
echo tasklist /FI "IMAGENAME eq pythonw.exe" /FO CSV | find /C "pythonw.exe" > temp.txt >> monitor.bat
echo set /p count= < temp.txt >> monitor.bat
echo del temp.txt >> monitor.bat
echo if %%count%% equ 0 ( >> monitor.bat
echo   echo 程序已结束运行，自动重启... >> monitor.bat
echo   start "" venv\Scripts\pythonw.exe deepseek_gui.py >> monitor.bat
echo ) >> monitor.bat
echo goto check >> monitor.bat

:: 在后台启动监视器
start /min monitor.bat

echo 程序已启动，此窗口可以关闭
exit /b 0 