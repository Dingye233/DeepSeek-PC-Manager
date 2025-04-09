"""
增强代码审验模块 - 提供高级代码验证功能
能够检测各种代码问题并提供修复建议
"""

import os
import json
import ast
import re
import importlib.util
import sys
from typing import Dict, Any, List, Optional, Tuple
import subprocess
import tempfile

def validate_python_code(code: str) -> Dict[str, Any]:
    """
    全面验证Python代码，检查语法错误、逻辑问题和潜在的bug
    
    Args:
        code: 要验证的Python代码
        
    Returns:
        包含验证结果的字典
    """
    result = {
        "有效": True,
        "错误": [],
        "警告": [],
        "建议": [],
        "代码结构": {}
    }
    
    # 1. 检查语法错误
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        result["有效"] = False
        result["错误"].append({
            "类型": "语法错误",
            "信息": str(e),
            "行号": e.lineno,
            "列号": e.offset,
            "详情": e.text
        })
        return result
    
    # 2. 分析代码结构
    functions = []
    classes = []
    imports = []
    variables = []
    
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            functions.append({
                "名称": node.name,
                "行号": node.lineno,
                "参数": [arg.arg for arg in node.args.args],
                "文档": ast.get_docstring(node) or ""
            })
        elif isinstance(node, ast.ClassDef):
            classes.append({
                "名称": node.name,
                "行号": node.lineno,
                "父类": [base.id if isinstance(base, ast.Name) else "..." for base in node.bases],
                "文档": ast.get_docstring(node) or ""
            })
        elif isinstance(node, ast.Import):
            for name in node.names:
                imports.append({
                    "模块": name.name,
                    "别名": name.asname,
                    "行号": node.lineno
                })
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            for name in node.names:
                imports.append({
                    "模块": f"{module}.{name.name}" if module else name.name,
                    "别名": name.asname,
                    "行号": node.lineno
                })
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    variables.append({
                        "名称": target.id,
                        "行号": node.lineno
                    })
    
    result["代码结构"] = {
        "函数": functions,
        "类": classes,
        "导入": imports,
        "变量": variables,
        "行数": len(code.splitlines())
    }
    
    # 3. 检查潜在逻辑问题
    # 3.1 检查未使用的导入
    defined_names = set()
    used_names = set()
    
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            if isinstance(node.ctx, ast.Load):
                used_names.add(node.id)
            elif isinstance(node.ctx, ast.Store):
                defined_names.add(node.id)
    
    # 检查未使用的导入
    imported_names = set()
    for imp in imports:
        if imp["别名"]:
            imported_names.add(imp["别名"])
        else:
            # 简化处理，只取最后一个组件
            module_parts = imp["模块"].split('.')
            imported_names.add(module_parts[-1])
    
    unused_imports = imported_names - used_names
    if unused_imports:
        for name in unused_imports:
            result["警告"].append({
                "类型": "未使用的导入",
                "信息": f"导入的模块 '{name}' 未被使用"
            })
    
    # 3.2 检查未使用的变量
    unused_vars = defined_names - used_names - {"_"}  # 忽略下划线变量
    if unused_vars:
        for name in unused_vars:
            result["警告"].append({
                "类型": "未使用的变量",
                "信息": f"变量 '{name}' 定义后未被使用"
            })
    
    # 3.3 检查可能的无限循环
    for node in ast.walk(tree):
        if isinstance(node, ast.While) and isinstance(node.test, ast.Constant):
            if node.test.value == True:
                result["警告"].append({
                    "类型": "潜在的无限循环",
                    "信息": f"第 {node.lineno} 行: while True 循环可能需要break语句",
                    "行号": node.lineno
                })
    
    # 3.4 检查空异常处理
    for node in ast.walk(tree):
        if isinstance(node, ast.Try):
            for handler in node.handlers:
                if not handler.body or all(isinstance(stmt, ast.Pass) for stmt in handler.body):
                    result["警告"].append({
                        "类型": "空异常处理",
                        "信息": f"第 {handler.lineno} 行: 异常被捕获但未处理",
                        "行号": handler.lineno
                    })
    
    # 3.5 检查可能的缺失返回值
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            returns_in_all_paths = False
            returns_in_some_paths = False
            
            # 检查函数体中是否有返回语句
            for child in ast.walk(node):
                if isinstance(child, ast.Return):
                    returns_in_some_paths = True
                    break
            
            if returns_in_some_paths:
                # 检查是否所有路径都有返回语句
                # 这只是一个简化的实现，完整的实现需要控制流分析
                has_if_without_return = False
                for child in node.body:
                    if isinstance(child, ast.If) and not any(isinstance(stmt, ast.Return) for stmt in child.body):
                        has_if_without_return = True
                        break
                
                if has_if_without_return:
                    result["警告"].append({
                        "类型": "可能缺失返回值",
                        "信息": f"函数 '{node.name}' (第 {node.lineno} 行) 可能在某些执行路径上没有返回值",
                        "行号": node.lineno
                    })
    
    # 4. 使用临时文件和pylint进行更深入的检查
    try:
        # 创建临时文件
        with tempfile.NamedTemporaryFile(suffix='.py', delete=False) as temp:
            temp_path = temp.name
            temp.write(code.encode('utf-8'))
        
        # 使用pylint检查代码
        try:
            process = subprocess.run(
                ['pylint', '--output-format=json', temp_path],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False  # 不要在pylint返回非零代码时引发异常
            )
            
            if process.stdout:
                try:
                    pylint_results = json.loads(process.stdout)
                    for issue in pylint_results:
                        if issue['type'] == 'error':
                            result["错误"].append({
                                "类型": "pylint错误",
                                "信息": issue['message'],
                                "行号": issue.get('line', 0),
                                "模块": issue.get('module', '')
                            })
                        elif issue['type'] == 'warning':
                            result["警告"].append({
                                "类型": "pylint警告",
                                "信息": issue['message'],
                                "行号": issue.get('line', 0),
                                "模块": issue.get('module', '')
                            })
                        else:
                            result["建议"].append({
                                "类型": "pylint建议",
                                "信息": issue['message'],
                                "行号": issue.get('line', 0),
                                "模块": issue.get('module', '')
                            })
                except json.JSONDecodeError:
                    # 如果不是JSON格式，尝试解析文本输出
                    pass
        except Exception as e:
            # pylint可能不可用，不影响其他检查
            result["建议"].append({
                "类型": "工具不可用",
                "信息": f"pylint检查不可用，建议安装: pip install pylint"
            })
        
        # 临时文件清理
        try:
            os.unlink(temp_path)
        except:
            pass
            
    except Exception as e:
        result["警告"].append({
            "类型": "检查过程错误",
            "信息": f"执行额外检查时出错: {str(e)}"
        })
    
    # 根据错误和警告情况，确定代码是否有效
    if result["错误"]:
        result["有效"] = False
    
    # 添加综合评分
    error_count = len(result["错误"])
    warning_count = len(result["警告"])
    suggestion_count = len(result["建议"])
    
    # 简单评分算法：100分满分，每个错误减10分，每个警告减3分
    score = max(0, 100 - error_count * 10 - warning_count * 3)
    result["评分"] = score
    
    # 添加整体结论
    if score >= 90:
        result["结论"] = "代码质量优秀"
    elif score >= 70:
        result["结论"] = "代码质量良好，有少量问题需要修复"
    elif score >= 50:
        result["结论"] = "代码质量中等，建议修复问题"
    else:
        result["结论"] = "代码质量较差，需要全面修复"
    
    return result

