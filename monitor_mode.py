import asyncio
import os
import time
import traceback
import re
import json
from typing import List, Dict, Any, Optional, Tuple, Union
from datetime import datetime
import threading
import queue
import importlib
import sys
import random

# 导入项目中的其他模块
# 注意：请确保已安装必要的依赖
# pip install openai paramiko
try:
    from deepseekAPI import client, tools, ask_user_to_continue, num_tokens_from_messages
    
    # 条件导入system_utils
    try:
        import system_utils
    except ImportError:
        print("警告: 未找到system_utils模块，系统命令功能将不可用")
        # 创建一个空对象作为替代
        class EmptyModule: pass
        system_utils = EmptyModule()
    
    # 条件导入file_utils
    try:
        import file_utils
    except ImportError:
        print("警告: 未找到file_utils模块，文件操作功能将不可用")
        # 创建一个空对象作为替代
        class EmptyModule: pass
        file_utils = EmptyModule()
        
    from ssh_controller_enhanced import SSHEnhancedController
except ImportError as e:
    print(f"错误: 缺少必要的依赖项: {e}")
    print("请运行以下命令安装: pip install openai paramiko")
    exit(1)

import get_email
import send_email
from console_utils import print_color, print_success, print_error, print_warning, print_info, print_highlight

# 注册SSH工具到工具列表
def register_tools(tools_list):
    """向工具列表添加各种工具"""
    # SSH工具
    ssh_tools = [
        {
            "type": "function",
            "function": {
                "name": "ssh_command",
                "description": "在远程服务器上执行单个SSH命令",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "host": {
                            "type": "string",
                            "description": "远程服务器的IP地址或主机名"
                        },
                        "username": {
                            "type": "string",
                            "description": "SSH连接的用户名"
                        },
                        "password": {
                            "type": "string",
                            "description": "SSH连接的密码"
                        },
                        "command": {
                            "type": "string",
                            "description": "要执行的命令"
                        }
                    },
                    "required": ["host", "username", "password", "command"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "ssh_interactive",
                "description": "创建交互式SSH会话，用于执行多个命令或处理需要交互的命令",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "host": {
                            "type": "string",
                            "description": "远程服务器的IP地址或主机名"
                        },
                        "username": {
                            "type": "string",
                            "description": "SSH连接的用户名"
                        },
                        "password": {
                            "type": "string",
                            "description": "SSH连接的密码"
                        },
                        "initial_command": {
                            "type": "string",
                            "description": "初始执行的命令"
                        }
                    },
                    "required": ["host", "username", "password"]
                }
            }
        }
    ]
    
    # 邮件工具
    email_tools = [
        {
            "type": "function",
            "function": {
                "name": "send_email",
                "description": "发送邮件给指定收件人",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "content": {
                            "type": "string",
                            "description": "邮件内容"
                        },
                        "receiver": {
                            "type": "string",
                            "description": "收件人邮箱"
                        },
                        "subject": {
                            "type": "string",
                            "description": "邮件主题"
                        },
                        "attachments": {
                            "type": "string",
                            "description": "附件路径，多个附件用逗号分隔"
                        }
                    },
                    "required": ["content", "receiver", "subject"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "check_email",
                "description": "检查并获取最新的邮件",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "max_emails": {
                            "type": "integer",
                            "description": "获取的最大邮件数量"
                        }
                    },
                    "required": []
                }
            }
        }
    ]
    
    # 代码操作工具
    code_tools = [
        {
            "type": "function",
            "function": {
                "name": "write_script",
                "description": "创建或更新脚本文件",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "filename": {
                            "type": "string",
                            "description": "脚本文件名，例如 monitor.py, check_status.sh"
                        },
                        "content": {
                            "type": "string",
                            "description": "脚本内容"
                        },
                        "mode": {
                            "type": "string",
                            "description": "写入模式：'w'表示覆盖，'a'表示追加",
                            "enum": ["w", "a"]
                        }
                    },
                    "required": ["filename", "content"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "execute_local_script",
                "description": "在本地执行脚本",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "filename": {
                            "type": "string",
                            "description": "要执行的脚本文件名"
                        },
                        "args": {
                            "type": "string",
                            "description": "脚本参数，多个参数用空格分隔"
                        }
                    },
                    "required": ["filename"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "execute_remote_script",
                "description": "在远程服务器上执行脚本",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "host": {
                            "type": "string",
                            "description": "远程服务器的IP地址或主机名"
                        },
                        "username": {
                            "type": "string",
                            "description": "SSH连接的用户名"
                        },
                        "password": {
                            "type": "string",
                            "description": "SSH连接的密码"
                        },
                        "script_content": {
                            "type": "string",
                            "description": "脚本内容，将首先上传到远程服务器"
                        },
                        "filename": {
                            "type": "string",
                            "description": "要执行的脚本文件名"
                        }
                    },
                    "required": ["host", "username", "password", "script_content"]
                }
            }
        }
    ]
    
    # 添加所有工具到工具列表
    tools_list.extend(ssh_tools)
    tools_list.extend(email_tools)
    tools_list.extend(code_tools)
    return tools_list

# 确保所有工具可用
all_tools = register_tools(tools.copy())

