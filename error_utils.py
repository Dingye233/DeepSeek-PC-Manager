import re
import os
import sys
import time
import random

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
        r'JSONDecodeError': "JSON解析错误，检查API返回格式或数据结构",
        r'KeyError: [\'\"]?(\w+)[\'\"]?': "字典中缺少键 {}",
        r'IndexError: (.+)': "索引错误: {}，可能是列表越界",
        r'ZeroDivisionError': "除零错误，检查分母是否为零",
        r'UnicodeError: (.+)': "Unicode编码错误: {}，检查文本编码",
        r'OSError: (.+)': "操作系统错误: {}，检查文件权限或磁盘空间",
        r'RuntimeError: (.+)': "运行时错误: {}",
        r'MemoryError': "内存不足，尝试降低处理数据量",
        r'Expecting value': "JSON解析错误: 可能收到了非JSON响应，尝试使用不同的API参数",
        r'API rate limit': "API调用频率限制，需要等待后重试",
        r'status code (\d+)': "HTTP状态码错误: {}，检查API状态或认证",
    }
    
    for pattern, solution_template in error_patterns.items():
        match = re.search(pattern, error_message)
        if match:
            return solution_template.format(match.group(1) if match.groups() else "")
    
    return "未能识别的错误: " + error_message

# 分析任务执行错误
def task_error_analysis(result, task_context):
    """
    分析工具执行结果中的错误，生成修复建议
    """
    # 检查是否包含成功执行的标识
    success_indicators = [
        "命令执行成功",
        "无输出",
        "## 命令执行成功",
        "执行成功"
    ]
    
    for indicator in success_indicators:
        if indicator in result:
            # 如果包含成功标识，不判定为错误
            return {"has_error": False}
    
    # 检查是否包含错误标识
    if "错误" in result or "Error" in result or "exception" in result.lower() or "failed" in result.lower():
        # 排除特殊情况：git命令的正常输出
        if "git" in task_context.get("args", {}).get("command", "").lower() and (
            "Changes" in result or 
            "branch" in result or 
            "commit" in result
        ):
            # git命令的正常输出不应被判定为错误
            return {"has_error": False}
            
        error_analysis = parse_error_message(result)
        repair_strategies = generate_repair_strategies(error_analysis, task_context)
        
        return {
            "has_error": True,
            "error_message": result,
            "analysis": error_analysis,
            "repair_strategies": repair_strategies,
            "context": task_context
        }
    
    # 特殊情况：检查JSON解析错误
    if "Expecting value" in result or "JSONDecodeError" in result:
        error_analysis = "JSON解析错误：API可能返回了非JSON格式数据"
        repair_strategies = [
            "尝试使用不同的API参数或请求头",
            "检查API服务是否正常",
            "添加错误重试机制，5秒后重试请求",
            "尝试使用替代API或服务"
        ]
        
        return {
            "has_error": True,
            "error_message": result,
            "analysis": error_analysis,
            "repair_strategies": repair_strategies,
            "context": task_context
        }
        
    return {"has_error": False}

def generate_repair_strategies(error_analysis, task_context):
    """
    根据错误分析生成修复策略
    """
    tool_name = task_context.get("tool", "未知工具")
    args = task_context.get("args", {})
    
    # 通用修复策略
    common_strategies = [
        "尝试使用不同的参数值",
        "检查输入数据格式是否正确",
        "使用try-except块包装代码处理异常",
        "添加详细的日志记录以便调试"
    ]
    
    # 根据错误类型生成特定策略
    specific_strategies = []
    
    if "模块" in error_analysis and "安装" in error_analysis:
        # 模块安装错误
        module_name = re.search(r"模块 (\w+)", error_analysis)
        if module_name:
            module = module_name.group(1)
            specific_strategies = [
                f"使用powershell_command工具执行: pip install {module}",
                f"尝试使用不同版本的依赖: pip install {module}==版本号",
                "检查Python环境路径是否正确",
                "使用conda安装模块: conda install -c conda-forge " + module
            ]
    
    elif "文件未找到" in error_analysis:
        # 文件路径错误
        specific_strategies = [
            "检查文件路径是否正确，使用绝对路径",
            "先检查文件是否存在，再尝试操作",
            "创建包含必要文件夹的路径: os.makedirs(path, exist_ok=True)",
            "查看文件是否有访问权限"
        ]
    
    elif "权限错误" in error_analysis:
        # 权限错误
        specific_strategies = [
            "以管理员身份运行命令",
            "修改文件权限",
            "尝试使用不同的目录或文件名",
            "先验证用户是否有目录的写入权限"
        ]
    
    elif "连接错误" in error_analysis or "网络" in error_analysis:
        # 网络连接错误
        specific_strategies = [
            "检查网络连接是否正常",
            "添加重试机制，间隔5-10秒尝试",
            "使用替代API或服务",
            "检查API密钥或认证是否有效"
        ]
    
    elif "JSON" in error_analysis or "解析" in error_analysis:
        # JSON解析错误
        specific_strategies = [
            "先检查API响应是否为JSON格式",
            "添加错误处理，尝试不同的解析方法",
            "检查API服务状态",
            "使用替代API或服务"
        ]
    
    elif "超时" in error_analysis:
        # 超时错误
        specific_strategies = [
            "增加超时时间参数",
            "分批处理数据减少单次请求量",
            "添加重试机制，间隔递增",
            "检查网络连接质量"
        ]
    
    elif "语法错误" in error_analysis:
        # 语法错误
        specific_strategies = [
            "检查代码语法，特别是括号、缩进和引号",
            "分解复杂表达式为多个简单步骤",
            "使用验证工具验证代码",
            "去除可能导致混淆的特殊字符"
        ]
    
    # 针对特定工具的策略
    tool_specific_strategies = {}
    
    # 搜索工具错误处理
    tool_specific_strategies["web_search"] = [
        "修改搜索关键词，使用更具体的术语",
        "减少搜索结果数量",
        "添加过滤条件限制搜索范围",
        "尝试使用ai_search替代web_search"
    ]
    
    # AI搜索工具错误处理
    tool_specific_strategies["ai_search"] = [
        "简化搜索查询，去除特殊字符",
        "关闭答案合成功能(设置answer=False)",
        "尝试使用web_search替代",
        "检查API密钥或认证状态"
    ]
    
    # 命令行工具错误处理
    tool_specific_strategies["powershell_command"] = [
        "添加错误处理参数，如-ErrorAction SilentlyContinue",
        "将复杂命令拆分为多个简单命令",
        "使用Python脚本替代命令行操作",
        "检查命令语法是否正确"
    ]
    
    tool_specific_strategies["cmd_command"] = [
        "添加错误重定向: 2>nul",
        "使用Python脚本替代命令行操作",
        "检查命令语法是否正确",
        "检查系统中是否安装了命令对应的程序"
    ]
    
    # Python代码工具错误处理
    tool_specific_strategies["write_code"] = [
        "简化代码逻辑，分步处理",
        "添加详细的错误处理和日志记录",
        "使用更健壮的库或方法",
        "验证代码语法和依赖"
    ]
    
    # 文件读取工具错误处理
    tool_specific_strategies["read_file"] = [
        "检查文件路径是否正确，优先使用绝对路径",
        "先确认文件是否存在: os.path.exists(file_path)",
        "尝试不同的编码，如utf-8, cp1252, latin1",
        "检查文件权限"
    ]
    
    # 结合通用策略和特定策略
    strategies = specific_strategies or common_strategies
    
    # 添加工具特定策略
    if tool_name in tool_specific_strategies:
        strategies.extend(tool_specific_strategies[tool_name])
    
    # 确保策略不重复
    strategies = list(dict.fromkeys(strategies))
    
    # 随机排序，避免总是提供相同的解决方案顺序
    random.shuffle(strategies)
    
    # 限制策略数量，避免过多
    return strategies[:5]

