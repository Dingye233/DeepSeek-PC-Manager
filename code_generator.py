import os
import json
from typing import Dict, List, Any, Optional, Union
import importlib.util
import sys
import ast
import traceback
from datetime import datetime

def generate_code(file_name: str, code: str) -> str:
    """
    将代码写入文件并返回文件的绝对路径
    
    :param file_name: 要创建的文件名（带扩展名）
    :param code: 文件内容
    :return: 操作结果信息
    """
    try:
        # 获取文件所在的目录路径
        dir_name = os.path.dirname(file_name)

        # 如果目录路径不为空且目录不存在，则创建目录
        if dir_name and not os.path.exists(dir_name):
            os.makedirs(dir_name, exist_ok=True)

        # 写入内容到文件
        with open(file_name, mode='w', encoding='utf-8') as f:
            f.write(code)
            
        return {
            "success": True,
            "message": f"文件创建成功: {os.path.abspath(file_name)}",
            "path": os.path.abspath(file_name)
        }
    except Exception as e:
        return {
            "success": False,
            "message": f"文件创建失败: {str(e)}",
            "error": str(e)
        }

def verify_python_code(code: str) -> Dict[str, Any]:
    """
    验证Python代码的语法是否正确
    
    :param code: Python代码
    :return: 验证结果
    """
    try:
        ast.parse(code)
        return {
            "valid": True,
            "message": "代码语法正确"
        }
    except SyntaxError as e:
        return {
            "valid": False,
            "message": f"语法错误: 第{e.lineno}行, 列{e.offset}, {e.msg}",
            "line": e.lineno,
            "column": e.offset,
            "text": e.text,
            "error": str(e)
        }
    except Exception as e:
        return {
            "valid": False,
            "message": f"验证错误: {str(e)}",
            "error": str(e)
        }

def execute_python_code(code: str, module_name: str = "__temp_module__") -> Dict[str, Any]:
    """
    执行Python代码并返回结果
    
    :param code: 要执行的Python代码
    :param module_name: 临时模块名称
    :return: 执行结果
    """
    try:
        # 创建临时文件
        temp_file = f"{module_name}.py"
        with open(temp_file, "w", encoding="utf-8") as f:
            f.write(code)
        
        # 动态导入模块
        spec = importlib.util.spec_from_file_location(module_name, temp_file)
        if spec is None:
            return {
                "success": False,
                "message": f"无法加载模块: {module_name}",
                "output": None,
                "error": "Module spec is None"
            }
            
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
        
        # 执行完成后删除临时文件
        if os.path.exists(temp_file):
            os.remove(temp_file)
        
        return {
            "success": True,
            "message": "代码执行成功",
            "module_name": module_name
        }
    except Exception as e:
        # 确保临时文件被删除
        if os.path.exists(temp_file):
            try:
                os.remove(temp_file)
            except:
                pass
        
        return {
            "success": False,
            "message": f"代码执行失败: {str(e)}",
            "error": str(e),
            "traceback": traceback.format_exc()
        }

def create_python_module(module_name: str, functions: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    创建Python模块文件，包含多个函数
    
    :param module_name: 模块名称(不包含.py)
    :param functions: 函数列表，每个函数是一个字典 {"name": "函数名", "params": "参数字符串", "body": "函数体", "docstring": "文档字符串"}
    :return: 操作结果
    """
    try:
        file_name = f"{module_name}.py"
        
        # 构建模块代码
        code = "# -*- coding: utf-8 -*-\n"
        code += f"# {module_name}.py - 自动生成的Python模块\n"
        code += f"# 创建时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        
        # 添加函数
        for func in functions:
            name = func.get("name", "unnamed_function")
            params = func.get("params", "")
            body = func.get("body", "    pass")
            docstring = func.get("docstring", "")
            
            code += f"def {name}({params}):\n"
            if docstring:
                code += f'    """{docstring}"""\n'
            
            # 确保函数体正确缩进
            indented_body = "\n".join(f"    {line}" for line in body.split("\n"))
            code += indented_body + "\n\n"
        
        # 写入文件
        result = generate_code(file_name, code)
        
        # 验证语法
        validation = verify_python_code(code)
        result["validation"] = validation
        
        return result
    
    except Exception as e:
        return {
            "success": False,
            "message": f"模块创建失败: {str(e)}",
            "error": str(e),
            "traceback": traceback.format_exc()
        }

def get_code_suggestion(description: str, language: str = "python") -> Dict[str, Any]:
    """
    根据描述生成代码建议（示例功能，实际实现需要LLM模型）
    
    :param description: 代码功能描述
    :param language: 编程语言
    :return: 建议代码
    """
    # 这个函数在实际应用中应使用LLM来生成代码
    # 这里只是返回一个占位函数
    return {
        "success": True,
        "message": "代码生成仅作示例，实际应用需要调用LLM API",
        "code": f"# {language} code for: {description}\n\ndef example_function():\n    print('This is an example function')\n    # Implement the functionality for: {description}\n"
    }

def append_to_file(file_name: str, content: str) -> Dict[str, Any]:
    """
    向现有文件追加内容
    
    :param file_name: 文件名
    :param content: 要追加的内容
    :return: 操作结果
    """
    try:
        # 确保目录存在
        dir_name = os.path.dirname(file_name)
        if dir_name and not os.path.exists(dir_name):
            os.makedirs(dir_name, exist_ok=True)
            
        # 文件不存在时创建
        if not os.path.exists(file_name):
            with open(file_name, 'w', encoding='utf-8') as f:
                f.write(content)
            action = "创建并写入"
        else:
            # 文件存在时追加
            with open(file_name, 'a', encoding='utf-8') as f:
                f.write(content)
            action = "追加到"
            
        return {
            "success": True,
            "message": f"内容已成功{action}文件: {os.path.abspath(file_name)}",
            "path": os.path.abspath(file_name)
        }
    except Exception as e:
        return {
            "success": False,
            "message": f"向文件追加内容失败: {str(e)}",
            "error": str(e),
            "traceback": traceback.format_exc()
        }

def read_code_file(file_name: str) -> Dict[str, Any]:
    """
    读取代码文件内容
    
    :param file_name: 文件名
    :return: 文件内容
    """
    try:
        if not os.path.exists(file_name):
            return {
                "success": False,
                "message": f"文件不存在: {file_name}",
                "content": None
            }
            
        with open(file_name, 'r', encoding='utf-8') as f:
            content = f.read()
            
        return {
            "success": True,
            "message": f"文件读取成功: {os.path.abspath(file_name)}",
            "content": content,
            "path": os.path.abspath(file_name)
        }
    except Exception as e:
        return {
            "success": False,
            "message": f"文件读取失败: {str(e)}",
            "error": str(e)
        }

# 测试函数
if __name__ == "__main__":
    # 测试代码生成
    test_code = """
def hello_world():
    print("Hello, World!")
    
if __name__ == "__main__":
    hello_world()
"""
    
    result = generate_code("test_generated.py", test_code)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    
    # 测试代码验证
    validation = verify_python_code(test_code)
    print(json.dumps(validation, indent=2, ensure_ascii=False)) 