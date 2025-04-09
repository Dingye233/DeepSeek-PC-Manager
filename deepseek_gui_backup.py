import sys
import os
import json
import time
import asyncio
import markdown
from datetime import datetime
import warnings
import re

# 添加忽略特定Qt警告的功能
class QtWarningFilter:
    def __init__(self):
        self._original_stderr = sys.stderr
        self.patterns_to_ignore = [
            r'QBasicTimer::start: Timers cannot be started from another thread',
            r'QObject::killTimer: Timers cannot be stopped from another thread',
            r'QObject::~QObject: Timers cannot be stopped from another thread'
        ]
        
    def write(self, text):
        # 检查是否需要忽略这个警告
        for pattern in self.patterns_to_ignore:
            if re.search(pattern, text):
                return  # 忽略匹配的警告
        # 正常写入其他内容
        self._original_stderr.write(text)
        
    def flush(self):
        self._original_stderr.flush()

# 安装警告过滤器
sys.stderr = QtWarningFilter()

from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                           QHBoxLayout, QTextEdit, QLineEdit, QPushButton, 
                           QTabWidget, QLabel, QSystemTrayIcon, QMenu, 
                           QAction, QFileDialog, QMessageBox, QFrame,
                           QGraphicsView, QGraphicsScene, QGraphicsPixmapItem,
                           QSplitter, QDialog, QProgressBar, QDialogButtonBox,
                           QListWidgetItem, QListWidget)
from PyQt5.QtCore import Qt, QTimer, QThread, pyqtSignal, QPropertyAnimation, QEasingCurve, QMetaObject, QDateTime
from PyQt5.QtGui import QIcon, QTextCursor, QColor, QPalette, QPixmap, QPainter, QFont, QTransform, QTextCharFormat
from PyQt5.QtSvg import QSvgWidget
from dotenv import load_dotenv
import threading

# Import the modules from your existing code
try:
    from deepseekAPI import reset_messages, cleanup_thread_pools, messages, client, tools
    from api_wrapper import APIBridge
    from message_utils import num_tokens_from_messages
except ImportError:
    # Mock objects for development/testing
    messages = []
    client = None
    tools = []
    class APIBridge:
        @staticmethod
        async def execute_task(user_input):
            return "Sample response from mock APIBridge"
        
        @staticmethod
        def get_messages():
            return messages
            
        @staticmethod
        def reset():
            messages.clear()
            
        @staticmethod
        def cleanup():
            pass
            
        @staticmethod
        def set_tool_output_callback(callback):
            """模拟设置工具输出回调函数"""
            pass
            
        @staticmethod
        def set_task_plan_callback(callback):
            """模拟设置任务计划回调函数"""
            pass
    
    def reset_messages():
        messages.clear()
    def cleanup_thread_pools():
        pass
    def num_tokens_from_messages(messages):
        return len(str(messages)) // 4

try:
    from tool_registry import get_tools
    from file_utils import user_information_read
except ImportError:
    def get_tools():
        return []
    def user_information_read():
        return "User information"

# Define a custom exception for task errors
class TaskExecutionError(Exception):
    pass

class MessageHistory:
    def __init__(self):
        self.messages = messages.copy()
        self.token_signal = None
        self.tool_signal = None
        self.summary_signal = None
        self.plan_signal = None

    def append(self, message):
        self.messages.append(message)

    def clear(self):
        self.messages = messages.copy()

    def __iter__(self):
        return iter(self.messages)

    def __len__(self):
        return len(self.messages)

    def __getitem__(self, index):
        return self.messages[index]

    def __setitem__(self, index, value):
        self.messages[index] = value

    def copy(self):
        new_history = MessageHistory()
        new_history.messages = self.messages.copy()
        return new_history

