from openai import OpenAI
import json
from datetime import datetime, timedelta
import asyncio
import os
import get_email
import re
from queue import Queue
import python_tools
import send_email
import ssh_controller
from dotenv import load_dotenv
from R1_optimize import r1_optimizer as R1
from tts_http_demo import tts_volcano
import code_tools 
import file_reader
import tool_registry
from weather_utils import get_weather
from time_utils import get_current_time
from input_utils import get_user_input_async
from file_utils import user_information_read
from error_utils import parse_error_message, task_error_analysis
from message_utils import num_tokens_from_messages, clean_message_history, clear_context
from console_utils import print_color, print_success, print_error, print_warning, print_info, print_highlight
from system_utils import powershell_command, list_directory

load_dotenv()
message_queue = Queue()

# 使用集中的工具注册
tools = tool_registry.get_tools()

client = OpenAI(api_key=os.environ.get("api_key"), base_url="https://api.deepseek.com")


messages = [{"role": "system","content": " 你叫小美，是一个热情的ai助手，这些是用户的一些关键信息，可能有用: "+user_information_read()}, 
{"role": "system","content": " 注意：1.文件操作必须使用绝对路径 2.危险操作要自动添加安全参数 "}]

# 添加任务规划和错误修复
task_planning_system_message = {
    "role": "system",
    "content": """你现在是一个自主规划任务的智能体，请遵循以下原则：
1. 接收到任务后，首先分析任务需求
2. 仅提供高层次概括的计划，不要提供详细步骤
3. 不要提供具体命令、代码、参数等执行细节
4. 不要使用具体的文件路径或文件名
5. 不要猜测用户环境和系统配置

执行方式：
- 任务拆解应限制在3-5个高级步骤
- 每个步骤只描述"做什么"，不描述"怎么做"
- 不要提供具体工具选择的建议
- 不要假设任何环境配置
- 提供简短的目标描述，而非执行说明


任务分析完成后，agent会自行确定具体执行步骤、选择适当工具，并执行必要操作。你的任务只是提供高层次指导，而非执行细节。
"""
}

