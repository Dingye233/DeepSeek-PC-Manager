import code_generator
import json
from typing import Dict, Any, Optional, List, Union
import os
import re

def write_code(file_name: str, code: str) -> str:
    """
    将代码写入文件并返回结果
    
    该函数会自动创建目录路径（如果需要），并提供详细的操作结果
    
    :param file_name: 要创建的文件名（带扩展名），可以是相对路径或绝对路径
    :param code: 文件内容
    :return: 包含操作结果的JSON字符串
    
    示例:
      成功: {"success": true, "message": "文件创建成功: /path/to/file.py", "path": "/path/to/file.py"}
      失败: {"success": false, "message": "文件创建失败: [错误原因]", "error": "[错误详情]"}
    """
    result = code_generator.generate_code(file_name, code)
    response = json.dumps(result, ensure_ascii=False, indent=2)
    
    # 为LLM提供明确的成功或失败信息
    success = result.get("success", False)
    if success:
        return f"文件创建成功: {result.get('path', file_name)}\n{response}"
    else:
        return f"文件创建失败: {result.get('error', '未知错误')}\n{response}"

def verify_code(code: str) -> str:
    """
    验证Python代码语法是否正确
    
    该函数使用Python的AST模块分析代码，不会执行代码，只进行语法检查
    
    :param code: 要验证的Python代码
    :return: 包含验证结果的JSON字符串，包括代码结构分析和潜在问题
    
    示例:
      通过: {"valid": true, "message": "代码语法正确", "structure": {...}}
      失败: {"valid": false, "message": "语法错误: 第10行, 列5, invalid syntax", "line": 10, ...}
    """
    result = code_generator.verify_python_code(code)
    response = json.dumps(result, ensure_ascii=False, indent=2)
    
    # 为LLM提供简洁的验证结果摘要
    if result.get("valid", False):
        return f"代码语法验证通过 ✓\n{response}"
    else:
        return f"代码语法错误 ✗: {result.get('message', '未知错误')}\n{response}"

def append_code(file_name: str, content: str) -> str:
    """
    向文件追加代码内容
    
    如果文件不存在，则创建新文件；如果已存在，则在文件末尾追加内容
    
    :param file_name: 文件名，可以是相对路径或绝对路径
    :param content: 要追加的内容
    :return: 包含操作结果的JSON字符串
    
    示例:
      成功: {"success": true, "message": "内容已成功追加到文件: /path/to/file.py", ...}
      失败: {"success": false, "message": "向文件追加内容失败: [错误原因]", ...}
    """
    result = code_generator.append_to_file(file_name, content)
    response = json.dumps(result, ensure_ascii=False, indent=2)
    
    # 为LLM提供明确的成功或失败信息
    success = result.get("success", False)
    if success:
        action = "创建" if "创建" in result.get("message", "") else "更新"
        return f"文件{action}成功: {result.get('path', file_name)}\n{response}"
    else:
        return f"文件操作失败: {result.get('error', '未知错误')}\n{response}"

def read_code(file_name: str, with_analysis: bool = True) -> str:
    """
    读取代码文件内容并可选提供分析
    
    该函数会尝试使用多种编码（utf-8, gbk等）读取文件，并自动检测文件类型
    
    :param file_name: 文件名，可以是相对路径或绝对路径
    :param with_analysis: 是否包含代码分析（默认为True）
    :return: 包含文件内容和分析结果的JSON字符串
    
    示例:
      成功: {"success": true, "content": "def hello():\\n    print('Hello')", "path": "...", "analysis": {...}}
      失败: {"success": false, "message": "文件不存在: /path/to/file.py", ...}
    """
    result = code_generator.read_code_file(file_name, with_analysis)
    
    # 为了避免返回超长的JSON，截断文件内容以适应LLM处理
    if "content" in result and result["content"] and len(result["content"]) > 10000:
        original_length = len(result["content"])
        result["content"] = result["content"][:10000] + f"\n\n... [截断内容，共{original_length}字节] ..."
        result["truncated"] = True
    
    response = json.dumps(result, ensure_ascii=False, indent=2)
    
    # 为LLM提供简洁的读取结果摘要
    success = result.get("success", False)
    if success:
        file_type = result.get("analysis", {}).get("language", "")
        file_type_str = f" ({file_type}文件)" if file_type else ""
        return f"文件读取成功{file_type_str}: {result.get('path', file_name)}\n{response}"
    else:
        return f"文件读取失败: {result.get('error', '未知错误')}\n{response}"

