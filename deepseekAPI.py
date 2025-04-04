from openai import OpenAI
import json
import asyncio
import os
import get_email
import re
import python_tools
import send_email
import ssh_controller
from dotenv import load_dotenv
from R1_optimize import r1_optimizer as R1
import code_tools 
import file_reader
import tool_registry
from weather_utils import get_weather
from time_utils import get_current_time
from input_utils import get_user_input_async, cancel_active_input  # 导入cancel_active_input函数
from file_utils import user_information_read
from error_utils import parse_error_message, task_error_analysis
from message_utils import num_tokens_from_messages, clean_message_history, clear_context, clean_message_history_with_llm
from console_utils import print_color, print_success, print_error, print_warning, print_info, print_highlight
from system_utils import powershell_command, cmd_command
import concurrent.futures
import sys  # 添加sys模块导入
import time  # 添加time模块导入

load_dotenv()

# 使用集中的工具注册
tools = tool_registry.get_tools()

client = OpenAI(api_key=os.environ.get("api_key"), base_url="https://api.deepseek.com")


messages = [{"role": "system","content": " 你叫小美，是一个热情的ai助手，这些是用户的一些关键信息，可能有用: "+user_information_read()}, 
{"role": "system","content": " 注意：1.文件操作必须使用绝对路径 2.危险操作要自动添加安全参数 3.对于涉及数据增删查改、批量处理、文件处理等复杂任务，必须优先使用Python脚本而非Shell命令，这样更安全高效且易于维护 4.创建脚本时确保使用合适的异常处理和备份机制 5.对于重复性操作或影响多个文件的操作，必须编写Python脚本而非手动执行命令 6.所有任务中创建的文件和脚本都应放在workspace文件夹下，如果该文件夹不存在则应先创建它 7.当处理数据量大或文件数量多时，绝对不要使用PowerShell或CMD命令，而应编写Python脚本 8.只有在执行简单的单一操作（如检查文件是否存在）时才考虑使用PowerShell或CMD"}]

# 将ask_user_to_continue函数从嵌套函数移到全局作用域
async def ask_user_to_continue(conversation_messages, is_task_complete=None):
    """询问用户是否继续尝试任务，即使智能体认为无法完成"""
    try:
        # 确保取消任何可能存在的输入任务
        cancel_active_input()
        time.sleep(0.1)  # 短暂等待确保取消完成
        
        print_highlight("\n===== 等待用户决策 =====")
        print_highlight("请输入您的想法或指示，按回车键提交")
        print_highlight("===========================")
        
        # 使用简单直接的输入模式
        try:
            user_choice = await get_user_input_async("智能体认为任务无法完成。您是否希望继续尝试，或者有其他建议？", 60)
            
            # 如果用户输入超时，默认继续执行
            if user_choice is None:
                print_warning("用户输入超时，默认继续尝试任务")
                # 默认继续尝试而非终止
                conversation_messages.append({
                    "role": "user", 
                    "content": "用户输入超时，系统默认继续尝试。请采用全新思路寻找解决方案。"
                })
                
                return "继续尝试"  # 返回默认值表示继续尝试
            
            # 正常处理用户输入
            if user_choice and user_choice.strip().lower() not in ["2", "终止", "停止", "结束", "放弃", "取消", "quit", "exit", "stop", "terminate", "cancel"]:
                # 用户选择继续尝试或提供了其他建议
                print_info(f"\n用户输入: {user_choice}")
                print_success("已接收用户输入，继续执行任务")
                
                # 重置任务失败标记（如果提供了is_task_complete参数）
                if is_task_complete is not None:
                    is_task_complete = False
                
                # 添加用户反馈到对话
                conversation_messages.append({
                    "role": "user", 
                    "content": f"用户希望继续尝试解决问题，并提供了以下反馈/建议：\n\"{user_choice}\"\n\n请考虑用户的输入，采用合适的方法继续解决问题。可以尝试新思路或按用户建议调整方案。直接开始执行，无需解释。"
                })
                
                return user_choice  # 直接返回用户输入
            else:
                # 用户确认终止
                print_warning("\n用户选择终止任务。")
                return user_choice  # 直接返回用户输入
                
        except asyncio.CancelledError:
            # 处理取消异常，默认继续执行
            print_warning("输入被取消，默认继续尝试任务")
            # 默认继续尝试而非终止
            conversation_messages.append({
                "role": "user", 
                "content": "系统检测到输入被取消，默认继续尝试。请采用全新思路寻找解决方案。"
            })
            
            return "继续尝试"  # 返回默认值表示继续尝试
            
    except Exception as e:
        # 获取用户输入失败时的处理，默认继续执行
        print_warning(f"获取用户输入失败: {str(e)}，默认继续尝试")
        # 默认继续尝试而非终止
        conversation_messages.append({
            "role": "user", 
            "content": "系统默认继续尝试。请采用全新思路寻找解决方案。"
        })
        
        return "继续尝试"  # 返回默认值表示继续尝试

