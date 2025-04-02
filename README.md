# DeepSeek-PC-Manager

基于DeepSeek大语言模型的智能助手系统，提供多种功能，包括文本交互、语音识别与合成、代码生成、邮件管理、天气查询等。

## 功能模块

### 核心功能
- **文本对话**：与大语言模型实时交互
- **语音识别与合成**：支持语音输入和输出（仅完整版本）
- **自主任务规划**：AI自动分解复杂任务并执行
- **错误处理与修复**：自动检测执行错误并尝试修复
- **上下文理解**：保持对话上下文连续性

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
或双击`start_voice_mode.bat`

### 交互方式
- **基础版本**: 仅支持文字输入/输出
- **完整版本**: 支持语音输入(连续1.5秒静音自动结束)和语音输出(自动将回复转为语音)

## 代码工具功能

本项目集成了代码生成和管理工具，无需使用PowerShell命令即可操作代码文件：

### 可用工具

1. **write_code** - 将代码写入文件
   ```python
   {
     "file_name": "example.py",  # 文件路径和名称
     "code": "print('Hello World')"  # 代码内容
   }
   ```

2. **verify_code** - 验证Python代码语法
   ```python
   {
     "code": "def example(): return 42"  # 要验证的Python代码
   }
   ```

3. **append_code** - 向文件追加代码
   ```python
   {
     "file_name": "example.py",  # 要追加的文件
     "content": "\ndef new_function():\n    pass"  # 要追加的内容
   }
   ```

4. **read_code** - 读取文件内容
   ```python
   {
     "file_name": "example.py"  # 要读取的文件
   }
   ```

5. **create_module** - 创建Python模块
   ```python
   {
     "module_name": "utils",  # 模块名称（不含.py）
     "functions_json": '[{"name": "add", "params": "a, b", "body": "return a + b", "docstring": "Add two numbers"}]'  # 函数定义JSON
   }
   ```

### 代码工具示例

可以运行代码生成器示例：
```bash
python -c "import code_tools; print(code_tools.write_code('hello_world.py', 'print(\"Hello, AI generated World!\")\n'))"
```
或双击`code_generator_demo.bat`

## 常见问题

1. **PyAudio安装失败**：
   - Windows: 下载预编译wheel文件安装
   - Linux: 安装系统依赖 `sudo apt-get install python3-pyaudio portaudio19-dev`
   - macOS: 使用Homebrew安装 `brew install portaudio`

2. **API密钥配置**：
   - 确保.env文件中的API密钥已正确配置
   - DeepSeek API密钥需要在[DeepSeek官网](https://platform.deepseek.com/)申请

3. **语音功能不工作**：
   - 检查麦克风和扬声器设置
   - 确保pyaudio和edge-tts正确安装
   - 语音识别需要网络连接

4. **依赖安装问题**：
   - 尝试使用国内镜像源: `pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple`

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

联系邮箱：1792491376@qq.com### 新增功能
- **AI任务自动化**：支持自动分解复杂任务并执行
- **智能错误修复**：自动检测并尝试修复执行错误
- **多工具集成**：增强文件操作、代码生成等工具链