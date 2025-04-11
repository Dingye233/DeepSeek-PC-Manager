import sys
import os
import json
import time
import asyncio
import markdown
from datetime import datetime
import warnings
import re
import math
import traceback

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
                           QListWidgetItem, QListWidget, QGroupBox, QComboBox,
                           QScrollArea, QDesktopWidget)
from PyQt5.QtCore import Qt, QTimer, QThread, pyqtSignal, QPropertyAnimation, QEasingCurve, QMetaObject, QDateTime, QSettings, QSize, QEvent, pyqtSlot, QRect
from PyQt5.QtGui import QIcon, QTextCursor, QColor, QPalette, QPixmap, QPainter, QFont, QTransform, QTextCharFormat, QGuiApplication, QClipboard, QTextOption, QSyntaxHighlighter, QTextFormat, QPen
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

class LoadingSpinner(QWidget):
    """自定义加载动画组件"""
    def __init__(self, parent=None, size=30, num_dots=8, dot_size=5):
        super().__init__(parent)
        self.setFixedSize(size, size)
        self.dots = num_dots
        self.dot_size = dot_size
        self.counter = 0
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_rotation)
        self.timer.start(100)  # 每100毫秒更新一次
        
    def update_rotation(self):
        """更新旋转动画"""
        self.counter = (self.counter + 1) % self.dots
        self.update()
        
    def paintEvent(self, event):
        """绘制组件"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        # 计算中心点和半径
        center_x = self.width() / 2
        center_y = self.height() / 2
        radius = min(center_x, center_y) - self.dot_size
        
        for i in range(self.dots):
            # 计算点的位置
            angle = 2 * 3.14159 * i / self.dots
            x = center_x + radius * math.cos(angle)
            y = center_y + radius * math.sin(angle)
            
            # 计算颜色 (当前位置最亮)
            alpha = 255 - ((i - self.counter) % self.dots) * (255 // self.dots)
            color = QColor(255, 165, 0, alpha)  # 橙色, 透明度变化
            painter.setBrush(color)
            painter.setPen(Qt.NoPen)
            
            # 绘制圆点
            painter.drawEllipse(int(x - self.dot_size/2), int(y - self.dot_size/2), 
                               self.dot_size, self.dot_size)
        
    def showEvent(self, event):
        """显示时启动定时器"""
        self.timer.start()
        
    def hideEvent(self, event):
        """隐藏时停止定时器"""
        self.timer.stop()

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
            # 检查信号和参数
            if not signal or not args:
                return
                
            # 先检查线程状态，避免在线程已结束时发送信号
            if not getattr(self, "_is_running", True):
                print("警告: 尝试在线程已结束后发送信号")
                return
                
            # 检查当前线程是否是GUI主线程
            if QThread.currentThread() != QApplication.instance().thread():
                # 如果不是主线程，使用Qt的信号-槽机制安全发送到主线程
                try:
                    signal.emit(*args)
                except RuntimeError as rt_error:
                    print(f"发出信号时出错 (非主线程): {str(rt_error)}")
                # 不在子线程中调用processEvents
                return
            
            # 在主线程中发出信号
            try:
                signal.emit(*args)
            except Exception as e:
                print(f"发出信号时出错 (主线程): {str(e)}")
                return
                
            # 大幅减少处理事件的调用，仅对关键输出类型进行处理
            # 过多调用processEvents会导致事件循环嵌套和应用崩溃
            if signal == self.console_output_ready:
                # 控制台输出频繁更新时不要每次都处理事件
                current_time = time.time()
                if not hasattr(self, '_last_process_time') or current_time - self._last_process_time > 0.5:
                    QApplication.processEvents(QEventLoop.ExcludeUserInputEvents)
                    self._last_process_time = current_time
        except Exception as e:
            print(f"发出信号时出错: {str(e)}")
            # 避免在信号处理期间崩溃
            pass
        
    def run(self):
        """QThread的主执行方法"""
        # 设置线程运行状态标志，供safe_emit方法使用
        self._is_running = True
        
        # 更新线程状态
        self.safe_emit(self.loading_state_changed, True)
        print("🌟 任务线程已启动")
        
        # 获取或创建事件循环
        try:
            loop = asyncio.get_event_loop()
            if loop.is_closed():
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        # 获取API桥接对象
        from api_wrapper import APIBridge
        
        # 初始化回调函数
        print("🔄 初始化API回调...")
        
        # 控制台输出回调 - 更新控制台区域
        def console_output_callback(text):
            # 将工具输出加入队列
            self.safe_emit(self.console_output_ready, text)
        
        # 注册回调函数
        APIBridge.register_tool_output_callback(console_output_callback)
        
        # 任务计划回调
        def task_plan_callback(task_plan):
            self.safe_emit(self.task_plan_ready, task_plan)
        
        APIBridge.register_task_plan_callback(task_plan_callback)
        
        # 摘要回调
        def summary_callback(summary):
            try:
                # 找到并更新任务摘要编辑区
                for window in QApplication.topLevelWidgets():
                    if isinstance(window, MainWindow):
                        if hasattr(window, 'update_task_summary'):
                            window.update_task_summary(summary)
            except Exception as e:
                print(f"🔴 更新任务摘要时出错: {str(e)}")
        
        APIBridge.register_summary_callback(summary_callback)
        
        # 工具状态回调
        def tool_status_callback(tool_name, status):
            # 更新工具状态显示
            self.safe_emit(self.tool_usage_ready, tool_name, status)
        
        APIBridge.register_tool_status_callback(tool_status_callback)
        
        # 结果回调 - 更新对话区域
        def result_callback(response):
            # 更新对话区域
            self.safe_emit(self.result_ready, response)
        
        APIBridge.register_result_callback(result_callback)
        
        # 用户输入回调 - 处理用户输入请求
        def input_callback(prompt, timeout=60, error_message=None):
            try:
                # 显示在控制台
                print(f"\n⚠️ 需要用户输入: {prompt}")
                if error_message:
                    print(f"🔴 错误信息: {error_message}")
                print(f"⏱️ 等待用户响应 (超时: {timeout}秒)")
                
                # 尝试从消息历史中找出最后一条AI消息
                try:
                    from deepseekAPI import messages
                    # 先记录一下计划使用的消息，以防后面崩溃
                    self.last_ai_message = "需要您的输入"
                    
                    # 查找最后一条AI消息
                    for msg in reversed(messages):
                        if msg.get("role") == "assistant" and msg.get("content"):
                            self.last_ai_message = msg.get("content")
                            break
                    
                    # 确保AI消息不是空的
                    if not self.last_ai_message or not self.last_ai_message.strip():
                        self.last_ai_message = "AI助手需要您的输入"
                    
                    # 构建完整的用户输入请求消息
                    input_request_msg = f"{self.last_ai_message}\n\n⚠️ 需要您的输入: {prompt}"
                    if error_message:
                        input_request_msg += f"\n\n错误信息: {error_message}"
                    input_request_msg += f"\n\n(将在{timeout}秒后默认继续执行，请注意查看对话框)"
                    
                    # 将AI最后的消息发送到UI (使用信号而不是直接调用)
                    self.safe_emit(self.result_ready, input_request_msg)
                    # 不在工作线程中调用processEvents
                    time.sleep(0.2)  # 增加短暂等待时间确保消息显示
                except Exception as e:
                    print(f"获取AI消息时出错 (这不会影响功能): {str(e)}")
                
                # 确保用户输入对话框在主线程中显示
                # 增加强制前台显示的机制
                try:
                    # 尝试激活主窗口，确保它在前台
                    for window in QApplication.topLevelWidgets():
                        if isinstance(window, MainWindow):
                            window.activateWindow()
                            window.raise_()
                            break
                except Exception as e:
                    print(f"激活主窗口时出错: {str(e)}")

                # 发射信号到主线程以显示对话框
                self.safe_emit(self.user_input_needed, prompt, timeout, error_message)
                
                # 创建一个事件循环等待结果
                input_event = asyncio.Event()
                try:
                    # 获取主窗口引用，更安全的方式
                    main_window = None
                    if self.gui_ref:
                        main_window = self.gui_ref
                    elif self.parent():
                        main_window = self.parent()
                        
                    if not main_window:
                        # 尝试从全局窗口列表获取MainWindow引用
                        try:
                            for window in QApplication.topLevelWidgets():
                                if isinstance(window, MainWindow):
                                    main_window = window
                                    break
                        except Exception as e:
                            print(f"尝试从全局寻找主窗口时出错: {str(e)}")
                        
                        # 如果仍然找不到主窗口
                        if not main_window:
                            print("🔴 无法获取主窗口引用，用户输入将失败")
                            return "继续执行"  # 默认继续
                        
                    # 设置窗口关联的事件和结果
                    main_window._current_input_event = input_event
                    main_window._current_input_result = None
                    
                    # 确保窗口显示在前台
                    try:
                        main_window.activateWindow()
                        main_window.raise_()
                    except Exception as e:
                        print(f"尝试激活主窗口时出错: {str(e)}")
                    
                    # 等待用户输入完成，增加超时处理
                    try:
                        # 使用线程事件而不是异步等待，避免事件循环嵌套问题
                        wait_event = threading.Event()
                        
                        # 在主线程中设置异步事件的回调机制
                        def on_input_complete():
                            try:
                                if not input_event.is_set():
                                    asyncio.run_coroutine_threadsafe(input_event.set(), loop)
                                wait_event.set()
                            except Exception as e:
                                print(f"🔴 设置输入完成事件时出错: {str(e)}")
                                wait_event.set()  # 确保在出错时也会继续
                        
                        # 通过QTimer在主线程中检查输入状态
                        def check_input_status():
                            try:
                                if main_window._current_input_result is not None:
                                    on_input_complete()
                                    return
                                # 确保对话框显示在前台
                                if hasattr(main_window, '_current_input_dialog') and main_window._current_input_dialog:
                                    try:
                                        if not main_window._current_input_dialog.isActiveWindow():
                                            main_window._current_input_dialog.activateWindow()
                                            main_window._current_input_dialog.raise_()
                                    except Exception as e:
                                        print(f"激活对话框时出错: {str(e)}")
                                # 继续检查
                                QTimer.singleShot(100, check_input_status)
                            except Exception as e:
                                print(f"检查输入状态时出错: {str(e)}")
                                # 出错时确保继续
                                on_input_complete()
                        
                        # 在主线程启动检查
                        QMetaObject.invokeMethod(QApplication.instance(), 
                                                lambda: QTimer.singleShot(0, check_input_status),
                                                Qt.QueuedConnection)
                        
                        # 使用线程事件等待而不是事件循环等待
                        if not wait_event.wait(timeout + 10):  # 给更多额外时间
                            print("🔴 等待用户输入超时")
                            # 添加弹出通知，提醒用户任务因超时将继续执行
                            try:
                                QMetaObject.invokeMethod(QApplication.instance(),
                                    lambda: QMessageBox.information(main_window, "输入超时", 
                                                                  "等待输入超时，任务将继续执行。"),
                                    Qt.QueuedConnection)
                            except Exception as e:
                                print(f"显示超时通知时出错: {str(e)}")
                            return "继续执行"
                    except Exception as e:
                        print(f"🔴 等待用户输入时出错: {str(e)}")
                        return "继续执行"  # 出错默认继续
                    
                    # 获取结果
                    result = main_window._current_input_result
                    
                    # 清理
                    main_window._current_input_event = None
                    main_window._current_input_result = None
                    
                    # 如果结果为空，返回默认值
                    if result is None:
                        return "继续执行"
                    
                    # 显示用户选择
                    print(f"👤 用户响应: {result}")
                    
                    return result
                except Exception as e:
                    print(f"🔴 处理用户输入时出错: {str(e)}")
                    return "继续执行"  # 出错时默认继续
            except Exception as e:
                print(f"🔴 用户输入回调发生异常: {str(e)}")
                return "继续执行"  # 如果出现任何错误，返回默认值
        
        # 注册用户输入回调函数
        APIBridge.register_input_callback(input_callback)
        
        # 定义一个变量来存储最后的AI消息，供用户输入时使用
        self.last_ai_message = None
        
        try:
            # 使用 APIBridge 执行任务
            print("🚀 开始执行任务...")
            result = loop.run_until_complete(APIBridge.execute_task(self.input_text))
            print("✅ 任务执行完成")
            
            # 获取并发送当前token数量
            try:
                from api_wrapper import APIBridge as ExternalAPIBridge
                token_count = ExternalAPIBridge.get_token_count()
                self.safe_emit(self.tool_usage_ready, "token_count", str(token_count))
            except Exception as e:
                print(f"🔴 获取token计数时出错: {str(e)}")
            
            # 获取并发送任务计划和摘要
            try:
                task_plan = APIBridge.get_task_plan()
                if task_plan and task_plan != "暂无任务计划信息":
                    self.safe_emit(self.task_plan_ready, task_plan)
            except Exception as e:
                print(f"🔴 获取任务计划时出错: {str(e)}")
            
            # 获取并发送最新的工具执行结果
            try:
                tool_output = APIBridge.get_latest_tool_output()
                if tool_output:
                    self.safe_emit(self.console_output_ready, tool_output)
                    # 通知工具输出状态更新了
                    self.safe_emit(self.tool_usage_ready, "工具输出", "已更新")
            except Exception as e:
                print(f"🔴 获取工具输出时出错: {str(e)}")
            
            # 移除重复的结果发送，API桥接层已经处理了结果发送
            # self.safe_emit(self.result_ready, result)
        except Exception as e:
            error_msg = f"执行任务时出错: {str(e)}"
            print(f"🔴 {error_msg}")
            self.safe_emit(self.error_occurred, error_msg)
        finally:
            # 避免在finally块中进行复杂的清理操作，而是传递信号让主线程处理
            try:
                print("🏁 任务线程即将完成")
                
                # 先标记线程状态为非运行，避免后续回调中访问已销毁的对象
                self._is_running = False
                
                try:
                    # 通知完成状态 - 只发送信号，不进行其他操作
                    self.loading_state_changed.emit(False)
                except Exception as signal_error:
                    print(f"🔴 发送完成状态信号时出错: {str(signal_error)}")
                
                try:
                    # 断开所有信号连接，防止延迟的信号被处理
                    self.result_ready.disconnect()
                except Exception:
                    pass  # 忽略断开连接时的错误
                    
                try:
                    # 不直接删除自己，在主线程中安排删除 - 延长延迟时间到5000毫秒(5秒)
                    # 确保所有回调和信号都有足够时间完成
                    QMetaObject.invokeMethod(QApplication.instance(), 
                                          lambda: QTimer.singleShot(5000, self.deleteLater),
                                          Qt.QueuedConnection)
                except Exception as delete_error:
                    print(f"🔴 安排删除线程时出错: {str(delete_error)}")
                    # 备用删除方法
                    QTimer.singleShot(5000, self.deleteLater)
                
            except Exception as e:
                print(f"🔴 线程清理过程中出错: {str(e)}")
                # 确保线程最终能被删除
                try:
                    QTimer.singleShot(5000, self.deleteLater)
                except:
                    pass

class MainWindow(QMainWindow):
    def __init__(self, parent=None):
        """构造函数：初始化主窗口"""
        super().__init__(parent)

        # 创建机器人图标
        self.robot_icon = self.create_robot_icon()
        
        # 设置窗口标题和大小
        self.setWindowTitle("DeepSeek PC Manager")
        self.resize(850, 650)
        self.setMinimumSize(600, 400)
        
        # 窗口属性设置
        self.setAttribute(Qt.WA_DeleteOnClose, False)
        
        # 初始化UI组件
        self.init_ui()
        
        # 创建系统托盘图标
        self.init_tray_icon()
        
        # 创建浮动球
        self.init_floating_ball()
        
        # 更新时钟
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_time)
        self.timer.start(1000)  # 每秒更新一次
        
    def init_ui(self):
        """初始化UI组件"""
        # 创建中央窗口部件
        central_widget = QWidget(self)
        self.setCentralWidget(central_widget)
        main_layout = QHBoxLayout(central_widget)
        
        # 创建左侧聊天区域
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        
        # 聊天显示区域
        self.chat_display = QTextEdit()
        self.chat_display.setReadOnly(True)
        self.chat_display.setStyleSheet("""
            QTextEdit {
                border: 1px solid #E0E0E0;
                border-radius: 8px;
                background-color: #FFFFFF;
                padding: 10px;
                font-size: 16px;
            }
        """)
        
        # 输入区域
        input_area = QWidget()
        input_layout = QHBoxLayout(input_area)
        input_layout.setContentsMargins(0, 10, 0, 0)
        
        self.input_field = QLineEdit()
        self.input_field.setPlaceholderText("输入您的问题或指令...")
        self.input_field.setStyleSheet("""
            QLineEdit {
                border: 1px solid #E0E0E0;
                border-radius: 20px;
                padding: 10px 15px;
                font-size: 16px;
                background-color: #F5F5F5;
            }
            QLineEdit:focus {
                border: 1px solid #2196F3;
                background-color: white;
            }
        """)
        self.input_field.returnPressed.connect(self.send_message)
        
        send_button = QPushButton("发送")
        send_button.setStyleSheet("""
            QPushButton {
                background-color: #2196F3;
                color: white;
                border: none;
                border-radius: 20px;
                padding: 10px 20px;
                font-size: 16px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #1976D2;
            }
            QPushButton:pressed {
                background-color: #0D47A1;
            }
        """)
        send_button.clicked.connect(self.send_message)
        
        input_layout.addWidget(self.input_field, 7)  # 占70%
        input_layout.addWidget(send_button, 3)  # 占30%
        
        # 添加组件到左侧布局
        left_layout.addWidget(self.chat_display, 8)  # 聊天区域占80%
        left_layout.addWidget(input_area, 2)  # 输入区域占20%
        
        # 初始化右侧面板
        self.init_right_panel()
        
        # 添加组件到主布局
        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(left_panel)
        splitter.addWidget(self.right_panel)
        splitter.setSizes([550, 300])  # 设置初始大小
        
        main_layout.addWidget(splitter)
        
        # 状态栏设置
        self.statusBar().setStyleSheet("QStatusBar { border-top: 1px solid #E0E0E0; }")
        self.status_layout = QHBoxLayout()
        self.status_layout.setContentsMargins(5, 0, 5, 0)
        self.status_layout.setSpacing(10)
        
        # 添加状态信息
        self.time_label = QLabel(datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        self.tool_label = QLabel("🔧 Tool: 无")
        self.token_label = QLabel("🔢 Tokens: 0")
        
        # 添加加载动画
        self.spinner = LoadingSpinner(self, size=25)
        self.spinner.hide()  # 初始隐藏
        
        status_bar_widget = QWidget()
        status_bar_widget.setLayout(self.status_layout)
        
        # 添加状态信息到状态栏
        self.status_layout.addWidget(self.time_label)
        self.status_layout.addWidget(self.tool_label)
        self.status_layout.addWidget(self.token_label)
        self.status_layout.addStretch(1)
        self.status_layout.addWidget(self.spinner)
        
        self.statusBar().addPermanentWidget(status_bar_widget, 1)
        
        # 欢迎消息
        welcome_message = """
