import os

from openai import OpenAI
import numpy as np
from dotenv import load_dotenv
load_dotenv()

def r1_optimizer(message: str) -> str:
    """
    调用DeepSeek Reasoner模型来解决复杂问题，特别适合代码生成和复杂bug修复
    
    该函数使用DeepSeek的reasoner模型，针对以下场景提供更强大的推理能力：
    1. 复杂代码生成：需要设计多层结构、算法实现等
    2. 难以修复的bug：需要深入理解和分析问题
    3. 算法设计与优化：需要高效的解决方案
    4. 复杂逻辑推理：需要多步骤的思考过程
    
    :param message: 包含完整问题描述和必要上下文的字符串
    :return: reasoner模型的响应，通常包含详细的解决方案
    """
    # 创建DeepSeek API客户端
    client = OpenAI(api_key=os.environ.get("api_key"), base_url="https://api.deepseek.com/beta")

    # 构建优化的提示词，鼓励模型先思考再解决问题
    messages = [
        {"role": "system", "content": "你是DeepSeek Reasoner，一个专门解决复杂编程和推理问题的AI助手。请先仔细思考问题，分析可能的解决方案，然后提供最优答案。"},
        {"role": "user", "content": message},
        {"role": "assistant", "content": "```python\n", "prefix": True}
    ]
    
    # 调用模型API
    response_r1 = client.chat.completions.create(
        model="deepseek-reasoner",
        messages=messages,
        stop=["```"],
        temperature=0.3  # 降低温度参数，使输出更加确定性和精确
    )
    
    # 获取模型推理过程和最终结果
    reasoning_content = response_r1.choices[0].message.reasoning_content
    content = response_r1.choices[0].message.content
    
    # 如果需要，可以在这里添加结果的后处理逻辑
    
    return str(content)
