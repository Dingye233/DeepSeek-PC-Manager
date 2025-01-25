import os
import sys
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.header import Header
from dotenv import load_dotenv
load_dotenv()
def send_email(sender_email, sender_password, recipient_email, subject, content, smtp_server='smtp.qq.com', port=587):
    """发送支持中英文和Emoji的邮件"""
    server = None
    try:
        # 创建多部分邮件消息
        msg = MIMEMultipart()
        msg['From'] = sender_email
        msg['To'] = recipient_email

        # 使用Header处理中文和emoji主题
        msg['Subject'] = Header(subject, 'utf-8')

        # 添加正文，支持HTML和中文
        msg.attach(MIMEText(content, 'html', 'utf-8'))

        # 建立安全连接
        server = smtplib.SMTP(smtp_server, port)
        server.starttls()

        # 登录
        server.login(sender_email, sender_password)

        # 发送邮件
        server.send_message(msg)
        return "邮件发送成功 🎉"

    except Exception as e:
        return f"发送邮件出错: {e}"

    finally:
        if server:
            try:
                server.quit()
            except Exception as close_error:
                return f"关闭连接时出错: {close_error}"

def main(receiver:str,_subject:str,_content:str):
    sender_email = os.environ.get("QQ_EMAIL")
    sender_password = os.environ.get("AUTH_CODE")

    recipient_email = receiver
    subject = _subject
    content = _content

    result = send_email(sender_email, sender_password, recipient_email, subject, content)
    return result