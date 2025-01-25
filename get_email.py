import imaplib
import email
from email.header import decode_header
import os
from typing import List, Dict, Optional
import functools
import threading
from dotenv import load_dotenv


class IMAPConnectionManager:
    """
    IMAP连接管理器，提供线程安全的连接复用机制
    """
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if not cls._instance:
            with cls._lock:
                if not cls._instance:
                    cls._instance = super().__new__(cls)
                    cls._instance._connection = None
        return cls._instance

    def get_connection(self):
        """
        获取或创建IMAP连接

        Returns:
            imaplib.IMAP4_SSL: IMAP连接对象
        """
        with self._lock:
            try:
                # 如果连接不存在或已关闭，重新创建
                if not self._connection:
                    self._connection = imaplib.IMAP4_SSL('imap.qq.com', 993)
                    self._connection.login(QQ_EMAIL, AUTH_CODE)
                return self._connection
            except Exception as e:
                print(f"连接创建失败: {e}")
                raise

    def release_connection(self):
        """
        释放IMAP连接
        """
        with self._lock:
            if self._connection:
                try:
                    self._connection.close()
                    self._connection.logout()
                except Exception as e:
                    print(f"连接关闭异常: {e}")
                finally:
                    self._connection = None


def retry_on_connection_error(max_retries=3):
    """
    连接错误重试装饰器

    Args:
        max_retries (int): 最大重试次数
    """

    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            connection_manager = IMAPConnectionManager()
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except (imaplib.IMAP4.error, ConnectionError) as e:
                    print(f"第 {attempt + 1} 次重试 - 错误: {e}")
                    connection_manager.release_connection()
                    if attempt == max_retries - 1:
                        raise
            return None

        return wrapper

    return decorator


def decode_mime_header(header: Optional[str]) -> str:
    """
    安全解码MIME头

    Args:
        header (str): 待解码的邮件头

    Returns:
        str: 解码后的文本
    """
    if not header:
        return "未知"

    decoded = []
    for part, encoding in decode_header(header):
        try:
            if isinstance(part, bytes):
                decoded.append(part.decode(encoding or 'utf-8', errors='ignore'))
            else:
                decoded.append(str(part))
        except Exception as e:
            print(f"解码错误: {e}")

    return "".join(decoded) or "未知"


class EmailRetriever:
    """
    邮件检索核心类
    提供高性能、线程安全的邮件检索功能
    """

    @staticmethod
    @retry_on_connection_error()
    def retrieve_emails(max_emails: int = 10) -> List[Dict]:
        """
        检索最新邮件列表

        Args:
            max_emails (int): 最大检索邮件数

        Returns:
            List[Dict]: 邮件元数据列表
        """
        connection_manager = IMAPConnectionManager()
        mail = connection_manager.get_connection()

        try:
            mail.select('inbox')

            # 优化检索性能
            status, messages = mail.search(None, 'ALL')
            all_email_ids = messages[0].split()

            # 选择最近邮件
            email_ids = all_email_ids[-max_emails:]

            email_list = []
            for email_id in reversed(email_ids):
                status, msg_data = mail.fetch(email_id, '(BODY.PEEK[HEADER])')
                if status == 'OK':
                    msg = email.message_from_bytes(msg_data[0][1])
                    email_list.append({
                        'id': email_id.decode(),
                        'subject': decode_mime_header(msg.get('Subject')),
                        'from': decode_mime_header(msg.get('From')),
                        'date': msg.get('Date', '未知日期')
                    })

            return email_list

        except Exception as e:
            print(f"邮件获取失败: {e}")
            return []

    @staticmethod
    @retry_on_connection_error()
    def get_email_details(email_id: str, save_attachments: bool = False) -> str:
        """
        获取指定邮件详情

        Args:
            email_id (str): 邮件ID
            save_attachments (bool): 是否保存附件

        Returns:
            str: 格式化邮件详情
        """
        connection_manager = IMAPConnectionManager()
        mail = connection_manager.get_connection()

        try:
            mail.select('inbox')
            status, msg_data = mail.fetch(email_id.encode(), '(RFC822)')

            if status != 'OK':
                return "找不到指定邮件"

            msg = email.message_from_bytes(msg_data[0][1])
            email_details = {
                'subject': decode_mime_header(msg['Subject']),
                'from': decode_mime_header(msg['From']),
                'date': msg['Date'],
                'body': '',
                'attachments': []
            }

            for part in msg.walk():
                content_type = part.get_content_type()
                content_disposition = str(part.get("Content-Disposition"))

                # 提取正文
                if content_type == "text/plain" and "attachment" not in content_disposition:
                    try:
                        email_details['body'] = part.get_payload(decode=True).decode('utf-8', errors='ignore')
                    except Exception:
                        email_details['body'] = "无法解码正文内容"

                # 处理附件
                if save_attachments and "attachment" in content_disposition:
                    filename = part.get_filename()
                    if filename:
                        filename = decode_mime_header(filename)
                        filepath = os.path.join("attachments", filename)

                        os.makedirs("attachments", exist_ok=True)
                        with open(filepath, "wb") as f:
                            f.write(part.get_payload(decode=True))

                        email_details['attachments'].append({
                            'filename': filename,
                            'filepath': os.path.abspath(filepath)
                        })

            # 构建返回结果
            result = [
                f"主题：{email_details['subject']}",
                f"发件人：{email_details['from']}",
                f"日期：{email_details['date']}",
                "\n正文内容：",
                email_details['body']
            ]

            if email_details['attachments']:
                result.append("\n附件：")
                for att in email_details['attachments']:
                    result.append(f"- {att['filename']} (保存位置: {att['filepath']})")

            return "\n".join(result)

        except Exception as e:
            return f"邮件解析失败: {str(e)}"


# QQ邮箱
load_dotenv()
QQ_EMAIL = os.environ.get("QQ_EMAIL")
AUTH_CODE = os.environ.get("AUTH_CODE")


# 兼容原有接口的函数
def retrieve_emails(max_emails=10):
    return EmailRetriever.retrieve_emails(max_emails)


def get_email_details(email_id: str, save_attachments: bool = False):
    return EmailRetriever.get_email_details(email_id, save_attachments)