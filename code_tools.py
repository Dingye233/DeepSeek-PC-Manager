import json
from typing import Dict, Any, Optional, List, Union
import os
import re
from datetime import datetime
# 导入所有增强版工具
from code_edit_enhanced import edit_code_section, edit_function, edit_code_by_pattern, insert_code
from code_validator_enhanced import validate_python_code, verify_imports, execute_code_safely, check_complexity
from code_search_enhanced import CodeSearchEngine

# 创建搜索引擎实例
search_engine = CodeSearchEngine()

def write_code(file_name: str, code: str, with_analysis: bool = False, create_backup: bool = True) -> str:
    """
    将代码写入文件并返回结果【增强版】
    
    该函数会自动创建目录路径（如果需要），并提供详细的操作结果，包括代码质量验证
    
    :param file_name: 要创建的文件名（带扩展名），可以是相对路径或绝对路径
    :param code: 文件内容
    :param with_analysis: 是否在结果中包含代码分析
    :param create_backup: 是否创建备份文件
    :return: 包含操作结果的JSON字符串
    
    示例:
      成功: {"success": true, "message": "文件创建成功: /path/to/file.py", "path": "/path/to/file.py"}
      失败: {"success": false, "message": "文件创建失败: [错误原因]", "error": "[错误详情]"}
    """
    try:
        # 备份已存在的文件
        if create_backup and os.path.exists(file_name):
            try:
                backup_file = f"{file_name}.bak"
                with open(file_name, 'r', encoding='utf-8') as src:
                    with open(backup_file, 'w', encoding='utf-8') as dst:
                        dst.write(src.read())
            except Exception as e:
                print(f"创建备份失败，继续执行: {str(e)}")
        
        # 获取文件所在的目录路径
        dir_name = os.path.dirname(file_name)

        # 如果目录路径不为空且目录不存在，则创建目录
        if dir_name and not os.path.exists(dir_name):
            os.makedirs(dir_name, exist_ok=True)
            
        # 写入内容到文件
        with open(file_name, mode='w', encoding='utf-8') as f:
            f.write(code)
            
        # 构建结果
        result = {
            "success": True,
            "message": f"文件创建成功: {os.path.abspath(file_name)}",
            "path": os.path.abspath(file_name),
            "file_size": os.path.getsize(file_name),
            "extension": os.path.splitext(file_name)[1],
            "created_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        
        # 增强功能：添加代码验证
        if file_name.endswith('.py'):
            validation = validate_python_code(code)
            if with_analysis:
                result["enhanced_validation"] = validation
            else:
                result["enhanced_validation"] = {
                    "有效": validation.get("有效", True),
                    "评分": validation.get("评分", 0),
                    "结论": validation.get("结论", "")
                }
            
            # 如果发现严重错误，添加警告信息
            if not validation.get("有效", True):
                result["warning"] = "代码可能存在问题，请检查验证结果"
        
        response = json.dumps(result, ensure_ascii=False, indent=2)
        
        # 为LLM提供明确的成功或失败信息
        success = result.get("success", False)
        if success:
            return f"文件创建成功: {result.get('path', file_name)}\n{response}"
        else:
            return f"文件创建失败: {result.get('error', '未知错误')}\n{response}"
    except Exception as e:
        error_result = {
            "success": False,
            "message": f"执行write_code时出错",
            "error": str(e)
        }
        return json.dumps(error_result, ensure_ascii=False, indent=2)

def verify_code(code: str, verbose: bool = False, check_best_practices: bool = False) -> str:
    """
    验证Python代码语法是否正确【增强版】
    
    该函数使用高级分析工具检查代码的语法、逻辑问题和代码质量
    
    :param code: 要验证的Python代码
    :param verbose: 是否返回详细的验证结果
    :param check_best_practices: 是否检查最佳实践
    :return: 包含验证结果的JSON字符串，包括代码结构分析和潜在问题
    
    示例:
      通过: {"valid": true, "message": "代码语法正确", "structure": {...}}
      失败: {"valid": false, "message": "语法错误: 第10行, 列5, invalid syntax", "line": 10, ...}
    """
    try:
        # 使用增强版的代码验证
        validation_options = {
            "详细检查": verbose,
            "检查最佳实践": check_best_practices
        }
        enhanced_result = validate_python_code(code, **validation_options)
        
        # 转换为原接口格式
        result = {
            "valid": enhanced_result.get("有效", False),
            "message": enhanced_result.get("结论", "")
        }
        
        # 如果需要详细结果
        if verbose:
            result["enhanced_validation"] = enhanced_result
        
        # 添加错误信息
        if "错误" in enhanced_result and enhanced_result["错误"]:
            first_error = enhanced_result["错误"][0]
            result["message"] = first_error.get("信息", "未知错误")
            result["line"] = first_error.get("行号", 0)
            result["column"] = first_error.get("列号", 0)
        
        # 添加代码结构信息
        if "代码结构" in enhanced_result:
            result["structure"] = enhanced_result["代码结构"]
        
        response = json.dumps(result, ensure_ascii=False, indent=2)
        
        # 为LLM提供简洁的验证结果摘要
        if result.get("valid", False):
            return f"代码语法验证通过 ✓\n{response}"
        else:
            return f"代码语法错误 ✗: {result.get('message', '未知错误')}\n{response}"
    except Exception as e:
        error_result = {
            "valid": False,
            "message": f"执行verify_code时出错: {str(e)}",
            "error": str(e)
        }
        return json.dumps(error_result, ensure_ascii=False, indent=2)

def append_code(file_name: str, content: str, verify_after: bool = False, create_backup: bool = True) -> str:
    """
    向文件追加代码内容【增强版】
    
    如果文件不存在，则创建新文件；如果已存在，则在文件末尾追加内容，并可选验证完整性
    
    :param file_name: 文件名，可以是相对路径或绝对路径
    :param content: 要追加的内容
    :param verify_after: 是否在追加后验证完整代码
    :param create_backup: 是否创建备份文件
    :return: 包含操作结果的JSON字符串
    
    示例:
      成功: {"success": true, "message": "内容已成功追加到文件: /path/to/file.py", ...}
      失败: {"success": false, "message": "向文件追加内容失败: [错误原因]", ...}
    """
    try:
        # 备份已存在的文件
        if create_backup and os.path.exists(file_name):
            try:
                backup_file = f"{file_name}.bak"
                with open(file_name, 'r', encoding='utf-8') as src:
                    with open(backup_file, 'w', encoding='utf-8') as dst:
                        dst.write(src.read())
            except Exception as e:
                print(f"创建备份失败，继续执行: {str(e)}")
        
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
        
        # 构建结果
        result = {
            "success": True,
            "message": f"内容已成功{action}文件: {os.path.abspath(file_name)}",
            "path": os.path.abspath(file_name),
            "original_size": original_size,
            "new_size": new_size,
            "added_bytes": new_size - original_size,
            "added_lines": content.count('\n') + (0 if content.endswith('\n') else 1)
        }
        
        # 增强功能：如果是Python文件，验证内容
        if verify_after and result.get("success", False) and file_name.endswith('.py'):
            # 读取完整文件内容进行验证
            try:
                with open(result.get("path", file_name), 'r', encoding='utf-8') as f:
                    complete_code = f.read()
                
                validation = validate_python_code(complete_code)
                result["enhanced_validation"] = {
                    "有效": validation.get("有效", True),
                    "评分": validation.get("评分", 0),
                    "结论": validation.get("结论", "")
                }
                
                # 如果发现严重错误，添加警告信息
                if not validation.get("有效", True):
                    result["warning"] = "添加内容后代码可能存在问题，请检查验证结果"
            except Exception as e:
                result["warning"] = f"无法验证完整代码: {str(e)}"
        
        response = json.dumps(result, ensure_ascii=False, indent=2)
        
        # 为LLM提供明确的成功或失败信息
        success = result.get("success", False)
        if success:
            action = "创建" if "创建" in result.get("message", "") else "更新"
            return f"文件{action}成功: {result.get('path', file_name)}\n{response}"
        else:
            return f"文件操作失败: {result.get('error', '未知错误')}\n{response}"
    except Exception as e:
        error_result = {
            "success": False,
            "message": f"执行append_code时出错",
            "error": str(e)
        }
        return json.dumps(error_result, ensure_ascii=False, indent=2)

def analyze_code_content(code: str, file_name: str = "") -> Dict[str, Any]:
    """
    分析代码结构和组成，替代code_generator.analyze_code
    
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
        # 使用内置的validate_python_code获取更详细的分析
        validation = validate_python_code(code)
        
        if validation.get("有效", False):
            # 从验证结果中提取信息
            result["metrics"] = {
                "functions": len(validation.get("代码结构", {}).get("函数", [])),
                "classes": len(validation.get("代码结构", {}).get("类", [])),
                "imports": validation.get("代码结构", {}).get("导入", []),
                "comment_ratio": 0,  # 将在下面计算
                "complexity": 0  # 将在下面计算
            }
            
            # 获取注释率和代码复杂度
            complexity_info = check_complexity(code)
            if complexity_info:
                total_lines = complexity_info.get("代码行数", 0)
                comment_lines = complexity_info.get("注释行", 0)
                
                if total_lines > 0:
                    result["metrics"]["comment_ratio"] = round(comment_lines / total_lines * 100, 2)
                
                result["metrics"]["complexity"] = complexity_info.get("圈复杂度", {}).get("总计", 0)
            
            # 查找潜在问题
            result["issues"] = []
            
            # 添加警告
            if "警告" in validation:
                for warning in validation.get("警告", []):
                    result["issues"].append({
                        "type": "warning",
                        "message": warning.get("信息", "未知警告"),
                        "line": warning.get("行号", 0)
                    })
            
            # 添加错误
            if "错误" in validation:
                for error in validation.get("错误", []):
                    result["issues"].append({
                        "type": "error",
                        "message": error.get("信息", "未知错误"),
                        "line": error.get("行号", 0)
                    })
        else:
            # 代码无效，记录错误
            result["error"] = validation.get("结论", "代码分析失败")
    
    return result

def read_code(file_name: str, with_analysis: bool = True, complexity_check: bool = False) -> str:
    """
    读取代码文件内容并可选提供深度分析【增强版】
    
    该函数会尝试使用多种编码（utf-8, gbk等）读取文件，并提供代码复杂度分析
    
    :param file_name: 文件名，可以是相对路径或绝对路径
    :param with_analysis: 是否包含基本代码分析（默认为True）
    :param complexity_check: 是否进行复杂度分析（默认为False）
    :return: 包含文件内容和分析结果的JSON字符串
    
    示例:
      成功: {"success": true, "content": "def hello():\\n    print('Hello')", "path": "...", "analysis": {...}}
      失败: {"success": false, "message": "文件不存在: /path/to/file.py", ...}
    """
    try:
        # 首先尝试读取文件
        try:
            # 尝试不同编码读取文件
            try:
                with open(file_name, 'r', encoding='utf-8') as f:
                    content = f.read()
                    encoding = 'utf-8'
            except UnicodeDecodeError:
                try:
                    with open(file_name, 'r', encoding='gbk') as f:
                        content = f.read()
                        encoding = 'gbk'
                except UnicodeDecodeError:
                    with open(file_name, 'r', encoding='latin-1') as f:
                        content = f.read()
                        encoding = 'latin-1'
            
            # 基本信息
            result = {
                "success": True,
                "message": f"文件读取成功: {os.path.abspath(file_name)}",
                "content": content,
                "path": os.path.abspath(file_name),
                "size": os.path.getsize(file_name),
                "encoding": encoding
            }
            
            # 分析代码
            if with_analysis:
                _, ext = os.path.splitext(file_name)
                if ext.lower() == '.py':
                    # Python文件分析
                    analysis = analyze_code_content(content, file_name)
                    result["analysis"] = analysis
                    
                    # 添加语法验证
                    validation = validate_python_code(content)
                    result["validation"] = {
                        "valid": validation.get("有效", False),
                        "message": validation.get("结论", "")
                    }
                else:
                    # 非Python文件的基本分析
                    result["analysis"] = {
                        "language": ext[1:] if ext else "unknown",
                        "line_count": len(content.splitlines()),
                        "char_count": len(content)
                    }
            
            # 增强功能：添加复杂度分析
            if complexity_check and file_name.endswith('.py'):
                complexity_analysis = check_complexity(content)
                result["enhanced_analysis"] = {
                    "复杂度": complexity_analysis.get("圈复杂度", {}),
                    "代码统计": {
                        "总行数": complexity_analysis.get("代码行数", 0),
                        "有效代码行": complexity_analysis.get("有效代码行", 0),
                        "注释行": complexity_analysis.get("注释行", 0),
                        "空行": complexity_analysis.get("空行", 0)
                    }
                }
                
                # 如果有警告，添加到结果中
                if "警告" in complexity_analysis and complexity_analysis["警告"]:
                    result["enhanced_analysis"]["警告"] = [
                        warning.get("信息", "") for warning in complexity_analysis["警告"]
                    ]
                
        except FileNotFoundError:
            return json.dumps({
                "success": False,
                "message": f"文件不存在: {file_name}",
                "error": "FileNotFoundError"
            }, ensure_ascii=False, indent=2)
        
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
    except Exception as e:
        error_result = {
            "success": False,
            "message": f"执行read_code时出错",
            "error": str(e)
        }
        return json.dumps(error_result, ensure_ascii=False, indent=2)

def create_module(module_name: str, functions_json: str, verify_imports: bool = False, create_tests: bool = False) -> str:
    """
    创建包含多个函数的Python模块【增强版】
    
    自动生成适当的导入语句、文档字符串和模块结构，并可选验证模块导入和创建测试代码
    
    :param module_name: 模块名称（不含.py扩展名）
    :param functions_json: 函数定义的JSON字符串，格式为[{"name": "函数名", "params": "参数列表", "body": "函数体", "docstring": "文档字符串"}]
    :param verify_imports: 是否验证导入语句
    :param create_tests: 是否创建测试代码
    :return: 包含操作结果的JSON字符串
    
    示例:
      成功: {"success": true, "message": "模块创建成功: /path/to/module.py", "module": {...}}
      失败: {"success": false, "message": "模块创建失败: [错误原因]", ...}
    """
    try:
        file_name = f"{module_name}.py"
        
        # 解析函数定义
        try:
            functions = json.loads(functions_json)
        except json.JSONDecodeError as e:
            return json.dumps({
                "success": False,
                "message": f"函数定义JSON解析失败: {str(e)}",
                "error": str(e)
            }, ensure_ascii=False, indent=2)
        
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
        with open(file_name, 'w', encoding='utf-8') as f:
            f.write(code)
        
        # 构建结果
        result = {
            "success": True,
            "message": f"模块创建成功: {os.path.abspath(file_name)}",
            "path": os.path.abspath(file_name),
            "module_name": module_name,
            "functions": [f.get("name") for f in functions],
            "code_size": len(code)
        }
        
        # 进行代码验证
        validation = validate_python_code(code)
        result["validation"] = {
            "valid": validation.get("有效", True),
            "score": validation.get("评分", 0),
            "conclusion": validation.get("结论", "")
        }
        
        # 增强功能：验证导入
        if verify_imports and result.get("success", False):
            try:
                # 验证导入
                import_result = verify_imports(code)
                result["imports_verification"] = import_result
                
                # 如果有问题，添加警告
                if "错误" in import_result and import_result["错误"]:
                    result["warning"] = "模块导入可能存在问题，请查看imports_verification部分"
            except Exception as e:
                result["warning"] = f"导入验证失败: {str(e)}"
        
        # 增强功能：创建测试代码
        if create_tests and result.get("success", False):
            try:
                # 创建测试文件
                test_file = f"test_{module_name}.py"
                
                # 生成测试代码
                test_code = f"""import unittest\nimport {module_name}\n\nclass Test{module_name.capitalize()}(unittest.TestCase):\n"""
                
                for func in functions:
                    func_name = func.get("name", "")
                    if not func_name:
                        continue
                    
                    test_code += f"""    def test_{func_name}(self):\n        \"\"\"测试 {func_name} 函数\"\"\"\n        # TODO: 添加测试用例\n        pass\n\n"""
                
                test_code += """if __name__ == '__main__':\n    unittest.main()"""
                
                # 写入测试文件
                with open(test_file, 'w', encoding='utf-8') as f:
                    f.write(test_code)
                
                result["test_file"] = {
                    "path": test_file,
                    "content": test_code
                }
            except Exception as e:
                result["test_file_error"] = f"创建测试文件失败: {str(e)}"
        
        response = json.dumps(result, ensure_ascii=False, indent=2)
        
        # 为LLM提供明确的成功或失败信息
        success = result.get("success", False)
        if success:
            return f"模块创建成功: {result.get('path', module_name+'.py')}\n{response}"
        else:
            return f"模块创建失败: {result.get('error', '未知错误')}\n{response}"
    except Exception as e:
        error_result = {
            "success": False,
            "message": f"执行create_module时出错",
            "error": str(e)
        }
        return json.dumps(error_result, ensure_ascii=False, indent=2)

def analyze_code(file_path: str) -> str:
    """
    分析代码文件的结构和质量
    
    :param file_path: 代码文件路径
    :return: 包含分析结果的JSON字符串
    
    示例:
      成功: {"success": true, "analysis": {...}, "path": "/path/to/file.py", ...}
      失败: {"success": false, "message": "代码分析失败: [错误原因]", ...}
    """
    try:
        # 读取文件内容
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                code = f.read()
        except UnicodeDecodeError:
            try:
                with open(file_path, 'r', encoding='gbk') as f:
                    code = f.read()
            except UnicodeDecodeError:
                with open(file_path, 'r', encoding='latin-1') as f:
                    code = f.read()
        
        # 初始化结果
        result = {
            "success": True,
            "path": file_path,
            "analysis": {}
        }
        
        # 根据文件类型进行不同的分析
        if file_path.endswith('.py'):
            # Python代码分析
            validation = validate_python_code(code)
            complexity = check_complexity(code)
            
            result["analysis"] = {
                "语法有效": validation.get("有效", False),
                "代码质量评分": validation.get("评分", 0),
                "复杂度": complexity.get("圈复杂度", {}),
                "代码统计": {
                    "总行数": complexity.get("代码行数", 0),
                    "有效代码行": complexity.get("有效代码行", 0),
                    "注释行": complexity.get("注释行", 0),
                    "空行": complexity.get("空行", 0)
                }
            }
            
            # 添加错误和警告
            if "错误" in validation and validation["错误"]:
                result["analysis"]["错误"] = validation["错误"]
            
            if "警告" in complexity and complexity["警告"]:
                result["analysis"]["警告"] = complexity["警告"]
                
            # 添加代码结构信息
            if "代码结构" in validation:
                result["analysis"]["结构"] = validation["代码结构"]
        else:
            # 非Python文件的基本分析
            line_count = len(code.splitlines())
            result["analysis"] = {
                "文件类型": os.path.splitext(file_path)[1],
                "总行数": line_count,
                "文件大小": os.path.getsize(file_path)
            }
        
        response = json.dumps(result, ensure_ascii=False, indent=2)
        return f"代码分析完成: {file_path}\n{response}"
    except Exception as e:
        error_result = {
            "success": False,
            "message": f"执行analyze_code时出错",
            "error": str(e)
        }
        return json.dumps(error_result, ensure_ascii=False, indent=2)

def search_code_in_file(file_path: str, query: str, search_type: str = "semantic") -> str:
    """
    在指定文件中搜索代码【增强版】
    
    支持多种搜索模式，包括语义搜索、精确匹配、正则表达式等
    
    :param file_path: 要搜索的文件路径
    :param query: 搜索查询内容
    :param search_type: 搜索类型，可选："semantic"(语义)、"exact"(精确)、"regex"(正则)、"function"(函数)、"class"(类)、"import"(导入)
    :return: 包含搜索结果的JSON字符串
    
    示例:
      成功: {"success": true, "matches": [...], "total_matches": 5, ...}
      失败: {"success": false, "message": "搜索失败: [错误原因]", ...}
    """
    try:
        # 使用搜索引擎实例进行搜索
        result = search_engine.search_code(file_path, query, search_type)
        
        # 格式化结果
        formatted_result = {
            "success": result.get("success", False),
            "file": file_path,
            "query": query,
            "search_type": search_type,
            "total_matches": result.get("total_matches", 0)
        }
        
        # 添加匹配结果，限制返回数量避免过大
        if "matches" in result:
            max_matches = 20  # 最多返回的匹配数
            matches = result["matches"][:max_matches]
            formatted_result["matches"] = matches
            
            if len(result["matches"]) > max_matches:
                formatted_result["truncated"] = True
                formatted_result["total_actual_matches"] = len(result["matches"])
        
        response = json.dumps(formatted_result, ensure_ascii=False, indent=2)
        
        # 提供简洁的摘要
        total = result.get("total_matches", 0)
        if total > 0:
            return f"找到 {total} 个匹配项\n{response}"
        else:
            return f"未找到匹配项\n{response}"
    except Exception as e:
        error_result = {
            "success": False,
            "message": f"执行search_code时出错",
            "error": str(e)
        }
        return json.dumps(error_result, ensure_ascii=False, indent=2)

def locate_code_section(file_path: str, start_line: int, end_line: int) -> str:
    """
    定位并提取代码文件中的特定行范围
    
    :param file_path: 文件路径
    :param start_line: 起始行号
    :param end_line: 结束行号
    :return: 包含代码片段和上下文的JSON字符串
    
    示例:
      成功: {"success": true, "code_section": "def hello():\\n    ...", "context_before": "...", ...}
      失败: {"success": false, "message": "代码定位失败: [错误原因]", ...}
    """
    try:
        # 使用搜索引擎实例定位代码
        result = search_engine.locate_code_section(file_path, start_line, end_line)
        
        # 转换为API返回格式
        formatted_result = {
            "success": result.get("success", False),
            "file": file_path,
            "start_line": result.get("start_line", start_line),
            "end_line": result.get("end_line", end_line)
        }
        
        # 添加代码片段和上下文
        if result.get("success", False):
            if "code_section" in result:
                formatted_result["code_section"] = result["code_section"]
            if "context_before" in result:
                formatted_result["context_before"] = result["context_before"]
            if "context_after" in result:
                formatted_result["context_after"] = result["context_after"]
        
        response = json.dumps(formatted_result, ensure_ascii=False, indent=2)
        
        # 提供简洁的摘要
        if result.get("success", False):
            return f"已定位代码段 (行 {start_line}-{end_line})\n{response}"
        else:
            return f"代码定位失败: {result.get('error', '未知错误')}\n{response}"
    except Exception as e:
        error_result = {
            "success": False,
            "message": f"执行locate_code_section时出错",
            "error": str(e)
        }
        return json.dumps(error_result, ensure_ascii=False, indent=2)

def get_code_context(file_path: str, line_number: int, context_lines: int = 5) -> str:
    """
    获取代码文件中特定行的上下文
    
    :param file_path: 文件路径
    :param line_number: 目标行号
    :param context_lines: 上下文的行数（默认5行）
    :return: 包含代码行及其上下文的JSON字符串
    
    示例:
      成功: {"success": true, "target_line": "def hello():", "context": "# 函数定义\\ndef hello():\\n    ...", ...}
      失败: {"success": false, "message": "获取上下文失败: [错误原因]", ...}
    """
    try:
        # 使用搜索引擎实例获取上下文
        result = search_engine.get_code_context(file_path, line_number, context_lines)
        
        # 转换为API返回格式
        formatted_result = {
            "success": result.get("success", False),
            "file": file_path,
            "line_number": result.get("line_number", line_number),
            "context_lines": context_lines
        }
        
        # 添加目标行和上下文
        if result.get("success", False):
            if "target_line" in result:
                formatted_result["target_line"] = result["target_line"]
            if "context" in result:
                formatted_result["context"] = result["context"]
        
        response = json.dumps(formatted_result, ensure_ascii=False, indent=2)
        
        # 提供简洁的摘要
        if result.get("success", False):
            return f"已获取第 {line_number} 行上下文\n{response}"
        else:
            return f"获取上下文失败: {result.get('error', '未知错误')}\n{response}"
    except Exception as e:
        error_result = {
            "success": False,
            "message": f"执行get_code_context时出错",
            "error": str(e)
        }
        return json.dumps(error_result, ensure_ascii=False, indent=2)

def edit_code_section_by_line(file_path: str, start_line: int, end_line: int, new_code: str) -> str:
    """
    编辑特定文件中指定行范围的代码
    
    :param file_path: 要编辑的文件路径
    :param start_line: 起始行号
    :param end_line: 结束行号
    :param new_code: 新代码内容
    :return: 包含编辑结果的JSON字符串
    
    示例:
      成功: {"success": true, "file": "/path/to/file.py", "diff": "..."} 
      失败: {"success": false, "message": "编辑失败: [错误原因]", ...}
    """
    try:
        # 使用增强版编辑函数
        result = edit_code_section(file_path, start_line, end_line, new_code)
        
        # 转换为统一的API返回格式
        formatted_result = {
            "success": result.get("成功", False),
            "file": result.get("文件", file_path),
            "start_line": result.get("起始行", start_line),
            "end_line": result.get("结束行", end_line),
            "backup_file": result.get("备份文件", "")
        }
        
        # 添加差异信息
        if "差异" in result:
            formatted_result["diff"] = result["差异"]
        
        # 添加错误信息
        if "错误" in result:
            formatted_result["error"] = result["错误"]
        
        response = json.dumps(formatted_result, ensure_ascii=False, indent=2)
        
        # 提供简洁的编辑结果摘要
        if formatted_result["success"]:
            return f"代码区域编辑成功 (行 {start_line}-{end_line})\n{response}"
        else:
            return f"代码编辑失败: {formatted_result.get('error', '未知错误')}\n{response}"
    except Exception as e:
        error_result = {
            "success": False,
            "message": f"执行edit_code_section_by_line时出错",
            "error": str(e)
        }
        return json.dumps(error_result, ensure_ascii=False, indent=2)

def edit_function_in_file(file_path: str, function_name: str, new_code: str) -> str:
    """
    编辑特定文件中的指定函数
    
    :param file_path: 要编辑的文件路径
    :param function_name: 要编辑的函数名
    :param new_code: 新函数代码
    :return: 包含编辑结果的JSON字符串
    
    示例:
      成功: {"success": true, "file": "/path/to/file.py", "function": "my_function", ...} 
      失败: {"success": false, "message": "函数编辑失败: [错误原因]", ...}
    """
    try:
        # 使用增强版编辑函数
        result = edit_function(file_path, function_name, new_code)
        
        # 转换为统一的API返回格式
        formatted_result = {
            "success": result.get("成功", False),
            "file": result.get("文件", file_path),
            "function": function_name,
            "start_line": result.get("起始行", 0),
            "end_line": result.get("结束行", 0),
            "backup_file": result.get("备份文件", "")
        }
        
        # 添加差异信息
        if "差异" in result:
            formatted_result["diff"] = result["差异"]
        
        # 添加错误信息
        if "错误" in result:
            formatted_result["error"] = result["错误"]
        
        response = json.dumps(formatted_result, ensure_ascii=False, indent=2)
        
        # 提供简洁的编辑结果摘要
        if formatted_result["success"]:
            return f"函数 '{function_name}' 编辑成功\n{response}"
        else:
            return f"函数编辑失败: {formatted_result.get('error', '未知错误')}\n{response}"
    except Exception as e:
        error_result = {
            "success": False,
            "message": f"执行edit_function_in_file时出错",
            "error": str(e)
        }
        return json.dumps(error_result, ensure_ascii=False, indent=2)

def edit_code_by_regex(file_path: str, pattern: str, replacement: str) -> str:
    """
    使用正则表达式模式编辑代码
    
    :param file_path: 要编辑的文件路径
    :param pattern: 正则表达式模式
    :param replacement: 替换内容
    :return: 包含编辑结果的JSON字符串
    
    示例:
      成功: {"success": true, "file": "/path/to/file.py", "matches": 3, ...} 
      失败: {"success": false, "message": "正则表达式编辑失败: [错误原因]", ...}
    """
    try:
        # 使用增强版编辑函数
        result = edit_code_by_pattern(file_path, pattern, replacement)
        
        # 转换为统一的API返回格式
        formatted_result = {
            "success": result.get("成功", False),
            "file": result.get("文件", file_path),
            "matches": result.get("匹配数量", 0),
            "backup_file": result.get("备份文件", "")
        }
        
        # 添加差异信息
        if "差异" in result:
            formatted_result["diff"] = result["差异"]
        
        # 添加错误信息
        if "错误" in result:
            formatted_result["error"] = result["错误"]
        
        response = json.dumps(formatted_result, ensure_ascii=False, indent=2)
        
        # 提供简洁的编辑结果摘要
        if formatted_result["success"]:
            match_count = formatted_result["matches"]
            return f"正则表达式替换成功，匹配 {match_count} 处\n{response}"
        else:
            return f"正则表达式替换失败: {formatted_result.get('error', '未知错误')}\n{response}"
    except Exception as e:
        error_result = {
            "success": False,
            "message": f"执行edit_code_by_regex时出错",
            "error": str(e)
        }
        return json.dumps(error_result, ensure_ascii=False, indent=2)

def insert_code_at_line(file_path: str, line_number: int, code: str) -> str:
    """
    在特定行插入代码
    
    :param file_path: 要编辑的文件路径
    :param line_number: 插入位置的行号
    :param code: 要插入的代码
    :return: 包含编辑结果的JSON字符串
    
    示例:
      成功: {"success": true, "file": "/path/to/file.py", "line": 10, ...} 
      失败: {"success": false, "message": "代码插入失败: [错误原因]", ...}
    """
    try:
        # 使用增强版编辑函数
        result = insert_code(file_path, line_number, code)
        
        # 转换为统一的API返回格式
        formatted_result = {
            "success": result.get("成功", False),
            "file": result.get("文件", file_path),
            "line": result.get("插入行", line_number),
            "backup_file": result.get("备份文件", "")
        }
        
        # 添加错误信息
        if "错误" in result:
            formatted_result["error"] = result["错误"]
        
        response = json.dumps(formatted_result, ensure_ascii=False, indent=2)
        
        # 提供简洁的编辑结果摘要
        if formatted_result["success"]:
            return f"代码已成功插入到第 {line_number} 行\n{response}"
        else:
            return f"代码插入失败: {formatted_result.get('error', '未知错误')}\n{response}"
    except Exception as e:
        error_result = {
            "success": False,
            "message": f"执行insert_code_at_line时出错",
            "error": str(e)
        }
        return json.dumps(error_result, ensure_ascii=False, indent=2)

def run_code_safely(code: str) -> str:
    """
    在安全环境中执行Python代码并返回结果
    
    :param code: 要执行的Python代码
    :return: 包含执行结果的JSON字符串
    
    示例:
      成功: {"success": true, "output": "Hello World", "execution_time": 0.123, ...}
      失败: {"success": false, "message": "执行失败: [错误原因]", "error": "...", ...}
    """
    try:
        # 使用增强版的安全执行函数
        result = execute_code_safely(code)
        
        # 转换为统一的API返回格式
        formatted_result = {
            "success": result.get("成功", False),
            "output": result.get("输出", ""),
            "execution_time": result.get("执行时间", 0)
        }
        
        # 添加错误信息
        if "错误" in result and result["错误"]:
            formatted_result["error"] = result["错误"]
        
        response = json.dumps(formatted_result, ensure_ascii=False, indent=2)
        
        # 提供简洁的执行结果摘要
        if formatted_result["success"]:
            execution_time = formatted_result["execution_time"]
            return f"代码执行成功 (耗时 {execution_time}秒)\n{response}"
        else:
            return f"代码执行失败: {formatted_result.get('error', '未知错误')}\n{response}"
    except Exception as e:
        error_result = {
            "success": False,
            "message": f"执行run_code_safely时出错",
            "error": str(e)
        }
        return json.dumps(error_result, ensure_ascii=False, indent=2)

def check_code_complexity(code: str) -> str:
    """
    分析代码复杂度和质量指标
    
    :param code: 要分析的Python代码
    :return: 包含复杂度分析结果的JSON字符串
    
    示例:
      成功: {"success": true, "complexity": {"total": 10, "average": 2.5}, "warnings": [...], ...}
      失败: {"success": false, "message": "分析失败: [错误原因]", ...}
    """
    try:
        # 使用增强版的复杂度检查函数
        result = check_complexity(code)
        
        # 转换为统一的API返回格式
        formatted_result = {
            "success": True,
            "complexity": result.get("圈复杂度", {}),
            "code_stats": {
                "total_lines": result.get("代码行数", 0),
                "code_lines": result.get("有效代码行", 0),
                "comment_lines": result.get("注释行", 0),
                "blank_lines": result.get("空行", 0)
            }
        }
        
        # 添加函数复杂度信息
        if "函数复杂度" in result:
            formatted_result["function_complexity"] = result["函数复杂度"]
        
        # 添加警告信息
        if "警告" in result and result["警告"]:
            formatted_result["warnings"] = result["警告"]
        
        response = json.dumps(formatted_result, ensure_ascii=False, indent=2)
        
        # 提供简洁的分析结果摘要
        total_complexity = formatted_result["complexity"].get("总计", 0)
        avg_complexity = formatted_result["complexity"].get("平均", 0)
        warning_count = len(formatted_result.get("warnings", []))
        
        return f"代码复杂度分析完成 (总复杂度: {total_complexity}, 平均: {avg_complexity}, 警告: {warning_count}条)\n{response}"
    except Exception as e:
        error_result = {
            "success": False,
            "message": f"执行check_code_complexity时出错",
            "error": str(e)
        }
        return json.dumps(error_result, ensure_ascii=False, indent=2) 