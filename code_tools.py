import code_generator
import json

def write_code(file_name: str, code: str) -> str:
    """
    将代码写入文件并返回结果
    
    :param file_name: 要创建的文件名（带扩展名）
    :param code: 文件内容
    :return: 操作结果（JSON字符串）
    """
    result = code_generator.generate_code(file_name, code)
    return json.dumps(result, ensure_ascii=False)

def verify_code(code: str) -> str:
    """
    验证Python代码语法是否正确
    
    :param code: 要验证的Python代码
    :return: 验证结果（JSON字符串）
    """
    result = code_generator.verify_python_code(code)
    return json.dumps(result, ensure_ascii=False)

def append_code(file_name: str, content: str) -> str:
    """
    向文件追加代码内容
    
    :param file_name: 文件名
    :param content: 要追加的内容
    :return: 操作结果（JSON字符串）
    """
    result = code_generator.append_to_file(file_name, content)
    return json.dumps(result, ensure_ascii=False)

def read_code(file_name: str) -> str:
    """
    读取代码文件内容
    
    :param file_name: 文件名
    :return: 文件内容（JSON字符串）
    """
    result = code_generator.read_code_file(file_name)
    return json.dumps(result, ensure_ascii=False)

def create_module(module_name: str, functions_json: str) -> str:
    """
    创建包含多个函数的Python模块
    
    :param module_name: 模块名称(不含.py)
    :param functions_json: 函数定义的JSON字符串，格式为 
                          [{"name": "函数名", "params": "参数字符串", 
                            "body": "函数体", "docstring": "文档字符串"}, ...]
    :return: 操作结果（JSON字符串）
    """
    try:
        functions = json.loads(functions_json)
        result = code_generator.create_python_module(module_name, functions)
        return json.dumps(result, ensure_ascii=False)
    except Exception as e:
        error_result = {
            "success": False,
            "message": f"解析函数JSON失败: {str(e)}",
            "error": str(e)
        }
        return json.dumps(error_result, ensure_ascii=False) 