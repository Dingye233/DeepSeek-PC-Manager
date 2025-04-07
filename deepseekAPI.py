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
from input_utils import get_user_input_async, cancel_active_input, cleanup_thread_pools  # 更新导入，添加cleanup_thread_pools
from file_utils import user_information_read
from error_utils import parse_error_message, task_error_analysis
from message_utils import num_tokens_from_messages, clean_message_history, clear_context, clean_message_history_with_llm
from console_utils import print_color, print_success, print_error, print_warning, print_info, print_highlight
from system_utils import powershell_command, cmd_command
import concurrent.futures
import sys  # 添加sys模块导入
import time  # 添加time模块导入
import threading
import msvcrt

load_dotenv()

# 使用集中的工具注册
tools = tool_registry.get_tools()

client = OpenAI(api_key=os.environ.get("api_key"), base_url="https://api.deepseek.com")


messages = [{"role": "system","content": " 你叫小美，是一个热情的ai助手，这些是用户的一些关键信息，可能有用: "+user_information_read()}, 
{"role": "system","content": " 注意：1.文件操作必须使用绝对路径 2.危险操作要自动添加安全参数 3.对于涉及数据增删查改、批量处理、文件处理等复杂任务，必须优先使用Python脚本而非Shell命令，这样更安全高效且易于维护 4.创建脚本时确保使用合适的异常处理和备份机制 5.对于重复性操作或影响多个文件的操作，必须编写Python脚本而非手动执行命令 6.所有任务中创建的文件和脚本都应放在workspace文件夹下，如果该文件夹不存在则应先创建它 7.当处理数据量大或文件数量多时，绝对不要使用PowerShell或CMD命令，而应编写Python脚本 8.只有在执行简单的单一操作（如检查文件是否存在）时才考虑使用PowerShell或CMD"}]

# 将ask_user_to_continue函数从嵌套函数移到全局作用域
# 使用input_utils中实现的函数，而不是自己实现
from input_utils import ask_user_to_continue

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