def suggest_alternative_tool(failed_tool, task_context):
    """
    根据失败的工具建议替代工具
    """
    alternative_tools = {
        "web_search": ["ai_search", "semantic_rerank"],
        "ai_search": ["web_search", "R1_opt"],
        "powershell_command": ["cmd_command", "write_code"],
        "cmd_command": ["powershell_command", "write_code"],
        "read_file": ["read_code"],
        "read_code": ["read_file"],
        "write_code": ["append_code", "verify_code"],
        "verify_code": ["write_code"],
    }
    
    if failed_tool in alternative_tools:
        return alternative_tools[failed_tool]
    return []

def get_error_retry_suggestions(error_message, tool_name, args):
    """
    基于错误消息和工具信息提供重试建议
    """
    # 解析错误类型
    error_type = "unknown"
    if "ModuleNotFoundError" in error_message or "ImportError" in error_message:
        error_type = "module_not_found"
    elif "FileNotFoundError" in error_message:
        error_type = "file_not_found"
    elif "PermissionError" in error_message:
        error_type = "permission_error"
    elif "ConnectionError" in error_message or "Timeout" in error_message:
        error_type = "network_error"
    elif "JSONDecodeError" in error_message or "Expecting value" in error_message:
        error_type = "json_error"
    elif "SyntaxError" in error_message:
        error_type = "syntax_error"
    
    # 基于错误类型和工具提供建议
    suggestions = {
        "module_not_found": {
            "message": "缺少必要的Python模块",
            "actions": [
                "尝试安装缺失的模块",
                "检查模块名称是否正确",
                "使用不同版本的模块"
            ]
        },
        "file_not_found": {
            "message": "找不到指定的文件",
            "actions": [
                "检查文件路径是否正确",
                "使用绝对路径而非相对路径",
                "先创建所需的目录结构",
                "检查文件名是否包含特殊字符"
            ]
        },
        "permission_error": {
            "message": "没有足够的权限执行操作",
            "actions": [
                "检查文件或目录的权限设置",
                "使用管理员权限执行操作",
                "尝试在不同目录下执行操作"
            ]
        },
        "network_error": {
            "message": "网络连接问题",
            "actions": [
                "检查网络连接是否正常",
                "添加重试机制，间隔5-10秒尝试",
                "使用替代API或服务",
                "检查API密钥或认证是否过期"
            ]
        },
        "json_error": {
            "message": "JSON数据解析错误",
            "actions": [
                "API可能返回了HTML而非JSON，检查API状态",
                "验证API密钥是否有效",
                "尝试不同的API参数",
                "使用替代API或服务"
            ]
        },
        "syntax_error": {
            "message": "代码语法错误",
            "actions": [
                "检查代码语法，特别是括号、缩进和引号",
                "分解复杂表达式为多个简单步骤",
                "使用验证工具验证代码",
                "去除可能导致混淆的特殊字符"
            ]
        },
        "unknown": {
            "message": "未知错误",
            "actions": [
                "记录详细错误信息",
                "尝试简化操作步骤",
                "使用替代方法或工具",
                "添加错误处理和重试机制"
            ]
        }
    }
    
    return suggestions.get(error_type, suggestions["unknown"]) 