import os
import json
from typing import Dict, List, Any, Optional, Union
import importlib.util
import sys
import ast
import traceback
import re
from datetime import datetime

def generate_code(file_name: str, code: str) -> Dict[str, Any]:
    """
    将代码写入文件并返回详细结果
    
    :param file_name: 要创建的文件名（带扩展名）
    :param code: 文件内容
    :return: 包含操作状态、路径和消息的结构化字典
    """
    try:
        # 获取文件所在的目录路径
        dir_name = os.path.dirname(file_name)

        # 如果目录路径不为空且目录不存在，则创建目录
        if dir_name and not os.path.exists(dir_name):
            os.makedirs(dir_name, exist_ok=True)

        # 获取文件扩展名
        _, ext = os.path.splitext(file_name)
        
        # 写入内容到文件
        with open(file_name, mode='w', encoding='utf-8') as f:
            f.write(code)
            
        abs_path = os.path.abspath(file_name)
        
        # 针对Python文件，进行语法检查
        validation_result = {}
        if ext.lower() == '.py':
            validation_result = verify_python_code(code)
        
        return {
            "success": True,
            "message": f"文件创建成功: {abs_path}",
            "path": abs_path,
            "file_size": os.path.getsize(file_name),
            "extension": ext,
            "created_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "validation": validation_result
        }
    except Exception as e:
        return {
            "success": False,
            "message": f"文件创建失败: {str(e)}",
            "error": str(e),
            "traceback": traceback.format_exc()
        }

def verify_python_code(code: str) -> Dict[str, Any]:
    """
    验证Python代码的语法是否正确，并提供详细的错误信息
    
    :param code: Python代码
    :return: 包含验证结果和详细错误信息的字典
    """
    try:
        # 解析代码
        tree = ast.parse(code)
        
        # 收集代码中定义的函数和类
        functions = []
        classes = []
        imports = []
        
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                functions.append({
                    "name": node.name,
                    "line": node.lineno,
                    "args": [arg.arg for arg in node.args.args],
                    "docstring": ast.get_docstring(node)
                })
            elif isinstance(node, ast.ClassDef):
                classes.append({
                    "name": node.name,
                    "line": node.lineno,
                    "bases": [base.id if isinstance(base, ast.Name) else "..." for base in node.bases],
                    "docstring": ast.get_docstring(node)
                })
            elif isinstance(node, ast.Import):
                for name in node.names:
                    imports.append({"module": name.name, "alias": name.asname})
            elif isinstance(node, ast.ImportFrom):
                for name in node.names:
                    imports.append({
                        "module": f"{node.module}.{name.name}" if node.module else name.name,
                        "alias": name.asname
                    })
        
        return {
            "valid": True,
            "message": "代码语法正确",
            "structure": {
                "functions": functions,
                "classes": classes,
                "imports": imports,
                "line_count": len(code.splitlines())
            }
        }
    except SyntaxError as e:
        # 提取出错误行的上下文
        lines = code.splitlines()
        context_lines = []
        
        start = max(0, e.lineno - 3)
        end = min(len(lines), e.lineno + 2)
        
        for i in range(start, end):
            line_indicator = "→ " if i + 1 == e.lineno else "  "
            context_lines.append(f"{i+1}: {line_indicator}{lines[i]}")
            
            # 在错误位置添加指示器
            if i + 1 == e.lineno:
                pointer = " " * (len(str(i+1)) + 4 + e.offset - 1) + "^"
                context_lines.append(pointer)
        
        return {
            "valid": False,
            "message": f"语法错误: 第{e.lineno}行, 列{e.offset}, {e.msg}",
            "line": e.lineno,
            "column": e.offset,
            "text": e.text,
            "error": str(e),
            "context": "\n".join(context_lines)
        }
    except Exception as e:
        return {
            "valid": False,
            "message": f"验证错误: {str(e)}",
            "error": str(e),
            "traceback": traceback.format_exc()
        }

