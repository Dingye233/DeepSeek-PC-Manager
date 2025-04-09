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
            # 处理可能的ChatCompletionMessage对象
            if not isinstance(message, dict):
                # 如果不是字典，尝试获取其属性
                try:
                    # 创建一个字典来处理非字典类型的消息对象
                    msg_dict = {}
                    if hasattr(message, 'role'):
                        msg_dict['role'] = message.role
                    if hasattr(message, 'content'):
                        msg_dict['content'] = message.content
                    if hasattr(message, 'name'):
                        msg_dict['name'] = message.name
                    if hasattr(message, 'tool_calls'):
                        msg_dict['tool_calls'] = message.tool_calls
                    message = msg_dict
                except:
                    # 如果无法处理，则跳过
                    continue
            
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
        try:
            token_sum = 0
            for m in messages:
                if isinstance(m, dict) and 'content' in m:
                    content = m['content']
                    if content:
                        token_sum += len(str(content)) // 3
                elif hasattr(m, 'content'):
                    content = m.content
                    if content:
                        token_sum += len(str(content)) // 3
            return token_sum + 20
        except:
            return 1000  # 如果完全无法估算，返回一个默认值

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
    non_system_messages = []
    for msg in messages:
        # 处理可能的ChatCompletionMessage对象
        role = msg['role'] if isinstance(msg, dict) else msg.role if hasattr(msg, 'role') else None
        if role != "system":
            non_system_messages.append(msg)
    
    # 准备消息的简短描述，供LLM评估
    message_summaries = []
    for i, msg in enumerate(non_system_messages):
        # 处理可能的ChatCompletionMessage对象
        if isinstance(msg, dict):
            role = msg.get('role', '')
            content = msg.get('content', '')
            tool_calls = msg.get('tool_calls', [])
            tool_call_id = msg.get('tool_call_id', '未知')
        else:
            role = msg.role if hasattr(msg, 'role') else ''
            content = msg.content if hasattr(msg, 'content') else ''
            tool_calls = msg.tool_calls if hasattr(msg, 'tool_calls') else []
            tool_call_id = getattr(msg, 'tool_call_id', '未知') if hasattr(msg, 'tool_call_id') else '未知'
            
        # 为不同类型的消息创建概要
        if role == "user":
            # 如果内容太长，截断它
            if len(content) > 100:
                content = content[:97] + "..."
            message_summaries.append(f"索引 {i}: 用户消息 - '{content}'")
        
        elif role == "assistant":
            if tool_calls:
                tool_names = []
                for tc in tool_calls:
                    if isinstance(tc, dict) and 'function' in tc and 'name' in tc['function']:
                        tool_names.append(tc['function']['name'])
                    elif hasattr(tc, 'function') and hasattr(tc.function, 'name'):
                        tool_names.append(tc.function.name)
                tool_str = ", ".join(tool_names)
                message_summaries.append(f"索引 {i}: 助手消息 - 工具调用: {tool_str}")
            else:
                if content and len(content) > 100:
                    content = content[:97] + "..."
                message_summaries.append(f"索引 {i}: 助手消息 - '{content}'")
        
        elif role == "tool":
            if content and len(content) > 100:
                content = content[:97] + "..."
            message_summaries.append(f"索引 {i}: 工具结果 - ID:{tool_call_id}, '{content}'")
    
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
    system_messages = []
    for msg in messages:
        # 处理可能的ChatCompletionMessage对象
        if isinstance(msg, dict):
            role = msg.get('role', '')
        else:
            role = msg.role if hasattr(msg, 'role') else ''
        
        if role == "system":
            system_messages.append(msg)
    
    # 获取LLM的清理建议
    evaluation_result = await evaluate_message_importance(messages, client, max_tokens)
    
    # 如果LLM建议保留所有消息或评估失败，使用默认清理逻辑
    if evaluation_result.get("keep_all", False) or "to_keep" not in evaluation_result:
        print_info("使用默认清理规则")
        return clean_message_history(messages, max_tokens)
    
    # 获取要保留的消息索引
    to_keep_indices = evaluation_result.get("to_keep", [])
    
    # 获取非系统消息
    non_system_messages = []
    for msg in messages:
        # 处理可能的ChatCompletionMessage对象
        if isinstance(msg, dict):
            role = msg.get('role', '')
        else:
            role = msg.role if hasattr(msg, 'role') else ''
        
        if role != "system":
            non_system_messages.append(msg)
    
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
        # 处理可能的ChatCompletionMessage对象
        if isinstance(msg, dict):
            role = msg.get('role', '')
            tool_calls = msg.get('tool_calls', [])
        else:
            role = msg.role if hasattr(msg, 'role') else ''
            tool_calls = msg.tool_calls if hasattr(msg, 'tool_calls') else []
        
        if role == "assistant" and tool_calls:
            for tool_call in tool_calls:
                if isinstance(tool_call, dict) and 'id' in tool_call:
                    tool_call_ids.append(tool_call['id'])
                elif hasattr(tool_call, 'id'):
                    tool_call_ids.append(tool_call.id)
    
    # 检查每个工具调用是否有对应响应
    response_ids = []
    for msg in kept_messages:
        # 处理可能的ChatCompletionMessage对象
        if isinstance(msg, dict):
            role = msg.get('role', '')
            tool_call_id = msg.get('tool_call_id', '')
        else:
            role = msg.role if hasattr(msg, 'role') else ''
            tool_call_id = msg.tool_call_id if hasattr(msg, 'tool_call_id') else ''
        
        if role == "tool" and tool_call_id:
            response_ids.append(tool_call_id)
    
    # 确保保留的消息中有完整的工具调用链
    for msg in non_system_messages:
        # 处理可能的ChatCompletionMessage对象
        if isinstance(msg, dict):
            role = msg.get('role', '')
            tool_calls = msg.get('tool_calls', [])
            tool_call_id = msg.get('tool_call_id', '')
        else:
            role = msg.role if hasattr(msg, 'role') else ''
            tool_calls = msg.tool_calls if hasattr(msg, 'tool_calls') else []
            tool_call_id = msg.tool_call_id if hasattr(msg, 'tool_call_id') else ''
        
        # 如果是助手消息，检查是否有工具调用没有对应响应
        if role == "assistant" and tool_calls:
            for tool_call in tool_calls:
                tc_id = None
                if isinstance(tool_call, dict) and 'id' in tool_call:
                    tc_id = tool_call['id']
                elif hasattr(tool_call, 'id'):
                    tc_id = tool_call.id
                
                if tc_id and tc_id in tool_call_ids and tc_id not in response_ids:
                    # 找到工具响应并添加到保留消息中
                    for response_msg in non_system_messages:
                        if isinstance(response_msg, dict):
                            resp_role = response_msg.get('role', '')
                            resp_id = response_msg.get('tool_call_id', '')
                        else:
                            resp_role = response_msg.role if hasattr(response_msg, 'role') else ''
                            resp_id = response_msg.tool_call_id if hasattr(response_msg, 'tool_call_id') else ''
                        
                        if resp_role == "tool" and resp_id == tc_id and response_msg not in kept_messages:
                            kept_messages.append(response_msg)
                            response_ids.append(tc_id)
        
        # 如果是工具响应消息，检查是否有对应的工具调用消息
        elif role == "tool" and tool_call_id and tool_call_id in tool_call_ids and msg not in kept_messages:
            # 确认是否有对应的调用消息
            has_call = False
            for call_msg in kept_messages:
                if isinstance(call_msg, dict):
                    call_role = call_msg.get('role', '')
                    call_tool_calls = call_msg.get('tool_calls', [])
                else:
                    call_role = call_msg.role if hasattr(call_msg, 'role') else ''
                    call_tool_calls = call_msg.tool_calls if hasattr(call_msg, 'tool_calls') else []
                
                if call_role == "assistant" and call_tool_calls:
                    for tc in call_tool_calls:
                        tc_id = None
                        if isinstance(tc, dict) and 'id' in tc:
                            tc_id = tc['id']
                        elif hasattr(tc, 'id'):
                            tc_id = tc.id
                        
                        if tc_id == tool_call_id:
                            has_call = True
                            break
                
                if has_call:
                    break
            
            # 如果没有对应的调用消息，该响应消息无用
            if not has_call:
                messages_to_remove.append(msg)
    
    # 移除不需要的消息
    for msg in messages_to_remove:
        if msg in kept_messages:
            kept_messages.remove(msg)
    
    # 构建最终清理后的消息列表
    cleaned_messages = system_messages + kept_messages
    
    # 验证token数量是否在目标范围内
    final_tokens = num_tokens_from_messages(cleaned_messages)
    if final_tokens > max_tokens:
        print_warning(f"LLM清理后token仍然超过目标（{final_tokens} > {max_tokens}），使用默认清理方法")
        return clean_message_history(messages, max_tokens)
    
    print_success(f"消息历史清理完成: {len(messages)} -> {len(cleaned_messages)} 条消息, {final_tokens} tokens")
    return cleaned_messages

