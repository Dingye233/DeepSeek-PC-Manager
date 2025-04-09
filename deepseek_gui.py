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
            
            # 注册用户输入回调函数
            def input_callback(prompt, timeout=60, error_message=None):
                # 发射信号到主线程以显示对话框
                self.safe_emit(self.user_input_needed, prompt, timeout, error_message)
                
                # 创建一个事件循环等待结果
                input_event = asyncio.Event()
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
            
            # 设置回调
            APIBridge.set_tool_output_callback(tool_output_callback)
            APIBridge.set_task_plan_callback(task_plan_callback)
            
            # 设置用户输入回调
            from input_utils import register_input_callback
            register_input_callback(input_callback)
            
            # 使用 APIBridge 执行任务
            result = loop.run_until_complete(APIBridge.execute_task(self.input_text))
            
            # 获取并发送当前token数量
            token_count = APIBridge.get_token_count()
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
            # 捕获意外错误
            error_msg = f"运行错误: {str(e)}"
            self.log_error(error_msg)
            self.safe_emit(self.error_occurred, error_msg)
            
        finally:
            # 清除回调
            APIBridge.set_tool_output_callback(None)
            APIBridge.set_task_plan_callback(None)
            
            # 注销用户输入回调
            from input_utils import register_input_callback
            register_input_callback(None)
            
            # 隐藏加载动画
            self.safe_emit(self.loading_state_changed, False)
            
            # 确保清理事件循环
            if loop and not loop.is_closed():
                loop.close()

