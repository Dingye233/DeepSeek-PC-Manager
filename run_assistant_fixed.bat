@echo off
echo 正在安装依赖...
pip install -r requirements.txt

echo 安装语音相关依赖...
pip install SpeechRecognition --no-cache-dir
pip install edge-tts --no-cache-dir
pip install html2text --no-cache-dir

echo 安装预编译的PyAudio...
pip install --upgrade pip
pip install pipwin
pipwin install pyaudio

echo 尝试备选方式安装PyAudio...
pip install pyaudio --no-cache-dir

echo 安装playsound...
pip install playsound==1.2.2

echo.
echo 启动AI助手...
python aaaa.py
pause
