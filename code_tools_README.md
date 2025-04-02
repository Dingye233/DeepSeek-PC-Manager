# 代码工具 (Code Tools)

这是一个为大型语言模型(LLM)设计的代码生成和管理工具集，允许模型直接生成和操作代码文件，而无需使用PowerShell命令。

## 功能特点

- **写入代码文件**：直接将代码写入指定文件，支持所有编程语言
- **验证Python代码**：检查Python代码语法是否正确
- **创建Python模块**：自动生成包含多个函数的Python模块
- **追加代码内容**：向现有文件追加内容
- **读取代码文件**：读取指定文件的内容

## 集成工具

这些工具已集成到以下文件中：
- `aaaa.py` - 支持语音交互的完整版本
- `deepseekAPI.py` - 仅支持文本交互的基础版本

## 如何使用

当用户请求AI编写或修改代码时，AI可以直接调用相应的工具函数，无需使用PowerShell命令，避免了因命令执行而可能产生的错误。

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

## 示例

参见 `code_tools_example.py` 文件，其中包含了所有工具的使用示例。

## 优势

1. **安全性**：直接操作文件，避免通过shell执行命令可能带来的风险
2. **跨平台**：不依赖特定平台的命令行工具，可在任何支持Python的环境运行
3. **错误处理**：提供清晰的错误信息和处理机制，方便调试
4. **语法验证**：在写入前验证代码语法，减少错误

## 文件结构

- `code_generator.py` - 核心功能实现
- `code_tools.py` - 工具函数接口层
- `code_tools_example.py` - 使用示例
- `code_tools_README.md` - 使用说明文档

## 注意事项

- 默认编码为UTF-8
- 写入文件时，如果目录不存在会自动创建
- 验证功能仅支持Python代码 