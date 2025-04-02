import os

def user_information_read() -> str:
    """
    读取用户信息文件，如果不存在则创建空文件
    :return: 文件内容
    """
    file_path = "user_information.txt"
    
    # 检查文件是否存在
    if not os.path.exists(file_path):
        # 如果文件不存在，创建一个空的user_information.txt文件
        try:
            with open(file_path, "w", encoding="utf-8") as file:
                file.write("")  # 创建空文件
            print(f"已创建空的用户信息文件: {file_path}")
        except Exception as e:
            return f"创建用户信息文件时出错: {str(e)}"
    
    try:
        # 读取文件内容
        with open(file_path, "r", encoding="utf-8") as file:
            content = file.read()
        return content
    except Exception as e:
        # 捕获可能的异常（如编码错误）
        return f"读取用户信息文件时出错: {str(e)}"

def update_user_information(key: str, value: str) -> str:
    """
    更新用户信息文件中的特定条目
    :param key: 要更新的信息键（例如"用户邮箱是"、"用户的名字是"等）
    :param value: 新的值
    :return: 更新结果信息
    """
    file_path = "user_information.txt"
    
    # 先确保文件存在
    if not os.path.exists(file_path):
        user_information_read()  # 调用读取函数会自动创建文件
    
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
        
        return f"已更新用户信息: {key}{value}"
    except Exception as e:
        return f"更新用户信息时出错: {str(e)}" 