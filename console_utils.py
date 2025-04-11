# 控制台打印辅助函数

# 扩展颜色常量
# 基础颜色
BLACK = "30"
RED = "31"
GREEN = "32"
YELLOW = "33"
BLUE = "34"
MAGENTA = "35"
CYAN = "36"
WHITE = "37"

# 亮色变体
BRIGHT_BLACK = "90"
BRIGHT_RED = "91"
BRIGHT_GREEN = "92"
BRIGHT_YELLOW = "93"
BRIGHT_BLUE = "94"
BRIGHT_MAGENTA = "95"
BRIGHT_CYAN = "96"
BRIGHT_WHITE = "97"

# 背景色
BG_BLACK = "40"
BG_RED = "41"
BG_GREEN = "42"
BG_YELLOW = "43"
BG_BLUE = "44"
BG_MAGENTA = "45"
BG_CYAN = "46"
BG_WHITE = "47"

# 格式
BOLD = "1"
UNDERLINE = "4"
REVERSED = "7"

def print_color(text, color_code, bg_code=None, format_code=None):
    """
    使用颜色代码打印文本，支持前景色、背景色和格式
    
    Args:
        text: 要打印的文本
        color_code: 颜色代码（前景色）
        bg_code: 背景色代码（可选）
        format_code: 格式代码，如粗体、下划线等（可选）
    """
    # 去掉文本开头的空行和换行符
    text = text.lstrip('\n')
    # 去掉文本末尾的多余换行符，保留最多一个
    text = text.rstrip('\n') + '\n' if text else ''
    
    # 构建ANSI代码
    format_str = []
    if format_code:
        format_str.append(format_code)
    if color_code:
        format_str.append(color_code)
    if bg_code:
        format_str.append(bg_code)
    
    format_combined = ";".join(format_str)
    
    print(f"\033[{format_combined}m{text}\033[0m", end='')

# 基础颜色函数
def print_success(text):
    """打印成功消息（绿色）"""
    print_color(text, GREEN)

def print_error(text):
    """打印错误消息（红色）"""
    print_color(text, RED)

def print_warning(text):
    """打印警告消息（黄色）"""
    print_color(text, YELLOW)

def print_info(text):
    """打印信息消息（青色）"""
    print_color(text, CYAN)

def print_highlight(text):
    """打印高亮消息（洋红色）"""
    print_color(text, MAGENTA)

# 针对任务模块的专用颜色函数
def print_task_header(text):
    """打印任务标题（白底蓝字）"""
    print_color(text, BLUE, BG_WHITE, BOLD)

def print_task_iteration(text):
    """打印任务迭代信息（亮蓝色）"""
    print_color(text, BRIGHT_BLUE)

def print_task_progress(text):
    """打印任务进度（亮青色）"""
    print_color(text, BRIGHT_CYAN)

def print_task_result(text):
    """打印任务结果（亮绿色）"""
    print_color(text, BRIGHT_GREEN)

def print_task_summary(text):
    """打印任务摘要（亮紫色底白字）"""
    print_color(text, WHITE, BG_MAGENTA)

def print_tool_name(text):
    """打印工具名称（亮黄色）"""
    print_color(text, BRIGHT_YELLOW, format_code=BOLD)

def print_tool_args(text):
    """打印工具参数（暗黄色）"""
    print_color(text, YELLOW)

def print_token_info(text):
    """打印Token信息（亮黑色/灰色）"""
    print_color(text, BRIGHT_BLACK)

def print_system_info(text):
    """打印系统信息（反转的青色）"""
    print_color(text, CYAN, format_code=REVERSED)

def print_debug(text):
    """打印调试信息（灰色）"""
    print_color(text, BRIGHT_BLACK) 