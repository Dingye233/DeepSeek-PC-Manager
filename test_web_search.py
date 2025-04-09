"""
Web搜索工具测试脚本
测试搜索、内容获取和关键词筛选等功能
"""

import json
from web_search_tool import WebSearchTool, web_search, fetch_webpage, filter_search_results

def print_json(obj):
    """美化打印JSON对象"""
    print(json.dumps(obj, ensure_ascii=False, indent=2))

def test_basic_search():
    """测试基本搜索功能"""
    print("=== 测试基本搜索功能 ===")
    
    query = "人工智能最新发展"
    results = web_search(query, num_results=3)
    
    print(f"查询: {query}")
    print(f"状态: {results['status']}")
    print(f"结果数量: {results['results_count']}")
    print("\n搜索结果摘要:")
    print(results['summary'])
    
    return results

def test_webpage_fetch():
    """测试网页内容获取功能"""
    print("\n=== 测试网页内容获取功能 ===")
    
    # 从上一步搜索结果中获取第一个URL
    search_results = test_basic_search()
    if search_results['status'] != 'success' or not search_results['results']:
        print("搜索结果为空，无法测试网页获取")
        return
    
    url = search_results['results'][0]['url']
    print(f"获取网页: {url}")
    
    # 提取关键词测试
    extract_keywords = ["智能", "发展", "技术"]
    result = fetch_webpage(url, extract_keywords=extract_keywords)
    
    print(f"状态: {result['status']}")
    print(f"标题: {result['title']}")
    
    # 打印元信息
    print("\n元信息:")
    for key, value in result.get('meta_info', {}).items():
        print(f"  {key}: {value}")
    
    # 打印关键句子
    print("\n关键句子:")
    for i, sentence in enumerate(result.get('key_sentences', []), 1):
        if len(sentence) > 100:
            sentence = sentence[:100] + "..."
        print(f"  {i}. {sentence}")
    
    # 打印内容片段
    content = result.get('content', '')
    if content:
        preview = content[:200] + "..." if len(content) > 200 else content
        print("\n内容预览:")
        print(preview)
    
    return result

def test_filter_results():
    """测试结果筛选功能"""
    print("\n=== 测试结果筛选功能 ===")
    
    # 先执行搜索
    search_results = test_basic_search()
    if search_results['status'] != 'success' or not search_results['results']:
        print("搜索结果为空，无法测试筛选功能")
        return
    
    # 定义筛选关键词
    filter_keys = ["大模型", "深度学习"]
    print(f"筛选关键词: {filter_keys}")
    
    # 筛选结果
    filtered = filter_search_results(search_results['results'], filter_keys)
    
    print(f"状态: {filtered['status']}")
    print(f"筛选前结果数: {len(search_results['results'])}")
    print(f"筛选后结果数: {filtered['results_count']}")
    
    # 打印筛选结果摘要
    if filtered['results']:
        print("\n筛选后结果摘要:")
        print(filtered['summary'])
    else:
        print("\n没有匹配的结果")
    
    return filtered

def test_keyword_search():
    """测试关键词搜索功能"""
    print("\n=== 测试关键词搜索功能 ===")
    
    query = "人工智能应用"
    keywords = ["医疗", "教育"]
    
    print(f"查询: {query}")
    print(f"关键词: {keywords}")
    print(f"匹配方式: 任一关键词")
    
    # 任一关键词匹配
    results_any = web_search(
        query=query, 
        num_results=5, 
        keywords=keywords, 
        match_all_keywords=False
    )
    
    print(f"状态: {results_any['status']}")
    print(f"任一关键词匹配结果数: {results_any['results_count']}")
    if results_any['results_count'] > 0:
        print("\n任一关键词匹配结果摘要:")
        print(results_any['summary'])
    else:
        print("未找到匹配任一关键词的结果")
    
    # 所有关键词匹配
    print("\n匹配方式: 所有关键词")
    results_all = web_search(
        query=query, 
        num_results=5, 
        keywords=keywords, 
        match_all_keywords=True
    )
    
    print(f"状态: {results_all['status']}")
    print(f"所有关键词匹配结果数: {results_all['results_count']}")
    if results_all['results_count'] > 0:
        print("\n所有关键词匹配结果摘要:")
        print(results_all['summary'])
    else:
        print("未找到匹配所有关键词的结果")
    
    return {
        "any_match": results_any,
        "all_match": results_all
    }

def performance_test():
    """性能测试"""
    print("\n=== 性能测试 ===")
    
    import time
    
    start_time = time.time()
    
    # 创建搜索工具实例
    search_tool = WebSearchTool()
    
    # 执行搜索
    query = "python 编程最佳实践"
    print(f"执行搜索: {query}")
    
    results = search_tool.search(query, num_results=5)
    
    # 测量搜索时间
    search_time = time.time() - start_time
    print(f"搜索用时: {search_time:.2f}秒")
    
    # 如果有结果，获取第一个网页内容
    if results:
        start_time = time.time()
        url = results[0]['url']
        print(f"获取网页: {url}")
        
        webpage = search_tool.fetch_webpage_content(url)
        
        fetch_time = time.time() - start_time
        print(f"获取网页用时: {fetch_time:.2f}秒")
    
    return {
        "search_time": search_time,
        "fetch_time": fetch_time if results else None
    }

def main():
    """主测试函数"""
    print("开始Web搜索工具测试...\n")
    
    try:
        # 1. 基本搜索测试
        test_basic_search()
        
        # 2. 网页内容获取测试
        test_webpage_fetch()
        
        # 3. 结果筛选测试
        test_filter_results()
        
        # 4. 关键词搜索测试
        test_keyword_search()
        
        # 5. 性能测试
        performance_test()
        
        print("\n测试完成!")
        
    except Exception as e:
        print(f"\n测试过程中出错: {str(e)}")

if __name__ == "__main__":
    main() 