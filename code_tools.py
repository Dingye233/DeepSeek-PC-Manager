import code_generator
import json
from typing import Dict, Any, Optional, List, Union
import os
import re
# 导入增强版工具
from code_edit_enhanced import edit_code_section, edit_function, edit_code_by_pattern, insert_code
from code_validator_enhanced import validate_python_code, verify_imports, execute_code_safely, check_complexity
# 导入代码搜索工具
from code_search_tools import search_code, locate_code_section, get_code_context

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
        
        # 使用原有实现
        result = code_generator.generate_code(file_name, code)
        
        # 增强功能：添加代码验证
        if result.get("success", False) and file_name.endswith('.py'):
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
        
        # 使用原实现
        result = code_generator.append_to_file(file_name, content)
        
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
        # 先使用原实现
        result = code_generator.read_code_file(file_name, with_analysis)
        
        # 增强功能：如果是Python文件并成功读取，添加增强版分析
        if (with_analysis or complexity_check) and result.get("success", False) and file_name.endswith('.py') and "content" in result:
            try:
                code = result["content"]
                if complexity_check:
                    # 添加复杂度分析
                    complexity_analysis = check_complexity(code)
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
            except Exception as e:
                result["enhanced_analysis_error"] = f"增强分析失败: {str(e)}"
        
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
        # 使用原实现
        result = code_generator.create_module(module_name, functions_json)
        
        # 增强功能：验证导入
        if verify_imports and result.get("success", False):
            # 获取生成的代码内容
            try:
                file_path = f"{module_name}.py"
                if "path" in result:
                    file_path = result["path"]
                
                with open(file_path, 'r', encoding='utf-8') as f:
                    code = f.read()
                
                # 验证导入
                import_result = verify_imports(code)
                result["imports_verification"] = import_result
                
                # 如果有问题，添加警告
                if "问题" in import_result and import_result["问题"]:
                    result["warning"] = "模块导入可能存在问题，请查看imports_verification部分"
            except Exception as e:
                result["warning"] = f"导入验证失败: {str(e)}"
        
        # 增强功能：创建测试代码
        if create_tests and result.get("success", False):
            try:
                # 创建测试文件
                test_file = f"test_{module_name}.py"
                
                # 解析函数
                functions = json.loads(functions_json)
                
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