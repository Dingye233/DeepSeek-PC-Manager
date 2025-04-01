import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.header import Header
from dotenv import load_dotenv

load_dotenv()


def send_email(sender_email, sender_password, recipient_email, subject, content, smtp_server='smtp.qq.com', port=465):
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

        # 建立SSL连接（QQ邮箱要求使用SSL）
        server = smtplib.SMTP_SSL(smtp_server, port)

        # 登录（使用授权码而不是邮箱密码）
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
            except Exception as e:
                # 这里改为打印错误而不是返回，避免覆盖主要结果
                print(f"关闭连接时出错: {e}")


def main(_content: str,receiver: str, _subject: str):
    sender_email = os.environ.get("QQ_EMAIL")
    sender_password = os.environ.get("AUTH_CODE")

    return send_email(
        sender_email,
        sender_password,
        receiver,
        _subject,
        _content
    )