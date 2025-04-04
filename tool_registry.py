"""


工具注册模块 - 集中管理所有可用的工具定义
这个模块用于定义所有可供AI助手使用的工具，避免在多个文件中重复定义
"""

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
                "description": "【推荐用于代码写入】将代码写入指定文件，专用于创建或覆盖代码文件，支持所有编程语言。比PowerShell更安全可靠，是处理代码的首选工具。",
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
                "description": "【代码安全检查】验证Python代码的语法是否正确，在写入文件前应先验证代码，避免语法错误。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "code": {
                            "type": "string",
                            "description": "要验证的Python代码"
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
                "description": "【推荐用于代码追加】向现有文件追加代码内容，专用于添加代码而不覆盖原文件。相比PowerShell的Add-Content更可靠，是添加代码的首选工具。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "file_name": {
                            "type": "string",
                            "description": "文件名，包括路径和扩展名"
                        },
                        "content": {
                            "type": "string",
                            "description": "要追加的代码内容"
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
                "description": "【推荐用于代码读取】读取代码文件内容，专用于获取代码文件内容，比PowerShell的Get-Content更适合代码分析，是读取代码的首选工具。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "file_name": {
                            "type": "string",
                            "description": "文件名，包括路径和扩展名"
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
                "description": "【推荐用于模块创建】创建包含多个函数的Python模块，自动处理导入和函数定义，大大简化模块创建过程。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "module_name": {
                            "type": "string",
                            "description": "模块名称(不含.py)"
                        },
                        "functions_json": {
                            "type": "string",
                            "description": "函数定义的JSON字符串数组，每个函数包含name、params、body和docstring"
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
                            "description": "是否只提取文本内容而不返回格式信息，默认为false"
                        }
                    },
                    "required": ["file_path"]
                }
            }
        }
    ]
    
    return tools 