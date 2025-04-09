"""


工具注册模块 - 集中管理所有可用的工具定义
这个模块用于定义所有可供AI助手使用的工具，避免在多个文件中重复定义
"""

# 导入代码搜索引擎
from code_search_enhanced import CodeSearchEngine
# 导入增强的代码编辑和审验功能 - 保留导入但不直接注册为工具
# 这些功能已经集成到原有工具中
from code_edit_enhanced import edit_code_section, edit_function, edit_code_by_pattern, insert_code
from code_validator_enhanced import validate_python_code, verify_imports, execute_code_safely, check_complexity
# 导入Web搜索工具
from web_search_tool import web_search, fetch_webpage, filter_search_results

# 初始化代码搜索引擎实例
code_search_engine = CodeSearchEngine()

# 定义所有工具
def get_tools():
    """返回所有可用工具的定义列表"""
    
    tools = [
        {
            "type": "function",
            "function": {
                "name": "clear_context",
                "description": "清除对话历史上下文，只保留系统消息",
                "parameters": {
                    "type": "object",
                    "properties": {}
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "user_input",
                "description": "当需要用户提供额外信息或确认时使用此工具，将暂停执行并使用语音方式等待用户输入",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "prompt": {
                            "type": "string",
                            "description": "向用户展示的提示信息，会通过语音读出"
                        },
                        "timeout": {
                            "type": "integer",
                            "description": "等待用户输入的最大秒数，默认60秒"
                        }
                    },
                    "required": ["prompt"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "get_current_time",
                "description": "获取当前时间",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "timezone": {
                            "type": "string",
                            "description": "时区",
                            "enum": ["UTC", "local"]
                        },
                    }
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "get_weather",
                "description": "获取城市未来24小时的天气(请区分用户问的时间段是属于今天还是明天的天气)",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "city": {
                            "type": "string",
                            "description": "城市名"
                        }
                    },
                    "required": ["city"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "powershell_command",
                "description": "【系统操作工具】通过PowerShell终端来控制系统操作（进程控制/系统设置/文件操作等），具有智能交互能力，可自动分析并响应命令执行过程中的确认请求。注意：对于代码和文件操作，请优先使用专用工具（write_code/read_code/append_code/read_file等）而非此工具。推荐一次执行一条命令，避免使用分号连接多条命令。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "command": {
                            "type": "string",
                            "description": "要执行的PowerShell命令。工具会智能处理需要用户确认的情况"
                        },
                        "timeout": {
                            "type": "integer",
                            "description": "命令执行的最大超时时间（秒），默认60秒。对于复杂或需要长时间运行的命令，应设置更长的超时时间"
                        }
                    },
                    "required": ["command"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "cmd_command",
                "description": "【系统操作工具】通过CMD终端(命令提示符)来控制系统操作，相比PowerShell，CMD更适合执行传统DOS命令、批处理文件和某些特定的Windows系统命令。具有智能交互能力，可自动分析并响应命令执行过程中的确认请求。注意：对于代码和文件操作，请优先使用专用工具而非此工具。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "command": {
                            "type": "string",
                            "description": "要执行的CMD命令。工具会智能处理需要用户确认的情况"
                        },
                        "timeout": {
                            "type": "integer",
                            "description": "命令执行的最大超时时间（秒），默认60秒。对于复杂或需要长时间运行的命令，应设置更长的超时时间"
                        }
                    },
                    "required": ["command"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "get_emails",
                "description": "获取邮箱中的邮件列表",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "limit": {
                            "type": "integer",
                            "description": "获取的邮件数量，默认为10"
                        },
                        "folder": {
                            "type": "string",
                            "description": "邮件文件夹，例如'INBOX'、'Sent'等，默认为'INBOX'"
                        }
                    }
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "get_email_detail",
                "description": "获取指定邮件的详细内容",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "email_id": {
                            "type": "string",
                            "description": "邮件ID"
                        }
                    },
                    "required": ["email_id"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "send_mail",
                "description": "发送一封邮件向指定邮箱",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "receiver": {
                            "type": "string",
                            "description": "收件人邮箱，请严格查看收件人邮箱是否是正确的邮箱格式"
                        },
                        "subject": {
                            "type": "string",
                            "description": "邮件主题"
                        },
                        "text": {
                            "type": "string",
                            "description": "邮件的内容  (用html的模板编写以避免编码问题)"
                        },
                        "attachments": {
                            "type": "string",
                            "description": "可选的附件文件路径，多个文件用英文逗号分隔，例如：'file1.pdf,file2.jpg'"
                        }
                    },
                    "required": ["receiver", "subject", "text"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "R1_opt",
                "description": "调用深度思考模型r1来解决棘手问题。当遇到以下情况时应优先考虑使用此工具：1) 需要生成复杂的代码逻辑；2) 遇到多次尝试仍无法修复的bug；3) 需要进行复杂的算法设计或优化；4) 需要思考复杂的逻辑推理问题；5) 需要全面分析文本中的深层含义；6) 需要多角度思考并给出深入见解的问答。此工具能提供更强大、更精确的思考能力，不仅适用于编程问题，也适用于需要深度思考的文本分析。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "message": {
                            "type": "string",
                            "description": "输入需要深度思考的问题，应包含充分的上下文和详细信息，以便r1模型能够正确理解和解决问题"
                        }
                    },
                    "required": ["message"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "ssh",
                "description": "管理远程ubuntu服务器",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "command": {
                            "type": "string",
                            "description": "输入ubuntu服务器的命令"
                        }
                    },
                    "required": ["command"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "write_code",
                "description": "【增强版代码写入工具】将代码写入指定文件，专用于创建或覆盖代码文件，支持所有编程语言。比PowerShell更安全可靠，并自动进行代码质量验证和错误检测。创建备份并提供代码质量评分。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "file_name": {
                            "type": "string",
                            "description": "文件名，包括路径和扩展名，例如 'app.py' 或 'src/utils.js'"
                        },
                        "code": {
                            "type": "string",
                            "description": "要写入文件的代码内容"
                        },
                        "with_analysis": {
                            "type": "boolean",
                            "description": "是否返回详细的代码分析结果，默认为false",
                            "default": False
                        },
                        "create_backup": {
                            "type": "boolean",
                            "description": "是否创建原文件的备份（如果文件已存在），默认为true",
                            "default": True
                        }
                    },
                    "required": ["file_name", "code"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "verify_code",
                "description": "【增强版代码验证工具】全面验证Python代码，不仅检查语法错误，还分析潜在的逻辑问题、未使用的导入、可能的无限循环等问题，并提供代码质量评分和改进建议。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "code": {
                            "type": "string",
                            "description": "要验证的Python代码"
                        },
                        "verbose": {
                            "type": "boolean",
                            "description": "是否返回详细的验证结果，包括完整的问题列表和建议，默认为false",
                            "default": False
                        },
                        "check_best_practices": {
                            "type": "boolean",
                            "description": "是否检查代码最佳实践（命名规范、注释完整性等），默认为false",
                            "default": False
                        }
                    },
                    "required": ["code"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "append_code",
                "description": "【增强版代码追加工具】向文件追加代码内容，会自动验证追加后代码的完整性和质量，创建备份文件，并提供详细的代码分析和潜在问题警告。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "file_name": {
                            "type": "string",
                            "description": "文件名，可以是相对路径或绝对路径"
                        },
                        "content": {
                            "type": "string",
                            "description": "要追加的内容"
                        },
                        "verify_after": {
                            "type": "boolean",
                            "description": "是否在追加后验证完整代码，默认为false",
                            "default": False
                        },
                        "create_backup": {
                            "type": "boolean",
                            "description": "是否创建文件备份，默认为true",
                            "default": True
                        }
                    },
                    "required": ["file_name", "content"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "read_code",
                "description": "【增强版代码读取工具】读取代码文件内容并提供深度分析，包括代码结构、复杂度分析、代码质量指标和潜在问题识别，适用于全面理解和分析代码。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "file_name": {
                            "type": "string",
                            "description": "文件名，可以是相对路径或绝对路径"
                        },
                        "with_analysis": {
                            "type": "boolean",
                            "description": "是否包含基本代码分析，默认为true",
                            "default": True
                        },
                        "complexity_check": {
                            "type": "boolean",
                            "description": "是否进行代码复杂度分析，默认为false",
                            "default": False
                        }
                    },
                    "required": ["file_name"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "create_module",
                "description": "【增强版模块创建工具】创建包含多个函数的Python模块，自动验证导入模块的可用性，检查代码质量，并生成完整的模块结构，包括导入语句、文档字符串和代码质量评分。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "module_name": {
                            "type": "string",
                            "description": "模块名称(不含.py)"
                        },
                        "functions_json": {
                            "type": "string",
                            "description": "函数定义的JSON字符串，格式为 [{'name': '函数名', 'params': '参数字符串', 'body': '函数体', 'docstring': '文档字符串'}]"
                        },
                        "verify_imports": {
                            "type": "boolean",
                            "description": "是否验证导入语句的可用性，默认为false",
                            "default": False
                        },
                        "create_tests": {
                            "type": "boolean",
                            "description": "是否创建对应的测试文件，默认为false",
                            "default": False
                        }
                    },
                    "required": ["module_name", "functions_json"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "read_file",
                "description": "【推荐用于文件读取】读取各种文件格式（文本、图片、文档等）并提取内容，支持多种格式，比PowerShell的Get-Content功能更强大，是读取文件的首选工具。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "file_path": {
                            "type": "string",
                            "description": "要读取的文件路径"
                        },
                        "encoding": {
                            "type": "string",
                            "description": "文件编码，默认为utf-8"
                        },
                        "extract_text_only": {
                            "type": "boolean",
                            "description": "是否只提取文本内容而不返回格式信息，默认为false",
                            "default": False
                        }
                    },
                    "required": ["file_path"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "search_code",
                "description": "【代码搜索增强工具】在代码文件中智能搜索特定内容，支持多种搜索模式（语义搜索、精确匹配、正则表达式等），帮助快速定位代码片段",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "file_path": {
                            "type": "string",
                            "description": "要搜索的文件路径"
                        },
                        "query": {
                            "type": "string",
                            "description": "搜索关键词。应从用户问题中提取2-5个核心词组，去掉无关修饰词。例如用户问'如何解决Windows 10蓝屏死机问题'，应搜索'Windows 10 蓝屏 解决方法'而非整句。避免长句，使用术语和专业名词。"
                        },
                        "search_type": {
                            "type": "string",
                            "description": "搜索类型: semantic(语义搜索)、exact(精确匹配)、regex(正则表达式)、function(函数定义)、class(类定义)、import(导入语句)",
                            "enum": ["semantic", "exact", "regex", "function", "class", "import"],
                            "default": "semantic"
                        },
                        "num_results": {
                            "type": "integer",
                            "description": "返回结果数量，默认为5，最大为50"
                        },
                        "filter_adult": {
                            "type": "boolean",
                            "description": "是否过滤成人内容，默认为true"
                        },
                        "keywords": {
                            "type": "array",
                            "items": {
                                "type": "string"
                            },
                            "description": "可选的关键词列表，用于过滤搜索结果。当提供时，只返回包含这些关键词的结果。"
                        },
                        "sort_by_relevance": {
                            "type": "boolean",
                            "description": "是否按相关性排序结果，默认为true"
                        },
                        "match_all_keywords": {
                            "type": "boolean",
                            "description": "是否要求匹配所有关键词，默认为false（匹配任意关键词即可）"
                        }
                    },
                    "required": ["file_path", "query"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "fetch_webpage",
                "description": "【Web内容获取工具】抓取和分析指定URL的网页内容。此工具特别适用于：1) 查看搜索结果中特定网页的完整内容；2) 获取文章、教程或文档的详细信息；3) 提取网页中与用户问题最相关的关键部分",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "url": {
                            "type": "string",
                            "description": "网页URL，必须以http://或https://开头"
                        },
                        "extract_keywords": {
                            "type": "array",
                            "items": {
                                "type": "string"
                            },
                            "description": "用于智能提取网页关键句子的词列表。应选择能精确定位用户所需信息的专业术语和核心名词，避免使用常见动词或形容词。例如，查询'Python异步编程教程'，应使用['asyncio', 'coroutine', '异步', '协程']等专业术语作为提取关键词"
                        }
                    },
                    "required": ["url"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "web_search",
                "description": "【Web搜索工具】通过搜索引擎查询信息。请注意：1) 不要直接复制用户的原始问题作为查询词；2) 应提取核心关键词并重新组织为精简的搜索关键词；3) 移除不必要的限定词、连词和虚词；4) 使用专业术语替代通用描述；5) 优先使用中文关键词进行搜索；6) 必要时将长句拆分为多个关键词组合",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "搜索关键词。应从用户问题中提取2-5个核心词组，去掉无关修饰词。例如用户问'如何解决Windows 10蓝屏死机问题'，应搜索'Windows 10 蓝屏 解决方法'而非整句。避免长句，使用术语和专业名词。"
                        },
                        "num_results": {
                            "type": "integer",
                            "description": "返回结果数量，默认为5，最大为50"
                        },
                        "filter_adult": {
                            "type": "boolean",
                            "description": "是否过滤成人内容，默认为true"
                        },
                        "keywords": {
                            "type": "array",
                            "items": {
                                "type": "string"
                            },
                            "description": "可选的关键词列表，用于过滤搜索结果。当提供时，只返回包含这些关键词的结果。"
                        },
                        "sort_by_relevance": {
                            "type": "boolean",
                            "description": "是否按相关性排序结果，默认为true"
                        },
                        "match_all_keywords": {
                            "type": "boolean",
                            "description": "是否要求匹配所有关键词，默认为false（匹配任意关键词即可）"
                        }
                    },
                    "required": ["query"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "filter_search_results",
                "description": "【搜索结果筛选工具】根据精炼关键词从现有搜索结果中智能筛选最相关信息。此工具应在web_search返回大量结果后使用，通过精确的关键词提取用户真正需要的信息",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "results": {
                            "type": "array",
                            "items": {
                                "type": "object"
                            },
                            "description": "搜索结果列表，通常是web_search函数返回的results字段"
                        },
                        "keywords": {
                            "type": "array",
                            "items": {
                                "type": "string"
                            },
                            "description": "筛选关键词列表。应选择用户问题中最具区分性的术语和名词，避免使用通用词。关键词应简短精确，每个词1-3个字为宜。例如，对于'如何解决最新版Windows系统的蓝屏问题'，应使用['最新版', 'Windows', '蓝屏']而非['如何', '解决', '问题']"
                        },
                        "match_all": {
                            "type": "boolean",
                            "description": "是否要求匹配所有关键词，默认为false（匹配任意关键词即可）"
                        }
                    },
                    "required": ["results", "keywords"]
                }
            }
        }
    ]
    
    return tools 