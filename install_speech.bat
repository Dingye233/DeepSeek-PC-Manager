@echo off
chcp 65001
echo 安装Python语音识别依赖...
pip install speechrecognition==3.8.1
pip install pyaudio
pip install edge-tts
pip install playsound==1.2.2
echo.
echo 尝试备选安装方法...
pip install pipwin
pipwin install pyaudio
echo.
echo 依赖安装完成，现在可以运行主程序了
pause