async def execute_unified_task(user_input, messages_history):
    """
    统一的任务执行流程，结合了复杂任务规划和简单任务执行的优点
    """
    # 检查用户输入是否为简单对话
    simple_chat_patterns = [
        r'^(好的?|是的?|嗯+|对的?|没错|可以的?|当然|行|OK|好嘞|好啊|嗯哼|那?就?好|没问题)$',
        r'^(不用了?|不需要|不用谢|谢谢|感谢|多谢|不客气)$',
        r'^(再见|拜拜|回头见|下次见|晚安|早安|午安)$',
        r'^(你好|早上好|下午好|晚上好|Hello|Hi|Hey|哈喽)$'
    ]
    
    for pattern in simple_chat_patterns:
        if re.match(pattern, user_input.strip(), re.IGNORECASE):
            print_info("检测到简单对话，不启动任务系统")
            simple_response = "好的，有什么我能帮你的请随时告诉我。"
            if "谢谢" in user_input or "感谢" in user_input:
                simple_response = "不客气，很高兴能帮到你！"
            elif "再见" in user_input or "拜拜" in user_input:
                simple_response = "再见！有需要随时找我。"
            elif "你好" in user_input or "早上好" in user_input or "下午好" in user_input or "晚上好" in user_input:
                simple_response = f"{user_input}！有什么我可以帮你的吗？"
                
            # 直接添加到消息历史而不启动任务系统
            messages_history.append({"role": "user", "content": user_input})
            messages_history.append({"role": "assistant", "content": simple_response})
            return simple_response
    
    # 初始化任务环境
    planning_messages = messages_history.copy()
    planning_messages.append({"role": "user", "content": user_input})
    
    print_info("\n===== 开始执行任务 =====")
    print_info(f"用户请求: {user_input}")
    print_info("=======================\n")
    
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
        max_recursive_verify = 2  # 最简单任务最多2次验证
    elif task_complexity == 2:
        max_recursive_verify = 4  # 较简单任务最多4次验证
    elif task_complexity == 3:
        max_recursive_verify = 8  # 中等复杂任务最多8次验证
    
    # 检查token数量并优化清理流程
    token_count = num_tokens_from_messages(planning_messages)
    if token_count > 28000:  # 提前清理，避免接近限制
        # 使用简单的消息清理而不是LLM清理，减少额外LLM调用
        if token_count > 35000:
            planning_messages = clean_message_history(planning_messages, 25000)
        else:
            # 仅在token数量中等时使用LLM清理
            planning_messages = await clean_message_history_with_llm(planning_messages, client, 25000)
    
    # 使用更简化的任务执行指导
    task_guidance = """
    请执行这个任务，遵循以下流程：1.分析任务需求 2.使用工具执行操作 3.分析结果决定下一步 4.完成时说明[任务已完成]
    注意：所有操作必须通过工具执行，每次一个操作，等待结果后再继续。处理多个文件、复杂分析或批量任务时，使用Python脚本而非命令行工具。
    """
    
    if task_complexity <= 2:
        # 对于简单任务使用更精简的指导
        planning_messages.append({"role": "user", "content": task_guidance})
    else:
        # 对于复杂任务使用详细指导
        planning_messages.append({"role": "user", "content": task_guidance + """
        对于数据处理、文件操作和批量任务，必须使用Python脚本而非PowerShell或CMD命令。
        在以下情况下必须编写Python脚本：处理多个文件（超过5个）、处理大量数据（超过1MB）、
        需要进行复杂数据分析、需要处理多种文件格式、需要执行批量操作、需要对文件内容进行解析。
        只有在执行非常简单的单一操作时才考虑使用PowerShell或CMD命令。
        """})
    
    # 任务执行循环
    max_iterations = max(max_recursive_verify, 20)  # 取两者较大值作为最大迭代次数
    iteration = 1
    is_task_complete = False
    task_failed = False
    
    while iteration <= max_iterations and not is_task_complete:
        print_info(f"\n===== 任务执行迭代 {iteration}/{max_iterations} =====")
        
        # 如果token数量过大，清理历史消息
        token_count = num_tokens_from_messages(planning_messages)
        if token_count > 28000:  # 提前清理，避免接近限制
            print_warning("Token数量超过预警阈值，清理消息历史...")
            planning_messages = clean_message_history(planning_messages, 25000)  # 使用简单清理而不是LLM清理
        
        # 调用API，执行任务步骤
        try:
            # 根据任务复杂度调整温度
            temperature = 0.2 if task_complexity <= 2 else 0.3
            
            response = client.chat.completions.create(
                model="deepseek-chat",
                messages=planning_messages,
                tools=tools,
                tool_choice="auto",
                temperature=temperature
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
                    print_info(f"\n正在执行工具: {func_name}")
                    print_info(f"参数: {args}")
                    
                    try:
                        # 针对不同工具优化执行
                        if func_name == "get_current_time":
                            result = get_current_time(args.get("timezone", "UTC"))
                        elif func_name == "get_weather":
                            result = get_weather(args["city"])
                        elif func_name == "powershell_command":
                            # 根据复杂度调整超时时间
                            timeout = args.get("timeout", 30 if task_complexity <= 2 else 60)
                            result = await powershell_command(args["command"], timeout)
                        elif func_name == "cmd_command":
                            # 根据复杂度调整超时时间
                            timeout = args.get("timeout", 30 if task_complexity <= 2 else 60)
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
                            print_warning(f"已使用R1深度思考工具，当前迭代: {iteration}/{max_iterations}")
                        elif func_name == "ssh":
                            ip = "192.168.10.107"
                            username = "ye"
                            password = "147258"
                            result = ssh_controller.ssh_interactive_command(ip, username, password, args["command"])
                        elif func_name == "clear_context":
                            messages = clear_context(messages)  # 更新全局消息历史
                            planning_messages = clear_context(planning_messages)  # 更新当前执行消息
                            result = "上下文已清除"
                            is_task_complete = True  # 标记任务完成
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
                        
                        # 针对简单任务优化：如果是复杂度为1的简单任务且工具执行结果中有成功信号
                        if task_complexity == 1 and ("成功" in str(result) or "完成" in str(result)) and not ("错误" in str(result) or "失败" in str(result)):
                            if iteration >= 2:  # 至少执行两次迭代
                                print_info("\n检测到简单任务已执行成功，将在评估后决定是否完成")
                        
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
                        # 修复：确保异步执行正确
                        print_info("\n正在等待用户决策...")
                        user_choice = await ask_user_to_continue(planning_messages)
                        
                        # 检查用户选择
                        if user_choice is None or user_choice == "":
                            # 超时或空输入情况，默认继续执行
                            print_info("\n用户未提供明确输入，系统默认继续尝试")
                            
                            # 添加系统默认决策到对话
                            planning_messages.append({
                                "role": "user", 
                                "content": "用户未提供明确输入，系统默认继续尝试。请采用全新思路寻找解决方案。"
                            })
                            
                            # 重置迭代计数
                            iteration = max(1, iteration - 3)  # 减少一些迭代次数，给予更多尝试机会
                            print_info(f"\n重置迭代计数至 {iteration}")
                            
                            # 主动清理线程池，防止卡住
                            cleanup_thread_pools()
                        elif user_choice.lower() in ["2", "终止", "停止", "结束", "放弃", "取消", "quit", "exit", "stop", "terminate", "cancel"]:
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
                        else:
                            # 用户提供了其他建议
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
                    except Exception as e:
                        # 获取用户输入异常时的处理
                        print_warning(f"获取用户输入异常: {str(e)}，默认继续尝试")
                        
                        # 添加系统默认决策到对话
                        planning_messages.append({
                            "role": "user", 
                            "content": f"获取用户输入失败: {str(e)}，系统默认继续尝试。请采用全新思路寻找解决方案。"
                        })
                        
                        # 主动清理线程池以防止资源泄露
                        cleanup_thread_pools()
                
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
                
                # 检查内容是否表明任务已完成
                if "任务已完成" in content or "已成功完成" in content:
                    print_success("\n✅ 助手表示任务已完成")
                    is_task_complete = True
                    
                    # 添加到主对话消息
                    messages_history.append({"role": "user", "content": user_input})
                    messages_history.append({"role": "assistant", "content": content})
                    
                    return content
                
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
    if not is_task_complete:
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
    
    return "任务已完成"

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
        
        # 如果模型决定调用工具，则启动统一任务处理
        if hasattr(message_data, 'tool_calls') and message_data.tool_calls:
            # 回退消息历史，移除刚刚添加的用户消息，因为任务规划会重新添加
            messages.pop()
            print_info("检测到工具调用，启动任务执行系统...")
            
            # 启动统一任务处理
            return await execute_unified_task(input_message, messages)
        else:
            # 即使模型没有选择调用工具，也分析回复内容是否暗示需要执行任务
            assistant_message = message_data.content
            print(assistant_message)
            
            # 分析回复内容，检查是否为任务请求
            is_task_request = False
            
            # 只有当回复较长且包含明确任务指示时才识别为任务
            if len(assistant_message) > 100:  # 确保回复足够长
                task_indicators = [
                    "我需要执行", "我可以帮你执行", "让我为你执行", "我会为你处理", 
                    "需要通过以下步骤执行", "可以按照以下步骤执行",
                    "这需要使用工具", "可以通过脚本", "需要编写代码", 
                    "我可以使用命令", "详细步骤如下", "具体操作步骤",
                    "我需要使用工具", "我将使用以下工具", "这是一个需要工具的任务"
                ]
                
                # 计算匹配的指示器数量
                match_count = 0
                for indicator in task_indicators:
                    if indicator in assistant_message:
                        match_count += 1
                
                # 只有当匹配到足够多的指示器时才认为是任务请求
                if match_count >= 1:
                    is_task_request = True
            
            # 如果内容暗示需要执行任务，切换到任务处理模式
            if is_task_request:
                # 删除刚才添加的消息，因为任务处理会重新添加
                messages.pop()
                print_info("内容分析显示这可能是一个任务请求，启动任务执行系统...")
                
                # 启动统一任务处理
                return await execute_unified_task(input_message, messages)
            
            # 普通对话回复
            messages.append({"role": "assistant", "content": assistant_message})
            
            return assistant_message

    except Exception as e:
        # 错误处理
        error_msg = f"API错误: {str(e)}"
        
        print_error(f"常规对话失败: {error_msg}")
        
        # 检查输入消息长度，短消息优先以对话方式处理
        if len(input_message) < 15:  # 短消息(如"那就好"、"好的"等)
            simple_response = "我理解了。有什么我可以帮到你的吗？"
            messages.append({"role": "assistant", "content": simple_response})
            print_info("检测到简短输入，使用对话模式回复")
            return simple_response
            
        # 对于较长消息才切换到任务执行系统
        print_info("切换到任务执行系统...")
        
        # 移除刚才添加的消息
        messages.pop()
        
        # 使用统一任务处理作为备选方案
        return await execute_unified_task(input_message, messages)

def reset_messages():
    """重置消息历史到初始状态"""
    global messages
    messages = [{"role": "system","content": " 你叫小美，是一个热情的ai助手，这些是用户的一些关键信息，可能有用: "+user_information_read()}] 

# 更新清理线程池的函数，使用input_utils中的函数
def cleanup_thread_pools():
    """简单清理不再使用的线程池，防止程序卡住"""
    from input_utils import cleanup_thread_pools as cleanup_input_pools
    
    # 调用input_utils中的清理函数
    cleanup_input_pools()
    
    # 此外尝试清理concurrent.futures中的线程池
    try:
        if hasattr(concurrent.futures, '_thread_executors'):
            for executor in list(concurrent.futures._thread_executors):
                if hasattr(executor, '_shutdown') and executor._shutdown:
                    try:
                        concurrent.futures._thread_executors.remove(executor)
                    except:
                        pass
    except:
        pass  # 忽略任何错误

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