import os


def encoding(code: str, file_name: str) -> str:
    """
    将 code 写入文件，并返回文件的绝对路径。

    :param code: 要写入文件的内容
    :param file_name: 文件名（可以是相对路径或绝对路径）
    :return: 文件的绝对路径
    """
    # 获取文件所在的目录路径
    dir_name = os.path.dirname(file_name)

    # 如果目录路径不为空且目录不存在，则创建目录
    if dir_name and not os.path.exists(dir_name):
        os.makedirs(dir_name, exist_ok=True)

    # 写入内容到文件
    with open(file_name, mode='w', encoding='utf-8') as f:
        f.write(code)

    # 返回文件的绝对路径
    return "文件创建成功并且成功写入内容："+os.path.abspath(file_name)
