import os

from openai import OpenAI
import numpy as np
from dotenv import load_dotenv
import re
load_dotenv()

def r1_optimizer(message: str, mode="auto", return_reasoning=False) -> str:
    """
    调用DeepSeek Reasoner模型来解决复杂问题，支持代码生成和文本推理
    
    该函数使用DeepSeek的reasoner模型，针对以下场景提供更强大的推理能力：
    1. 复杂代码生成：需要设计多层结构、算法实现等
    2. 难以修复的bug：需要深入理解和分析问题
    3. 算法设计与优化：需要高效的解决方案
    4. 复杂逻辑推理：需要多步骤的思考过程
    5. 文本分析与问答：需要深度理解和推理的问题
    6. 概念解释：需要详细和清晰的解释
    
    :param message: 包含完整问题描述和必要上下文的字符串
    :param mode: 处理模式 - "code"(代码生成), "text"(文本推理), "auto"(自动检测)
    :param return_reasoning: 是否返回模型的推理过程
    :return: reasoner模型的响应，通常包含详细的解决方案
    """
    # 创建DeepSeek API客户端
    client = OpenAI(api_key=os.environ.get("api_key"), base_url="https://api.deepseek.com/beta")
    
    # 自动检测模式 - 分析问题是否与代码相关
    if mode == "auto":
        code_keywords = ['代码', '编程', '函数', '算法', '实现', 'bug', '错误', '修复', 
                         'code', 'function', 'programming', 'algorithm', 'implement', 
                         'class', 'python', 'java', 'javascript', 'c++', 'html', 'css']
        
        # 检查消息中是否包含代码关键词
        has_code_keywords = any(keyword in message.lower() for keyword in code_keywords)
        
        # 检查是否包含代码块
        has_code_block = '```' in message
        
        # 如果包含代码关键词或代码块，则使用代码模式
        mode = "code" if (has_code_keywords or has_code_block) else "text"
    
    # 根据模式设置系统提示词和格式化参数
    if mode == "code":
        system_content = "你是DeepSeek Reasoner，一个专门解决复杂编程和推理问题的AI助手。请先仔细思考问题，分析可能的解决方案，然后提供最优答案。解答编程问题时，请提供完整、可运行的代码，并确保代码逻辑清晰。"
        prefix_content = "```python\n"
        stop_sequence = ["```"]
    else:  # text模式
        system_content = "你是DeepSeek Reasoner，一个专注于深度思考和复杂推理的AI助手。面对问题时，请先进行系统性思考，分析各种可能性，考虑不同角度，然后提供深入、全面的答案。请保持逻辑清晰，回答有条理，并尽可能提供具体例子来支持你的观点。"
        prefix_content = ""
        stop_sequence = None

    # 构建优化的提示词
    messages = [
        {"role": "system", "content": system_content},
        {"role": "user", "content": message}
    ]
    
    # 添加前缀（如果有）
    if prefix_content:
        messages.append({"role": "assistant", "content": prefix_content, "prefix": True})
    
    # 调用模型API
    response_r1 = client.chat.completions.create(
        model="deepseek-reasoner",
        messages=messages,
        stop=stop_sequence,
        temperature=0.5  # 降低温度参数，使输出更加确定性和精确
    )
    
    # 获取模型推理过程和最终结果
    reasoning_content = response_r1.choices[0].message.reasoning_content
    content = response_r1.choices[0].message.content
    
    # 如果是代码模式，确保代码块格式正确
    if mode == "code" and not content.strip().endswith("```"):
        content = content + "\n```"
    
    # 返回结果
    if return_reasoning:
        return {
            "result": str(content),
            "reasoning": str(reasoning_content)
        }
    
    return str(content)

# 添加一个便捷的文本推理专用函数
def r1_text_reasoning(message: str, return_reasoning=False) -> str:
    """文本推理专用函数，强制使用text模式"""
    return r1_optimizer(message, mode="text", return_reasoning=return_reasoning)

# 添加一个便捷的代码生成专用函数
def r1_code_generator(message: str, return_reasoning=False) -> str:
    """代码生成专用函数，强制使用code模式"""
    return r1_optimizer(message, mode="code", return_reasoning=return_reasoning)
