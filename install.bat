@echo off
echo ========================================================
echo              AI智能助手 - 安装程序
echo ========================================================
echo.

:: 检查Python是否安装
where python >nul 2>&1
if %errorlevel% neq 0 (
    echo [错误] 未检测到Python。请先安装Python 3.8或更高版本。
    echo        下载地址: https://www.python.org/downloads/
    pause
    exit /b 1
)

:: 检查Python版本
python -c "import sys; exit(0) if sys.version_info >= (3,8) else exit(1)"
if %errorlevel% neq 0 (
    echo [警告] Python版本低于3.8，可能会遇到兼容性问题。
    echo        建议升级到Python 3.8或更高版本。
    echo.
    set /p continue="是否继续安装? (y/n): "
    if /i not "%continue%"=="y" exit /b 1
)

echo [信息] 正在执行自动安装脚本...
echo.

:: 执行自动安装脚本
python auto_setup.py

if %errorlevel% neq 0 (
    echo.
    echo [错误] 安装过程中出现问题。请查看上方错误信息。
    pause
    exit /b 1
)

echo.
echo ========================================================
echo              安装完成!
echo ========================================================
echo.
echo 您现在可以：
echo  1. 编辑 .env 文件配置您的API密钥
echo  2. 运行 start_text_mode.bat（基础版本，仅文本）
echo     或 start_voice_mode.bat（完整版本，含语音功能）
echo.
echo 感谢使用！
echo.
pause 