# 添加任务规划和错误修复
task_planning_system_message = {
    "role": "system",
    "content": """你现在是一个自主规划任务的智能体，请遵循以下原则：
1. 接收到任务后，首先分析任务需求
2. 仅提供高层次概括的计划，不要提供详细步骤
3. 不要提供具体命令、代码、参数等执行细节
4. 不要使用具体的文件路径或文件名
5. 不要猜测用户环境和系统配置
6. 对于数据增删查改、批量文件处理、重复性操作等任务，必须在规划中使用Python脚本而非执行shell命令
7. 严格限制PowerShell和CMD命令的使用，仅用于非常简单的单一操作
8. 遇到以下情况时必须使用Python脚本而非命令行工具：
   - 处理超过5个文件
   - 数据量超过1MB
   - 需要执行复杂的数据分析或转换
   - 需要处理多种文件格式
   - 需要对文件内容进行复杂解析
   - 需要对数据执行批量操作
9. 在任务涉及多个文件操作时，必须考虑Python脚本的可靠性和安全性优势
10. 所有任务创建的文件和脚本都应放在workspace文件夹中，如果不存在应先创建

执行方式：
- 任务拆解应限制在3-5个高级步骤
- 每个步骤只描述"做什么"，不描述"怎么做"
- 不要提供具体工具选择的建议
- 不要假设任何环境配置
- 提供简短的目标描述，而非执行说明
- 对于文件操作、数据处理等任务，明确规划使用Python脚本，尤其是涉及到多个文件或需要重复执行的任务
- 规划时考虑使用workspace文件夹存放生成的文件，确保结构清晰

任务分析完成后，agent会自行确定具体执行步骤、选择适当工具，并执行必要操作。你的任务只是提供高层次指导，而非执行细节。
"""
}