async def execute_task_with_planning(user_input, messages_history):
    """
    使用任务规划执行用户请求
    """
    # 添加任务规划系统消息
    planning_messages = messages_history.copy()
    
    # 替换或添加任务规划系统消息
    system_message_index = next((i for i, msg in enumerate(planning_messages) if msg["role"] == "system"), None)
    if system_message_index is not None:
        combined_content = planning_messages[system_message_index]["content"] + "\n\n" + task_planning_system_message["content"]
        planning_messages[system_message_index]["content"] = combined_content
    else:
        planning_messages.insert(0, task_planning_system_message)
    
    # 添加用户输入
    planning_messages.append({"role": "user", "content": f"请分析以下任务，只提供高层次任务计划（3-5个步骤），不要提供具体执行细节：{user_input}"})
    
    # 检查token数量
    token_count = num_tokens_from_messages(planning_messages)
    print_info(f"\n===== 初始token数量: {token_count} =====")
    if token_count > 30000:  # 设置30000作为预警阈值
        planning_messages = clean_message_history(planning_messages)
    
    # 获取任务规划
    try:
        planning_response = client.chat.completions.create(
            model="deepseek-chat",
            messages=planning_messages,
            temperature=0.3
        )
        
        task_plan = planning_response.choices[0].message.content
        print("\n===== 任务规划（高层次目标）=====")
        print(task_plan)
        print("====================\n")
        
        # 添加任务规划到对话历史
        planning_messages.append({"role": "assistant", "content": task_plan})
        
        # 执行任务（最多尝试5次）
        max_attempts = 5
        for attempt in range(max_attempts):
            try:
                # 添加执行提示
                execution_prompt = f"""现在开始执行任务计划的第{attempt+1}次尝试。
基于上述高层次目标，请自行确定具体执行步骤并调用适当的工具。
不要解释你将如何执行，直接调用工具执行必要操作。
每次只执行一个具体步骤，等待结果后再决定下一步。"""

                if attempt > 0:
                    execution_prompt += f" 这是第{attempt+1}次尝试，前面{attempt}次尝试失败。请根据之前的错误调整策略。"
                
                planning_messages.append({"role": "user", "content": execution_prompt})
                
                # 初始化递归验证
                recursive_verify_count = 0
                max_recursive_verify = 10  # 最大递归验证次数
                is_task_complete = False
                current_execution_messages = planning_messages.copy()
                
                # 初始化任务进度和R1调用计数
                task_progress = 0
                r1_call_count = 0  # 仅用于显示信息，不作为终止判断依据
                last_progress = 0
                progress_history = []  # 记录历次进度，仅用于显示和参考
                
                # 内部递归验证循环
                while recursive_verify_count < max_recursive_verify and not is_task_complete:
                    recursive_verify_count += 1
                    
                    # 显示迭代次数
                    print(f"\n===== 任务执行迭代 {recursive_verify_count}/{max_recursive_verify} =====")
                    
                    # 检查当前token数量
                    token_count = num_tokens_from_messages(current_execution_messages)
                    print_info(f"当前token数量: {token_count}")
                    
                    # 如果token数量超过阈值，清理消息历史
                    if token_count > 30000:  # 设置30000作为预警阈值
                        print_warning("Token数量超过预警阈值，清理消息历史...")
                        current_execution_messages = clean_message_history(current_execution_messages)
                    
                    # 调用API执行任务步骤
                    execution_response = client.chat.completions.create(
                        model="deepseek-chat",
                        messages=current_execution_messages,
                        tools=tools,
                        tool_choice="auto",
                        temperature=0.3
                    )
                    
                    message_data = execution_response.choices[0].message
                    
                    # 处理工具调用
                    if hasattr(message_data, 'tool_calls') and message_data.tool_calls:
                        # 执行工具调用并收集结果
                        tool_calls = message_data.tool_calls
                        tool_outputs = []
                        step_success = True
                        
                        # 添加助手消息和工具调用
                        current_execution_messages.append({
                            "role": "assistant",
                            "content": None,
                            "tool_calls": [
                                {
                                    "id": tc.id,
                                    "type": "function",
                                    "function": {
                                        "name": tc.function.name,
                                        "arguments": tc.function.arguments
                                    }
                                } for tc in tool_calls
                            ]
                        })
                        
                        for tool_call in tool_calls:
                            func_name = tool_call.function.name
                            args = json.loads(tool_call.function.arguments)
                            print(f"\n正在执行工具: {func_name}")
                            print(f"参数: {args}")
                            
                            try:
                                # 执行工具函数
                                if func_name == "get_current_time":
                                    result = get_current_time(args.get("timezone", "UTC"))
                                elif func_name == "get_weather":
                                    result = get_weather(args["city"])
                                elif func_name == "powershell_command":
                                    # 执行原始命令
                                    cmd_result = await powershell_command(args["command"])
                                    result = cmd_result
                                elif func_name == "email_check":
                                    result = get_email.retrieve_emails()
                                elif func_name == "email_details":
                                    result = get_email.get_email_details(args["email_id"])
                                elif func_name == "encoding":
                                    result = python_tools.encoding(args["encoding"], args["file_name"])
                                elif func_name == "send_mail":
                                    # 处理附件参数
                                    attachments = None
                                    if "attachments" in args and args["attachments"]:
                                        attachments_input = args["attachments"]
                                        # 如果是逗号分隔的多个文件，分割成列表
                                        if isinstance(attachments_input, str) and "," in attachments_input:
                                            # 分割字符串并去除每个路径两边的空格
                                            attachments = [path.strip() for path in attachments_input.split(",")]
                                        else:
                                            attachments = attachments_input
                                    
                                    result = send_email.main(args["text"], args["receiver"], args["subject"], attachments)
                                elif func_name == "R1_opt":
                                    result = R1(args["message"])
                                    r1_call_count += 1  # 增加R1调用计数
                                    print_warning(f"已使用R1深度思考工具，当前迭代: {recursive_verify_count}/{max_recursive_verify}")
                                elif func_name == "ssh":
                                    ip = "192.168.10.107"
                                    username = "ye"
                                    password = "147258"
                                    result = ssh_controller.ssh_interactive_command(ip, username, password, args["command"])
                                elif func_name == "clear_context":
                                    messages = clear_context(messages)  # 更新全局消息历史
                                    current_execution_messages = clear_context(current_execution_messages)  # 更新当前执行消息
                                    result = "上下文已清除"
                                    is_task_complete = True  # 标记任务完成
                                    # 设置验证结果为任务已完成
                                    verify_json = {
                                        "is_complete": True,
                                        "completion_status": "上下文已成功清除",
                                        "is_failed": False
                                    }
                                elif func_name == "write_code":
                                    result = code_tools.write_code(args["file_name"], args["code"])
                                elif func_name == "verify_code":
                                    result = code_tools.verify_code(args["code"])
                                elif func_name == "append_code":
                                    result = code_tools.append_code(args["file_name"], args["content"])
                                elif func_name == "read_code":
                                    result = code_tools.read_code(args["file_name"])
                                elif func_name == "create_module":
                                    result = code_tools.create_module(args["module_name"], args["functions_json"])
                                elif func_name == "user_input":
                                    # 新增工具: 请求用户输入
                                    prompt = args.get("prompt", "请提供更多信息：")
                                    timeout = args.get("timeout", 60)
                                    user_input = await get_user_input_async(prompt, timeout)
                                    result = f"用户输入: {user_input}" if user_input else "用户未提供输入（超时）"
                                elif func_name == "read_file":
                                    result = file_reader.read_file(args["file_path"], args["encoding"], args["extract_text_only"])
                                elif func_name == "list_files":
                                    result = file_reader.list_files(args["directory_path"], args["include_pattern"], args["recursive"])
                                elif func_name == "list_directory":
                                    result = await list_directory(args.get("path", "."))
                                else:
                                    raise ValueError(f"未定义的工具调用: {func_name}")
                                
                                print_success(f"工具执行结果: {result}")
                                
                                # 分析执行结果是否有错误
                                error_info = task_error_analysis(result, {"tool": func_name, "args": args})
                                if error_info["has_error"]:
                                    print_warning(f"\n检测到错误: {error_info['analysis']}")
                                    step_success = False
                                    
                                    # 将错误信息添加到结果中
                                    result = f"{result}\n\n分析: {error_info['analysis']}"
                                    
                                    # 发送错误信息到GUI
                                    if 'message_queue' in globals():
                                        message_queue.put({
                                            "type": "error",
                                            "text": f"工具 {func_name} 执行出错: {error_info['analysis']}"
                                        })
                                
                            except Exception as e:
                                error_msg = f"工具执行失败: {str(e)}"
                                print_error(f"\n===== 工具执行错误 =====")
                                print_error(f"工具名称: {func_name}")
                                print_error(f"错误类型: {type(e)}")
                                print_error(f"错误信息: {str(e)}")
                                print_error("========================\n")
                                result = error_msg
                                step_success = False
                                
                                # 发送错误到GUI
                                if 'message_queue' in globals():
                                    message_queue.put({"type": "error", "text": error_msg})
                            
                            # 添加工具结果到消息历史
                            current_execution_messages.append({
                                "role": "tool",
                                "tool_call_id": tool_call.id,
                                "content": str(result)
                            })
                            
                            # 发送工具结果到GUI
                            if 'message_queue' in globals():
                                message_queue.put({
                                    "type": "tool_result",
                                    "text": f"{func_name} 执行完成"
                                })
                            
                            tool_outputs.append({
                                "tool_call_id": tool_call.id,
                                "output": str(result)
                            })
                        
                        # 验证当前步骤执行后，任务是否完成
                        verify_prompt = """
                        请分析当前任务的执行情况：
                        
                        1. 对已完成的步骤进行简要总结
                        2. 评估当前任务的进展程度 (0-100%)
                        3. 确认是否需要调整原计划
                        4. 明确规划接下来的1-2步具体行动
                        
                        任务结束判断：
                        - 如果任务已完全完成，请明确表示"任务已完成"并总结结果
                        - 如果任务无法继续执行或遇到无法克服的障碍，请明确表示"任务失败"并说明原因
                        - 如果任务部分完成但达到了可接受的结果，请表示"任务部分完成"
                        
                        请清晰标记任务状态为：[完成]/[失败]/[继续]
                        """
                        
                        # 在验证前检查token数量
                        token_count = num_tokens_from_messages(current_execution_messages)
                        print_info(f"验证前token数量: {token_count}")
                        if token_count > 30000:
                            print_warning("Token数量超过预警阈值，清理消息历史...")
                            current_execution_messages = clean_message_history(current_execution_messages)
                        
                        current_execution_messages.append({"role": "user", "content": verify_prompt})
                        
                        # 调用验证
                        verify_response = client.chat.completions.create(
                            model="deepseek-chat",
                            messages=current_execution_messages,
                            temperature=0.1
                        )
                        
                        verify_result = verify_response.choices[0].message.content
                        print_info("\n===== 任务进展评估 =====")
                        print(verify_result)
                        print_info("=========================\n")
                        
                        # 添加验证结果到消息历史
                        current_execution_messages.append({"role": "assistant", "content": verify_result})
                        
                        # 解析验证结果 - 增强的结束任务判断
                        task_completed = False
                        task_failed = False
                        
                        # 检查是否明确标记了任务状态
                        if "[完成]" in verify_result:
                            is_task_complete = True
                            task_completed = True
                            print_success("\n✅ 任务明确标记为已完成! 准备生成总结...")
                            break
                        elif "[失败]" in verify_result:
                            is_task_complete = True  # 虽然失败但任务结束
                            task_failed = True
                            print_warning("\n⚠️ 任务明确标记为失败! 准备生成失败分析...")
                            break
                        
                        # 备用检查 - 基于文本内容判断
                        if "任务已完成" in verify_result or "任务完成" in verify_result:
                            is_task_complete = True
                            task_completed = True
                            print_success("\n✅ 任务已完成! 准备生成总结...")
                            break
                        elif "任务失败" in verify_result or "无法完成任务" in verify_result or "无法继续执行" in verify_result:
                            is_task_complete = True  # 虽然失败但任务结束
                            task_failed = True
                            print_warning("\n⚠️ 任务失败! 准备生成失败分析...")
                            break
                        elif "部分完成" in verify_result and "100%" not in verify_result:
                            # 任务部分完成但达到了可接受的状态
                            if "可接受" in verify_result or "已满足需求" in verify_result:
                                is_task_complete = True
                                task_completed = True
                                print_success("\n✅ 任务部分完成但已达到可接受状态! 准备生成总结...")
                                break
                        
                        # 检查是否多次重复相同的步骤 - 通过进度判断是否卡住
                        progress_match = re.search(r'(\d+)%', verify_result)
                        if progress_match:
                            current_progress = int(progress_match.group(1))
                            
                            # 如果连续3次进度没有变化且已经执行了至少5次迭代，认为任务卡住了
                            if recursive_verify_count >= 5:
                                # 使用非类成员变量存储进度历史
                                if 'last_progress_values' not in locals():
                                    last_progress_values = []
                                
                                last_progress_values.append(current_progress)
                                if len(last_progress_values) > 3:
                                    last_progress_values.pop(0)
                                
                                # 检查最近3次进度是否相同
                                if len(last_progress_values) == 3 and len(set(last_progress_values)) == 1:
                                    is_task_complete = True
                                    task_failed = True
                                    print_warning(f"\n⚠️ 任务进度已连续3次保持在{current_progress}%! 判定为无法继续进行...")
                                    break
                        
                        # 如果任务未完成，让模型根据当前进展动态规划下一步
                        if recursive_verify_count < max_recursive_verify:
                            plan_prompt = """
                            基于当前任务的进展情况，请执行下一步操作：
                            
                            1. 直接调用相应的工具执行下一步
                            2. 不要解释你将要做什么，直接执行
                            3. 根据实际情况灵活调整执行计划
                            4. 遇到问题主动寻找解决方案
                            
                            记住：
                            - 专注解决问题，而不是机械地按原计划执行
                            - 如果任务确实无法完成，请明确表示"任务失败"并说明原因
                            """
                            current_execution_messages.append({"role": "user", "content": plan_prompt})
                    else:
                        # 没有工具调用，可能是任务结束或需要进一步指导
                        content = message_data.content
                        current_execution_messages.append({"role": "assistant", "content": content})
                        
                        # 输出消息内容
                        print_info("\n===== 助手消息 =====")
                        print(content)
                        print_info("====================\n")
                        
                        # 检查是否包含完成信息
                        if "任务已完成" in content or "任务完成" in content:
                            is_task_complete = True
                            print_success("\n✅ 任务已完成! 准备生成总结...")
                            break
                        
                        # 如果模型未完成任务，提示继续
                        if recursive_verify_count < max_recursive_verify:
                            current_execution_messages.append({
                                "role": "user", 
                                "content": "请直接调用相应的工具继续执行任务，不要解释你将要做什么，直接执行。对于未完成部分，请自行决定具体步骤。"
                            })
                
                # 内部递归结束后，更新外部消息历史
                planning_messages = current_execution_messages.copy()
                
                # 检查任务是否在递归内完成
                if is_task_complete:
                    # 根据任务是否成功完成或失败选择不同提示
                    if not task_failed:
                        # 任务成功，获取简洁总结回复
                        planning_messages.append({
                            "role": "user", 
                            "content": "任务执行完成，请简洁总结执行结果（不超过100字）。使用简短句子，避免复杂解释。"
                        })
                    else:
                        # 任务失败，获取失败原因和建议
                        planning_messages.append({
                            "role": "user", 
                            "content": "任务执行失败，请简要说明失败原因和可能的解决方案（不超过100字）。"
                        })
                    
                    # 最后的总结回复
                    final_response = client.chat.completions.create(
                        model="deepseek-chat",
                        messages=planning_messages,
                        temperature=0.2,
                        max_tokens=150  # 限制token数量
                    )
                    
                    summary = final_response.choices[0].message.content
                    
                    if not task_failed:
                        print_info("\n===== 任务执行总结 =====")
                        print_highlight(summary)
                    else:
                        print_info("\n===== 任务失败分析 =====")
                        print_error(summary)
                    print_info("========================\n")
                    
                    # 添加到主对话历史
                    messages_history.append({"role": "user", "content": user_input})
                    messages_history.append({"role": "assistant", "content": summary})
                    
                    # 发送总结到GUI
                    if 'message_queue' in globals():
                        message_queue.put({"type": "assistant", "text": summary})
                        message_queue.put({"type": "complete"})
                    
                    return summary
                else:
                    # 任务在内部递归中未完成，添加错误反馈
                    if recursive_verify_count >= max_recursive_verify:
                        iteration_error = f"已达到最大内部验证次数({max_recursive_verify}次)，但任务仍未完成。"
                    else:
                        iteration_error = "执行过程中遇到无法克服的问题，任务未能完成。"
                    
                    planning_messages.append({
                        "role": "user", 
                        "content": f"执行任务时遇到错误。这是第{attempt+1}次尝试，{iteration_error}请分析错误原因并提出改进方案，以便下一次尝试。"
                    })
                    
                    error_analysis_response = client.chat.completions.create(
                        model="deepseek-chat",
                        messages=planning_messages,
                        temperature=0.2
                    )
                    
                    error_analysis = error_analysis_response.choices[0].message.content
                    print_info(f"\n===== 错误分析（尝试 {attempt+1}/{max_attempts}）=====")
                    print_error(error_analysis)
                    print_info("========================\n")
                    
                    # 添加错误分析到对话历史
                    planning_messages.append({"role": "assistant", "content": error_analysis})
                    
                    # 发送错误分析到GUI
                    if 'message_queue' in globals():
                        message_queue.put({
                            "type": "tool_result",
                            "text": f"分析错误并重试（尝试 {attempt+1}/{max_attempts}）"
                        })
                    
                    # 如果是最后一次尝试，返回失败
                    if attempt == max_attempts - 1:
                        failure_message = f"在{max_attempts}次尝试后，任务执行失败。以下是最终分析：\n\n{error_analysis}"
                        
                        # 添加到主对话历史
                        messages_history.append({"role": "user", "content": user_input})
                        messages_history.append({"role": "assistant", "content": failure_message})
                        
                        # 发送失败消息到GUI
                        if 'message_queue' in globals():
                            message_queue.put({"type": "assistant", "text": failure_message})
                            message_queue.put({"type": "complete"})
                        
                        return failure_message
                    
            except Exception as e:
                print_error(f"\n===== 执行错误 =====")
                print_error(f"错误类型: {type(e)}")
                print_error(f"错误信息: {str(e)}")
                print_error("===================\n")
                
                # 发送错误到GUI
                if 'message_queue' in globals():
                    message_queue.put({
                        "type": "error",
                        "text": f"执行错误: {str(e)}"
                    })
                
                # 如果是最后一次尝试，返回失败
                if attempt == max_attempts - 1:
                    error_message = f"执行任务时出现系统错误: {str(e)}"
                    
                    # 添加到主对话历史
                    messages_history.append({"role": "user", "content": user_input})
                    messages_history.append({"role": "assistant", "content": error_message})
                    
                    # 发送错误消息到GUI
                    if 'message_queue' in globals():
                        message_queue.put({"type": "assistant", "text": error_message})
                        message_queue.put({"type": "complete"})
                    
                    return error_message
        
    except Exception as e:
        error_message = f"任务规划失败: {str(e)}"
        print_error(f"\n===== 规划错误 =====")
        print_error(error_message)
        print_error("===================\n")
        
        # 添加到主对话历史
        messages_history.append({"role": "user", "content": user_input})
        messages_history.append({"role": "assistant", "content": error_message})
        
        # 发送规划错误到GUI
        if 'message_queue' in globals():
            message_queue.put({"type": "error", "text": error_message})
            message_queue.put({"type": "complete"})
        
        return error_message

