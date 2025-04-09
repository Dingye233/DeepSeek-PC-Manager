"""
增强代码编辑模块 - 提供精确代码编辑功能
可与代码搜索工具配合，对特定代码段进行精确修改
"""

import os
import json
import difflib
from typing import Dict, Any, List, Tuple, Optional
import ast
import re

def edit_code_section(file_path: str, start_line: int, end_line: int, new_code: str) -> Dict[str, Any]:
    """
    编辑特定文件中指定行范围的代码
    
    Args:
        file_path: 要编辑的文件路径
        start_line: 起始行号
        end_line: 结束行号
        new_code: 新代码内容
        
    Returns:
        包含编辑结果信息的字典
    """
    try:
        # 读取文件内容
        with open(file_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        # 确保行号在有效范围内
        total_lines = len(lines)
        if start_line < 1 or start_line > total_lines:
            return {
                "成功": False,
                "错误": f"起始行号无效: {start_line}，文件共有 {total_lines} 行",
                "文件": file_path
            }
        
        if end_line < start_line or end_line > total_lines:
            end_line = min(total_lines, max(start_line, end_line))
        
        # 保存原始内容用于对比
        original_section = ''.join(lines[start_line-1:end_line])
        
        # 准备新的文件内容
        new_lines = lines[:start_line-1] + [new_code] + lines[end_line:]
        
        # 创建备份文件
        backup_path = f"{file_path}.bak"
        with open(backup_path, 'w', encoding='utf-8') as f:
            f.writelines(lines)
        
        # 写入修改后的内容
        with open(file_path, 'w', encoding='utf-8') as f:
            f.writelines(new_lines)
        
        # 生成差异对比
        diff = difflib.unified_diff(
            lines[start_line-1:end_line],
            [new_code],
            fromfile=f"{file_path} (原始)",
            tofile=f"{file_path} (修改后)",
            lineterm=''
        )
        
        return {
            "成功": True,
            "文件": file_path,
            "起始行": start_line,
            "结束行": end_line,
            "备份文件": backup_path,
            "差异": '\n'.join(diff)
        }
        
    except Exception as e:
        return {
            "成功": False,
            "错误": str(e),
            "文件": file_path
        }

def edit_function(file_path: str, function_name: str, new_code: str) -> Dict[str, Any]:
    """
    编辑特定文件中的指定函数
    
    Args:
        file_path: 要编辑的文件路径
        function_name: 要编辑的函数名
        new_code: 新函数代码
        
    Returns:
        包含编辑结果信息的字典
    """
    try:
        # 检查文件是否为Python文件
        if not file_path.endswith('.py'):
            return {
                "成功": False,
                "错误": "只支持编辑Python文件的函数",
                "文件": file_path
            }
        
        # 读取文件内容
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # 解析代码
        try:
            tree = ast.parse(content)
        except SyntaxError as e:
            return {
                "成功": False,
                "错误": f"文件语法错误: {str(e)}",
                "文件": file_path
            }
        
        # 查找函数定义
        function_node = None
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == function_name:
                function_node = node
                break
        
        if function_node is None:
            return {
                "成功": False,
                "错误": f"找不到函数 '{function_name}'",
                "文件": file_path
            }
        
        # 获取函数的行范围
        start_line = function_node.lineno
        end_line = 0
        
        # 找到函数结束行
        for node in ast.walk(function_node):
            if hasattr(node, 'lineno'):
                end_line = max(end_line, node.lineno)
        
        # 如果没有找到结束行，使用简单的启发式方法
        if end_line <= start_line:
            lines = content.splitlines()
            indent = 0
            
            # 获取函数定义行的缩进
            for char in lines[start_line-1]:
                if char == ' ':
                    indent += 1
                else:
                    break
            
            # 向下扫描，找到缩进级别小于或等于函数定义的行
            end_line = start_line
            for i in range(start_line, len(lines)):
                # 跳过空行
                if not lines[i].strip():
                    end_line = i + 1
                    continue
                    
                # 计算当前行的缩进
                current_indent = 0
                for char in lines[i]:
                    if char == ' ':
                        current_indent += 1
                    else:
                        break
                
                # 如果缩进小于等于函数定义行，表示函数结束
                if current_indent <= indent and i > start_line:
                    end_line = i
                    break
                    
                end_line = i + 1
        
        # 使用edit_code_section进行实际编辑
        return edit_code_section(file_path, start_line, end_line, new_code)
        
    except Exception as e:
        return {
            "成功": False,
            "错误": str(e),
            "文件": file_path
        }

def edit_code_by_pattern(file_path: str, pattern: str, replacement: str) -> Dict[str, Any]:
    """
    使用正则表达式模式编辑代码
    
    Args:
        file_path: 要编辑的文件路径
        pattern: 正则表达式模式
        replacement: 替换内容
        
    Returns:
        包含编辑结果信息的字典
    """
    try:
        # 读取文件内容
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # 编译正则表达式
        try:
            regex = re.compile(pattern, re.MULTILINE | re.DOTALL)
        except re.error as e:
            return {
                "成功": False,
                "错误": f"正则表达式错误: {str(e)}",
                "文件": file_path
            }
        
        # 保存原始内容用于对比
        original_content = content
        
        # 统计匹配数量
        matches = regex.findall(content)
        match_count = len(matches)
        
        if match_count == 0:
            return {
                "成功": False,
                "错误": f"未找到匹配的代码模式",
                "文件": file_path
            }
        
        # 进行替换
        new_content = regex.sub(replacement, content)
        
        # 如果内容没有变化
        if new_content == content:
            return {
                "成功": False,
                "错误": "替换后内容与原内容相同",
                "文件": file_path
            }
        
        # 创建备份文件
        backup_path = f"{file_path}.bak"
        with open(backup_path, 'w', encoding='utf-8') as f:
            f.write(original_content)
        
        # 写入修改后的内容
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(new_content)
        
        # 生成差异对比
        diff = difflib.unified_diff(
            original_content.splitlines(True),
            new_content.splitlines(True),
            fromfile=f"{file_path} (原始)",
            tofile=f"{file_path} (修改后)",
            lineterm=''
        )
        
        return {
            "成功": True,
            "文件": file_path,
            "匹配数量": match_count,
            "备份文件": backup_path,
            "差异": '\n'.join(diff)
        }
        
    except Exception as e:
        return {
            "成功": False,
            "错误": str(e),
            "文件": file_path
        }

def insert_code(file_path: str, line_number: int, code: str) -> Dict[str, Any]:
    """
    在特定行插入代码
    
    Args:
        file_path: 要编辑的文件路径
        line_number: 插入位置的行号
        code: 要插入的代码
        
    Returns:
        包含编辑结果信息的字典
    """
    try:
        # 读取文件内容
        with open(file_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        # 确保行号在有效范围内
        total_lines = len(lines)
        if line_number < 1 or line_number > total_lines + 1:
            return {
                "成功": False,
                "错误": f"行号无效: {line_number}，文件共有 {total_lines} 行",
                "文件": file_path
            }
        
        # 创建备份文件
        backup_path = f"{file_path}.bak"
        with open(backup_path, 'w', encoding='utf-8') as f:
            f.writelines(lines)
        
        # 准备新的文件内容
        new_lines = lines[:line_number-1] + [code] + lines[line_number-1:]
        
        # 写入修改后的内容
        with open(file_path, 'w', encoding='utf-8') as f:
            f.writelines(new_lines)
        
        return {
            "成功": True,
            "文件": file_path,
            "插入行": line_number,
            "备份文件": backup_path
        }
        
    except Exception as e:
        return {
            "成功": False,
            "错误": str(e),
            "文件": file_path
        } 