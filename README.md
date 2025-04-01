# 基于大语言模型的智能助手

这是一个基于DeepSeek大语言模型的个人智能助手系统，提供多种功能，包括文本交互、语音识别与合成、代码生成、邮件管理、天气查询等。系统支持两种运行模式：基础文本模式和完整语音模式。

## 功能特点

### 核心功能
- **文本对话**：与大语言模型实时交互
- **语音识别与合成**：支持语音输入和输出（仅完整版本）
- **自主任务规划**：AI自动分解复杂任务并执行
- **错误处理与修复**：自动检测执行错误并尝试修复
- **上下文理解**：保持对话上下文连续性

### 工具集成
- **文件操作**：创建、读取、修改文件
- **代码生成器**：编写、验证和管理代码文件
- **系统命令执行**：通过PowerShell控制系统
- **邮件收发**：检查邮箱和发送邮件
- **天气查询**：获取城市实时天气信息
- **SSH控制**：管理远程服务器

## 系统要求

- **操作系统**: Windows 10/11 (主要支持)，Linux和macOS(部分功能可用)
- **Python**: 3.8或更高版本
- **依赖包**: 见requirements.txt
- **API密钥**: 
  - DeepSeek API
  - 天气API (和风天气)
  - STT API (语音识别，可选)

## 一键安装与配置

本项目提供了自动化安装脚本，可以一键完成环境配置：

```bash
python auto_setup.py
```

此脚本将自动：
1. 检测系统环境
2. 安装所有依赖库
3. 处理特殊依赖(如PyAudio)
4. 配置.env环境变量文件
5. 创建便捷启动脚本

### 手动安装

如需手动安装，请执行以下步骤：

1. 安装依赖：
   ```bash
   pip install -r requirements.txt
   ```

2. 创建并配置.env文件：
   ```
   # API Keys
   api_key=your_deepseek_api_key
   key=your_weather_api_key
   sttkey=your_speech_to_text_api_key
   
   # 邮件设置
   sender=your_email@example.com
   password=your_email_password
   smtp_server=smtp.example.com
   smtp_port=465
   
   # 其他配置
   TTS_DEVICE=cuda
   ```

3. 处理PyAudio的安装(Windows系统)：
   如果pip安装失败，请从[此处](https://www.lfd.uci.edu/~gohlke/pythonlibs/#pyaudio)下载适合您Python版本的wheel文件并安装。

## 配置用户信息 (可选)

为让AI更好地了解用户习惯和偏好，您可以创建`user_information.txt`文件：

```
# 基本信息
姓名: 张三
年龄: 30
职业: 软件工程师
所在地: 北京

# 系统偏好
操作系统: Windows 11
常用浏览器: Chrome
工作目录: D:\Projects
常用IDE: VS Code

# 个人习惯
主题偏好: 暗色主题
常用快捷键: Ctrl+C, Ctrl+V, Alt+Tab
输入法: 搜狗拼音

# 重要日期
生日: 1990-01-01
入职日期: 2020-03-15

# 联系方式
邮箱: example@example.com
电话: 13800138000

# 其他信息
语言: 中文, 英语
爱好: 阅读, 编程, 摄影
特殊需求: 无
常用工具: Git, Docker, Photoshop
```

## 使用方法

### 基础版本 (无语音功能)
运行基础版本:
```bash
python deepseekAPI.py
```
或双击`start_text_mode.bat`

### 完整版本 (带语音功能)
运行完整版本:
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
├── README.md               # 项目说明文档
├── requirements.txt        # 依赖包列表
├── .env                    # 环境变量配置
├── auto_setup.py           # 自动安装配置脚本
├── aaaa.py                 # 完整版本(含语音功能)
├── deepseekAPI.py          # 基础版本(仅文本功能)
├── code_generator.py       # 代码生成核心功能
├── code_tools.py           # 代码工具接口层
├── python_tools.py         # Python辅助工具
├── get_email.py            # 邮件获取功能
├── send_email.py           # 邮件发送功能
├── ssh_controller.py       # SSH远程控制
├── user_information.txt    # 用户信息配置(可选)
├── start_text_mode.bat     # 基础版本启动脚本
├── start_voice_mode.bat    # 完整版本启动脚本
└── code_generator_demo.bat # 代码工具示例脚本
```

## 许可证

本项目仅用于个人学习和研究，不得用于商业用途。

## 联系方式

如有问题或建议，请通过以下方式联系：

- Email: your-email@example.com
- GitHub: https://github.com/yourusername/your-repo