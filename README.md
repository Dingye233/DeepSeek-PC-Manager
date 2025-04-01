# DeepSeek-PC-Manager

DeepSeek-PC-Manager 是一个基于 DeepSeek 大模型的本地电脑管理工具。通过自然语言交互，用户可以方便地控制本地电脑的各种服务，并执行一些基本的系统管理任务。

## 功能特性

1. **本地电脑控制**: 通过大模型构建的 Agent 控制本地电脑的各种服务。
2. **天气查询**: 查询指定城市未来24小时的天气情况。
3. **时间查询**: 获取当前时间，支持 UTC 和本地时区。
4. **文件管理**: 对本地电脑文件进行增删查改操作。
5. **系统管理**: 基本的系统管理功能，如进程控制、系统设置等。
6. **脚本编写与运行**: 支持通过大模型编写脚本并运行。
7. **邮件收发**: 查看收件箱邮件列表、获取邮件详情，以及发送邮件。
8. **远程服务器管理**: 通过 SSH 管理远程 Ubuntu 服务器。
9. **文本转语音**: 使用火山引擎 TTS 实现文本转语音功能。
10. **编码与文件生成**: 创建指定文件并写入内容，返回文件绝对路径。
11. **深度思考模型 R1**: 调用 R1 模型解决棘手问题。

## 安装说明

### 环境要求

- Python 3.x
- Windows 操作系统
- Visual C++ Build Tools（用于编译某些Python包）

### 安装步骤

#### 1. 创建并激活conda虚拟环境（推荐）