class FloatingBall(QWidget):
    clicked = pyqtSignal()
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        # 增加窗口大小以确保内容完全显示
        self.setFixedSize(120, 120)
        
        # 创建图形视图和场景
        self.scene = QGraphicsScene(0, 0, 120, 120)  # 明确设置场景大小
        self.view = QGraphicsView(self.scene, self)
        self.view.setStyleSheet("background: transparent; border: none;")
        self.view.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.view.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.view.setRenderHint(QPainter.Antialiasing)  # 添加抗锯齿
        self.view.setRenderHint(QPainter.SmoothPixmapTransform)
        
        # 创建emoji文本项
        self.emoji_item = self.scene.addText("🤖")
        self.emoji_item.setFont(QFont("Arial", 40))
        self.emoji_item.setDefaultTextColor(QColor(0, 0, 0))
        
        # 设置视图大小和场景范围
        self.view.setFixedSize(120, 120)
        self.view.setSceneRect(0, 0, 120, 120)  # 确保视图显示整个场景
        
        # 计算并设置emoji的中心点位置，使其居中显示
        emoji_rect = self.emoji_item.boundingRect()
        self.emoji_item.setPos(
            (self.view.width() - emoji_rect.width()) / 2,
            (self.view.height() - emoji_rect.height()) / 2
        )
        
        # 存储emoji中心点坐标，用于旋转
        self.emoji_center = self.emoji_item.boundingRect().center()
        
        # 使用无边距布局
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.view)
        self.setLayout(layout)
        
        # 初始化拖动相关变量
        self.drag_position = None
        self.setStyleSheet("""
            QWidget {
                background-color: rgba(255, 255, 255, 180); /* 增加不透明度 */
                border-radius: 60px; /* 调整为窗口大小的一半 */
            }
        """)
        
        # 设置默认位置为桌面右侧
        screen = QApplication.primaryScreen().geometry()
        self.move(screen.width() - self.width() - 20, screen.height() // 2 - self.height() // 2)
        
        # 创建旋转动画，降低旋转速度
        self.rotation_angle = 0
        self.rotation_timer = QTimer(self)
        self.rotation_timer.timeout.connect(self.rotate)
        self.rotation_timer.start(80)  # 降低旋转速度，之前是50ms

    def rotate(self):
        # 更新旋转角度，减小旋转幅度
        self.rotation_angle = (self.rotation_angle + 3) % 360  # 减小旋转步长，之前是5
        
        # 创建变换并设置旋转中心点
        transform = QTransform()
        # 先移动到中心点
        transform.translate(self.emoji_center.x(), self.emoji_center.y())
        # 执行旋转
        transform.rotate(self.rotation_angle)
        # 再移回原位置
        transform.translate(-self.emoji_center.x(), -self.emoji_center.y())
        
        # 应用变换
        self.emoji_item.setTransform(transform)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            # 记录鼠标按下时的位置
            self.drag_position = event.globalPos() - self.frameGeometry().topLeft()
            # 设置鼠标追踪开启，以接收连续的mouseMoveEvent
            self.setMouseTracking(True)
            event.accept()
        
        # 发送点击信号
        self.clicked.emit()

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.LeftButton and self.drag_position is not None:
            # 计算移动位置
            self.move(event.globalPos() - self.drag_position)
            event.accept()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            # 释放鼠标时清除拖动位置
            self.drag_position = None
            self.setMouseTracking(False)
            event.accept()

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton:
            # 双击时显示主窗口并隐藏悬浮球
            self.parent().showNormal()
            self.parent().activateWindow()
            self.hide()
            event.accept()

class LoadingSpinner(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(40, 40)
        self.setMaximumSize(40, 40)
        
        # 创建更现代化的加载动画SVG
        self.svg_str = """
        <svg xmlns="http://www.w3.org/2000/svg" width="40" height="40" viewBox="0 0 24 24" fill="none">
          <circle cx="12" cy="12" r="10" stroke="#E0E0E0" stroke-width="2" />
          <path d="M12 2C6.48 2 2 6.48 2 12" stroke="#4CAF50" stroke-width="3" stroke-linecap="round">
            <animateTransform
              attributeName="transform"
              type="rotate"
              from="0 12 12"
              to="360 12 12"
              dur="0.8s"
              repeatCount="indefinite" />
          </path>
          <circle cx="12" cy="12" r="1" fill="#4CAF50">
            <animate
              attributeName="r"
              values="1;3;1"
              dur="1s"
              repeatCount="indefinite" />
          </circle>
        </svg>
        """
        
        # 创建并设置SVG部件
        self.svg_widget = QSvgWidget(self)
        self.svg_widget.setGeometry(0, 0, 40, 40)
        self.svg_widget.load(bytearray(self.svg_str, 'utf-8'))
        
        # 创建布局
        layout = QVBoxLayout()
        layout.addWidget(self.svg_widget)
        layout.setContentsMargins(0, 0, 0, 0)
        self.setLayout(layout)
        self.hide()  # 初始时隐藏

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        
        # Window setup
        self.setWindowTitle("🤖 DeepSeek AI Assistant")
        self.setMinimumSize(900, 700)
        
        # Create a custom icon with emoji
        pixmap = QPixmap(32, 32)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        font = QFont()
        font.setPointSize(24)
        painter.setFont(font)
        painter.drawText(pixmap.rect(), Qt.AlignCenter, "🤖")
        painter.end()
        self.setWindowIcon(QIcon(pixmap))
        
        # 初始化用户输入相关变量
        self._current_input_event = None
        self._current_input_result = None
        
        # Initialize variables
        self.messages_history = MessageHistory()
        self.task_summary = []
        self.worker = None
        self.current_tool = "None"
        self.secondary_input_needed = False
        self.secondary_input = None
        self.prompt = None
        self.input_dialog = None
        
        # Setup UI
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        
        # Main layout with splitter
        self.main_layout = QVBoxLayout(self.central_widget)
        self.main_splitter = QSplitter(Qt.Horizontal)
        
        # Create left and right panels
        self.init_left_panel()
        self.init_right_panel()
        
        # Add panels to splitter
        self.main_splitter.addWidget(self.left_panel)
        self.main_splitter.addWidget(self.right_panel)
        self.main_splitter.setSizes([int(self.width() * 0.65), int(self.width() * 0.35)])
        
        # Add splitter to main layout
        self.main_layout.addWidget(self.main_splitter)
        
        # Create system tray icon
        self.init_system_tray()
        
        # Create floating ball (hidden initially)
        self.floating_ball = FloatingBall()
        self.floating_ball.clicked.connect(self.show_from_floating_ball)
        self.floating_ball.hide()
        
        # Load environment variables
        load_dotenv()
        
        # Apply stylesheet
        self.apply_stylesheet()
        
        # Start time updater
        self.start_time_updater()
        
        # 连接用户输入信号
        self.worker = None

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

    def init_right_panel(self):
        self.right_panel = QWidget()
        self.right_layout = QVBoxLayout(self.right_panel)
        
        # Tab widget for different sections
        self.tab_widget = QTabWidget()
        self.tab_widget.setStyleSheet("""
            QTabWidget::pane {
                border: 1px solid #E0E0E0;
                border-radius: 8px;
                padding: 5px;
            }
            QTabBar::tab {
                background-color: #F5F5F5;
                border: 1px solid #E0E0E0;
                border-bottom-color: none;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
                padding: 8px 12px;
                margin-right: 2px;
            }
            QTabBar::tab:selected {
                background-color: white;
                border-bottom-color: white;
                color: #4CAF50;
                font-weight: bold;
            }
        """)
        
        # Task plan tab
        self.task_plan_tab = QTextEdit()
        self.task_plan_tab.setReadOnly(True)
        self.task_plan_tab.setPlaceholderText("任务计划将在此显示...")
        # 添加初始说明
        self.task_plan_tab.setHtml("""
        <div style="color:#666666; font-style:italic; text-align:center; margin-top:20px;">
            <p>任务计划和摘要会实时显示在这里</p>
            <p>包括工作进度和状态更新</p>
        </div>
        """)
        self.tab_widget.addTab(self.task_plan_tab, "📋 任务计划")
        
        # Console output tab
        self.console_output_tab = QTextEdit()
        self.console_output_tab.setReadOnly(True)
        self.console_output_tab.setPlaceholderText("工具输出将在此显示...")
        # 添加初始说明
        self.console_output_tab.setHtml("""
        <div style="color:#666666; font-style:italic; text-align:center; margin-top:20px;">
            <p>工具执行结果会实时显示在这里</p>
            <p>您可以看到每个工具的输出和可能的错误信息</p>
        </div>
        """)
        self.console_output_tab.setStyleSheet("font-family: 'Courier New', monospace;")
        self.tab_widget.addTab(self.console_output_tab, "🔧 工具输出")
        
        # Tools history tab
        tools_tab = QWidget()
        tools_layout = QVBoxLayout(tools_tab)
        
        # 添加工具历史列表
        tools_layout.addWidget(QLabel("🔨 已使用工具历史:"))
        self.tool_history = QListWidget()
        self.tool_history.setAlternatingRowColors(True)
        self.tool_history.setStyleSheet("""
            QListWidget {
                border: 1px solid #E0E0E0;
                border-radius: 5px;
                background-color: white;
                font-family: 'Segoe UI', Arial, sans-serif;
            }
            QListWidget::item {
                padding: 5px;
                border-bottom: 1px solid #F0F0F0;
            }
            QListWidget::item:alternate {
                background-color: #F8F8F8;
            }
        """)
        tools_layout.addWidget(self.tool_history)
        
        self.tab_widget.addTab(tools_tab, "🔨 工具历史")
        
        # Settings tab
        self.settings_tab = QWidget()
        self.init_settings_tab()
        self.tab_widget.addTab(self.settings_tab, "⚙️ 设置")
        
        # Help tab
        self.help_tab = QTextEdit()
        self.help_tab.setReadOnly(True)
        self.load_help_content()
        self.tab_widget.addTab(self.help_tab, "❓ 帮助")
        
        self.right_layout.addWidget(self.tab_widget)
        
        # Action buttons
        action_buttons = QWidget()
        action_layout = QHBoxLayout(action_buttons)
        
        # Import button
        self.import_button = QPushButton("📥 导入对话")
        self.import_button.clicked.connect(self.import_chat_history)
        action_layout.addWidget(self.import_button)
        
        # Export button
        self.export_button = QPushButton("📤 导出对话")
        self.export_button.clicked.connect(self.export_chat_history)
        action_layout.addWidget(self.export_button)
        
        # Summary button
        self.summary_button = QPushButton("📝 查看摘要")
        self.summary_button.clicked.connect(self.show_summary)
        action_layout.addWidget(self.summary_button)
        
        self.right_layout.addWidget(action_buttons)

    def init_settings_tab(self):
        settings_layout = QVBoxLayout(self.settings_tab)
        
        # API Keys section
        keys_group = QWidget()
        keys_layout = QVBoxLayout(keys_group)
        keys_layout.setContentsMargins(0, 0, 0, 10)
        
        # DeepSeek API Key
        keys_layout.addWidget(QLabel("🔑 DeepSeek API Key:"))
        self.api_key_input = QLineEdit()
        self.api_key_input.setText(os.getenv("api_key", ""))
        self.api_key_input.setEchoMode(QLineEdit.Password)  # Hide by default
        keys_layout.addWidget(self.api_key_input)
        
        # Weather API Key
        keys_layout.addWidget(QLabel("🌦️ Weather API Key:"))
        self.weather_key_input = QLineEdit()
        self.weather_key_input.setText(os.getenv("key", ""))
        keys_layout.addWidget(self.weather_key_input)
        
        settings_layout.addWidget(keys_group)
        
        # Email settings section
        email_group = QWidget()
        email_layout = QVBoxLayout(email_group)
        email_layout.setContentsMargins(0, 0, 0, 10)
        
        # Email address
        email_layout.addWidget(QLabel("📧 Email Address:"))
        self.email_input = QLineEdit()
        self.email_input.setText(os.getenv("QQ_EMAIL", ""))
        email_layout.addWidget(self.email_input)
        
        # Auth code
        email_layout.addWidget(QLabel("🔐 Email Auth Code:"))
        self.auth_code_input = QLineEdit()
        self.auth_code_input.setText(os.getenv("AUTH_CODE", ""))
        self.auth_code_input.setEchoMode(QLineEdit.Password)
        email_layout.addWidget(self.auth_code_input)
        
        settings_layout.addWidget(email_group)
        
        # Save settings button
        self.save_settings_button = QPushButton("💾 Save Settings")
        self.save_settings_button.clicked.connect(self.save_settings)
        self.save_settings_button.setStyleSheet("""
            QPushButton {
                background-color: #2196F3;
                color: white;
                border: none;
                border-radius: 5px;
                padding: 8px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #1E88E5;
            }
        """)
        settings_layout.addWidget(self.save_settings_button)
        
        # User information section
        settings_layout.addWidget(QLabel("👤 User Information:"))
        self.user_info_edit = QTextEdit()
        self.load_user_info()
        settings_layout.addWidget(self.user_info_edit)
        
        # Save user info button
        self.save_user_info_button = QPushButton("🔄 Update User Info")
        self.save_user_info_button.clicked.connect(self.save_user_info)
        self.save_user_info_button.setStyleSheet("""
            QPushButton {
                background-color: #FF9800;
                color: white;
                border: none;
                border-radius: 5px;
                padding: 8px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #FB8C00;
            }
        """)
        settings_layout.addWidget(self.save_user_info_button)

    def init_system_tray(self):
        self.tray_icon = QSystemTrayIcon(self)
        
        # Create a custom icon with emoji
        pixmap = QPixmap(32, 32)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        font = QFont()
        font.setPointSize(24)
        painter.setFont(font)
        painter.drawText(pixmap.rect(), Qt.AlignCenter, "🤖")
        painter.end()
        
        self.tray_icon.setIcon(QIcon(pixmap))
        self.tray_icon.setToolTip("DeepSeek AI Assistant")
        
        # Create tray menu
        tray_menu = QMenu()
        
        show_action = QAction("Show Assistant", self)
        show_action.triggered.connect(self.show_from_tray)
        tray_menu.addAction(show_action)
        
        quit_action = QAction("Quit", self)
        quit_action.triggered.connect(self.quit_application)
        tray_menu.addAction(quit_action)
        
        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.activated.connect(self.tray_icon_activated)
        self.tray_icon.show()

    def apply_stylesheet(self):
        self.setStyleSheet("""
            QMainWindow, QWidget {
                background-color: #F9F9F9;
                color: #333333;
                font-family: 'Segoe UI', Arial, sans-serif;
            }
            
            QSplitter::handle {
                background-color: #E0E0E0;
                width: 1px;
            }
            
            QPushButton {
                background-color: #4CAF50;
                color: white;
                border: none;
                border-radius: 5px;
                padding: 8px;
                font-weight: bold;
            }
            
            QPushButton:hover {
                background-color: #45a049;
            }
            
            QPushButton:pressed {
                background-color: #388E3C;
            }
            
            QLabel {
                color: #424242;
            }
            
            QTextEdit, QLineEdit {
                background-color: white;
                border: 1px solid #E0E0E0;
                border-radius: 5px;
                padding: 5px;
            }
            
            QTextEdit:focus, QLineEdit:focus {
                border: 1px solid #4CAF50;
            }
        """)

    def start_time_updater(self):
        self.time_timer = QTimer(self)
        self.time_timer.timeout.connect(self.update_time)
        self.time_timer.start(1000)  # Update every second

    def update_time(self):
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.time_label.setText(f"🕒 {current_time}")

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

    def append_message(self, role, content):
        if role == "user":
            # 用户消息使用绿色，字体大小14px
            self.chat_display.append(f'<div style="color: #2E7D32; font-size: 14px;"><b>👤 You:</b> {content}</div>')
        else:
            # 助手消息使用蓝色，字体大小14px
            html = markdown.markdown(content)
            self.chat_display.append(f'<div style="color: #1976D2; font-size: 14px;"><b>🤖 Assistant:</b> {html}</div>')
        self.chat_display.moveCursor(QTextCursor.End)

    def handle_response(self, response):
        self.append_message("assistant", response)

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
            
            # 在聊天区域显示错误信息
            self.chat_display.append(
                f'<div style="color: #D32F2F; font-size: 14px; background-color: #FFEBEE; padding: 8px; border-left: 4px solid #D32F2F; margin: 5px 0;">'
                f'<b>⚠️ 执行出错:</b> {error_message}</div>'
            )
            self.chat_display.repaint()
            QApplication.processEvents()
            
            # 切换到控制台输出选项卡
            self.tab_widget.setCurrentIndex(1)
            
            # 短暂延迟，让用户能看到错误信息
            time.sleep(0.5)
            
        # 更新最后确认时间
        last_confirmation_time = current_time
        
        self.secondary_input_needed = True
        self.prompt = prompt
        
        # 创建对话框并显示，传递错误信息
        self.input_dialog = SecondaryInputDialog(prompt, parent=self, timeout=timeout, error_message=error_message)
        self.input_dialog.input_received.connect(self.handle_secondary_input)
        self.input_dialog.exec_()

    def handle_secondary_input(self, input_text):
        """处理二次输入结果 - 由主线程调用"""
        self.secondary_input = input_text
        self.secondary_input_needed = False
        
        # 如果有等待中的事件，设置结果并触发事件
        if self._current_input_event is not None:
            self._current_input_result = input_text
            # 使用异步方法安全触发事件
            def set_event():
                import asyncio
                asyncio.run_coroutine_threadsafe(self._set_event_async(), asyncio.get_event_loop())
            
            # 使用QMetaObject.invokeMethod确保在正确的线程上调用
            QTimer.singleShot(0, set_event)
        
        # 清除对话框引用
        self.input_dialog = None

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

class SecondaryInputDialog(QDialog):
    """用户二次输入对话框，用于任务执行过程中需要用户确认或提供额外信息的场景"""
    
    # 定义输入接收信号
    input_received = pyqtSignal(str)
    
    def __init__(self, prompt, parent=None, timeout=60, error_message=None):
        super().__init__(parent)
        self.setWindowTitle("需要用户输入")
        self.setWindowFlags(self.windowFlags() | Qt.WindowStaysOnTopHint)
        self.resize(500, 300)  # 增加窗口大小以容纳错误信息
        
        # 设置主布局
        layout = QVBoxLayout(self)
        
        # 如果有错误信息，先显示错误框
        if error_message:
            error_frame = QFrame()
            error_frame.setStyleSheet("""
                background-color: #FFEBEE;
                border-left: 4px solid #D32F2F;
                border-radius: 4px;
                padding: 8px;
                margin-bottom: 10px;
            """)
            error_layout = QVBoxLayout(error_frame)
            
            error_title = QLabel("⚠️ 执行出错")
            error_title.setStyleSheet("color: #D32F2F; font-weight: bold; font-size: 14px;")
            error_layout.addWidget(error_title)
            
            error_details = QLabel(error_message)
            error_details.setWordWrap(True)
            error_details.setStyleSheet("color: #555555;")
            error_layout.addWidget(error_details)
            
            layout.addWidget(error_frame)
        
        # 添加提示信息标签
        prompt_label = QLabel(prompt)
        prompt_label.setWordWrap(True)
        prompt_label.setStyleSheet("font-size: 14px; margin-bottom: 10px;")
        layout.addWidget(prompt_label)
        
        # 添加选项说明
        options_label = QLabel("1. 继续尝试 (直接输入建议或按回车)\n2. 终止任务 (输入数字2或\"终止\")")
        options_label.setStyleSheet("color: #0D47A1; font-weight: bold;")
        layout.addWidget(options_label)
        
        # 添加输入框
        self.input_field = QTextEdit()
        self.input_field.setPlaceholderText("请输入您的选择或建议...")
        self.input_field.setMinimumHeight(100)
        layout.addWidget(self.input_field)
        
        # 添加按钮
        button_layout = QHBoxLayout()
        
        # 继续按钮
        self.continue_button = QPushButton("继续尝试")
        self.continue_button.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                border: none;
                border-radius: 5px;
                padding: 8px 16px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
        """)
        self.continue_button.clicked.connect(self.accept_input)
        button_layout.addWidget(self.continue_button)
        
        # 终止按钮
        self.terminate_button = QPushButton("终止任务")
        self.terminate_button.setStyleSheet("""
            QPushButton {
                background-color: #F44336;
                color: white;
                border: none;
                border-radius: 5px;
                padding: 8px 16px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #D32F2F;
            }
        """)
        self.terminate_button.clicked.connect(self.terminate_task)
        button_layout.addWidget(self.terminate_button)
        
        layout.addLayout(button_layout)
        
        # 添加倒计时进度条
        countdown_layout = QHBoxLayout()
        countdown_label = QLabel(f"倒计时 {timeout} 秒:")
        countdown_layout.addWidget(countdown_label)
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, timeout)
        self.progress_bar.setValue(timeout)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setFormat("%v 秒")
        countdown_layout.addWidget(self.progress_bar)
        
        layout.addLayout(countdown_layout)
        
        # 设置倒计时定时器
        self.timeout = timeout
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_countdown)
        self.timer.start(1000)  # 每秒更新一次
        
        # 设置窗口样式
        self.setStyleSheet("""
            QDialog {
                background-color: #F9F9F9;
                border: 1px solid #E0E0E0;
                border-radius: 5px;
            }
            QLabel {
                color: #424242;
            }
            QTextEdit {
                background-color: white;
                border: 1px solid #E0E0E0;
                border-radius: 5px;
                padding: 5px;
            }
        """)
        
        # 使窗口居中
        if parent:
            self.move(
                parent.x() + parent.width() // 2 - self.width() // 2,
                parent.y() + parent.height() // 2 - self.height() // 2
            )
    
    def update_countdown(self):
        """更新倒计时"""
        current_value = self.progress_bar.value()
        if current_value > 0:
            self.progress_bar.setValue(current_value - 1)
        else:
            # 时间到，自动提交当前输入
            self.timer.stop()
            self.accept_input()
    
    def accept_input(self):
        """接受用户输入并发送信号"""
        self.timer.stop()
        input_text = self.input_field.toPlainText().strip()
        self.input_received.emit(input_text)
        self.accept()
    
    def terminate_task(self):
        """终止任务"""
        self.timer.stop()
        self.input_received.emit("2")  # 发送终止信号
        self.accept()
    
    def closeEvent(self, event):
        """处理对话框关闭事件"""
        self.timer.stop()
        self.input_received.emit("")  # 发送空字符串表示用户关闭了对话框
        super().closeEvent(event)

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