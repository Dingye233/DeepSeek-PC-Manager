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
1. 接收到任务后，首先分析任务需求并制定执行计划
2. 将复杂任务分解为可执行的子任务步骤
3. 执行每个步骤并观察结果
4. 如果执行过程中遇到错误或异常，分析错误原因并重新规划解决方案
5. 持续尝试不同方法直到任务成功完成或确定无法完成
6. 任务完成后总结执行过程和结果

执行方式：
- 对于复杂任务，独立思考并自主规划解决方案
- 根据用户输入或环境反馈调整计划
- 使用工具执行具体操作（如执行命令、创建文件等）
- 遇到错误时分析错误信息并自动修正
- 使用循环方式验证任务是否完成，直到成功或确认失败

关键能力：
- 任务分解与规划能力
- 错误检测与自动修复
- 持续尝试与备选方案
- 结果验证与确认

工具选择指南：
1. 代码操作优先级：
   - 写入代码文件：优先使用 write_code 工具，而不是 powershell_command
   - 追加代码内容：优先使用 append_code 工具，而不是 powershell_command
   - 读取代码文件：优先使用 read_code 工具，而不是 powershell_command
   - 验证Python代码：使用 verify_code 工具检查语法
   - 创建模块：使用 create_module 工具创建多函数模块
   - 仅当专用代码工具无法满足需求时才使用 powershell_command 操作代码

2. 文件操作优先级：
   - 读取通用文件：优先使用 read_file 工具
   - 列出目录文件：优先使用 list_files 或 list_directory 工具
   - 仅在需要执行系统命令时使用 powershell_command

用户交互指南：
- 当你需要用户提供更多信息时，使用user_input工具请求输入
- 适合使用user_input的场景：
  1. 需要用户确认某个重要决定（如删除文件、修改配置）
  2. 需要用户提供任务中缺失的信息（如文件名、目标路径等）
  3. 有多个可能的解决方案，需要用户选择
  4. 任务执行过程中出现意外情况，需要用户提供指导