## 欢迎使用 DeepSeek PC Manager

我是您的AI助手，可以帮助您执行以下任务：

- 📂 **文件管理**: 查找、整理、重命名文件
- 🔍 **系统分析**: 检测系统问题与优化
- ⚙️ **配置管理**: 调整系统设置
- 🛠️ **故障排除**: 解决常见问题

请在下方输入框中输入您的问题或任务。
        """
        self.append_message("assistant", welcome_message)
        
    def create_robot_icon(self):
        """创建机器人emoji图标"""
        try:
            # 创建多种尺寸的图标
            icon_sizes = [16, 24, 32, 48, 64, 128]
            self.robot_icon = QIcon()
            
            for size in icon_sizes:
                pixmap = QPixmap(size, size)
                pixmap.fill(Qt.transparent)
                
                painter = QPainter(pixmap)
                painter.setRenderHint(QPainter.Antialiasing)
                painter.setRenderHint(QPainter.TextAntialiasing)
                
                # 使用更安全的绘制方法 - 不依赖于字体
                # 机器人图标的简单绘制
                painter.setPen(Qt.NoPen)
                
                # 绘制机器人头部（圆形）
                head_color = QColor(120, 120, 220)  # 蓝紫色
                painter.setBrush(head_color)
                head_size = int(size * 0.8)
                head_x = (size - head_size) // 2
                head_y = (size - head_size) // 2
                painter.drawEllipse(head_x, head_y, head_size, head_size)
                
                # 绘制眼睛（两个小圆）
                eye_color = QColor(255, 255, 255)  # 白色
                painter.setBrush(eye_color)
                eye_size = int(size * 0.15)
                eye_spacing = int(size * 0.2)
                eye_y = int(size * 0.35)
                
                left_eye_x = int(size / 2 - eye_spacing)
                right_eye_x = int(size / 2 + eye_spacing - eye_size)
                
                painter.drawEllipse(left_eye_x, eye_y, eye_size, eye_size)
                painter.drawEllipse(right_eye_x, eye_y, eye_size, eye_size)
                
                # 绘制眼珠（小黑点）
                pupil_color = QColor(0, 0, 0)  # 黑色
                painter.setBrush(pupil_color)
                pupil_size = int(eye_size * 0.5)
                pupil_offset = int((eye_size - pupil_size) / 2)
                
                painter.drawEllipse(left_eye_x + pupil_offset, eye_y + pupil_offset, pupil_size, pupil_size)
                painter.drawEllipse(right_eye_x + pupil_offset, eye_y + pupil_offset, pupil_size, pupil_size)
                
                # 绘制嘴巴（直线）
                mouth_color = QColor(70, 70, 70)  # 深灰色
                pen = QPen()
                pen.setColor(mouth_color)
                pen.setWidth(int(size * 0.05))
                painter.setPen(pen)
                
                mouth_y = int(size * 0.65)
                mouth_width = int(size * 0.4)
                painter.drawLine(int(size / 2 - mouth_width / 2), mouth_y, 
                                 int(size / 2 + mouth_width / 2), mouth_y)
                
                # 绘制天线（两条线）
                antenna_color = QColor(100, 100, 100)  # 灰色
                pen.setColor(antenna_color)
                pen.setWidth(int(size * 0.03))
                painter.setPen(pen)
                
                antenna_base_y = int(size * 0.2)
                antenna_top_y = int(size * 0.05)
                antenna_spacing = int(size * 0.15)
                
                painter.drawLine(int(size / 2 - antenna_spacing), antenna_base_y, 
                                 int(size / 2 - antenna_spacing), antenna_top_y)
                painter.drawLine(int(size / 2 + antenna_spacing), antenna_base_y, 
                                 int(size / 2 + antenna_spacing), antenna_top_y)
                
                painter.end()
                
                self.robot_icon.addPixmap(pixmap)
            
            # 设置窗口图标
            self.setWindowIcon(self.robot_icon)
            
            return self.robot_icon
        except Exception as e:
            print(f"创建机器人图标时出错: {str(e)}")
            # 返回默认图标
            return QIcon()
        
    def init_tray_icon(self):
        """初始化系统托盘图标"""
        # 创建系统托盘图标
        self.tray_icon = QSystemTrayIcon(self)
        self.tray_icon.setIcon(self.robot_icon)
        self.tray_icon.setToolTip("DeepSeek PC Manager")
        
        # 创建托盘菜单
        self.tray_menu = QMenu()
        
        # 添加显示动作
        show_action = QAction("显示", self)
        show_action.triggered.connect(self.show_from_tray)
        self.tray_menu.addAction(show_action)
        
        # 添加分隔线
        self.tray_menu.addSeparator()
        
        # 添加退出动作
        quit_action = QAction("退出", self)
        quit_action.triggered.connect(self.quit_application)
        self.tray_menu.addAction(quit_action)
        
        # 设置托盘菜单
        self.tray_icon.setContextMenu(self.tray_menu)
        
        # 连接托盘图标激活信号
        self.tray_icon.activated.connect(self.tray_icon_activated)
        
        # 显示托盘图标
        self.tray_icon.show()

    def init_floating_ball(self):
        """初始化浮动球"""
        try:
            self.floating_ball = QWidget(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
            self.floating_ball.setFixedSize(60, 80)  # 加高一点以容纳文字标签
            # 设置窗口背景透明
            self.floating_ball.setAttribute(Qt.WA_TranslucentBackground)
            
            layout = QVBoxLayout(self.floating_ball)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(0)
            
            # 创建一个QLabel用于显示自定义绘制的机器人图标
            self.robot_label = QLabel()
            self.robot_label.setFixedSize(50, 50)
            
            # 创建图像并绘制机器人
            robot_pixmap = QPixmap(50, 50)
            robot_pixmap.fill(Qt.transparent)
            
            painter = QPainter(robot_pixmap)
            painter.setRenderHint(QPainter.Antialiasing)
            
            # 绘制圆形背景（半透明）
            bg_color = QColor(30, 30, 30, 150)  # 深色半透明背景
            painter.setBrush(bg_color)
            painter.setPen(Qt.NoPen)
            painter.drawEllipse(0, 0, 50, 50)
            
            # 绘制机器人图标（类似create_robot_icon方法中的绘制逻辑）
            # 绘制机器人头部（圆形）
            head_color = QColor(120, 120, 220)  # 蓝紫色
            painter.setBrush(head_color)
            head_size = 40
            head_x = (50 - head_size) // 2
            head_y = (50 - head_size) // 2
            painter.drawEllipse(head_x, head_y, head_size, head_size)
            
            # 绘制眼睛（两个小圆）
            eye_color = QColor(255, 255, 255)  # 白色
            painter.setBrush(eye_color)
            eye_size = 7
            eye_spacing = 10
            eye_y = 17
            
            left_eye_x = 50 // 2 - eye_spacing
            right_eye_x = 50 // 2 + eye_spacing - eye_size
            
            painter.drawEllipse(left_eye_x, eye_y, eye_size, eye_size)
            painter.drawEllipse(right_eye_x, eye_y, eye_size, eye_size)
            
            # 绘制眼珠（小黑点）
            pupil_color = QColor(0, 0, 0)  # 黑色
            painter.setBrush(pupil_color)
            pupil_size = eye_size // 2
            pupil_offset = (eye_size - pupil_size) // 2
            
            painter.drawEllipse(left_eye_x + pupil_offset, eye_y + pupil_offset, pupil_size, pupil_size)
            painter.drawEllipse(right_eye_x + pupil_offset, eye_y + pupil_offset, pupil_size, pupil_size)
            
            # 绘制嘴巴（直线）
            mouth_color = QColor(70, 70, 70)  # 深灰色
            pen = QPen()
            pen.setColor(mouth_color)
            pen.setWidth(2)
            painter.setPen(pen)
            
            mouth_y = 32
            mouth_width = 20
            painter.drawLine(50 // 2 - mouth_width // 2, mouth_y, 
                           50 // 2 + mouth_width // 2, mouth_y)
            
            # 绘制天线（两条线）
            antenna_color = QColor(100, 100, 100)  # 灰色
            pen.setColor(antenna_color)
            pen.setWidth(1)
            painter.setPen(pen)
            
            antenna_base_y = 10
            antenna_top_y = 2
            antenna_spacing = 7
            
            painter.drawLine(50 // 2 - antenna_spacing, antenna_base_y, 
                           50 // 2 - antenna_spacing, antenna_top_y)
            painter.drawLine(50 // 2 + antenna_spacing, antenna_base_y, 
                           50 // 2 + antenna_spacing, antenna_top_y)
            
            painter.end()
            
            # 设置图像
            self.robot_label.setPixmap(robot_pixmap)
            self.robot_label.setAlignment(Qt.AlignCenter)
            layout.addWidget(self.robot_label)
            
            # 添加"执行中"文本标签
            self.status_label = QLabel("执行中")
            self.status_label.setStyleSheet("""
                background-color: transparent;
                color: #1976D2;  /* 蓝色 */
                font-size: 12px;
                font-weight: bold;
            """)
            self.status_label.setAlignment(Qt.AlignCenter)
            layout.addWidget(self.status_label)
            
            # 设置圆形窗口样式
            self.floating_ball.setStyleSheet("""
                QWidget {
                    background-color: transparent;
                }
            """)
            
            # 创建透明度动画
            self.opacity_animation = QPropertyAnimation(self.floating_ball, b"windowOpacity")
            self.opacity_animation.setDuration(1500)  # 1.5秒完成一次变化
            self.opacity_animation.setStartValue(1.0)
            self.opacity_animation.setEndValue(0.5)
            self.opacity_animation.setEasingCurve(QEasingCurve.InOutSine)
            
            # 创建标签文字透明度动画（通过样式表模拟）
            self.text_opacity = 100
            self.text_fade_direction = -1  # -1为减小，1为增加
            self.text_timer = QTimer(self)
            self.text_timer.timeout.connect(self.update_text_opacity)
            
            # 连接动画完成信号
            self.opacity_animation.finished.connect(self.toggle_opacity_animation)
            
            # 添加鼠标事件处理
            self.floating_ball.mousePressEvent = self.floating_ball_mouse_press
            self.floating_ball.mouseMoveEvent = self.floating_ball_mouse_move
            self.floating_ball.mouseReleaseEvent = self.floating_ball_mouse_release
            self.floating_ball.mouseDoubleClickEvent = self.floating_ball_double_click
            
            # 初始化拖动相关变量
            self._drag_pos = None
            self._is_dragging = False
            
            # 从设置中读取上次的位置
            try:
                settings = QSettings()
                pos = settings.value("FloatingBall/Position")
                if pos:
                    self.floating_ball.move(pos)
                else:
                    # 默认位置在屏幕右上角
                    screen = QApplication.primaryScreen().geometry()
                    self.floating_ball.move(screen.width() - 80, 20)
            except Exception as e:
                print(f"读取悬浮球位置时出错: {str(e)}")
                # 默认位置在屏幕右上角
                screen = QApplication.primaryScreen().geometry()
                self.floating_ball.move(screen.width() - 80, 20)
            
            # 初始隐藏浮动球和状态标签
            self.floating_ball.hide()
            self.status_label.hide()
            
        except Exception as e:
            print(f"初始化浮动球时出错: {str(e)}")
            self.floating_ball = None
            
    def update_text_opacity(self):
        """更新文本标签的透明度"""
        try:
            # 更新透明度值
            self.text_opacity += self.text_fade_direction * 2
            
            # 检查边界并反转方向
            if self.text_opacity <= 0:
                self.text_opacity = 0
                self.text_fade_direction = 1
            elif self.text_opacity >= 100:
                self.text_opacity = 100
                self.text_fade_direction = -1
                
            # 应用新的透明度
            self.status_label.setStyleSheet(f"""
                background-color: transparent;
                color: rgba(25, 118, 210, {self.text_opacity/100});
                font-size: 12px;
                font-weight: bold;
            """)
        except Exception as e:
            print(f"更新文本透明度时出错: {str(e)}")
            
    def toggle_opacity_animation(self):
        """切换透明度动画方向"""
        try:
            current_opacity = self.floating_ball.windowOpacity()
            
            # 反转动画
            self.opacity_animation.setStartValue(current_opacity)
            self.opacity_animation.setEndValue(1.0 if current_opacity <= 0.5 else 0.5)
            self.opacity_animation.start()
        except Exception as e:
            print(f"切换透明度动画时出错: {str(e)}")
            
    def start_floating_ball_animation(self):
        """启动悬浮球动画效果"""
        try:
            # 显示状态标签
            self.status_label.show()
            # 启动透明度动画
            self.opacity_animation.start()
            # 启动文本透明度动画
            self.text_timer.start(50)  # 每50毫秒更新一次
        except Exception as e:
            print(f"启动悬浮球动画时出错: {str(e)}")
            
    def stop_floating_ball_animation(self):
        """停止悬浮球动画效果"""
        try:
            # 停止透明度动画
            self.opacity_animation.stop()
            # 恢复初始透明度
            self.floating_ball.setWindowOpacity(1.0)
            # 停止文本动画
            self.text_timer.stop()
            # 隐藏状态标签
            self.status_label.hide()
        except Exception as e:
            print(f"停止悬浮球动画时出错: {str(e)}")
            
    def floating_ball_mouse_press(self, event):
        """处理浮动球鼠标按下事件"""
        if event.button() == Qt.LeftButton:
            self._drag_pos = event.globalPos() - self.floating_ball.frameGeometry().topLeft()
            self._is_dragging = False  # 初始设置为False，在移动时才设置为True
            event.accept()
            
    def floating_ball_mouse_move(self, event):
        """处理浮动球鼠标移动事件"""
        if event.buttons() == Qt.LeftButton and self._drag_pos is not None:
            self._is_dragging = True  # 标记正在拖动
            # 计算新位置
            new_pos = event.globalPos() - self._drag_pos
            
            # 确保不会拖出屏幕
            screen = QApplication.primaryScreen().geometry()
            x = max(0, min(new_pos.x(), screen.width() - self.floating_ball.width()))
            y = max(0, min(new_pos.y(), screen.height() - self.floating_ball.height()))
            
            self.floating_ball.move(x, y)
            event.accept()
            
    def floating_ball_mouse_release(self, event):
        """处理浮动球鼠标释放事件"""
        if event.button() == Qt.LeftButton:
            # 如果没有拖动，则认为是点击事件
            if not self._is_dragging:
                self.show_from_floating_ball()
            else:
                # 保存新位置
                try:
                    settings = QSettings()
                    settings.setValue("FloatingBall/Position", self.floating_ball.pos())
                except Exception as e:
                    print(f"保存悬浮球位置时出错: {str(e)}")
            
            self._drag_pos = None
            self._is_dragging = False
            event.accept()
            
    def floating_ball_double_click(self, event):
        """处理浮动球双击事件"""
        if event.button() == Qt.LeftButton:
            self.show_from_floating_ball()
            event.accept()
            
    def changeEvent(self, event):
        """处理窗口状态变化事件"""
        if event.type() == QEvent.WindowStateChange:
            # 如果窗口被最小化
            if self.windowState() & Qt.WindowMinimized:
                # 如果系统托盘图标可见，则隐藏窗口
                if hasattr(self, 'tray_icon') and self.tray_icon.isVisible():
                    # 延迟执行hide，防止最小化动画问题
                    QTimer.singleShot(0, self.hide)
                    # 当窗口隐藏到托盘时，不在任务栏显示
                    self.update_taskbar_visibility(False)
                    # 显示气泡提示
                    self.tray_icon.showMessage(
                        "DeepSeek PC Manager",
                        "程序已最小化到系统托盘，双击图标可恢复",
                        QSystemTrayIcon.Information,
                        2000
                    )
                    event.accept()
            elif self.windowState() & Qt.WindowActive:
                # 窗口被激活时，确保在任务栏显示
                self.update_taskbar_visibility(True)
                
        super().changeEvent(event)

    def closeEvent(self, event):
        """处理窗口关闭事件"""
        # 只是隐藏，不关闭
        event.ignore()
        # 隐藏主窗口并更新任务栏可见性
        self.hide()
        self.update_taskbar_visibility(False)
        # 显示系统托盘气泡提示
        self.tray_icon.showMessage(
            "DeepSeek PC Manager",
            "程序已最小化到系统托盘，双击图标可恢复",
            QSystemTrayIcon.Information,
            2000
        )

    def show_from_tray(self):
        """从系统托盘显示窗口"""
        # 从托盘显示窗口时更新任务栏可见性
        self.update_taskbar_visibility(True)
        self.showNormal()
        self.activateWindow()
        self.raise_()  # 确保窗口在前台显示
        
    def tray_icon_activated(self, reason):
        """处理系统托盘图标激活事件"""
        if reason == QSystemTrayIcon.DoubleClick:
            self.show_from_tray()

    def quit_application(self):
        """程序退出逻辑，确保正常终止"""
        # 关闭所有进行中的任务和线程
        try:
            # 停止可能正在运行的worker线程
            if hasattr(self, 'worker') and self.worker and self.worker.isRunning():
                self.worker.quit()
                self.worker.wait(1000)  # 最多等待1秒
            
            # 停止动画和定时器
            if hasattr(self, 'floating_ball') and self.floating_ball:
                self.stop_floating_ball_animation()
            
            # 记录正常退出
            try:
                with open("recovery_log.txt", "a", encoding="utf-8") as f:
                    f.write(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 用户手动退出程序\n")
            except:
                pass
        except Exception as e:
            print(f"退出程序时出错: {str(e)}")
        
        # 使用QApplication.exit()代替quit()可以设置返回码
        QApplication.exit(0)

    def handle_secondary_input_needed(self, prompt, timeout=60, error_message=None):
        """处理需要用户二次输入的情况，例如工具执行失败需要用户选择继续或终止"""
        try:
            # 确保清除可能存在的旧对话框引用
            if hasattr(self, '_current_input_dialog') and self._current_input_dialog:
                try:
                    if self._current_input_dialog.isVisible():
                        self._current_input_dialog.close()
                except Exception:
                    pass
                self._current_input_dialog = None
                
            # 创建一个自定义dialog
            dialog = QDialog(self)
            dialog.setWindowTitle("需要您的输入")
            dialog.setMinimumWidth(600)  # 设置最小宽度，确保显示足够信息
            
            # 保存对话框引用，便于其他函数访问
            self._current_input_dialog = dialog
            
            # 设置窗口标志，确保显示在最前
            dialog.setWindowFlags(dialog.windowFlags() | Qt.WindowStaysOnTopHint)
            
            layout = QVBoxLayout(dialog)
            
            # 添加醒目标题标签
            title_label = QLabel("⚠️ 任务需要您的输入或决策")
            title_label.setStyleSheet("""
                font-size: 16px;
                font-weight: bold;
                color: #FF5722;
                padding: 5px;
            """)
            layout.addWidget(title_label)
            
            # 从消息历史中获取最后一条AI消息作为上下文
            ai_context = "未找到上下文信息"
            try:
                from deepseekAPI import messages
                for msg in reversed(messages):
                    if msg.get("role") == "assistant" and msg.get("content"):
                        ai_context = msg.get("content")
                        break
            except Exception as e:
                print(f"获取AI上下文时出错: {str(e)}")
            
            # 显示任务上下文信息
            context_group = QGroupBox("AI上下文信息")
            context_layout = QVBoxLayout(context_group)
            
            # 显示最后的AI消息
            context_text = QTextEdit()
            context_text.setReadOnly(True)
            context_text.setPlainText(ai_context)
            context_text.setStyleSheet("""
                QTextEdit {
                    background-color: #F0F8FF;
                    border: 1px solid #B0C4DE;
                    border-radius: 5px;
                    padding: 10px;
                    font-size: 14px;
                    max-height: 150px;
                }
            """)
            context_layout.addWidget(context_text)
            layout.addWidget(context_group)
            
            # 显示当前输入请求信息
            input_request_group = QGroupBox("输入请求")
            input_request_layout = QVBoxLayout(input_request_group)
            
            # 显示具体的提示信息
            prompt_text = QTextEdit()
            prompt_text.setReadOnly(True)
            prompt_text.setPlainText(prompt)
            prompt_text.setStyleSheet("""
                QTextEdit {
                    background-color: #F5F5F5;
                    border: 1px solid #E0E0E0;
                    border-radius: 5px;
                    padding: 10px;
                    font-size: 14px;
                    max-height: 100px;
                }
            """)
            input_request_layout.addWidget(prompt_text)
            layout.addWidget(input_request_group)
            
            # 如果有错误信息，显示错误信息
            if error_message:
                error_group = QGroupBox("错误信息")
                error_group.setStyleSheet("QGroupBox { color: #D32F2F; }")
                error_layout = QVBoxLayout(error_group)
                
                error_label = QLabel(error_message)
                error_label.setWordWrap(True)
                error_label.setStyleSheet("color: #D32F2F;")
                error_layout.addWidget(error_label)
                
                layout.addWidget(error_group)
            
            # 输入说明
            input_group = QGroupBox("您的回应")
            input_layout = QVBoxLayout(input_group)
            
            # 添加解决问题的提示
            if error_message:
                suggestion_label = QLabel("""
                <b>建议操作：</b><br>
                1. 选择"继续尝试"：系统将尝试其他方法解决问题<br>
                2. 选择"终止任务"：停止当前任务执行<br>
                3. 提供自定义解决方案：在下方输入框中提供具体解决方法
                """)
                suggestion_label.setStyleSheet("""
                    background-color: #E8F5E9;
                    border-radius: 5px;
                    padding: 10px;
                    margin-bottom: 10px;
                """)
                suggestion_label.setWordWrap(True)
                input_layout.addWidget(suggestion_label)
            
            # 添加常用选项按钮
            options_layout = QHBoxLayout()
            continue_btn = QPushButton("继续尝试")
            continue_btn.setStyleSheet("""
                QPushButton {
                    background-color: #4CAF50;
                    color: white;
                    border: none;
                    border-radius: 15px;
                    padding: 8px 15px;
                    font-weight: bold;
                }
                QPushButton:hover {
                    background-color: #45a049;
                }
            """)
            continue_btn.clicked.connect(lambda: self.handle_option_selected(dialog, "继续尝试"))
            
            terminate_btn = QPushButton("终止任务")
            terminate_btn.setStyleSheet("""
                QPushButton {
                    background-color: #F44336;
                    color: white;
                    border: none;
                    border-radius: 15px;
                    padding: 8px 15px;
                    font-weight: bold;
                }
                QPushButton:hover {
                    background-color: #D32F2F;
                }
            """)
            terminate_btn.clicked.connect(lambda: self.handle_option_selected(dialog, "终止"))
            
            options_layout.addWidget(continue_btn)
            options_layout.addWidget(terminate_btn)
            input_layout.addLayout(options_layout)
            
            # 自定义输入说明
            custom_label = QLabel("或者提供您自己的指导/建议:")
            input_layout.addWidget(custom_label)
            
            # 输入框 - 使用QTextEdit替代，便于多行输入
            input_field = QTextEdit()
            input_field.setPlaceholderText("在此输入您的自定义回应，例如提供新的方法或思路...\n按Ctrl+Enter快速提交")
            input_field.setMaximumHeight(100)
            
            # 设置按键事件处理，支持Ctrl+Enter快速提交
            def handle_key_press(event):
                if event.key() == Qt.Key_Return and event.modifiers() & Qt.ControlModifier:
                    self.handle_option_selected(dialog, input_field.toPlainText())
                else:
                    QTextEdit.keyPressEvent(input_field, event)
            
            # 自定义QTextEdit类处理按键事件
            class CustomTextEdit(QTextEdit):
                def keyPressEvent(self, event):
                    if event.key() == Qt.Key_Return and event.modifiers() & Qt.ControlModifier:
                        self.parent().parent().handle_option_selected(dialog, self.toPlainText())
                    else:
                        super().keyPressEvent(event)
            
            # 替换为自定义文本编辑框
            input_field = CustomTextEdit()
            input_field.setPlaceholderText("在此输入您的自定义回应，例如提供新的方法或思路...\n按Ctrl+Enter快速提交")
            input_field.setMaximumHeight(100)
            input_layout.addWidget(input_field)
            
            # 提交自定义输入按钮
            submit_btn = QPushButton("提交自定义回应 (Ctrl+Enter)")
            submit_btn.setStyleSheet("""
                QPushButton {
                    background-color: #2196F3;
                    color: white;
                    border: none;
                    border-radius: 15px;
                    padding: 8px 15px;
                    font-weight: bold;
                }
                QPushButton:hover {
                    background-color: #1976D2;
                }
            """)
            submit_btn.clicked.connect(lambda: self.handle_option_selected(dialog, input_field.toPlainText()))
            input_layout.addWidget(submit_btn)
            
            # 设置默认焦点在输入框
            input_field.setFocus()
            
            layout.addWidget(input_group)
            
            # 添加倒计时显示
            countdown_label = QLabel(f"倒计时: {timeout}秒")
            countdown_label.setStyleSheet("color: #FF5722; font-weight: bold;")
            layout.addWidget(countdown_label)
            
            # 创建定时器更新倒计时
            timer = QTimer(dialog)
            remaining_time = [timeout]  # 使用列表以便在嵌套函数中修改
            
            def update_countdown():
                remaining_time[0] -= 1
                if remaining_time[0] <= 0:
                    timer.stop()
                    # 检查用户是否已经输入了内容
                    if input_field.toPlainText().strip():
                        # 如果用户输入了内容但没有点击提交，自动提交
                        self.handle_option_selected(dialog, input_field.toPlainText())
                    else:
                        dialog.accept()  # 时间到自动接受对话框
                        if not self._current_input_result:
                            self._current_input_result = "继续尝试"
                else:
                    countdown_label.setText(f"倒计时: {remaining_time[0]}秒")
                    # 最后10秒改为红色加粗提醒
                    if remaining_time[0] <= 10:
                        countdown_label.setStyleSheet("color: #D50000; font-weight: bold; font-size: 16px;")
            
            timer.timeout.connect(update_countdown)
            timer.start(1000)  # 每秒更新一次
            
            # 在聊天窗口中添加提示消息，让用户知道需要输入什么
            # 将AI上下文和输入请求一起显示在对话区域中
            prompt_msg = f"{ai_context}\n\n⚠️ 需要您的输入: {prompt}"
            if error_message:
                prompt_msg += f"\n\n错误信息: {error_message}"
            
            prompt_msg += f"\n\n如果不操作，将在{timeout}秒后默认继续执行。请在弹出的对话框中做出选择。"
            self.append_message("assistant", prompt_msg)
            
            # 确保对话框在前台显示
            dialog.setWindowFlags(dialog.windowFlags() | Qt.WindowStaysOnTopHint)
            dialog.activateWindow()
            dialog.raise_()
            
            # 屏幕居中显示
            frame_geometry = dialog.frameGeometry()
            screen_center = QDesktopWidget().availableGeometry().center()
            frame_geometry.moveCenter(screen_center)
            dialog.move(frame_geometry.topLeft())
            
            # 显示消息框并等待用户选择
            dialog.setModal(True)
            
            # 再次确保在前台显示
            QTimer.singleShot(100, lambda: dialog.activateWindow())
            QTimer.singleShot(100, lambda: dialog.raise_())
            
            if dialog.exec_():
                timer.stop()  # 确保停止定时器
                result = self._current_input_result if self._current_input_result else "继续尝试"
                
                # 记录用户选择到控制台
                print(f"用户输入结果: {result}")
                self.console_output_tab.append(f"用户选择: {result}")
                
                # 清理引用
                self._current_input_dialog = None
                
                return result
            else:
                timer.stop()  # 确保停止定时器
                
                # 清理引用
                self._current_input_dialog = None
                
                return "继续尝试"  # 如果对话框被关闭，默认继续尝试
                
        except Exception as e:
            self.log_error(f"处理二次输入时出错: {str(e)}")
            
            # 尝试显示错误提示
            try:
                QMessageBox.warning(self, "输入处理错误", 
                                 f"处理用户输入时发生错误: {str(e)}\n系统将默认继续执行任务。")
            except:
                pass
                
            return "继续尝试"  # 出错时默认继续尝试

    def handle_option_selected(self, dialog, result):
        """处理用户选择的选项"""
        # 确保结果不为空
        if result is None or (isinstance(result, str) and not result.strip()):
            result = "继续尝试"
        
        # 记录用户输入并输出到控制台以便调试
        print(f"用户选择了: {result}")
        self.console_output_tab.append(f"用户输入响应: {result}")
        
        # 如果用户选择终止，通知用户并准备终止流程
        if result == "终止":
            try:
                # 在UI中显示终止消息
                self.append_message("system", "用户选择终止任务，系统将停止当前执行。")
                self.console_output_tab.append("⚠️ 用户选择终止任务")
                
                # 终止当前工作线程(如果存在)
                if hasattr(self, 'worker') and self.worker and self.worker.isRunning():
                    try:
                        print("正在终止工作线程...")
                        self.worker.quit()
                        self.worker.wait(1000)  # 等待最多1秒
                        
                        # 如果仍在运行，尝试强制断开连接
                        if self.worker.isRunning():
                            try:
                                self.worker.result_ready.disconnect()
                                self.worker.error_occurred.disconnect()
                                self.worker.console_output_ready.disconnect()
                                self.worker.user_input_needed.disconnect()
                                self.worker.loading_state_changed.disconnect()
                            except Exception:
                                pass
                    except Exception as e:
                        print(f"终止工作线程时出错: {str(e)}")
                
                # 设置加载状态为False
                self.update_loading_state(False)
                
                # 显示终止消息
                QMessageBox.information(self, "任务已终止", 
                                     "根据您的选择，当前任务已被终止。\n您可以开始一个新的任务。")
            except Exception as e:
                print(f"处理终止任务时出错: {str(e)}")
        # 如果用户选择继续或输入自定义响应，设置重置迭代标志
        elif result == "继续尝试" or len(result) > 0:
            # 继续尝试时，记录详细日志
            if result == "继续尝试":
                self.console_output_tab.append("用户选择继续尝试，系统将重置迭代计数")
            else:
                # 用户提供了自定义解决方案
                self.console_output_tab.append(f"用户提供了自定义解决方案: {result}")
                # 在UI中显示用户的自定义方案
                self.append_message("user", f"我的建议：{result}")
            
            try:
                # 通过APIBridge设置重置迭代标志
                from api_wrapper import APIBridge
                if hasattr(APIBridge, 'set_reset_iteration_flag'):
                    APIBridge.set_reset_iteration_flag(True)
                    print("已设置重置迭代标志")
                    self.console_output_tab.append("📌 已发送重置迭代计数器信号")
                else:
                    print("APIBridge没有set_reset_iteration_flag方法")
                    # 尝试使用其他可用方法处理
                    if hasattr(APIBridge, 'reset'):
                        APIBridge.reset()
                        print("使用APIBridge.reset()作为替代")
                        self.console_output_tab.append("📌 已使用reset方法作为替代")
            except Exception as e:
                print(f"设置重置迭代标志时出错: {str(e)}")
                self.console_output_tab.append(f"⚠️ 设置重置标志时出错: {str(e)}")
                
            # 如果用户提供了自定义解决方案，尝试特殊处理
            if result != "继续尝试" and len(result) > 10:  # 确保是有意义的建议
                try:
                    # 检查是否包含Python代码片段
                    if "```python" in result or "def " in result or "import " in result:
                        self.console_output_tab.append("📌 检测到用户提供了Python代码建议")
                        # 可以在此添加特定的代码建议处理逻辑
                    
                    # 检查是否是修改命令行参数的建议
                    if "--dry-run" in result or "-n" in result or "参数" in result:
                        self.console_output_tab.append("📌 检测到用户建议修改命令行参数")
                        # 可以在此添加特定的参数修改建议处理逻辑
                except Exception as e:
                    print(f"处理用户自定义解决方案时出错: {str(e)}")
        
        # 保存用户的选择结果
        self._current_input_result = result
        
        # 关闭对话框
        dialog.accept()

    def _ensure_single_worker(self):
        """确保同一时间只有一个工作线程在运行"""
        if hasattr(self, 'worker') and self.worker and self.worker.isRunning():
            try:
                print("停止之前的工作线程...")
                
                # 先尝试使用更温和的方式终止线程
                self.worker.loading_state_changed.emit(False)  # 触发清理流程
                
                # 通知线程停止但不强制终止
                self.worker.quit()
                
                # 等待最多2秒 - 增加等待时间
                if not self.worker.wait(2000):
                    print("警告: 之前的工作线程没有及时响应")
                    # 再给它一些时间完成
                    if not self.worker.wait(2000):
                        print("错误: 工作线程仍未响应，将强制断开连接")
                        # 断开所有信号连接，避免过时的信号影响新线程
                        try:
                            self.worker.result_ready.disconnect()
                            self.worker.error_occurred.disconnect()
                            self.worker.console_output_ready.disconnect()
                            self.worker.task_plan_ready.disconnect()
                            self.worker.tool_usage_ready.disconnect()
                            self.worker.loading_state_changed.disconnect()
                            self.worker.user_input_needed.disconnect()
                        except Exception as disconnect_error:
                            print(f"断开信号连接时出错: {disconnect_error}")
                
                # 短暂延迟确保信号处理完成
                QTimer.singleShot(200, lambda: None)
                
                # 移除引用，让Qt对象自动清理
                print("安全移除工作线程引用")
                self.worker = None
                
            except Exception as e:
                print(f"清理之前的工作线程时出错: {e}")
                # 出错时也确保设置为None，但先断开连接
                try:
                    if self.worker:
                        self.worker.result_ready.disconnect()
                        self.worker.loading_state_changed.disconnect()
                except:
                    pass
                self.worker = None

    def init_right_panel(self):
        self.right_panel = QWidget()
        self.right_layout = QVBoxLayout(self.right_panel)
        
        # Tab widget for task plan, console output, and tool history
        self.tab_widget = QTabWidget()
        
        # Task Plan Tab
        self.task_plan_tab = QTextEdit()
        self.task_plan_tab.setReadOnly(True)
        self.task_plan_tab.setStyleSheet("""
            QTextEdit {
                border: 1px solid #E0E0E0;
                border-radius: 8px;
                background-color: #FAFAFA;
                padding: 10px;
                font-size: 16px;
                font-family: 'Consolas', 'Courier New', monospace;
            }
        """)
        self.tab_widget.addTab(self.task_plan_tab, "📝 任务计划")
        
        # Console Output Tab
        self.console_output_tab = QTextEdit()
        self.console_output_tab.setReadOnly(True)
        self.console_output_tab.setStyleSheet("""
            QTextEdit {
                border: 1px solid #E0E0E0;
                border-radius: 8px;
                background-color: #2B2B2B;
                color: #A9B7C6;
                padding: 10px;
                font-size: 16px;
                font-family: 'Consolas', 'Courier New', monospace;
            }
        """)
        self.tab_widget.addTab(self.console_output_tab, "🖥️ 控制台输出")
        
        # Tool History Tab
        tool_history_widget = QWidget()
        tool_history_layout = QVBoxLayout(tool_history_widget)
        
        self.tool_history = QListWidget()
        self.tool_history.setStyleSheet("""
            QListWidget {
                border: 1px solid #E0E0E0;
                border-radius: 8px;
                background-color: #FAFAFA;
                padding: 5px;
                font-size: 16px;
            }
            QListWidget::item {
                border-bottom: 1px solid #F0F0F0;
                padding: 5px;
            }
            QListWidget::item:selected {
                background-color: #E3F2FD;
                color: #1976D2;
            }
        """)
        tool_history_layout.addWidget(QLabel("最近使用的工具:"))
        tool_history_layout.addWidget(self.tool_history)
        
        # Add clear history button
        clear_history_btn = QPushButton("清除历史")
        clear_history_btn.clicked.connect(lambda: self.tool_history.clear())
        clear_history_btn.setStyleSheet("""
            QPushButton {
                background-color: #F44336;
                color: white;
                border: none;
                border-radius: 15px;
                padding: 5px 10px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #D32F2F;
            }
        """)
        tool_history_layout.addWidget(clear_history_btn)
        
        self.tab_widget.addTab(tool_history_widget, "🧰 工具历史")
        
        # Task Summary
        task_summary_group = QGroupBox("📊 任务摘要")
        task_summary_layout = QVBoxLayout(task_summary_group)
        
        self.task_summary = QTextEdit()
        self.task_summary.setReadOnly(True)
        self.task_summary.setStyleSheet("""
            QTextEdit {
                border: 1px solid #E0E0E0;
                border-radius: 8px;
                background-color: white;
                padding: 10px;
                font-size: 16px;
            }
        """)
        self.task_summary.setMaximumHeight(150)
        task_summary_layout.addWidget(self.task_summary)
        
        # Add components to right panel
        self.right_layout.addWidget(self.tab_widget, 7)  # Tab widget takes 70% of space
        self.right_layout.addWidget(task_summary_group, 3)  # Task summary takes 30% of space

    def update_loading_state(self, state):
        """更新加载状态，显示或隐藏加载动画"""
        try:
            if state:
                # 加载开始
                self.spinner.show()  # 显示加载动画
                
                # 如果悬浮球可见，则启动动画
                if hasattr(self, 'floating_ball') and self.floating_ball and self.floating_ball.isVisible():
                    self.start_floating_ball_animation()
                
                # 如果状态栏右侧没有加载状态文本，则添加
                if not hasattr(self, 'loading_label') or not self.loading_label:
                    self.loading_label = QLabel("正在处理请求... ")
                    self.loading_label.setStyleSheet("color: #FF9800; font-weight: bold;")
                    self.status_layout.addWidget(self.loading_label)
            else:
                # 加载结束 - 延迟清理，避免过早释放资源
                QTimer.singleShot(0, self._complete_loading_cleanup)
        except Exception as e:
            print(f"更新加载状态时出错: {str(e)}")
            
    def _complete_loading_cleanup(self):
        """完成加载后的清理工作 - 在主线程中执行"""
        try:
            # 隐藏加载动画
            if hasattr(self, 'spinner') and self.spinner:
                self.spinner.hide()
                
            # 停止悬浮球动画
            if hasattr(self, 'floating_ball') and self.floating_ball:
                self.stop_floating_ball_animation()
            
            # 隐藏加载状态文本
            if hasattr(self, 'loading_label') and self.loading_label:
                self.loading_label.hide()
                self.status_layout.removeWidget(self.loading_label)
                self.loading_label.deleteLater()
                self.loading_label = None
                
            # 清理可能存在的工作线程引用 - 更安全的方式
            if hasattr(self, 'worker') and self.worker:
                # 检查线程是否仍在运行
                if self.worker.isRunning():
                    # 如果仍在运行，推迟清理，让线程自行完成
                    print("工作线程仍在运行，推迟清理...")
                    # 1秒后再次尝试清理
                    QTimer.singleShot(1000, self._complete_loading_cleanup)
                    return
                else:
                    # 线程已经完成，安全移除引用
                    print("工作线程已完成，安全移除引用")
                    self.worker = None
                
            # 输出状态信息到控制台
            if hasattr(self, 'console_output_tab'):
                self.console_output_tab.append("\n✅ 任务已完成，界面已更新\n")
        except Exception as e:
            print(f"完成加载清理时出错: {str(e)}")

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
            f'<div style="color: #D32F2F; font-size: 16px;">'
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

    def show_from_floating_ball(self):
        # 停止悬浮球动画
        self.stop_floating_ball_animation()
        self.showNormal()
        self.activateWindow()

    def update_token_count(self, count):
        """更新token计数显示"""
        # 确保在主线程中执行
        if QThread.currentThread() != QApplication.instance().thread():
            # 如果在工作线程中调用，使用invokeMethod确保在主线程执行
            QMetaObject.invokeMethod(self, "update_token_count_main_thread", 
                                 Qt.QueuedConnection,
                                 Q_ARG(str, str(count)))
            return
        
        # 已在主线程中，直接执行
        self.update_token_count_main_thread(str(count))
    
    @pyqtSlot(str)
    def update_token_count_main_thread(self, count_str):
        """在主线程中安全地更新token计数"""
        try:
            self.token_label.setText(f"🔢 Tokens: {count_str}")
        except Exception as e:
            print(f"更新token计数时出错: {str(e)}")

    def update_tool_status(self, tool_name, tool_status=None):
        """更新工具状态"""
        self.current_tool = tool_name
        # 识别增强版工具并添加相应标记
        enhanced_tools = ["search_code", "locate_code_section", "get_code_context"]
        
        try:
            # 添加到工具历史
            if tool_name not in ["发生错误", "无", "token_count"]:
                tool_item = QListWidgetItem(f"🔧 {tool_name}")
                if tool_name in enhanced_tools:
                    tool_item.setText(f"🔧+ {tool_name}")
                self.tool_history.insertItem(0, tool_item)  # 新的工具添加到顶部
                
                # 限制历史数量
                if self.tool_history.count() > 15:
                    self.tool_history.takeItem(self.tool_history.count() - 1)
            
            # 处理token count特殊情况
            if tool_name == "token_count" and tool_status is not None:
                self.update_token_count(tool_status)
                return
                
            # 更新工具标签
            if tool_name not in ["发生错误", "无", "token_count"]:
                self.tool_label.setText(f"🔧 Tool: {tool_name}")
            
            # 只有在提供了status参数时才更新控制台
            if tool_status is not None:
                # 格式化状态信息并添加到控制台
                time_str = QDateTime.currentDateTime().toString("HH:mm:ss")
                status_msg = f"\n[{time_str}] 工具状态更新: {tool_name} - {tool_status}\n"
                
                cursor = self.console_output_tab.textCursor()
                cursor.movePosition(QTextCursor.End)
                
                # 设置文本格式
                format = QTextCharFormat()
                format.setForeground(QColor("#663399"))  # 使用紫色
                cursor.setCharFormat(format)
                
                # 插入文本
                cursor.insertText(status_msg)
                
                # 滚动到最新内容
                self.console_output_tab.setTextCursor(cursor)
                self.console_output_tab.ensureCursorVisible()
                
                # 切换到控制台输出选项卡
                self.tab_widget.setCurrentIndex(1)  # 任务计划是第2个选项卡（索引为1）
        except Exception as e:
            print(f"更新工具状态时出错: {str(e)}")

    @pyqtSlot(str)
    def update_task_summary_main_thread(self, summary):
        """在主线程中安全地更新任务摘要区域"""
        try:
            # 清空之前的内容
            self.task_summary.clear()
            
            # 设置富文本格式化摘要
            formatted_summary = ""
            
            # 解析摘要内容，添加颜色和格式
            if "==== 任务摘要 ====" in summary:
                lines = summary.split('\n')
                for line in lines:
                    if "==== 任务摘要 ====" in line or "=======================" in line:
                        # 标题行使用蓝色粗体
                        formatted_summary += f'<div style="color:#1976D2; font-weight:bold;">{line}</div>'
                    elif "任务:" in line or "开始时间:" in line or "进度:" in line:
                        # 基本信息使用绿色
                        formatted_summary += f'<div style="color:#2E7D32;">{line}</div>'
                    elif line.strip().startswith("- "):
                        # 列表项使用橙色
                        formatted_summary += f'<div style="color:#FF9800; margin-left:15px;">{line}</div>'
                    elif "已执行工具:" in line or "状态更新:" in line:
                        # 小标题使用紫色
                        formatted_summary += f'<div style="color:#6A1B9A; font-weight:bold; margin-top:5px;">{line}</div>'
                    else:
                        # 其他文本使用默认颜色
                        formatted_summary += f'<div>{line}</div>'
            else:
                # 如果不是标准格式，直接添加
                formatted_summary = f'<div>{summary}</div>'
            
            # 安全地设置富文本
            try:
                self.task_summary.setHtml(formatted_summary)
                # 滚动到顶部
                self.task_summary.moveCursor(QTextCursor.Start)
            except Exception as html_error:
                print(f"设置任务摘要HTML时出错: {str(html_error)}")
                # 尝试使用纯文本作为后备
                try:
                    self.task_summary.setPlainText(summary)
                except:
                    pass
            
        except Exception as e:
            print(f"更新任务摘要时出错: {str(e)}")

    def update_task_plan(self, plan):
        """更新任务计划区域"""
        # 确保在主线程中执行
        if QThread.currentThread() != QApplication.instance().thread():
            # 如果在工作线程中调用，使用invokeMethod确保在主线程执行
            QMetaObject.invokeMethod(self, "update_task_plan_main_thread", 
                                  Qt.QueuedConnection,
                                  Q_ARG(str, plan))
            return
        
        # 已在主线程中，直接执行
        self.update_task_plan_main_thread(plan)
            
    @pyqtSlot(str)
    def update_task_plan_main_thread(self, plan):
        """在主线程中安全地更新任务计划区域"""
        try:
            cursor = self.task_plan_tab.textCursor()
            cursor.movePosition(QTextCursor.End)
            
            # 格式化并添加计划文本
            time_str = QDateTime.currentDateTime().toString("HH:mm:ss")
            formatted_text = f"\n[{time_str}] 更新任务计划:\n{plan}\n"
            
            # 设置文本格式
            format = QTextCharFormat()
            format.setForeground(QColor("#0066CC"))  # 使用蓝色
            format.setFontWeight(QFont.Bold)
            cursor.setCharFormat(format)
            
            # 安全地修改文本文档
            try:
                # 插入文本
                cursor.insertText(formatted_text)
                
                # 滚动到最新内容
                self.task_plan_tab.setTextCursor(cursor)
                self.task_plan_tab.ensureCursorVisible()
            except Exception as text_error:
                print(f"插入任务计划时出错: {str(text_error)}")
                # 尝试使用更安全的方式添加文本
                try:
                    self.task_plan_tab.append(formatted_text)
                except:
                    pass
            
            # 切换到任务计划选项卡 - 避免刷新UI
            self.tab_widget.setCurrentIndex(0)  # 任务计划是第1个选项卡（索引为0）
        except Exception as e:
            self.log_error(f"更新任务计划时出错: {str(e)}")

    def update_console_output(self, output):
        """更新控制台输出区域"""
        # 确保在主线程中执行
        if QThread.currentThread() != QApplication.instance().thread():
            # 在工作线程中调用时，使用invokeMethod确保在主线程执行
            QMetaObject.invokeMethod(self, "update_console_output_main_thread", 
                                  Qt.QueuedConnection,
                                  Q_ARG(str, output))
            return
            
        # 已在主线程中，直接执行
        self.update_console_output_main_thread(output)
            
    @pyqtSlot(str)
    def update_console_output_main_thread(self, output):
        """在主线程中安全地更新控制台输出"""
        try:
            # 检查输出大小，防止过大的输出导致内存问题
            if len(output) > 10000:
                # 如果输出太大，截断并只显示前后部分
                truncated_output = output[:4000] + "\n\n... [输出过长，已截断] ...\n\n" + output[-4000:]
                output = truncated_output
            
            # 检查控制台文本是否已经太长，限制总大小
            current_text = self.console_output_tab.toPlainText()
            max_console_size = 5000  # 限制控制台文本最大字符数
            
            if len(current_text) > max_console_size:
                # 如果文本太长，完全清除
                self.console_output_tab.clear()
                self.console_output_tab.append("【已清空控制台输出，以防止内存问题】\n\n")
                
                # 在清除后强制垃圾回收
                import gc
                gc.collect()
            
            cursor = self.console_output_tab.textCursor()
            cursor.movePosition(QTextCursor.End)
            
            # 直接使用输出文本，不添加时间前缀
            formatted_text = output
            
            # 设置文本格式
            format = QTextCharFormat()
            format.setForeground(QColor("#006600"))  # 使用绿色
            cursor.setCharFormat(format)
            
            # 安全地修改文本文档
            try:
                # 插入文本
                cursor.insertText(formatted_text)
                
                # 滚动到最新内容
                self.console_output_tab.setTextCursor(cursor)
                self.console_output_tab.ensureCursorVisible()
            except Exception as text_error:
                print(f"插入文本时出错: {str(text_error)}", file=sys.stderr)
                # 尝试使用更安全的方式添加文本
                try:
                    self.console_output_tab.append(formatted_text)
                except:
                    pass
            
            # 切换到控制台输出选项卡 - 但不刷新UI
            self.tab_widget.setCurrentIndex(1)  # 控制台输出是第2个选项卡（索引为1）
            
        except Exception as e:
            print(f"更新控制台输出时出错: {str(e)}", file=sys.stderr)

    def log_error(self, msg):
        """安全地记录错误"""
        print(f"ERROR: {msg}", file=sys.stderr)
        # 也将错误发送到UI
        try:
            # 确保错误信息立即显示
            QApplication.processEvents()
        except Exception as e:
            print(f"记录错误时出错: {str(e)}", file=sys.stderr)
            
    def handle_response(self, response):
        # 确保在主线程中更新UI
        if QThread.currentThread() != QApplication.instance().thread():
            # 如果在工作线程中调用，使用invokeMethod确保在主线程执行
            QMetaObject.invokeMethod(self, "handle_response_main_thread", 
                                   Qt.QueuedConnection,
                                   Q_ARG(str, response))
        else:
            # 已在主线程中，直接执行
            self.handle_response_main_thread(response)
    
    @pyqtSlot(str)
    def handle_response_main_thread(self, response):
        """在主线程中安全地更新对话区域"""
        try:
            self.append_message("assistant", response)
        except Exception as e:
            print(f"更新对话时出错: {str(e)}")

    def append_message(self, role, content):
        """将消息添加到聊天显示区域"""
        # 确保在主线程中执行
        if QThread.currentThread() != QApplication.instance().thread():
            # 如果在工作线程中调用，通过信号槽确保在主线程执行
            QMetaObject.invokeMethod(self, "append_message", 
                                   Qt.QueuedConnection,
                                   Q_ARG(str, role),
                                   Q_ARG(str, content))
            return
            
        try:
            if role == "user":
                # 用户消息使用绿色，16px字体
                self.chat_display.append(f'<div style="color: #2E7D32; font-size: 16px;"><b>👤 You:</b> {content}</div>')
            else:
                # 助手消息使用蓝色，16px字体
                # 在主线程中安全转换markdown
                try:
                    html = markdown.markdown(content)
                except Exception as md_error:
                    print(f"Markdown转换出错: {str(md_error)}")
                    html = content  # 转换失败时使用原始文本
                    
                self.chat_display.append(f'<div style="color: #1976D2; font-size: 16px;"><b>🤖 Assistant:</b> {html}</div>')
            
            # 滚动到最新内容
            self.chat_display.moveCursor(QTextCursor.End)
        except Exception as e:
            print(f"添加消息到聊天区域时出错: {str(e)}")

    def send_message(self):
        user_input = self.input_field.text().strip()
        if not user_input:
            return
            
        # Clear input field
        self.input_field.clear()
        
        # Add user message to chat
        self.append_message("user", user_input)
        
        # 停止并清理之前的工作线程（如果存在）
        self._ensure_single_worker()
        
        # Create and start worker thread
        self.worker = WorkerThread(user_input, APIBridge, self) 
        self.worker.result_ready.connect(self.handle_response)
        self.worker.error_occurred.connect(self.handle_error)
        self.worker.console_output_ready.connect(self.update_console_output)
        self.worker.task_plan_ready.connect(self.update_task_plan)
        self.worker.tool_usage_ready.connect(self.update_tool_status)
        self.worker.loading_state_changed.connect(self.update_loading_state)
        self.worker.user_input_needed.connect(self.handle_secondary_input_needed)
        self.worker.start()

    def update_taskbar_visibility(self, show_in_taskbar):
        """更新窗口在任务栏中的可见性"""
        try:
            if show_in_taskbar:
                # 确保窗口在任务栏中显示
                self.setWindowFlags(Qt.Window)
            else:
                # 从任务栏中隐藏窗口
                self.setWindowFlags(Qt.Tool)
            
            # 应用更改后需要重新显示窗口（如果窗口当前可见）
            was_visible = self.isVisible()
            if was_visible:
                self.show()
                
            # 确保窗口图标正确设置
            if hasattr(self, 'robot_icon'):
                self.setWindowIcon(self.robot_icon)
        except Exception as e:
            print(f"更新任务栏可见性时出错: {str(e)}")

    def update_time(self):
        """更新时间标签"""
        try:
            current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            self.time_label.setText(current_time)
        except Exception as e:
            print(f"更新时间时出错: {str(e)}")

    def update_tool_status(self, tool_name, tool_status=None):
        """更新工具状态"""
        # 确保在主线程中执行
        if QThread.currentThread() != QApplication.instance().thread():
            # 如果在工作线程中调用，使用invokeMethod确保在主线程执行
            QMetaObject.invokeMethod(self, "update_tool_status_main_thread", 
                                  Qt.QueuedConnection,
                                  Q_ARG(str, tool_name),
                                  Q_ARG(object, tool_status))
            return
        
        # 已在主线程中，直接执行
        self.update_tool_status_main_thread(tool_name, tool_status)
    
    @pyqtSlot(str, object)
    def update_tool_status_main_thread(self, tool_name, tool_status=None):
        """在主线程中安全地更新工具状态"""
        try:
            self.current_tool = tool_name
            # 识别增强版工具并添加相应标记
            enhanced_tools = ["search_code", "locate_code_section", "get_code_context"]
            
            # 添加到工具历史
            if tool_name not in ["发生错误", "无", "token_count"]:
                try:
                    tool_item = QListWidgetItem(f"🔧 {tool_name}")
                    if tool_name in enhanced_tools:
                        tool_item.setText(f"🔧+ {tool_name}")
                    self.tool_history.insertItem(0, tool_item)  # 新的工具添加到顶部
                    
                    # 限制历史数量
                    if self.tool_history.count() > 15:
                        self.tool_history.takeItem(self.tool_history.count() - 1)
                except Exception as history_error:
                    print(f"更新工具历史时出错: {str(history_error)}")
            
            # 处理token count特殊情况
            if tool_name == "token_count" and tool_status is not None:
                self.update_token_count(tool_status)
                return
                
            # 更新工具标签
            if tool_name not in ["发生错误", "无", "token_count"]:
                try:
                    self.tool_label.setText(f"🔧 Tool: {tool_name}")
                except Exception as label_error:
                    print(f"更新工具标签时出错: {str(label_error)}")
            
            # 只有在提供了status参数时才更新控制台
            if tool_status is not None:
                try:
                    # 格式化状态信息并添加到控制台
                    time_str = QDateTime.currentDateTime().toString("HH:mm:ss")
                    status_msg = f"\n[{time_str}] 工具状态更新: {tool_name} - {tool_status}\n"
                    
                    # 使用更安全的方式添加到控制台
                    self.console_output_tab.append(f"<span style='color:#663399;'>{status_msg}</span>")
                    
                    # 切换到控制台输出选项卡
                    self.tab_widget.setCurrentIndex(1)  # 控制台输出是第2个选项卡（索引为1）
                except Exception as console_error:
                    print(f"更新控制台输出时出错: {str(console_error)}")
        except Exception as e:
            print(f"更新工具状态时出错: {str(e)}")

    def update_task_summary(self, summary):
        """更新任务摘要区域"""
        # 确保在主线程中执行
        if QThread.currentThread() != QApplication.instance().thread():
            # 如果在工作线程中调用，使用invokeMethod确保在主线程执行
            QMetaObject.invokeMethod(self, "update_task_summary_main_thread", 
                                 Qt.QueuedConnection,
                                 Q_ARG(str, summary))
            return
        
        # 已在主线程中，直接执行
        self.update_task_summary_main_thread(summary)

# 检查是否禁用过度确认
DISABLE_EXCESSIVE_CONFIRMATION = os.getenv("DISABLE_EXCESSIVE_CONFIRMATION", "false").lower() == "true"
# 用于防止短时间内多次弹出确认窗口
CONFIRMATION_COOLDOWN = 10  # 秒
last_confirmation_time = 0

def main():
    # Load environment variables
    load_dotenv()
    
    # 添加异常恢复日志
    recovery_log_path = "recovery_log.txt"
    try:
        with open(recovery_log_path, "a", encoding="utf-8") as f:
            f.write(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 程序启动\n")
    except:
        pass
        
    try:
        # 设置异常处理器
        def handle_exception(exc_type, exc_value, exc_traceback):
            print("未捕获的异常:", exc_type, exc_value)
            import traceback
            traceback.print_exception(exc_type, exc_value, exc_traceback)
            
            # 保存错误到日志
            try:
                with open("error_log.txt", "a", encoding="utf-8") as f:
                    f.write(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 未捕获的异常:\n")
                    traceback.print_exception(exc_type, exc_value, exc_traceback, file=f)
            except:
                pass
            
            # 记录应用崩溃以便重启
            try:
                with open(recovery_log_path, "a", encoding="utf-8") as f:
                    f.write(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 程序崩溃: {exc_type.__name__}: {exc_value}\n")
            except:
                pass
                
            # 如果GUI已经初始化，显示错误对话框
            if 'app' in locals():
                try:
                    error_msg = str(exc_value)
                    QMessageBox.critical(None, "错误", f"程序发生错误:\n{error_msg}\n\n请查看错误日志获取详细信息。")
                except:
                    pass
        
        # 设置全局异常处理器
        sys.excepthook = handle_exception
        
        # 忽略特定的警告
        warnings.filterwarnings("ignore", category=DeprecationWarning, module="sip")
        # 忽略DirectWrite字体错误
        warnings.filterwarnings("ignore", category=UserWarning, message=".*DirectWrite.*")
        
        # 防止Qt内部事件循环崩溃
        QApplication.setAttribute(Qt.AA_UseDesktopOpenGL, True)
        QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
        QApplication.setAttribute(Qt.AA_ShareOpenGLContexts, True)
        
        # Create QApplication instance
        app = QApplication(sys.argv)
        
        # 设置应用程序信息
        app.setApplicationName("DeepSeek PC Manager")
        app.setApplicationVersion("1.0.0")
        app.setOrganizationName("DeepSeek")
        app.setOrganizationDomain("deepseek.com")
        
        # 设置默认字体，使用系统默认字体并提供回退选项
        default_font = app.font()
        font_families = ["Microsoft YaHei UI", "Microsoft YaHei", "SimHei", "Arial", "Helvetica", "sans-serif"]
        
        # 逐个尝试字体，直到找到可用的
        for font_family in font_families:
            try:
                test_font = QFont(font_family)
                if test_font.exactMatch():
                    default_font.setFamily(font_family)
                    print(f"使用字体: {font_family}")
                    break
            except:
                continue
        
        app.setFont(default_font)
        
        # 添加崩溃恢复检测
        try:
            with open(recovery_log_path, "r", encoding="utf-8") as f:
                last_lines = f.readlines()[-3:]  # 读取最后3行
                crash_detected = any("程序崩溃" in line for line in last_lines)
                
                if crash_detected:
                    print("检测到上次程序异常退出，正在启动恢复模式...")
                    # 向用户显示提示
                    QMessageBox.information(None, "程序恢复", 
                        "检测到上次程序异常退出，已启动恢复模式。\n如果遇到问题，请尝试清除配置文件后重启。")
            
        except:
            pass
        
        # Create main window with improved error handling
        try:
            window = MainWindow()
            window.show()
        except Exception as window_error:
            print(f"创建主窗口失败: {window_error}")
            QMessageBox.critical(None, "启动错误", f"创建主窗口失败:\n{window_error}")
            return 1
        
        # Run application with exception handling
        try:
            return app.exec_()
        except Exception as exec_error:
            print(f"事件循环执行出错: {exec_error}")
            return 1
            
    except Exception as e:
        print(f"程序启动错误: {e}")
        # 保存错误到日志文件
        try:
            with open("error_log.txt", "a", encoding="utf-8") as f:
                import traceback
                f.write(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 程序启动错误:\n")
                f.write(traceback.format_exc())
                f.write("\n")
        except:
            pass
        
        # 显示错误对话框
        if 'app' in locals():
            QMessageBox.critical(None, "启动错误", f"程序启动时出错:\n{e}\n请查看错误日志获取详细信息。")
        return 1

if __name__ == "__main__":
    # 添加自动重启功能
    while True:
        try:
            exit_code = main()
            
            # 记录程序正常退出
            try:
                with open("recovery_log.txt", "a", encoding="utf-8") as f:
                    f.write(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 程序退出，退出代码: {exit_code}\n")
            except:
                pass
                
            # 如果是正常退出(用户手动关闭)，则不重启
            if exit_code == 0:
                print("程序正常退出")
                sys.exit(exit_code)
            # 如果是带退出码的退出，则尝试重启
            elif exit_code > 0:
                # 重启前等待一小段时间
                print(f"程序异常退出(代码:{exit_code})，将在3秒后重启...")
                time.sleep(3)
                
                # 清理资源（不要强制垃圾回收）
                continue
            # 如果是其他情况，可能是用户意外关闭窗口
            else:
                print("程序意外退出，但不重启")
                sys.exit(0)
            
        except Exception as e:
            print(f"重启循环中发生错误: {e}")
            # 记录错误
            try:
                with open("error_log.txt", "a", encoding="utf-8") as f:
                    import traceback
                    f.write(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 重启循环错误:\n")
                    f.write(traceback.format_exc())
            except:
                pass
            
            # 避免无限快速重启
            time.sleep(5)
            
            # 如果连续重启失败次数过多，则退出
            try:
                restart_count_file = "restart_count.txt"
                restart_count = 1
                
                if os.path.exists(restart_count_file):
                    with open(restart_count_file, "r") as f:
                        try:
                            restart_count = int(f.read().strip()) + 1
                        except:
                            restart_count = 1
                
                with open(restart_count_file, "w") as f:
                    f.write(str(restart_count))
                
                # 如果重启次数超过5次，则退出
                if restart_count > 5:
                    print("连续重启失败次数过多，程序将退出")
                    with open("recovery_log.txt", "a", encoding="utf-8") as f:
                        f.write(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 连续重启失败次数过多，程序退出\n")
                    sys.exit(1)
            except:
                pass