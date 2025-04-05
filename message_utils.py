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

# 更新后的clean_message_history函数，保留原始功能但可选使用LLM
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
    
    # 追踪需要保留的tool_call_ids
    required_tool_call_ids = set()
    
    # 收集最近10个消息中的所有工具调用
    tool_calls = []
    recent_messages = messages[-10:] if len(messages) > 10 else messages
    
    for msg in recent_messages:
        if msg["role"] == "assistant" and msg.get("tool_calls"):
            tool_calls.append(msg)
            # 记录所有需要响应的tool_call_ids
            for tool_call in msg.get("tool_calls", []):
                if isinstance(tool_call, dict) and tool_call.get("id"):
                    required_tool_call_ids.add(tool_call["id"])
    
    # 收集所有必要的工具响应
    tool_results = []
    for msg in messages:
        if msg["role"] == "tool" and msg.get("tool_call_id") in required_tool_call_ids:
            # 限制工具结果的长度
            if "content" in msg and isinstance(msg["content"], str) and len(msg["content"]) > 500:
                # 只保留前300个字符和后200个字符
                msg = msg.copy()
                msg["content"] = msg["content"][:300] + "\n...[内容已截断]...\n" + msg["content"][-200:]
            tool_results.append(msg)
            # 标记这个ID已处理
            if msg.get("tool_call_id") in required_tool_call_ids:
                required_tool_call_ids.remove(msg.get("tool_call_id"))
    
    # 检查是否所有tool_call_id都有对应响应
    if required_tool_call_ids:
        print_warning(f"警告: 有{len(required_tool_call_ids)}个工具调用没有对应响应")
        # 如果有未匹配的工具调用，从tool_calls中移除对应的消息
        filtered_tool_calls = []
        for msg in tool_calls:
            if msg.get("tool_calls"):
                # 创建消息副本
                new_msg = msg.copy()
                # 只保留有对应响应的工具调用
                new_tool_calls = []
                for tool_call in new_msg.get("tool_calls", []):
                    if tool_call.get("id") not in required_tool_call_ids:
                        new_tool_calls.append(tool_call)
                # 如果有保留的工具调用，更新消息
                if new_tool_calls:
                    new_msg["tool_calls"] = new_tool_calls
                    filtered_tool_calls.append(new_msg)
                # 如果没有保留任何工具调用，但有内容，则保留文本内容
                elif new_msg.get("content"):
                    new_msg.pop("tool_calls", None)
                    filtered_tool_calls.append(new_msg)
            else:
                filtered_tool_calls.append(msg)
        tool_calls = filtered_tool_calls
    
    # 组合清理后的消息
    cleaned_messages = system_messages + recent_user_messages + recent_assistant + tool_calls + tool_results
    
    # 如果仍然超过限制，继续减少工具结果的内容
    if num_tokens_from_messages(cleaned_messages) > max_tokens:
        for i, msg in enumerate(cleaned_messages):
            if msg["role"] == "tool" and "content" in msg and isinstance(msg["content"], str):
                # 进一步限制内容
                cleaned_messages[i] = msg.copy()
                cleaned_messages[i]["content"] = msg["content"][:100] + "\n...[大部分内容已省略]...\n" + msg["content"][-100:]
    
    # 最后一次检查消息序列完整性
    tool_call_ids = []
    tool_response_ids = []
    
    for msg in cleaned_messages:
        if msg["role"] == "assistant" and msg.get("tool_calls"):
            for tool_call in msg.get("tool_calls", []):
                if isinstance(tool_call, dict) and tool_call.get("id"):
                    tool_call_ids.append(tool_call["id"])
        elif msg["role"] == "tool" and msg.get("tool_call_id"):
            tool_response_ids.append(msg["tool_call_id"])
    
    # 确保每个工具调用都有对应响应
    missing_responses = set(tool_call_ids) - set(tool_response_ids)
    if missing_responses:
        print_warning(f"最终检查: 仍有{len(missing_responses)}个工具调用没有响应，将移除这些调用")
        # 再次过滤工具调用
        for i, msg in enumerate(cleaned_messages):
            if msg["role"] == "assistant" and msg.get("tool_calls"):
                # 创建消息副本
                new_msg = cleaned_messages[i].copy()
                # 只保留有对应响应的工具调用
                new_tool_calls = []
                for tool_call in new_msg.get("tool_calls", []):
                    if tool_call.get("id") not in missing_responses:
                        new_tool_calls.append(tool_call)
                # 更新消息
                if new_tool_calls:
                    new_msg["tool_calls"] = new_tool_calls
                else:
                    new_msg.pop("tool_calls", None)
                cleaned_messages[i] = new_msg
    
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