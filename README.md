# DeepSeek-PC-Manager

DeepSeek-PC-Manager 是一个基于 DeepSeek 大模型的本地电脑管理工具。通过自然语言交互，用户可以方便地控制本地电脑的各种服务，并执行一些基本的系统管理任务。

## 功能特性

1. **本地电脑控制**: 通过大模型构建的 Agent 控制本地电脑的各种服务。
2. **天气查询**: 查询指定城市未来24小时的天气情况。
3. **时间查询**: 获取当前时间，支持 UTC 和本地时区。
4. **文件管理**: 对本地电脑文件进行增删查改操作。
5. **系统管理**: 基本的系统管理功能，如进程控制、系统设置等。
6. **脚本编写与运行**: 最近新增功能，支持通过大模型编写脚本并运行。

## 安装说明

### 1. 安装 Python
确保您的系统已安装 Python 3.x 版本。可以从 [Python 官网](https://www.python.org/downloads/) 下载安装。

### 2. 安装依赖
在项目根目录下，运行以下命令安装所需依赖：

#### Windows
```bash
pip install -r requirements.txt
```

#### Linux/MacOS
```bash
pip3 install -r requirements.txt
```

将以下内容保存为 `requirements.txt`：
```
openai
python-dotenv
edge-tts
playsound
requests
geopy
keyboard
SpeechRecognition
```

### 3. 本地模块
以下模块为项目本地模块，无需单独安装：
- `get_email`
- `python_tools`
- `send_email`
- `R1_optimize`

其他标准库（无需安装）：
- `json`
- `datetime`
- `asyncio`
- `os`
- `tempfile`
- `threading`
- `time`
- `subprocess`
- `re`
- `queue`

## 使用说明

1. **配置环境变量**: 在项目根目录创建 `.env` 文件，配置必要的环境变量。
2. **运行项目**: 在项目目录下运行 `python main.py` 启动项目。
3. **交互使用**: 通过自然语言与系统交互，执行所需操作。

## 示例

- **查询天气**: "告诉我北京今天的天气"
- **时间查询**: "现在UTC时间是多少"
- **文件管理**: "在D盘创建一个test.txt文件"
- **系统管理**: "帮我关闭一下浏览器的进程"
- **脚本运行**: "写一个Python脚本打印Hello World并运行"

## 贡献

欢迎提交 Issue 和 Pull Request，共同完善项目。

## 许可证

本项目采用 Apache 许可证，详情请见 LICENSE 文件。