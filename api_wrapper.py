"""
API 包装器 - 安全调用 deepseekAPI 的功能
"""
import asyncio
import sys
import traceback
from typing import Any, Dict, List, Optional, Union
import time

# 尝试导入 deepseekAPI 模块
try:
    import deepseekAPI
    from deepseekAPI import messages, client, tools
except ImportError as e:
    print(f"无法导入 deepseekAPI: {e}")
    sys.exit(1)

# 为深度思考API桥定义一个类
class MessageHistory:
    """消息历史类，用于存储和管理对话历史"""
    
    def __init__(self):
        self.messages = []
        self.token_signal = None
        self.tool_output_signal = None
        self.summary_signal = None
        self.plan_signal = None
        
    def append(self, message):
        """添加消息到历史"""
        self.messages.append(message)
        
    def __getitem__(self, index):
        """获取指定索引的消息"""
        return self.messages[index]
    
    def __len__(self):
        """获取消息历史长度"""
        return len(self.messages)
    
    def copy(self):
        """创建消息历史的副本"""
        new_history = MessageHistory()
        new_history.messages = self.messages.copy()
        return new_history

class APIBridge:
    """安全调用 deepseekAPI 功能的桥接类"""
    
    # 存储最新的工具执行结果
    _latest_tool_output = ""
    
    # 回调函数
    _tool_output_callback = None  # 控制台输出
    _task_plan_callback = None    # 任务计划
    _token_signal = None          # token计数
    _summary_signal = None        # 任务摘要
    _result_signal = None         # 对话结果
    _tool_status_signal = None    # 工具状态
    _input_callback = None        # 新增：用户输入回调函数
    
    _token_count = 0
    _task_plan = "暂无任务计划信息"
    
    # 新增：重置迭代标志
    _reset_iteration_flag = False
    
    @staticmethod
    def register_tool_output_callback(callback):
        """注册工具输出回调函数"""
        APIBridge._tool_output_callback = callback
        
    @staticmethod
    def register_result_callback(callback):
        """注册结果回调函数"""
        APIBridge._result_signal = callback
    
    @staticmethod
    def register_token_callback(callback):
        """注册token计数回调函数"""
        APIBridge._token_signal = callback
    
    @staticmethod
    def register_task_plan_callback(callback):
        """注册任务计划回调函数"""
        APIBridge._task_plan_callback = callback
    
    @staticmethod
    def register_summary_callback(callback):
        """注册任务摘要回调函数"""
        APIBridge._summary_signal = callback
    
    @staticmethod
    def register_tool_status_callback(callback):
        """注册工具状态回调函数"""
        APIBridge._tool_status_signal = callback
    
    @staticmethod
    def register_input_callback(callback):
        """注册用户输入回调函数"""
        APIBridge._input_callback = callback
        # 同时注册到input_utils模块中
        try:
            from input_utils import register_input_callback
            register_input_callback(callback)
        except Exception as e:
            print(f"注册input_utils回调时出错: {str(e)}")
    
    @staticmethod
    def set_reset_iteration_flag(flag):
        """设置重置迭代标志"""
        APIBridge._reset_iteration_flag = flag
        print(f"已设置重置迭代标志: {flag}")
    
    @staticmethod
    def get_reset_iteration_flag():
        """获取并清除重置迭代标志（一次性使用）"""
        flag = APIBridge._reset_iteration_flag
        APIBridge._reset_iteration_flag = False  # 获取后自动重置
        return flag
    
    @staticmethod
    async def execute_task(user_input: str) -> str:
        """执行任务，返回结果"""
        # 保存原始输出流
        original_stdout = sys.stdout
        original_stderr = sys.stderr
        
        # 创建用于捕获输出的字符串缓冲区
        import io
        capture_stdout = io.StringIO()
        capture_stderr = io.StringIO()
        
        class CaptureOutput:
            """捕获输出并同时发送到回调的类"""
            def __init__(self, buffer, callback=None, prefix=""):
                self.buffer = buffer
                self.callback = callback
                self.prefix = prefix
                self.line_buffer = ""
                
            def write(self, text):
                # 写入到缓冲区
                self.buffer.write(text)
                # 累积行缓冲区
                self.line_buffer += text
                
                # 如果有完整行，发送到回调
                if '\n' in self.line_buffer and self.callback:
                    lines = self.line_buffer.split('\n')
                    for i in range(len(lines)-1):  # 保留最后一个不完整的行
                        if lines[i]:  # 不发送空行
                            self.callback(f"{self.prefix}{lines[i]}")
                    self.line_buffer = lines[-1]
                    
                # 如果行缓冲区太长，也发送
                if len(self.line_buffer) > 200 and self.callback:
                    self.callback(f"{self.prefix}{self.line_buffer}")
                    self.line_buffer = ""
                    
            def flush(self):
                self.buffer.flush()
                if self.line_buffer and self.callback:
                    self.callback(f"{self.prefix}{self.line_buffer}")
                    self.line_buffer = ""
        
        class SilentOutput:
            """抑制终端输出的类"""
            def write(self, *args, **kwargs):
                pass  # 不做任何事情
            
            def flush(self):
                pass  # 不做任何事情
        
        try:
            # 导入深度思考API模块
            from deepseekAPI import main, messages, client
            
            # 注册用户输入回调到input_utils模块
            if APIBridge._input_callback:
                try:
                    from input_utils import register_input_callback
                    register_input_callback(APIBridge._input_callback)
                    if APIBridge._tool_output_callback:
                        APIBridge._tool_output_callback("已注册用户输入回调函数")
                except Exception as e:
                    if APIBridge._tool_output_callback:
                        APIBridge._tool_output_callback(f"注册用户输入回调失败: {str(e)}")
            
            # 使用捕获输出替换标准输出
            # 1. 创建同时发送到控制台的捕获器
            if APIBridge._tool_output_callback:
                sys.stdout = CaptureOutput(
                    capture_stdout, 
                    APIBridge._tool_output_callback
                )
                sys.stderr = CaptureOutput(
                    capture_stderr, 
                    APIBridge._tool_output_callback,
                    prefix="[错误] "
                )
            else:
                # 如果没有回调，则只捕获不发送
                sys.stdout = CaptureOutput(capture_stdout)
                sys.stderr = CaptureOutput(capture_stderr, prefix="[错误] ")
            
            # 显示任务开始信息 (通过回调机制发送到GUI)
            if APIBridge._tool_output_callback:
                APIBridge._tool_output_callback("\n========== 任务执行开始 ==========")
                APIBridge._tool_output_callback(f"输入: {user_input}")
                APIBridge._tool_output_callback("===================================\n")
            
            # 更新工具状态显示
            if APIBridge._tool_status_signal:
                APIBridge._tool_status_signal("当前任务", user_input[:30] + "..." if len(user_input) > 30 else user_input)
            
            # 直接使用main函数执行任务
            try:
                if APIBridge._tool_output_callback:
                    APIBridge._tool_output_callback("使用main函数执行任务...")
                
                # 确保刷新流
                sys.stdout.flush()
                sys.stderr.flush()
                
                # 执行main函数，此过程中所有输出都会被捕获并发送到回调
                response = await main(user_input)
                
                # 再次刷新流，确保所有输出都被发送
                sys.stdout.flush()
                sys.stderr.flush()
                
                # 任务完成后，更新token计数
                if APIBridge._token_signal:
                    from message_utils import num_tokens_from_messages
                    token_count = num_tokens_from_messages(messages)
                    APIBridge._token_signal(token_count)
                    
                # 提取并更新任务摘要
                try:
                    if hasattr(deepseekAPI, 'task_summary') and APIBridge._summary_signal:
                        summary_text = APIBridge.get_task_summary()  # 使用正确的方法名
                        APIBridge._summary_signal(summary_text)
                except Exception as summary_error:
                    if APIBridge._tool_output_callback:
                        APIBridge._tool_output_callback(f"更新任务摘要时出错: {str(summary_error)}")
                
            except Exception as main_error:
                # 确保刷新流，捕获到最后一刻的输出
                sys.stdout.flush()
                sys.stderr.flush()
                
                # 如果main失败，尝试直接API调用
                if APIBridge._tool_output_callback:
                    APIBridge._tool_output_callback(f"main函数执行失败，尝试直接API调用...\n错误: {str(main_error)}")
                try:
                    # 添加用户输入到消息历史
                    temp_messages = messages.copy()
                    temp_messages.append({"role": "user", "content": user_input})
                    
                    # 直接调用API
                    api_response = client.chat.completions.create(
                        model="deepseek-chat",
                        messages=temp_messages,
                        temperature=0.3
                    )
                    
                    response = api_response.choices[0].message.content
                    
                    # 添加到消息历史
                    messages.append({"role": "user", "content": user_input})
                    messages.append({"role": "assistant", "content": response})
                except Exception as api_error:
                    if APIBridge._tool_output_callback:
                        APIBridge._tool_output_callback(f"直接API调用也失败，返回错误信息\n错误: {str(api_error)}")
                    raise main_error
            
            # 获取捕获的所有输出
            all_stdout = capture_stdout.getvalue()
            all_stderr = capture_stderr.getvalue()
            
            # 如果有捕获到的输出还没通过回调发送，发送它们
            if all_stdout and APIBridge._tool_output_callback:
                lines = all_stdout.strip().split('\n')
                for line in lines:
                    if line.strip():  # 不发送空行
                        APIBridge._tool_output_callback(line)
                    
            if all_stderr and APIBridge._tool_output_callback:
                lines = all_stderr.strip().split('\n')
                for line in lines:
                    if line.strip():  # 不发送空行
                        APIBridge._tool_output_callback(f"[错误] {line}")
            
            # 显示任务完成信息
            if APIBridge._tool_output_callback:
                APIBridge._tool_output_callback("\n========== 任务执行完成 ==========")
                APIBridge._tool_output_callback(f"结果: {response[:100]}..." if len(response) > 100 else response)
                APIBridge._tool_output_callback("===================================\n")
            
            # 确保任务执行完成后有充分时间发送回调，避免线程退出时数据丢失
            try:
                # 更新对话框显示 - 任务完成时的结果
                if APIBridge._result_signal:
                    # 添加短暂延迟使其与previous_result比较，避免重复更新
                    if not hasattr(APIBridge, '_previous_result') or APIBridge._previous_result != response:
                        APIBridge._previous_result = response
                        APIBridge._result_signal(response)
                        # 增加短暂睡眠确保信号传递完成
                        time.sleep(0.1)
                
                # 更新工具状态 - 任务完成
                if APIBridge._tool_status_signal:
                    APIBridge._tool_status_signal("任务状态", "已完成")
                    time.sleep(0.05)  # 短暂等待确保信号处理
                    
                    # 更新最终token计数
                    try:
                        from message_utils import num_tokens_from_messages
                        token_count = num_tokens_from_messages(messages)
                        APIBridge._tool_status_signal("token_count", str(token_count))
                        time.sleep(0.05)  # 短暂等待确保信号处理
                    except Exception as token_error:
                        print(f"更新token计数时出错: {token_error}", file=sys.stderr)
            except Exception as callback_error:
                print(f"发送完成回调时出错: {callback_error}", file=sys.stderr)
                # 错误不影响返回结果
            
            return response
                
        except Exception as e:
            error_msg = f"任务执行失败: {str(e)}"
            if APIBridge._tool_output_callback:
                APIBridge._tool_output_callback(f"\n========== 任务执行失败 ==========")
                APIBridge._tool_output_callback(error_msg)
                APIBridge._tool_output_callback("===================================\n")
                
                # 提供错误详情
                error_details = traceback.format_exc()
                APIBridge._tool_output_callback("\n详细错误信息:")
                APIBridge._tool_output_callback(error_details)
            
                # 更新对话框显示 - 任务失败消息
                if APIBridge._result_signal:
                    APIBridge._result_signal(f"执行任务时出错: {str(e)}")
            
                # 更新工具状态 - 任务失败
                if APIBridge._tool_status_signal:
                    APIBridge._tool_status_signal("任务状态", "失败")
            
            return f"执行任务时出错: {str(e)}"
        finally:
            # 恢复原始输出流
            sys.stdout = original_stdout
            sys.stderr = original_stderr
    
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

    @staticmethod
    def get_task_summary() -> str:
        """获取当前任务的摘要信息"""
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
            
            return "暂无任务摘要信息"
        except Exception as e:
            print(f"获取任务摘要时出错: {e}", file=sys.stderr)
            return "获取任务摘要时出错" 