async def execute_task_with_planning(user_input, messages_history):
    """
    使用任务规划执行用户请求
    """
    # 添加任务规划系统消息
    planning_messages = messages_history.copy()
    
    # 检测是否为简单任务（如git操作），可以直接执行而无需复杂验证
    simple_task_patterns = [
        (r'git\s+(add|commit|push|pull|clone|status|checkout|branch|merge|rebase|fetch)', 2),  # git操作，较少验证
        (r'(ls|dir)\s+', 1),  # 列出文件，最少验证
        (r'cd\s+', 1),  # 切换目录，最少验证
        (r'(cat|type)\s+', 1),  # 查看文件内容，最少验证
        (r'(mkdir|md)\s+', 1),  # 创建目录，最少验证
        (r'(rm|del|rmdir|rd)\s+', 3),  # 删除操作，较多验证
        (r'(cp|copy|mv|move)\s+', 2),  # 复制移动，较少验证
        (r'(ping|ipconfig|ifconfig)\s*', 1),  # 网络命令，最少验证
        (r'echo\s+', 1),  # 回显，最少验证
    ]
    
    # 确定任务复杂度级别
    task_complexity = 4  # 默认复杂度（需要完整验证）
    for pattern, complexity in simple_task_patterns:
        if re.search(pattern, user_input.lower()):
            task_complexity = complexity
            print_info(f"检测到简单任务类型，复杂度级别: {complexity}/4")
            break
    
    # 根据任务复杂度调整验证频率和深度
    max_recursive_verify = 15
    if task_complexity == 1:
        max_recursive_verify = 3  # 最简单任务最多3次验证
    elif task_complexity == 2:
        max_recursive_verify = 6  # 较简单任务最多6次验证
    elif task_complexity == 3:
        max_recursive_verify = 10  # 中等复杂任务最多10次验证
    
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
        
        # 执行任务（最多尝试7次）
        max_attempts = 7
        for attempt in range(max_attempts):
            try:
                # 添加执行提示
                execution_prompt = f"""现在开始执行任务计划的第{attempt+1}次尝试。
基于上述高层次目标，请自行确定具体执行步骤并调用适当的工具。
不要解释你将如何执行，直接调用工具执行必要操作。
每次只执行一个具体步骤，等待结果后再决定下一步。

对于数据增删查改、批量处理、文件操作等任务，必须编写和使用Python脚本而非直接执行shell命令，这样更安全和可靠。
特别是在以下情况下，必须使用Python脚本而不是PowerShell或CMD命令：
1. 处理多个文件（超过5个文件）
2. 数据量较大（超过1MB）
3. 需要进行复杂数据分析
4. 需要处理多种文件格式
5. 需要执行批量操作
6. 需要对文件内容进行解析

只有在执行非常简单的单一操作时才考虑使用PowerShell或CMD命令。
当需要处理多个文件、进行重复性操作或复杂数据处理时，必须创建Python脚本而非执行一系列命令。
所有任务创建的文件和脚本都应放在workspace文件夹中，如果该文件夹不存在，请首先创建它。"""

                if attempt > 0:
                    execution_prompt += f" 这是第{attempt+1}次尝试，前面{attempt}次尝试失败。请根据之前的错误调整策略。"
                
                planning_messages.append({"role": "user", "content": execution_prompt})
                
                # 初始化递归验证
                recursive_verify_count = 0
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
                                    # 执行原始命令，支持timeout参数
                                    timeout = args.get("timeout", 60)  # 从args中获取timeout参数，如果没有则使用默认值60秒
                                    result = await powershell_command(args["command"], timeout)
                                elif func_name == "cmd_command":
                                    # 执行CMD命令，支持timeout参数
                                    timeout = args.get("timeout", 60)  # 从args中获取timeout参数，如果没有则使用默认值60秒
                                    result = await cmd_command(args["command"], timeout)
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
                                elif func_name == "list_directory" or func_name == "list_dir":
                                    # 处理已废弃的工具
                                    error_message = f"工具 '{func_name}' 已被废弃，请使用 'powershell_command' 工具执行 'Get-ChildItem' 命令或 'cmd_command' 工具执行 'dir' 命令来列出目录内容。"
                                    print_warning(error_message)
                                    result = error_message
                                else:
                                    raise ValueError(f"未定义的工具调用: {func_name}")
                                
                                print_success(f"工具执行结果: {result}")
                                
                                # 通用任务成功信号检测
                                success_signals = [
                                    "成功", "已完成", "已创建", "已添加", "已发送", "完成", "正常",
                                    "success", "created", "added", "sent", "completed", "done"
                                ]
                                
                                # 通用错误信号检测
                                error_signals = [
                                    "错误", "失败", "异常", "exception", "error", "failed", 
                                    "failure", "invalid", "无法", "不能", "cannot", "unable to"
                                ]
                                
                                # 检查是否存在错误信号
                                has_error = any(signal.lower() in str(result).lower() for signal in error_signals)
                                
                                # 先添加工具执行结果到历史（必须在检查成功信号前添加）
                                current_execution_messages.append({
                                    "role": "tool",
                                    "tool_call_id": tool_call.id,
                                    "content": str(result)
                                })
                                
                                # 如果工具结果中包含成功信号且不包含错误信号，可能已成功完成任务
                                if any(signal.lower() in str(result).lower() for signal in success_signals) and not has_error:
                                    print_info("\n检测到工具执行成功，评估任务是否已完成")
                                    
                                    # 简单询问模型任务是否已完成（作为普通用户消息添加）
                                    completion_check_prompt = """
                                    根据刚刚执行的工具和结果，判断当前任务是否已经完成？
                                    如果完成，请简洁回答：[任务已完成] + 简短说明
                                    如果未完成，只需回答：[任务未完成] + 缺少的步骤
                                    不要有其他额外解释，保持回答简洁。
                                    """
                                    
                                    current_execution_messages.append({"role": "user", "content": completion_check_prompt})
                                    
                                    completion_check_response = client.chat.completions.create(
                                        model="deepseek-chat",
                                        messages=current_execution_messages,
                                        temperature=0.1,
                                        max_tokens=100
                                    )
                                    
                                    completion_check = completion_check_response.choices[0].message.content
                                    print_info(f"任务完成状态检查: {completion_check}")
                                    
                                    # 添加模型回复到消息历史
                                    current_execution_messages.append({"role": "assistant", "content": completion_check})
                                    
                                    # 如果模型确认任务已完成，生成总结并返回
                                    if "[任务已完成]" in completion_check:
                                        print_success("\n任务已确认完成")
                                        is_task_complete = True
                                        task_completed = True
                                        
                                        # 生成简单总结
                                        summary_start = completion_check.find("[任务已完成]") + len("[任务已完成]")
                                        summary = completion_check[summary_start:].strip()
                                        
                                        # 如果摘要为空或过短，请求一个更详细的摘要
                                        if len(summary) < 10:
                                            summary_prompt = "任务已完成。请简洁总结执行结果（不超过50字）"
                                            current_execution_messages.append({"role": "user", "content": summary_prompt})
                                            
                                            summary_response = client.chat.completions.create(
                                                model="deepseek-chat",
                                                messages=current_execution_messages,
                                                temperature=0.2,
                                                max_tokens=50
                                            )
                                            
                                            summary = summary_response.choices[0].message.content
                                            current_execution_messages.append({"role": "assistant", "content": summary})
                                        
                                        print_success(f"\n✅ {summary}")
                                        
                                        # 更新主对话消息
                                        messages_history.append({"role": "user", "content": user_input})
                                        messages_history.append({"role": "assistant", "content": summary})
                                        
                                        # 主动清理线程池
                                        cleanup_thread_pools()
                                    
                                        return summary
                                
                                # 分析执行结果是否有错误
                                error_info = task_error_analysis(result, {"tool": func_name, "args": args})
                                if error_info["has_error"]:
                                    print_warning(f"\n检测到错误: {error_info['analysis']}")
                                    step_success = False
                                    
                                    # 将错误信息添加到结果中
                                    result = f"{result}\n\n分析: {error_info['analysis']}"
                            
                            except Exception as e:
                                error_msg = f"工具执行失败: {str(e)}"
                                print_error(f"\n===== 工具执行错误 =====")
                                print_error(f"工具名称: {func_name}")
                                print_error(f"错误类型: {type(e)}")
                                print_error(f"错误信息: {str(e)}")
                                print_error("========================\n")
                                result = error_msg
                                step_success = False
                            
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
                        
                        # 增强的深度验证 - 检查潜在的虚假成功声明
                        task_step_verification = """
                        分析当前执行结果和历史工具调用，请验证：
                        1. 任务的每个必要步骤是否都已执行并成功完成
                        2. 最后一步操作的输出是否表明任务真正完成（而不是警告/错误信息）
                        3. 是否有必要的前置操作被遗漏（如保存文件、提交更改等）
                        4. 工具调用的输出结果是否表明操作已成功（不只是执行了命令）
                        5. 任务声明的进度是否与实际完成的步骤一致
                        6. 是否有"看起来完成但实际未完成"的情况（如无变更推送、空操作）

                        对于声明的每个已完成步骤，请找出对应的工具调用证据。
                        如果发现任何不一致或缺失步骤，请修正任务评估结果。
                        
                        具体回答：任务是否真正完成？如果未完成，还需要哪些步骤？
                        """
                        
                        # 当任务可能完成时进行更严格的验证
                        potential_completion = (
                            "[完成]" in verify_result or 
                            "100%" in verify_result or 
                            "任务完成" in verify_result or
                            "已完成" in verify_result
                        )
                        
                        # 收集可能表明成功的词语但常常暗示问题的输出模式
                        suspicious_patterns = [
                            ("Everything up-to-date", "git push"),
                            ("Already up-to-date", "git pull"),
                            ("没有需要提交的内容", "git commit"),
                            ("正常终止", "运行失败"),
                            ("Not connected", "连接"),
                            ("Permission denied", "权限"),
                            ("已经存在", "创建"),
                            ("未找到", "删除"),
                            ("cannot access", "访问"),
                            ("无法访问", "访问"),
                            ("error", "错误"),
                            ("Error:", "错误")
                        ]
                        
                        # 检查工具输出中是否有可疑结果
                        has_suspicious_output = False
                        recent_tool_outputs = []
                        
                        # 提取最近的工具调用输出
                        for i in range(len(current_execution_messages)-1, max(0, len(current_execution_messages)-20), -1):
                            if current_execution_messages[i].get("role") == "tool":
                                recent_tool_outputs.append(current_execution_messages[i].get("content", ""))
                        
                        # 在输出中查找可疑模式
                        for output in recent_tool_outputs:
                            for pattern, context in suspicious_patterns:
                                if pattern in str(output) and context in str(current_execution_messages[-20:]):
                                    has_suspicious_output = True
                                    break
                            if has_suspicious_output:
                                break
                                
                        # 如果声称任务完成或有可疑输出，进行二次验证
                        verification_performed = False
                        if potential_completion or has_suspicious_output:
                            verification_performed = True
                            current_execution_messages.append({"role": "user", "content": task_step_verification})
                            verification_response = client.chat.completions.create(
                                model="deepseek-chat",
                                messages=current_execution_messages,
                                temperature=0.1
                            )
                            
                            verification_result = verification_response.choices[0].message.content
                            print_info("\n===== 深度任务验证 =====")
                            print(verification_result)
                            print_info("=========================\n")
                            
                            # 添加验证结果到消息历史
                            current_execution_messages.append({"role": "assistant", "content": verification_result})
                            
                            # 根据深度验证结果判断任务是否真正完成
                            completion_indicators = ["任务已真正完成", "所有步骤已完成", "已确认完成", "已完成所有必要步骤"]
                            incomplete_indicators = ["未完成", "缺少步骤", "需要继续", "尚未完成", "未执行", "还需要"]
                            
                            is_verified_complete = any(indicator in verification_result for indicator in completion_indicators)
                            is_verified_incomplete = any(indicator in verification_result for indicator in incomplete_indicators)
                            
                            if is_verified_incomplete or (not is_verified_complete and has_suspicious_output):
                                # 添加纠正提示
                                correction_prompt = """
                                系统发现任务尚未真正完成。请继续执行必要步骤：
                                
                                1. 分析上一步的执行结果，确定是否达到了预期效果
                                2. 仔细检查工具输出中的警告/错误信息
                                3. 完成所有必要的前置和后置操作
                                4. 验证每一步的实际结果，而非仅执行命令
                                5. 如遇到意外结果，调整策略而非直接标记完成
                                
                                请继续执行任务，直到确认所有步骤真正达到了预期效果。
                                """
                                current_execution_messages.append({"role": "user", "content": correction_prompt})
                                print_warning("\n⚠️ 发现任务未真正完成，将继续执行...")
                                continue
                                
                        # 如果没有进行验证或验证通过，继续标准验证流程
                        
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
                            # 不要自动接受任务失败标记，而是增加一次确认步骤
                            confirm_prompt = """
                            系统检测到你标记了任务失败。在最终放弃前，请再次确认：

                            1. 是否尝试了所有可能的解决方案？
                            2. 是否有替代方法可以达到类似效果？
                            3. 能否部分完成任务而非完全放弃？

                            如果重新思考后确实无法完成，请明确回复"确认任务无法完成"
                            否则，请继续尝试执行任务，寻找新的解决方案。
                            """
                            current_execution_messages.append({"role": "user", "content": confirm_prompt})
                            
                            # 获取确认响应
                            confirm_response = client.chat.completions.create(
                                model="deepseek-chat",
                                messages=current_execution_messages,
                                temperature=0.1
                            )
                            
                            confirm_result = confirm_response.choices[0].message.content
                            current_execution_messages.append({"role": "assistant", "content": confirm_result})
                            
                            print_info("\n===== 失败确认 =====")
                            print(confirm_result)
                            print_info("======================\n")
                            
                            # 只有在明确确认失败的情况下才标记为失败
                            if "确认任务无法完成" in confirm_result:
                                # 询问用户是否继续尝试
                                should_continue = await ask_user_to_continue(current_execution_messages, is_task_complete)
                                # 检查should_continue的值，如果是None（输入超时）或者用户选择继续（不是终止命令）
                                if should_continue is None or (should_continue and should_continue.strip().lower() not in ["2", "终止", "停止", "结束", "放弃", "取消", "quit", "exit", "stop", "terminate", "cancel"]):
                                    # 用户选择继续或超时默认继续
                                    continue  # 用户选择继续尝试
                                else:
                                    # 用户明确选择终止
                                    is_task_complete = True  # 虽然失败但任务结束
                                    task_failed = True
                                    print_warning("\n⚠️ 任务确认失败! 准备生成失败分析...")
                                    break
                        elif "任务已完成" in verify_result or "任务完成" in verify_result:
                            is_task_complete = True
                            task_completed = True
                            print_success("\n✅ 任务已完成! 准备生成总结...")
                            break
                        elif ("任务失败" in verify_result and "明确" in verify_result) or ("完全无法" in verify_result and "解决方案" not in verify_result):
                            # 更严格的失败条件判断，必须明确表示完全无法继续
                            confirm_prompt = """
                            系统检测到你可能要放弃任务。在最终放弃前，请再次尝试思考：

                            1. 是否尝试了所有可能的解决方案？
                            2. 是否有替代方法可以达到类似效果？
                            3. 能否部分完成任务而非完全放弃？

                            如果重新思考后确实无法完成，请明确回复"确认任务无法完成"
                            否则，请继续尝试执行任务，寻找新的解决方案。
                            """
                            current_execution_messages.append({"role": "user", "content": confirm_prompt})
                            
                            # 获取确认响应
                            confirm_response = client.chat.completions.create(
                                model="deepseek-chat",
                                messages=current_execution_messages,
                                temperature=0.1
                            )
                            
                            confirm_result = confirm_response.choices[0].message.content
                            current_execution_messages.append({"role": "assistant", "content": confirm_result})
                            
                            print_info("\n===== 失败确认 =====")
                            print(confirm_result)
                            print_info("======================\n")
                            
                            # 只有在明确确认失败的情况下才标记为失败
                            if "确认任务无法完成" in confirm_result:
                                # 询问用户是否继续尝试
                                should_continue = await ask_user_to_continue(current_execution_messages, is_task_complete)
                                # 检查should_continue的值，如果是None（输入超时）或者用户选择继续（不是终止命令）
                                if should_continue is None or (should_continue and should_continue.strip().lower() not in ["2", "终止", "停止", "结束", "放弃", "取消", "quit", "exit", "stop", "terminate", "cancel"]):
                                    # 用户选择继续或超时默认继续
                                    continue  # 用户选择继续尝试
                                else:
                                    # 用户明确选择终止
                                    is_task_complete = True  # 虽然失败但任务结束
                                    task_failed = True
                                    print_warning("\n⚠️ 任务确认失败! 准备生成失败分析...")
                                    break
                        elif "部分完成" in verify_result and "100%" not in verify_result:
                            # 任务部分完成但达到了可接受的状态
                            if "可接受" in verify_result or "已满足需求" in verify_result or "基本满足" in verify_result:
                                is_task_complete = True
                                task_completed = True
                                print_success("\n✅ 任务部分完成但已达到可接受状态! 准备生成总结...")
                                break
                        
                        # 检查是否多次重复相同的步骤 - 通过进度判断是否卡住
                        progress_match = re.search(r'(\d+)%', verify_result)
                        if progress_match:
                            current_progress = int(progress_match.group(1))
                            
                            # 如果连续5次进度没有变化且已经执行了至少8次迭代，认为任务卡住了
                            if recursive_verify_count >= 8:
                                # 使用非类成员变量存储进度历史
                                if 'last_progress_values' not in locals():
                                    last_progress_values = []
                                
                                last_progress_values.append(current_progress)
                                if len(last_progress_values) > 5:
                                    last_progress_values.pop(0)
                                
                                # 检查最近5次进度是否完全相同
                                if len(last_progress_values) == 5 and len(set(last_progress_values)) == 1:
                                    # 在放弃前，给模型一次突破机会
                                    breakthrough_prompt = f"""
                                    系统检测到任务进度已连续5次保持在{current_progress}%，看起来你可能遇到了阻碍。

                                    请尝试以下策略来突破当前困境：
                                    1. 改变思路，尝试完全不同的解决方案
                                    2. 将复杂问题拆解为更小的步骤
                                    3. 使用R1_opt工具寻求深度分析
                                    4. 检查是否有其他工具可以帮助解决问题
                                    5. 降低目标，尝试部分完成任务

                                    请大胆创新，不要局限于之前的方法。这是你突破困境的最后机会。
                                    """
                                    current_execution_messages.append({"role": "user", "content": breakthrough_prompt})
                                    
                                    # 跳过自动判定卡住的逻辑，给模型一次突破的机会
                                    continue
                        
                        # 如果任务未完成，让模型根据当前进展动态规划下一步
                        if recursive_verify_count < max_recursive_verify:
                            plan_prompt = """
                            基于当前任务的进展情况，请执行下一步操作：
                            
                            1. 直接调用相应的工具执行下一步
                            2. 不要解释你将要做什么，直接执行
                            3. 根据实际情况灵活调整执行计划
                            4. 遇到问题主动寻找解决方案
                            5. 如果遇到困难，尝试更创新的方法或使用R1_opt寻求深度分析
                            
                            记住：
                            - 专注解决问题，而不是机械地按原计划执行
                            - 坚持不懈，尽量找到解决方案而非放弃
                            - 只有在确实尝试了所有可能方法后，才考虑放弃任务
                            """
                            current_execution_messages.append({"role": "user", "content": plan_prompt})
                
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
                    
                    # 主动清理线程池
                    cleanup_thread_pools()
                    
          
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
                    
            except Exception as e:
                print_error(f"\n===== 执行错误 =====")
                print_error(f"错误类型: {type(e)}")
                print_error(f"错误信息: {str(e)}")
                print_error("===================\n")
                
                # 如果是最后一次尝试，返回失败
                if attempt == max_attempts - 1:
                    error_message = f"执行任务时出现系统错误: {str(e)}"
                    
                    # 添加到主对话历史
                    messages_history.append({"role": "user", "content": user_input})
                    messages_history.append({"role": "assistant", "content": error_message})
                    
                    
                    return error_message
        
    except Exception as e:
        error_message = f"任务规划失败: {str(e)}"
        print_error(f"\n===== 规划错误 =====")
        print_error(error_message)
        print_error("===================\n")
        
        # 添加到主对话历史
        messages_history.append({"role": "user", "content": user_input})
        messages_history.append({"role": "assistant", "content": error_message})
        
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
        print_warning("Token数量超过预警阈值，让LLM决定消息清理策略...")
        # 使用LLM智能清理消息
        messages = await clean_message_history_with_llm(messages, client)
            
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
            
            # 启动精简版任务执行流程
            return await execute_simple_task(input_message, messages)
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
                
                # 启动精简版任务执行流程
                return await execute_simple_task(input_message, messages)
            
            # 普通对话回复
            messages.append({"role": "assistant", "content": assistant_message})
            
            return assistant_message

    except Exception as e:
        # 错误处理
        error_msg = f"API错误: {str(e)}"
        
        print_error(f"常规对话失败: {error_msg}")
        print_info("切换到任务规划系统...")
        
        # 移除刚才添加的消息
        messages.pop()
        
        # 使用简化版任务执行流程作为备选方案
        return await execute_simple_task(input_message, messages)