def verify_imports(code: str) -> Dict[str, Any]:
    """
    验证代码中的导入语句是否可用
    
    Args:
        code: 要验证的Python代码
        
    Returns:
        包含导入验证结果的字典
    """
    result = {
        "有效": True,
        "错误": [],
        "可用模块": [],
        "不可用模块": []
    }
    
    try:
        # 解析代码，提取导入语句
        tree = ast.parse(code)
        
        imports = []
        # 收集import语句
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for name in node.names:
                    imports.append({
                        "模块": name.name,
                        "行号": node.lineno
                    })
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                imports.append({
                    "模块": module,
                    "行号": node.lineno
                })
        
        # 验证每个导入模块是否可用
        for imp in imports:
            module_name = imp["模块"]
            
            # 跳过相对导入
            if module_name.startswith('.'):
                continue
                
            # 处理复杂的导入情况，只检查主模块
            main_module = module_name.split('.')[0]
            
            try:
                # 尝试导入模块
                # 使用importlib.util.find_spec避免实际加载模块
                spec = importlib.util.find_spec(main_module)
                if spec is not None:
                    result["可用模块"].append(module_name)
                else:
                    result["不可用模块"].append(module_name)
                    result["错误"].append({
                        "类型": "模块不可用",
                        "信息": f"模块 '{module_name}' 无法找到或导入",
                        "行号": imp["行号"]
                    })
            except (ImportError, ModuleNotFoundError):
                result["不可用模块"].append(module_name)
                result["错误"].append({
                    "类型": "模块不可用",
                    "信息": f"模块 '{module_name}' 无法找到或导入",
                    "行号": imp["行号"]
                })
        
        # 更新验证结果
        if result["错误"]:
            result["有效"] = False
            
    except SyntaxError as e:
        result["有效"] = False
        result["错误"].append({
            "类型": "语法错误",
            "信息": str(e),
            "行号": getattr(e, "lineno", 0)
        })
    except Exception as e:
        result["有效"] = False
        result["错误"].append({
            "类型": "验证错误",
            "信息": str(e)
        })
    
    return result

