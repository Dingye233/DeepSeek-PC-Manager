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
from web_search_tool import web_search, ai_search, semantic_rerank
# 导入code_tools模块中的所有工具函数
from code_tools import (
    write_code,
    verify_code,
    append_code,
    read_code,
    create_module,
    analyze_code,
    search_code_in_file,
    locate_code_section,
    get_code_context,
    edit_code_section_by_line,
    edit_function_in_file,
    edit_code_by_regex,
    insert_code_at_line,
    check_code_complexity
)

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
                            "description": "向用户展示的提示信息"
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
                            "description": "【必须设置】命令执行的最大超时时间（秒）。你必须根据命令的复杂性和可能的执行时间进行评估设置，禁止使用默认值。"
                        }
                    },
                    "required": ["command", "timeout"]
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
                            "description": "【必须设置】命令执行的最大超时时间（秒）。你必须根据命令的复杂性和可能的执行时间进行评估设置，禁止使用默认值。"
                        }
                    },
                    "required": ["command", "timeout"]
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
                "name": "web_search",
                "description": "【Web搜索工具】通过博查API搜索引擎查询信息。使用限制：1) 仅当其他工具无法解决问题时使用；2) 优先使用本地代码搜索和文件操作工具；3) 不要直接复制用户的原始问题作为查询词；4) 应提取核心关键词并重新组织为精简的搜索关键词；5) 移除不必要的限定词、连词和虚词；6) 使用专业术语替代通用描述；7) 优先使用中文关键词进行搜索；8) 必要时将长句拆分为多个关键词组合",
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
                            "description": "是否过滤成人内容，默认为false"
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
                "name": "ai_search",
                "description": "【AI搜索增强工具】通过博查AI Search API进行高级搜索，功能包括：1)返回网页结果(最多50条)；2)获取并保存图片(如人物、产品、场景等)；3)提供多种模态卡片(包括天气、百科、医疗、万年历、火车、星座、贵金属、汇率、油价、手机、股票、汽车等垂直领域结构化数据)；4)生成AI回答和延伸问题。比普通web_search能获取更丰富、更智能的搜索体验，并能将图片和模态卡保存到本地文件夹供后续使用。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "搜索关键词。可以是一般查询(如'Windows蓝屏问题')，也可以是针对特定图片('奥迪RS7高清图片')或特定模态卡('上海天气'、'比特币汇率')的查询。针对垂直领域使用更精确的词汇能够获得更好的结构化数据。"
                        },
                        "num_results": {
                            "type": "integer",
                            "description": "返回结果数量，默认为5，最大为50。对于图片和模态卡，建议使用较小值如3-5"
                        },
                        "filter_adult": {
                            "type": "boolean",
                            "description": "是否过滤成人内容，默认为false"
                        },
                        "answer": {
                            "type": "boolean",
                            "description": "是否生成AI回答，默认为false。当需要AI进行总结或分析时设为true"
                        },
                        "stream": {
                            "type": "boolean",
                            "description": "是否使用流式输出，默认为false。流式输出适合长回答，但不影响模态卡和图片的获取"
                        }
                    },
                    "required": ["query"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "semantic_rerank",
                "description": "【语义排序工具】使用博查Semantic Reranker对文档列表进行语义相关性排序，根据用户查询智能对文档进行重新排序，确保最相关的内容排在前面。适用于需要对大量文本内容按相关性排序的场景。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "查询字符串，用于评估文档相关性的基准"
                        },
                        "documents": {
                            "type": "array",
                            "items": {
                                "type": "string"
                            },
                            "description": "要排序的文档列表，每个文档应为字符串"
                        },
                        "model": {
                            "type": "string",
                            "description": "使用的排序模型，默认为'gte-rerank'"
                        },
                        "top_n": {
                            "type": "integer",
                            "description": "返回排名前n的结果，默认返回所有结果"
                        }
                    },
                    "required": ["query", "documents"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "analyze_code",
                "description": "【代码分析工具】分析代码文件的结构和质量，提供详细的代码质量报告、复杂度分析和潜在问题识别",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "file_path": {
                            "type": "string",
                            "description": "代码文件路径"
                        }
                    },
                    "required": ["file_path"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "search_code_in_file",
                "description": "【代码搜索工具】在指定文件中搜索代码，支持多种搜索模式，包括语义搜索、精确匹配、正则表达式等",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "file_path": {
                            "type": "string",
                            "description": "要搜索的文件路径"
                        },
                        "query": {
                            "type": "string",
                            "description": "搜索查询内容"
                        },
                        "search_type": {
                            "type": "string",
                            "description": "搜索类型，可选：'semantic'(语义)、'exact'(精确)、'regex'(正则)、'function'(函数)、'class'(类)、'import'(导入)",
                            "enum": ["semantic", "exact", "regex", "function", "class", "import"],
                            "default": "semantic"
                        }
                    },
                    "required": ["file_path", "query"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "locate_code_section",
                "description": "【代码定位工具】定位并提取代码文件中的特定行范围，获取代码上下文信息",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "file_path": {
                            "type": "string",
                            "description": "文件路径"
                        },
                        "start_line": {
                            "type": "integer",
                            "description": "起始行号"
                        },
                        "end_line": {
                            "type": "integer",
                            "description": "结束行号"
                        }
                    },
                    "required": ["file_path", "start_line", "end_line"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "get_code_context",
                "description": "【代码上下文工具】获取代码文件中特定行的上下文，查看代码的周围环境",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "file_path": {
                            "type": "string",
                            "description": "文件路径"
                        },
                        "line_number": {
                            "type": "integer",
                            "description": "目标行号"
                        },
                        "context_lines": {
                            "type": "integer",
                            "description": "上下文的行数（默认5行）",
                            "default": 5
                        }
                    },
                    "required": ["file_path", "line_number"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "edit_code_section_by_line",
                "description": "【代码编辑工具】编辑特定文件中指定行范围的代码，自动创建备份并验证编辑后的代码质量",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "file_path": {
                            "type": "string",
                            "description": "要编辑的文件路径"
                        },
                        "start_line": {
                            "type": "integer",
                            "description": "起始行号"
                        },
                        "end_line": {
                            "type": "integer",
                            "description": "结束行号"
                        },
                        "new_code": {
                            "type": "string",
                            "description": "新代码内容"
                        }
                    },
                    "required": ["file_path", "start_line", "end_line", "new_code"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "edit_function_in_file",
                "description": "【函数编辑工具】编辑特定文件中的指定函数，自动定位函数边界并替换函数代码",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "file_path": {
                            "type": "string",
                            "description": "要编辑的文件路径"
                        },
                        "function_name": {
                            "type": "string",
                            "description": "要编辑的函数名"
                        },
                        "new_code": {
                            "type": "string",
                            "description": "新函数代码"
                        }
                    },
                    "required": ["file_path", "function_name", "new_code"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "edit_code_by_regex",
                "description": "【正则替换工具】使用正则表达式模式编辑代码，进行批量替换操作",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "file_path": {
                            "type": "string",
                            "description": "要编辑的文件路径"
                        },
                        "pattern": {
                            "type": "string",
                            "description": "正则表达式模式"
                        },
                        "replacement": {
                            "type": "string",
                            "description": "替换内容"
                        }
                    },
                    "required": ["file_path", "pattern", "replacement"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "insert_code_at_line",
                "description": "【代码插入工具】在特定行插入代码，不覆盖现有内容",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "file_path": {
                            "type": "string",
                            "description": "要编辑的文件路径"
                        },
                        "line_number": {
                            "type": "integer",
                            "description": "插入位置的行号"
                        },
                        "code": {
                            "type": "string",
                            "description": "要插入的代码"
                        }
                    },
                    "required": ["file_path", "line_number", "code"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "check_code_complexity",
                "description": "【代码复杂度分析工具】分析代码复杂度和质量指标，包括圈复杂度、代码行数、注释比例等",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "code": {
                            "type": "string",
                            "description": "要分析的Python代码"
                        }
                    },
                    "required": ["code"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "search_code",
                "description": "【代码搜索工具】使用代码搜索引擎在整个代码库中搜索代码，支持语义搜索和关键词匹配",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "搜索查询字符串"
                        },
                        "search_type": {
                            "type": "string",
                            "description": "搜索类型，可选：'semantic'(语义)、'keyword'(关键词)",
                            "enum": ["semantic", "keyword"],
                            "default": "semantic"
                        },
                        "file_extensions": {
                            "type": "string",
                            "description": "要搜索的文件扩展名，用逗号分隔，例如：'.py,.js,.java'",
                        },
                        "max_results": {
                            "type": "integer",
                            "description": "返回的最大结果数量",
                            "default": 5
                        }
                    },
                    "required": ["query"]
                }
            }
        }
    ]
    
    return tools 