import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
from email.header import Header
from dotenv import load_dotenv

load_dotenv()


def send_email(sender_email, sender_password, recipient_email, subject, content, attachments=None, smtp_server='smtp.qq.com', port=465):
    """
    发送支持中英文、Emoji和附件的邮件
    
    参数:
    - sender_email: 发件人邮箱
    - sender_password: 发件人密码（授权码）
    - recipient_email: 收件人邮箱
    - subject: 邮件主题
    - content: 邮件正文（支持HTML）
    - attachments: 附件列表，每个元素是一个附件文件路径
    - smtp_server: SMTP服务器地址
    - port: SMTP服务器端口
    
    返回:
    - 发送结果消息
    """
    server = None
    attachment_count = 0
    failed_attachments = []
    
    try:
        # 创建多部分邮件消息
        msg = MIMEMultipart()
        msg['From'] = sender_email
        msg['To'] = recipient_email

        # 使用Header处理中文和emoji主题
        msg['Subject'] = Header(subject, 'utf-8')

        # 添加正文，支持HTML和中文
        msg.attach(MIMEText(content, 'html', 'utf-8'))

        # 添加附件
        if attachments:
            print(f"处理附件: {attachments}")
            if isinstance(attachments, str):
                # 如果attachments是单个文件路径字符串，转换为列表
                attachments = [attachments]
                
            for file_path in attachments:
                if not file_path or not file_path.strip():
                    print("跳过空附件路径")
                    continue
                    
                file_path = file_path.strip()
                print(f"处理附件文件: {file_path}")
                
                # 检查文件是否存在
                if not os.path.exists(file_path):
                    error_msg = f"附件文件不存在: {file_path}"
                    print(error_msg)
                    failed_attachments.append({"path": file_path, "reason": "文件不存在"})
                    continue
                
                # 检查文件是否可读
                if not os.access(file_path, os.R_OK):
                    error_msg = f"附件文件无法读取 (权限问题): {file_path}"
                    print(error_msg)
                    failed_attachments.append({"path": file_path, "reason": "无法读取文件"})
                    continue
                    
                try:
                    # 获取文件名
                    filename = os.path.basename(file_path)
                    
                    # 读取文件内容
                    with open(file_path, 'rb') as f:
                        attachment = MIMEApplication(f.read())
                    
                    # 添加附件头部
                    attachment.add_header('Content-Disposition', 'attachment', filename=filename)
                    msg.attach(attachment)
                    attachment_count += 1
                    print(f"附件 {filename} 添加成功")
                except Exception as e:
                    error_msg = f"处理附件 {file_path} 出错: {e}"
                    print(error_msg)
                    failed_attachments.append({"path": file_path, "reason": str(e)})

        # 检查环境变量是否设置
        if not sender_email:
            return "发送邮件失败: 未设置QQ_EMAIL环境变量"
        if not sender_password:
            return "发送邮件失败: 未设置AUTH_CODE环境变量"
            
        # 建立SSL连接（QQ邮箱要求使用SSL）
        server = smtplib.SMTP_SSL(smtp_server, port)

        # 登录（使用授权码而不是邮箱密码）
        server.login(sender_email, sender_password)

        # 发送邮件
        server.send_message(msg)
        
        # 返回成功消息，包含附件信息
        if failed_attachments:
            failed_info = ", ".join([f"{a['path']}({a['reason']})" for a in failed_attachments])
            if attachment_count > 0:
                return f"邮件发送成功 🎉，已附加 {attachment_count} 个附件，但以下附件处理失败: {failed_info}"
            else:
                return f"邮件发送成功 🎉，但所有附件处理失败: {failed_info}"
        elif attachment_count > 0:
            return f"邮件发送成功 🎉，已附加 {attachment_count} 个附件"
        else:
            return "邮件发送成功 🎉"

    except Exception as e:
        error_message = f"发送邮件出错: {e}"
        print(error_message)
        return error_message

    finally:
        if server:
            try:
                server.quit()
            except Exception as e:
                # 这里改为打印错误而不是返回，避免覆盖主要结果
                print(f"关闭连接时出错: {e}")


def main(content: str, receiver: str, subject: str, attachments=None):
    """
    发送邮件的主函数
    
    参数:
    - content: 邮件内容
    - receiver: 收件人邮箱
    - subject: 邮件主题
    - attachments: 附件列表或单个附件路径
    
    返回:
    - 发送结果消息
    """
    sender_email = os.environ.get("QQ_EMAIL")
    sender_password = os.environ.get("AUTH_CODE")
    
    # 检查参数
    print(f"发送邮件参数: 收件人={receiver}, 主题={subject}, 附件={attachments}")
    
    # 记录是否设置了环境变量
    if not sender_email:
        print("警告: 未设置QQ_EMAIL环境变量")
    if not sender_password:
        print("警告: 未设置AUTH_CODE环境变量")

    return send_email(
        sender_email,
        sender_password,
        receiver,
        subject,
        content,
        attachments
    )