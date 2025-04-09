# 控制台打印辅助函数

def print_color(text, color_code):
    """使用颜色代码打印文本，去掉多余的空行"""
    # 去掉文本开头的空行和换行符
    text = text.lstrip('\n')
    # 去掉文本末尾的多余换行符，保留最多一个
    text = text.rstrip('\n') + '\n' if text else ''
    print(f"\033[{color_code}m{text}\033[0m", end='')

def print_success(text):
    """打印成功消息（绿色）"""
    print_color(text, "32")

def print_error(text):
    """打印错误消息（红色）"""
    print_color(text, "31")

def print_warning(text):
    """打印警告消息（黄色）"""
    print_color(text, "33")

def print_info(text):
    """打印信息消息（蓝色）"""
    print_color(text, "36")

def print_highlight(text):
    """打印高亮消息（紫色）"""
    print_color(text, "35") 