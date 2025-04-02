import tiktoken
from typing import Optional, List, Dict, Any
import re

# 消息Token计数函数
def num_tokens_from_messages(messages, model="deepseek-chat"):
    """
    计算消息列表中的token数量
    :param messages: 消息列表
    :param model: 模型名称
    :return: token数量
    """
    try:
        encoding = tiktoken.encoding_for_model("gpt-3.5-turbo")  # 使用兼容的编码方式
        
        num_tokens = 0
        for message in messages:
            # 每条消息的基础token数
            num_tokens += 4  # 每条消息有固定的开销
            
            for key, value in message.items():
                if key == "role" or key == "name":
                    num_tokens += len(encoding.encode(value)) + 1
                elif key == "content":
                    if value is not None:
                        num_tokens += len(encoding.encode(value))
                elif key == "tool_calls":
                    num_tokens += 4  # tool_calls字段的固定开销
                    for tool_call in value:
                        if isinstance(tool_call, dict):
                            # 处理工具调用的各个字段
                            for tc_key, tc_value in tool_call.items():
                                if tc_key == "function":
                                    # 处理函数字段
                                    for f_key, f_value in tc_value.items():
                                        if isinstance(f_value, str):
                                            num_tokens += len(encoding.encode(f_value))
                                else:
                                    if isinstance(tc_value, str):
                                        num_tokens += len(encoding.encode(tc_value))
        
        # 添加模型的基础token数
        num_tokens += 3  # 基础的token开销
        return num_tokens
    except Exception as e:
        print(f"计算token数量时出错: {str(e)}")
        # 如果无法计算，返回一个估计值
        return sum(len(str(m.get("content", ""))) for m in messages) // 3

# 清理不重要的消息历史
def clean_message_history(messages, max_tokens=30000):
    """
    清理消息历史，保留重要信息并减少token数量
    :param messages: 消息列表
    :param max_tokens: 目标token数量
    :return: 清理后的消息列表
    """
    if num_tokens_from_messages(messages) <= max_tokens:
        return messages
    
    print(f"\n===== Token数量超过阈值，正在清理消息历史 =====")
    
    # 保留system消息
    system_messages = [msg for msg in messages if msg["role"] == "system"]
    
    # 获取用户最后的消息
    recent_user_messages = [msg for msg in messages if msg["role"] == "user"][-2:]
    
    # 获取所有助手消息，并保留最近的回复
    assistant_messages = [msg for msg in messages if msg["role"] == "assistant"]
    recent_assistant = assistant_messages[-1:] if assistant_messages else []
    
    # 保留最重要的工具调用和结果
    tool_calls = []
    tool_results = []
    
    for i, msg in enumerate(messages):
        # 保留最近的工具调用
        if msg["role"] == "assistant" and msg.get("tool_calls") and i >= len(messages) - 10:
            tool_calls.append(msg)
        
        # 保留对应的结果
        if msg["role"] == "tool" and i >= len(messages) - 10:
            # 限制工具结果的长度
            if "content" in msg and isinstance(msg["content"], str) and len(msg["content"]) > 500:
                # 只保留前300个字符和后200个字符
                msg = msg.copy()
                msg["content"] = msg["content"][:300] + "\n...[内容已截断]...\n" + msg["content"][-200:]
            tool_results.append(msg)
    
    # 组合清理后的消息
    cleaned_messages = system_messages + recent_user_messages + recent_assistant + tool_calls + tool_results
    
    # 如果仍然超过限制，继续减少工具结果的内容
    if num_tokens_from_messages(cleaned_messages) > max_tokens:
        for i, msg in enumerate(cleaned_messages):
            if msg["role"] == "tool" and "content" in msg and isinstance(msg["content"], str):
                # 进一步限制内容
                cleaned_messages[i] = msg.copy()
                cleaned_messages[i]["content"] = msg["content"][:100] + "\n...[大部分内容已省略]...\n" + msg["content"][-100:]
    
    current_tokens = num_tokens_from_messages(cleaned_messages)
    print(f"清理后token数量: {current_tokens} (目标: {max_tokens})")
    
    return cleaned_messages

# 清除对话上下文
def clear_context(messages: list) -> list:
    """
    清除对话上下文
    :param messages: 当前的对话历史
    :return: 清空后的对话历史，只保留系统消息
    """
    # 保留系统消息，清除其他消息
    system_messages = [msg for msg in messages if msg["role"] == "system"]
    return system_messages 