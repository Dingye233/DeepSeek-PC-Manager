#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Web UI前端 - 为AI助手提供网页界面
支持Markdown显示、代码高亮和实时交互
"""

import os
import sys
import json
import asyncio
import threading
import time
import queue
from datetime import datetime
from flask import Flask, render_template, request, jsonify, Response, stream_with_context
import markdown
import bleach
from pygments import highlight
from pygments.lexers import get_lexer_by_name
from pygments.formatters import HtmlFormatter
import re
import uuid
from dotenv import load_dotenv
import requests

# 导入现有后端模块
try:
    import deepseekAPI as backend
except ImportError:
    print("警告: 无法导入deepseekAPI模块，将使用API直接调用方式")
    backend = None

# 加载环境变量
load_dotenv()
api_key = os.getenv("api_key")

# 创建Flask应用
app = Flask(__name__, 
            static_folder='static',
            template_folder='templates')

# 创建消息队列用于前后端通信
message_queue = queue.Queue()
if backend:
    backend.message_queue = message_queue

# 存储会话历史
chat_history = []

# Markdown转HTML
def md_to_html(md_text):
    """将Markdown文本转换为HTML"""
    # 允许的HTML标签和属性
    allowed_tags = [
        'a', 'abbr', 'acronym', 'b', 'blockquote', 'code', 'em', 'i', 
        'li', 'ol', 'pre', 'strong', 'ul', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 
        'p', 'hr', 'br', 'div', 'span', 'img', 'table', 'thead', 'tbody', 'tr', 
        'th', 'td', 'sup', 'sub'
    ]
    allowed_attrs = {
        '*': ['class', 'style'],
        'a': ['href', 'title', 'target'],
        'img': ['src', 'alt', 'title', 'width', 'height'],
        'td': ['colspan', 'rowspan', 'align'],
        'th': ['colspan', 'rowspan', 'align']
    }
    
    # 转换Markdown为HTML
    html = markdown.markdown(
        md_text,
        extensions=[
            'markdown.extensions.fenced_code',
            'markdown.extensions.tables',
            'markdown.extensions.codehilite',
            'markdown.extensions.nl2br',
            'markdown.extensions.toc'
        ]
    )
    
    # 处理代码块高亮
    def highlight_code(match):
        code = match.group(2)
        lang = match.group(1) or 'text'
        try:
            lexer = get_lexer_by_name(lang, stripall=True)
        except:
            lexer = get_lexer_by_name('text', stripall=True)
        formatter = HtmlFormatter(linenos=False, cssclass=f"codehilite language-{lang}")
        return highlight(code, lexer, formatter)
    
    # 清理HTML，防止XSS攻击
    clean_html = bleach.clean(html, tags=allowed_tags, attributes=allowed_attrs)
    return clean_html

def get_deepseek_response(message_list):
    """调用DeepSeek API获取回复"""
    url = "https://api.deepseek.com/v1/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }
    data = {
        "model": "deepseek-chat",
        "messages": message_list,
        "temperature": 0.7,
        "max_tokens": 2000
    }
    
    try:
        response = requests.post(url, headers=headers, json=data)
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"]
    except Exception as e:
        return f"API请求错误: {str(e)}"

def format_code_blocks(text):
    """处理代码块，使用Pygments进行语法高亮"""
    pattern = r'```(\w+)?\n(.*?)\n```'
    
    def replace_code_block(match):
        lang = match.group(1) or 'text'
        code = match.group(2)
        try:
            lexer = get_lexer_by_name(lang, stripall=True)
        except:
            lexer = get_lexer_by_name('text', stripall=True)
        formatter = HtmlFormatter(style='monokai', cssclass='codehilite')
        highlighted = highlight(code, lexer, formatter)
        return highlighted
    
    # 使用正则表达式的DOTALL模式来匹配多行
    formatted = re.sub(pattern, replace_code_block, text, flags=re.DOTALL)
    return formatted

# 路由定义
@app.route('/')
def index():
    """渲染主页"""
    current_time = datetime.now().strftime("%H:%M:%S")
    return render_template('index.html', current_time=current_time)

@app.route('/api/chat', methods=['POST'])
def chat():
    """处理聊天请求"""
    global chat_history
    
    data = request.json
    user_message = data.get('message', '')
    
    if not user_message:
        return jsonify({'error': 'No message provided'}), 400
    
    # 创建消息历史
    if not chat_history:
        chat_history = [{"role": "system", "content": "你是一个强大的基于DeepSeek大语言模型的智能助手。你可以协助用户处理各种任务，包括但不限于回答问题、生成代码、解释概念、提供建议等。请尽量给出简洁、准确、有帮助的回复。"}]
    
    chat_history.append({"role": "user", "content": user_message})
    
    # 调用API获取回复
    ai_response = get_deepseek_response(chat_history)
    chat_history.append({"role": "assistant", "content": ai_response})
    
    # 分析响应中是否包含工具调用或任务规划信息
    tool_calls = extract_tool_calls(ai_response)
    task_planning = extract_task_planning(ai_response)
    
    # 将原始markdown转换为HTML，保留代码块
    html_content = markdown.markdown(ai_response, extensions=['fenced_code', 'tables'])
    
    # 清理HTML内容，但保留安全标签
    allowed_tags = list(bleach.ALLOWED_TAGS) + ['p', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'pre', 'code', 'ol', 'ul', 'li', 'blockquote', 'table', 'thead', 'tbody', 'tr', 'th', 'td']
    allowed_attrs = {'*': ['class']}
    cleaned_html = bleach.clean(html_content, tags=allowed_tags, attributes=allowed_attrs)
    
    # 处理代码块高亮
    formatted_response = format_code_blocks(ai_response)
    
    return jsonify({
        'text': ai_response,
        'html': formatted_response,
        'id': str(uuid.uuid4()),
        'tool_calls': tool_calls,
        'task_planning': task_planning
    })

@app.route('/api/stream', methods=['GET'])
def stream_connection():
    """建立流式连接"""
    def generate():
        yield f"data: {json.dumps({'type': 'connected'})}\n\n"
    return Response(stream_with_context(generate()), content_type='text/event-stream')

@app.route('/api/stream', methods=['POST'])
def stream():
    """流式返回处理过程"""
    data = request.json
    user_input = data.get('message', '')
    
    if backend:
        # 使用后端模块处理
        # 清空当前队列
        while not message_queue.empty():
            message_queue.get()
        
        # 启动处理线程
        threading.Thread(target=lambda: asyncio.run(backend.main(user_input))).start()
        
        # 返回流式更新的端点
        return jsonify({"status": "processing", "stream_url": "/api/stream_updates"})
    else:
        # 直接处理并返回响应
        if not chat_history:
            chat_history = [{"role": "system", "content": "你是一个强大的基于DeepSeek大语言模型的智能助手。你可以协助用户处理各种任务，包括但不限于回答问题、生成代码、解释概念、提供建议等。请尽量给出简洁、准确、有帮助的回复。"}]
        
        chat_history.append({"role": "user", "content": user_input})
        
        # 调用API获取回复
        ai_response = get_deepseek_response(chat_history)
        chat_history.append({"role": "assistant", "content": ai_response})
        
        # 分析工具调用和任务规划
        tool_calls = extract_tool_calls(ai_response)
        task_planning = extract_task_planning(ai_response)
        
        # 将结果放入队列
        message_queue.put({
            "type": "assistant",
            "text": ai_response,
            "tool_calls": tool_calls,
            "task_planning": task_planning
        })
        message_queue.put({
            "type": "complete",
            "text": ""
        })
        
        # 返回流式更新的端点
        return jsonify({"status": "processing", "stream_url": "/api/stream_updates"})

@app.route('/api/history', methods=['GET'])
def get_history():
    """获取聊天历史"""
    filtered_history = [msg for msg in chat_history if msg["role"] != "system"]
    return jsonify({"history": filtered_history})

@app.route('/api/clear', methods=['POST'])
def clear_history():
    """清除聊天历史和上下文"""
    global chat_history
    chat_history = []
    if backend:
        backend.messages = backend.clear_context(backend.messages)
    return jsonify({"status": "success", "message": "历史记录已清除"})

# 创建必要的目录
def create_directories():
    """创建必要的目录结构"""
    os.makedirs('static/css', exist_ok=True)
    os.makedirs('static/js', exist_ok=True)
    os.makedirs('templates', exist_ok=True)

# 工具调用和任务规划提取函数
def extract_tool_calls(text):
    """从响应中提取工具调用信息"""
    tool_calls = []
    
    # 搜索工具调用的模式
    pattern = r'调用工具[：:]\s*`([^`]+)`|使用工具[：:]\s*`([^`]+)`|执行命令[：:]\s*`([^`]+)`|运行命令[：:]\s*`([^`]+)`'
    matches = re.finditer(pattern, text, re.MULTILINE)
    
    for match in matches:
        # 获取匹配的工具名称（从4个捕获组中选择非None的一个）
        tool_name = next((g for g in match.groups() if g is not None), "未知工具")
        tool_calls.append({
            "tool": tool_name,
            "position": match.start()
        })
    
    return tool_calls

def extract_task_planning(text):
    """从响应中提取任务规划信息"""
    # 搜索任务规划的模式
    plan_pattern = r'任务计划[：:](.*?)(?=\n\n|$)|计划步骤[：:](.*?)(?=\n\n|$)|我将按照以下步骤(.*?)(?=\n\n|$)'
    plan_match = re.search(plan_pattern, text, re.DOTALL)
    
    if plan_match:
        # 获取匹配的计划内容（从3个捕获组中选择非None的一个）
        plan_content = next((g for g in plan_match.groups() if g is not None), "")
        return {
            "has_plan": True,
            "plan_text": plan_content.strip(),
            "position": plan_match.start()
        }
    
    return {"has_plan": False}

@app.route('/api/stream_updates', methods=['GET'])
def stream_updates():
    """提供来自消息队列的流式更新"""
    def generate():
        last_id = None
        
        while True:
            try:
                if not message_queue.empty():
                    message = message_queue.get()
                    
                    # 添加工具调用和任务规划分析
                    if message.get("type") == "assistant" and "text" in message:
                        message["tool_calls"] = extract_tool_calls(message["text"])
                        message["task_planning"] = extract_task_planning(message["text"])
                    
                    message_id = message.get("id", str(uuid.uuid4()))
                    if message_id != last_id:
                        yield f"data: {json.dumps(message)}\n\n"
                        last_id = message_id
                    
                    # 如果是完成消息，退出循环
                    if message.get("type") == "complete":
                        break
                else:
                    time.sleep(0.1)
            except Exception as e:
                print(f"流式更新错误: {e}")
                yield f"data: {json.dumps({'type': 'error', 'text': str(e)})}\n\n"
                break
    
    return Response(stream_with_context(generate()), content_type='text/event-stream')

# 主函数
def main():
    create_directories()
    print("\n========================================================")
    print("              AI助手 - Web界面已启动")
    print("========================================================")
    print("\n[信息] Web界面已启动，请访问 http://127.0.0.1:5000")
    print("[信息] 按Ctrl+C可以停止服务器\n")
    app.run(debug=True, host='127.0.0.1', port=5000, threaded=True)

if __name__ == "__main__":
    main() 