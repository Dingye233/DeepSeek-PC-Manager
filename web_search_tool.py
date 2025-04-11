"""
Web搜索工具 - 基于博查API的网页搜索和内容爬取工具
该工具可以根据关键词搜索网页，提取搜索结果和快照信息，并可根据快照关键词筛选爬取特定网页内容
"""

import requests
from bs4 import BeautifulSoup
import re
import time
import random
from urllib.parse import quote_plus, urlparse, parse_qs
import logging
import json
from datetime import datetime
import os
import shutil
from dotenv import load_dotenv
import hashlib
import html

# 添加导入，用于保存图片和HTML文件
import pathlib
import uuid
import base64

# 配置日志
logging.basicConfig(level=logging.WARNING, format='%(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# 加载环境变量
load_dotenv()
BOCHAI_API_KEY = os.environ.get("web_search_key")

class WebSearchTool:
    """Web搜索工具类，用于搜索和爬取网页内容"""
    
    def __init__(self):
        """初始化搜索工具"""
        # 预定义多个User-Agent，随机使用
        self.user_agents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/96.0.4664.110 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/98.0.4758.102 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:97.0) Gecko/20100101 Firefox/97.0',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.2 Safari/605.1.15',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/99.0.4844.51 Safari/537.36 Edg/99.0.1150.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/101.0.4951.54 Safari/537.36',
            'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/100.0.4896.75 Safari/537.36'
        ]
        
        # 基础请求头
        self.base_headers = {
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'DNT': '1'  # Do Not Track
        }
        
        # 更新随机User-Agent
        self._update_headers()
        
        self.api_url = "https://api.bochaai.com/v1/web-search"
        self.ai_search_url = "https://api.bochaai.com/v1/ai-search"
        self.rerank_url = "https://api.bochaai.com/v1/rerank"
        self.api_key = BOCHAI_API_KEY
        
        self.timeout = 10
        self.cache = {}
    
    def _update_headers(self):
        """更新随机User-Agent和其他请求头"""
        headers = self.base_headers.copy()
        headers['User-Agent'] = random.choice(self.user_agents)
        self.headers = headers
    
    def _search_with_bochai_api(self, query, num_results=10):
        """
        使用博查API执行搜索
        
        参数:
            query (str): 搜索查询
            num_results (int): 要获取的结果数量
            
        返回:
            list: 搜索结果列表
        """
        logging.info(f"使用博查API搜索: {query}")
        results = []
        
        try:
            # 构建请求
            headers = {
                'Authorization': f'Bearer {self.api_key}',
                'Content-Type': 'application/json'
            }
            
            payload = {
                "query": query,
                "freshness": "noLimit",
                "summary": True,
                "count": min(num_results, 50),  # API最大支持50条结果
                "page": 1
            }
            
            # 发送请求
            response = requests.post(
                self.api_url,
                headers=headers,
                json=payload,
                timeout=self.timeout
            )
            
            # 检查响应
            if response.status_code != 200:
                logging.error(f"博查API请求失败: 状态码 {response.status_code}")
                return []
            
            # 解析响应
            data = response.json()
            if data.get("code") != 200:
                logging.error(f"博查API返回错误: {data.get('msg')}")
                return []
            
            # 提取搜索结果
            search_data = data.get("data", {})
            web_pages = search_data.get("webPages", {})
            web_results = web_pages.get("value", [])
            
            # 转换为标准格式
            for item in web_results:
                result = {
                    'title': item.get('name', ''),
                    'url': item.get('url', ''),
                    'description': item.get('snippet', ''),
                    'summary': item.get('summary', ''),
                    'site_name': item.get('siteName', ''),
                    'favicon': item.get('siteIcon', ''),
                    'date': item.get('datePublished', ''),
                    'source': 'BochaiAPI'
                }
                results.append(result)
            
            # 添加图片结果
            images = search_data.get("images", {})
            image_results = images.get("value", [])
            for item in image_results:
                # 只添加有效的图片结果
                if item.get('contentUrl') and item.get('hostPageUrl'):
                    result = {
                        'title': item.get('name', '图片结果'),
                        'url': item.get('hostPageUrl', ''),
                        'image_url': item.get('contentUrl', ''),
                        'thumbnail': item.get('thumbnailUrl', ''),
                        'width': item.get('width', 0),
                        'height': item.get('height', 0),
                        'type': 'image',
                        'source': 'BochaiAPI'
                    }
                    results.append(result)
            
            logging.info(f"博查API搜索成功: 找到 {len(results)} 条结果")
            
        except Exception as e:
            logging.error(f"博查API搜索出错: {str(e)}")
            
        return results
    
    def _search_with_ai_search(self, query, num_results=5, answer=True, stream=False, summary=False):
        """
        使用博查AI Search API执行搜索
        
        Args:
            query (str): 搜索查询
            num_results (int): 要返回的结果数量
            answer (bool): 是否生成AI回答
            stream (bool): 是否使用流式输出
            summary (bool): 是否创建摘要
            
        Returns:
            dict: 搜索结果或错误信息
        """
        import os
        import json
        import requests
        import logging
        import time
        from dotenv import load_dotenv
        
        # 加载环境变量获取API密钥
        load_dotenv()
        api_key = os.getenv("web_search_key")
        
        if not api_key:
            return {
                "status": "error",
                "error": "未找到API密钥。请在.env文件中设置web_search_key变量。"
            }
        
        logger = logging.getLogger("deepseek.web_search")
        logger.info(f"使用博查AI Search API搜索: {query}")
        
        # 构建请求URL和参数
        url = "https://bocha.ai/ai/api/search"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}"
        }
        
        payload = {
            "query": query,
            "count": num_results,
            "answer": "true" if answer else "false",
            "stream": "true" if stream else "false",
            "mkt": "zh-CN"
        }
        
        if self.filter_adult:
            payload["safeSearch"] = "Strict"
        
        # 执行API请求
        try:
            start_time = time.time()
            response = requests.post(url, headers=headers, json=payload, timeout=30)
            elapsed_time = time.time() - start_time
            
            logger.info(f"博查API响应时间: {elapsed_time:.2f}秒")
            
            # 检查响应状态
            if response.status_code != 200:
                error_msg = f"API请求失败，状态码: {response.status_code}"
                try:
                    error_data = response.json()
                    if "error" in error_data:
                        error_msg += f", 错误: {error_data['error']}"
                except:
                    error_msg += f", 响应: {response.text[:200]}"
                    
                logger.error(error_msg)
                return {
                    "status": "error",
                    "error": error_msg
                }
            
            # 解析JSON响应
            try:
                result_data = response.json()
                logger.info(f"成功获取搜索结果")
                
                # 检查结果是否有效
                if not isinstance(result_data, dict):
                    return {
                        "status": "error", 
                        "error": "API返回的数据格式无效"
                    }
                    
                # 记录结果统计
                stats = []
                if "webPages" in result_data and "value" in result_data["webPages"]:
                    stats.append(f"网页: {len(result_data['webPages']['value'])}")
                    
                if "images" in result_data and "value" in result_data["images"]:
                    stats.append(f"图片: {len(result_data['images']['value'])}")
                    
                if "modalCards" in result_data:
                    stats.append(f"模态卡片: {len(result_data['modalCards'])}")
                    
                if "answer" in result_data:
                    stats.append("AI回答: 是")
                    
                logger.info(f"搜索结果统计: {', '.join(stats)}")
                
                return {
                    "status": "success",
                    "data": result_data
                }
                
            except json.JSONDecodeError as e:
                error_msg = f"解析API响应JSON失败: {str(e)}"
                logger.error(error_msg)
                logger.error(f"响应内容: {response.text[:500]}")
                return {
                    "status": "error",
                    "error": error_msg
                }
                
        except requests.RequestException as e:
            error_msg = f"请求博查API时发生错误: {str(e)}"
            logger.error(error_msg)
            return {
                "status": "error",
                "error": error_msg
            }
        except Exception as e:
            error_msg = f"执行搜索时发生未知错误: {str(e)}"
            logger.error(error_msg)
            return {
                "status": "error",
                "error": error_msg
            }
    
    def _rerank_documents(self, query, documents, model="gte-rerank", top_n=None, return_documents=True):
        """
        使用博查Semantic Reranker API对文档进行排序
        
        参数:
            query (str): 查询字符串
            documents (list): 要排序的文档列表
            model (str): 使用的模型
            top_n (int): 返回排名前n的结果
            return_documents (bool): 是否返回文档内容
            
        返回:
            dict: 包含排序结果的字典
        """
        logging.info(f"使用博查Semantic Reranker API排序文档")
        
        try:
            # 构建请求
            headers = {
                'Authorization': f'Bearer {self.api_key}',
                'Content-Type': 'application/json'
            }
            
            payload = {
                "model": model,
                "query": query,
                "documents": documents,
                "return_documents": return_documents
            }
            
            if top_n is not None:
                payload["top_n"] = top_n
            
            # 发送请求
            response = requests.post(
                self.rerank_url,
                headers=headers,
                json=payload,
                timeout=self.timeout
            )
            
            # 检查响应
            if response.status_code != 200:
                logging.error(f"博查Semantic Reranker API请求失败: 状态码 {response.status_code}")
                return {"status": "error", "error": f"API请求失败: {response.status_code}"}
            
            # 解析响应
            data = response.json()
            if data.get("code") != 200:
                logging.error(f"博查Semantic Reranker API返回错误: {data.get('msg')}")
                return {"status": "error", "error": data.get("msg", "未知错误")}
            
            logging.info(f"博查Semantic Reranker API排序成功")
            return {
                "status": "success",
                "data": data.get("data", {})
            }
            
        except Exception as e:
            logging.error(f"博查Semantic Reranker API出错: {str(e)}")
            return {"status": "error", "error": str(e)}

