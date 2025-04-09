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
# 导入代码搜索工具函数
from code_search_tools import search_code, locate_code_section, get_code_context
# 导入增强版工具, 但只用于内部实现，不注册为独立工具
from code_edit_enhanced import edit_code_section, edit_function, edit_code_by_pattern, insert_code
from code_validator_enhanced import validate_python_code, verify_imports, execute_code_safely, check_complexity
# 导入Web搜索工具
from web_search_tool import web_search, fetch_webpage, filter_search_results
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
    统一任务执行函数 - 处理复杂和简单任务
    """
    global client, task_summary
    
    # 初始化任务摘要
    task_summary = {
        "start_time": time.strftime("%Y-%m-%d %H:%M:%S"),
        "user_input": user_input,
        "current_tools": [],
        "status_updates": [],
        "complete": False
    }
    
    # 添加用户输入到消息历史
    planning_messages = messages_history.copy()
    planning_messages.append({"role": "user", "content": user_input})
    
    # 发送token计数信号
    token_count = num_tokens_from_messages(planning_messages)
    if hasattr(messages_history, 'token_signal'):
        messages_history.token_signal.emit(token_count)
    
    # 更新任务摘要
    def update_task_summary(tool_name=None, status=None, progress=None):
        """更新任务摘要并返回格式化文本"""
        if tool_name:
            task_summary["current_tools"].append(tool_name)
        if status:
            task_summary["status_updates"].append(status)
        if progress:
            task_summary["progress"] = progress
            
        summary_text = f"""==== 任务摘要 ====
任务: {task_summary['user_input']}
开始时间: {task_summary['start_time']}
进度: {task_summary.get('progress', 0)}%

已执行工具:
{chr(10).join(f'- {tool}' for tool in task_summary['current_tools'])}

