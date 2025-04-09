import ast
import re
from typing import Dict, List, Any, Optional, Tuple
import os
from difflib import SequenceMatcher
import json

class CodeSearchEngine:
    def __init__(self):
        self.cache = {}  # 用于缓存已分析的文件
        self.max_cache_size = 100  # 最大缓存文件数

    def search_code(self, file_path: str, query: str, search_type: str = "semantic") -> Dict[str, Any]:
        """
        增强的代码搜索功能，支持多种搜索模式
        
        Args:
            file_path: 要搜索的文件路径
            query: 搜索查询
            search_type: 搜索类型，可选值：
                - "semantic": 语义搜索（默认）
                - "exact": 精确匹配
                - "regex": 正则表达式
                - "function": 函数定义
                - "class": 类定义
                - "import": 导入语句
        
        Returns:
            包含搜索结果的结构化字典
        """
        try:
            # 读取文件内容
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # 根据文件类型选择解析方式
            _, ext = os.path.splitext(file_path)
            if ext.lower() == '.py':
                return self._search_python_code(content, query, search_type)
            else:
                return self._search_generic_code(content, query, search_type)
                
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "file": file_path
            }

    def _search_python_code(self, content: str, query: str, search_type: str) -> Dict[str, Any]:
        """搜索Python代码"""
        try:
            tree = ast.parse(content)
            results = []
            
            if search_type == "semantic":
                # 语义搜索：分析代码结构和上下文
                results.extend(self._semantic_search(tree, query))
            elif search_type == "function":
                # 搜索函数定义
                results.extend(self._search_functions(tree, query))
            elif search_type == "class":
                # 搜索类定义
                results.extend(self._search_classes(tree, query))
            elif search_type == "import":
                # 搜索导入语句
                results.extend(self._search_imports(tree, query))
            else:
                # 其他搜索类型使用通用搜索
                results.extend(self._search_generic_code(content, query, search_type)["matches"])
            
            return {
                "success": True,
                "matches": results,
                "total_matches": len(results)
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }

    def _semantic_search(self, tree: ast.AST, query: str) -> List[Dict[str, Any]]:
        """语义搜索实现"""
        results = []
        query = query.lower()
        
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
                # 检查函数/类名
                if query in node.name.lower():
                    results.append(self._get_node_info(node))
                
                # 检查文档字符串
                docstring = ast.get_docstring(node)
                if docstring and query in docstring.lower():
                    results.append(self._get_node_info(node))
                
                # 检查函数体中的注释
                for child in ast.walk(node):
                    if isinstance(child, ast.Expr) and isinstance(child.value, ast.Str):
                        if query in child.value.s.lower():
                            results.append(self._get_node_info(node))
            
            # 检查变量名和字符串
            elif isinstance(node, ast.Name) and query in node.id.lower():
                results.append(self._get_node_info(node))
            elif isinstance(node, ast.Str) and query in node.s.lower():
                results.append(self._get_node_info(node))
        
        return results

    def _search_functions(self, tree: ast.AST, query: str) -> List[Dict[str, Any]]:
        """搜索函数定义"""
        results = []
        query = query.lower()
        
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                if query in node.name.lower():
                    results.append(self._get_node_info(node))
        
        return results

    def _search_classes(self, tree: ast.AST, query: str) -> List[Dict[str, Any]]:
        """搜索类定义"""
        results = []
        query = query.lower()
        
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                if query in node.name.lower():
                    results.append(self._get_node_info(node))
        
        return results

    def _search_imports(self, tree: ast.AST, query: str) -> List[Dict[str, Any]]:
        """搜索导入语句"""
        results = []
        query = query.lower()
        
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for name in node.names:
                    if query in name.name.lower():
                        results.append(self._get_node_info(node))
            elif isinstance(node, ast.ImportFrom):
                if node.module and query in node.module.lower():
                    results.append(self._get_node_info(node))
                for name in node.names:
                    if query in name.name.lower():
                        results.append(self._get_node_info(node))
        
        return results

    def _get_node_info(self, node: ast.AST) -> Dict[str, Any]:
        """获取AST节点的详细信息"""
        info = {
            "type": type(node).__name__,
            "line": getattr(node, 'lineno', 0),
            "col": getattr(node, 'col_offset', 0)
        }
        
        if isinstance(node, ast.FunctionDef):
            info.update({
                "name": node.name,
                "args": [arg.arg for arg in node.args.args],
                "docstring": ast.get_docstring(node)
            })
        elif isinstance(node, ast.ClassDef):
            info.update({
                "name": node.name,
                "bases": [base.id if isinstance(base, ast.Name) else str(base) for base in node.bases],
                "docstring": ast.get_docstring(node)
            })
        elif isinstance(node, ast.Import):
            info["names"] = [{"name": n.name, "asname": n.asname} for n in node.names]
        elif isinstance(node, ast.ImportFrom):
            info.update({
                "module": node.module,
                "names": [{"name": n.name, "asname": n.asname} for n in node.names]
            })
        
        return info

    def _search_generic_code(self, content: str, query: str, search_type: str) -> Dict[str, Any]:
        """通用代码搜索实现"""
        results = []
        lines = content.splitlines()
        
        if search_type == "exact":
            # 精确匹配
            for i, line in enumerate(lines):
                if query in line:
                    results.append({
                        "line": i + 1,
                        "content": line,
                        "match_type": "exact"
                    })
        elif search_type == "regex":
            # 正则表达式匹配
            try:
                pattern = re.compile(query)
                for i, line in enumerate(lines):
                    if pattern.search(line):
                        results.append({
                            "line": i + 1,
                            "content": line,
                            "match_type": "regex"
                        })
            except re.error:
                return {
                    "success": False,
                    "error": "Invalid regular expression"
                }
        else:
            # 模糊匹配
            for i, line in enumerate(lines):
                similarity = SequenceMatcher(None, query.lower(), line.lower()).ratio()
                if similarity > 0.7:  # 相似度阈值
                    results.append({
                        "line": i + 1,
                        "content": line,
                        "similarity": similarity,
                        "match_type": "fuzzy"
                    })
        
        return {
            "success": True,
            "matches": results,
            "total_matches": len(results)
        }

    def locate_code_section(self, file_path: str, start_line: int, end_line: int) -> Dict[str, Any]:
        """
        定位代码片段
        
        Args:
            file_path: 文件路径
            start_line: 起始行号
            end_line: 结束行号
            
        Returns:
            包含代码片段和上下文信息的字典
        """
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            
            # 确保行号在有效范围内
            start_line = max(1, min(start_line, len(lines)))
            end_line = max(start_line, min(end_line, len(lines)))
            
            # 获取上下文（前后各3行）
            context_start = max(1, start_line - 3)
            context_end = min(len(lines), end_line + 3)
            
            # 提取代码片段和上下文
            code_section = lines[start_line-1:end_line]
            context_before = lines[context_start-1:start_line-1]
            context_after = lines[end_line:context_end]
            
            return {
                "success": True,
                "file": file_path,
                "start_line": start_line,
                "end_line": end_line,
                "code_section": "".join(code_section),
                "context_before": "".join(context_before),
                "context_after": "".join(context_after)
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "file": file_path
            }

    def get_code_context(self, file_path: str, line_number: int, context_lines: int = 5) -> Dict[str, Any]:
        """
        获取代码行的上下文
        
        Args:
            file_path: 文件路径
            line_number: 行号
            context_lines: 上下文的行数
            
        Returns:
            包含代码行及其上下文的字典
        """
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            
            # 确保行号在有效范围内
            line_number = max(1, min(line_number, len(lines)))
            
            # 计算上下文范围
            start_line = max(1, line_number - context_lines)
            end_line = min(len(lines), line_number + context_lines)
            
            # 提取上下文
            context = lines[start_line-1:end_line]
            
            return {
                "success": True,
                "file": file_path,
                "line_number": line_number,
                "context": "".join(context),
                "target_line": lines[line_number-1].strip()
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "file": file_path
            } 