# 搜索工具函数接口 - 注册到工具注册表使用
def web_search(query, num_results=5, filter_adult=False, keywords=None, sort_by_relevance=True, match_all_keywords=False):
    """
    执行网络搜索并返回结果
    
    参数:
        query (str): 搜索关键词
        num_results (int): 返回结果数量
        filter_adult (bool): 是否过滤成人内容
        keywords (list): 可选的关键词列表，用于过滤结果
        sort_by_relevance (bool): 是否按相关性排序结果
        match_all_keywords (bool): 是否要求匹配所有关键词
        
    返回:
        dict: 包含搜索结果的字典
    """
    start_time = time.time()
    logger.info(f"开始执行网络搜索，查询: '{query}'，请求 {num_results} 个结果")
    
    # 标准化查询参数
    if isinstance(query, str):
        query = query.strip()
    else:
        return {
            "status": "error",
            "error": "查询必须是字符串类型",
            "results": [],
            "results_count": 0,
            "summary": "搜索失败: 无效的查询类型",
            "message": "搜索失败: 查询参数必须是字符串",
            "elapsed_time": "0.00秒"
        }
    
    if not query:
        return {
            "status": "error",
            "error": "查询不能为空",
            "results": [],
            "results_count": 0,
            "summary": "搜索失败: 查询内容为空",
            "message": "请提供搜索关键词",
            "elapsed_time": "0.00秒"
        }
    
    # 确保keywords是列表类型    
    if keywords and isinstance(keywords, str):
        keywords = [keywords]
        
    # 限制num_results在合理范围
    num_results = max(1, min(50, num_results))
    
    try:
        # 创建搜索工具实例
        search_tool = WebSearchTool()
        
        # 记录搜索已经开始
        logger.info(f"搜索开始: '{query}'")
        
        # 执行搜索
        results = search_tool._search_with_bochai_api(query, num_results=num_results)
        
        # 如果有关键词，则进行过滤
        if keywords and results:
            filtered_results = []
            for result in results:
                # 获取搜索结果文本内容
                result_text = (
                    (result.get('title', '') or '') + ' ' + 
                    (result.get('description', '') or '') + ' ' + 
                    (result.get('summary', '') or '')
                ).lower()
                
                # 检查关键词匹配
                matches = []
                for keyword in keywords:
                    keyword_lower = keyword.lower()
                    matches.append(keyword_lower in result_text)
                
                # 根据匹配策略决定是否保留结果
                if match_all_keywords and all(matches):
                    filtered_results.append(result)
                elif not match_all_keywords and any(matches):
                    filtered_results.append(result)
            
            results = filtered_results
            logger.info(f"关键词过滤后剩余 {len(results)} 个结果")
        
        # 根据相关性排序（如果需要）
        if sort_by_relevance and results and len(results) > 1:
            try:
                # 准备要排序的文档
                docs_to_rerank = []
                for result in results:
                    text = (result.get('description', '') or result.get('summary', '') or result.get('title', ''))
                    if text:
                        docs_to_rerank.append(text)
                
                if docs_to_rerank:
                    # 执行语义排序
                    rerank_result = search_tool._rerank_documents(
                        query=query,
                        documents=docs_to_rerank,
                        top_n=len(docs_to_rerank)
                    )
                    
                    if rerank_result.get("status") == "success":
                        reranked_data = rerank_result.get("data", {})
                        reranked_results = reranked_data.get("results", [])
                        
                        if reranked_results:
                            # 根据排序结果重新排列原始结果
                            sorted_results = []
                            for reranked_item in reranked_results:
                                index = reranked_item.get("index")
                                if index is not None and 0 <= index < len(results):
                                    sorted_results.append(results[index])
                            
                            if sorted_results:
                                results = sorted_results
                                logger.info("搜索结果已按相关性排序")
            except Exception as e:
                logger.error(f"排序搜索结果时出错: {str(e)}")
                # 如果排序失败，继续使用原始顺序
        
        elapsed_time = time.time() - start_time
        logger.info(f"搜索完成，用时: {elapsed_time:.2f}秒，找到结果数: {len(results)}")
        
        # 根据结果生成合适的消息
        if results:
            message = f"找到 {len(results)} 个搜索结果"
            if keywords:
                message += f"，已根据 {'所有' if match_all_keywords else '任一'} 关键词 ({', '.join(keywords)}) 进行过滤"
            if sort_by_relevance:
                message += "，并按相关性排序"
            
            # 整理搜索结果为摘要
            summary_items = []
            for i, result in enumerate(results[:num_results]):
                title = result.get('title', '无标题')
                url = result.get('url', '')
                description = result.get('description', '') or result.get('summary', '')
                
                if len(description) > 200:
                    description = description[:197] + "..."
                
                summary_item = f"{i+1}. **{title}**\n   {url}\n   {description}"
                summary_items.append(summary_item)
            
            summary = "\n\n".join(summary_items)
        else:
            message = "未找到相关搜索结果，请尝试使用不同的关键词"
            summary = f"抱歉，我们无法找到与\"{query}\"相关的搜索结果。可能的原因：\n1. 关键词过于专业或不常见\n2. 搜索引擎可能暂时无法访问\n3. 可能需要更具体或更一般的关键词\n\n建议：\n- 尝试不同的关键词或短语\n- 使用更通用的术语\n- 检查关键词拼写"
        
        return {
            "status": "success",
            "query": query,
            "results_count": len(results),
            "results": results,
            "summary": summary,
            "message": message,
            "keywords": keywords,
            "match_all_keywords": match_all_keywords,
            "sort_by_relevance": sort_by_relevance,
            "elapsed_time": f"{elapsed_time:.2f}秒"
        }
        
    except Exception as e:
        # 计算已经过时间
        elapsed_time = time.time() - start_time
        error_msg = f"执行网络搜索时出错: {str(e)}"
        logger.error(error_msg)
        
        return {
            "status": "error",
            "query": query,
            "error": error_msg,
            "error_type": type(e).__name__,
            "results": [],
            "results_count": 0,
            "summary": f"搜索\"{query}\"时遇到了问题。这可能是由于网络连接问题、搜索服务暂时不可用或关键词格式问题导致的。\n\n建议：\n- 稍后重试\n- 使用更简单的关键词\n- 检查网络连接",
            "message": "搜索失败，请稍后重试",
            "elapsed_time": f"{elapsed_time:.2f}秒"
        }

