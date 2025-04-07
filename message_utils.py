import tiktoken
from typing import Optional, List, Dict, Any
import re
from openai import OpenAI
import os
import json
from console_utils import print_color, print_success, print_error, print_warning, print_info, print_highlight

# 消息Token计数函数
def num_tokens_from_messages(messages, model="deepseek-chat"):
    """
    计算消息列表中的token数量
    :param messages: 消息列表
    :param model: 模型名称
    :return: token数量
    """
    try:
        # 使用缓存减少重复编码创建
        if not hasattr(num_tokens_from_messages, "_encoding"):
            num_tokens_from_messages._encoding = tiktoken.encoding_for_model("gpt-3.5-turbo")
        encoding = num_tokens_from_messages._encoding
        
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
        # 出错时使用简单估算方法
        return sum(len(str(m.get("content", ""))) // 3 for m in messages) + 20

# LLM评估消息重要性
async def evaluate_message_importance(messages, client, max_tokens=30000):
    """
    使用LLM评估消息的重要性，决定哪些消息可以被清理
    :param messages: 消息列表
    :param client: OpenAI客户端
    :param max_tokens: 目标token数量
    :return: 清理建议，包含应保留和应删除的消息索引
    """
    current_tokens = num_tokens_from_messages(messages)
    if current_tokens <= max_tokens:
        return {"keep_all": True}
    
    print_info(f"\n===== 使用LLM评估消息重要性 =====")
    print_info(f"当前token数: {current_tokens}, 目标: {max_tokens}")
    
    # 准备评估消息
    # 不包含system消息，因为它们总是被保留
    non_system_messages = [msg for i, msg in enumerate(messages) if msg["role"] != "system"]
    
    # 准备消息的简短描述，供LLM评估
    message_summaries = []
    for i, msg in enumerate(non_system_messages):
        # 为不同类型的消息创建概要
        if msg["role"] == "user":
            content = msg.get("content", "")
            # 如果内容太长，截断它
            if len(content) > 100:
                content = content[:97] + "..."
            message_summaries.append(f"索引 {i}: 用户消息 - '{content}'")
        
        elif msg["role"] == "assistant":
            if msg.get("tool_calls"):
                tool_names = []
                for tc in msg.get("tool_calls", []):
                    if isinstance(tc, dict) and tc.get("function", {}).get("name"):
                        tool_names.append(tc["function"]["name"])
                tool_str = ", ".join(tool_names)
                message_summaries.append(f"索引 {i}: 助手消息 - 工具调用: {tool_str}")
            else:
                content = msg.get("content", "")
                if content and len(content) > 100:
                    content = content[:97] + "..."
                message_summaries.append(f"索引 {i}: 助手消息 - '{content}'")
        
        elif msg["role"] == "tool":
            tool_id = msg.get("tool_call_id", "未知")
            content = msg.get("content", "")
            if content and len(content) > 100:
                content = content[:97] + "..."
            message_summaries.append(f"索引 {i}: 工具结果 - ID:{tool_id}, '{content}'")
    
    # 准备评估提示
    evaluation_prompt = f"""
作为一个对话清理专家，你需要分析以下消息列表，确定哪些消息对当前对话最不重要，可以被删除以减少token数量。
当前token数: {current_tokens}，目标token数: {max_tokens}，需要减少约 {current_tokens - max_tokens} tokens。

消息列表:
{chr(10).join(message_summaries)}

规则:
1. 系统消息已自动保留，不在此列表中
2. 保留最近的用户消息和助手回复
3. 保留形成完整工具调用链的消息（一个assistant工具调用消息及其对应的tool响应消息）
4. 优先删除较早的、不相关的或重复信息的消息
5. 优先保留包含关键信息或重要指令的消息

以JSON格式返回你的决策:
{
  "to_remove": [消息索引列表],
  "to_keep": [消息索引列表],
  "reasoning": "简短说明你的决策理由"
}
"""
    
    try:
        # 调用LLM进行评估
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[{"role": "user", "content": evaluation_prompt}],
            temperature=0.1
        )
        
        result = response.choices[0].message.content
        
        # 尝试解析JSON结果
        try:
            parsed_result = json.loads(result)
            print_info(f"LLM评估结果: 建议保留{len(parsed_result.get('to_keep', []))}条消息，删除{len(parsed_result.get('to_remove', []))}条消息")
            print_info(f"理由: {parsed_result.get('reasoning', '未提供')}")
            return parsed_result
        except json.JSONDecodeError:
            print_warning("无法解析LLM返回的JSON，将使用默认清理规则")
            return {"keep_all": False}
        
    except Exception as e:
        print_warning(f"调用LLM评估消息重要性失败: {str(e)}")
        return {"keep_all": False}

