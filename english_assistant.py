from openai import OpenAI
import json
import asyncio
import os
import re
import sys
import time
import threading
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

# 初始化OpenAI客户端
client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"), base_url="https://api.openai.com/v1")

# 系统消息定义
SYSTEM_MESSAGE = """你是一位友好的英语聊天伙伴，可以自然地与用户进行英语对话。你的特殊能力是能够在对话中优雅地纠正用户的语法和词汇错误，使纠正成为对话的自然组成部分。

指导原则：
1. 保持对话自然流畅，像朋友间聊天一样
2. 当用户使用英语表达有误时，在回复中巧妙融入纠正
3. 纠正方式应该温和、友好，不要让用户感到尴尬
4. 可以使用以下纠正技巧：
   - 复述用户的话，但使用正确的表达（"你的意思是..."）
   - 在回答中自然使用正确的表达方式
   - 用示例展示正确用法
   - 简短解释常见错误原因（如果合适）
5. 不要使用明显的标记或特殊格式指出错误
6. 优先回应用户的问题或话题，然后再考虑语言纠正
7. 如果用户英语完全正确，就不需要任何纠正，正常对话即可

记住：你的主要目标是进行愉快的对话，语言纠正是自然融入的增值服务，而非对话的中心。"""

# 初始化消息历史
messages = [{"role": "system", "content": SYSTEM_MESSAGE}]

# 控制台输出辅助函数
def print_color(text, color=None):
    """打印彩色文本"""
    colors = {
        "red": "\033[91m",
        "green": "\033[92m",
        "yellow": "\033[93m",
        "blue": "\033[94m",
        "purple": "\033[95m",
        "cyan": "\033[96m",
        "white": "\033[97m",
        "reset": "\033[0m"
    }
    if color in colors:
        print(f"{colors[color]}{text}{colors['reset']}")
    else:
        print(text)

def print_info(text):
    """打印信息"""
    print_color(f"[信息] {text}", "blue")

def print_success(text):
    """打印成功信息"""
    print_color(f"[成功] {text}", "green")

def print_error(text):
    """打印错误信息"""
    print_color(f"[错误] {text}", "red")

def print_warning(text):
    """打印警告信息"""
    print_color(f"[警告] {text}", "yellow")

def print_assistant(text):
    """打印助手回复"""
    print_color(f"助手: {text}", "cyan")

def print_user(text):
    """打印用户输入"""
    print_color(f"用户: {text}", "white")

# 主要处理函数
async def process_user_input(user_input):
    """处理用户输入并返回助手回复"""
    global messages
    
    # 添加用户消息到历史
    messages.append({"role": "user", "content": user_input})
    
    try:
        # 调用API获取回复
        response = client.chat.completions.create(
            model="gpt-4o",  # 使用适合的模型
            messages=messages,
            temperature=0.7,
            max_tokens=1000
        )
        
        # 获取回复文本
        reply_text = response.choices[0].message.content
        
        # 添加助手回复到历史
        messages.append({"role": "assistant", "content": reply_text})
        
        # 如果历史消息过长，进行清理
        if len(messages) > 20:
            # 保留系统消息和最近的对话
            messages = [messages[0]] + messages[-19:]
        
        return reply_text
        
    except Exception as e:
        print_error(f"处理用户输入时出错: {str(e)}")
        return f"很抱歉，处理您的请求时出现了错误。错误信息: {str(e)}"

# 词汇学习功能
async def provide_vocabulary_learning(topic):
    """基于话题提供词汇学习"""
    vocab_prompt = f"""请以对话方式介绍与"{topic}"相关的5个有用英语词汇或短语。
不要使用列表格式，而是像在教朋友一样自然地介绍这些词汇。
对每个词汇，包括：意思解释、例句、以及如何在日常对话中使用它们。
回复应该像朋友间的对话，而不是正式的词汇表。"""
    
    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "system", "content": "你是友好的英语伙伴，在日常对话中自然地帮助朋友学习词汇"},
                      {"role": "user", "content": vocab_prompt}],
            temperature=0.7,
            max_tokens=1500
        )
        
        return response.choices[0].message.content
    except Exception as e:
        print_error(f"获取词汇学习内容时出错: {str(e)}")
        return f"无法提供词汇学习内容。错误: {str(e)}"

