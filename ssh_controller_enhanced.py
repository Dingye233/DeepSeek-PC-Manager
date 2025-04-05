import paramiko
import asyncio
import os
import time
import re
import json
import random
import string
import threading
import queue
import socket
from typing import Dict, Any, Optional, Tuple, List, Union
from console_utils import print_color, print_success, print_error, print_warning, print_info
from threading import Lock
from dotenv import load_dotenv
import traceback

# 导入OpenAI客户端，用于LLM分析
from openai import OpenAI

# 加载环境变量
load_dotenv()

# 获取API密钥
api_key = os.environ.get("api_key")

# SSH连接缓存
class SSHConnectionCache:
    """SSH连接缓存，用于管理和复用SSH连接"""
    _instance = None
    _lock = Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super(SSHConnectionCache, cls).__new__(cls)
                    cls._instance._connections = {}
                    cls._instance._last_access = {}
        return cls._instance
    
    def get_connection(self, host: str, username: str, password: str) -> Optional[paramiko.SSHClient]:
        """获取SSH连接，如果不存在则创建新连接"""
        key = f"{username}@{host}"
        
        with self._lock:
            # 检查连接是否存在且有效
            if key in self._connections:
                client = self._connections[key]
                try:
                    # 尝试执行一个简单命令来验证连接是否有效
                    transport = client.get_transport()
                    if transport and transport.is_active():
                        # 更新最后访问时间
                        self._last_access[key] = time.time()
                        print_info(f"复用已有SSH连接: {key}")
                        return client
                except Exception:
                    # 连接已失效，移除它
                    print_warning(f"SSH连接 {key} 已失效，将创建新连接")
                    self._remove_connection(key)
            
            # 创建新连接
            try:
                client = paramiko.SSHClient()
                client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                print_info(f"正在创建新SSH连接: {key}")
                client.connect(host, username=username, password=password, timeout=15)
                
                # 存储新连接
                self._connections[key] = client
                self._last_access[key] = time.time()
                print_success(f"SSH连接成功: {key}")
                return client
            except Exception as e:
                print_error(f"SSH连接失败: {key} - {str(e)}")
                return None
    
    def _remove_connection(self, key: str):
        """移除并关闭连接"""
        if key in self._connections:
            try:
                client = self._connections[key]
                client.close()
            except Exception:
                pass
            
            del self._connections[key]
            if key in self._last_access:
                del self._last_access[key]
    
    def close_idle_connections(self, max_idle_time: int = 300):
        """关闭空闲连接"""
        current_time = time.time()
        idle_keys = []
        
        with self._lock:
            for key, last_access in self._last_access.items():
                if current_time - last_access > max_idle_time:
                    idle_keys.append(key)
            
            for key in idle_keys:
                print_info(f"关闭空闲SSH连接: {key}")
                self._remove_connection(key)
    
    def close_all_connections(self):
        """关闭所有连接"""
        with self._lock:
            for key in list(self._connections.keys()):
                self._remove_connection(key)

# 创建一个服务器信息缓存，用于存储远程服务器的信息
class ServerInfoCache:
    """服务器信息缓存，用于存储远程服务器的信息"""
    _instance = None
    _lock = Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super(ServerInfoCache, cls).__new__(cls)
                    cls._instance._cache = {}
        return cls._instance
    
    def get_server_info(self, host: str, username: str) -> Optional[Dict[str, Any]]:
        """获取服务器信息"""
        key = f"{username}@{host}"
        with self._lock:
            return self._cache.get(key)
    
    def set_server_info(self, host: str, username: str, info: Dict[str, Any]):
        """设置服务器信息"""
        key = f"{username}@{host}"
        with self._lock:
            self._cache[key] = info
    
    def clear_cache(self):
        """清除缓存"""
        with self._lock:
            self._cache.clear()

# 添加交互消息队列类
class InteractionQueue:
    """SSH交互消息队列，用于在SSH线程和Agent线程之间传递消息"""
    def __init__(self):
        # SSH -> Agent: SSH输出队列
        self.output_queue = queue.Queue()
        # Agent -> SSH: Agent输入队列
        self.input_queue = queue.Queue()
        # 控制信号
        self.stop_signal = threading.Event()
    
    def put_output(self, output: str):
        """SSH线程将输出放入队列，供Agent线程处理"""
        self.output_queue.put(output)
    
    def get_output(self, timeout=None) -> Optional[str]:
        """Agent线程从队列获取SSH输出"""
        try:
            return self.output_queue.get(block=True, timeout=timeout)
        except queue.Empty:
            return None
    
    def put_input(self, input_text: str):
        """Agent线程将输入放入队列，供SSH线程处理"""
        self.input_queue.put(input_text)
    
    def get_input(self, timeout=None) -> Optional[str]:
        """SSH线程从队列获取Agent输入"""
        try:
            return self.input_queue.get(block=True, timeout=timeout)
        except queue.Empty:
            return None
    
    def stop(self):
        """发送停止信号"""
        self.stop_signal.set()
    
    def is_stopped(self) -> bool:
        """检查是否收到停止信号"""
        return self.stop_signal.is_set()