def ai_search(query, num_results=5, filter_adult=False, answer=True, stream=False):
    """
    执行AI增强型Web搜索，可获取多种格式的结果并保存到本地
    
    Args:
        query (str): 搜索查询，可以是：
            - 一般性查询（如"Windows蓝屏解决方法"）
            - 针对特定图片的查询（如"奥迪RS7高清图片"、"苹果新品发布会图片"）
            - 针对特定模态卡的查询（如"上海天气"、"比特币汇率"、"周杰伦星座"）
        num_results (int): 要返回的结果数量，建议图片和模态卡查询使用3-5
        filter_adult (bool): 是否过滤成人内容
        answer (bool): 是否生成AI回答摘要
        stream (bool): 是否使用流式输出（仅影响AI回答，不影响图片和模态卡）
    
    Returns:
        str: 包含搜索结果摘要、下载的图片和模态卡路径的字符串
             对于图片查询会下载并保存图片到本地
             对于模态卡会将结构化数据保存为HTML文件
    """
    import os
    import time
    import json
    import requests
    import logging
    import shutil
    import html
    from urllib.parse import urlparse, quote
    from pathlib import Path
    from datetime import datetime
    
    logger = logging.getLogger("deepseek.web_search")
    
    # 创建保存搜索结果的文件夹
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_query = quote(query[:50], safe='')  # 使查询安全用于文件名
    base_dir = Path("search_return") / f"{timestamp}_{safe_query}"
    
    # 创建目录结构
    image_dir = base_dir / "images"
    card_dir = base_dir / "cards"
    web_dir = base_dir / "webpages"
    
    os.makedirs(image_dir, exist_ok=True)
    os.makedirs(card_dir, exist_ok=True)
    os.makedirs(web_dir, exist_ok=True)
    
    logger.info(f"创建目录用于保存搜索结果: {base_dir}")
    
    # 验证查询
    if not query or not query.strip():
        return "错误: 搜索查询不能为空"
    
    # 执行搜索
    tool = WebSearchTool()
    tool.filter_adult = filter_adult  # 添加过滤器属性
    search_result = tool._search_with_ai_search(query, num_results=num_results, answer=answer, stream=stream)
    
    if search_result["status"] != "success":
        return f"搜索失败: {search_result.get('error', '未知错误')}"
    
    result_data = search_result["data"]
    saved_images = 0
    saved_cards = 0
    saved_webpages = 0
    
    # 保存图片结果
    if "images" in result_data and "value" in result_data["images"]:
        images = result_data["images"]["value"]
        for i, img in enumerate(images):
            if i >= num_results:
                break
                
            try:
                img_url = img.get("contentUrl")
                if not img_url:
                    continue
                    
                # 下载图片
                img_response = requests.get(img_url, timeout=15, stream=True, headers={
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/96.0.4664.110 Safari/537.36'
                })
                
                if img_response.status_code == 200:
                    # 从Content-Type或URL确定扩展名
                    content_type = img_response.headers.get('Content-Type', '')
                    extension = '.jpg'  # 默认扩展名
                    
                    if 'png' in content_type.lower():
                        extension = '.png'
                    elif 'gif' in content_type.lower():
                        extension = '.gif'
                    elif 'jpeg' in content_type.lower() or 'jpg' in content_type.lower():
                        extension = '.jpg'
                    elif 'webp' in content_type.lower():
                        extension = '.webp'
                    elif 'bmp' in content_type.lower():
                        extension = '.bmp'
                    else:
                        # 尝试从URL获取扩展名
                        parsed_url = urlparse(img_url)
                        path = parsed_url.path.lower()
                        if path.endswith('.png'):
                            extension = '.png'
                        elif path.endswith('.gif'):
                            extension = '.gif'
                        elif path.endswith('.jpg') or path.endswith('.jpeg'):
                            extension = '.jpg'
                        elif path.endswith('.webp'):
                            extension = '.webp'
                        elif path.endswith('.bmp'):
                            extension = '.bmp'
                    
                    img_filename = f"image_{i+1}{extension}"
                    img_path = os.path.join(image_dir, img_filename)
                    
                    # 验证图片有效性
                    try:
                        from PIL import Image
                        from io import BytesIO
                        
                        # 在保存前验证图片
                        image_bytes = img_response.content
                        img = Image.open(BytesIO(image_bytes))
                        img.verify()  # 验证图片完整性
                        
                        # 图片验证通过后保存
                        with open(img_path, 'wb') as f:
                            f.write(image_bytes)
                        
                        saved_images += 1
                        logger.info(f"已保存并验证图片: {img_path}")
                    except Exception as img_error:
                        logger.error(f"图片验证失败: {str(img_error)}")
                        continue
                else:
                    logger.warning(f"下载图片失败，状态码: {img_response.status_code}")
            except Exception as e:
                logger.error(f"保存图片时出错: {str(e)}")
    
    # 保存网页摘要
    try:
        if "webPages" in result_data and "value" in result_data["webPages"]:
            webpages = result_data["webPages"]["value"]
            for i, page in enumerate(webpages):
                if i >= num_results:
                    break
                    
                try:
                    page_filename = f"webpage_{i+1}.html"
                    page_path = os.path.join(web_dir, page_filename)
                    
                    # 创建简单的HTML页面显示网页信息
                    with open(page_path, 'w', encoding='utf-8') as f:
                        title = html.escape(page.get("name", "无标题"))
                        url = html.escape(page.get("url", "#"))
                        snippet = html.escape(page.get("snippet", "无描述"))
                        
                        html_content = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>{title}</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; line-height: 1.6; }}
        h1 {{ color: #2c3e50; }}
        .url {{ color: #3498db; }}
        .snippet {{ background-color: #f9f9f9; padding: 15px; border-left: 4px solid #2ecc71; }}
    </style>
</head>
<body>
    <h1>{title}</h1>
    <p class="url"><a href="{url}" target="_blank">{url}</a></p>
    <div class="snippet">{snippet}</div>
</body>
</html>"""
                        f.write(html_content)
                    
                    saved_webpages += 1
                    logger.info(f"已保存网页摘要: {page_path}")
                except Exception as e:
                    logger.error(f"保存网页摘要时出错: {str(e)}")
    except Exception as e:
        logger.error(f"处理网页结果时出错: {str(e)}")
    
    # 保存模态卡片
    if "modalCards" in result_data:
        cards = result_data["modalCards"]
        for i, card in enumerate(cards):
            try:
                card_filename = f"card_{i+1}.html"
                card_path = os.path.join(card_dir, card_filename)
                
                # 为模态卡片创建可视化HTML
                with open(card_path, 'w', encoding='utf-8') as f:
                    card_type = card.get("cardType", "未知类型")
                    card_title = html.escape(card.get("title", "无标题"))
                    
                    # 创建Card的HTML表示
                    html_content = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>{card_title}</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; line-height: 1.6; }}
        h1 {{ color: #2c3e50; }}
        .card {{ background-color: #f9f9f9; padding: 20px; border-radius: 5px; box-shadow: 0 2px 5px rgba(0,0,0,0.1); }}
        .card-type {{ color: #3498db; margin-bottom: 10px; }}
        .property {{ margin: 10px 0; }}
        .property-name {{ font-weight: bold; color: #16a085; }}
        pre {{ background-color: #f0f0f0; padding: 10px; border-radius: 3px; overflow-x: auto; }}
    </style>
</head>
<body>
    <h1>{card_title}</h1>
    <div class="card">
        <div class="card-type">类型: {card_type}</div>
        <pre>{html.escape(json.dumps(card, ensure_ascii=False, indent=2))}</pre>
    </div>
</body>
</html>"""
                    f.write(html_content)
                
                saved_cards += 1
                logger.info(f"已保存模态卡片: {card_path}")
            except Exception as e:
                logger.error(f"保存模态卡片时出错: {str(e)}")
    
    # 创建索引页面
    index_path = os.path.join(base_dir, "index.html")
    try:
        with open(index_path, 'w', encoding='utf-8') as f:
            # 提取AI回答和后续问题
            ai_answer = ""
            follow_up_questions = []
            
            if "answer" in result_data:
                answer_data = result_data["answer"]
                ai_answer = html.escape(answer_data.get("text", ""))
                
                if "followupQuestions" in answer_data:
                    follow_up_questions = [html.escape(q) for q in answer_data.get("followupQuestions", [])]
            
            # 构建索引HTML
            sections = []
            
            # 添加AI回答部分
            if ai_answer:
                sections.append(f"""
<section class="search-section">
    <h2>AI回答</h2>
    <div class="answer-card">
        <p>{ai_answer}</p>
    </div>
</section>""")
            
            # 添加后续问题部分
            if follow_up_questions:
                questions_html = "\n".join([f"<li>{q}</li>" for q in follow_up_questions])
                sections.append(f"""
<section class="search-section">
    <h2>后续问题</h2>
    <ul class="question-list">
        {questions_html}
    </ul>
</section>""")
            
            # 添加图片部分
            if saved_images > 0:
                image_links = []
                for i in range(1, saved_images + 1):
                    for ext in ['.jpg', '.png', '.gif', '.webp', '.bmp']:
                        img_path = f"images/image_{i}{ext}"
                        full_path = os.path.join(base_dir, img_path)
                        if os.path.exists(full_path):
                            image_links.append(f'<div class="image-item"><a href="{img_path}" target="_blank"><img src="{img_path}" alt="搜索结果图片 {i}"></a></div>')
                            break
                
                images_html = "\n".join(image_links)
                sections.append(f"""
<section class="search-section">
    <h2>图片结果 ({saved_images})</h2>
    <div class="image-grid">
        {images_html}
    </div>
</section>""")
            
            # 添加网页部分
            if saved_webpages > 0:
                webpage_links = []
                for i in range(1, saved_webpages + 1):
                    webpage_path = f"webpages/webpage_{i}.html"
                    webpage_links.append(f'<li><a href="{webpage_path}" target="_blank">网页结果 {i}</a></li>')
                
                webpages_html = "\n".join(webpage_links)
                sections.append(f"""
<section class="search-section">
    <h2>网页结果 ({saved_webpages})</h2>
    <ul class="webpage-list">
        {webpages_html}
    </ul>
</section>""")
            
            # 添加模态卡片部分
            if saved_cards > 0:
                card_links = []
                for i in range(1, saved_cards + 1):
                    card_path = f"cards/card_{i}.html"
                    card_links.append(f'<li><a href="{card_path}" target="_blank">模态卡片 {i}</a></li>')
                
                cards_html = "\n".join(card_links)
                sections.append(f"""
<section class="search-section">
    <h2>模态卡片 ({saved_cards})</h2>
    <ul class="card-list">
        {cards_html}
    </ul>
</section>""")
            
            # 合并所有部分
            all_sections = "\n".join(sections)
            
            # 完整HTML页面
            html_content = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>搜索结果: {html.escape(query)}</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 0; padding: 20px; line-height: 1.6; }}
        h1 {{ color: #2c3e50; text-align: center; margin-bottom: 30px; }}
        h2 {{ color: #3498db; border-bottom: 1px solid #e0e0e0; padding-bottom: 10px; }}
        .search-section {{ margin-bottom: 40px; }}
        .answer-card {{ background-color: #f5f5f5; padding: 20px; border-radius: 5px; border-left: 5px solid #2ecc71; }}
        .question-list {{ list-style-type: disc; padding-left: 20px; }}
        .question-list li {{ margin-bottom: 10px; color: #16a085; }}
        .image-grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 15px; }}
        .image-item img {{ max-width: 100%; height: auto; border-radius: 3px; box-shadow: 0 2px 5px rgba(0,0,0,0.1); }}
        .webpage-list, .card-list {{ list-style-type: none; padding-left: 0; }}
        .webpage-list li, .card-list li {{ margin-bottom: 10px; }}
        .webpage-list a, .card-list a {{ color: #3498db; text-decoration: none; padding: 8px; display: inline-block; 
                                        border: 1px solid #e0e0e0; border-radius: 3px; transition: background-color 0.2s; }}
        .webpage-list a:hover, .card-list a:hover {{ background-color: #f0f0f0; }}
        .query-info {{ color: #7f8c8d; text-align: center; margin-bottom: 30px; }}
    </style>
</head>
<body>
    <h1>搜索结果</h1>
    <p class="query-info">查询: "{html.escape(query)}" | 时间: {timestamp.replace("_", " ")}</p>
    
    {all_sections}
    
    <footer style="text-align: center; margin-top: 50px; color: #7f8c8d; font-size: 0.9em;">
        搜索结果由博查AI提供
    </footer>
</body>
</html>"""
            f.write(html_content)
        
        logger.info(f"已创建搜索结果索引页: {index_path}")
    except Exception as e:
        logger.error(f"创建索引页面时出错: {str(e)}")
    
    # 返回摘要信息
    total_items = saved_images + saved_cards + saved_webpages
    result = f"已保存{total_items}个搜索结果到 {base_dir} 文件夹中。"
    
    if saved_images > 0:
        result += f" 图片: {saved_images}个。"
    if saved_webpages > 0:
        result += f" 网页: {saved_webpages}个。"
    if saved_cards > 0:
        result += f" 模态卡片: {saved_cards}个。"
        
    if ai_answer:
        result += f"\n\nAI回答:\n{ai_answer}"
        
    result += f"\n\n可以打开索引文件查看完整结果: {index_path}"
    
    return result

def semantic_rerank(query, documents, model="gte-rerank", top_n=None):
    """
    使用博查Semantic Reranker API对文档进行排序
    
    参数:
        query (str): 查询字符串
        documents (list): 要排序的文档列表，每个文档是一个字符串或包含"text"字段的字典
        model (str): 使用的模型，默认为"gte-rerank"
        top_n (int): 返回排名前n的结果，默认返回所有结果
        
    返回:
        dict: 包含排序结果的字典
    """
    start_time = time.time()
    logger.info(f"开始执行语义排序，查询: '{query}'")
    
    # 验证参数
    if not query or not isinstance(query, str):
            return {
                "status": "error",
            "error": "查询必须是非空字符串",
            "message": "语义排序失败: 无效的查询参数",
            "elapsed_time": "0.00秒"
        }
    
    if not documents or not isinstance(documents, list) or len(documents) == 0:
            return {
                "status": "error",
            "error": "文档列表不能为空",
            "message": "语义排序失败: 未提供待排序文档",
            "elapsed_time": "0.00秒"
        }
    
    # 标准化文档格式
    formatted_documents = []
    for doc in documents:
        if isinstance(doc, str):
            formatted_documents.append({"text": doc})
        elif isinstance(doc, dict) and "text" in doc:
            formatted_documents.append({"text": doc["text"]})
        else:
            return {
                "status": "error",
                "error": "文档格式不正确，每个文档应该是字符串或包含'text'字段的字典",
                "message": "语义排序失败: 文档格式错误",
                "elapsed_time": "0.00秒"
            }
    
    try:
        # 创建搜索工具实例
        search_tool = WebSearchTool()
        
        # 执行语义排序
        rerank_result = search_tool._rerank_documents(
            query=query,
            documents=formatted_documents,
            model=model,
            top_n=top_n,
            return_documents=True
        )
        
        elapsed_time = time.time() - start_time
        
        if rerank_result["status"] != "success":
            return {
                "status": "error",
                "query": query,
                "error": rerank_result.get("error", "语义排序失败"),
                "message": "语义排序失败，请稍后重试",
                "elapsed_time": f"{elapsed_time:.2f}秒"
            }
        
        # 处理排序结果
        rerank_data = rerank_result["data"]
        model_used = rerank_data.get("model", model)
        results = rerank_data.get("results", [])
        
        # 整理排序结果
        ranked_documents = []
        for result in results:
            ranked_documents.append({
                "document": result.get("document", {}).get("text", ""),
                "relevance_score": result.get("relevance_score", 0),
                "index": result.get("index", -1)
            })
        
        # 生成摘要
        summary_items = []
        for i, doc in enumerate(ranked_documents):
            score = doc["relevance_score"]
            text = doc["document"]
            
            if len(text) > 200:
                text = text[:197] + "..."
            
            summary_item = f"{i+1}. 相关度: {score:.4f}\n   {text}"
            summary_items.append(summary_item)
        
        summary = "\n\n".join(summary_items)
        
        return {
            "status": "success",
            "query": query,
            "model": model_used,
            "ranked_documents": ranked_documents,
            "results_count": len(ranked_documents),
            "summary": summary,
            "message": f"语义排序完成，使用模型 {model_used}，已对 {len(documents)} 个文档按相关性排序",
            "elapsed_time": f"{elapsed_time:.2f}秒"
        }
        
    except Exception as e:
        # 计算已经过时间
        elapsed_time = time.time() - start_time
        error_msg = f"执行语义排序时出错: {str(e)}"
        logger.error(error_msg)
        
        return {
            "status": "error",
            "query": query,
            "error": error_msg,
            "error_type": type(e).__name__,
            "message": "语义排序失败，请稍后重试",
            "elapsed_time": f"{elapsed_time:.2f}秒"
        } 