def create_module(module_name: str, functions_json: str) -> str:
    """
    创建包含多个函数的Python模块
    
    自动生成适当的导入语句、文档字符串和模块结构
    
    :param module_name: 模块名称(不含.py)
    :param functions_json: 函数定义的JSON字符串，格式为 
                          [{"name": "函数名", "params": "参数字符串", 
                            "body": "函数体", "docstring": "文档字符串",
                            "decorators": ["装饰器1", "装饰器2"]}]
    :return: 包含操作结果的JSON字符串
    
    示例JSON输入:
    [
      {
        "name": "add",
        "params": "a: int, b: int",
        "body": "return a + b",
        "docstring": "将两个数相加"
      },
      {
        "name": "subtract",
        "params": "a: int, b: int",
        "body": "return a - b",
        "docstring": "计算两个数的差"
      }
    ]
    
    输出示例:
      成功: {"success": true, "message": "文件创建成功: utils.py", "path": "/path/to/utils.py", ...}
      失败: {"success": false, "message": "解析函数JSON失败: [错误原因]", ...}
    """
    try:
        functions = json.loads(functions_json)
        
        # 验证函数格式
        for i, func in enumerate(functions):
            if "name" not in func:
                return json.dumps({
                    "success": False,
                    "message": f"第{i+1}个函数缺少'name'字段",
                    "error": "函数格式错误"
                }, ensure_ascii=False, indent=2)
            
            # 确保函数体以适当的缩进格式化
            if "body" in func and func["body"]:
                # 移除所有前导缩进
                lines = func["body"].splitlines()
                if lines:
                    min_indent = min((len(line) - len(line.lstrip())) for line in lines if line.strip())
                    func["body"] = "\n".join(line[min_indent:] if line.strip() else line for line in lines)
        
        result = code_generator.create_python_module(module_name, functions)
        
        # 添加生成代码的简要信息
        if result.get("success", False):
            function_count = len(functions)
            function_names = [f['name'] for f in functions if 'name' in f]
            result["summary"] = {
                "module_name": module_name,
                "function_count": function_count,
                "function_names": function_names
            }
        
        response = json.dumps(result, ensure_ascii=False, indent=2)
        
        # 为LLM提供明确的成功或失败信息
        success = result.get("success", False)
        if success:
            return f"模块创建成功: {module_name}.py，包含{len(functions)}个函数\n{response}"
        else:
            return f"模块创建失败: {result.get('error', '未知错误')}\n{response}"
            
    except Exception as e:
        error_result = {
            "success": False,
            "message": f"解析函数JSON失败: {str(e)}",
            "error": str(e)
        }
        return f"模块创建失败: {str(e)}\n{json.dumps(error_result, ensure_ascii=False, indent=2)}"

def analyze_code(file_path: str) -> str:
    """
    分析代码文件的结构、复杂度和潜在问题
    
    :param file_path: 要分析的代码文件路径
    :return: 包含分析结果的JSON字符串
    
    分析内容包括:
    - 代码结构: 函数、类、导入等
    - 代码度量: 行数、复杂度、注释比例等
    - 潜在问题: 未使用的导入、过长的行等
    """
    try:
        # 读取文件内容
        read_result = code_generator.read_code_file(file_path, True)
        
        if not read_result.get("success", False):
            return json.dumps(read_result, ensure_ascii=False, indent=2)
        
        # 文件内容已经在read_code_file中被分析
        analysis = read_result.get("analysis", {})
        validation = read_result.get("validation", {})
        
        # 合并分析和验证结果
        result = {
            "success": True,
            "file_path": file_path,
            "analysis": analysis,
            "validation": validation if validation else {}
        }
        
        response = json.dumps(result, ensure_ascii=False, indent=2)
        
        # 为LLM提供分析摘要
        language = analysis.get("language", "未知")
        line_count = analysis.get("line_count", 0)
        
        metrics = analysis.get("metrics", {})
        functions = metrics.get("functions", 0)
        classes = metrics.get("classes", 0)
        complexity = metrics.get("complexity", 0)
        
        issues = analysis.get("issues", [])
        issue_count = len(issues)
        
        return f"代码分析完成: {file_path} ({language}文件, {line_count}行, {functions}函数, {classes}类, 复杂度:{complexity}, {issue_count}个潜在问题)\n{response}"
        
    except Exception as e:
        error_result = {
            "success": False,
            "message": f"代码分析失败: {str(e)}",
            "error": str(e)
        }
        return json.dumps(error_result, ensure_ascii=False, indent=2) 