- 使用清晰具体的提示语，告诉用户需要提供什么信息
- 设置合理的超时时间，避免长时间等待
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
    planning_messages.append({"role": "user", "content": f"请完成以下任务，并详细规划执行步骤：{user_input}"})
    
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
        print("\n===== 任务规划 =====")
        print(task_plan)
        print("====================\n")
        
        # 添加任务规划到对话历史
        planning_messages.append({"role": "assistant", "content": task_plan})
        
        # 执行任务（最多尝试5次）
        max_attempts = 5
        for attempt in range(max_attempts):
            try:
                # 添加执行提示
                execution_prompt = f"现在开始执行任务计划的第{attempt+1}次尝试。请调用适当的工具执行计划中的步骤。"
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
                    # 在执行新迭代前先验证任务是否已完成
                    if recursive_verify_count > 0:  # 跳过第一次迭代的验证
                        print_info("\n===== 任务验证：检查当前任务是否在之前验证中被标记为完成 =====")
                        # 验证提示
                        pre_verify_prompt = """
                        现在作为严格的执行验证系统，请分析当前任务的状态和用户请求的完成情况。
                        
                        必须区分以下三点：
                        1. 用户的原始请求要求
                        2. 已经实际执行的步骤（必须有明确的工具调用记录作为证据）
                        3. 计划要执行但尚未执行的步骤
                        
                        请分析对话历史中的实际工具调用情况，检查真正的执行证据，而非仅计划或意图。
                        
                        请严格按照以下JSON格式回复：
                        {
                            "is_complete": true/false,  // 任务是否已完成（完成的定义：所有必要步骤均有工具调用证据）
                            "confidence": 0.0-1.0,  // 对完成状态判断的置信度
                            "progress_percentage": 0-100,  // 任务完成的百分比
                            "execution_evidence": [
                                {"tool": "工具名称", "purpose": "使用目的", "result_summary": "结果概述", "success": true/false}
                            ],  // 列出关键工具调用证据
                            "steps_completed": ["已完成的步骤1", "已完成的步骤2"],  // 有明确证据表明已完成的步骤
                            "steps_remaining": ["未完成的步骤1", "未完成的步骤2"],  // 尚未完成的步骤
                            "is_stuck": true/false,  // 任务是否卡住无法继续
                            "stuck_reason": "若任务卡住，说明原因",
                            "hallucination_risk": "低/中/高",  // 评估将计划误认为执行的风险
                            "hallucination_warning": "如发现幻觉倾向，请在此详细说明"
                        }
                        
                        严格提醒：
                        1. 仅有操作计划不等于执行成功，必须有工具调用证据
                        2. 检测到幻觉风险（将计划误认为已执行）时，必须将hallucination_risk标为"高"
                        3. 完成判断必须基于客观证据，而非主观判断
                        4. 高置信度判断要求必须有充分的工具调用证据支持
                        """
                        
                        token_count = num_tokens_from_messages(current_execution_messages)
                        if token_count > 30000:
                            print_warning("Token数量超过阈值，清理消息历史...")
                            current_execution_messages = clean_message_history(current_execution_messages)
                            token_count = num_tokens_from_messages(current_execution_messages)
                            print_info(f"清理后token数量: {token_count}")
                        
                        # 添加验证提示
                        current_execution_messages.append({"role": "user", "content": pre_verify_prompt})
                        
                        verification_complete = False
                        verification_attempts = 0
                        max_verification_attempts = 10
                        prev_progress = 0
                        
                        while not verification_complete and verification_attempts < max_verification_attempts:
                            verification_attempts += 1
                            print_info(f"执行任务验证，第{verification_attempts}次尝试")
                            
                            token_count = num_tokens_from_messages(current_execution_messages)
                            print_info(f"验证前token数量: {token_count}")
                            if token_count > 30000:
                                print_warning("Token数量超过阈值，清理消息历史...")
                                current_execution_messages = clean_message_history(current_execution_messages)
                            
                            verify_response = client.chat.completions.create(
                                model="deepseek-chat",
                                messages=current_execution_messages,
                                temperature=0.1
                            )
                            
                            verify_result = verify_response.choices[0].message.content
                            print_info("\n===== 任务验证结果 =====")
                            print(verify_result)
                            print_info("=========================\n")
                            
                            # 添加验证结果到消息历史
                            current_execution_messages.append({"role": "assistant", "content": verify_result})
                            
                            # 解析验证结果
                            try:
                                # 尝试提取JSON部分
                                json_match = re.search(r'({.*})', verify_result, re.DOTALL)
                                if json_match:
                                    verify_json = json.loads(json_match.group(1))
                                else:
                                    # 尝试直接解析全文
                                    verify_json = json.loads(verify_result)
                                
                                # 检查工具调用证据情况
                                execution_evidence = verify_json.get("execution_evidence", [])
                                evidence_count = len(execution_evidence)
                                successful_evidence = sum(1 for ev in execution_evidence if ev.get("success", False))
                                
                                if evidence_count > 0:
                                    print_info(f"\n任务执行证据：检测到 {evidence_count} 个关键工具调用，其中 {successful_evidence} 个成功执行")
                                
                                # 检查幻觉风险
                                hallucination_risk = verify_json.get("hallucination_risk", "未知")
                                if hallucination_risk == "高":
                                    print_warning(f"\n⚠️ 高幻觉风险警告: {verify_json.get('hallucination_warning', '未提供详细信息')}")
                                    # 高幻觉风险时，强制认为任务未完成
                                    verify_json["is_complete"] = False
                                    verify_json["confidence"] = min(verify_json.get("confidence", 0.5), 0.3)  # 降低置信度
                                
                                # 更新进度信息
                                current_progress = verify_json.get("progress_percentage", 0)
                                if current_progress > prev_progress:
                                    print_success(f"任务进度上升: {prev_progress}% -> {current_progress}%")
                                elif current_progress < prev_progress:
                                    print_warning(f"任务进度下降: {prev_progress}% -> {current_progress}%")
                                else:
                                    print_info(f"任务进度保持不变: {current_progress}%")
                                prev_progress = current_progress
                                
                                # 判断任务是否完成（增加严格条件）
                                is_complete = verify_json.get("is_complete", False)
                                confidence = verify_json.get("confidence", 0.0)
                                
                                # 严格条件：必须有足够工具调用证据、低幻觉风险、高置信度
                                reliable_completion = (
                                    is_complete and 
                                    evidence_count >= 1 and  # 至少有1个工具调用证据
                                    successful_evidence > 0 and  # 至少有1个成功执行的工具调用
                                    hallucination_risk != "高" and  # 非高幻觉风险
                                    confidence >= 0.7  # 置信度至少0.7
                                )
                                
                                if reliable_completion:
                                    print_success("\n✅ 验证通过：任务已完成!")
                                    verification_complete = True
                                    current_execution_messages.append({
                                        "role": "user", 
                                        "content": "验证确认任务已完成。请总结任务执行结果，包括所有工具调用及其结果。"
                                    })
                                    break
                                
                                if verify_json.get("is_stuck", False):
                                    stuck_reason = verify_json.get("stuck_reason", "未提供具体原因")
                                    print_error(f"\n❌ 任务卡住: {stuck_reason}")
                                    verification_complete = True
                                    failure_reason = f"任务卡住: {stuck_reason}"
                                    break
                                    
                            except Exception as e:
                                print_error(f"解析验证结果时出错: {e}")
                                # 继续尝试下一次验证
                            
                            if verification_attempts >= max_verification_attempts:
                                print_warning(f"达到最大验证尝试次数 ({max_verification_attempts})，停止验证")
                                verification_complete = True
                                failure_reason = "验证尝试次数过多"
                    
                    recursive_verify_count += 1
                    # 显示迭代次数和任务进度
                    progress_bar = "=" * int(task_progress/5) + ">" + " " * (20 - int(task_progress/5))
                    print(f"\n===== 任务执行迭代 {recursive_verify_count}/{max_recursive_verify} | 进度: {task_progress}% [{progress_bar}] =====")
                    
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
                                    # 检查是否存在更合适的专用工具
                                    command = args["command"].lower()
                                    better_tool = None
                                    warning_msg = ""
                                    
                                    # 检测是否在进行代码操作，应该使用专用代码工具
                                    if (("echo" in command or "set-content" in command or "add-content" in command or "out-file" in command) and 
                                        any(ext in command for ext in [".py", ".js", ".html", ".css", ".json", ".txt", ".md"])):
                                        if "append" in command or "add-content" in command:
                                            better_tool = "append_code"
                                        else:
                                            better_tool = "write_code"
                                    elif "get-content" in command and any(ext in command for ext in [".py", ".js", ".html", ".css", ".json", ".txt", ".md"]):
                                        better_tool = "read_code"
                                    elif "dir" in command or "get-childitem" in command or "ls" in command:
                                        better_tool = "list_directory 或 list_files"
                                    
                                    if better_tool:
                                        print_warning(f"\n⚠️ 检测到不理想的工具选择: 使用powershell_command执行代码/文件操作")
                                        print_warning(f"💡 建议使用专用工具: {better_tool}")
                                        # 添加提示到结果中
                                        warning_msg = f"\n[工具选择提示] 此操作更适合使用 {better_tool} 工具，请在下次迭代中考虑使用专用工具。"
                                        
                                    # 执行原始命令
                                    cmd_result = await powershell_command(args["command"])
                                    
                                    # 如果有更好的工具选择，添加提示到结果中
                                    if better_tool:
                                        result = cmd_result + warning_msg
                                    else:
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
                        现在作为严格的执行验证系统，请分析当前任务的执行情况和完成状态。
                        
                        必须严格区分以下两点：
                        1. 描述的计划或意图（不等同于执行）
                        2. 有证据的已执行操作（必须有工具调用记录）
                        
                        请严格基于以下事实进行评估：
                        1. 当前对话历史中记录的实际工具调用
                        2. 这些工具调用返回的具体结果
                        3. 与用户原始需求的匹配程度
                        
                        必须检查每个必要步骤是否都有对应的工具调用证据。没有工具调用证据的步骤不能视为已完成。
                        
                        请严格按照以下格式回复:
                        {
                            "is_complete": true/false,  // 任务是否已完成（必须基于工具调用证据判断）
                            "completion_status": "简短描述当前执行状态和结果",
                            "execution_evidence": [
                                {"tool": "工具名称", "purpose": "使用目的", "result_summary": "结果概述", "success": true/false}
                            ],  // 列出关键工具调用证据
                            "next_steps": ["下一步1", "下一步2"],  // 若任务未完成，下一步需要执行的操作列表
                            "is_failed": true/false,  // 任务是否已失败且无法继续
                            "failure_reason": "若已失败，失败的原因",
                            "gap_analysis": "描述计划与实际执行之间的差距，特别是尚未执行的关键步骤",
                            "hallucination_check": "检查是否存在将计划误认为已执行的幻觉情况"
                        }
                        
                        严格提醒：
                        1. 仅有操作计划不等于执行完成，必须有工具调用证据
                        2. 如检测到幻觉（将计划误认为执行），必须在hallucination_check中标明
                        3. 完成判断必须基于客观证据，而非主观判断或期望
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
                        print_info("\n===== 任务验证结果 =====")
                        print(verify_result)
                        print_info("=========================\n")
                        
                        # 添加验证结果到消息历史
                        current_execution_messages.append({"role": "assistant", "content": verify_result})
                        
                        # 解析验证结果
                        try:
                            # 尝试提取JSON部分
                            json_match = re.search(r'({.*})', verify_result, re.DOTALL)
                            if json_match:
                                verify_json = json.loads(json_match.group(1))
                            else:
                                # 如果没有明确的JSON，尝试更灵活的解析
                                verify_json = {
                                    "is_complete": "true" in verify_result.lower() and "完成" in verify_result,
                                    "is_failed": "失败" in verify_result or "无法继续" in verify_result,
                                    "completion_status": verify_result[:100] + "..."  # 简短摘要
                                }
                            
                            # 检查执行证据（如果存在）
                            execution_evidence = verify_json.get("execution_evidence", [])
                            evidence_count = len(execution_evidence)
                            successful_evidence = sum(1 for ev in execution_evidence if ev.get("success", False))
                            
                            if evidence_count > 0:
                                print_info(f"\n任务执行证据：检测到 {evidence_count} 个关键工具调用，其中 {successful_evidence} 个成功执行")
                            
                            # 检查幻觉情况
                            hallucination_check = verify_json.get("hallucination_check", "")
                            if hallucination_check and "幻觉" in hallucination_check:
                                print_warning(f"\n⚠️ 幻觉检测: {hallucination_check}")
                                # 出现幻觉时，强制认为任务未完成
                                verify_json["is_complete"] = False
                            
                            # 检查执行差距
                            gap_analysis = verify_json.get("gap_analysis", "")
                            if gap_analysis:
                                print_info(f"\n执行差距分析: {gap_analysis}")
                            
                            # 考虑证据进行完成状态判断
                            has_reliable_evidence = evidence_count > 0 and successful_evidence > 0
                            if verify_json.get("is_complete", False) and not has_reliable_evidence:
                                print_warning("\n⚠️ 验证错误：声称任务完成但缺乏充分执行证据")
                                # 修正判断
                                verify_json["is_complete"] = False
                                verify_json["completion_status"] = "任务未完成：缺乏充分执行证据"
                            
                            # 检查任务是否完成或失败
                            if verify_json.get("is_complete", False) is True:
                                is_task_complete = True
                                print_success("\n✅ 任务已完成! 准备生成总结...")
                                break
                            
                            if verify_json.get("is_failed", False) is True:
                                print_error(f"\n❌ 任务无法继续: {verify_json.get('failure_reason', '未知原因')}")
                                break
                            
                            # 如果任务未完成也未失败，继续下一步
                            next_steps = verify_json.get("next_steps", ["请继续执行任务的下一步骤"])
                            if isinstance(next_steps, list):
                                next_step_text = "\n".join([f"- {step}" for step in next_steps])
                            else:
                                next_step_text = str(next_steps)
                            
                            print_info("\n===== 下一步计划 =====")
                            print_highlight(next_step_text)
                            print_info("======================\n")
                            
                            current_execution_messages.append({
                                "role": "user", 
                                "content": f"任务尚未完成。现在请执行下一步: {next_step_text}"
                            })
                            
                            # 发送验证进度到GUI
                            if 'message_queue' in globals():
                                message_queue.put({
                                    "type": "tool_result",
                                    "text": f"任务进度: {verify_json.get('completion_status', '进行中')}，准备下一步"
                                })
                            
                        except (json.JSONDecodeError, ValueError) as e:
                            print_error(f"验证结果解析失败: {str(e)}")
                            # 如果解析失败，简单继续
                            current_execution_messages.append({
                                "role": "user", 
                                "content": "请继续执行任务的下一步骤。"
                            })
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
                        
                        # 如果模型未调用工具但也未完成，提示继续
                        if recursive_verify_count < max_recursive_verify:
                            current_execution_messages.append({
                                "role": "user", 
                                "content": "请继续执行任务，如果需要，请调用相应的工具。"
                            })
                
                # 内部递归结束后，更新外部消息历史
                planning_messages = current_execution_messages.copy()
                
                # 检查任务是否在递归内完成
                if is_task_complete:
                    # 任务成功，获取简洁总结回复
                    planning_messages.append({
                        "role": "user", 
                        "content": "任务执行完成，请简洁总结执行结果（不超过100字）。使用简短句子，避免复杂解释。"
                    })
                    
                    # 最后的总结回复
                    final_response = client.chat.completions.create(
                        model="deepseek-chat",
                        messages=planning_messages,
                        temperature=0.2,
                        max_tokens=150  # 限制token数量
                    )
                    
                    summary = final_response.choices[0].message.content
                    print_info("\n===== 任务执行总结 =====")
                    print_highlight(summary)
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
            print("检测到工具调用，启动任务规划系统...")
            return await execute_task_with_planning(input_message, messages)
        else:
            # 如果不需要调用工具，直接处理普通回复
            assistant_message = message_data.content
            print(assistant_message)
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
        
        # 使用任务规划作为备选方案
        messages.pop()  # 移除刚才添加的消息
        print("常规对话失败，切换到任务规划系统...")
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