async def main(input_message: str):
    global messages
    
    if input_message.lower() == 'quit':
        return False

    # 检查是否是清除上下文的命令
    if input_message.lower() in ["清除上下文", "清空上下文", "clear context", "reset context"]:
        messages = clear_context(messages)
        print_info("上下文已清除")
        return True  # 返回True表示应该继续执行程序而不是退出
        
    # 检查当前token数量
    token_count = num_tokens_from_messages(messages)
    print_info(f"当前对话token数量: {token_count}")
    if token_count > 30000:
        print_warning("Token数量超过预警阈值，清理消息历史...")
        messages = clean_message_history(messages)
            
    # 先尝试常规对话，检查是否需要调用工具
    messages.append({"role": "user", "content": input_message})

    try:
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=messages,
            tools=tools,
            tool_choice="auto",
            temperature=0.3
        )
        
        message_data = response.choices[0].message
        
        # 如果模型决定调用工具，则启动任务规划模式
        if hasattr(message_data, 'tool_calls') and message_data.tool_calls:
            # 回退消息历史，移除刚刚添加的用户消息，因为任务规划会重新添加
            messages.pop()
            print_info("检测到工具调用，启动任务规划系统...")
            return await execute_task_with_planning(input_message, messages)
        else:
            # 即使模型没有选择调用工具，也分析回复内容是否暗示需要执行任务
            assistant_message = message_data.content
            print(assistant_message)
            
            # 分析回复内容，检查是否为任务请求
            is_task_request = False
            task_indicators = [
                "我需要", "我可以帮你", "让我为你", "我会为你", "需要执行", "可以执行",
                "这需要", "可以通过", "需要使用", "我可以使用", "步骤如下", "操作步骤",
                "首先需要", "应该先", "我们可以", "建议执行", "应该执行"
            ]
            
            for indicator in task_indicators:
                if indicator in assistant_message:
                    is_task_request = True
                    break
                    
            # 如果内容暗示需要执行任务，切换到任务规划模式
            if is_task_request:
                # 删除刚才添加的消息，因为任务规划会重新添加
                messages.pop()
                print_info("内容分析显示这可能是一个任务请求，启动任务规划系统...")
                return await execute_task_with_planning(input_message, messages)
            
            # 普通对话回复
            messages.append({"role": "assistant", "content": assistant_message})
            
            # 发送到GUI队列
            if 'message_queue' in globals():
                message_queue.put({"type": "assistant", "text": assistant_message})
                message_queue.put({"type": "complete"})
            
            return assistant_message

    except Exception as e:
        # 将错误信息发送到GUI队列
        error_msg = f"API错误: {str(e)}"
        if 'message_queue' in globals():
            message_queue.put({"type": "error", "text": error_msg})
        
        print_error(f"常规对话失败: {error_msg}")
        print_info("切换到任务规划系统...")
        
        # 移除刚才添加的消息
        messages.pop()
        
        # 使用任务规划作为备选方案
        return await execute_task_with_planning(input_message, messages)


def reset_messages():
    """重置消息历史到初始状态"""
    global messages
    messages = [{"role": "system","content": " 你叫小美，是一个热情的ai助手，这些是用户的一些关键信息，可能有用: "+user_information_read()}] 

if __name__ == "__main__":
    if not os.path.exists("user_information.txt"):
        with open("user_information.txt", "w", encoding="utf-8") as file:
            file.write("用户关键信息表:user_information.txt")
        print(f"文件 '{"user_information.txt"}' 已创建")

    print("程序启动成功")
    while True:
        try:
            input_message = input("\n输入消息: ")
            
            if input_message:
                result = asyncio.run(main(input_message))
                # 只有当返回值明确为False时才退出循环
                if result is False:
                    break
        except KeyboardInterrupt:
            print("\n程序已被用户中断")
            break
        except Exception as e:
            print("\n===== 主程序错误 =====")
            print(f"错误类型: {type(e)}")
            print(f"错误信息: {str(e)}")
            print("=====================\n")