# 清理不重要的消息历史
async def clean_message_history_with_llm(messages, client, max_tokens=30000):
    """
    使用LLM智能清理消息历史，保留重要信息并减少token数量
    :param messages: 消息列表
    :param client: OpenAI客户端
    :param max_tokens: 目标token数量
    :return: 清理后的消息列表
    """
    if num_tokens_from_messages(messages) <= max_tokens:
        return messages
    
    print_info(f"\n===== Token数量超过阈值，使用LLM清理消息历史 =====")
    
    # 保留system消息
    system_messages = [msg for msg in messages if msg["role"] == "system"]
    
    # 获取LLM的清理建议
    evaluation_result = await evaluate_message_importance(messages, client, max_tokens)
    
    # 如果LLM建议保留所有消息或评估失败，使用默认清理逻辑
    if evaluation_result.get("keep_all", False) or "to_keep" not in evaluation_result:
        print_info("使用默认清理规则")
        return clean_message_history(messages, max_tokens)
    
    # 获取要保留的消息索引
    to_keep_indices = evaluation_result.get("to_keep", [])
    
    # 获取非系统消息
    non_system_messages = [msg for msg in messages if msg["role"] != "system"]
    
    # 根据索引保留重要消息
    kept_messages = []
    for i in to_keep_indices:
        if 0 <= i < len(non_system_messages):
            kept_messages.append(non_system_messages[i])
    
    # 最后的完整性检查：确保所有工具调用都有对应的响应
    tool_call_ids = []
    messages_to_remove = []
    
    # 收集所有工具调用ID
    for i, msg in enumerate(kept_messages):
        if msg["role"] == "assistant" and msg.get("tool_calls"):
            for tool_call in msg.get("tool_calls", []):
                if isinstance(tool_call, dict) and tool_call.get("id"):
                    tool_call_ids.append(tool_call["id"])
    
    # 检查每个工具调用是否有对应响应
    response_ids = [msg.get("tool_call_id") for msg in kept_messages if msg["role"] == "tool"]
    missing_responses = set(tool_call_ids) - set(response_ids)
    
    # 如果有未匹配的工具调用，从kept_messages中移除
    if missing_responses:
        print_warning(f"有{len(missing_responses)}个工具调用没有对应响应，将移除这些调用")
        for i, msg in enumerate(kept_messages):
            if msg["role"] == "assistant" and msg.get("tool_calls"):
                new_tool_calls = []
                for tool_call in msg.get("tool_calls", []):
                    if tool_call.get("id") not in missing_responses:
                        new_tool_calls.append(tool_call)
                
                if not new_tool_calls:
                    messages_to_remove.append(i)
                else:
                    kept_messages[i]["tool_calls"] = new_tool_calls
    
    # 移除标记为删除的消息
    kept_messages = [msg for i, msg in enumerate(kept_messages) if i not in messages_to_remove]
    
    # 组合清理后的消息
    cleaned_messages = system_messages + kept_messages
    
    # 如果仍然超过限制，使用默认方法进一步减少
    if num_tokens_from_messages(cleaned_messages) > max_tokens:
        print_warning("LLM清理后仍超过token限制，使用默认方法进一步清理")
        return clean_message_history(cleaned_messages, max_tokens)
    
    current_tokens = num_tokens_from_messages(cleaned_messages)
    print_info(f"LLM清理后token数量: {current_tokens} (目标: {max_tokens})")
    
    return cleaned_messages

# 更新后的clean_message_history函数，更高效的实现
def clean_message_history(messages, max_tokens=30000):
    """
    清理消息历史，保留重要信息并减少token数量
    :param messages: 消息列表
    :param max_tokens: 目标token数量
    :return: 清理后的消息列表
    """
    current_tokens = num_tokens_from_messages(messages)
    if current_tokens <= max_tokens:
        return messages
    
    print_info(f"\n===== Token数量超过阈值 ({current_tokens}>{max_tokens})，正在清理消息历史 =====")
    
    # 保留system消息，它们通常很重要
    system_messages = [msg for msg in messages if msg["role"] == "system"]
    system_tokens = num_tokens_from_messages(system_messages)
    
    # 剩余可用token
    remaining_tokens = max_tokens - system_tokens
    
    # 如果仅system消息就超过了限制，则必须裁剪system消息
    if system_tokens > max_tokens * 0.8:  # 允许system消息最多占用80%的配额
        print_warning("系统消息占用token过多，将裁剪部分系统消息")
        # 按重要性排序：保留第一条和最后一条system消息
        if len(system_messages) > 2:
            system_messages = [system_messages[0], system_messages[-1]]
            # 重新计算system消息的token数
            system_tokens = num_tokens_from_messages(system_messages)
            remaining_tokens = max_tokens - system_tokens
    
    # 其余非系统消息
    non_system_messages = [msg for msg in messages if msg["role"] != "system"]
    
    # 如果没有非系统消息，直接返回系统消息
    if not non_system_messages:
        return system_messages
    
    # 为了保留对话连贯性，我们需要保留最近的消息
    # 估计每条消息的平均token数
    avg_msg_tokens = (current_tokens - system_tokens) / len(non_system_messages)
    
    # 估计可以保留的消息数量
    keep_msg_count = int(remaining_tokens / avg_msg_tokens * 0.95)  # 预留5%的余量
    
    # 确保至少保留几条最近消息
    keep_msg_count = max(keep_msg_count, min(4, len(non_system_messages)))
    
    # 保留最近的消息
    kept_messages = non_system_messages[-keep_msg_count:]
    
    # 组合最终的消息列表
    cleaned_messages = system_messages + kept_messages
    
    # 验证清理后的token数量
    final_tokens = num_tokens_from_messages(cleaned_messages)
    
    # 如果仍然超出限制，递归调用直到满足要求
    if final_tokens > max_tokens:
        # 进一步减少保留的消息数量
        print_warning(f"第一次清理后仍超过限制 ({final_tokens}>{max_tokens})，继续清理...")
        # 递归调用，但减少目标token以确保一定能满足
        return clean_message_history(cleaned_messages, max_tokens - 1000)
    
    print_success(f"清理完成，从 {current_tokens} 减少到 {final_tokens} tokens，保留了 {len(kept_messages)}/{len(non_system_messages)} 条非系统消息")
    
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