def execute_code_safely(code: str) -> Dict[str, Any]:
    """
    在安全环境中执行代码并验证运行结果
    
    Args:
        code: 要执行的Python代码
        
    Returns:
        包含执行结果的字典
    """
    result = {
        "成功": False,
        "输出": "",
        "错误": "",
        "执行时间": 0
    }
    
    # 创建临时文件
    try:
        with tempfile.NamedTemporaryFile(suffix='.py', delete=False) as temp:
            temp_path = temp.name
            temp.write(code.encode('utf-8'))
        
        # 设置超时时间（秒）
        timeout = 5
        
        # 执行代码
        import time
        start_time = time.time()
        
        try:
            process = subprocess.run(
                [sys.executable, temp_path],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=timeout
            )
            
            end_time = time.time()
            result["执行时间"] = round(end_time - start_time, 3)
            
            # 收集输出
            result["输出"] = process.stdout
            
            # 检查是否有错误
            if process.returncode != 0:
                result["错误"] = process.stderr
                result["成功"] = False
            else:
                result["成功"] = True
                
        except subprocess.TimeoutExpired:
            result["成功"] = False
            result["错误"] = f"执行超时，超过{timeout}秒"
        except Exception as e:
            result["成功"] = False
            result["错误"] = str(e)
        
        # 删除临时文件
        try:
            os.unlink(temp_path)
        except:
            pass
            
    except Exception as e:
        result["成功"] = False
        result["错误"] = f"准备执行环境时出错: {str(e)}"
    
    return result

def check_complexity(code: str) -> Dict[str, Any]:
    """
    分析代码复杂度和质量指标
    
    Args:
        code: 要分析的Python代码
        
    Returns:
        包含复杂度分析结果的字典
    """
    result = {
        "圈复杂度": {},
        "函数复杂度": [],
        "代码行数": len(code.splitlines()),
        "有效代码行": 0,
        "注释行": 0,
        "空行": 0,
        "警告": []
    }
    
    # 计算有效代码行、注释行和空行
    lines = code.splitlines()
    for line in lines:
        stripped = line.strip()
        if not stripped:
            result["空行"] += 1
        elif stripped.startswith('#'):
            result["注释行"] += 1
        else:
            result["有效代码行"] += 1
    
    try:
        # 解析代码
        tree = ast.parse(code)
        
        # 分析每个函数的复杂度
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                complexity = 1  # 基础复杂度
                
                # 遍历函数体中的所有节点
                for child in ast.walk(node):
                    # 控制流增加复杂度
                    if isinstance(child, (ast.If, ast.For, ast.While, ast.Try)):
                        complexity += 1
                    # 布尔运算符增加复杂度
                    elif isinstance(child, ast.BoolOp):
                        complexity += len(child.values) - 1
                
                # 记录函数复杂度
                func_info = {
                    "名称": node.name,
                    "行号": node.lineno,
                    "复杂度": complexity
                }
                result["函数复杂度"].append(func_info)
                
                # 警告过于复杂的函数
                if complexity > 10:
                    result["警告"].append({
                        "类型": "函数过于复杂",
                        "信息": f"函数 '{node.name}' (第 {node.lineno} 行) 复杂度为 {complexity}，建议拆分为更小的函数",
                        "行号": node.lineno
                    })
                
        # 计算整体圈复杂度
        total_complexity = sum(f["复杂度"] for f in result["函数复杂度"])
        result["圈复杂度"] = {
            "总计": total_complexity,
            "平均": round(total_complexity / len(result["函数复杂度"]), 2) if result["函数复杂度"] else 0
        }
        
        # 添加代码质量评估
        if result["圈复杂度"]["平均"] > 8:
            result["警告"].append({
                "类型": "整体复杂度过高",
                "信息": f"代码平均复杂度为 {result['圈复杂度']['平均']}，建议重构以降低复杂度"
            })
        
        # 检查函数长度
        for func in result["函数复杂度"]:
            # 估算函数长度（简单实现）
            func_length = 0
            in_func = False
            func_indent = 0
            
            for i, line in enumerate(lines):
                if i + 1 >= func["行号"]:
                    if not in_func:
                        in_func = True
                        # 获取函数定义行的缩进
                        func_indent = len(line) - len(line.lstrip())
                    
                    if in_func:
                        # 如果遇到缩进级别小于等于函数定义的行，认为函数结束
                        if line.strip() and (len(line) - len(line.lstrip())) <= func_indent:
                            if i + 1 > func["行号"]:  # 不把函数定义行本身算作结束
                                break
                        func_length += 1
            
            if func_length > 50:
                result["警告"].append({
                    "类型": "函数过长",
                    "信息": f"函数 '{func['名称']}' (第 {func['行号']} 行) 长度约为 {func_length} 行，建议拆分为更小的函数",
                    "行号": func["行号"]
                })
                
    except SyntaxError:
        # 语法错误时跳过复杂度分析
        pass
    except Exception as e:
        result["警告"].append({
            "类型": "分析错误",
            "信息": f"复杂度分析时出错: {str(e)}"
        })
    
    return result 