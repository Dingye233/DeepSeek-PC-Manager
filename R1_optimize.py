import os

from openai import OpenAI
import numpy as np
from dotenv import load_dotenv
load_dotenv()
def r1_optimizer(message:str)->str:
    client = OpenAI(api_key=os.environ.get("api_key"), base_url="https://api.deepseek.com/beta")

    messages=[{"role": "user", "content":message},{"role": "assistant", "content": "```python\n", "prefix": True}]
    response_r1 = client.chat.completions.create(
        model="deepseek-reasoner",
        messages=messages,
        stop=["```"]
    )
    reasoning_content = response_r1.choices[0].message.reasoning_content
    content = response_r1.choices[0].message.content
    return str(content)
def collect_user_information(message:str):
    client = OpenAI(api_key=os.environ.get("api_key"), base_url="https://api.deepseek.com/beta")
    with open("user_information.txt", "r", encoding="utf-8") as file:
        content = file.read()
    messages = [{"role":"system","content":"请提取用户文本里面的关键信息，只收集日常信息，然后跟前面收集的信息做对比，查漏补缺,提取不到关键信息则输出一个空字符串"},{"role":"system","content":"这是前面已经收集的信息: "+content},{"role": "user", "content":"这是用户跟其他模型交互的文本，提取一些有用的信息以构建用户的个性化需求:" +message}]
    response_r2 = client.chat.completions.create(
        model="deepseek-chat",
        messages=messages,
        temperature=0.5

    )
    content = response_r2.choices[0].message.content
    with open("user_information.txt", "a", encoding="utf-8") as file:
        file.write(content)