class WorkerThread(QThread):
    # 信号定义
    result_ready = pyqtSignal(str)
    task_plan_ready = pyqtSignal(str)
    console_output_ready = pyqtSignal(str)
    user_input_needed = pyqtSignal(str, int, object)  # prompt, timeout, error_message(可以为None)
    error_occurred = pyqtSignal(str)
    tool_usage_ready = pyqtSignal(str, str)  # 工具名称, 工具状态
    loading_state_changed = pyqtSignal(bool)
    
    def __init__(self, input_text, api_bridge, gui_ref=None):
        super().__init__()
        self.input_text = input_text
        self.api_bridge = api_bridge
        self.gui_ref = gui_ref
        self.user_continue = None
        self.user_continue_lock = threading.Lock()
        self.user_continue_event = threading.Event()
        
    def safe_emit(self, signal, *args):
        """安全地发出信号并立即处理事件"""
        try:
            if signal and args:
                # 在主线程中发出信号
                signal.emit(*args)
                # 立即处理事件，确保UI实时更新
                QApplication.processEvents()
                # 对于重要更新（比如控制台输出和任务计划），强制刷新
                if signal in [self.console_output_ready, self.task_plan_ready]:
                    # 多处理几次事件，确保UI完全更新
                    for _ in range(3):
                        QApplication.processEvents()
                        time.sleep(0.01)  # 短暂暂停让UI有时间绘制
        except Exception as e:
            print(f"发出信号时出错: {str(e)}")
        
    def log_error(self, msg):
        """安全地记录错误"""
        print(f"ERROR: {msg}", file=sys.stderr)
        # 也将错误发送到UI
        try:
            self.error_occurred.emit(msg)
            # 确保错误信息立即显示
            QApplication.processEvents()
        except Exception as e:
            print(f"发送错误信号时出错: {str(e)}", file=sys.stderr)
        
    def run(self):
        """QThread的主执行方法"""
        loop = None
        try:
            # 显示加载动画
            self.safe_emit(self.loading_state_changed, True)
            
            # 创建异步事件循环
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            # 注册回调函数以实时接收工具输出和任务计划
            def tool_output_callback(output):
                if output and output.strip():
                    # 立即发送信号并确保UI更新
                    self.safe_emit(self.console_output_ready, output)
                    # 分割消息以确保及时传递
                    lines = output.strip().split("\n")
                    # 如果消息过长，分多次发送以提高实时性
                    if len(lines) > 10:
                        chunks = ["\n".join(lines[i:i+10]) for i in range(0, len(lines), 10)]
                        for chunk in chunks:
                            if chunk and chunk.strip():
                                self.safe_emit(self.console_output_ready, chunk)
                                # 短暂暂停以确保UI更新
                                time.sleep(0.05)
            
            def task_plan_callback(plan):
                if plan and plan.strip():
                    # 立即发送信号并确保UI更新
                    self.safe_emit(self.task_plan_ready, plan)
                    # 添加迭代次数识别和更新
                    if "迭代" in plan:
                        try:
                            # 尝试从计划中提取迭代信息
                            iteration_match = re.search(r'迭代\s*(\d+)\s*/\s*(\d+)', plan)
                            if iteration_match:
                                current_iter = int(iteration_match.group(1))
                                total_iter = int(iteration_match.group(2))
                                # TODO: 添加迭代更新信号
                                print(f"识别到迭代进度: {current_iter}/{total_iter}")
                        except Exception as e:
                            self.log_error(f"提取迭代信息时出错: {e}")
            
            # 定义一个变量来存储最后的AI消息，供用户输入时使用
            self.last_ai_message = None
            
            # 注册用户输入回调函数
            def input_callback(prompt, timeout=60, error_message=None):
                try:
                    # 记录最后一条AI消息
                    from deepseekAPI import messages
                    for msg in reversed(messages):
                        if msg.get("role") == "assistant" and msg.get("content"):
                            self.last_ai_message = msg.get("content")
                            break
                    
                    # 将AI最后的消息发送到UI
                    if self.last_ai_message:
                        self.safe_emit(self.result_ready, self.last_ai_message)
                        # 确保UI更新
                        QApplication.processEvents()
                        time.sleep(0.1)  # 短暂等待确保消息显示
                except Exception as e:
                    self.log_error(f"获取AI消息时出错: {str(e)}")
                
                # 发射信号到主线程以显示对话框
                self.safe_emit(self.user_input_needed, prompt, timeout, error_message)
                
                # 创建一个事件循环等待结果
                input_event = asyncio.Event()
                try:
                    self.parent()._current_input_event = input_event
                    self.parent()._current_input_result = None
                    
                    # 等待用户输入完成
                    loop.run_until_complete(asyncio.wait_for(input_event.wait(), timeout + 5))
                    
                    # 获取结果
                    result = self.parent()._current_input_result
                    
                    # 清理
                    self.parent()._current_input_event = None
                    self.parent()._current_input_result = None
                    
                    return result
                except Exception as e:
                    self.log_error(f"处理用户输入时出错: {str(e)}")
                    return "继续执行"  # 出错时默认继续
            
            # 设置回调
            APIBridge.set_tool_output_callback(tool_output_callback)
            APIBridge.set_task_plan_callback(task_plan_callback)
            
            # 设置用户输入回调
            from input_utils import register_input_callback
            register_input_callback(input_callback)
            
            try:
                # 使用 APIBridge 执行任务
                result = loop.run_until_complete(APIBridge.execute_task(self.input_text))
                
                # 获取并发送当前token数量
                from api_wrapper import APIBridge as ExternalAPIBridge
                token_count = ExternalAPIBridge.get_token_count()
                self.safe_emit(self.tool_usage_ready, "token_count", str(token_count))
                
                # 获取并发送任务计划和摘要
                task_plan = APIBridge.get_task_plan()
                if task_plan and task_plan != "暂无任务计划信息":
                    self.safe_emit(self.task_plan_ready, task_plan)
                
                # 获取并发送最新的工具执行结果
                tool_output = APIBridge.get_latest_tool_output()
                if tool_output:
                    self.safe_emit(self.console_output_ready, tool_output)
                    # 通知工具输出状态更新了
                    self.safe_emit(self.tool_usage_ready, "工具输出", "已更新")
                
                # 发送完成信号
                self.safe_emit(self.result_ready, result)
            except Exception as e:
                error_msg = f"执行任务时出错: {str(e)}"
                self.log_error(error_msg)
                self.safe_emit(self.error_occurred, error_msg)
            
        except Exception as e:
            # 捕获意外错误
            error_msg = f"运行错误: {str(e)}"
            self.log_error(error_msg)
            self.safe_emit(self.error_occurred, error_msg)
            
        finally:
            # 清除回调
            try:
                APIBridge.set_tool_output_callback(None)
                APIBridge.set_task_plan_callback(None)
                
                # 注销用户输入回调
                from input_utils import register_input_callback
                register_input_callback(None)
            except Exception as e:
                print(f"清理回调时出错: {str(e)}")
            
            # 隐藏加载动画
            self.safe_emit(self.loading_state_changed, False)
            
            # 确保清理事件循环
            if loop and not loop.is_closed():
                try:
                    loop.close()
                except Exception as e:
                    print(f"关闭事件循环时出错: {str(e)}")
                    
    def handle_secondary_input_needed(self, prompt, timeout=60, error_message=None):
        """处理需要用户二次输入的情况 - 由主线程调用"""
        # 这个方法必须由主线程调用
        # 可以通过信号从工作线程调用到主线程
        
        global last_confirmation_time
        current_time = time.time()
        
        # 检查是否启用了防止过度确认功能，以及是否在冷却期内
        if DISABLE_EXCESSIVE_CONFIRMATION and (current_time - last_confirmation_time < CONFIRMATION_COOLDOWN):
            # 如果在冷却期内，自动返回继续执行的响应
            self._current_input_result = "继续执行"
            if self._current_input_event is not None:
                def set_event():
                    import asyncio
                    asyncio.run_coroutine_threadsafe(self._set_event_async(), asyncio.get_event_loop())
                QTimer.singleShot(0, set_event)
            return
        
        # AI消息已经由WorkerThread中的input_callback发送和显示
        # 此处不再尝试获取和显示AI消息
            
        # 先将错误信息显示在控制台和聊天记录中
        if error_message:
            # 在控制台输出错误信息
            error_formatted = f"\n⚠️ 任务执行出错: {error_message}\n"
            cursor = self.console_output_tab.textCursor()
            cursor.movePosition(QTextCursor.End)
            
            # 设置错误文本格式
            format = QTextCharFormat()
            format.setForeground(QColor("#D32F2F"))  # 红色
            format.setFontWeight(QFont.Bold)
            cursor.setCharFormat(format)
            
            # 插入文本
            cursor.insertText(error_formatted)
            
            # 滚动到最新内容
            self.console_output_tab.setTextCursor(cursor)
            self.console_output_tab.ensureCursorVisible()
            
            # 强制立即更新UI
            self.console_output_tab.repaint()
            QApplication.processEvents()
            
            # 切换到控制台输出选项卡
            self.tab_widget.setCurrentIndex(1)
            
        # 更新最后确认时间
        last_confirmation_time = current_time
        
        self.secondary_input_needed = True
        self.prompt = prompt
        
        # 在聊天区域显示提示信息
        formatted_prompt = f"""
        <div style="background-color: #E8F5E9; padding: 10px; border-left: 4px solid #4CAF50; margin: 5px 0;">
            <b>🔄 需要您的输入:</b><br/>
            {prompt}<br/><br/>
            <span style="color: #0D47A1;">请直接在输入框中输入您的回复:</span><br/>
            - 直接按回车或输入建议 = 继续任务<br/>
            - 输入"终止"或"2" = 终止任务
        </div>
        """
        
        # 如果有错误信息，也在聊天区域显示
        if error_message:
            formatted_error = f"""
            <div style="background-color: #FFEBEE; padding: 10px; border-left: 4px solid #D32F2F; margin: 5px 0;">
                <b>⚠️ 错误详情:</b><br/>
                {error_message}
            </div>
            """
            self.chat_display.append(formatted_error)
            
        # 在聊天区域显示提示信息
        self.chat_display.append(formatted_prompt)
        self.chat_display.moveCursor(QTextCursor.End)
        self.chat_display.ensureCursorVisible()
        
        # 修改输入框提示文字
        self.input_field.setPlaceholderText(f"请输入您的回复 (剩余时间: {timeout}秒)...")
        self.input_field.setFocus()
        
        # 创建一个定时器来处理超时
        self.input_timer = QTimer(self)
        self.input_timer.timeout.connect(self.handle_input_timeout)
        self.input_timer.start(timeout * 1000)  # 转换为毫秒
        
        # 连接输入框的回车信号
        self.input_field.returnPressed.disconnect(self.send_message)
        self.input_field.returnPressed.connect(self.handle_secondary_input_from_field)
        
        # 也断开发送按钮的连接并重新连接
        self.send_button.clicked.disconnect(self.send_message)
        self.send_button.clicked.connect(self.handle_secondary_input_from_field)
        
        # 更改发送按钮文本
        self.send_button.setText("提交回复")
        
    def handle_secondary_input_from_field(self):
        """从输入框获取二次输入"""
        # 获取用户输入
        input_text = self.input_field.text().strip()
        
        # 清空输入框
        self.input_field.clear()
        
        # 重置输入框提示
        self.input_field.setPlaceholderText("💬 Type your message here...")
        
        # 停止定时器
        if hasattr(self, 'input_timer') and self.input_timer.isActive():
            self.input_timer.stop()
            
        # 恢复输入框和按钮的连接
        self.input_field.returnPressed.disconnect(self.handle_secondary_input_from_field)
        self.input_field.returnPressed.connect(self.send_message)
        
        self.send_button.clicked.disconnect(self.handle_secondary_input_from_field)
        self.send_button.clicked.connect(self.send_message)
        
        # 恢复发送按钮文本
        self.send_button.setText("Send 📤")
        
        # 在聊天区域显示用户的回复
        self.chat_display.append(f'<div style="color: #2E7D32; font-size: 14px;"><b>👤 您的回复:</b> {input_text}</div>')
        
        # 设置结果并触发事件
        self.secondary_input = input_text
        self.secondary_input_needed = False
        
        # 如果有等待中的事件，设置结果并触发事件
        if self._current_input_event is not None:
            self._current_input_result = input_text
            # 使用异步方法安全触发事件
            def set_event():
                import asyncio
                asyncio.run_coroutine_threadsafe(self._set_event_async(), asyncio.get_event_loop())
            
            # 使用QTimer确保在正确的线程上调用
            QTimer.singleShot(0, set_event)
        
    def handle_input_timeout(self):
        """处理输入超时"""
        # 如果用户在规定时间内没有输入，自动提交空字符串
        if self.secondary_input_needed:
            # 添加超时提示
            self.chat_display.append('<div style="color: #FFA000; font-size: 14px;"><b>⏱️ 输入超时:</b> 自动继续执行</div>')
            
            # 重置状态
            self.input_field.returnPressed.disconnect(self.handle_secondary_input_from_field)
            self.input_field.returnPressed.connect(self.send_message)
            
            self.send_button.clicked.disconnect(self.handle_secondary_input_from_field)
            self.send_button.clicked.connect(self.send_message)
            
            # 恢复提示和按钮文本
            self.input_field.setPlaceholderText("💬 Type your message here...")
            self.send_button.setText("Send 📤")
            
            # 如果有等待中的事件，设置结果并触发事件
            if self._current_input_event is not None:
                self._current_input_result = "继续执行"  # 超时默认继续
                # 使用异步方法安全触发事件
                def set_event():
                    import asyncio
                    asyncio.run_coroutine_threadsafe(self._set_event_async(), asyncio.get_event_loop())
                
                # 使用QTimer确保在正确的线程上调用
                QTimer.singleShot(0, set_event)
            
            self.secondary_input_needed = False

    async def _set_event_async(self):
        """安全地设置事件"""
        if self._current_input_event is not None:
            self._current_input_event.set()
            
    def _ensure_single_worker(self):
        """确保只有一个工作线程在运行"""
        if hasattr(self, 'worker') and self.worker and self.worker.isRunning():
            try:
                print("检测到正在运行的工作线程，正在停止...")
                self.worker.quit()
                if not self.worker.wait(1000):  # 等待1秒
                    print("强制终止工作线程")
                    self.worker.terminate()
                    self.worker.wait(1000)  # 再等待1秒确保终止
            except Exception as e:
                print(f"清理之前的线程时出错: {e}")
                
        # 重置事件和结果
        self._current_input_event = None
        self._current_input_result = None

    def update_loading_state(self, state):
        """更新加载状态，显示或隐藏加载动画"""
        if state:
            self.spinner.show()  # 显示加载动画
            
            # 如果状态栏右侧没有加载状态文本，则添加
            if not hasattr(self, 'loading_label') or not self.loading_label:
                self.loading_label = QLabel("正在处理请求... ")
                self.loading_label.setStyleSheet("color: #FF9800; font-weight: bold;")
                self.status_layout.addWidget(self.loading_label)
        else:
            self.spinner.hide()  # 隐藏加载动画
            
            # 隐藏加载状态文本
            if hasattr(self, 'loading_label') and self.loading_label:
                self.loading_label.hide()
                self.status_layout.removeWidget(self.loading_label)
                self.loading_label.deleteLater()
                self.loading_label = None

    def show_from_tray(self):
        self.showNormal()
        self.activateWindow()

    def show_from_floating_ball(self):
        self.showNormal()
        self.activateWindow()
        self.floating_ball.hide()

    def tray_icon_activated(self, reason):
        if reason == QSystemTrayIcon.Trigger:
            self.show_from_tray()

    def changeEvent(self, event):
        if event.type() == event.WindowStateChange:
            if self.windowState() & Qt.WindowMinimized:
                self.hide()
                self.floating_ball.show()
                self.floating_ball.move(self.x(), self.y())

    def closeEvent(self, event):
        self.quit_application()

    def quit_application(self):
        # 在程序退出前确保所有线程正确结束
        try:
            if hasattr(self, 'worker') and self.worker and self.worker.isRunning():
                print("等待工作线程结束...")
                self.worker.quit()
                # 等待最多3秒
                if not self.worker.wait(3000):
                    print("强制终止工作线程")
                    self.worker.terminate()
            
            # 使用 APIBridge 清理资源
            APIBridge.cleanup()
        except Exception as e:
            print(f"清理线程时出错: {e}")
        
        QApplication.quit()

    def load_help_content(self):
        try:
            with open("README.md", "r", encoding="utf-8") as f:
                content = f.read()
                html = markdown.markdown(content)
                self.help_tab.setHtml(html)
        except Exception as e:
            self.help_tab.setPlainText(f"Error loading help content: {str(e)}")

    def load_user_info(self):
        try:
            with open("user-information.txt", "r", encoding="utf-8") as f:
                self.user_info_edit.setPlainText(f.read())
        except Exception as e:
            self.user_info_edit.setPlainText("")

    def save_user_info(self):
        try:
            with open("user-information.txt", "w", encoding="utf-8") as f:
                f.write(self.user_info_edit.toPlainText())
            QMessageBox.information(self, "Success", "User information saved successfully!")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save user information: {str(e)}")

    def save_settings(self):
        try:
            with open(".env", "w") as f:
                f.write(f'api_key="{self.api_key_input.text()}"\n')
                f.write(f'key="{self.weather_key_input.text()}"\n')
                f.write(f'QQ_EMAIL="{self.email_input.text()}"\n')
                f.write(f'AUTH_CODE="{self.auth_code_input.text()}"\n')
            QMessageBox.information(self, "Success", "Settings saved successfully!")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save settings: {str(e)}")

    def import_chat_history(self):
        file_name, _ = QFileDialog.getOpenFileName(self, "Import Chat History", "", "JSON Files (*.json)")
        if file_name:
            try:
                with open(file_name, "r", encoding="utf-8") as f:
                    history = json.load(f)
                    
                    # 先清空当前消息历史
                    self.messages_history.clear()
                    
                    # 添加导入的消息到历史
                    for msg in history:
                        self.messages_history.append(msg)
                    
                    # 更新界面显示
                    self.chat_display.clear()
                    for msg in history:
                        if msg["role"] in ["user", "assistant"]:
                            self.append_message(msg["role"], msg["content"])
                    
                    # 同步到后端 API 的消息历史
                    from deepseekAPI import messages as api_messages
                    api_messages.clear()
                    for msg in history:
                        api_messages.append(msg)
                    
                    # 更新 Token 计数
                    token_count = num_tokens_from_messages(self.messages_history)
                    if hasattr(self, 'token_label'):
                        self.token_label.setText(f"🔢 Tokens: {token_count}")
                        
                QMessageBox.information(self, "Success", "聊天历史导入成功!")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"导入聊天历史失败: {str(e)}")

    def export_chat_history(self):
        file_name, _ = QFileDialog.getSaveFileName(self, "Export Chat History", "", "JSON Files (*.json)")
        if file_name:
            try:
                # 确保文件名以.json结尾
                if not file_name.endswith('.json'):
                    file_name += '.json'
                
                # 导出完整的对话历史
                with open(file_name, "w", encoding="utf-8") as f:
                    json.dump(list(self.messages_history), f, ensure_ascii=False, indent=2)
                
                QMessageBox.information(self, "Success", "聊天历史导出成功!")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"导出聊天历史失败: {str(e)}")

    def show_summary(self):
        summary_dialog = QMessageBox(self)
        summary_dialog.setWindowTitle("Task Summary")
        summary_dialog.setText("\n".join(self.task_summary))
        summary_dialog.exec_()

    # Add a method to handle errors from the worker thread
    def handle_error(self, error_msg):
        """处理错误信息"""
        # 记录错误
        try:
            with open("error_log.txt", "a", encoding="utf-8") as f:
                f.write(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {error_msg}\n")
        except Exception as e:
            print(f"无法写入错误日志: {e}", file=sys.stderr)
        
        # 在聊天窗口显示错误
        self.chat_display.append(
            f'<div style="color: #D32F2F; font-size: 14px;">'
            f'<b>⚠️ 错误:</b> {error_msg}</div>'
        )
        
        # 在控制台输出窗口也显示错误
        self.console_output_tab.append(
            f'<div style="color: #D32F2F; background-color: #FFEBEE; padding: 5px; '
            f'border-left: 4px solid #D32F2F; margin: 5px 0;">'
            f'<b>执行错误:</b><br/>{error_msg}</div>'
        )
        
        # 更新工具状态
        self.update_tool_status("发生错误", "错误")
        
        # 隐藏加载动画
        self.update_loading_state(False)

# 检查是否禁用过度确认
DISABLE_EXCESSIVE_CONFIRMATION = os.getenv("DISABLE_EXCESSIVE_CONFIRMATION", "false").lower() == "true"
# 用于防止短时间内多次弹出确认窗口
CONFIRMATION_COOLDOWN = 10  # 秒
last_confirmation_time = 0

def main():
    # Load environment variables
    load_dotenv()
    
    # Create QApplication instance
    app = QApplication(sys.argv)
    
    # Create main window
    window = MainWindow()
    window.show()
    
    # Run application
    sys.exit(app.exec_())

if __name__ == "__main__":
    main() 