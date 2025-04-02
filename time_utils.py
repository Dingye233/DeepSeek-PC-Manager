from datetime import datetime

def get_current_time(timezone: str = "UTC") -> str:
    """
    获取当前时间
    :param timezone: 时区，可选值为 "UTC" 或 "local"
    :return: 格式化的时间字符串
    """
    now = datetime.utcnow() if timezone == "UTC" else datetime.now()
    return now.strftime("%Y-%m-%d %H:%M:%S") 