async def execute_simple_task(user_input, messages_history):
    """
    简化版任务执行流程，减少复杂性，每步都立即评估结果
    """
    # 初始化任务环境
    planning_messages = messages_history.copy()
    planning_messages.append({"role": "user", "content": user_input})
    
    print_info("\n===== 开始执行任务 =====")
    print_info(f"用户请求: {user_input}")
    print_info("=======================\n")
    
    # 检查token数量
    token_count = num_tokens_from_messages(planning_messages)
    if token_count > 30000:
        # 使用LLM智能清理消息
        planning_messages = await clean_message_history_with_llm(planning_messages, client)
    
    # 添加任务执行指导指南
    task_guidance = """
    现在你需要执行一个任务，请遵循以下流程：
    1. 分析需要执行的任务，确定必要的步骤
    2. 一次调用一个工具，完成一个子步骤
    3. 根据工具执行结果分析下一步操作
    4. 当任务完全完成时，明确说明[任务已完成]
    
    要点：
    - 必须使用工具来执行实际操作，而不是仅描述你要做什么
    - 每次只执行一个操作，等待结果后再确定下一步
    - 每次执行后要分析工具的执行结果，判断是否成功
    - 任务只有在所有必要步骤都通过工具调用执行成功后才算完成
    - 对于数据处理、文件操作和批量任务，必须使用Python脚本而非PowerShell或CMD命令
    - 在以下情况下，必须编写Python脚本而非使用命令行工具：
      * 处理多个文件（超过5个）
      * 处理大量数据（超过1MB）
      * 需要进行复杂数据分析
      * 需要处理多种文件格式
      * 需要执行批量操作
      * 需要对文件内容进行解析
    - 只有在执行非常简单的单一操作时才考虑使用PowerShell或CMD命令
    """
    
    planning_messages.append({"role": "user", "content": task_guidance})
    
    # 任务执行循环
    max_iterations = 20  # 最大迭代次数
    iteration = 1  # 将iteration从循环中提取出来以便重置
    while iteration <= max_iterations:
        print_info(f"\n===== 任务执行进度 {iteration}/{max_iterations} =====")
        
        # 如果token数量过大，使用LLM清理历史消息
        token_count = num_tokens_from_messages(planning_messages)
        if token_count > 30000:
            print_warning("Token数量超过预警阈值，让LLM决定消息清理策略...")
            planning_messages = await clean_message_history_with_llm(planning_messages, client)
        
        # 调用API，执行任务步骤
        try:
            response = client.chat.completions.create(
                model="deepseek-chat",
                messages=planning_messages,
                tools=tools,
                tool_choice="auto",
                temperature=0.3
            )
            
            message_data = response.choices[0].message
            
            # 如果模型选择调用工具
            if hasattr(message_data, 'tool_calls') and message_data.tool_calls:
                tool_calls = message_data.tool_calls
                
                # 添加助手消息和工具调用到历史
                planning_messages.append({
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
                
                # 执行每个工具调用
                for tool_call in tool_calls:
                    func_name = tool_call.function.name
                    args = json.loads(tool_call.function.arguments)
                    print_info(f"\n执行工具: {func_name}")
                    print_info(f"参数: {args}")
                    
                    try:
                        # 执行工具函数
                        if func_name == "get_current_time":
                            result = get_current_time(args.get("timezone", "UTC"))
                        elif func_name == "get_weather":
                            result = get_weather(args["city"])
                        elif func_name == "powershell_command":
                            # 执行原始命令，支持timeout参数
                            timeout = args.get("timeout", 60)  # 从args中获取timeout参数，如果没有则使用默认值60秒
                            result = await powershell_command(args["command"], timeout)
                        elif func_name == "cmd_command":
                            # 执行CMD命令，支持timeout参数
                            timeout = args.get("timeout", 60)  # 从args中获取timeout参数，如果没有则使用默认值60秒
                            result = await cmd_command(args["command"], timeout)
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
                                if isinstance(attachments_input, str) and "," in attachments_input:
                                    attachments = [path.strip() for path in attachments_input.split(",")]
                                else:
                                    attachments = attachments_input
                            
                            result = send_email.main(args["text"], args["receiver"], args["subject"], attachments)
                        elif func_name == "R1_opt":
                            result = R1(args["message"])
                        elif func_name == "ssh":
                            ip = "192.168.10.107"
                            username = "ye"
                            password = "147258"
                            result = ssh_controller.ssh_interactive_command(ip, username, password, args["command"])
                        elif func_name == "clear_context":
                            messages = clear_context(messages)  # 更新全局消息历史
                            planning_messages = clear_context(planning_messages)  # 更新当前执行消息
                            result = "上下文已清除"
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
                            prompt = args.get("prompt", "请提供更多信息：")
                            timeout = args.get("timeout", 60)
                            user_input_data = await get_user_input_async(prompt, timeout)
                            result = f"用户输入: {user_input_data}" if user_input_data else "用户未提供输入（超时）"
                        elif func_name == "read_file":
                            result = file_reader.read_file(args["file_path"], args["encoding"], args["extract_text_only"])
                        elif func_name == "list_directory" or func_name == "list_dir":
                            # 处理已废弃的工具
                            error_message = f"工具 '{func_name}' 已被废弃，请使用 'powershell_command' 工具执行 'Get-ChildItem' 命令或 'cmd_command' 工具执行 'dir' 命令来列出目录内容。"
                            print_warning(error_message)
                            result = error_message
                        else:
                            raise ValueError(f"未定义的工具调用: {func_name}")
                        
                        print_success(f"工具执行结果: {result}")
                        
                        # 添加工具执行结果到历史
                        planning_messages.append({
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "content": str(result)
                        })
                        
                    except Exception as e:
                        error_msg = f"工具执行失败: {str(e)}"
                        print_error(f"\n工具执行错误: {error_msg}")
                        
                        # 添加错误信息到历史
                        planning_messages.append({
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "content": error_msg
                        })
                    
                # 工具执行后，要求模型评估任务状态
                assessment_prompt = """
                请分析刚刚执行的工具结果，并回答以下问题：
                1. 工具执行是否成功？为什么？
                2. 当前任务完成了多少进度(0-100%)?
                3. 接下来需要执行什么操作？
                
                如果任务已经完全完成，请在回答开头明确写出：[任务已完成] + 简短结果摘要
                如果任务执行遇到了问题，但仍需要继续，请在回答开头写：[继续执行]
                如果任务无法完成，请在回答开头写：[任务失败] + 失败原因
                
                请记住：
                - 只有当所有必要步骤都成功执行后，任务才算完成
                - 任务进度评估应基于实际完成的工作，而非计划的工作
                - 接下来的步骤应该是具体的、可执行的操作
                """
                
                planning_messages.append({"role": "user", "content": assessment_prompt})
                
                # 获取任务评估结果
                assessment_response = client.chat.completions.create(
                    model="deepseek-chat",
                    messages=planning_messages,
                    temperature=0.1
                )
                
                assessment_result = assessment_response.choices[0].message.content
                planning_messages.append({"role": "assistant", "content": assessment_result})
                
                print_info("\n===== 任务状态评估 =====")
                print(assessment_result)
                print_info("=========================\n")
                
                # 检查任务是否已完成
                if "[任务已完成]" in assessment_result:
                    print_success("\n✅ 任务完成!")
                    
                    # 提取摘要
                    summary_start = assessment_result.find("[任务已完成]") + len("[任务已完成]")
                    summary = assessment_result[summary_start:].strip()
                    
                    # 如果摘要太短，生成更详细的摘要
                    if len(summary) < 10:
                        summary_prompt = "任务已完成。请简洁总结执行结果（不超过200字）。"
                        planning_messages.append({"role": "user", "content": summary_prompt})
                        
                        summary_response = client.chat.completions.create(
                            model="deepseek-chat",
                            messages=planning_messages,
                            temperature=0.2,
                            max_tokens=200
                        )
                        
                        summary = summary_response.choices[0].message.content
                    
                    print_success(f"任务结果: {summary}")
                    
                    # 更新主对话消息
                    messages_history.append({"role": "user", "content": user_input})
                    messages_history.append({"role": "assistant", "content": summary})
                    
                    # 主动清理线程池
                    cleanup_thread_pools()
                    
                    return summary
                
                elif "[任务失败]" in assessment_result:
                    # 询问用户是否继续尝试
                    try:
                        # 询问用户是否希望继续尝试
                        # 添加保护，防止用户输入被重复取消
                        try:
                            # 确保先取消任何已有的输入任务
                            cancel_active_input()
                            time.sleep(0.5)  # 短暂等待以确保任何先前的取消操作完成
                            
                            # 询问用户是否希望继续尝试
                            user_choice = await ask_user_to_continue(planning_messages, is_task_complete)
                            
                        except asyncio.CancelledError:
                            # 如果输入被取消，默认继续尝试
                            print_warning("用户输入被取消，默认继续尝试")
                            user_choice = "继续尝试"
                            
                            # 添加系统默认决策到对话
                            planning_messages.append({
                                "role": "user", 
                                "content": "用户输入被取消，系统默认继续尝试。请采用全新思路寻找解决方案。"
                            })
                            
                        except Exception as e:
                            # 如果获取用户输入失败，也默认继续
                            print_warning(f"获取用户输入异常: {str(e)}，默认继续尝试")
                            user_choice = "继续尝试"
                            
                            # 添加系统默认决策到对话
                            planning_messages.append({
                                "role": "user", 
                                "content": f"获取用户输入失败: {str(e)}，系统默认继续尝试。请采用全新思路寻找解决方案。"
                            })
                        
                        # 检查用户选择
                        if user_choice is None or (user_choice and user_choice.strip().lower() not in ["2", "终止", "停止", "结束", "放弃", "取消", "quit", "exit", "stop", "terminate", "cancel"]):
                            # 用户选择继续尝试、输入超时或提供了其他建议
                            if user_choice is None:
                                print_info("\n用户输入超时，系统默认继续尝试")
                                
                                # 添加系统默认决策到对话
                                planning_messages.append({
                                    "role": "user", 
                                    "content": "用户输入超时，系统默认继续尝试。请采用全新思路寻找解决方案。"
                                })
                                
                            elif user_choice == "继续尝试":
                                # 已通过异常处理添加了消息，不需要额外处理
                                pass
                                
                            else:
                                print_info(f"\n用户输入: {user_choice}")
                                
                                # 添加用户反馈到对话
                                planning_messages.append({
                                    "role": "user", 
                                    "content": f"用户希望继续尝试解决问题，并提供了以下反馈/建议：\n\"{user_choice}\"\n\n请考虑用户的输入，采用合适的方法继续解决问题。可以尝试新思路或按用户建议调整方案。直接开始执行，无需解释。"
                                })
                            
                            # 重置迭代计数，相当于给予全新的尝试机会
                            iteration = 1
                            print_info("\n⚠️ 用户选择继续尝试，迭代计数已重置！")
                            continue  # 继续执行任务
                        else:
                            # 用户确认终止
                            print_warning("\n用户选择终止任务。")
                            
                            # 提取失败原因
                            failure_start = assessment_result.find("[任务失败]") + len("[任务失败]")
                            failure_reason = assessment_result[failure_start:].strip()
                            
                            # 更新主对话消息
                            messages_history.append({"role": "user", "content": user_input})
                            messages_history.append({"role": "assistant", "content": f"任务执行失败: {failure_reason}"})
                            
                            # 主动清理线程池
                            cleanup_thread_pools()
                            

                            return f"任务执行失败: {failure_reason}"
                    except Exception as e:
                        # 获取用户输入失败时的处理
                        print_warning(f"获取用户输入失败: {str(e)}，默认继续尝试")
                        
                        # 添加到对话
                        planning_messages.append({
                            "role": "user", 
                            "content": "系统默认继续尝试。请采用全新思路寻找解决方案。"
                        })
                        
                        # 重置迭代计数，相当于给予全新的尝试机会
                        iteration = 1
                        print_info("\n⚠️ 默认继续尝试，迭代计数已重置！")
                        continue
                
                # 如果任务需要继续执行，添加执行提示
                execute_prompt = """
                请根据当前的任务进展，直接执行下一步操作：
                1. 不要解释你将要做什么，直接调用必要的工具
                2. 只执行一个具体步骤，等待结果后再确定下一步
                3. 专注于解决问题，而不是机械地按原计划执行
                
                记住：必须使用工具来执行实际操作，而不是仅描述你要做什么
                """
                
                planning_messages.append({"role": "user", "content": execute_prompt})
                
            else:
                # 如果模型没有调用工具，提醒它必须使用工具
                content = message_data.content
                planning_messages.append({"role": "assistant", "content": content})
                
                print_warning("\n⚠️ 助手没有调用任何工具")
                print(content)
                
                # 提示模型必须调用工具
                tool_reminder = """
                你需要通过调用工具来执行任务，而不是仅描述计划或说明将做什么。
                
                请直接调用相应的工具执行当前步骤。不要解释你将要做什么，直接执行工具调用。
                记住：只有通过工具调用成功执行的操作才算真正完成了任务。
                """
                
                planning_messages.append({"role": "user", "content": tool_reminder})
        
        except Exception as e:
            error_msg = f"迭代执行错误: {str(e)}"
            print_error(f"\n===== 执行错误 =====")
            print_error(error_msg)
            print_error("===================\n")
            
            # 添加错误信息到消息历史
            planning_messages.append({
                "role": "user", 
                "content": f"执行过程中发生错误: {error_msg}。请调整策略，尝试其他方法继续执行任务。"
            })
        
        # 增加迭代计数
        iteration += 1
    
    # 如果达到最大迭代次数仍未完成任务
    print_warning(f"\n⚠️ 已达到最大迭代次数({max_iterations})，但任务仍未完成")
    
    # 生成最终总结
    summary_prompt = "尽管执行了多次操作，但任务似乎未能完全完成。请总结当前状态和已完成的步骤。"
    planning_messages.append({"role": "user", "content": summary_prompt})
    
    summary_response = client.chat.completions.create(
        model="deepseek-chat",
        messages=planning_messages,
        temperature=0.2,
        max_tokens=100
    )
    
    summary = summary_response.choices[0].message.content
    
    # 更新主对话消息
    messages_history.append({"role": "user", "content": user_input})
    messages_history.append({"role": "assistant", "content": summary})
    
    return summary

def reset_messages():
    """重置消息历史到初始状态"""
    global messages
    messages = [{"role": "system","content": " 你叫小美，是一个热情的ai助手，这些是用户的一些关键信息，可能有用: "+user_information_read()}] 

# 添加一个线程池清理辅助函数
def cleanup_thread_pools():
    """清理不再使用的线程池，防止程序卡住"""
    # 使用更安全的方式关闭线程池
    if hasattr(concurrent.futures, '_thread_executors'):
        for executor in list(concurrent.futures._thread_executors):
            if hasattr(executor, '_shutdown') and executor._shutdown:
                try:
                    concurrent.futures._thread_executors.remove(executor)
                except:
                    pass
    # 如果我们自己维护了线程池列表，也可以清理它们
    if hasattr(get_user_input_async, 'executors'):
        for executor in list(get_user_input_async.executors):
            try:
                if not executor._shutdown:
                    executor.shutdown(wait=False)
                get_user_input_async.executors.remove(executor)
            except:
                pass

if __name__ == "__main__":
    # 使用从user_information_read函数获取用户信息
    # 该函数会自动确保文件存在，不需要在这里手动创建
    user_info = user_information_read()
    
    print("程序启动成功")
    
    # 注册程序退出时的清理函数
    def cleanup_resources():
        """清理程序资源，确保线程池正确关闭"""
        print("\n正在清理资源...")
        
        # 安全关闭线程池
        # 避免直接访问内部属性
        try:
            # 尝试关闭任何可能存在的线程池
            cleanup_thread_pools()
            
            # 清理TimerThread实例
            from input_utils import TimerThread
            if hasattr(TimerThread, 'cleanup_timer_threads'):
                TimerThread.cleanup_timer_threads()
            
            # 确保任何导入的模块中的线程池也被关闭
            for module_name in list(sys.modules.keys()):
                module = sys.modules[module_name]
                if hasattr(module, 'executor') and hasattr(module.executor, 'shutdown'):
                    try:
                        module.executor.shutdown(wait=False)
                    except:
                        pass
        except Exception as e:
            print(f"关闭线程池时出错: {str(e)}")
        
        print("资源清理完成")
    
    import atexit
    atexit.register(cleanup_resources)
    
    try:
        while True:
            try:
                input_message = input("\n输入消息: ")
                
                if input_message:
                    result = asyncio.run(main(input_message))
                    # 只有当返回值明确为False时才退出循环
                    if result is False:
                        break
                    
                    # 主动清理线程池
                    cleanup_thread_pools()
                    
            except KeyboardInterrupt:
                print("\n程序已被用户中断")
                break
            except Exception as e:
                print("\n===== 主程序错误 =====")
                print(f"错误类型: {type(e)}")
                print(f"错误信息: {str(e)}")
                print("=====================\n")
                
    finally:
        # 确保在程序结束时清理资源
        cleanup_resources()