1. 安装Anaconda或Miniconda（如果尚未安装）：
   - 访问 [Anaconda下载页面](https://www.anaconda.com/download) 或 [Miniconda下载页面](https://docs.conda.io/en/latest/miniconda.html)
   - 下载并安装适合您系统的版本

2. 一键创建环境（推荐）：
```bash
# 使用environment.yml文件创建环境（包含所有必需依赖）
conda env create -f environment.yml
# 激活环境
conda activate deepseek-pc
```

3. 验证环境：
```bash
# 查看当前Python路径，应该指向conda环境目录
where python
# 查看Python版本，应该是3.10.x
python --version
```

注意：如果创建环境时遇到网络问题，可以尝试使用清华源：
```bash
conda config --add channels https://mirrors.tuna.tsinghua.edu.cn/anaconda/pkgs/free/
conda config --add channels https://mirrors.tuna.tsinghua.edu.cn/anaconda/pkgs/main/
conda config --set show_channel_urls yes
conda env create -f environment.yml
```

#### 2. 安装 Visual C++ Build Tools

在安装Python包之前，需要先安装Visual C++ Build Tools：

1. 访问 [Visual Studio 下载页面](https://visualstudio.microsoft.com/visual-cpp-build-tools/)
2. 下载并安装 "Build Tools for Visual Studio"
3. 在安装程序中选择 "Desktop development with C++"

#### 3. 安装Python依赖

在项目根目录下打开命令提示符（CMD）或PowerShell，运行以下命令：

```bash
pip install -r requirements.txt
```

如果安装过程中遇到问题，可以尝试以下替代方案：

1. 使用清华源加速安装：
```bash
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
```

2. 如果某些包安装失败，可以单独安装：
```bash
pip install openai python-dotenv edge-tts playsound requests geopy keyboard SpeechRecognition paramiko PySimpleGUI pyaudio python-dateutil beautifulsoup4 lxml
```

#### 4. 配置环境变量

1. 在项目根目录创建 `.env` 文件，复制以下内容并填写相应的API密钥：

```bash
# 必需配置
api_key="your_deepseek_api_key"  # DeepSeek API密钥，从 https://api.deepseek.com 获取

# 可选配置（根据需要使用）
# 和风天气API配置
key="your_qweather_api_key"  # 和风天气API密钥，从 https://dev.qweather.com/ 获取

# 邮件服务配置
QQ_EMAIL="your_qq_email"  # QQ邮箱地址
AUTH_CODE="your_auth_code"  # QQ邮箱授权码，在QQ邮箱设置中获取

# 语音识别配置（用于语音输入功能）
sttkey="your_stt_api_key"  # 语音识别API密钥，从 https://api.siliconflow.cn/ 获取

# 语音合成配置（用于语音输出功能）
ttskey="your_tts_api_key"  # 语音合成API密钥，从 https://api.siliconflow.cn/ 获取

# 火山引擎TTS配置（用于语音输出功能）
appid="your_volcano_appid"  # 火山引擎应用ID
access_token="your_volcano_access_token"  # 火山引擎访问令牌
```

2. 获取API密钥：
   - **必需配置**：
     - DeepSeek API密钥：从 https://api.deepseek.com 获取（必需，用于基础对话功能）
   
   - **可选配置**（根据需要使用）：
     - 和风天气API密钥：从 https://dev.qweather.com/ 获取（用于天气查询功能）
     - QQ邮箱配置：在QQ邮箱设置中获取授权码（用于邮件收发功能）
     - 语音识别API密钥：从 https://api.siliconflow.cn/ 获取（用于语音输入功能）
     - 语音合成API密钥：从 https://api.siliconflow.cn/ 获取（用于语音输出功能）
     - 火山引擎TTS配置：从火山引擎控制台获取（用于语音输出功能）

3. 将获取到的API密钥替换到 `.env` 文件中对应的位置

注意：
- 仅配置 DeepSeek API 密钥时，可以使用基础版本（`deepseekAPI.py`）进行文本对话
- 如需使用语音功能，需要配置语音识别和语音合成相关的API密钥
- 其他功能（天气查询、邮件收发等）需要配置对应的API密钥

#### 5. 配置用户信息（可选）

1. 在项目根目录创建 `user_information.txt` 文件，用于存储您的个人信息和偏好设置。这些信息将帮助AI更好地理解您的使用习惯和需求。

2. 如果您没有手动创建该文件，程序会在首次运行时自动创建一个空的文件。

3. 文件格式示例：
```txt
# 用户关键信息表

## 基本信息
- 姓名：张三
- 年龄：25
- 职业：软件工程师
- 所在地：北京

## 系统偏好
- 操作系统：Windows 10
- 常用浏览器：Chrome
- 工作目录：D:/Projects
- 常用IDE：VS Code

## 个人习惯
- 喜欢使用深色主题
- 习惯使用快捷键
- 经常使用语音输入
- 偏好简洁的界面

## 重要日期
- 生日：1998-01-01
- 入职日期：2020-07-01

## 联系方式
- 邮箱：example@email.com
- 手机：13800138000

## 其他信息
- 常用语言：中文、English
- 兴趣爱好：编程、阅读、运动
- 特殊需求：需要定期备份重要文件
- 常用工具：Git、Docker、Postman
```

4. 您可以根据需要修改或添加其他信息，例如：
   - 常用联系人
   - 重要文件路径
   - 工作习惯
   - 特殊需求
   - 其他个人偏好

注意：这些信息将帮助AI更好地理解您的使用习惯和需求，提供更个性化的服务。您可以根据实际需要填写或修改这些信息。如果文件为空，程序仍然可以正常运行，只是AI助手将无法获取到您的个性化信息。

#### 6. 验证安装

安装完成后，可以通过以下命令验证安装是否成功：

```bash
python -c "import openai, dotenv, edge_tts, playsound, requests, geopy, keyboard, speech_recognition, paramiko, PySimpleGUI, pyaudio, dateutil, bs4, lxml; print('所有依赖安装成功！')"
```

### 常见问题

1. **pyaudio 安装失败**
   - 确保已安装 Visual C++ Build Tools
   - 尝试使用预编译的wheel文件：
     ```bash
     pip install pipwin
     pipwin install pyaudio
     ```

2. **edge-tts 安装失败**
   - 确保网络连接正常
   - 尝试使用国内镜像源

3. **其他包安装失败**
   - 检查Python版本是否兼容
   - 确保pip已更新到最新版本：
     ```bash
     python -m pip install --upgrade pip
     ```

### 注意事项

1. 安装过程中可能需要管理员权限
2. 某些包可能需要额外的系统依赖，请按照提示安装
3. 如果使用虚拟环境，请确保在虚拟环境中执行安装命令
4. 请妥善保管您的API密钥，不要将其分享给他人
5. 使用conda环境时：
   - 每次打开新的命令行窗口都需要重新激活环境：`conda activate deepseek-pc`
   - 激活成功后，命令行前面会显示 `(deepseek-pc)`，表示已切换到该环境
   - 如果要退出环境，可以使用 `conda deactivate` 命令

## 使用说明

### 1. 运行方式

#### 1.1 基础版本（无语音功能）
使用 `deepseekAPI.py` 运行，仅支持文本交互：
```bash
# 确保已激活conda环境
conda activate deepseek-pc
# 运行程序
python deepseekAPI.py
```

#### 1.2 完整版本（带语音功能）
使用 `aaaa.py` 运行，支持语音输入和语音输出：
```bash
# 确保已激活conda环境
conda activate deepseek-pc
# 运行程序
python aaaa.py
```

### 2. 交互使用
- 基础版本：通过文本输入与系统交互
- 完整版本：
  - 语音输入：直接说话即可（静音1.5秒自动结束）
  - 语音输出：系统会自动将回复转换为语音播放

## 示例

- **查询天气**: "告诉我北京今天的天气"
- **时间查询**: "现在UTC时间是多少"
- **文件管理**: "在D盘创建一个test.txt文件"
- **系统管理**: "帮我关闭一下浏览器的进程"
- **脚本运行**: "写一个Python脚本打印Hello World并运行"
- **邮件功能**: "查看我的收件箱" 或 "发送邮件给2690119214@qq.com"
- **远程服务器**: "在远程服务器上执行ls命令"
- **文本转语音**: "把这段文字转成语音"
- **编码功能**: "创建一个hello.py文件并写入print('Hello World')"
- **深度思考**: "调用R1模型解决这个问题"

## 贡献

欢迎提交 Issue 或 Pull Request，共同完善项目。

## 许可证

本项目采用 Apache 许可证，详情请见 LICENSE 文件。

## 联系与支持

如果安装过程中遇到问题，请查看项目文档或提交Issue。

## 快速启动

1. 创建启动脚本 `start.bat`：
```batch
@echo off
call conda activate deepseek-pc
python aaaa.py
pause
```

2. 双击 `start.bat` 即可启动程序

注意：首次使用需要先完成环境配置和API密钥设置。