# Web搜索工具

本工具提供基于Bing搜索引擎的网页搜索和内容爬取功能，适用于AI agent获取网络信息。工具经过优化，支持关键词搜索、内容提取和智能筛选等功能。

## 特性

- **基于Bing搜索**: 使用Bing搜索引擎（无广告版本）进行关键词搜索
- **内容智能提取**: 自动识别并提取网页的主要内容，过滤无关元素
- **关键词筛选**: 支持通过关键词对搜索结果进行筛选
- **关键句提取**: 从网页中提取包含特定关键词的关键句子
- **网页元信息提取**: 提取网页的标题、描述、关键词等元信息
- **Agent优化**: 专为AI agent设计，提供结构化数据和摘要信息

## 安装

确保已安装以下依赖:
```
pip install requests beautifulsoup4
```

或直接更新requirements.txt后安装:
```
pip install -r requirements.txt
```

## 使用方法

### 1. 基本搜索

```python
from web_search_tool import web_search

# 执行搜索
results = web_search(
    query="人工智能最新发展", 
    num_results=5,
    filter_adult=True
)

# 输出搜索结果
print(results['summary'])
```

### 2. 获取网页内容

```python
from web_search_tool import fetch_webpage

# 获取指定URL的网页内容
webpage = fetch_webpage(
    url="https://example.com/article", 
    extract_keywords=["人工智能", "大模型"]
)

# 获取标题和内容
title = webpage['title']
content = webpage['content']
key_sentences = webpage['key_sentences']
```

### 3. 筛选搜索结果

```python
from web_search_tool import web_search, filter_search_results

# 先执行搜索
search_results = web_search("人工智能技术")

# 筛选包含特定关键词的结果
filtered_results = filter_search_results(
    results=search_results['results'],
    keywords=["大模型", "深度学习"],
    match_all=False  # 匹配任意关键词即可
)
```

## 工具注册（供Agent使用）

本工具已注册到工具注册表中，可以通过以下方式在agent中使用:

1. **web_search**: 执行网络搜索
```json
{
  "name": "web_search",
  "description": "【Web搜索工具】使用Bing搜索引擎搜索指定关键词，返回搜索结果列表",
  "parameters": {
    "query": "搜索关键词",
    "num_results": 5,
    "filter_adult": true
  }
}
```

2. **fetch_webpage**: 获取网页内容
```json
{
  "name": "fetch_webpage",
  "description": "【Web内容获取工具】抓取指定URL的网页内容",
  "parameters": {
    "url": "https://example.com/article",
    "extract_keywords": ["关键词1", "关键词2"]
  }
}
```

3. **filter_search_results**: 筛选搜索结果
```json
{
  "name": "filter_search_results",
  "description": "【搜索结果筛选工具】根据关键词筛选搜索结果",
  "parameters": {
    "results": [搜索结果列表],
    "keywords": ["关键词1", "关键词2"],
    "match_all": false
  }
}
```

## Agent使用示例

以下是AI agent调用这些工具的示例对话流程:

1. **用户**: "查一下最新的人工智能研究进展"

2. **Agent调用web_search工具**:
   ```
   工具: web_search
   参数: {"query": "最新人工智能研究进展", "num_results": 5}
   ```

3. **获取搜索结果后，Agent决定获取特定文章**:
   ```
   工具: fetch_webpage
   参数: {"url": "https://example.com/ai-research", "extract_keywords": ["大模型", "研究突破"]}
   ```

4. **Agent基于提取的关键句子回答用户**:
   "根据最新研究，人工智能领域最近有以下进展: [摘要内容]..."

## 高级用法

### 直接使用WebSearchTool类

如果需要更灵活的控制，可以直接使用WebSearchTool类:

```python
from web_search_tool import WebSearchTool

# 创建工具实例
search_tool = WebSearchTool()

# 自定义搜索
results = search_tool.search("关键词", num_results=10)

# 自定义内容提取
webpage = search_tool.fetch_webpage_content("https://example.com")
```

### 自定义结果处理

```python
# 提取关键句子
sentences = search_tool.extract_key_sentences(
    content=webpage["content"],
    keywords=["人工智能", "大模型"],
    max_sentences=5
)

# 生成自定义摘要
summary = search_tool.summarize_results(
    results=filtered_results,
    keywords=["人工智能"],
    detailed=True
)
```

## 错误处理

所有工具函数都返回包含status字段的字典:
- status="success": 操作成功
- status="error": 操作失败，error字段包含错误信息

建议在使用时检查状态码:

```python
result = web_search("查询关键词")
if result['status'] == 'success':
    # 处理结果
else:
    # 处理错误
    print(f"搜索失败: {result['error']}")
```

## 性能调优

如果需要为特定场景优化性能，可以调整以下参数:

1. **WebSearchTool类初始化参数**:
   - max_retries: 最大重试次数
   - timeout: 请求超时时间
   - delay_range: 请求间隔随机延迟范围

2. **搜索参数**:
   - num_results: 控制结果数量，权衡精度和速度

## 注意事项

1. 请遵守Bing搜索引擎的使用条款
2. 添加适当的请求延迟，避免频繁请求被封锁
3. 处理好网络异常和超时情况
4. 网页内容可能因网站结构变化而无法正确提取

## 测试

使用提供的测试脚本进行功能测试:

```
python test_web_search.py
``` 