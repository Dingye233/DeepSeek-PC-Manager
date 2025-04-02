import re

# 解析错误信息
def parse_error_message(error_message):
    """
    解析错误信息，提取关键信息
    """
    # 常见错误类型及其解决方案
    error_patterns = {
        r'ModuleNotFoundError: No module named [\'\"]?(\w+)[\'\"]?': "缺少依赖模块 {}，需要安装",
        r'ImportError: (\w+)': "导入模块 {} 失败，检查模块名称是否正确",
        r'SyntaxError: (.+)': "代码语法错误: {}，需要修复",
        r'NameError: name [\'\"]?(\w+)[\'\"]? is not defined': "变量 {} 未定义",
        r'AttributeError: [\'\"]?(\w+)[\'\"]?': "属性或方法 {} 不存在",
        r'TypeError: (.+)': "类型错误: {}",
        r'ValueError: (.+)': "值错误: {}",
        r'PermissionError: (.+)': "权限错误: {}，可能需要管理员权限",
        r'FileNotFoundError: (.+)': "文件未找到: {}",
        r'ConnectionError: (.+)': "连接错误: {}，检查网络连接",
        r'Timeout': "操作超时，可能需要延长等待时间或检查连接",
    }
    
    for pattern, solution_template in error_patterns.items():
        match = re.search(pattern, error_message)
        if match:
            return solution_template.format(match.group(1))
    
    return "未能识别的错误: " + error_message

# 分析任务执行错误
def task_error_analysis(result, task_context):
    """
    分析工具执行结果中的错误，生成修复建议
    """
    if "错误" in result or "Error" in result or "exception" in result.lower() or "failed" in result.lower():
        error_analysis = parse_error_message(result)
        return {
            "has_error": True,
            "error_message": result,
            "analysis": error_analysis,
            "context": task_context
        }
    return {"has_error": False} 