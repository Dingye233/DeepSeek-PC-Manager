@echo off
echo 正在启动DeepSeek AI助手Web界面...
echo ======================================

echo 启动Web服务...
start python web_ui.py

echo Web服务已启动！
echo 请在浏览器中访问: http://localhost:5000

echo 按任意键关闭此窗口...
pause 