# 永久性SSH会话管理器
class PersistentSSHManager:
    """管理长期存活的SSH会话，跟随程序生命周期"""
    _instance = None
    _lock = Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super(PersistentSSHManager, cls).__new__(cls)
                    cls._instance._init()
        return cls._instance
    
    def _init(self):
        """初始化SSH会话管理器"""
        # 活跃会话字典 {session_id: session_info}
        self.active_sessions = {}
        # 队列和线程字典
        self.interaction_queues = {}
        self.ssh_threads = {}
        self.agent_threads = {}
        # 会话输出历史
        self.session_history = {}
        # 存活标志
        self.running = False
        # 线程安全锁
        self.session_lock = threading.Lock()
        # LLM客户端
        self.llm_client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")
    
    def start(self):
        """启动SSH会话管理器"""
        self.running = True
        print_info("SSH会话管理器已启动")
        
        # 启动会话监控线程
        self.monitor_thread = threading.Thread(target=self._monitor_sessions)
        self.monitor_thread.daemon = True
        self.monitor_thread.start()
    
    def stop(self):
        """停止所有SSH会话"""
        self.running = False
        
        with self.session_lock:
            for session_id in list(self.active_sessions.keys()):
                self.close_session(session_id)
        
        print_info("SSH会话管理器已停止")
    
    def create_session(self, host: str, username: str, password: str, 
                       initial_command: str = "") -> str:
        """
        创建新的SSH会话
        
        Args:
            host: 主机地址
            username: 用户名
            password: 密码
            initial_command: 初始命令
            
        Returns:
            session_id: 会话ID
        """
        # 生成会话ID
        session_id = f"{username}@{host}_{int(time.time())}_{random.randint(1000, 9999)}"
        
        # 创建交互队列
        interaction_queue = InteractionQueue()
        
        # 创建会话信息
        session_info = {
            "host": host,
            "username": username,
            "password": password,
            "start_time": time.time(),
            "last_activity": time.time(),
            "status": "connecting",
            "commands_history": [],
            "current_output": "",
            "os_info": {"os_type": "Unknown", "version": "Unknown"}
        }
        
        # 启动SSH线程
        ssh_thread = threading.Thread(
            target=self._ssh_session_worker,
            args=(session_id, host, username, password, initial_command, interaction_queue)
        )
        ssh_thread.daemon = True
        
        # 启动Agent线程
        agent_thread = threading.Thread(
            target=self._agent_worker,
            args=(session_id, interaction_queue, host, username, password)
        )
        agent_thread.daemon = True
        
        # 更新会话信息
        with self.session_lock:
            self.active_sessions[session_id] = session_info
            self.interaction_queues[session_id] = interaction_queue
            self.ssh_threads[session_id] = ssh_thread
            self.agent_threads[session_id] = agent_thread
            self.session_history[session_id] = []
        
        # 启动线程
        ssh_thread.start()
        agent_thread.start()
        
        print_success(f"已创建SSH会话: {session_id}")
        return session_id
    
    def send_command(self, session_id: str, command: str) -> bool:
        """
        向指定会话发送命令
        
        Args:
            session_id: 会话ID
            command: 要执行的命令
            
        Returns:
            bool: 是否成功发送
        """
        with self.session_lock:
            if session_id not in self.active_sessions:
                print_error(f"会话不存在: {session_id}")
                return False
            
            if self.active_sessions[session_id]["status"] != "connected":
                print_error(f"会话未连接或已关闭: {session_id}")
                return False
            
            # 更新最后活动时间
            self.active_sessions[session_id]["last_activity"] = time.time()
            
            # 添加到命令历史
            self.active_sessions[session_id]["commands_history"].append(command)
            
            # 发送到队列
            queue = self.interaction_queues.get(session_id)
            if queue:
                queue.put_input(command)
                print_info(f"命令已发送到会话 {session_id}: {command}")
                return True
            else:
                print_error(f"会话队列不存在: {session_id}")
                return False
    
    def get_session_output(self, session_id: str, since_time: float = None) -> str:
        """
        获取会话输出
        
        Args:
            session_id: 会话ID
            since_time: 获取指定时间后的输出
            
        Returns:
            str: 会话输出
        """
        with self.session_lock:
            if session_id not in self.active_sessions:
                return f"会话不存在: {session_id}"
            
            history = self.session_history.get(session_id, [])
            
            if not history:
                return ""
            
            if since_time is None:
                # 返回所有历史
                return "".join([entry["output"] for entry in history])
            else:
                # 返回指定时间后的历史
                recent_outputs = [
                    entry["output"] for entry in history 
                    if entry["timestamp"] > since_time
                ]
                return "".join(recent_outputs)
    
    def get_session_status(self, session_id: str) -> Dict[str, Any]:
        """
        获取会话状态
        
        Args:
            session_id: 会话ID
            
        Returns:
            Dict: 会话状态信息
        """
        with self.session_lock:
            if session_id not in self.active_sessions:
                return {"status": "not_found", "error": f"会话不存在: {session_id}"}
            
            session = self.active_sessions[session_id]
            return {
                "status": session["status"],
                "host": session["host"],
                "username": session["username"],
                "start_time": session["start_time"],
                "last_activity": session["last_activity"],
                "uptime": time.time() - session["start_time"],
                "idle_time": time.time() - session["last_activity"],
                "os_info": session["os_info"],
                "commands_count": len(session["commands_history"])
            }
    
    def close_session(self, session_id: str) -> bool:
        """
        关闭指定会话
        
        Args:
            session_id: 会话ID
            
        Returns:
            bool: 是否成功关闭
        """
        with self.session_lock:
            if session_id not in self.active_sessions:
                print_warning(f"会话不存在，无法关闭: {session_id}")
                return False
            
            # 获取队列并发送停止信号
            queue = self.interaction_queues.get(session_id)
            if queue:
                queue.stop()
            
            # 等待线程结束
            ssh_thread = self.ssh_threads.get(session_id)
            agent_thread = self.agent_threads.get(session_id)
            
            if ssh_thread and ssh_thread.is_alive():
                ssh_thread.join(timeout=5)
            
            if agent_thread and agent_thread.is_alive():
                agent_thread.join(timeout=5)
            
            # 更新会话状态
            self.active_sessions[session_id]["status"] = "closed"
            
            # 保留会话历史但移除线程和队列
            if session_id in self.ssh_threads:
                del self.ssh_threads[session_id]
            if session_id in self.agent_threads:
                del self.agent_threads[session_id]
            if session_id in self.interaction_queues:
                del self.interaction_queues[session_id]
            
            print_info(f"会话已关闭: {session_id}")
            return True
    
    def list_sessions(self) -> List[Dict[str, Any]]:
        """
        列出所有会话
        
        Returns:
            List[Dict]: 会话列表
        """
        with self.session_lock:
            session_list = []
            for session_id, session in self.active_sessions.items():
                session_list.append({
                    "session_id": session_id,
                    "host": session["host"],
                    "username": session["username"],
                    "status": session["status"],
                    "start_time": session["start_time"],
                    "uptime": time.time() - session["start_time"],
                    "last_activity": session["last_activity"],
                    "idle_time": time.time() - session["last_activity"]
                })
            return session_list
    
    def _ssh_session_worker(self, session_id: str, host: str, username: str, password: str,
                           initial_command: str, interaction_queue: InteractionQueue):
        """SSH会话工作线程"""
        try:
            # 创建SSH客户端
            client = paramiko.SSHClient()
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            
            # 连接
            print_info(f"[会话 {session_id}] 正在连接 {username}@{host}...")
            client.connect(host, username=username, password=password, timeout=15)
            
            # 更新会话状态
            with self.session_lock:
                if session_id in self.active_sessions:
                    self.active_sessions[session_id]["status"] = "connected"
            
            print_success(f"[会话 {session_id}] 连接成功")
            
            # 创建交互式shell
            shell = client.invoke_shell()
            shell.settimeout(10)  # 设置较短的超时，允许定期检查队列
            
            # 处理初始输出
            time.sleep(1)
            initial_output = ""
            while shell.recv_ready():
                chunk = shell.recv(4096).decode('utf-8', errors='replace')
                initial_output += chunk
            
            # 输出到终端并放入历史
            if initial_output:
                print(initial_output, end='', flush=True)
                interaction_queue.put_output(initial_output)
                self._add_to_history(session_id, initial_output)
            
            # 发送初始命令
            if initial_command:
                print_info(f"[会话 {session_id}] 发送初始命令: {initial_command}")
                shell.send(initial_command + "\n")
            
            # 主循环
            while not interaction_queue.is_stopped():
                try:
                    # 处理输出
                    if shell.recv_ready():
                        chunk = shell.recv(4096).decode('utf-8', errors='replace')
                        if chunk:
                            print(chunk, end='', flush=True)
                            interaction_queue.put_output(chunk)
                            self._add_to_history(session_id, chunk)
                            
                            # 更新最后活动时间
                            with self.session_lock:
                                if session_id in self.active_sessions:
                                    self.active_sessions[session_id]["last_activity"] = time.time()
                    
                    # 处理输入
                    user_input = interaction_queue.get_input(timeout=0.5)
                    if user_input is not None:
                        shell.send(f"{user_input}\n")
                        
                        # 更新最后活动时间
                        with self.session_lock:
                            if session_id in self.active_sessions:
                                self.active_sessions[session_id]["last_activity"] = time.time()
                    
                    # 检查会话状态
                    if shell.exit_status_ready():
                        print_warning(f"[会话 {session_id}] 远程shell已退出")
                        break
                    
                    # 小憩一下
                    time.sleep(0.1)
                    
                except socket.timeout:
                    continue
                except Exception as e:
                    print_error(f"[会话 {session_id}] 会话处理出错: {str(e)}")
                    interaction_queue.put_output(f"[错误] {str(e)}")
                    break
            
            # 会话结束，清理资源
            try:
                shell.close()
                client.close()
            except:
                pass
            
            # 更新会话状态
            with self.session_lock:
                if session_id in self.active_sessions:
                    self.active_sessions[session_id]["status"] = "disconnected"
            
            print_info(f"[会话 {session_id}] SSH会话已结束")
            
        except Exception as e:
            error_detail = traceback.format_exc()
            print_error(f"[会话 {session_id}] SSH会话出错: {str(e)}\n{error_detail}")
            
            # 更新会话状态
            with self.session_lock:
                if session_id in self.active_sessions:
                    self.active_sessions[session_id]["status"] = "error"
            
            # 通知Agent线程
            interaction_queue.put_output(f"[致命错误] SSH连接失败: {str(e)}")
            interaction_queue.stop()
    
    def _agent_worker(self, session_id: str, interaction_queue: InteractionQueue, 
                     host: str, username: str, password: str):
        """Agent工作线程，处理自动响应和决策"""
        try:
            print_info(f"[会话 {session_id}] Agent工作线程已启动")
            
            # 会话状态跟踪
            session_state = {
                "os_info": {"os_type": "Unknown", "version": "Unknown"},
                "current_command": "",
                "command_state": "idle",  # idle, running, waiting_for_response, error
                "last_command_time": time.time(),
                "command_history": [],
                "context_buffer": [],  # 保存最近的交互历史
                "task_state": "init",  # init, exploring, executing, analyzing, planning
                "task_steps": [],  # 如果有多步任务，记录步骤
                "step_index": 0
            }
            
            # 缓存最近的输出，用于上下文分析
            recent_outputs = []
            output_buffer = ""
            
            # 识别模式
            password_patterns = [
                r'\[sudo\].*?密码.*?:',
                r'\[sudo\].*?password.*?:',
                r'password.*?:',
                r'密码.*?:',
                r'Password for.*?:',
                r'Authentication password.*?:'
            ]
            
            error_patterns = [
                r'command not found',
                r'没有那个文件或目录',
                r'No such file or directory',
                r'permission denied',
                r'权限不足',
                r'cannot access',
                r'错误:',
                r'Error:',
                r'failed',
                r'Failed'
            ]
            
            success_patterns = [
                r'successfully',
                r'Successfully',
                r'成功',
                r'已完成',
                r'Completed',
                r'completed'
            ]
            
            # 主循环
            while not interaction_queue.is_stopped():
                # 获取SSH输出
                output = interaction_queue.get_output(timeout=1)
                if output is None:
                    # 如果长时间没有输出，考虑下一步操作
                    if session_state["command_state"] == "running" and \
                       time.time() - session_state["last_command_time"] > 30:
                        # 命令可能已悄悄完成或卡住，尝试检查状态
                        if self._is_prompt_line(output_buffer):
                            session_state["command_state"] = "idle"
                            print_info("[Agent线程] 命令似乎已完成")
                            self._analyze_command_result(session_state, output_buffer)
                            output_buffer = ""
                    continue
                
                # 更新最后活动时间
                session_state["last_command_time"] = time.time()
                
                # 添加到缓冲区和上下文
                output_buffer += output
                recent_outputs.append(output)
                session_state["context_buffer"].append({"type": "output", "content": output, "time": time.time()})
                if len(recent_outputs) > 10:
                    recent_outputs = recent_outputs[-10:]
                
                # 控制上下文缓冲区大小
                if len(session_state["context_buffer"]) > 20:
                    session_state["context_buffer"] = session_state["context_buffer"][-20:]
                
                # 如果需要检测操作系统
                if session_state["os_info"]["os_type"] == "Unknown" and len(output_buffer) > 20:
                    session_state["os_info"] = self._detect_os_from_output(output_buffer)
                    print_info(f"[Agent线程] 检测到远程系统: {session_state['os_info']['os_type']} {session_state['os_info'].get('version', '')}")
                
                # 检查是否需要输入密码
                if any(re.search(pattern, output_buffer, re.IGNORECASE) for pattern in password_patterns):
                    print_info("[Agent线程] 检测到密码提示，自动输入密码")
                    interaction_queue.put_input(password)
                    session_state["context_buffer"].append({"type": "input", "content": "<密码输入>", "time": time.time()})
                    output_buffer = ""  # 清空缓冲区
                    continue
                
                # 检查是否有其他需要响应的提示
                if self._needs_auto_response(output_buffer):
                    # 使用更智能的方式生成响应，考虑上下文
                    response = self._generate_contextual_response(output_buffer, session_state)
                    if response:
                        print_info(f"[Agent线程] 生成自动响应: {response}")
                        interaction_queue.put_input(response)
                        session_state["context_buffer"].append({"type": "input", "content": response, "time": time.time()})
                        output_buffer = ""  # 清空缓冲区
                        continue
                
                # 检查错误和成功信息
                if any(re.search(pattern, output_buffer, re.IGNORECASE) for pattern in error_patterns):
                    if session_state["command_state"] == "running":
                        session_state["command_state"] = "error"
                        print_warning(f"[Agent线程] 检测到错误: {self._extract_error_message(output_buffer)}")
                
                if any(re.search(pattern, output_buffer, re.IGNORECASE) for pattern in success_patterns):
                    if session_state["command_state"] == "running":
                        print_info(f"[Agent线程] 检测到成功信息")
                
                # 检查提示符以确认命令完成
                if self._is_prompt_line(output):
                    if session_state["command_state"] in ["running", "waiting_for_response"]:
                        session_state["command_state"] = "idle"
                        print_info("[Agent线程] 命令已完成")
                        
                        # 分析命令结果并考虑下一步操作
                        self._analyze_command_result(session_state, output_buffer)
                        
                        # 如果有多步任务，可能需要执行下一步
                        if session_state["task_state"] == "executing" and session_state["task_steps"]:
                            if session_state["step_index"] < len(session_state["task_steps"]) - 1:
                                session_state["step_index"] += 1
                                next_cmd = session_state["task_steps"][session_state["step_index"]]
                                print_info(f"[Agent线程] 执行下一步: {next_cmd}")
                                interaction_queue.put_input(next_cmd)
                                session_state["command_state"] = "running"
                                session_state["current_command"] = next_cmd
                                session_state["command_history"].append(next_cmd)
                                session_state["context_buffer"].append({"type": "input", "content": next_cmd, "time": time.time()})
                
                # 清空输出缓冲区
                output_buffer = ""
            
            print_info(f"[会话 {session_id}] Agent工作线程已结束")
            
        except Exception as e:
            error_detail = traceback.format_exc()
            print_error(f"[会话 {session_id}] Agent线程出错: {str(e)}\n{error_detail}")
    
    def _add_to_history(self, session_id: str, output: str):
        """添加输出到会话历史"""
        with self.session_lock:
            if session_id not in self.session_history:
                self.session_history[session_id] = []
            
            # 添加输出记录
            self.session_history[session_id].append({
                "timestamp": time.time(),
                "output": output
            })
            
            # 限制历史记录大小
            if len(self.session_history[session_id]) > 1000:
                # 保留最近的500条
                self.session_history[session_id] = self.session_history[session_id][-500:]
            
            # 更新当前输出
            if session_id in self.active_sessions:
                self.active_sessions[session_id]["current_output"] += output
                # 限制当前输出大小
                if len(self.active_sessions[session_id]["current_output"]) > 50000:
                    self.active_sessions[session_id]["current_output"] = \
                        self.active_sessions[session_id]["current_output"][-25000:]
    
    def _monitor_sessions(self):
        """会话监控线程"""
        while self.running:
            try:
                # 检查会话活动状态
                with self.session_lock:
                    current_time = time.time()
                    for session_id, session in list(self.active_sessions.items()):
                        # 检查空闲会话，超过4小时未活动则关闭
                        idle_time = current_time - session["last_activity"]
                        if idle_time > 14400 and session["status"] == "connected":  # 4小时 = 14400秒
                            print_warning(f"会话 {session_id} 空闲超过4小时，自动关闭")
                            self.close_session(session_id)
                        
                        # 检查僵尸会话
                        if session["status"] in ["error", "disconnected"]:
                            # 检查僵尸会话是否已经存在超过1小时
                            if current_time - session["last_activity"] > 3600:
                                print_warning(f"僵尸会话 {session_id} 已超过1小时，清理")
                                # 从活跃会话列表中移除
                                del self.active_sessions[session_id]
                
                # 睡眠一段时间
                time.sleep(60)  # 每分钟检查一次
                
            except Exception as e:
                print_error(f"会话监控线程错误: {str(e)}")
                time.sleep(120)  # 出错后等待较长时间
    
    def _detect_os_from_output(self, output: str) -> Dict[str, str]:
        """从SSH输出检测操作系统类型"""
        output = output.lower()
        os_info = {"os_type": "Unknown", "version": "Unknown"}
        
        if "linux" in output:
            os_info["os_type"] = "Linux"
            # 尝试确定Linux发行版
            if "ubuntu" in output:
                os_info["os_type"] = "Ubuntu"
            elif "centos" in output:
                os_info["os_type"] = "CentOS"
            elif "debian" in output:
                os_info["os_type"] = "Debian"
            elif "fedora" in output:
                os_info["os_type"] = "Fedora"
        elif "darwin" in output or "mac" in output:
            os_info["os_type"] = "macOS"
        elif "windows" in output:
            os_info["os_type"] = "Windows"
        elif "bsd" in output:
            os_info["os_type"] = "BSD"
        
        # 尝试提取版本号
        version_match = re.search(r'(\d+\.\d+\.\d+)', output)
        if version_match:
            os_info["version"] = version_match.group(1)
        
        return os_info
    
    def _is_prompt_line(self, text: str) -> bool:
        """检查文本是否包含命令提示符"""
        # 通用Unix提示符模式
        unix_prompt = re.compile(r'[\w\-\.]+@[\w\-\.]+:[~\w\/\.\-]*[$#>]\s*$')
        # Windows提示符模式
        windows_prompt = re.compile(r'[A-Za-z]:\\.*>\s*$')
        
        lines = text.split('\n')
        last_line = lines[-1] if lines else ""
        
        return bool(unix_prompt.search(last_line) or windows_prompt.search(last_line))
    
    def _needs_auto_response(self, text: str) -> bool:
        """检查是否需要自动响应"""
        # 常见需要响应的模式
        patterns = [
            r'\[y/n\]',
            r'\(yes/no\)',
            r'\(y/n\)',
            r'continue\?',
            r'proceed\?',
            r'are you sure',
            r'confirmation'
        ]
        
        return any(re.search(pattern, text, re.IGNORECASE) for pattern in patterns)
    
    def _generate_contextual_response(self, prompt_text: str, session_state: Dict[str, Any]) -> str:
        """根据上下文生成智能响应"""
        try:
            # 准备更详细的上下文
            recent_context = "\n".join([
                f">{'>' if item['type'] == 'input' else ' '} {item['content']}"
                for item in session_state["context_buffer"][-10:]  # 最近10条交互
            ])
            
            # 组建更智能的提示
            messages = [
                {"role": "system", "content": (
                    f"你是SSH智能助手，为远程系统({session_state['os_info']['os_type']} "
                    f"{session_state['os_info'].get('version', '')})生成最佳响应。\n"
                    f"当前命令: {session_state['current_command']}\n"
                    f"任务状态: {session_state['task_state']}\n"
                    f"命令状态: {session_state['command_state']}"
                )},
                {"role": "user", "content": (
                    f"以下是最近的SSH交互历史:\n\n{recent_context}\n\n"
                    f"当前需要响应的提示:\n{prompt_text}\n\n"
                    f"请生成最合适的响应，只需直接输出应该输入的内容，不要解释。"
                )}
            ]
            
            response = self.llm_client.chat.completions.create(
                model="deepseek-chat",
                messages=messages,
                temperature=0.3
            )
            
            auto_response = response.choices[0].message.content.strip()
            
            # 对于简单的确认类问题，验证返回结果的合理性
            if any(pattern in prompt_text.lower() for pattern in ['[y/n]', '(yes/no)', 'continue?']):
                if len(auto_response) > 3 or (auto_response.lower() not in ['y', 'n', 'yes', 'no']):
                    return 'y'  # 如果LLM返回了不合理的响应，就使用默认的"y"
            
            return auto_response
            
        except Exception as e:
            print_error(f"上下文响应生成失败: {str(e)}")
            # 提供默认响应
            if "[y/n]" in prompt_text.lower() or "(yes/no)" in prompt_text.lower():
                return "y"  # 默认确认
            else:
                return ""  # 默认空响应
    
    def _analyze_command_result(self, session_state: Dict[str, Any], output: str):
        """分析命令执行结果并更新会话状态"""
        try:
            # 如果没有当前命令，无需分析
            if not session_state["current_command"]:
                return
            
            # 简单分析常见命令结果
            cmd = session_state["current_command"].strip()
            
            # 检查是否是探索性命令
            if cmd in ['ls', 'ls -la', 'ls -l', 'dir', 'pwd', 'whoami', 'id', 'uname -a', 'cat /etc/os-release']:
                session_state["task_state"] = "exploring"
            
            # 检查是否是安装/配置命令
            if any(x in cmd for x in ['apt', 'yum', 'dnf', 'brew', 'install', 'config', 'setup', 'systemctl']):
                session_state["task_state"] = "configuring"
            
            # 如果命令产生了错误
            if session_state["command_state"] == "error":
                # 可以根据错误类型生成建议的修复命令
                if "permission denied" in output.lower() or "权限不足" in output:
                    print_info(f"检测到权限问题，可能需要使用sudo")
                elif "command not found" in output.lower():
                    print_info(f"命令未找到，可能需要安装相关软件包")
        
        except Exception as e:
            print_error(f"分析命令结果失败: {str(e)}")
    
    def _extract_error_message(self, output: str) -> str:
        """从输出中提取错误信息"""
        # 尝试寻找常见的错误标记
        error_lines = []
        for line in output.split('\n'):
            if any(x in line.lower() for x in ['error', 'failed', 'fatal', '错误', '失败']):
                error_lines.append(line.strip())
        
        if error_lines:
            return '\n'.join(error_lines[-3:])  # 返回最后3条错误信息
        return "未能提取具体错误信息"


