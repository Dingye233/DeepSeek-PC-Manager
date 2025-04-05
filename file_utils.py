import os

def user_information_read() -> str:
    """
    读取用户信息文件，按以下顺序尝试：
    1. 当前目录下的user_information.txt
    2. 用户文档目录下的DeepSeek-PC-Manager/user_information.txt
    如果都不存在则创建空文件
    :return: 文件内容
    """
    # 首先尝试从当前目录读取
    current_dir_path = os.path.join(os.getcwd(), "user_information.txt")
    
    # 然后尝试从脚本所在目录读取
    script_dir = os.path.dirname(os.path.abspath(__file__))
    script_dir_path = os.path.join(script_dir, "user_information.txt")
    
    # 最后尝试从用户文档目录读取
    user_docs = os.path.join(os.path.expanduser("~"), "Documents", "DeepSeek-PC-Manager")
    user_docs_path = os.path.join(user_docs, "user_information.txt")
    
    # 检查所有可能路径
    paths_to_try = [current_dir_path, script_dir_path, user_docs_path]
    
    # 首先尝试读取现有文件
    for file_path in paths_to_try:
        if os.path.exists(file_path):
            try:
                with open(file_path, "r", encoding="utf-8") as file:
                    content = file.read()
                print(f"已读取用户信息文件: {file_path}")
                return content
            except Exception as e:
                print(f"尝试读取 {file_path} 时出错: {str(e)}")
                continue
    
    # 如果没有找到现有文件，创建一个新文件
    # 首先在当前目录创建
    try:
        target_path = current_dir_path
        with open(target_path, "w", encoding="utf-8") as file:
            file.write("用户关键信息表:user_information.txt\n")
            file.write(f"本项目的本地地址是{os.getcwd()}\n")
        print(f"已创建用户信息文件: {target_path}")
        
        # 如果用户文档目录不存在，创建它并复制文件过去
        if not os.path.exists(user_docs):
            os.makedirs(user_docs)
            with open(user_docs_path, "w", encoding="utf-8") as file:
                file.write("用户关键信息表:user_information.txt\n")
                file.write(f"本项目的本地地址是{os.getcwd()}\n")
        
        return "用户关键信息表:user_information.txt\n" + f"本项目的本地地址是{os.getcwd()}\n"
    except Exception as e:
        return f"创建用户信息文件时出错: {str(e)}"

def update_user_information(key: str, value: str) -> str:
    """
    更新用户信息文件中的特定条目
    :param key: 要更新的信息键（例如"用户邮箱是"、"用户的名字是"等）
    :param value: 新的值
    :return: 更新结果信息
    """
    # 首先尝试从当前目录读取
    current_dir_path = os.path.join(os.getcwd(), "user_information.txt")
    
    # 然后尝试从脚本所在目录读取
    script_dir = os.path.dirname(os.path.abspath(__file__))
    script_dir_path = os.path.join(script_dir, "user_information.txt")
    
    # 最后尝试从用户文档目录读取
    user_docs = os.path.join(os.path.expanduser("~"), "Documents", "DeepSeek-PC-Manager")
    user_docs_path = os.path.join(user_docs, "user_information.txt")
    
    # 检查所有可能路径
    paths_to_try = [current_dir_path, script_dir_path, user_docs_path]
    
    # 查找存在的文件
    file_path = None
    for path in paths_to_try:
        if os.path.exists(path):
            file_path = path
            break
    
    # 如果没有找到文件，调用user_information_read创建一个
    if file_path is None:
        user_information_read()
        file_path = current_dir_path
    
    try:
        # 读取所有行
        with open(file_path, "r", encoding="utf-8") as file:
            lines = file.readlines()
        
        # 查找并更新匹配的行
        updated = False
        for i, line in enumerate(lines):
            if line.startswith(key):
                lines[i] = f"{key}{value}\n"
                updated = True
                break
        
        # 如果没有找到匹配的行，添加新行
        if not updated:
            lines.append(f"{key}{value}\n")
        
        # 写回文件
        with open(file_path, "w", encoding="utf-8") as file:
            file.writelines(lines)
        
        # 如果更新的不是用户文档目录中的文件，同时更新用户文档目录中的文件
        if file_path != user_docs_path and os.path.exists(user_docs):
            if not os.path.exists(user_docs_path):
                # 如果用户文档目录中没有文件，复制整个文件
                with open(user_docs_path, "w", encoding="utf-8") as file:
                    file.writelines(lines)
            else:
                # 否则只更新特定条目
                try:
                    with open(user_docs_path, "r", encoding="utf-8") as file:
                        doc_lines = file.readlines()
                    
                    doc_updated = False
                    for i, line in enumerate(doc_lines):
                        if line.startswith(key):
                            doc_lines[i] = f"{key}{value}\n"
                            doc_updated = True
                            break
                    
                    if not doc_updated:
                        doc_lines.append(f"{key}{value}\n")
                    
                    with open(user_docs_path, "w", encoding="utf-8") as file:
                        file.writelines(doc_lines)
                except Exception:
                    # 如果更新用户文档目录中的文件失败，忽略错误
                    pass
        
        return f"已更新用户信息: {key}{value}"
    except Exception as e:
        return f"更新用户信息时出错: {str(e)}" 