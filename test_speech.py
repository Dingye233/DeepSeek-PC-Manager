import speech_recognition as sr
import time
import sys

def test_speech_recognition():
    print("测试语音识别功能...")
    try:
        # 创建recognizer实例
        r = sr.Recognizer()
        
        # 测试麦克风
        print("测试麦克风...")
        try:
            with sr.Microphone() as source:
                print("麦克风正常！")
                print("正在调整环境噪音...")
                r.adjust_for_ambient_noise(source, duration=1)
                print("请说一些话...")
                audio = r.listen(source, timeout=5)
                print("捕获到音频！尝试识别...")
                
                try:
                    # 使用Google识别
                    text = r.recognize_google(audio, language="zh-CN")
                    print(f"识别结果: {text}")
                    return True
                except sr.UnknownValueError:
                    print("无法识别语音内容")
                except sr.RequestError as e:
                    print(f"Google语音识别服务错误: {e}")
        except Exception as e:
            print(f"麦克风访问失败: {e}")
            print("确保您的麦克风已连接并正常工作")
            return False
            
    except Exception as e:
        print(f"语音测试失败: {e}")
        return False
    
    return False

if __name__ == "__main__":
    print("语音识别测试程序")
    print("================")
    print(f"Python版本: {sys.version}")
    print(f"SpeechRecognition版本: {sr.__version__}")
    
    success = test_speech_recognition()
    
    if success:
        print("\n测试成功！语音识别工作正常")
    else:
        print("\n测试失败，语音识别功能有问题")
    
    input("按Enter键退出...") 