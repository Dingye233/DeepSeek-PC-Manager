"""
API 包装器 - 安全调用 deepseekAPI 的功能
"""
import asyncio
import sys
import traceback
from typing import Any, Dict, List, Optional, Union

# 尝试导入 deepseekAPI 模块
try:
    import deepseekAPI
    from deepseekAPI import messages, client, tools
except ImportError as e:
    print(f"无法导入 deepseekAPI: {e}")
    sys.exit(1)

class APIBridge:
    """安全调用 deepseekAPI 功能的桥接类"""
    
    # 存储最新的工具执行结果
    _latest_tool_output = ""
    
    # 回调函数
    _tool_output_callback = None
    _task_plan_callback = None
    
    @staticmethod
    def set_tool_output_callback(callback):
        """设置工具输出回调函数"""
        APIBridge._tool_output_callback = callback
        
    @staticmethod
    def set_task_plan_callback(callback):
        """设置任务计划回调函数"""
        APIBridge._task_plan_callback = callback
    
    @staticmethod
    async def execute_task(user_input: str) -> str:
        """执行一个任务，返回结果"""
        try:
            # 重置最新工具输出
            APIBridge._latest_tool_output = ""
            
            # 捕获标准输出
            from io import StringIO
            original_stdout = sys.stdout
            captured_output = StringIO()
            sys.stdout = captured_output
            
            try:
                # 添加用户输入到消息历史
                messages.append({"role": "user", "content": user_input})
                
                # 安装监听器来捕获工具执行结果
                APIBridge._install_tool_output_listener()
                
                # 创建一个任务来监控和更新stdout内容
                async def monitor_stdout():
                    last_size = 0
                    while True:
                        current_size = captured_output.tell()
                        if current_size > last_size:
                            # 有新的输出
                            captured_output.seek(last_size)
                            new_content = captured_output.read()
                            captured_output.seek(current_size)
                            last_size = current_size
                            
                            # 检查新内容中是否包含工具执行结果
                            if "工具执行结果:" in new_content or "tool result:" in new_content:
                                # 更新最新工具输出
                                APIBridge._latest_tool_output = new_content
                                # 调用回调函数
                                if APIBridge._tool_output_callback:
                                    APIBridge._tool_output_callback(new_content)
                            
                            # 检查是否包含任务计划更新
                            if ("任务计划:" in new_content or 
                                "执行计划:" in new_content or 
                                "task plan:" in new_content or 
                                "任务摘要" in new_content):
                                # 调用回调函数
                                if APIBridge._task_plan_callback:
                                    APIBridge._task_plan_callback(new_content)
                        
                        # 等待一段时间再检查
                        await asyncio.sleep(0.1)
                
                # 启动监控任务
                monitor_task = asyncio.create_task(monitor_stdout())
                
                # 调用 deepseekAPI 的 main 函数，使用正确的参数名称 input_message
                result = await deepseekAPI.main(input_message=user_input)
                
                # 停止监控任务
                monitor_task.cancel()
                try:
                    await monitor_task
                except asyncio.CancelledError:
                    pass
                
                # 处理捕获的完整输出，确保没有遗漏的工具结果
                output = captured_output.getvalue()
                # 检查是否包含工具执行结果
                tool_outputs = []
                for line in output.splitlines():
                    if "工具执行结果:" in line or "tool result:" in line:
                        # 提取工具执行结果
                        result_start_idx = output.find(line)
                        if result_start_idx != -1:
                            result_text = output[result_start_idx:].split("\n\n")[0] + "\n\n"
                            tool_outputs.append(result_text)
                
                # 确保最后一次工具输出被捕获到
                if tool_outputs and APIBridge._tool_output_callback:
                    APIBridge._tool_output_callback(tool_outputs[-1])
                
                # 从消息历史提取助手的回复
                assistant_response = None
                for msg in reversed(list(messages)):  # 创建副本以避免迭代时修改
                    if msg.get("role") == "assistant":
                        assistant_response = msg.get("content", "")
                        break
                
                if assistant_response:
                    return assistant_response
                
                # 如果在消息历史中找不到回复，则返回 main() 的结果
                if isinstance(result, dict) and "content" in result:
                    return result["content"]
                return str(result)
            finally:
                # 恢复标准输出
                sys.stdout = original_stdout
                
                # 卸载监听器
                APIBridge._uninstall_tool_output_listener()
                
        except Exception as e:
            error_details = traceback.format_exc()
            print(f"执行任务时出错:\n{error_details}", file=sys.stderr)
            return f"⚠️ 执行任务时出错: {str(e)}"
    
    @staticmethod
    def _install_tool_output_listener():
        """安装工具结果监听器"""
        try:
            # 捕获 deepseekAPI 中的工具执行结果
            if hasattr(deepseekAPI, 'tools'):
                original_tools = []
                for i, tool in enumerate(deepseekAPI.tools):
                    if "function" in tool and "name" in tool["function"]:
                        tool_name = tool["function"]["name"]
                        
                        # 保存原始 function
                        if not hasattr(deepseekAPI, '_original_tools'):
                            deepseekAPI._original_tools = {}
                        
                        if tool_name not in deepseekAPI._original_tools and "python_tools" in sys.modules:
                            python_tools = sys.modules.get("python_tools")
                            if hasattr(python_tools, tool_name):
                                original_func = getattr(python_tools, tool_name)
                                deepseekAPI._original_tools[tool_name] = original_func
                                
                                # 创建包装函数来捕获结果
                                def create_wrapper(orig_func, tool_name):
                                    async def wrapper(*args, **kwargs):
                                        try:
                                            result = await orig_func(*args, **kwargs)
                                            # 更新最新工具输出并调用回调
                                            output_text = f"工具执行结果: {tool_name}\n\n{result}"
                                            APIBridge._latest_tool_output = output_text
                                            if APIBridge._tool_output_callback:
                                                APIBridge._tool_output_callback(output_text)
                                            return result
                                        except Exception as e:
                                            # 捕获工具执行错误并格式化为工具结果
                                            error_text = f"工具执行结果: {tool_name} (错误)\n\n执行出错: {str(e)}"
                                            APIBridge._latest_tool_output = error_text
                                            if APIBridge._tool_output_callback:
                                                APIBridge._tool_output_callback(error_text)
                                            # 重新抛出异常，让上层处理
                                            raise
                                    return wrapper
                                
                                # 安装包装函数
                                if hasattr(python_tools, tool_name):
                                    setattr(python_tools, tool_name, create_wrapper(original_func, tool_name))
            
            # 尝试捕获代码搜索工具的结果
            try:
                if "code_search_tools" in sys.modules:
                    code_search_tools = sys.modules.get("code_search_tools")
                    search_tool_names = ["search_code", "locate_code_section", "get_code_context"]
                    
                    if not hasattr(deepseekAPI, '_original_search_tools'):
                        deepseekAPI._original_search_tools = {}
                    
                    for tool_name in search_tool_names:
                        if hasattr(code_search_tools, tool_name):
                            # 保存原始函数
                            if tool_name not in deepseekAPI._original_search_tools:
                                original_func = getattr(code_search_tools, tool_name)
                                deepseekAPI._original_search_tools[tool_name] = original_func
                                
                                # 创建包装函数
                                def create_search_wrapper(orig_func, tool_name):
                                    def wrapper(*args, **kwargs):
                                        try:
                                            result = orig_func(*args, **kwargs)
                                            # 更新最新工具输出并调用回调
                                            output_text = f"工具执行结果: {tool_name}\n\n{result}"
                                            APIBridge._latest_tool_output = output_text
                                            if APIBridge._tool_output_callback:
                                                APIBridge._tool_output_callback(output_text)
                                            return result
                                        except Exception as e:
                                            # 捕获工具执行错误并格式化为工具结果
                                            error_text = f"工具执行结果: {tool_name} (错误)\n\n执行出错: {str(e)}"
                                            APIBridge._latest_tool_output = error_text
                                            if APIBridge._tool_output_callback:
                                                APIBridge._tool_output_callback(error_text)
                                            # 重新抛出异常，让上层处理
                                            raise
                                    return wrapper
                                
                                # 安装包装函数
                                setattr(code_search_tools, tool_name, create_search_wrapper(original_func, tool_name))
            except Exception as e:
                print(f"安装代码搜索工具监听器时出错: {e}", file=sys.stderr)
        except Exception as e:
            print(f"安装工具监听器时出错: {e}", file=sys.stderr)
    
    @staticmethod
    def _uninstall_tool_output_listener():
        """卸载工具结果监听器"""
        try:
            # 恢复原始工具函数
            if hasattr(deepseekAPI, '_original_tools'):
                for tool_name, original_func in deepseekAPI._original_tools.items():
                    if "python_tools" in sys.modules:
                        python_tools = sys.modules.get("python_tools")
                        if hasattr(python_tools, tool_name):
                            setattr(python_tools, tool_name, original_func)
                
                # 清除保存的原始函数
                delattr(deepseekAPI, '_original_tools')
            
            # 恢复代码搜索工具函数
            if hasattr(deepseekAPI, '_original_search_tools'):
                if "code_search_tools" in sys.modules:
                    code_search_tools = sys.modules.get("code_search_tools")
                    for tool_name, original_func in deepseekAPI._original_search_tools.items():
                        if hasattr(code_search_tools, tool_name):
                            setattr(code_search_tools, tool_name, original_func)
                
                # 清除保存的原始函数
                delattr(deepseekAPI, '_original_search_tools')
        except Exception as e:
            print(f"卸载工具监听器时出错: {e}", file=sys.stderr)
    
    @staticmethod
    def get_latest_tool_output() -> str:
        """获取最新的工具执行结果"""
        return APIBridge._latest_tool_output

    @staticmethod
    def get_task_plan() -> str:
        """获取当前任务的计划和摘要"""
        try:
            # 尝试从 deepseekAPI 的任务摘要中获取信息
            if hasattr(deepseekAPI, 'task_summary'):
                summary = deepseekAPI.task_summary
                
                # 格式化任务摘要
                formatted_summary = "==== 任务摘要 ====\n"
                
                # 添加基本信息
                if 'user_input' in summary:
                    formatted_summary += f"任务: {summary['user_input']}\n"
                if 'start_time' in summary:
                    formatted_summary += f"开始时间: {summary['start_time']}\n"
                if 'progress' in summary:
                    formatted_summary += f"进度: {summary.get('progress', 0)}%\n"
                
                # 添加已执行工具
                if 'current_tools' in summary and summary['current_tools']:
                    formatted_summary += "\n已执行工具:\n"
                    for tool in summary['current_tools']:
                        formatted_summary += f"- {tool}\n"
                
                # 添加状态更新
                if 'status_updates' in summary and summary['status_updates']:
                    formatted_summary += "\n状态更新:\n"
                    for status in summary['status_updates']:
                        formatted_summary += f"- {status}\n"
                
                formatted_summary += "=======================\n"
                return formatted_summary
            
            # 如果找不到 task_summary，从最近的消息中提取可能的计划信息
            for msg in reversed(list(messages)):
                content = msg.get("content", "")
                if "任务状态评估" in content or "任务已完成" in content or "任务摘要" in content:
                    return content
            
            return "暂无任务计划信息"
        except Exception as e:
            print(f"获取任务计划时出错: {e}", file=sys.stderr)
            return "获取任务计划时出错"

    @staticmethod
    def get_token_count() -> int:
        """获取当前消息历史的token数量"""
        try:
            from message_utils import num_tokens_from_messages
            return num_tokens_from_messages(messages)
        except Exception as e:
            print(f"计算token数量时出错: {e}", file=sys.stderr)
            return 0

    @staticmethod
    def get_messages() -> List[Dict[str, str]]:
        """获取当前消息历史"""
        return list(messages)

    @staticmethod
    def reset() -> None:
        """重置消息历史"""
        if hasattr(deepseekAPI, 'reset_messages'):
            deepseekAPI.reset_messages()

    @staticmethod
    def cleanup() -> None:
        """清理资源"""
        if hasattr(deepseekAPI, 'cleanup_thread_pools'):
            deepseekAPI.cleanup_thread_pools() 