# 语法建议功能
async def provide_grammar_tips(grammar_point):
    """提供语法使用建议"""
    grammar_prompt = f"""请以朋友间聊天的方式，解释"{grammar_point}"语法的使用。
避免使用教科书式的讲解，而是像聊天一样自然地分享这个语法点的用法和小技巧。
包括2-3个自然的例句，以及在日常对话中如何正确使用它。
回复应该轻松友好，就像你在咖啡厅和朋友分享英语小窍门一样。"""
    
    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "system", "content": "你是友好的英语伙伴，在日常对话中自然地解释语法要点"},
                      {"role": "user", "content": grammar_prompt}],
            temperature=0.7,
            max_tokens=1500
        )
        
        return response.choices[0].message.content
    except Exception as e:
        print_error(f"获取语法建议时出错: {str(e)}")
        return f"无法提供语法建议。错误: {str(e)}"

# 表达润色功能
async def polish_expression(text):
    """以对话方式润色用户的英语表达"""
    polish_prompt = f"""假设我们是朋友，我刚说了这句话："{text}"
如果这句话有任何不自然或不地道的表达，请在回复中像朋友间聊天一样，自然地提出更好的表达方式。
不要使用正式的纠正格式，而是融入到对话中，就像你在日常对话中随口提到的建议。
如果表达已经很好，就简单地继续对话，赞赏我的表达并回应内容。"""
    
    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "system", "content": "你是友好的英语伙伴，在自然对话中提供语言表达建议"},
                      {"role": "user", "content": polish_prompt}],
            temperature=0.7,
            max_tokens=1000
        )
        
        return response.choices[0].message.content
    except Exception as e:
        print_error(f"润色表达时出错: {str(e)}")
        return f"无法润色表达。错误: {str(e)}"

# 用户输入处理
async def get_user_input():
    """获取用户输入"""
    return input("用户: ")

# 帮助信息
def print_help():
    """打印帮助信息"""
    help_text = """
英语聊天助手使用指南:
- 直接用英语与助手聊天，助手会在对话中自然地纠正语言错误
- 特殊命令:
  * /vocab <话题>: 了解相关话题的词汇
  * /grammar <语法点>: 获取语法使用建议
  * /polish <文本>: 优化英语表达
  * /help: 显示此帮助信息
  * /clear: 清除对话历史
  * /exit: 退出助手
"""
    print_color(help_text, "cyan")

# 主程序
async def main():
    print_success("英语聊天助手已启动！")
    print_info("开始用英语聊天吧，助手会在对话中自然地帮你改进语言表达。")
    print_info("输入 /help 获取更多帮助。")
    
    while True:
        try:
            # 获取用户输入
            user_input = await get_user_input()
            
            # 检查特殊命令
            if user_input.lower() == "/exit":
                print_info("感谢使用英语聊天助手，再见！")
                break
                
            elif user_input.lower() == "/help":
                print_help()
                continue
                
            elif user_input.lower() == "/clear":
                global messages
                messages = [messages[0]]  # 只保留系统消息
                print_info("对话历史已清除。")
                continue
                
            elif user_input.lower().startswith("/vocab "):
                topic = user_input[7:].strip()
                print_info(f"正在获取关于\"{topic}\"的词汇...")
                vocab_content = await provide_vocabulary_learning(topic)
                print_assistant(vocab_content)
                continue
                
            elif user_input.lower().startswith("/grammar "):
                grammar_point = user_input[9:].strip()
                print_info(f"正在获取关于\"{grammar_point}\"的语法建议...")
                grammar_content = await provide_grammar_tips(grammar_point)
                print_assistant(grammar_content)
                continue
                
            elif user_input.lower().startswith("/polish "):
                text = user_input[8:].strip()
                print_info("正在优化您的表达...")
                polished_content = await polish_expression(text)
                print_assistant(polished_content)
                continue
            
            # 正常对话处理
            print_info("正在处理您的输入...")
            reply = await process_user_input(user_input)
            
            # 打印助手回复
            print_assistant(reply)
            
        except KeyboardInterrupt:
            print_info("\n检测到键盘中断，正在退出...")
            break
        except Exception as e:
            print_error(f"发生错误: {str(e)}")

# 主程序入口
if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print_info("\n感谢使用英语聊天助手，再见！")
    except Exception as e:
        print_error(f"程序异常终止: {str(e)}")
    finally:
        # 确保程序正常退出
        sys.exit(0) 