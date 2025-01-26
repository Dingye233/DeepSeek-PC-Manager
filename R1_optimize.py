import os

from openai import OpenAI
import numpy as np
from dotenv import load_dotenv
load_dotenv()
def r1_optimizer(message:str)->str:
    client = OpenAI(api_key=os.environ.get("api_key"), base_url="https://api.deepseek.com/beta")

    messages=[{"role": "user", "content": "判断用户是否有代码,命令,文本编辑的需求，如果没有这方面的需求直接输出一个空的字符串: "+message},{"role": "assistant", "content": "```python\n", "prefix": True}]
    response_r1 = client.chat.completions.create(
        model="deepseek-reasoner",
        messages=messages,
        stop=["```"]
    )
    reasoning_content = response_r1.choices[0].message.reasoning_content
    content = response_r1.choices[0].message.content
    return str(content)