def analyze_code(code: str, file_name: str = "") -> Dict[str, Any]:
    """
    分析代码结构、复杂度和潜在问题
    
    :param code: 要分析的代码
    :param file_name: 文件名（可选，用于确定语言）
    :return: 包含分析结果的字典
    """
    # 确定编程语言
    if file_name:
        _, ext = os.path.splitext(file_name)
        ext = ext.lower()
    else:
        # 猜测语言类型
        if "def " in code and "import " in code:
            ext = ".py"
        elif "<html" in code.lower():
            ext = ".html"
        elif "function " in code and "{" in code:
            ext = ".js"
        else:
            ext = ""

    result = {
        "language": ext[1:] if ext else "unknown",
        "line_count": len(code.splitlines()),
        "char_count": len(code),
        "metrics": {}
    }

    # Python特定分析
    if ext == ".py":
        try:
            tree = ast.parse(code)
            
            # 基本计数
            function_count = 0
            class_count = 0
            comment_lines = 0
            imports = []
            complexity = 0
            
            # 计算注释行数
            lines = code.splitlines()
            for line in lines:
                stripped = line.strip()
                if stripped.startswith('#'):
                    comment_lines += 1
            
            # 计算圈复杂度（基于分支判断和循环）
            for node in ast.walk(tree):
                if isinstance(node, (ast.If, ast.For, ast.While, ast.comprehension)):
                    complexity += 1
                elif isinstance(node, ast.BoolOp):
                    if isinstance(node.op, ast.And) or isinstance(node.op, ast.Or):
                        complexity += len(node.values) - 1
                elif isinstance(node, ast.FunctionDef):
                    function_count += 1
                    # 给每个函数一个基础值
                    complexity += 1
                elif isinstance(node, ast.ClassDef):
                    class_count += 1
                elif isinstance(node, ast.Import):
                    for name in node.names:
                        imports.append(name.name)
                elif isinstance(node, ast.ImportFrom):
                    if node.module:
                        for name in node.names:
                            imports.append(f"{node.module}.{name.name}")
            
            result["metrics"] = {
                "functions": function_count,
                "classes": class_count,
                "comments": comment_lines,
                "imports": imports,
                "complexity": complexity,
                "comment_ratio": round(comment_lines / result["line_count"] * 100, 2) if result["line_count"] > 0 else 0
            }
            
            # 查找潜在问题
            issues = []
            
            # 检查过长的行
            for i, line in enumerate(lines):
                if len(line) > 100:
                    issues.append({
                        "type": "style",
                        "message": f"第{i+1}行超过100个字符(长度为{len(line)})",
                        "line": i+1
                    })
            
            # 检查未使用的导入
            imported_names = set()
            for imp in imports:
                if '.' in imp:
                    imported_names.add(imp.split('.')[-1])
                else:
                    imported_names.add(imp)
            
            code_without_comments = re.sub(r'#.*$', '', code, flags=re.MULTILINE)
            for name in imported_names:
                # 排除常见的特殊情况
                if name in ['*', 'load_dotenv']:
                    continue
                # 检查导入名称是否在代码中使用
                pattern = r'\b' + re.escape(name) + r'\b'
                if not re.search(pattern, code_without_comments):
                    issues.append({
                        "type": "warning",
                        "message": f"可能存在未使用的导入: {name}"
                    })
            
            result["issues"] = issues
            
        except Exception as e:
            result["error"] = str(e)
    
    return result