class MonitorMode:
    """监听模式类，用于运维监控场景，支持无限迭代执行任务"""
    
    def __init__(self):
        """初始化监听模式"""
        self.messages = [{"role": "system", "content": "你是一个智能运维助手，负责规划和执行各种系统管理任务。你擅长分析任务需求，制定详细计划，并使用各种工具来完成任务。你能够连接远程服务器，执行命令，监控系统状态，编写和执行脚本。你应该保持高效、专业的工作方式，确保任务顺利完成。在遇到问题时，你应该积极寻找解决方案，而不是等待用户指示。你应该仅在发现错误或异常状态时向管理员发送报告，正常运行无需打扰管理员。"}]
        self.ssh = SSHEnhancedController()
        self.running = False
        self.task_queue = queue.Queue()
        self.root_users = self._load_root_users()
        self.last_email_check = 0
        self.email_check_interval = 30  # 检查邮件的间隔(秒)
        self.processed_email_ids = set()  # 已处理的邮件ID集合
        self.processed_emails_details = {}  # 存储已处理邮件的详细信息，包括时间戳、主题等
        self.current_task = None  # 当前正在执行的任务
        self.current_task_messages = []  # 当前任务的消息历史
        
        # Token管理
        self.max_tokens = 3000  # 保留的最大token数
        self.token_check_interval = 5  # 每5次迭代检查一次token

        # 初始化工具映射表
        self.tool_mapping = {
            # SSH相关工具
            "ssh_command": self.ssh_command,
            "ssh_interactive": self.ssh_interactive,
            "ssh": self.ssh_interactive,  # 添加别名，支持简单的ssh命名
            
            # 系统工具 - 安全地添加系统工具
            **({"powershell_command": system_utils.powershell_command, 
                "cmd_command": system_utils.cmd_command} 
               if hasattr(system_utils, 'powershell_command') else {}),
            
            # 邮件工具
            "send_email": send_email.main,
            "send_mail": send_email.main,  # 添加别名，支持send_mail命名
            "check_email": get_email.EmailRetriever.retrieve_emails,
            
            # 输入输出工具
            "user_input": self._ask_user_input,
            
            # 代码操作工具
            "write_script": self.write_script,
            "execute_local_script": self.execute_local_script,
            "execute_remote_script": self.execute_remote_script
        }
    
        # SSH会话管理
        self.ssh_controller = SSHEnhancedController()
        self.active_sessions = {}  # {task_context_id: session_id}
        
        # 启动SSH会话管理器
        self.session_manager_started = False
    
    async def _ask_user_input(self, prompt="请输入：", timeout=60):
        """获取用户输入的包装函数"""
        try:
            loop = asyncio.get_event_loop()
            print(prompt)
            future = loop.run_in_executor(None, input)
            return await asyncio.wait_for(future, timeout=timeout)
        except asyncio.TimeoutError:
            print_warning(f"输入超时(超过{timeout}秒)")
            return None
        except Exception as e:
            print_error(f"获取用户输入失败: {str(e)}")
            return None
        
    def _load_root_users(self) -> List[str]:
        """加载root用户列表"""
        try:
            if not os.path.exists('root_users.txt'):
                # 如果文件不存在，创建默认的root用户列表
                with open('root_users.txt', 'w', encoding='utf-8') as f:
                    f.write("# 管理员邮箱列表 - 只有这些邮箱可以发送指令\n")
                    admin_email = os.environ.get("QQ_EMAIL", "1792491376@qq.com")
                    f.write(f"{admin_email}\n")
                    f.write("# 添加更多管理员邮箱，每行一个\n")
                    print_info("已创建默认root用户列表文件: root_users.txt")
            
            # 读取root用户列表
            with open('root_users.txt', 'r', encoding='utf-8') as f:
                lines = f.readlines()
            
            # 过滤注释行和空行，并去除每行的空白字符
            emails = [line.strip() for line in lines if line.strip() and not line.strip().startswith('#')]
            print_info(f"已加载 {len(emails)} 个root用户邮箱")
            return emails
        except Exception as e:
            print_error(f"加载root用户列表失败: {str(e)}")
            # 返回默认的管理员邮箱
            default_email = os.environ.get("QQ_EMAIL", "1792491376@qq.com")
            return [default_email]
    
    async def _is_stop_command(self, message_content: str) -> Tuple[bool, float]:
        """
        使用LLM判断邮件内容是否为终止命令
        
        Args:
            message_content: 邮件内容
            
        Returns:
            tuple: (是否终止命令, 置信度)
        """
        try:
            # 构建系统提示和用户消息
            system_prompt = "你需要判断以下消息是否表达了'希望终止当前运行的程序'的意图。只考虑消息的语义内容，不要被特定词汇所限制。"
            user_prompt = f"请分析以下消息内容，判断发送者是否想要终止或停止当前正在运行的程序或任务：\n\n{message_content}\n\n你的回答应该是：\n1. 第一行：'是'或'否'\n2. 第二行：置信度(0-1)\n3. 第三行：简短理由"
            
            # 调用LLM进行分析
            response = client.chat.completions.create(
                model="deepseek-chat",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.1
            )
            
            analysis = response.choices[0].message.content
            
            # 解析回答
            lines = analysis.strip().split('\n')
            is_stop = "是" in lines[0].lower()
            
            # 提取置信度
            confidence = 0.5  # 默认置信度
            if len(lines) > 1:
                confidence_match = re.search(r'([\d\.]+)', lines[1])
                if confidence_match:
                    confidence = float(confidence_match.group(1))
            
            # 提取理由
            reason = lines[2] if len(lines) > 2 else "无理由提供"
            
            print_info(f"LLM分析结果: {'终止命令' if is_stop else '非终止命令'}, 置信度: {confidence}, 理由: {reason}")
            
            return is_stop, confidence
            
        except Exception as e:
            print_error(f"LLM分析失败: {str(e)}")
            # 如果LLM分析失败，默认返回非终止命令
            return False, 0.0
    
    async def _analyze_email_intent(self, subject: str, body: str) -> Tuple[str, bool, bool]:
        """
        分析邮件意图，判断是新任务、任务补充还是终止命令
        
        Args:
            subject: 邮件主题
            body: 邮件正文
            
        Returns:
            tuple: (邮件内容, 是否终止命令, 是否任务补充)
        """
        try:
            # 1. 检查是否为终止命令
            is_stop, stop_confidence = await self._is_stop_command(body)
            if is_stop and stop_confidence >= 0.7:
                return body, True, False
                
            # 2. 使用LLM判断是否为任务补充
            system_prompt = f"""
            你需要判断以下消息是否是对正在执行任务的补充信息或新指令。
            
            当前执行的任务: {self.current_task if self.current_task else '无'}
            
            判断标准:
            - 如果消息内容是为当前任务提供额外信息、参数或指导，则为"任务补充"
            - 如果消息内容是全新的、独立的指令，则为"新任务"
            """
            
            user_prompt = f"请分析以下消息内容，判断是任务补充还是新任务：\n\n主题：{subject}\n正文：{body}\n\n你的回答应该是：\n1. 第一行：'任务补充'或'新任务'\n2. 第二行：置信度(0-1)\n3. 第三行：简短理由"
            
            response = client.chat.completions.create(
                model="deepseek-chat",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.1
            )
            
            analysis = response.choices[0].message.content
            
            # 解析回答
            lines = analysis.strip().split('\n')
            is_supplement = "任务补充" in lines[0]
            
            # 提取置信度
            confidence = 0.5  # 默认置信度
            if len(lines) > 1:
                confidence_match = re.search(r'([\d\.]+)', lines[1])
                if confidence_match:
                    confidence = float(confidence_match.group(1))
            
            # 提取理由
            reason = lines[2] if len(lines) > 2 else "无理由提供"
            
            print_info(f"LLM分析结果: {'任务补充' if is_supplement else '新任务'}, 置信度: {confidence}, 理由: {reason}")
            
            # 只有当当前有任务在执行且置信度足够高时，才认为是任务补充
            is_supplement_confirmed = is_supplement and confidence >= 0.7 and self.current_task is not None
            
            return body, False, is_supplement_confirmed
            
        except Exception as e:
            print_error(f"邮件意图分析失败: {str(e)}")
            # 如果分析失败，默认返回新任务
            return body, False, False
    
    async def check_email_commands(self) -> Tuple[Optional[str], bool, bool]:
        """
        检查邮件获取新指令
        
        Returns:
            tuple: (指令内容, 是否是终止命令, 是否是任务补充)
        """
        # 移除时间间隔检查，每次调用都执行邮件检查
        self.last_email_check = time.time()
        print_info("检查邮件中...")
        
        try:
            # 获取最新的3封邮件
            emails = get_email.EmailRetriever.retrieve_emails(3)
            if not emails:
                print_info("未找到邮件")
                return None, False, False
            
            # 只处理最新的一封邮件
            latest_email = emails[0]
            
            # 提取邮件关键信息
            email_id = latest_email.get('id')
            sender = latest_email.get('from', '')
            sent_time = latest_email.get('time', '')
            subject = latest_email.get('subject', '无主题')
            
            # 创建邮件特征指纹（ID + 时间 + 主题）用于重复检测
            email_fingerprint = f"{email_id}-{sent_time}-{subject}"
            
            # 检查是否已处理过（基于ID）
            if email_id in self.processed_email_ids:
                print_info(f"跳过已处理的邮件(ID): {subject}")
                return None, False, False
                
            # 检查是否基于时间戳和主题处理过
            for stored_id, details in self.processed_emails_details.items():
                if (details['time'] == sent_time and 
                    details['subject'] == subject and 
                    details['sender'] == sender):
                    print_info(f"跳过可能重复的邮件(时间+主题): {subject}")
                    # 标记为已处理，避免再次检查
                    self.processed_email_ids.add(email_id)
                    return None, False, False
            
            # 提取发件人邮箱
            sender_email_match = re.search(r'[\w\.-]+@[\w\.-]+', sender)
            if not sender_email_match:
                print_warning(f"无法从 {sender} 提取邮箱地址")
                return None, False, False
                
            sender_email = sender_email_match.group(0)
            
            # 检查是否为root用户
            if sender_email in self.root_users:
                print_highlight(f"发现来自管理员 {sender_email} 的邮件: {subject} (时间: {sent_time})")
                
                # 获取邮件详情
                email_detail = get_email.EmailRetriever.get_email_details(email_id)
                
                # 提取主题和正文
                subject_match = re.search(r'主题：(.+)', email_detail)
                subject = subject_match.group(1).strip() if subject_match else "无主题"
                
                # 查找正文内容
                body_start = email_detail.find("正文内容：")
                if body_start != -1:
                    body = email_detail[body_start + len("正文内容："):].strip()
                    
                    # 检查是否是指令(放宽条件，任何来自root用户的邮件都视为可能的指令)
                    body_content, is_stop, is_supplement = await self._analyze_email_intent(subject, body)
                    
                    # 标记为已处理
                    self.processed_email_ids.add(email_id)
                    self.processed_emails_details[email_id] = {
                        'time': sent_time,
                        'subject': subject,
                        'sender': sender,
                        'content': body[:100] + ('...' if len(body) > 100 else ''),
                        'processed_at': time.time()
                    }
                    
                    if is_stop:
                        print_warning(f"收到终止命令: {body_content}")
                        await self.send_report(
                            title="收到终止命令",
                            content=f"收到来自 {sender_email} 的终止命令: {body_content}\n\n监听模式将停止运行。",
                            is_error=False,
                            force_send=True  # 强制发送
                        )
                        return body_content, True, False
                    
                    if is_supplement:
                        print_highlight(f"收到来自管理员 {sender_email} 的任务补充: {subject}")
                        print_info(f"邮件ID: {email_id}, 时间: {sent_time}")
                        print_info(f"已将此邮件标记为已处理")
                        return body_content, False, True
                    else:
                        print_highlight(f"收到来自管理员 {sender_email} 的新指令: {subject}")
                        print_info(f"邮件ID: {email_id}, 时间: {sent_time}")
                        print_info(f"已将此邮件标记为已处理")
                        return body_content, False, False
                else:
                    print_warning(f"无法找到邮件正文内容，邮件ID: {email_id}")
            else:
                print_info(f"跳过非管理员邮件: {sender_email}")
            
            return None, False, False
        except Exception as e:
            print_error(f"检查邮件失败: {str(e)}\n{traceback.format_exc()}")
            return None, False, False
    
    async def _should_send_report(self, content: str, is_error: bool) -> bool:
        """
        使用LLM判断是否需要发送报告
        
        Args:
            content: 报告内容
            is_error: 是否是错误报告
            
        Returns:
            bool: 是否需要发送报告
        """
        # 如果是致命性错误导致监控功能无法运行，才发送错误报告
        if is_error:
            # 检查是否是致命错误
            fatal_error_indicators = [
                "连接失败", "无法访问服务器", "认证失败", "权限被拒绝",
                "网络中断", "无法执行监控", "服务不可用", "监控任务中断"
            ]
            
            is_fatal = any(indicator in content for indicator in fatal_error_indicators)
            if not is_fatal:
                # 非致命错误，检查是否需要用户提供额外信息
                needs_info = "需要" in content and any(key in content for key in ["密码", "密钥", "凭据", "token", "用户名", "认证", "权限"])
                if needs_info:
                    return True
                else:
                    print_info("非致命错误，不发送报告")
                    return False
            return True
            
        try:
            # 构建系统提示和用户消息
            system_prompt = """
            你是一个智能运维监控助手，需要判断是否向管理员发送报告。
            你应该遵循以下严格原则:
            1. 仅在以下情况发送报告:
               - 服务器出现异常状态（如CPU/内存/磁盘使用率过高、服务宕机、安全威胁）
               - 任务缺少关键信息（如密码、密钥等）需要用户补充
               - 监控任务本身无法继续执行（如连接中断、权限问题）
            2. 不要因为以下情况发送报告:
               - 服务器状态正常
               - 程序执行中的小错误但不影响监控功能
               - 常规状态更新或进度报告
            3. 报告内容必须包含具体的异常信息或缺失信息描述，否则不应发送
            """
            
            user_prompt = f"请分析以下报告内容，判断是否需要发送给管理员:\n\n{content}\n\n你的回答应该是:\n1. 第一行: '需要发送'或'无需发送'\n2. 第二行: 简短理由"
            
            # 调用LLM进行分析
            response = client.chat.completions.create(
                model="deepseek-chat",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.1
            )
            
            analysis = response.choices[0].message.content
            
            # 解析回答
            lines = analysis.strip().split('\n')
            should_send = "需要发送" in lines[0]
            
            # 提取理由
            reason = lines[1] if len(lines) > 1 else "无理由提供"
            
            print_info(f"报告发送分析: {'需要发送' if should_send else '无需发送'}, 理由: {reason}")
            
            return should_send
            
        except Exception as e:
            print_error(f"报告发送分析失败: {str(e)}")
            # 如果分析失败，默认不发送报告
            return False
    
    async def send_report(self, title: str, content: str, is_error: bool = False, force_send: bool = False):
        """
        发送报告给管理员
        
        Args:
            title: 报告标题
            content: 报告内容
            is_error: 是否是错误报告
            force_send: 是否强制发送（不经过LLM判断）
        """
        try:
            # 判断是否需要发送报告
            if not force_send and not await self._should_send_report(content, is_error):
                print_info(f"报告[{title}]无需发送，系统运行正常")
                return False
                
            # 准备HTML格式的邮件内容
            html_content = f"""
            <html>
            <head>
                <style>
                    body {{ font-family: Arial, sans-serif; }}
                    .header {{ background-color: {'#FFD2D2' if is_error else '#D2FFD2'}; padding: 10px; }}
                    .content {{ padding: 20px; }}
                    .footer {{ font-size: 12px; color: #888; padding: 10px; }}
                </style>
            </head>
            <body>
                <div class="header">
                    <h2>{'⚠️ 错误报告' if is_error else '✅ 状态报告'}: {title}</h2>
                    <p>时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
                </div>
                <div class="content">
                    {content.replace('\n', '<br>')}
                </div>
                <div class="footer">
                    此邮件由DeepSeek-PC-Manager监控模式自动发送
                </div>
            </body>
            </html>
            """
            
            # 获取所有root用户
            for email in self.root_users:
                # 发送邮件
                result = send_email.main(
                    content=html_content,
                    receiver=email,
                    subject=f"{'[错误]' if is_error else '[状态]'} {title}",
                    attachments=None
                )
                print_info(f"发送报告给 {email}: {result}")
            
            return True
        except Exception as e:
            print_error(f"发送报告失败: {str(e)}")
            return False
    
    async def execute_task(self, user_input: str, is_supplement: bool = False) -> bool:
        """执行用户的任务，根据任务内容选择工具"""
        try:
            # 检测任务类型
            simple_task_patterns = [
                (r'git\s+(add|commit|push|pull|clone|status|checkout|branch|merge|rebase|fetch)', 2),  # git操作
                (r'(ls|dir)\s+', 1),  # 列出文件
                (r'cd\s+', 1),  # 切换目录
                (r'(cat|type)\s+', 1),  # 查看文件内容
                (r'(mkdir|md)\s+', 1),  # 创建目录
                (r'(rm|del|rmdir|rd)\s+', 3),  # 删除操作
                (r'(cp|copy|mv|move)\s+', 2),  # 复制移动
                (r'(ping|ipconfig|ifconfig)\s*', 1),  # 网络命令
                (r'echo\s+', 1),  # 回显
            ]
            
            # 确定任务复杂度
            task_complexity = 4  # 默认复杂度（需要完整验证）
            for pattern, complexity in simple_task_patterns:
                if re.search(pattern, user_input.lower()):
                    task_complexity = complexity
                    print_info(f"检测到简单任务类型，复杂度级别: {complexity}/4")
                    break
                
            # 根据任务复杂度调整验证频率
            max_verify = 10
            if task_complexity == 1:
                max_verify = 2
            elif task_complexity == 2:
                max_verify = 4
            elif task_complexity == 3:
                max_verify = 6
            
            # 启动任务执行
            task_context = {
                "task_description": user_input,
                "session": None,
                "mode": "execute_task",
                "task_input": user_input,
                "task_input_timestamp": time.time(),
                "last_interaction_time": time.time(),
                "ssh_enabled": False,
                "ssh_info": None,
            }
            
            # 设置deepseekAPI客户端
            import deepseekAPI
            
            # 如果是补充信息，添加到上一条消息中
            if is_supplement:
                # 添加补充信息到历史记录中的最后一个用户消息
                for i in range(len(deepseekAPI.messages)-1, -1, -1):
                    if deepseekAPI.messages[i].get("role") == "user":
                        # 追加到已有消息
                        if isinstance(deepseekAPI.messages[i].get("content"), str):
                            deepseekAPI.messages[i]["content"] += f"\n[补充信息]: {user_input}"
                        break
            else:
                # 添加新的用户消息
                deepseekAPI.messages.append({"role": "user", "content": user_input})
            
            # 执行前检查token数量并清理
            token_count = deepseekAPI.num_tokens_from_messages(deepseekAPI.messages)
            if token_count > 28000:  # 提前清理
                await deepseekAPI.clean_message_history_with_llm(deepseekAPI.messages, deepseekAPI.client, 25000)
            
            # 动态调整系统提示
            system_prompt = "你叫小美，是一个热情的ai助手，帮助用户处理任务。"
            if task_complexity <= 2:
                # 简单任务使用简短系统提示
                deepseekAPI.messages[0] = {"role": "system", "content": system_prompt}
            
            # 执行任务的主循环
            response = None
            iteration = 0
            max_iterations = max(10, max_verify + 5)  # 确保至少有10次迭代
            
            while iteration < max_iterations:
                iteration += 1
                print_info(f"任务执行迭代: {iteration}/{max_iterations}")
                
                # API调用
                response = await deepseekAPI.execute_unified_task(user_input, deepseekAPI.messages)
                
                # 判断任务是否完成
                if "[任务已完成]" in response:
                    print_success("任务执行完成！")
                    break
                
                # 检查是否需要用户输入
                if "请提供" in response or "需要您提供" in response or "请输入" in response:
                    supplement = await self._ask_user_input("请提供更多信息: ", timeout=120)
                    if supplement:
                        user_input = supplement
                        deepseekAPI.messages.append({"role": "user", "content": supplement})
                    else:
                        print_warning("未获取到用户输入，尝试继续执行...")
                
                # 简单任务提前结束
                if task_complexity <= 2 and iteration >= max_verify:
                    print_info(f"简单任务已执行{iteration}次迭代，自动结束")
                    break
                
            # 处理任务结果
            final_result = response or "任务执行完成"
            return await self._handle_task_result(final_result)
        except Exception as e:
            error_message = f"执行任务出错: {str(e)}\n{traceback.format_exc()}"
            print_error(error_message)
            await self.send_report("任务执行出错", error_message, is_error=True)
            return False

    async def _handle_task_result(self, result: str) -> bool:
        """处理任务执行结果"""
        print_info(result)
        return True

    async def start(self):
        """启动监听模式"""
        self.running = True
        print_highlight("\n===== 监听模式已启动 =====")
        print_highlight("系统将每次迭代都检查邮件，查看是否有新指令")
        print_highlight("系统会记录已处理邮件，避免重复执行相同的指令")
        print_highlight("您可以通过邮件发送任务补充信息或终止指令")
        print_highlight("系统仅在异常或错误时发送报告，正常运行不会打扰管理员")
        print_highlight("=================================================")
        
        # 询问是否使用直接控制台模式
        console_mode = input("\n是否使用直接控制台交互模式? (y/n): ").strip().lower() == 'y'
        
        if console_mode:
            await self.start_console_mode()
            return
            
        # 获取初始任务
        initial_task = input("\n请输入初始任务: ")
        if not initial_task.strip():
            initial_task = "连接到指定服务器，检查系统状态并解决任何发现的问题"
            print_info(f"使用默认任务: {initial_task}")
            
        # 发送启动通知
        await self.send_report(
            title="监听模式已启动",
            content=f"初始任务: {initial_task}\n\n监听模式已启动，将持续运行直到收到终止指令。您可以通过邮件发送新任务或补充当前任务的详细信息。系统会规划和执行各种复杂任务，并仅在发现异常或错误时才会发送报告。",
            is_error=False,
            force_send=True  # 强制发送启动通知
        )
        
        # 添加初始任务
        self.current_task = initial_task
        
        # 清空已处理邮件ID集合，以免影响后续指令处理
        self.processed_email_ids.clear()
        self.processed_emails_details.clear()
        print_info("已清空邮件处理历史记录")
        
        # 主循环 - 无限循环直到收到终止命令
        iteration_count = 0
        last_cleanup_time = time.time()
        while self.running:
            try:
                iteration_count += 1
                print_highlight(f"\n===== 监听模式迭代 {iteration_count} =====")
                
                # 执行当前任务或从队列获取新任务
                if self.current_task:
                    # 执行当前任务
                    await self.execute_task(self.current_task)
                elif not self.task_queue.empty():
                    # 从队列获取新任务
                    next_task = self.task_queue.get()
                    await self.execute_task(next_task)
                
                # 检查邮件中的新指令
                print_info("\n检查邮件中的新指令...")
                command, is_stop_command, is_supplement = await self.check_email_commands()
                
                # 输出当前处理状态
                if len(self.processed_email_ids) > 0:
                    print_info(f"当前已处理邮件: {len(self.processed_email_ids)} 封")
                    
                    # 显示最近处理的3封邮件
                    recent_emails = sorted(
                        self.processed_emails_details.items(), 
                        key=lambda x: x[1]['processed_at'], 
                        reverse=True
                    )[:3]
                    
                    if recent_emails:
                        print_info("最近处理的邮件:")
                        for email_id, details in recent_emails:
                            print_info(f"  - [{details['time']}] {details['subject']}")
                    
                    # 维护token计数，确保不超过限制
                    if iteration_count % self.token_check_interval == 0 and self.current_task_messages:
                        self.current_task_messages = await self._cleanup_tokens_smart(self.current_task_messages, None)
                    
                    # 每小时清理一次过老的邮件记录，避免内存占用过大
                    current_time = time.time()
                    if current_time - last_cleanup_time > 3600:  # 每小时清理一次
                        self._cleanup_old_email_records()
                        last_cleanup_time = current_time
                
                # 处理终止命令
                if is_stop_command:
                    print_warning("收到终止命令，即将停止监听模式...")
                    self.running = False
                    break
                
                # 处理新指令或任务补充
                if command:
                    if is_supplement:
                        # 任务补充，直接执行
                        if self.current_task:
                            await self.execute_task(command, is_supplement=True)
                        else:
                            print_warning("收到任务补充，但当前没有活动任务。将作为新任务处理。")
                            self.task_queue.put(command)
                    else:
                        # 新任务添加到队列
                        self.task_queue.put(command)
                        print_success(f"已将新指令添加到任务队列: {command}")
                
                # 如果没有任务，执行默认的状态检查
                if self.current_task is None and self.task_queue.empty():
                    # 默认执行系统状态检查
                    print_info("\n无活动任务，执行默认状态检查...")
                    self.current_task = "执行系统状态检查，检查CPU、内存、磁盘使用率，如果发现异常请报告。仅在发现异常时发送报告，正常状态无需发送。"
                
                # 休眠一段时间，减少CPU使用率
                await asyncio.sleep(10)
                
            except KeyboardInterrupt:
                print_warning("\n收到键盘中断信号，但监听模式会继续运行")
                print_warning("要停止监听模式，请通过授权邮箱发送终止指令")
                await asyncio.sleep(5)
            except Exception as e:
                error_detail = traceback.format_exc()
                print_error(f"监听模式运行异常: {str(e)}\n{error_detail}")
                
                # 发送错误报告
                await self.send_report(
                    title="监听模式异常",
                    content=f"异常详情: {str(e)}\n\n{error_detail}\n\n监听模式将在10秒后继续运行",
                    is_error=True
                )
                await asyncio.sleep(10)  # 出错后等待一段时间再继续
        
        print_info("监听模式已停止")

    async def start_console_mode(self):
        """启动直接控制台交互模式"""
        print_highlight("\n===== 直接控制台交互模式已启动 =====")
        print_highlight("在此模式下，LLM将直接读取控制台输出并执行命令")
        print_highlight("你可以与LLM直接对话，它会根据控制台情况执行任务")
        print_highlight("输入'exit'或'quit'退出此模式")
        print_highlight("=======================================")
        
        console_messages = [
            {"role": "system", "content": """你是一个直接与用户交互的终端助手。
你可以执行各种系统操作，包括文件操作、网络连接、远程SSH等。
你将直接看到终端输出并做出反应，不需要中间人转发命令。
请始终以简洁明了的方式回答，并关注控制台输出以便调整你的行动。
当用户请求执行命令时，你应该直接使用相应的命令而不是使用工具调用。
你的回答应该基于控制台的实际情况，而不是预设的模板。"""}
        ]
        
        while self.running:
            try:
                # 获取用户输入
                user_input = input("\n请输入指令或问题 (exit/quit退出): ")
                
                # 检查是否退出
                if user_input.lower() in ['exit', 'quit']:
                    print_info("退出控制台交互模式...")
                    self.running = False
                    break
                
                # 将用户输入添加到消息历史
                console_messages.append({"role": "user", "content": user_input})
                
                # 调用LLM生成响应，并处理可能的命令执行
                response = client.chat.completions.create(
                    model="deepseek-chat",
                    messages=console_messages,
                    temperature=0.3
                )
                
                assistant_response = response.choices[0].message.content
                
                # 识别命令执行请求
                # 寻找可能的命令模式: ```bash ... ```或$开头的行
                command_patterns = [
                    r'```(?:bash|shell|cmd|powershell)?\s*(.*?)```',  # 代码块内容
                    r'\$\s*(.*?)(?:\n|$)'  # $开头的命令
                ]
                
                commands_to_execute = []
                
                for pattern in command_patterns:
                    matches = re.findall(pattern, assistant_response, re.DOTALL)
                    commands_to_execute.extend([cmd.strip() for cmd in matches if cmd.strip()])
                
                # 显示LLM回答（去除代码块，因为命令会实际执行）
                clean_response = re.sub(r'```(?:bash|shell|cmd|powershell)?\s*(.*?)```', '', assistant_response, flags=re.DOTALL)
                clean_response = re.sub(r'\$\s*(.*?)(?:\n|$)', '', clean_response)
                
                print_info("\n助手回答:")
                print(clean_response.strip())
                
                # 添加助手回复到消息历史
                console_messages.append({"role": "assistant", "content": assistant_response})
                
                # 执行提取出的命令
                for command in commands_to_execute:
                    if command:
                        print_highlight(f"\n执行命令: {command}")
                        
                        # 根据操作系统确定使用的shell
                        shell_cmd = command
                        
                        try:
                            # 使用asyncio执行命令
                            process = await asyncio.create_subprocess_shell(
                                shell_cmd,
                                stdout=asyncio.subprocess.PIPE,
                                stderr=asyncio.subprocess.PIPE,
                                shell=True
                            )
                            
                            # 获取输出
                            stdout, stderr = await process.communicate()
                            stdout_str = stdout.decode('utf-8', errors='replace')
                            stderr_str = stderr.decode('utf-8', errors='replace')
                            
                            # 输出结果
                            if process.returncode == 0:
                                if stdout_str.strip():
                                    print_success("命令执行成功:")
                                    print(stdout_str)
                                else:
                                    print_success("命令执行成功 (无输出)")
                            else:
                                print_error(f"命令执行失败，返回码: {process.returncode}")
                                if stderr_str.strip():
                                    print(stderr_str)
                            
                            # 将命令输出添加到消息历史
                            output_content = f"命令 `{command}` 的执行结果:\n"
                            if stdout_str.strip():
                                output_content += f"标准输出:\n```\n{stdout_str}\n```\n"
                            if stderr_str.strip():
                                output_content += f"错误输出:\n```\n{stderr_str}\n```\n"
                            if not stdout_str.strip() and not stderr_str.strip():
                                output_content += "命令执行成功，无输出。\n"
                                
                            console_messages.append({"role": "user", "content": output_content})
                            
                        except Exception as e:
                            error_detail = traceback.format_exc()
                            print_error(f"命令执行异常: {str(e)}")
                            console_messages.append({
                                "role": "user", 
                                "content": f"命令 `{command}` 执行出错: {str(e)}"
                            })
                
                # 限制消息历史长度
                if len(console_messages) > 20:  # 保留系统消息和最近的对话
                    console_messages = [console_messages[0]] + console_messages[-19:]
                
            except KeyboardInterrupt:
                print_warning("\n收到键盘中断信号")
                user_confirm = input("是否退出控制台交互模式? (y/n): ").strip().lower()
                if user_confirm == 'y':
                    print_info("退出控制台交互模式...")
                    self.running = False
                    break
            except Exception as e:
                error_detail = traceback.format_exc()
                print_error(f"控制台交互模式异常: {str(e)}\n{error_detail}")
                await asyncio.sleep(2)  # 出错后短暂停顿
        
        print_info("控制台交互模式已停止")

    async def write_script(self, filename: str, content: str, mode: str = "w") -> str:
        """创建或更新脚本文件
        
        Args:
            filename: 脚本文件名
            content: 脚本内容
            mode: 写入模式，'w'覆盖，'a'追加
            
        Returns:
            操作结果消息
        """
        try:
            # 确保脚本目录存在
            script_dir = os.path.join(os.getcwd(), "scripts")
            if not os.path.exists(script_dir):
                os.makedirs(script_dir)
            
            # 构建完整文件路径
            file_path = os.path.join(script_dir, filename)
            
            # 写入文件
            with open(file_path, mode, encoding='utf-8') as f:
                f.write(content)
            
            # 如果是脚本文件，确保有执行权限
            if filename.endswith(".sh") or filename.endswith(".py"):
                # 在Windows上不需要这个操作，在Linux/Unix上才需要
                if os.name != 'nt':
                    os.chmod(file_path, 0o755)
            
            print_success(f"脚本已{'更新' if mode == 'a' else '创建'}: {file_path}")
            return f"脚本已{'更新' if mode == 'a' else '创建'}: {file_path}"
            
        except Exception as e:
            error_msg = f"创建脚本文件失败: {str(e)}"
            print_error(error_msg)
            return error_msg
    
    async def execute_local_script(self, filename: str, args: str = "") -> str:
        """在本地执行脚本
        
        Args:
            filename: 脚本文件名
            args: 脚本参数
            
        Returns:
            脚本执行结果
        """
        try:
            # 构建完整文件路径
            script_dir = os.path.join(os.getcwd(), "scripts")
            file_path = os.path.join(script_dir, filename)
            
            # 检查文件是否存在
            if not os.path.exists(file_path):
                return f"错误: 脚本文件不存在: {file_path}"
            
            # 根据文件类型决定如何执行
            cmd = []
            if filename.endswith(".py"):
                cmd = [sys.executable, file_path]
            elif filename.endswith(".sh"):
                if os.name == 'nt':
                    # 在Windows上，尝试使用WSL或Git Bash
                    if os.path.exists("C:\\Windows\\System32\\wsl.exe"):
                        cmd = ["wsl", "bash", file_path]
                    elif os.path.exists("C:\\Program Files\\Git\\bin\\bash.exe"):
                        cmd = ["C:\\Program Files\\Git\\bin\\bash.exe", file_path]
                    else:
                        # 使用普通的cmd
                        cmd = ["cmd", "/c", file_path]
                else:
                    cmd = ["/bin/bash", file_path]
            else:
                cmd = [file_path]
            
            # 添加参数
            if args:
                cmd.extend(args.split())
            
            # 执行命令
            print_info(f"执行脚本: {' '.join(cmd)}")
            
            try:
                # 使用asyncio创建子进程
                process = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
            except FileNotFoundError as e:
                # 如果找不到执行文件，尝试使用shell模式
                print_warning(f"找不到执行文件: {e}，尝试使用shell模式")
                process = await asyncio.create_subprocess_shell(
                    ' '.join(cmd),
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
            
            # 获取输出
            stdout, stderr = await process.communicate()
            stdout_str = stdout.decode('utf-8', errors='replace')
            stderr_str = stderr.decode('utf-8', errors='replace')
            
            # 输出结果
            if process.returncode == 0:
                print_success("脚本执行成功")
                print(stdout_str)
                return f"脚本执行成功:\n{stdout_str}"
            else:
                print_error(f"脚本执行失败，返回码: {process.returncode}")
                print(stderr_str)
                return f"脚本执行失败，返回码: {process.returncode}\n错误信息:\n{stderr_str}"
            
        except Exception as e:
            error_detail = traceback.format_exc()
            print_error(f"执行脚本失败: {str(e)}\n{error_detail}")
            return f"执行脚本失败: {str(e)}\n{error_detail}"
    
    async def _process_session_output(self, task_context: Dict[str, Any]):
        """处理SSH会话输出"""
        try:
            session_id = task_context.get("session_id")
            if not session_id:
                return
            
            # 获取最近的输出
            since_time = task_context.get("last_output_check", 0)
            
            try:
                recent_output = await asyncio.wait_for(
                    self.ssh_controller.get_session_output(session_id, since_time),
                    timeout=10  # 10秒超时
                )
                
                # 更新最后检查时间
                task_context["last_output_check"] = time.time()
                
                if not recent_output:
                    return
                
                # 打印输出供用户查看
                if recent_output.strip():
                    print_info(f"\n----- SSH输出 -----\n{recent_output}\n-------------------")
                
                # 将输出添加到任务消息历史
                if self.current_task_messages:
                    # 创建一个新的助手消息，包含终端输出
                    terminal_message = {
                        "role": "assistant",
                        "content": f"```terminal\n{recent_output}\n```"
                    }
                    
                    # 添加到消息历史
                    self.current_task_messages.append(terminal_message)
                    
                    # 清理令牌以避免超出限制
                    if len(self.current_task_messages) > 50:  # 只有在消息较多时才进行清理
                        self.current_task_messages = await self._cleanup_tokens_smart(self.current_task_messages)
            except asyncio.TimeoutError:
                print_warning(f"获取SSH会话输出超时，将在下次迭代重试")
                # 不更新最后检查时间，以便下次重试
            except Exception as e:
                print_error(f"获取SSH会话输出失败: {str(e)}")
                # 如果获取输出失败，不要更新最后检查时间，以便下次重试
        
        except Exception as e:
            print_error(f"处理SSH会话输出失败: {str(e)}")
            
    async def ssh_interactive(self, host: str, command: str = None, username: str = None, password: str = None, 
                            context: Dict[str, Any] = None) -> str:
        """SSH交互式会话，使用增强的智能交互功能"""
        try:
            # 获取上下文信息
            task_context = context or {}
            
            # 如果当前任务上下文中已经有连接信息，优先使用
            if not host and "host" in task_context:
                host = task_context["host"]
            if not username and "username" in task_context:
                username = task_context["username"]
            if not password and "password" in task_context:
                password = task_context["password"]
            
            # 如果还是缺少必要参数，向用户请求
            if not host:
                host = await self.user_input("请输入目标主机地址：")
                task_context["host"] = host
                
            if not username:
                username = await self.user_input("请输入用户名：")
                task_context["username"] = username
                
            if not password:
                password = await self.user_input("请输入密码：", is_password=True)
                task_context["password"] = password
            
            # 如果命令为空，使用默认命令
            if not command:
                command = ""
            
            print_info(f"开始SSH交互式会话: {username}@{host}")
            
            # 确保SSH会话已创建（使用新的智能会话方法）
            session_exists = await self._ensure_ssh_session(task_context)
            
            if session_exists and task_context.get("session_id"):
                # 使用现有会话发送命令
                print_info(f"使用已有会话发送命令: {command}")
                if command:
                    try:
                        # 添加超时处理
                        await asyncio.wait_for(
                            self.ssh_controller.send_to_session(
                                session_id=task_context["session_id"],
                                command=command
                            ),
                            timeout=15  # 15秒超时
                        )
                        
                        # 等待一小段时间让命令执行并产生输出
                        await asyncio.sleep(1)
                        
                        return f"命令已发送到会话: {task_context['session_id']}\n请等待命令执行结果..."
                        
                    except asyncio.TimeoutError:
                        print_warning(f"发送命令到会话超时，将重试")
                        # 尝试重新连接会话
                        task_context.pop("session_id", None)
                        await self._ensure_ssh_session(task_context)
                        return f"发送命令到会话超时，已重新建立连接，请重试命令"
                        
                    except Exception as e:
                        print_error(f"发送命令到会话失败: {str(e)}")
                        return f"发送命令到会话失败: {str(e)}"
                else:
                    # 如果没有命令，只是维持会话并告知用户
                    return f"SSH会话已建立，会话ID: {task_context['session_id']}\n监控会话输出中..."
            else:
                # 创建新的交互式会话
                try:
                    # 使用增强的智能交互会话
                    session_id = await asyncio.wait_for(
                        self.ssh_controller.interactive_agent_session(
                            host=host, 
                            username=username, 
                            password=password, 
                            task_description=command if command else None
                        ),
                        timeout=30  # 30秒超时
                    )
                    
                    # 更新任务上下文
                    task_context["session_id"] = session_id
                    task_context["commands_executed"] = task_context.get("commands_executed", 0) + 1
                    task_context["connection_established"] = True
                    task_context["last_output_check"] = time.time()
                    
                    # 开始监控会话输出（如果尚未启动）
                    if not hasattr(self, "monitor_tasks") or session_id not in self.monitor_tasks:
                        monitor_task = asyncio.create_task(
                            self._monitor_session_output(task_context)
                        )
                        
                        if not hasattr(self, "monitor_tasks"):
                            self.monitor_tasks = {}
                        self.monitor_tasks[session_id] = monitor_task
                    
                    return f"SSH智能会话已建立，会话ID: {session_id}\n监控会话输出中..."
                    
                except asyncio.TimeoutError:
                    print_warning("智能交互会话连接超时")
                    return "SSH交互式会话连接超时，请检查网络连接或服务器状态"
                    
                except Exception as e:
                    print_error(f"SSH交互式会话失败: {str(e)}")
                    return f"SSH交互式会话失败: {str(e)}"
                
        except Exception as e:
            print_error(f"SSH交互式会话失败: {str(e)}")
            return f"SSH交互式会话失败: {str(e)}"

    async def execute_remote_script(self, host: str, username: str, password: str, 
                                   script_content: str, filename: str = "temp_script.sh") -> str:
        """在远程服务器上执行脚本
        
        Args:
            host: 远程服务器地址
            username: 用户名
            password: 密码
            script_content: 脚本内容
            filename: 脚本文件名
            
        Returns:
            脚本执行结果
        """
        try:
            # 首先在本地创建临时脚本
            script_dir = os.path.join(os.getcwd(), "scripts")
            local_path = os.path.join(script_dir, filename)
            
            # 确保scripts目录存在
            os.makedirs(script_dir, exist_ok=True)
            
            # 写入脚本内容
            try:
                with open(local_path, 'w', encoding='utf-8') as f:
                    f.write(script_content)
                print_info(f"脚本已保存到本地: {local_path}")
            except Exception as e:
                error_msg = f"保存脚本文件失败: {str(e)}"
                print_error(error_msg)
                return error_msg
            
            # 确保SSH会话已创建
            task_context = {
                "host": host,
                "username": username,
                "password": password
            }
            
            session_exists = await self._ensure_ssh_session(task_context)
            
            if session_exists and task_context.get("session_id"):
                # 使用现有会话上传并执行脚本
                try:
                    # 上传脚本
                    print_info(f"通过SSH会话上传脚本到远程服务器")
                    remote_path = f"/tmp/{filename}"
                    
                    # 首先创建远程目录
                    await asyncio.wait_for(
                        self.ssh_controller.send_command(
                            session_id=task_context["session_id"],
                            command=f"mkdir -p /tmp"
                        ),
                        timeout=10  # 10秒超时
                    )
                    
                    # 使用会话命令上传文件内容
                    script_lines = script_content.split("\n")
                    upload_cmd = f"cat > {remote_path} << 'EOF'\n" + script_content + "\nEOF"
                    
                    await asyncio.wait_for(
                        self.ssh_controller.send_command(
                            session_id=task_context["session_id"],
                            command=upload_cmd
                        ),
                        timeout=30  # 30秒超时，文件传输可能需要更长时间
                    )
                    
                    # 设置脚本为可执行
                    await asyncio.wait_for(
                        self.ssh_controller.send_command(
                            session_id=task_context["session_id"],
                            command=f"chmod +x {remote_path}"
                        ),
                        timeout=10  # 10秒超时
                    )
                    
                    # 执行脚本
                    print_info(f"开始在远程服务器上执行脚本")
                    await asyncio.wait_for(
                        self.ssh_controller.send_command(
                            session_id=task_context["session_id"],
                            command=f"bash {remote_path}"
                        ),
                        timeout=30  # 30秒超时，脚本执行可能需要更长时间
                    )
                    
                    # 等待输出
                    await asyncio.sleep(1)
                    
                    # 获取最近的输出
                    try:
                        output = await asyncio.wait_for(
                            self.ssh_controller.get_session_output(
                                session_id=task_context["session_id"],
                                since_time=task_context.get("last_output_check", 0)
                            ),
                            timeout=10  # 10秒超时
                        )
                        
                        # 更新最后检查时间
                        task_context["last_output_check"] = time.time()
                        
                        return f"脚本执行输出:\n{output}"
                    except asyncio.TimeoutError:
                        print_warning("获取脚本输出超时，脚本可能仍在执行中")
                        return "脚本已执行，但获取输出超时。脚本可能仍在运行中，请稍后查看结果。"
                        
                except asyncio.TimeoutError as e:
                    print_warning(f"脚本执行操作超时: {str(e)}")
                    return f"脚本执行操作超时，请检查网络连接或服务器状态。脚本可能部分已执行。"
                except Exception as e:
                    print_error(f"通过会话执行脚本失败: {str(e)}")
                    return f"通过会话执行脚本失败: {str(e)}"
            else:
                # 使用普通SSH命令执行脚本
                try:
                    # 通过SSH将脚本上传到远程服务器
                    print_info(f"上传脚本到远程服务器: {username}@{host}")
                    
                    # 使用SSH控制器执行命令
                    # 上传脚本
                    cat_cmd = f"""
echo '{script_content}' > /tmp/{filename} && 
chmod +x /tmp/{filename} && 
/tmp/{filename}
"""
                    try:
                        result = await asyncio.wait_for(
                            self.ssh_controller.execute_command(
                                host=host,
                                username=username,
                                password=password,
                                command=cat_cmd
                            ),
                            timeout=60  # 60秒超时，脚本执行可能需要更长时间
                        )
                        return result
                    except asyncio.TimeoutError:
                        print_warning("脚本执行命令超时")
                        return "脚本执行命令超时，请检查网络连接或服务器状态。脚本可能部分已执行。"
                    
                except Exception as e:
                    print_error(f"通过命令执行脚本失败: {str(e)}")
                    return f"通过命令执行脚本失败: {str(e)}"
                
        except Exception as e:
            error_msg = f"在远程服务器执行脚本失败: {str(e)}\n{traceback.format_exc()}"
            print_error(error_msg)
            return error_msg

    def _cleanup_old_email_records(self):
        """清理过老的邮件记录，避免内存占用过大"""
        try:
            # 计算一天前的时间戳
            one_day_ago = time.time() - 86400  # 86400秒 = 24小时
            
            # 找出所有一天前处理的邮件
            old_email_ids = [
                email_id for email_id, details in self.processed_emails_details.items()
                if details.get('processed_at', 0) < one_day_ago
            ]
            
            if old_email_ids:
                # 从详细信息字典中删除
                for email_id in old_email_ids:
                    if email_id in self.processed_emails_details:
                        del self.processed_emails_details[email_id]
                    
                    # 从ID集合中删除
                    if email_id in self.processed_email_ids:
                        self.processed_email_ids.remove(email_id)
                
                print_info(f"已清理 {len(old_email_ids)} 封过期邮件记录")
                print_info(f"当前记录邮件数量: {len(self.processed_email_ids)}")
        except Exception as e:
            print_error(f"清理邮件记录失败: {str(e)}")
            # 如果清理失败，不影响主流程

    async def ssh_command(self, host: str, command: str, username: str = None, password: str = None, 
                      context: Dict[str, Any] = None) -> str:
        """执行SSH命令"""
        try:
            # 获取上下文信息
            task_context = context or {}
            
            # 如果当前任务上下文中已经有连接信息，优先使用
            if not host and "host" in task_context:
                host = task_context["host"]
            if not username and "username" in task_context:
                username = task_context["username"]
            if not password and "password" in task_context:
                password = task_context["password"]
            
            # 如果还是缺少必要参数，向用户请求
            if not host:
                host = await self._ask_user_input("请输入目标主机地址：")
                task_context["host"] = host
                
            if not username:
                username = await self._ask_user_input("请输入用户名：")
                task_context["username"] = username
                
            if not password:
                password = await self._ask_user_input("请输入密码：", is_password=True)
                task_context["password"] = password
            
            print_info(f"执行SSH命令: {command}")
            
            # 使用SSH控制器执行命令
            try:
                result = await asyncio.wait_for(
                    self.ssh_controller.execute_command(host, username, password, command),
                    timeout=60  # 设置60秒超时
                )
                
                # 更新任务上下文
                task_context["commands_executed"] = task_context.get("commands_executed", 0) + 1
                
                return result
            except asyncio.TimeoutError:
                print_warning("SSH命令执行超时")
                return "SSH命令执行超时，请检查网络连接或服务器状态"
                
        except Exception as e:
            error_detail = traceback.format_exc()
            print_error(f"SSH命令执行失败: {str(e)}\n{error_detail}")
            return f"SSH命令执行失败: {str(e)}"

    async def _ensure_ssh_session(self, task_context: Dict[str, Any]) -> bool:
        """确保SSH会话已经创建并正常连接"""
        try:
            host = task_context.get("host")
            username = task_context.get("username")
            password = task_context.get("password")
            
            # 检查是否已经有会话ID
            session_id = task_context.get("session_id")
            
            if session_id:
                # 检查会话是否有效
                session_status = await self.ssh_controller.get_session_status(session_id)
                if session_status["status"] == "connected":
                    print_info(f"复用现有SSH会话: {session_id}")
                    return True
                else:
                    print_warning(f"会话 {session_id} 已断开，将创建新会话")
                    # 清除失效的会话ID
                    task_context.pop("session_id", None)
            
            if not all([host, username, password]):
                print_error("缺少SSH连接信息")
                return False
            
            # 创建新的智能会话
            try:
                print_info(f"正在创建新的智能SSH会话: {username}@{host}")
                # 使用新的智能交互式会话方法
                new_session_id = await self.ssh_controller.interactive_agent_session(
                    host=host,
                    username=username,
                    password=password
                )
                
                if isinstance(new_session_id, str) and new_session_id.startswith("创建Agent驱动会话失败"):
                    print_error(f"创建会话失败: {new_session_id}")
                    return False
                
                print_success(f"创建智能SSH会话成功: {new_session_id}")
                
                # 更新任务上下文
                task_context["session_id"] = new_session_id
                task_context["last_output_check"] = time.time()
                
                # 开始监控会话输出
                monitor_task = asyncio.create_task(
                    self._monitor_session_output(task_context)
                )
                
                # 存储监控任务，以便后续管理
                if not hasattr(self, "monitor_tasks"):
                    self.monitor_tasks = {}
                self.monitor_tasks[new_session_id] = monitor_task
                
                return True
                
            except Exception as e:
                print_error(f"创建SSH会话失败: {str(e)}")
                return False
        
        except Exception as e:
            print_error(f"确保SSH会话时出错: {str(e)}")
            return False

    async def _monitor_session_output(self, task_context: Dict[str, Any]):
        """持续监控会话输出的任务"""
        session_id = task_context.get("session_id")
        if not session_id:
            return
        
        print_info(f"开始监控会话 {session_id} 的输出")
        
        async def output_callback(output, timestamp):
            """输出回调函数"""
            if output.strip():
                print_info(f"\n----- SSH实时输出 -----\n{output}\n-------------------")
                
                # 更新LLM上下文
                if hasattr(self, "current_task_messages") and self.current_task_messages:
                    # 创建一个新的消息，包含终端输出
                    terminal_message = {
                        "role": "assistant" if not output.startswith(">") else "user",
                        "content": f"```terminal\n{output}\n```"
                    }
                    
                    # 如果前一条也是终端输出，则合并
                    if self.current_task_messages and \
                       self.current_task_messages[-1].get("content", "").startswith("```terminal"):
                        self.current_task_messages[-1]["content"] += f"\n{output}"
                    else:
                        self.current_task_messages.append(terminal_message)
                
                # 分析输出，发现可能需要智能响应的情况
                await self._analyze_ssh_output(task_context, output)
        
        # 开始监控
        try:
            await self.ssh_controller.monitor_session(session_id, output_callback)
        except Exception as e:
            print_error(f"监控会话 {session_id} 失败: {str(e)}")

    async def _analyze_ssh_output(self, task_context: Dict[str, Any], output: str):
        """分析SSH输出，并处理各种需要智能响应的场景"""
        session_id = task_context.get("session_id")
        if not session_id:
            return
        
        # 常见需要响应的模式
        prompt_patterns = {
            "password": [r'\[sudo\].*?密码.*?:', r'password.*?:', r'密码.*?:'],
            "confirmation": [r'\[y/n\]', r'\(yes/no\)', r'continue\?', r'proceed\?', r'are you sure'],
            "error": [r'command not found', r'权限不足', r'permission denied', r'no such file or directory'],
            "completion": [r'installation successful', r'completed successfully', r'安装成功', r'successfully', r'成功']
        }
        
        # 检查密码提示
        if any(re.search(pattern, output, re.IGNORECASE) for pattern in prompt_patterns["password"]):
            print_info(f"检测到需要输入密码，自动处理")
            password = task_context.get("password")
            if password:
                await self.ssh_controller.send_to_session(session_id, password)
            else:
                print_warning("会话需要密码但未找到保存的密码信息")
                
        # 检查确认提示
        elif any(re.search(pattern, output, re.IGNORECASE) for pattern in prompt_patterns["confirmation"]):
            print_info(f"检测到需要确认，自动响应")
            await self.ssh_controller.send_to_session(session_id, "y")
            
        # 检查错误
        elif any(re.search(pattern, output, re.IGNORECASE) for pattern in prompt_patterns["error"]):
            print_warning(f"检测到错误消息")
            # 这里可以根据错误类型生成修复命令
            # 先简单记录，未来可扩展为智能修复
            task_context["last_error"] = output
            
        # 检查成功完成
        elif any(re.search(pattern, output, re.IGNORECASE) for pattern in prompt_patterns["completion"]):
            print_success(f"检测到操作成功完成")
            task_context["last_success"] = output

    async def ssh_task(self, host: str, task_description: str, username: str = None, password: str = None, 
                     context: Dict[str, Any] = None) -> str:
        """
        执行智能SSH任务，让Agent自动完成复杂操作
        
        Args:
            host: 目标主机
            task_description: 任务描述
            username: 用户名
            password: 密码
            context: 上下文信息
            
        Returns:
            执行结果描述
        """
        try:
            # 获取上下文信息
            task_context = context or {}
            
            # 如果当前任务上下文中已经有连接信息，优先使用
            if not host and "host" in task_context:
                host = task_context["host"]
            if not username and "username" in task_context:
                username = task_context["username"]
            if not password and "password" in task_context:
                password = task_context["password"]
            
            # 如果还是缺少必要参数，向用户请求
            if not host:
                host = await self.user_input("请输入目标主机地址：")
                task_context["host"] = host
                
            if not username:
                username = await self.user_input("请输入用户名：")
                task_context["username"] = username
                
            if not password:
                password = await self.user_input("请输入密码：", is_password=True)
                task_context["password"] = password
            
            print_info(f"开始执行SSH智能任务：{task_description}")
            
            # 确保会话已创建
            session_exists = await self._ensure_ssh_session(task_context)
            
            if session_exists and task_context.get("session_id"):
                session_id = task_context["session_id"]
                
                # 使用execute_task方法执行复杂任务
                try:
                    success = await asyncio.wait_for(
                        self.ssh_controller.execute_task(
                            session_id=session_id,
                            task_description=task_description
                        ),
                        timeout=60  # 给任务规划60秒超时
                    )
                    
                    if success:
                        return f"智能任务已开始执行。任务：{task_description}\n请等待Agent执行任务并观察输出..."
                    else:
                        return f"任务规划失败，请尝试提供更明确的任务描述或检查连接状态"
                    
                except asyncio.TimeoutError:
                    print_warning("任务规划超时")
                    return "任务规划超时，请尝试简化任务描述或拆分为多个步骤"
                    
                except Exception as e:
                    print_error(f"执行智能任务失败: {str(e)}")
                    return f"执行智能任务失败: {str(e)}"
            else:
                return "无法创建或找到有效的SSH会话，请先确保网络连接正常"
                
        except Exception as e:
            print_error(f"执行SSH智能任务失败: {str(e)}")
            return f"执行SSH智能任务失败: {str(e)}"

# 直接作为主程序运行
def main():
    """主函数，直接运行监听模式"""
    print_highlight("\n===== DeepSeek-PC-Manager 监听模式 =====")
    print_highlight("版本: 1.0.0")
    print_highlight("======================================")
    
    try:
        # 运行监听模式
        asyncio.run(run_monitor_mode())
    except KeyboardInterrupt:
        print_warning("\n程序被用户中断")
    except Exception as e:
        print_error(f"程序运行异常: {str(e)}\n{traceback.format_exc()}")
    finally:
        print_info("程序已退出")

async def run_monitor_mode():
    """运行监听模式的入口函数"""
    monitor = MonitorMode()
    await monitor.start()

if __name__ == "__main__":
    # 直接作为脚本运行时执行main函数
    main() 