@echo off
echo ========================================================
echo              AI助手 - Web界面启动程序
echo ========================================================
echo.

echo [信息] 正在启动Web界面...
python web_ui.py

if %errorlevel% neq 0 (
    echo.
    echo [错误] 启动Web界面失败，请检查Python环境和依赖是否正确安装。
    echo        尝试执行: pip install -r requirements.txt
    pause
    exit /b 1
)

pause 