def execute_python_code(code: str, module_name: str = "__temp_module__") -> Dict[str, Any]:
    """
    执行Python代码并返回结果，包括执行时间和输出信息
    
    :param code: 要执行的Python代码
    :param module_name: 临时模块名称
    :return: 包含执行结果、输出和错误信息的字典
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
            
        # 捕获标准输出
        original_stdout = sys.stdout
        sys.stdout = OutputCapture()
        
        start_time = datetime.now()
        
        # 执行代码
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
        
        end_time = datetime.now()
        execution_time = (end_time - start_time).total_seconds()
        
        # 恢复标准输出并获取捕获的输出
        captured_output = sys.stdout.getvalue()
        sys.stdout = original_stdout
        
        # 执行完成后删除临时文件
        if os.path.exists(temp_file):
            os.remove(temp_file)
        
        return {
            "success": True,
            "message": "代码执行成功",
            "module_name": module_name,
            "execution_time": execution_time,
            "output": captured_output
        }
    except Exception as e:
        # 恢复标准输出
        if 'original_stdout' in locals():
            sys.stdout = original_stdout
        
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

class OutputCapture:
    """用于捕获标准输出的辅助类"""
    def __init__(self):
        self.data = []
    
    def write(self, text):
        self.data.append(text)
    
    def getvalue(self):
        return ''.join(self.data)
    
    def flush(self):
        pass

def create_python_module(module_name: str, functions: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    创建Python模块文件，包含多个函数，支持更丰富的函数定义选项
    
    :param module_name: 模块名称(不包含.py)
    :param functions: 函数列表，每个函数是一个字典 {"name": "函数名", "params": "参数字符串", "body": "函数体", "docstring": "文档字符串", "decorators": ["装饰器1", "装饰器2"]}
    :return: 包含操作结果的详细字典
    """
    try:
        file_name = f"{module_name}.py"
        
        # 构建模块代码
        code = "# -*- coding: utf-8 -*-\n"
        code += f"# {module_name}.py - 自动生成的Python模块\n"
        code += f"# 创建时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        
        # 自动添加导入语句(从函数体中检测)
        imports = set()
        for func in functions:
            body = func.get("body", "")
            # 简单的导入检测
            imports_in_body = re.findall(r'(?:import|from)\s+([a-zA-Z0-9_.]+)', body)
            imports.update(imports_in_body)
        
        # 添加导入语句
        if imports:
            for imp in sorted(imports):
                if '.' in imp:  # 可能是from x import y形式
                    continue  # 简单起见，忽略这种情况
                code += f"import {imp}\n"
            code += "\n"
        
        # 添加函数
        for func in functions:
            name = func.get("name", "unnamed_function")
            params = func.get("params", "")
            body = func.get("body", "    pass")
            docstring = func.get("docstring", "")
            decorators = func.get("decorators", [])
            
            # 添加装饰器
            for decorator in decorators:
                code += f"@{decorator}\n"
            
            code += f"def {name}({params}):\n"
            if docstring:
                code += f'    """{docstring}"""\n'
            
            # 确保函数体正确缩进
            indented_body = "\n".join(f"    {line}" for line in body.split("\n"))
            code += indented_body + "\n\n"
        
        # 添加模块测试代码
        code += "\n# 模块自测代码\n"
        code += "if __name__ == \"__main__\":\n"
        code += "    print(f\"模块 {__name__} 已加载\")\n"
        
        # 写入文件
        result = generate_code(file_name, code)
        
        # 验证语法
        validation = verify_python_code(code)
        result["validation"] = validation
        
        # 添加代码结构分析
        result["analysis"] = analyze_code(code, file_name)
        
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
    向现有文件追加内容，提供更详细的结果信息
    
    :param file_name: 文件名
    :param content: 要追加的内容
    :return: 包含操作详情的结果字典
    """
    try:
        # 确保目录存在
        dir_name = os.path.dirname(file_name)
        if dir_name and not os.path.exists(dir_name):
            os.makedirs(dir_name, exist_ok=True)
            
        # 获取原始文件大小
        original_size = 0
        if os.path.exists(file_name):
            original_size = os.path.getsize(file_name)
            with open(file_name, 'a', encoding='utf-8') as f:
                f.write(content)
            action = "追加到"
        else:
            # 文件不存在时创建
            with open(file_name, 'w', encoding='utf-8') as f:
                f.write(content)
            action = "创建并写入"
        
        # 获取更新后文件大小
        new_size = os.path.getsize(file_name)
        
        return {
            "success": True,
            "message": f"内容已成功{action}文件: {os.path.abspath(file_name)}",
            "path": os.path.abspath(file_name),
            "original_size": original_size,
            "new_size": new_size,
            "added_bytes": new_size - original_size,
            "added_lines": content.count('\n') + (0 if content.endswith('\n') else 1)
        }
    except Exception as e:
        return {
            "success": False,
            "message": f"向文件追加内容失败: {str(e)}",
            "error": str(e),
            "traceback": traceback.format_exc()
        }

def read_code_file(file_name: str, with_analysis: bool = True) -> Dict[str, Any]:
    """
    读取代码文件内容，并可选择性地提供代码分析
    
    :param file_name: 文件名
    :param with_analysis: 是否包含代码分析
    :return: 文件内容和分析结果
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
        
        result = {
            "success": True,
            "message": f"文件读取成功: {os.path.abspath(file_name)}",
            "content": content,
            "path": os.path.abspath(file_name),
            "size": os.path.getsize(file_name),
            "last_modified": datetime.fromtimestamp(os.path.getmtime(file_name)).strftime("%Y-%m-%d %H:%M:%S")
        }
        
        if with_analysis:
            result["analysis"] = analyze_code(content, file_name)
            
            # 针对Python文件，添加语法分析
            _, ext = os.path.splitext(file_name)
            if ext.lower() == '.py':
                result["validation"] = verify_python_code(content)
        
        return result
    except UnicodeDecodeError:
        # 尝试使用不同的编码
        for encoding in ['gbk', 'latin-1', 'cp1252']:
            try:
                with open(file_name, 'r', encoding=encoding) as f:
                    content = f.read()
                
                result = {
                    "success": True,
                    "message": f"文件读取成功(使用{encoding}编码): {os.path.abspath(file_name)}",
                    "content": content,
                    "path": os.path.abspath(file_name),
                    "encoding": encoding
                }
                
                if with_analysis:
                    result["analysis"] = analyze_code(content, file_name)
                
                return result
            except UnicodeDecodeError:
                continue
        
        return {
            "success": False,
            "message": f"文件编码无法识别: {file_name}",
            "error": "UnicodeDecodeError: 尝试了utf-8、gbk、latin-1和cp1252编码，但都失败了"
        }
    except Exception as e:
        return {
            "success": False,
            "message": f"文件读取失败: {str(e)}",
            "error": str(e),
            "traceback": traceback.format_exc()
        }
