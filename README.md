# DeepSeek-PC-Manager

基于DeepSeek大语言模型的智能助手系统，提供多种功能，包括文本交互、语音识别与合成、代码生成、邮件管理、天气查询等。

---

## 系统特性 | System Features

### 智能任务验证系统 | Intelligent Task Verification System

DeepSeek-PC实现了一套严格的任务验证机制，确保用户请求被真正执行而非仅停留在计划阶段：

1. **计划与执行严格区分**
   - 系统能够明确区分"计划做什么"和"已经做了什么"
   - 仅将有明确工具调用证据的步骤视为已完成
   - 防止大模型将任务描述误认为已执行操作

2. **证据驱动的完成判断**
   - 任务完成状态基于实际工具调用记录而非模型自我评估
   - 为每个关键步骤收集执行证据，包括工具名称、目的和结果
   - 自动计算成功执行的工具调用比例，作为任务完成度的客观指标

3. **幻觉风险评估**
   - 实时监控并评估模型将计划误认为执行的风险
   - 对高风险幻觉场景进行明确警告和强制纠正
   - 通过执行差距分析，揭示计划与实际执行间的差异

4. **递进式验证机制**
   - 在执行前、执行过程中和执行后进行多层次验证
   - 追踪任务进度变化，及时发现进度停滞或倒退的情况
   - 支持多次验证尝试，确保验证结果的可靠性

此验证系统大幅提高了任务执行的可靠性，确保用户请求被真正执行完成，而非仅仅获得一个未实际执行的计划或描述。

---

## 功能模块

### 核心功能

- **文本对话**：与大语言模型实时交互
- **语音识别与合成**：支持语音输入和输出（仅完整版本）
- **自主任务规划**：AI自动分解复杂任务并执行
- **智能任务验证**：严格区分计划与执行，通过工具调用证据验证任务完成度
- **幻觉防护机制**：实时评估和防止模型将计划误认为已执行的操作
- **错误处理与修复**：自动检测执行错误并尝试修复
- **上下文理解**：保持对话上下文连续性

### 工具集成

- **文件操作**：创建、读取、修改文件 (`code_generator.py`)
- **代码生成器**：编写、验证和管理代码文件 (`code_generator.py`)
- **系统命令执行**：通过PowerShell控制系统 (`powershell_command`)
- **邮件收发**：检查邮箱和发送邮件 (`send_email.py`)
- **天气查询**：获取城市实时天气信息 (`get_weather`)
- **SSH控制**：管理远程服务器 (`ssh_controller.py`)

---

## 系统要求

- **操作系统**: Windows 10/11
- **Python**: 3.8+
- **主要依赖**: 
  - `edge-tts`
  - `paramiko`
  - `python-dotenv`
  - 完整列表见`requirements.txt`

---

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

---

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

---

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

---

## 项目结构

```
├── README.md
├── aaaa.py                # 完整版本(含语音功能)
├── deepseekAPI.py         # 基础版本(仅文本功能)
├── tool_registry.py       # 集中式工具定义模块
├── system_utils.py        # 系统工具和命令执行功能
├── code_generator.py      # 代码生成工具
├── code_tools.py          # 代码操作工具集
├── file_utils.py          # 文件操作工具集
├── send_email.py          # 邮件发送功能
├── ssh_controller.py      # SSH远程控制
├── auto_setup.py          # 自动环境配置工具
└── requirements.txt       # 依赖列表
```

---

## 新增功能

### 工具注册模块

为了提高代码的可维护性和减少重复，项目新增了集中式工具注册模块`tool_registry.py`，统一管理所有可用工具的定义。这一改进：

- 消除了在不同文件中重复定义工具的需要
- 简化了工具集的管理和更新
- 保证了工具定义在整个系统中的一致性

### PowerShell命令工具智能交互改进

PowerShell命令执行工具(`powershell_command`)已升级，具备更智能的交互能力：

- **LLM辅助决策**：使用DeepSeek模型分析命令执行过程中的交互提示，自动提供最合适的响应
- **上下文感知**：保留最近50行命令输出作为上下文，提高分析的准确性
- **自信度评估**：根据LLM对建议响应的置信度，自动响应或请求用户确认
- **超时机制**：加入15秒超时机制，确保命令执行不会因等待用户输入而无限阻塞
- **交互计数**：跟踪并显示命令执行过程中的交互次数
- **优化使用建议**：推荐一次执行单条命令，避免使用分号连接多条命令，提高执行的可靠性和安全性

这些改进使得PowerShell命令执行更加自动化和智能化，显著减少了用户需要手动处理的交互次数，同时保持了适当的安全控制。

### 用户信息管理

新增用户信息管理功能，可以：

- 记录和更新用户个人信息
- 在对话中自动应用用户信息，提供更个性化的交互体验
- 通过`update_user_information`函数更新用户信息文件中的特定条目

### 文件工具增强

文件操作工具集进行了功能扩展：

- 为文件读写操作添加了更健壮的错误处理
- 文件工具现在提供更清晰的分类和使用建议，引导用户选择最适合特定任务的工具
- 每个文件工具都配备了更详细的描述，说明其优势和推荐使用场景

---

## 安装说明

### 快速开始

1. 克隆项目仓库或下载源代码
2. 运行自动环境配置工具：
   ```bash
   python auto_setup.py
   ```
3. 启动系统：
   - 文本模式：`python deepseekAPI.py`
   - 语音模式：`python aaaa.py` 或双击 `start_voice_mode.bat`

### 手动配置

1. 安装依赖：
   ```bash
   pip install -r requirements.txt
   ```

2. 配置环境变量：
   - 创建`.env`文件，添加必要的API密钥：
   ```
   api_key=your_deepseek_api_key
   ```

3. 运行系统：
   - 文本模式：`python deepseekAPI.py`
   - 语音模式：`python aaaa.py`

---

## 许可证

仅供个人学习和研究使用

联系邮箱：1792491376@qq.com
