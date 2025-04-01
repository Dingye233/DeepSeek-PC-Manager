# DeepSeek-PC-Manager

基于DeepSeek大语言模型的智能助手系统，提供多种功能，包括文本交互、语音识别与合成、代码生成、邮件管理、天气查询等。

## 功能模块

### 核心功能
- **文本对话**：与大语言模型实时交互 (`deepseekAPI.py`)
- **语音识别与合成**：支持语音输入和输出 (`aaaa.py`)
- **自主任务规划**：AI自动分解复杂任务并执行 (`deepseekAPI.py`)
- **错误处理与修复**：自动检测执行错误并尝试修复 (`deepseekAPI.py`)

### 工具集成
- **文件操作**：创建、读取、修改文件 (`code_generator.py`)
- **代码生成器**：编写、验证和管理代码文件 (`code_generator.py`)
- **系统命令执行**：通过PowerShell控制系统 (`powershell_command`)
- **邮件收发**：检查邮箱和发送邮件 (`send_email.py`)
- **天气查询**：获取城市实时天气信息 (`get_weather`)
- **SSH控制**：管理远程服务器 (`ssh_controller.py`)

## 系统要求

- **操作系统**: Windows 10/11
- **Python**: 3.8+
- **主要依赖**: 
  - `edge-tts`
  - `paramiko`
  - `python-dotenv`
  - 完整列表见`requirements.txt`

## 使用说明

### 基础版本 (无语音功能)
```bash
python deepseekAPI.py
```

### 完整版本 (带语音功能)
```bash
python aaaa.py
```

## 项目结构

```
├── README.md
├── aaaa.py                # 完整版本(含语音功能)
├── deepseekAPI.py         # 基础版本(仅文本功能)
├── code_generator.py      # 代码生成工具
├── send_email.py          # 邮件发送功能
├── ssh_controller.py      # SSH远程控制
└── requirements.txt       # 依赖列表
```

## 许可证

仅供个人学习和研究使用