class SSHEnhancedController:
    """增强版SSH控制器，支持更智能的交互和自动响应"""
    
    def __init__(self):
        """初始化SSH控制器"""
        self.connection_cache = SSHConnectionCache()
        self.server_cache = ServerInfoCache()
        self.llm_client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")
        self.credential_store = {}  # 用于临时存储凭据
        # 初始化持久会话管理器
        self.session_manager = PersistentSSHManager()
    
    async def execute_command(self, host: str, username: str, password: str, command: str) -> str:
        """执行单个SSH命令"""
        try:
            # 获取SSH连接
            client = self.connection_cache.get_connection(host, username, password)
            if not client:
                return f"SSH连接失败: {username}@{host}"
            
            # 执行命令
            print_info(f"执行SSH命令: {command}")
            stdin, stdout, stderr = client.exec_command(command, timeout=120)
            
            # 获取输出
            output = stdout.read().decode('utf-8', errors='replace')
            error = stderr.read().decode('utf-8', errors='replace')
            
            # 组合结果
            result = output
            if error:
                result += f"\n错误输出:\n{error}"
            
            return result
        except Exception as e:
            error_detail = traceback.format_exc()
            print_error(f"SSH命令执行失败: {str(e)}\n{error_detail}")
            return f"SSH命令执行失败: {str(e)}"
    
    async def interactive_session(self, host: str, username: str, password: str, initial_command: str = "") -> str:
        """创建交互式SSH会话，使用多线程架构分离SSH和Agent逻辑"""
        try:
            print_info(f"开始创建交互式SSH会话: {username}@{host}")
            
            # 创建交互队列
            interaction_queue = InteractionQueue()
            
            # 创建结果队列，用于返回会话结果
            result_queue = queue.Queue()
            
            # 创建SSH会话线程
            ssh_thread = threading.Thread(
                target=self._ssh_session_thread,
                args=(host, username, password, initial_command, interaction_queue, result_queue)
            )
            
            # 创建Agent处理线程
            agent_thread = threading.Thread(
                target=self._agent_processing_thread,
                args=(interaction_queue, host, username, password)
            )
            
            # 启动线程
            ssh_thread.daemon = True
            agent_thread.daemon = True
            
            ssh_thread.start()
            agent_thread.start()
            
            # 等待SSH线程完成
            ssh_thread.join(timeout=900)  # 最长等待15分钟
            
            # 发送停止信号
            interaction_queue.stop()
            
            # 等待Agent线程完成
            agent_thread.join(timeout=10)
            
            # 获取会话结果
            try:
                session_result = result_queue.get(timeout=5)
                return session_result
            except queue.Empty:
                return "SSH会话已完成，但未返回结果"
            
        except Exception as e:
            error_detail = traceback.format_exc()
            print_error(f"SSH交互会话失败: {str(e)}\n{error_detail}")
            return f"SSH交互会话失败: {str(e)}"
    
    def _ssh_session_thread(self, host: str, username: str, password: str, 
                           initial_command: str, interaction_queue: InteractionQueue,
                           result_queue: queue.Queue):
        """SSH会话线程，处理SSH连接和数据传输"""
        try:
            # 获取SSH客户端
            client = paramiko.SSHClient()
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            
            # 连接信息提示
            print_info(f"[SSH线程] 正在连接到 {username}@{host}...")
            
            # 尝试连接
            client.connect(host, username=username, password=password, timeout=15)
            print_success("[SSH线程] SSH连接成功")
            
            # 创建交互式shell
            shell = client.invoke_shell()
            shell.settimeout(10)  # 设置较短的超时，允许定期检查队列
            
            # 清除初始欢迎信息
            time.sleep(1)
            initial_output = ""
            while shell.recv_ready():
                initial_output += shell.recv(4096).decode('utf-8', errors='replace')
            
            # 将初始输出放入队列
            if initial_output:
                interaction_queue.put_output(initial_output)
            
            # 发送初始命令
            if initial_command:
                print_info(f"[SSH线程] 发送初始命令: {initial_command}")
                shell.send(initial_command + "\n")
            
            # 设置会话超时
            session_timeout = 900  # 15分钟
            start_time = time.time()
            
            # 存储完整输出
            full_output = initial_output
            
            # 主循环
            while not interaction_queue.is_stopped() and time.time() - start_time < session_timeout:
                try:
                    # 检查SSH输出
                    if shell.recv_ready():
                        output = shell.recv(4096).decode('utf-8', errors='replace')
                        if output:
                            print(output, end='', flush=True)  # 实时显示输出
                            full_output += output
                            interaction_queue.put_output(output)
                    
                    # 检查是否有Agent输入
                    agent_input = interaction_queue.get_input(timeout=0.5)
                    if agent_input is not None:
                        print_info(f"[SSH线程] 收到Agent输入: {agent_input}")
                        shell.send(agent_input + "\n")
                    
                    # 检查会话是否结束
                    if shell.exit_status_ready():
                        print_info("[SSH线程] SSH会话已退出")
                        break
                    
                    # 短暂休息，避免过度占用CPU
                    time.sleep(0.1)
                    
                except socket.timeout:
                    # 超时不是错误，继续检查
                    continue
                except Exception as e:
                    print_error(f"[SSH线程] 处理SSH交互时出错: {str(e)}")
                    interaction_queue.put_output(f"[错误] {str(e)}")
                    break
            
            # 会话完成，关闭连接
            shell.close()
            client.close()
            
            # 将完整输出放入结果队列
            result_queue.put(full_output)
            print_info("[SSH线程] SSH会话已完成")
            
        except Exception as e:
            error_detail = traceback.format_exc()
            print_error(f"[SSH线程] SSH会话失败: {str(e)}\n{error_detail}")
            result_queue.put(f"SSH会话失败: {str(e)}")
            interaction_queue.stop()
    
    def _agent_processing_thread(self, interaction_queue: InteractionQueue, host: str, username: str, password: str):
        """Agent处理线程，负责分析SSH输出并生成响应"""
        try:
            print_info("[Agent线程] 启动Agent处理")
            
            # 会话状态跟踪
            session_state = {
                "os_info": {"os_type": "Unknown", "version": "Unknown"},
                "current_command": "",
                "command_state": "idle",  # idle, running, waiting_for_response, error
                "last_command_time": time.time(),
                "command_history": [],
                "context_buffer": [],  # 保存最近的交互历史
                "task_state": "init",  # init, exploring, executing, analyzing, planning
                "task_steps": [],  # 如果有多步任务，记录步骤
                "step_index": 0
            }
            
            # 缓存最近的输出，用于上下文分析
            recent_outputs = []
            output_buffer = ""
            
            # 识别模式
            password_patterns = [
                r'\[sudo\].*?密码.*?:',
                r'\[sudo\].*?password.*?:',
                r'password.*?:',
                r'密码.*?:',
                r'Password for.*?:',
                r'Authentication password.*?:'
            ]
            
            error_patterns = [
                r'command not found',
                r'没有那个文件或目录',
                r'No such file or directory',
                r'permission denied',
                r'权限不足',
                r'cannot access',
                r'错误:',
                r'Error:',
                r'failed',
                r'Failed'
            ]
            
            success_patterns = [
                r'successfully',
                r'Successfully',
                r'成功',
                r'已完成',
                r'Completed',
                r'completed'
            ]
            
            # 主循环
            while not interaction_queue.is_stopped():
                # 获取SSH输出
                output = interaction_queue.get_output(timeout=1)
                if output is None:
                    # 如果长时间没有输出，考虑下一步操作
                    if session_state["command_state"] == "running" and \
                       time.time() - session_state["last_command_time"] > 30:
                        # 命令可能已悄悄完成或卡住，尝试检查状态
                        if self._is_prompt_line(output_buffer):
                            session_state["command_state"] = "idle"
                            print_info("[Agent线程] 命令似乎已完成")
                            self._analyze_command_result(session_state, output_buffer)
                            output_buffer = ""
                    continue
                
                # 更新最后活动时间
                session_state["last_command_time"] = time.time()
                
                # 添加到缓冲区和上下文
                output_buffer += output
                recent_outputs.append(output)
                session_state["context_buffer"].append({"type": "output", "content": output, "time": time.time()})
                if len(recent_outputs) > 10:
                    recent_outputs = recent_outputs[-10:]
                
                # 控制上下文缓冲区大小
                if len(session_state["context_buffer"]) > 20:
                    session_state["context_buffer"] = session_state["context_buffer"][-20:]
                
                # 如果需要检测操作系统
                if session_state["os_info"]["os_type"] == "Unknown" and len(output_buffer) > 20:
                    session_state["os_info"] = self._detect_os_from_output(output_buffer)
                    print_info(f"[Agent线程] 检测到远程系统: {session_state['os_info']['os_type']} {session_state['os_info'].get('version', '')}")
                
                # 检查是否需要输入密码
                if any(re.search(pattern, output_buffer, re.IGNORECASE) for pattern in password_patterns):
                    print_info("[Agent线程] 检测到密码提示，自动输入密码")
                    interaction_queue.put_input(password)
                    session_state["context_buffer"].append({"type": "input", "content": "<密码输入>", "time": time.time()})
                    output_buffer = ""  # 清空缓冲区
                    continue
                
                # 检查是否有其他需要响应的提示
                if self._needs_auto_response(output_buffer):
                    # 使用更智能的方式生成响应，考虑上下文
                    response = self._generate_contextual_response(output_buffer, session_state)
                    if response:
                        print_info(f"[Agent线程] 生成自动响应: {response}")
                        interaction_queue.put_input(response)
                        session_state["context_buffer"].append({"type": "input", "content": response, "time": time.time()})
                        output_buffer = ""  # 清空缓冲区
                        continue
                
                # 检查错误和成功信息
                if any(re.search(pattern, output_buffer, re.IGNORECASE) for pattern in error_patterns):
                    if session_state["command_state"] == "running":
                        session_state["command_state"] = "error"
                        print_warning(f"[Agent线程] 检测到错误: {self._extract_error_message(output_buffer)}")
                
                if any(re.search(pattern, output_buffer, re.IGNORECASE) for pattern in success_patterns):
                    if session_state["command_state"] == "running":
                        print_info(f"[Agent线程] 检测到成功信息")
                
                # 检查提示符以确认命令完成
                if self._is_prompt_line(output):
                    if session_state["command_state"] in ["running", "waiting_for_response"]:
                        session_state["command_state"] = "idle"
                        print_info("[Agent线程] 命令已完成")
                        
                        # 分析命令结果并考虑下一步操作
                        self._analyze_command_result(session_state, output_buffer)
                        
                        # 如果有多步任务，可能需要执行下一步
                        if session_state["task_state"] == "executing" and session_state["task_steps"]:
                            if session_state["step_index"] < len(session_state["task_steps"]) - 1:
                                session_state["step_index"] += 1
                                next_cmd = session_state["task_steps"][session_state["step_index"]]
                                print_info(f"[Agent线程] 执行下一步: {next_cmd}")
                                interaction_queue.put_input(next_cmd)
                                session_state["command_state"] = "running"
                                session_state["current_command"] = next_cmd
                                session_state["command_history"].append(next_cmd)
                                session_state["context_buffer"].append({"type": "input", "content": next_cmd, "time": time.time()})
                
                # 清空输出缓冲区
                output_buffer = ""
            
            # 控制缓冲区大小
            if len(output_buffer) > 10000:
                output_buffer = output_buffer[-5000:]
        
            print_info("[Agent线程] Agent处理已完成")
            
        except Exception as e:
            error_detail = traceback.format_exc()
            print_error(f"[Agent线程] 处理失败: {str(e)}\n{error_detail}")
    
    def _detect_os_from_output(self, output: str) -> Dict[str, str]:
        """从SSH输出检测操作系统信息"""
        output = output.lower()
        os_info = {"os_type": "Unknown", "version": "Unknown"}
        
        if "linux" in output:
            os_info["os_type"] = "Linux"
            # 尝试确定Linux发行版
            if "ubuntu" in output:
                os_info["os_type"] = "Ubuntu"
            elif "centos" in output:
                os_info["os_type"] = "CentOS"
            elif "debian" in output:
                os_info["os_type"] = "Debian"
            elif "fedora" in output:
                os_info["os_type"] = "Fedora"
        elif "darwin" in output or "mac" in output:
            os_info["os_type"] = "macOS"
        elif "windows" in output:
            os_info["os_type"] = "Windows"
        elif "bsd" in output:
            os_info["os_type"] = "BSD"
        
        # 尝试提取版本号
        version_match = re.search(r'(\d+\.\d+\.\d+)', output)
        if version_match:
            os_info["version"] = version_match.group(1)
        
        return os_info
    
    def _is_prompt_line(self, text: str) -> bool:
        """检查文本是否包含命令提示符"""
        # 通用Unix提示符模式
        unix_prompt = re.compile(r'[\w\-\.]+@[\w\-\.]+:[~\w\/\.\-]*[$#>]\s*$')
        # Windows提示符模式
        windows_prompt = re.compile(r'[A-Za-z]:\\.*>\s*$')
        
        lines = text.split('\n')
        last_line = lines[-1] if lines else ""
        
        return bool(unix_prompt.search(last_line) or windows_prompt.search(last_line))
    
    def _needs_auto_response(self, text: str) -> bool:
        """检查是否需要自动响应"""
        # 常见需要响应的模式
        patterns = [
            r'\[y/n\]',
            r'\(yes/no\)',
            r'\(y/n\)',
            r'continue\?',
            r'proceed\?',
            r'are you sure',
            r'confirmation'
        ]
        
        return any(re.search(pattern, text, re.IGNORECASE) for pattern in patterns)
    
    def _generate_contextual_response(self, prompt_text: str, session_state: Dict[str, Any]) -> str:
        """根据上下文生成智能响应"""
        try:
            # 准备更详细的上下文
            recent_context = "\n".join([
                f">{'>' if item['type'] == 'input' else ' '} {item['content']}"
                for item in session_state["context_buffer"][-10:]  # 最近10条交互
            ])
            
            # 组建更智能的提示
            messages = [
                {"role": "system", "content": (
                    f"你是SSH智能助手，为远程系统({session_state['os_info']['os_type']} "
                    f"{session_state['os_info'].get('version', '')})生成最佳响应。\n"
                    f"当前命令: {session_state['current_command']}\n"
                    f"任务状态: {session_state['task_state']}\n"
                    f"命令状态: {session_state['command_state']}"
                )},
                {"role": "user", "content": (
                    f"以下是最近的SSH交互历史:\n\n{recent_context}\n\n"
                    f"当前需要响应的提示:\n{prompt_text}\n\n"
                    f"请生成最合适的响应，只需直接输出应该输入的内容，不要解释。"
                )}
            ]
            
            response = self.llm_client.chat.completions.create(
                model="deepseek-chat",
                messages=messages,
                temperature=0.3
            )
            
            auto_response = response.choices[0].message.content.strip()
            
            # 对于简单的确认类问题，验证返回结果的合理性
            if any(pattern in prompt_text.lower() for pattern in ['[y/n]', '(yes/no)', 'continue?']):
                if len(auto_response) > 3 or (auto_response.lower() not in ['y', 'n', 'yes', 'no']):
                    return 'y'  # 如果LLM返回了不合理的响应，就使用默认的"y"
            
            return auto_response
            
        except Exception as e:
            print_error(f"上下文响应生成失败: {str(e)}")
            # 提供默认响应
            if "[y/n]" in prompt_text.lower() or "(yes/no)" in prompt_text.lower():
                return "y"  # 默认确认
            else:
                return ""  # 默认空响应
    
    def _analyze_command_result(self, session_state: Dict[str, Any], output: str):
        """分析命令执行结果并更新会话状态"""
        try:
            # 如果没有当前命令，无需分析
            if not session_state["current_command"]:
                return
            
            # 简单分析常见命令结果
            cmd = session_state["current_command"].strip()
            
            # 检查是否是探索性命令
            if cmd in ['ls', 'ls -la', 'ls -l', 'dir', 'pwd', 'whoami', 'id', 'uname -a', 'cat /etc/os-release']:
                session_state["task_state"] = "exploring"
            
            # 检查是否是安装/配置命令
            if any(x in cmd for x in ['apt', 'yum', 'dnf', 'brew', 'install', 'config', 'setup', 'systemctl']):
                session_state["task_state"] = "configuring"
            
            # 如果命令产生了错误
            if session_state["command_state"] == "error":
                # 可以根据错误类型生成建议的修复命令
                if "permission denied" in output.lower() or "权限不足" in output:
                    print_info(f"检测到权限问题，可能需要使用sudo")
                elif "command not found" in output.lower():
                    print_info(f"命令未找到，可能需要安装相关软件包")
        
        except Exception as e:
            print_error(f"分析命令结果失败: {str(e)}")
    
    def _extract_error_message(self, output: str) -> str:
        """从输出中提取错误信息"""
        # 尝试寻找常见的错误标记
        error_lines = []
        for line in output.split('\n'):
            if any(x in line.lower() for x in ['error', 'failed', 'fatal', '错误', '失败']):
                error_lines.append(line.strip())
        
        if error_lines:
            return '\n'.join(error_lines[-3:])  # 返回最后3条错误信息
        return "未能提取具体错误信息"

    async def execute_task(self, session_id: str, task_description: str) -> bool:
        """
        执行复杂任务，让Agent智能规划并执行多步骤命令
        
        Args:
            session_id: 会话ID
            task_description: 任务描述
            
        Returns:
            bool: 任务是否成功执行
        """
        try:
            with self.session_lock:
                if session_id not in self.active_sessions:
                    print_error(f"会话不存在: {session_id}")
                    return False
                
                session_info = self.active_sessions[session_id]
                if session_info["status"] != "connected":
                    print_error(f"会话未连接: {session_id}")
                    return False
                
                # 获取会话状态信息
                os_info = session_info["os_info"]
                session_output = self.get_session_output(session_id)
                
                print_info(f"[会话 {session_id}] 开始规划任务: {task_description}")
                
                # 使用LLM规划任务步骤
                messages = [
                    {"role": "system", "content": (
                        f"你是SSH任务规划专家，需要将复杂任务分解为在远程服务器({os_info['os_type']} {os_info.get('version', '')})上的具体命令步骤。"
                    )},
                    {"role": "user", "content": (
                        f"目标任务: {task_description}\n\n"
                        f"已知会话信息:\n"
                        f"- 操作系统: {os_info['os_type']} {os_info.get('version', '')}\n"
                        f"- 最近输出示例: {session_output[-500:] if len(session_output) > 500 else session_output}\n\n"
                        f"请将任务分解为3-10个具体的命令步骤，以便自动执行。直接返回JSON格式的命令列表:\n"
                        f"[\n  \"命令1\",\n  \"命令2\",\n  ...\n]"
                    )}
                ]
                
                response = self.llm_client.chat.completions.create(
                    model="deepseek-chat",
                    messages=messages,
                    temperature=0.3
                )
                
                # 尝试解析返回的命令列表
                try:
                    response_text = response.choices[0].message.content.strip()
                    
                    # 提取JSON部分
                    json_match = re.search(r'\[\s*".*"\s*\]', response_text, re.DOTALL)
                    if json_match:
                        response_text = json_match.group(0)
                    
                    # 清理并解析JSON
                    cleaned_text = response_text.replace("'", "\"")
                    task_steps = json.loads(cleaned_text)
                    
                    # 验证返回的步骤
                    if not isinstance(task_steps, list) or len(task_steps) == 0:
                        raise ValueError("返回的不是有效的命令列表")
                    
                    print_info(f"[会话 {session_id}] 规划了{len(task_steps)}个步骤的任务:")
                    for i, step in enumerate(task_steps):
                        print_info(f"  步骤{i+1}: {step}")
                    
                    # 获取交互队列
                    queue = self.interaction_queues.get(session_id)
                    if not queue:
                        print_error(f"会话队列不存在: {session_id}")
                        return False
                    
                    # 向Agent线程发送任务信息
                    with self.session_lock:
                        if session_id in self.active_sessions:
                            # 尝试获取相关的Agent线程
                            agent_thread = self.agent_threads.get(session_id)
                            if agent_thread and hasattr(agent_thread, '_target'):
                                # 更新线程的状态
                                for thread_id, thread in threading._active.items():
                                    if thread is agent_thread:
                                        # 创建特殊消息通知Agent线程
                                        task_message = {
                                            "type": "task",
                                            "steps": task_steps,
                                            "description": task_description
                                        }
                                        
                                        # 发送第一条命令
                                        first_command = task_steps[0]
                                        print_info(f"[会话 {session_id}] 执行第一个步骤: {first_command}")
                                        queue.put_input(first_command)
                                        
                                        return True
                
                    # 如果找不到Agent线程，则使用常规方式执行第一个命令
                    first_command = task_steps[0]
                    print_info(f"[会话 {session_id}] 执行第一个步骤: {first_command}")
                    return await self.send_command(session_id, first_command)
                    
                except Exception as e:
                    print_error(f"解析任务步骤失败: {str(e)}")
                    # 如果解析失败，尝试直接执行任务描述作为命令
                    print_warning(f"将直接尝试执行任务描述作为命令")
                    return await self.send_command(session_id, task_description)
        
        except Exception as e:
            print_error(f"执行任务失败: {str(e)}")
            return False

    async def _clear_buffer(self, shell):
        """清除缓冲区"""
        while shell.recv_ready():
            shell.recv(4096)
        await asyncio.sleep(0.5)

    async def create_persistent_session(self, host: str, username: str, password: str, 
                                       initial_command: str = "") -> str:
        """创建持久化SSH会话"""
        # 启动会话管理器（如果尚未启动）
        if not self.session_manager.running:
            self.session_manager.start()
        
        # 创建会话
        session_id = self.session_manager.create_session(
            host=host,
            username=username,
            password=password,
            initial_command=initial_command
        )
        
        return session_id

    async def send_to_session(self, session_id: str, command: str) -> bool:
        """向会话发送命令"""
        return self.session_manager.send_command(session_id, command)

    async def get_session_output(self, session_id: str, since_time: float = None) -> str:
        """获取会话输出"""
        return self.session_manager.get_session_output(session_id, since_time)

    async def get_session_status(self, session_id: str) -> Dict[str, Any]:
        """获取会话状态"""
        return self.session_manager.get_session_status(session_id)

    async def close_session(self, session_id: str) -> bool:
        """关闭会话"""
        return self.session_manager.close_session(session_id)

    async def list_sessions(self) -> List[Dict[str, Any]]:
        """列出所有会话"""
        return self.session_manager.list_sessions()

    async def monitor_session(self, session_id: str, callback_function=None) -> None:
        """
        开始监控SSH会话，可选地提供回调函数处理输出
        
        Args:
            session_id: 会话ID
            callback_function: 回调函数，接收(output, time)作为参数
        """
        last_check_time = time.time()
        
        while True:
            try:
                # 检查会话状态
                status = await self.get_session_status(session_id)
                if status["status"] != "connected":
                    print_info(f"会话 {session_id} 已断开连接，停止监控")
                    break
                
                # 获取新输出
                output = await self.get_session_output(session_id, last_check_time)
                if output:
                    # 更新最后检查时间
                    current_time = time.time()
                    
                    # 如果提供了回调函数，调用它
                    if callback_function and callable(callback_function):
                        await callback_function(output, current_time)
                    
                    last_check_time = current_time
                
                # 适度休眠，避免过度占用资源
                await asyncio.sleep(0.5)
                
            except Exception as e:
                print_error(f"监控会话出错: {str(e)}")
                await asyncio.sleep(5)  # 出错后等待较长时间

    async def interactive_agent_session(self, host: str, username: str, password: str, 
                                      task_description: str = None) -> str:
        """
        创建由Agent驱动的交互式会话，可选提供任务描述
        
        Args:
            host: 主机地址
            username: 用户名
            password: 密码
            task_description: 任务描述，如果提供则Agent会尝试完成任务
            
        Returns:
            session_id: 会话ID
        """
        try:
            # 创建持久会话
            session_id = await self.create_persistent_session(host, username, password)
            
            # 如果有任务描述，交给Agent处理
            if task_description:
                print_info(f"Agent任务: {task_description}")
                await self.execute_task(session_id, task_description)
            
            return session_id
        
        except Exception as e:
            print_error(f"创建Agent驱动会话失败: {str(e)}")
            return f"创建Agent驱动会话失败: {str(e)}"

# 测试函数
async def test_ssh():
    controller = SSHEnhancedController()
    result = await controller.interactive_session(
        host="192.168.1.100",
        username="test",
        password="password",
        initial_command="ls -la"
    )
    print(result)

if __name__ == "__main__":
    asyncio.run(test_ssh()) 