# 更新后的clean_message_history函数，更高效的实现
def clean_message_history(messages, max_tokens=30000):
    """
    清理消息历史，保留重要消息并减少token数量
    :param messages: 消息列表
    :param max_tokens: 目标token数量
    :return: 清理后的消息列表
    """
    current_tokens = num_tokens_from_messages(messages)
    if current_tokens <= max_tokens:
        return messages
    
    print_info(f"\n===== 清理消息历史 =====")
    print_info(f"当前token数: {current_tokens}, 目标: {max_tokens}")
    
    # 分离系统消息和非系统消息
    system_messages = []
    non_system_messages = []
    
    for msg in messages:
        # 处理可能的ChatCompletionMessage对象
        if isinstance(msg, dict):
            role = msg.get('role', '')
        else:
            role = msg.role if hasattr(msg, 'role') else ''
        
        if role == "system":
            system_messages.append(msg)
        else:
            non_system_messages.append(msg)
    
    # 保留最近的20条消息（可能超过token限制）
    kept_recent = non_system_messages[-20:] if len(non_system_messages) > 20 else non_system_messages
    
    # 如果仍然超过限制，递归减半保留之前的消息
    cleaned_messages = system_messages + kept_recent
    
    if num_tokens_from_messages(cleaned_messages) > max_tokens and len(kept_recent) > 2:
        # 递归减半，直到满足token限制
        half_size = len(kept_recent) // 2
        return clean_message_history(system_messages + kept_recent[-half_size:], max_tokens)
    
    current_tokens = num_tokens_from_messages(cleaned_messages)
    print_info(f"清理后token数量: {current_tokens} (目标: {max_tokens})")
    
    return cleaned_messages

# 清除对话上下文
def clear_context(messages: list) -> list:
    """
    清除对话历史上下文，只保留系统消息
    :param messages: 消息列表
    :return: 只包含系统消息的消息列表
    """
    try:
        # 创建一个新的消息列表，只包含系统消息
        system_messages = []
        for msg in messages:
            # 处理可能的ChatCompletionMessage对象
            if isinstance(msg, dict):
                role = msg.get('role', '')
            else:
                role = msg.role if hasattr(msg, 'role') else ''
            
            if role == "system":
                system_messages.append(msg)
        
        if not system_messages:
            # 如果没有系统消息，返回一个空列表
            return []
        
        # 添加一条助手消息，说明上下文已清除
        system_messages.append({
            "role": "assistant",
            "content": "上下文已清除。我已经忘记了之前的对话内容，但仍然保留了关于如何与您互动的基本指导。"
        })
        
        return system_messages
    except Exception as e:
        print_error(f"清除上下文时出错: {str(e)}")
        return messages  # 出错时返回原始消息列表 