状态更新:
{chr(10).join(f'- {status}' for status in task_summary['status_updates'])}
=======================
"""
        # 发送任务摘要信号
        if hasattr(messages_history, 'summary_signal'):
            messages_history.summary_signal.emit(summary_text)
        
        return summary_text
    
    # 检查token数量并优化清理流程
    token_count = num_tokens_from_messages(planning_messages)
    # 更新token计数信号
    if hasattr(messages_history, 'token_signal'):
        messages_history.token_signal.emit(token_count)
        
    if token_count > 28000:  # 提前清理，避免接近限制
        # 使用简单的消息清理而不是LLM清理，减少额外LLM调用
        if token_count > 35000:
            planning_messages = clean_message_history(planning_messages, 25000)
        else:
            # 仅在token数量中等时使用LLM清理
            planning_messages = await clean_message_history_with_llm(planning_messages, client, 25000)
        
        # 清理后更新token计数
        token_count = num_tokens_from_messages(planning_messages)
        if hasattr(messages_history, 'token_signal'):
            messages_history.token_signal.emit(token_count)
    
    # 使用更简化的任务执行指导
    task_guidance = """
    请执行这个任务，遵循以下流程：1.分析任务需求 2.使用工具执行操作 3.分析结果决定下一步 4.完成时说明[任务已完成]
    注意：所有操作必须通过工具执行，每次一个操作，等待结果后再继续。处理多个文件、复杂分析或批量任务时，使用Python脚本而非命令行工具。
    """
    
    planning_messages.append({"role": "user", "content": task_guidance + """
    对于数据处理、文件操作和批量任务，必须使用Python脚本而非PowerShell或CMD命令。
    在以下情况下必须编写Python脚本：处理多个文件（超过5个）、处理大量数据（超过1MB）、
    需要进行复杂数据分析、需要处理多种文件格式、需要执行批量操作、需要对文件内容进行解析。
    只有在执行非常简单的单一操作时才考虑使用PowerShell或CMD命令。
    """})
    
    # 任务执行循环
    max_iterations = 20  # 固定最大迭代次数
    iteration = 1
    is_task_complete = False
    task_failed = False
    
    while iteration <= max_iterations and not is_task_complete:
        print_info(f"\n===== 任务执行迭代 {iteration}/{max_iterations} =====")
        
        # 如果token数量过大，清理历史消息
        token_count = num_tokens_from_messages(planning_messages)
        # 更新token计数信号
        if hasattr(messages_history, 'token_signal'):
            messages_history.token_signal.emit(token_count)
        
        if token_count > 28000:  # 提前清理，避免接近限制
            print_warning("Token数量超过预警阈值，清理消息历史...")
            planning_messages = clean_message_history(planning_messages, 25000)  # 使用简单清理而不是LLM清理
            
            # 清理后更新token计数
            token_count = num_tokens_from_messages(planning_messages)
            if hasattr(messages_history, 'token_signal'):
                messages_history.token_signal.emit(token_count)
        
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
                
                # 将模型的思考和工具调用请求添加到规划消息中
                planning_messages.append(message_data)
                
                # 处理每个工具调用
                for tool_call in tool_calls:
                    tool_name = tool_call.function.name
                    tool_arguments = json.loads(tool_call.function.arguments)
                    
                    try:
                        # 更新任务摘要
                        update_task_summary(tool_name=tool_name)
                        
                        if tool_name == "clear_context":
                            tool_result = clear_context()
                            planning_messages = [messages_history[0]]  # 保留系统消息
                            planning_messages.append({"role": "user", "content": user_input})
                            
                        elif tool_name == "user_input":
                            prompt = tool_arguments.get("prompt", "请提供更多信息")
                            timeout = tool_arguments.get("timeout", 60)
                            tool_result = await get_user_input_async(prompt, timeout)
                            
                        elif tool_name == "get_current_time":
                            timezone = tool_arguments.get("timezone", "local")
                            tool_result = get_current_time(timezone)
                        
                        elif tool_name == "get_weather":
                            city = tool_arguments.get("city", "")
                            tool_result = get_weather(city)
                            
                        elif tool_name == "powershell_command":
                            command = tool_arguments.get("command", "")
                            timeout = tool_arguments.get("timeout", 60)
                            tool_result = powershell_command(command, timeout)
                            
                        elif tool_name == "cmd_command":
                            command = tool_arguments.get("command", "")
                            timeout = tool_arguments.get("timeout", 60)
                            tool_result = cmd_command(command, timeout)
                            
                        elif tool_name == "get_emails":
                            limit = tool_arguments.get("limit", 10)
                            folder = tool_arguments.get("folder", "INBOX")
                            tool_result = get_email.get_emails(limit, folder)
                            
                        elif tool_name == "get_email_detail":
                            email_id = tool_arguments.get("email_id", "")
                            tool_result = get_email.get_email_detail(email_id)
                            
                        elif tool_name == "send_mail":
                            receiver = tool_arguments.get("receiver", "")
                            subject = tool_arguments.get("subject", "")
                            text = tool_arguments.get("text", "")
                            attachments = tool_arguments.get("attachments", "")
                            tool_result = send_email.send_mail(receiver, subject, text, attachments)
                            
                        elif tool_name == "R1_opt":
                            message = tool_arguments.get("message", "")
                            tool_result = R1(message)
                            
                        elif tool_name == "ssh":
                            command = tool_arguments.get("command", "")
                            tool_result = ssh_controller.execute(command)
                            
                        elif tool_name == "write_code":
                            file_name = tool_arguments.get("file_name", "")
                            code = tool_arguments.get("code", "")
                            with_analysis = tool_arguments.get("with_analysis", False)
                            create_backup = tool_arguments.get("create_backup", True)
                            tool_result = code_tools.write_code(file_name, code, with_analysis, create_backup)
                            
                        elif tool_name == "verify_code":
                            code = tool_arguments.get("code", "")
                            verbose = tool_arguments.get("verbose", False)
                            check_best_practices = tool_arguments.get("check_best_practices", False)
                            tool_result = code_tools.verify_code(code, verbose, check_best_practices)
                            
                        elif tool_name == "append_code":
                            file_name = tool_arguments.get("file_name", "")
                            content = tool_arguments.get("content", "")
                            verify_after = tool_arguments.get("verify_after", False)
                            create_backup = tool_arguments.get("create_backup", True)
                            tool_result = code_tools.append_code(file_name, content, verify_after, create_backup)
                            
                        elif tool_name == "read_code":
                            file_name = tool_arguments.get("file_name", "")
                            with_analysis = tool_arguments.get("with_analysis", True)
                            complexity_check = tool_arguments.get("complexity_check", False)
                            tool_result = code_tools.read_code(file_name, with_analysis, complexity_check)
                            
                        elif tool_name == "read_file":
                            file_path = tool_arguments.get("file_path", "")
                            max_size = tool_arguments.get("max_size", 1024*1024*10)  # 默认10MB
                            encoding = tool_arguments.get("encoding", "utf-8")
                            tool_result = json.dumps(file_reader.read_file(file_path, max_size, encoding))
                            
                        elif tool_name == "create_module":
                            module_name = tool_arguments.get("module_name", "")
                            functions_json = tool_arguments.get("functions_json", "[]")
                            verify_imports = tool_arguments.get("verify_imports", False)
                            create_tests = tool_arguments.get("create_tests", False)
                            tool_result = code_tools.create_module(module_name, functions_json, verify_imports, create_tests)
                            
                        # 代码搜索工具
                        elif tool_name == "search_code":
                            file_path = tool_arguments.get("file_path", "")
                            query = tool_arguments.get("query", "")
                            search_type = tool_arguments.get("search_type", "semantic")
                            tool_result = search_code(file_path, query, search_type)
                            
                        elif tool_name == "locate_code_section":
                            file_path = tool_arguments.get("file_path", "")
                            start_line = tool_arguments.get("start_line", 1)
                            end_line = tool_arguments.get("end_line", 10)
                            tool_result = locate_code_section(file_path, start_line, end_line)
                            
                        elif tool_name == "get_code_context":
                            file_path = tool_arguments.get("file_path", "")
                            line_number = tool_arguments.get("line_number", 1)
                            context_lines = tool_arguments.get("context_lines", 5)
                            tool_result = get_code_context(file_path, line_number, context_lines)
                        
                        # Web搜索工具
                        elif tool_name == "web_search":
                            query = tool_arguments.get("query", "")
                            num_results = tool_arguments.get("num_results", 5)
                            filter_adult = tool_arguments.get("filter_adult", True)
                            keywords = tool_arguments.get("keywords", None)
                            sort_by_relevance = tool_arguments.get("sort_by_relevance", True)
                            match_all_keywords = tool_arguments.get("match_all_keywords", False)
                            tool_result = json.dumps(web_search(query, num_results, filter_adult, keywords, sort_by_relevance, match_all_keywords), ensure_ascii=False)
                            
                        elif tool_name == "fetch_webpage":
                            url = tool_arguments.get("url", "")
                            extract_keywords = tool_arguments.get("extract_keywords", None)
                            tool_result = json.dumps(fetch_webpage(url, extract_keywords), ensure_ascii=False)
                            
                        elif tool_name == "filter_search_results":
                            results = tool_arguments.get("results", [])
                            keywords = tool_arguments.get("keywords", [])
                            match_all = tool_arguments.get("match_all", False)
                            tool_result = json.dumps(filter_search_results(results, keywords, match_all), ensure_ascii=False)
                        
                        # 移除重复的增强工具调用处理代码，这些功能已经集成到原始工具中
                        # 原始工具的内部实现现在使用增强版功能
                        
                        else:
                            tool_result = f"未知工具: {tool_name}"
                            
                        # 检查任务结果中是否包含完成标记
                        if isinstance(tool_result, str) and "[任务已完成]" in tool_result:
                            is_task_complete = True
                        
                        print_success(f"工具执行结果: {tool_result}")
                        
                        # 更新任务摘要
                        summary_text = update_task_summary(
                            status=f"工具 {tool_name} 执行成功: {str(tool_result)[:100]}...",
                            progress=min(100, int((iteration / max_iterations) * 100))
                        )
                        print_info(summary_text)
                        
                        # 发送工具输出信号
                        if hasattr(messages_history, 'tool_output_signal'):
                            messages_history.tool_output_signal.emit(str(tool_result))
                        
                        # 添加工具执行结果到历史
                        planning_messages.append({
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "content": str(tool_result)
                        })
                        
                    except Exception as e:
                        error_msg = f"工具执行错误: {str(e)}"
                        print_error(error_msg)
                        
                        # 记录详细错误信息
                        error_analysis = task_error_analysis(e)
                        
                        # 更新任务摘要
                        summary_text = update_task_summary(
                            status=f"工具 {tool_name} 执行失败: {error_msg}",
                            progress=min(100, int((iteration / max_iterations) * 100))
                        )
                        
                        # 添加错误信息到历史
                        planning_messages.append({
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "content": f"工具执行失败: {error_msg}\n\n详细错误: {error_analysis}"
                        })
                        
                        # 如果是关键错误，标记任务失败
                        if "FileNotFoundError" in str(e) or "PermissionError" in str(e):
                            task_failed = True
                        
                    # 清理线程池以防止资源泄露
                    cleanup_thread_pools()
                
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
                
                # 更新任务摘要
                summary_text = update_task_summary(
                    status=f"任务状态评估: {assessment_result}",
                    progress=min(100, int((iteration / max_iterations) * 100))
                )
                print_info(summary_text)
                
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
                    
                    # 更新任务摘要
                    summary_text = update_task_summary(
                        status=f"任务完成: {summary}",
                        progress=100
                    )
                    print_success(summary_text)
                    
                    # 更新主对话消息
                    messages_history.append({"role": "user", "content": user_input})
                    messages_history.append({"role": "assistant", "content": summary})
                    
                    # 主动清理线程池
                    cleanup_thread_pools()
                    
                    return summary
                
                elif "[任务失败]" in assessment_result:
                    # 询问用户是否继续尝试
                    try:
                        print_info("\n正在等待用户决策...")
                        error_failed_tools = []
                        for tool_info in tool_calls:
                            execution_successful = getattr(tool_info, "execution_successful", True)
                            if not execution_successful:
                                error_failed_tools.append(getattr(tool_info, "name", "未知工具"))
                        
                        # 更新任务摘要
                        error_message = f"工具执行失败: {', '.join(error_failed_tools)}"
                        update_task_summary(status=f"任务执行出现错误，无法继续: {', '.join(error_failed_tools)}")
                        
                        # 向用户询问是否继续尝试，即使有错误
                        user_choice = await ask_user_to_continue(planning_messages, is_direct_tool_call=False, error_message=error_message)
                        if user_choice == "终止":
                            task_failed = True
                            break
                    except Exception as e:
                        print_warning(f"获取用户输入异常: {str(e)}，默认继续尝试")
                        
                        planning_messages.append({
                            "role": "user", 
                            "content": f"获取用户输入失败: {str(e)}，系统默认继续尝试。请采用全新思路寻找解决方案。"
                        })
                        
                        cleanup_thread_pools()
            
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
            
            # 更新任务摘要
            summary_text = update_task_summary(
                status=f"执行错误: {error_msg}",
                progress=min(100, int((iteration / max_iterations) * 100))
            )
            print_error(summary_text)
            
            planning_messages.append({
                "role": "user", 
                "content": f"执行过程中发生错误: {error_msg}。请调整策略，尝试其他方法继续执行任务。"
            })
        
        iteration += 1
    
    # 如果达到最大迭代次数仍未完成任务
    if not is_task_complete:
        print_warning(f"\n⚠️ 已达到最大迭代次数({max_iterations})，但任务仍未完成")
        
        summary_prompt = "尽管执行了多次操作，但任务似乎未能完全完成。请总结当前状态和已完成的步骤。"
        planning_messages.append({"role": "user", "content": summary_prompt})
        
        summary_response = client.chat.completions.create(
            model="deepseek-chat",
            messages=planning_messages,
            temperature=0.2,
            max_tokens=100
        )
        
        summary = summary_response.choices[0].message.content
        
        # 更新任务摘要
        summary_text = update_task_summary(
            status=f"任务未完成: {summary}",
            progress=100
        )
        print_warning(summary_text)
        
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