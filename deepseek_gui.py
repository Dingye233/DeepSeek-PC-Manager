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
                           QListWidgetItem, QListWidget, QGroupBox, QComboBox)
from PyQt5.QtCore import Qt, QTimer, QThread, pyqtSignal, QPropertyAnimation, QEasingCurve, QMetaObject, QDateTime, QSettings
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
                    # 尝试从消息历史中找出最后一条AI消息
                    try:
                        from deepseekAPI import messages
                        # 先记录一下计划使用的消息，以防后面崩溃
                        self.last_ai_message = "需要您的输入"
                        
                        for msg in reversed(messages):
                            if msg.get("role") == "assistant" and msg.get("content"):
                                self.last_ai_message = msg.get("content")
                                break
                        
                        # 确保AI消息不是空的
                        if not self.last_ai_message or not self.last_ai_message.strip():
                            self.last_ai_message = "AI助手需要您的输入"
                        
                        # 将AI最后的消息发送到UI
                        self.safe_emit(self.result_ready, self.last_ai_message)
                        # 确保UI更新
                        QApplication.processEvents()
                        time.sleep(0.1)  # 短暂等待确保消息显示
                    except Exception as e:
                        self.log_error(f"获取AI消息时出错 (这不会影响功能): {str(e)}")
                
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
                            self.log_error("无法获取主窗口引用，用户输入将失败")
                            return "继续执行"  # 默认继续
                            
                        main_window._current_input_event = input_event
                        main_window._current_input_result = None
                        
                        # 等待用户输入完成，增加超时处理
                        try:
                            loop.run_until_complete(asyncio.wait_for(input_event.wait(), timeout + 5))
                        except asyncio.TimeoutError:
                            self.log_error("等待用户输入超时")
                            return "继续执行"  # 超时默认继续
                        
                        # 获取结果
                        result = main_window._current_input_result
                        
                        # 清理
                        main_window._current_input_event = None
                        main_window._current_input_result = None
                        
                        # 如果结果为空，返回默认值
                        if result is None:
                            return "继续执行"
                            
                        return result
                    except Exception as e:
                        self.log_error(f"处理用户输入时出错: {str(e)}")
                        return "继续执行"  # 出错时默认继续
                except Exception as e:
                    self.log_error(f"用户输入回调发生异常: {str(e)}")
                    return "继续执行"  # 如果出现任何错误，返回默认值
            
            # 设置回调，使用异常处理
            try:
                APIBridge.set_tool_output_callback(tool_output_callback)
                APIBridge.set_task_plan_callback(task_plan_callback)
                
                # 设置用户输入回调
                from input_utils import register_input_callback
                register_input_callback(input_callback)
            except Exception as e:
                self.log_error(f"设置回调函数时出错: {str(e)}")
            
            try:
                # 使用 APIBridge 执行任务
                result = loop.run_until_complete(APIBridge.execute_task(self.input_text))
                
                # 获取并发送当前token数量
                try:
                    from api_wrapper import APIBridge as ExternalAPIBridge
                    token_count = ExternalAPIBridge.get_token_count()
                    self.safe_emit(self.tool_usage_ready, "token_count", str(token_count))
                except Exception as e:
                    self.log_error(f"获取token计数时出错: {str(e)}")
                
                # 获取并发送任务计划和摘要
                try:
                    task_plan = APIBridge.get_task_plan()
                    if task_plan and task_plan != "暂无任务计划信息":
                        self.safe_emit(self.task_plan_ready, task_plan)
                except Exception as e:
                    self.log_error(f"获取任务计划时出错: {str(e)}")
                
                # 获取并发送最新的工具执行结果
                try:
                    tool_output = APIBridge.get_latest_tool_output()
                    if tool_output:
                        self.safe_emit(self.console_output_ready, tool_output)
                        # 通知工具输出状态更新了
                        self.safe_emit(self.tool_usage_ready, "工具输出", "已更新")
                except Exception as e:
                    self.log_error(f"获取工具输出时出错: {str(e)}")
                
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
                try:
                    APIBridge.set_tool_output_callback(None)
                except:
                    pass
                    
                try:
                    APIBridge.set_task_plan_callback(None)
                except:
                    pass
                
                # 注销用户输入回调
                try:
                    from input_utils import register_input_callback
                    register_input_callback(None)
                except:
                    pass
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
                    
    async def _set_event_async(self):
        """安全地设置事件"""
        if self._current_input_event is not None:
            self._current_input_event.set()
        
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        
        # 设置窗口标题和大小
        self.setWindowTitle("DeepSeek PC Manager")
        self.resize(1200, 800)
        
        # 初始化成员变量
        self._current_input_event = None
        self._current_input_result = None
        self.current_tool = "无"
        self.worker = None
        
        # 初始化UI
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
        # 主布局为水平分割器
        self.main_splitter = QSplitter(Qt.Horizontal)
        self.setCentralWidget(self.main_splitter)
        
        # 初始化左右面板
        self.init_left_panel()
        self.init_right_panel()
        
        # 添加面板到分割器
        self.main_splitter.addWidget(self.left_panel)
        self.main_splitter.addWidget(self.right_panel)
        
        # 设置初始分割比例 (70% 左面板, 30% 右面板)
        self.main_splitter.setSizes([int(self.width() * 0.7), int(self.width() * 0.3)])
        
        # 隐藏加载动画
        self.spinner.hide()
        
        # 创建菜单栏
        self.create_menu_bar()
    
    def create_menu_bar(self):
        """创建菜单栏"""
        menubar = self.menuBar()
        
        # 文件菜单
        file_menu = menubar.addMenu('文件')
        
        # 添加设置选项
        settings_action = QAction('设置', self)
        settings_action.triggered.connect(self.show_settings)
        file_menu.addAction(settings_action)
        
        file_menu.addSeparator()
        
        # 添加退出选项
        exit_action = QAction('退出', self)
        exit_action.triggered.connect(self.quit_application)
        file_menu.addAction(exit_action)
        
        # 帮助菜单
        help_menu = menubar.addMenu('帮助')
        
        # 添加关于选项
        about_action = QAction('关于', self)
        about_action.triggered.connect(self.show_about)
        help_menu.addAction(about_action)
        
        # 添加帮助文档选项
        help_doc_action = QAction('帮助文档', self)
        help_doc_action.triggered.connect(self.show_help)
        help_menu.addAction(help_doc_action)
    
    def show_settings(self):
        """显示设置对话框"""
        settings_dialog = QDialog(self)
        settings_dialog.setWindowTitle("设置")
        settings_dialog.setMinimumWidth(500)
        
        layout = QVBoxLayout(settings_dialog)
        
        # 添加设置选项
        settings_group = QGroupBox("基本设置")
        settings_layout = QVBoxLayout(settings_group)
        
        # API设置
        api_layout = QHBoxLayout()
        api_label = QLabel("API密钥:")
        api_input = QLineEdit()
        api_input.setEchoMode(QLineEdit.Password)
        api_layout.addWidget(api_label)
        api_layout.addWidget(api_input)
        settings_layout.addLayout(api_layout)
        
        # 主题设置
        theme_layout = QHBoxLayout()
        theme_label = QLabel("主题:")
        theme_combo = QComboBox()
        theme_combo.addItems(["默认", "暗色", "浅色"])
        theme_layout.addWidget(theme_label)
        theme_layout.addWidget(theme_combo)
        settings_layout.addLayout(theme_layout)
        
        # 语言设置
        lang_layout = QHBoxLayout()
        lang_label = QLabel("语言:")
        lang_combo = QComboBox()
        lang_combo.addItems(["简体中文", "English"])
        lang_layout.addWidget(lang_label)
        lang_layout.addWidget(lang_combo)
        settings_layout.addLayout(lang_layout)
        
        layout.addWidget(settings_group)
        
        # 添加按钮
        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(settings_dialog.accept)
        button_box.rejected.connect(settings_dialog.reject)
        layout.addWidget(button_box)
        
        settings_dialog.exec_()
        
    def show_about(self):
        """显示关于对话框"""
        about_text = """
        <h2>DeepSeek PC Manager</h2>
        <p>版本: 1.0.0</p>
        <p>一个智能的PC管理助手，帮助您更高效地管理计算机。</p>
        <p>© 2023 DeepSeek Team</p>
        """
        
        QMessageBox.about(self, "关于", about_text)
        
    def show_help(self):
        """显示帮助文档"""
        help_dialog = QDialog(self)
        help_dialog.setWindowTitle("帮助文档")
        help_dialog.setMinimumSize(800, 600)
        
        layout = QVBoxLayout(help_dialog)
        
        # 创建帮助内容
        help_text = QTextEdit()
        help_text.setReadOnly(True)
        help_text.setHtml("""
        <h1>DeepSeek PC Manager 帮助文档</h1>
        
        <h2>基本功能</h2>
        <p>DeepSeek PC Manager 是一个智能的PC管理助手，可以帮助您：</p>
        <ul>
            <li>系统优化</li>
            <li>软件管理</li>
            <li>文件整理</li>
            <li>性能监控</li>
        </ul>
        
        <h2>使用方法</h2>
        <p>在输入框中输入您的需求，AI助手会帮您完成任务。</p>
        
        <h2>常见问题</h2>
        <p><b>Q: 如何开始使用？</b></p>
        <p>A: 直接在输入框中输入您的需求即可。</p>
        
        <p><b>Q: 支持哪些功能？</b></p>
        <p>A: 支持系统优化、软件管理、文件整理、性能监控等多种功能。</p>
        """)
        
        layout.addWidget(help_text)
        
        # 添加关闭按钮
        close_button = QPushButton("关闭")
        close_button.clicked.connect(help_dialog.accept)
        layout.addWidget(close_button)
        
        help_dialog.exec_()
    
    def update_time(self):
        """更新时间标签"""
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.time_label.setText("🕒 " + current_time)
    
    def init_tray_icon(self):
        """初始化系统托盘图标"""
        try:
            self.tray_icon = QSystemTrayIcon(self)
            
            # 使用简单的默认图标
            app_icon = QIcon()
            pixmap = QPixmap(32, 32)
            pixmap.fill(QColor('#1976D2'))
            app_icon.addPixmap(pixmap)
            self.tray_icon.setIcon(app_icon)
            
            # 创建托盘菜单
            tray_menu = QMenu()
            
            # 添加显示操作
            show_action = QAction("显示", self)
            show_action.triggered.connect(self.show_from_tray)
            tray_menu.addAction(show_action)
            
            # 添加退出操作
            quit_action = QAction("退出", self)
            quit_action.triggered.connect(self.quit_application)
            tray_menu.addAction(quit_action)
            
            # 设置托盘菜单
            self.tray_icon.setContextMenu(tray_menu)
            
            # 连接托盘图标激活信号
            self.tray_icon.activated.connect(self.tray_icon_activated)
            
            # 显示托盘图标
            self.tray_icon.show()
        except Exception as e:
            print(f"初始化系统托盘时出错: {str(e)}")
    
    def init_floating_ball(self):
        """初始化浮动球"""
        try:
            self.floating_ball = QWidget(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
            self.floating_ball.setFixedSize(60, 60)
            # 设置窗口背景透明
            self.floating_ball.setAttribute(Qt.WA_TranslucentBackground)
            
            layout = QVBoxLayout(self.floating_ball)
            layout.setContentsMargins(0, 0, 0, 0)
            
            # 使用机器人emoji的标签
            label = QLabel("🤖")
            label.setStyleSheet("""
                background-color: transparent;
                color: white;
                font-size: 30px;
                font-weight: bold;
            """)
            label.setAlignment(Qt.AlignCenter)
            layout.addWidget(label)
            
            # 设置圆形窗口样式
            self.floating_ball.setStyleSheet("""
                QWidget {
                    background-color: transparent;
                }
            """)
            
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
            
            # 初始隐藏浮动球
            self.floating_ball.hide()
            
        except Exception as e:
            print(f"初始化浮动球时出错: {str(e)}")
            self.floating_ball = None
            
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
        if event.type() == event.WindowStateChange:
            if self.windowState() & Qt.WindowMinimized:
                self.hide()
                # 显示悬浮球在上次保存的位置
                self.floating_ball.show()
                # 不需要移动到当前窗口位置
                # self.floating_ball.move(self.x(), self.y())

    def handle_secondary_input_needed(self, input_event_data):
        """处理需要用户二次输入的情况，例如工具执行失败需要用户选择继续或终止"""
        try:
            # 创建一个自定义dialog
            dialog = QDialog(self)
            dialog.setWindowTitle("需要您的输入")
            layout = QVBoxLayout(dialog)
            
            # 显示解释说明
            explanation = input_event_data.get('explanation', '工具执行需要您的输入')
            explanation_label = QLabel(explanation)
            explanation_label.setWordWrap(True)
            explanation_label.setStyleSheet("padding: 10px; font-size: 14px;")
            layout.addWidget(explanation_label)
            
            # 添加选项
            options = input_event_data.get('options', [])
            if options:
                options_group = QGroupBox("请选择:")
                options_layout = QVBoxLayout(options_group)
                
                for i, option in enumerate(options):
                    option_btn = QPushButton(f"{i+1}. {option}")
                    option_btn.clicked.connect(lambda _, idx=i+1: self.handle_option_selected(dialog, str(idx)))
                    options_layout.addWidget(option_btn)
                
                layout.addWidget(options_group)
            
            # 输入框和确认按钮
            input_layout = QHBoxLayout()
            input_field = QLineEdit()
            input_field.setPlaceholderText("在此输入您的回应...")
            input_layout.addWidget(input_field, 3)
            
            confirm_btn = QPushButton("确认")
            confirm_btn.clicked.connect(lambda: self.handle_option_selected(dialog, input_field.text()))
            input_layout.addWidget(confirm_btn, 1)
            
            layout.addLayout(input_layout)
            
            # 添加取消按钮
            cancel_btn = QPushButton("取消")
            cancel_btn.clicked.connect(dialog.reject)
            layout.addWidget(cancel_btn)
            
            # 保存当前的事件数据
            self._current_input_event = dialog
            self._current_input_result = None
            
            # 显示消息框并等待用户选择
            dialog.setModal(True)
            
            # 在请求用户输入前，先发送解释信息到聊天窗口
            if 'explanation_msg' in input_event_data and input_event_data['explanation_msg']:
                self.append_message("assistant", input_event_data['explanation_msg'])
            
            # 显示对话框等待用户输入
            if dialog.exec_():
                return self._current_input_result
            else:
                return "2"  # 默认选择终止
                
        except Exception as e:
            self.log_error(f"处理二次输入时出错: {str(e)}")
            return "2"  # 出错时默认终止
            
    def handle_option_selected(self, dialog, result):
        """处理用户选择的选项"""
        self._current_input_result = result
        dialog.accept()

    def _ensure_single_worker(self):
        """确保同一时间只有一个工作线程在运行"""
        if hasattr(self, 'worker') and self.worker and self.worker.isRunning():
            try:
                print("停止之前的工作线程...")
                self.worker.quit()
                # 等待最多2秒
                if not self.worker.wait(2000):
                    print("强制终止之前的工作线程")
                    self.worker.terminate()
                self.worker = None
            except Exception as e:
                print(f"清理之前的工作线程时出错: {e}")

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
                font-size: 13px;
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
                font-size: 13px;
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
                font-size: 13px;
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
                font-size: 13px;
            }
        """)
        self.task_summary.setMaximumHeight(150)
        task_summary_layout.addWidget(self.task_summary)
        
        # Add components to right panel
        self.right_layout.addWidget(self.tab_widget, 7)  # Tab widget takes 70% of space
        self.right_layout.addWidget(task_summary_group, 3)  # Task summary takes 30% of space

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
        
    def init_left_panel(self):
        self.left_panel = QWidget()
        self.left_layout = QVBoxLayout(self.left_panel)
        
        # Status bar with token count, tool status, and time
        self.status_bar = QWidget()
        self.status_layout = QHBoxLayout(self.status_bar)
        self.status_layout.setContentsMargins(5, 5, 5, 5)
        
        # Token counter
        self.token_label = QLabel("🔢 Tokens: 0")
        self.token_label.setStyleSheet("color: #1976D2; font-weight: bold;")
        self.status_layout.addWidget(self.token_label)
        
        # Tool indicator
        self.tool_label = QLabel("🔧 Tool: None")
        self.tool_label.setStyleSheet("color: #9E9E9E;")
        self.status_layout.addWidget(self.tool_label)
        
        # Current time
        self.time_label = QLabel("🕒 " + datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        self.time_label.setStyleSheet("color: #757575;")
        self.status_layout.addWidget(self.time_label)
        
        # Loading spinner (hidden initially)
        self.spinner = LoadingSpinner()
        self.status_layout.addWidget(self.spinner)
        
        self.left_layout.addWidget(self.status_bar)
        
        # Chat display area
        self.chat_display = QTextEdit()
        self.chat_display.setReadOnly(True)
        self.chat_display.setAcceptRichText(True)
        self.chat_display.setStyleSheet("""
            QTextEdit {
                border: 1px solid #E0E0E0;
                border-radius: 8px;
                background-color: white;
                padding: 10px;
                font-size: 14px;
            }
        """)
        self.left_layout.addWidget(self.chat_display, 1)
        
        # Input area container
        input_container = QWidget()
        input_layout = QHBoxLayout(input_container)
        input_layout.setContentsMargins(0, 10, 0, 5)
        
        # Message input field
        self.input_field = QLineEdit()
        self.input_field.setPlaceholderText("💬 Type your message here...")
        self.input_field.returnPressed.connect(self.send_message)
        self.input_field.setStyleSheet("""
            QLineEdit {
                border: 1px solid #E0E0E0;
                border-radius: 20px;
                padding: 10px 15px;
                font-size: 14px;
                background-color: white;
            }
            QLineEdit:focus {
                border: 1px solid #4CAF50;
            }
        """)
        input_layout.addWidget(self.input_field)
        
        # Send button
        self.send_button = QPushButton("Send 📤")
        self.send_button.setFixedWidth(100)
        self.send_button.clicked.connect(self.send_message)
        self.send_button.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                border: none;
                border-radius: 20px;
                padding: 10px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
            QPushButton:pressed {
                background-color: #388E3C;
            }
        """)
        input_layout.addWidget(self.send_button)
        
        self.left_layout.addWidget(input_container)
        
    def update_token_count(self, count):
        self.token_label.setText(f"🔢 Tokens: {count}")

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

    def update_task_summary(self, summary):
        self.task_summary.append(summary)

    def update_task_plan(self, plan):
        """更新任务计划区域"""
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
            
            # 插入文本
            cursor.insertText(formatted_text)
            
            # 滚动到最新内容
            self.task_plan_tab.setTextCursor(cursor)
            self.task_plan_tab.ensureCursorVisible()
            
            # 强制立即更新UI
            self.task_plan_tab.repaint()
            QApplication.processEvents()
            
            # 切换到任务计划选项卡
            self.tab_widget.setCurrentIndex(0)  # 任务计划是第1个选项卡（索引为0）
        except Exception as e:
            self.log_error(f"更新任务计划时出错: {str(e)}")

    def update_console_output(self, output):
        """更新控制台输出区域"""
        try:
            cursor = self.console_output_tab.textCursor()
            cursor.movePosition(QTextCursor.End)
            
            # 格式化并添加输出文本
            time_str = QDateTime.currentDateTime().toString("HH:mm:ss")
            formatted_text = f"\n[{time_str}] 工具输出:\n{output}\n"
            
            # 设置文本格式
            format = QTextCharFormat()
            format.setForeground(QColor("#006600"))  # 使用绿色
            cursor.setCharFormat(format)
            
            # 插入文本
            cursor.insertText(formatted_text)
            
            # 滚动到最新内容
            self.console_output_tab.setTextCursor(cursor)
            self.console_output_tab.ensureCursorVisible()
            
            # 强制立即更新UI
            self.console_output_tab.repaint()
            QApplication.processEvents()
            
            # 切换到控制台输出选项卡
            self.tab_widget.setCurrentIndex(1)  # 控制台输出是第2个选项卡（索引为1）
        except Exception as e:
            self.log_error(f"更新控制台输出时出错: {str(e)}")
            
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
        self.append_message("assistant", response)

    def append_message(self, role, content):
        if role == "user":
            # A user message using green, 14px font size
            self.chat_display.append(f'<div style="color: #2E7D32; font-size: 14px;"><b>👤 You:</b> {content}</div>')
        else:
            # Assistant message using blue, 14px font size
            html = markdown.markdown(content)
            self.chat_display.append(f'<div style="color: #1976D2; font-size: 14px;"><b>🤖 Assistant:</b> {html}</div>')
        self.chat_display.moveCursor(QTextCursor.End)

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

# 检查是否禁用过度确认
DISABLE_EXCESSIVE_CONFIRMATION = os.getenv("DISABLE_EXCESSIVE_CONFIRMATION", "false").lower() == "true"
# 用于防止短时间内多次弹出确认窗口
CONFIRMATION_COOLDOWN = 10  # 秒
last_confirmation_time = 0

def main():
    # Load environment variables
    load_dotenv()
    
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
        
        # Create QApplication instance
        app = QApplication(sys.argv)
        
        # 设置应用程序信息
        app.setApplicationName("DeepSeek PC Manager")
        app.setApplicationVersion("1.0.0")
        app.setOrganizationName("DeepSeek")
        app.setOrganizationDomain("deepseek.com")
        
        # 设置默认字体
        default_font = app.font()
        default_font.setFamily("Microsoft YaHei UI")
        app.setFont(default_font)
        
        # Create main window
        window = MainWindow()
        window.show()
        
        # Run application
        sys.exit(app.exec_())
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
        sys.exit(1)

if __name__ == "__main__":
    main() 