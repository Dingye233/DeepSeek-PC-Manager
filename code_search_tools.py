"""
代码搜索工具实现模块 - 连接工具注册与CodeSearchEngine
提供实际的代码搜索、代码定位和代码上下文获取功能
"""

import json
from code_search_enhanced import CodeSearchEngine

# 创建CodeSearchEngine实例
search_engine = CodeSearchEngine()

def search_code(file_path: str, query: str, search_type: str = "semantic"):
    """
    实现代码搜索工具的函数
    
    参数:
        file_path: 要搜索的文件路径
        query: 搜索查询内容
        search_type: 搜索类型，默认为semantic
    
    返回:
        搜索结果的JSON字符串
    """
    try:
        result = search_engine.search_code(file_path, query, search_type)
        
        # 格式化结果用于更好的显示
        formatted_result = {
            "成功": result.get("success", False),
            "搜索文件": file_path,
            "搜索内容": query,
            "搜索类型": search_type,
            "匹配数量": result.get("total_matches", 0),
        }
        
        # 添加匹配结果
        if result.get("success", False) and "matches" in result:
            matches = []
            for match in result["matches"]:
                match_info = {
                    "行号": match.get("line", "未知"),
                }
                
                # 添加不同类型的匹配信息
                if "type" in match:  # AST节点信息
                    match_info["类型"] = match["type"]
                    if "name" in match:
                        match_info["名称"] = match["name"]
                if "content" in match:  # 行内容
                    match_info["内容"] = match["content"]
                
                matches.append(match_info)
            
            formatted_result["匹配结果"] = matches[:10]  # 限制输出结果数量
            if len(result["matches"]) > 10:
                formatted_result["说明"] = f"共找到{len(result['matches'])}个匹配，只显示前10个"
        
        return json.dumps(formatted_result, ensure_ascii=False, indent=2)
        
    except Exception as e:
        error_result = {
            "成功": False,
            "错误": str(e),
            "文件": file_path
        }
        return json.dumps(error_result, ensure_ascii=False, indent=2)

def locate_code_section(file_path: str, start_line: int, end_line: int):
    """
    实现代码定位工具的函数
    
    参数:
        file_path: 文件路径
        start_line: 起始行号
        end_line: 结束行号
    
    返回:
        代码片段及上下文的JSON字符串
    """
    try:
        result = search_engine.locate_code_section(file_path, start_line, end_line)
        
        # 格式化结果
        formatted_result = {
            "成功": result.get("success", False),
            "文件": file_path,
            "起始行": result.get("start_line", start_line),
            "结束行": result.get("end_line", end_line),
        }
        
        if result.get("success", False):
            # 添加代码片段和上下文信息
            if "context_before" in result and result["context_before"]:
                formatted_result["前置上下文"] = result["context_before"]
            
            if "code_section" in result:
                formatted_result["代码片段"] = result["code_section"]
            
            if "context_after" in result and result["context_after"]:
                formatted_result["后续上下文"] = result["context_after"]
        
        return json.dumps(formatted_result, ensure_ascii=False, indent=2)
        
    except Exception as e:
        error_result = {
            "成功": False,
            "错误": str(e),
            "文件": file_path
        }
        return json.dumps(error_result, ensure_ascii=False, indent=2)

def get_code_context(file_path: str, line_number: int, context_lines: int = 5):
    """
    实现代码上下文获取工具的函数
    
    参数:
        file_path: 文件路径
        line_number: 目标行号
        context_lines: 上下文的行数
    
    返回:
        代码行及上下文的JSON字符串
    """
    try:
        result = search_engine.get_code_context(file_path, line_number, context_lines)
        
        # 格式化结果
        formatted_result = {
            "成功": result.get("success", False),
            "文件": file_path,
            "行号": result.get("line_number", line_number),
        }
        
        if result.get("success", False):
            # 添加目标行和上下文
            if "target_line" in result:
                formatted_result["目标行"] = result["target_line"]
            
            if "context" in result:
                formatted_result["上下文"] = result["context"]
        
        return json.dumps(formatted_result, ensure_ascii=False, indent=2)
        
    except Exception as e:
        error_result = {
            "成功": False,
            "错误": str(e),
            "文件": file_path
        }
        return json.dumps(error_result, ensure_ascii=False, indent=2) 