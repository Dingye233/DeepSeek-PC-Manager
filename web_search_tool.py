"""
Web搜索工具 - 基于Bing搜索引擎的网页搜索和内容爬取工具
该工具可以根据关键词搜索网页，提取搜索结果和快照信息，并可根据快照关键词筛选爬取特定网页内容
"""

import requests
from bs4 import BeautifulSoup
import re
import time
import random
from urllib.parse import quote_plus, urlparse, parse_qs
import logging
import concurrent.futures
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import json
from functools import lru_cache
import html2text
import threading
from datetime import datetime

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

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
        
        # 初始化空Cookie
        self.cookies = {}
        
        # 更新随机User-Agent
        self._update_headers()
        
        self.search_results = []
        self.current_page = 1
        self.max_retries = 3
        self.timeout = 10  # 减少超时时间
        self.delay_range = (0.5, 1.5)  # 减少随机延迟(秒)
        
        # 创建会话对象，用于所有请求，添加重试机制
        self.session = self._create_session()
        
        # 缓存，减少重复请求
        self.cache = {}
        
        # 搜索超时控制
        self.search_timeout = 20  # 整体搜索超时（秒）
        
        # HTML转Markdown转换器
        self.html_converter = html2text.HTML2Text()
        self.html_converter.ignore_links = False
        self.html_converter.ignore_images = False
        self.html_converter.ignore_tables = False
        
        # 每次启动先进行Cookie获取
        self._get_initial_cookies()
    
    def _create_session(self):
        """创建请求会话，添加重试机制"""
        session = requests.Session()
        
        # 配置重试策略
        retry_strategy = Retry(
            total=self.max_retries,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET", "HEAD"],
            backoff_factor=0.5
        )
        
        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        
        return session
    
    def _update_headers(self):
        """更新随机User-Agent和其他请求头"""
        headers = self.base_headers.copy()
        headers['User-Agent'] = random.choice(self.user_agents)
        self.headers = headers
    
    def _get_initial_cookies(self):
        """获取初始Cookie以模拟真实浏览器会话"""
        cache_key = "initial_cookies"
        if cache_key in self.cache:
            self.cookies = self.cache[cache_key]
            logger.info("从缓存加载Cookie")
            return
            
        try:
            # 访问Bing首页获取Cookie
            response = self.session.get(
                "https://www.bing.com/",
                headers=self.headers,
                timeout=5  # 减少超时时间
            )
            
            if response.status_code == 200:
                self.cookies = response.cookies
                self.cache[cache_key] = response.cookies
                logger.info("成功获取初始Cookie")
                # 在拿到Cookie后稍等一下
                time.sleep(random.uniform(0.2, 0.5))
            else:
                logger.warning(f"获取初始Cookie失败: {response.status_code}")
        except Exception as e:
            logger.warning(f"获取初始Cookie时出错: {str(e)}")
    
    def search(self, query, num_results=10, keywords=None, sort_by_relevance=True, match_all_keywords=False):
        """
        执行网络搜索并返回结果
        
        参数:
            query (str): 搜索查询
            num_results (int): 要获取的最大结果数
            keywords (list): 可选的关键词列表，用于过滤结果
            sort_by_relevance (bool): 是否按照相关性排序结果，默认为True
            match_all_keywords (bool): 是否要求匹配所有关键词，默认为False
        
        返回:
            list: 搜索结果列表
        """
        results = []
        
        # 检查缓存
        cache_key = f"{query}_{num_results}"
        if cache_key in self.cache:
            logging.info(f"从缓存中获取搜索结果: {query}")
            cached_results = self.cache[cache_key]
            # 只缓存原始结果，仍然应用过滤和排序
            results = self._filter_results_by_keywords(cached_results, keywords, match_all_keywords)
            if sort_by_relevance:
                results = self.sort_results(results, query)
            return results[:num_results]
        
        # 尝试使用Google搜索API
        try:
            if hasattr(self, 'google_api_key') and hasattr(self, 'google_cx') and self.google_api_key and self.google_cx:
                results = self._search_with_google_api(query, num_results)
            else:
                # 尝试使用备用方法
                results = self._search_with_fallback(query, num_results)
        except Exception as e:
            logging.error(f"搜索错误: {str(e)}")
            logging.info("尝试使用备用搜索方法")
            try:
                results = self._search_with_fallback(query, num_results)
            except Exception as fallback_error:
                logging.error(f"备用搜索方法也失败: {str(fallback_error)}")
        
        # 缓存原始搜索结果
        if results:
            self.cache[cache_key] = results
            logging.info(f"缓存了 {len(results)} 条搜索结果: {query}")
        
        # 应用关键词过滤
        filtered_results = self._filter_results_by_keywords(results, keywords, match_all_keywords)
        
        # 应用相关性排序
        if sort_by_relevance:
            filtered_results = self.sort_results(filtered_results, query)
        
        return filtered_results[:num_results]
    
    def _search_with_google_api(self, query, num_results=10):
        """
        使用Google自定义搜索API执行搜索
        
        参数:
            query (str): 搜索查询
            num_results (int): 要获取的结果数量
            
        返回:
            list: 搜索结果列表
        """
        logging.info(f"使用Google API搜索: {query}")
        results = []
        
        try:
            # Google CSE API限制每次请求最多10个结果
            max_per_request = 10
            required_requests = (num_results + max_per_request - 1) // max_per_request
            
            for i in range(required_requests):
                start_index = i * max_per_request + 1
                api_url = f"https://www.googleapis.com/customsearch/v1"
                params = {
                    'q': query,
                    'key': self.google_api_key,
                    'cx': self.google_cx,
                    'start': start_index,
                    'num': min(max_per_request, num_results - (i * max_per_request))
                }
                
                response = self._make_request(f"{api_url}?{urllib.parse.urlencode(params)}")
                
                if not response or response.status_code != 200:
                    logging.warning(f"Google API请求失败: {response.status_code if response else 'No response'}")
                    continue
                
                data = response.json()
                
                if 'items' not in data:
                    logging.warning(f"Google API返回数据中没有items字段: {data.get('error', {}).get('message', '')}")
                    continue
                
                for item in data['items']:
                    result = {
                        'title': item.get('title', ''),
                        'url': item.get('link', ''),
                        'description': item.get('snippet', ''),
                        'source': 'Google API'
                    }
                    results.append(result)
                
                # API有速率限制，请求之间添加延迟
                if i < required_requests - 1:
                    time.sleep(random.uniform(1, 2))
            
            logging.info(f"Google API搜索成功: 找到 {len(results)} 条结果")
            
        except Exception as e:
            logging.error(f"Google API搜索出错: {str(e)}")
            
        return results[:num_results] if results else []
    
    def _search_with_fallback(self, query, num_results=10):
        """
        使用Bing搜索引擎作为备用搜索方法
        
        参数:
            query (str): 搜索查询
            num_results (int): 要获取的结果数量
            
        返回:
            list: 搜索结果列表
        """
        logging.info(f"使用Bing搜索: {query}")
        all_results = []
        
        # 编码查询字符串
        encoded_query = quote_plus(query)
        
        # 确定需要多少页的结果
        results_per_page = 10  # Bing每页通常有10个结果
        required_pages = (num_results + results_per_page - 1) // results_per_page
        required_pages = min(required_pages, 3)  # 限制最多抓取3页，避免过多请求
        
        for page in range(1, required_pages + 1):
            # 构造Bing搜索URL
            if page == 1:
                search_url = f"https://www.bing.com/search?q={encoded_query}&setlang=zh-CN"
            else:
                first_result = (page - 1) * results_per_page + 1
                search_url = f"https://www.bing.com/search?q={encoded_query}&first={first_result}&setlang=zh-CN"
            
            logging.info(f"请求页面 {page}/{required_pages}: {search_url}")
            
            # 发送请求
            response = self._make_request(search_url)
            
            if not response or response.status_code != 200:
                logging.warning(f"搜索请求失败: {response.status_code if response else 'No response'}")
                continue
                
            # 解析搜索结果
            page_results = self._parse_search_results(response.text)
            
            if page_results:
                all_results.extend(page_results)
                logging.info(f"页面 {page} 解析到 {len(page_results)} 个结果")
            else:
                logging.warning(f"页面 {page} 未找到结果")
                # 如果连第一页都没有结果，可能是搜索引擎限制或其他问题
                if page == 1:
                    break
            
            # 如果已经获取足够的结果，停止请求更多页面
            if len(all_results) >= num_results:
                break
                
            # 在请求之间添加随机延迟，避免被视为爬虫
            if page < required_pages:
                delay = random.uniform(*self.delay_range)
                logging.info(f"请求下一页前等待 {delay:.2f} 秒")
                time.sleep(delay)
        
        # 去重处理
        unique_results = self._deduplicate_results(all_results)
        
        logging.info(f"Bing搜索完成: 总共找到 {len(unique_results)} 条唯一结果")
        
        return unique_results[:num_results]
    
    def _filter_results_by_keywords(self, results, keywords, match_all_keywords=False):
        """
        根据指定的关键词过滤搜索结果
        
        参数:
            results (list): 要过滤的搜索结果列表
            keywords (list): 关键词列表
            match_all_keywords (bool): 是否要求匹配所有关键词
            
        返回:
            list: 过滤后的结果列表
        """
        if not keywords or not results:
            return results
            
        filtered_results = []
        keywords = [kw.lower() for kw in keywords]
        
        for result in results:
            title = result.get('title', '').lower()
            snippet = result.get('snippet', '').lower() or result.get('description', '').lower()
            url = result.get('url', '').lower()
            
            # 计算匹配的关键词
            matches = []
            for keyword in keywords:
                if keyword in title or keyword in snippet or keyword in url:
                    matches.append(keyword)
            
            # 根据匹配策略确定是否保留结果
            if match_all_keywords and len(matches) == len(keywords):
                filtered_results.append(result)
            elif not match_all_keywords and matches:
                filtered_results.append(result)
                
        logging.info(f"关键词过滤: 从 {len(results)} 条结果中过滤得到 {len(filtered_results)} 条结果")
        return filtered_results
    
    def _search_timeout_handler(self):
        """搜索超时处理器"""
        logger.warning(f"搜索操作超时 ({self.search_timeout}秒)，强制终止")
        # 在线程中无法直接抛出异常给主线程，只能记录警告
    
    def _deduplicate_results(self, results):
        """去除重复的搜索结果并保持原有顺序"""
        seen_urls = set()
        unique_results = []
        
        for result in results:
            url = result.get('url', '')
            # 标准化URL进行比较
            norm_url = self._normalize_url(url)
            
            if norm_url and norm_url not in seen_urls:
                seen_urls.add(norm_url)
                unique_results.append(result)
                
        return unique_results
    
    def _normalize_url(self, url):
        """标准化URL以进行比较，去除不必要的参数等"""
        try:
            parsed = urlparse(url)
            # 返回主要部分，忽略常见的跟踪参数
            return f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
        except:
            return url
    
    def _make_request(self, url, timeout=None):
        """发送HTTP请求并处理重试逻辑"""
        # 如果没有指定超时，使用默认值
        if timeout is None:
            timeout = self.timeout
            
        # 检查缓存
        cache_key = f"request_{url}"
        if cache_key in self.cache:
            logger.info(f"从缓存返回网页内容: {url[:50]}...")
            return self.cache[cache_key]
        
        # 每次请求前更新headers
        self._update_headers()
        
        # 添加refer和其他可能的防爬参数
        if "bing.com/search" in url:
            self.headers['Referer'] = 'https://www.bing.com/'
        
        for attempt in range(self.max_retries):
            try:
                # 添加随机延迟
                if attempt > 0:
                    sleep_time = 2 ** attempt + random.uniform(0, 1)
                    logger.info(f"重试前等待 {sleep_time:.2f} 秒")
                    time.sleep(sleep_time)
                
                response = self.session.get(
                    url, 
                    headers=self.headers, 
                    timeout=timeout,
                    cookies=self.cookies,
                    allow_redirects=True
                )
                
                # 保存新Cookie以保持会话
                if response.cookies:
                    self.cookies.update(response.cookies)
                
                # 检查是否有反爬机制
                if "captcha" in response.url.lower() or "verify" in response.url.lower():
                    logger.warning(f"检测到验证码或反爬措施: {response.url}")
                    # 可以在这里添加验证码处理逻辑
                    return None
                
                # 检查HTTP状态码
                if response.status_code != 200:
                    logger.warning(f"请求返回非200状态码: {response.status_code}")
                    if attempt < self.max_retries - 1:
                        continue
                    return None
                
                # 检查响应内容
                if len(response.text) < 1000:  # 如果内容过短，可能是被拦截了
                    logger.warning(f"响应内容过短({len(response.text)}字符)，可能被拦截")
                    if attempt < self.max_retries - 1:
                        continue
                
                # 将HTML内容中的相对URL转换为绝对URL
                base_url = response.url
                response._content = response.content.replace(
                    b'href="/', 
                    f'href="{base_url.split("/")[0]}//{base_url.split("/")[2]}/'.encode()
                )
                
                # 缓存响应
                self.cache[cache_key] = response
                
                return response
                
            except (requests.RequestException, Exception) as e:
                logger.warning(f"请求失败 (尝试 {attempt+1}/{self.max_retries}): {str(e)}")
                if attempt < self.max_retries - 1:
                    continue
                return None
    
    def _parse_search_results(self, html_content):
        """
        解析Bing搜索结果页面
        
        参数:
            html_content (str): 搜索结果页面HTML内容
            
        返回:
            list: 搜索结果列表
        """
        if not html_content:
            return []
            
        results = []
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # 首先尝试解析主搜索结果
        main_results = soup.select('#b_results > li.b_algo')
        if not main_results:
            # 备用选择器
            main_results = soup.select('.b_algo')
        
        for result in main_results:
            try:
                # 提取标题和链接
                title_element = result.select_one('h2 a')
                if not title_element:
                    continue
                    
                title = title_element.get_text(strip=True)
                url = title_element.get('href', '')
                
                if not url or not title:
                    continue
                
                # 规范化URL
                if not url.startswith(('http://', 'https://')):
                    continue
                
                # 过滤Bing自身URL和特定域名
                if self._should_filter_url(url):
                    continue
                
                # 提取描述
                description = ""
                desc_element = result.select_one('.b_caption p')
                if desc_element:
                    description = desc_element.get_text(strip=True)
                
                # 提取日期（如果存在）
                date = ""
                date_element = result.select_one('.news_dt')
                if date_element:
                    date = date_element.get_text(strip=True)
                
                # 找出可能的favicon
                favicon = ""
                favicon_element = result.select_one('.b_favicon img')
                if favicon_element:
                    favicon = favicon_element.get('src', '')
                
                # 创建结果项
                result_item = {
                    'title': title,
                    'url': url,
                    'description': description,
                    'favicon': favicon,
                    'date': date
                }
                
                results.append(result_item)
                
            except Exception as e:
                logger.warning(f"解析搜索结果项时出错: {str(e)}")
                continue
        
        # 尝试解析并添加特殊搜索结果（如新闻、视频等）
        try:
            self._add_special_results(soup, results)
        except Exception as e:
            logger.warning(f"解析特殊搜索结果时出错: {str(e)}")
        
        return results
    
    def _add_special_results(self, soup, results):
        """添加特殊搜索结果（新闻、视频等）"""
        # 尝试添加新闻结果
        news_results = soup.select('#b_results .b_slidebar li.news_item')
        if news_results:
            for news in news_results[:3]:  # 限制最多3个新闻
                try:
                    title_element = news.select_one('a.title')
                    if not title_element:
                        continue
                        
                    title = title_element.get_text(strip=True)
                    url = title_element.get('href', '')
                    
                    if not url or not title or self._should_filter_url(url):
                        continue
                    
                    # 提取新闻来源和日期
                    source = ""
                    date = ""
                    source_element = news.select_one('.source')
                    if source_element:
                        source_text = source_element.get_text(strip=True)
                        # 尝试分离来源和日期
                        parts = source_text.split('·')
                        if len(parts) > 0:
                            source = parts[0].strip()
                        if len(parts) > 1:
                            date = parts[1].strip()
                    
                    # 提取描述
                    description = ""
                    desc_element = news.select_one('.snippet')
                    if desc_element:
                        description = desc_element.get_text(strip=True)
                    
                    results.append({
                        'title': title,
                        'url': url,
                        'description': description,
                        'source': source,
                        'date': date,
                        'type': 'news'
                    })
                except Exception:
                    continue
    
    def _should_filter_url(self, url):
        """判断URL是否应该被过滤掉"""
        lower_url = url.lower()
        
        # 过滤Bing自身URL
        if 'bing.com' in lower_url:
            return True
            
        # 过滤特定域名
        filtered_domains = [
            'microsofttranslator.com',
            'microsoft.com/en-us/translator',
            'go.microsoft.com',
            'msn.com',
            'microsoftstore.com',
            'windows.net'
        ]
        
        for domain in filtered_domains:
            if domain in lower_url:
                return True
                
        return False
    
    def sort_results(self, results, query):
        """
        根据与查询的相关性对搜索结果进行排序
        
        参数:
            results (list): 搜索结果列表
            query (str): 原始搜索查询
            
        返回:
            list: 排序后的搜索结果列表
        """
        if not results or len(results) <= 1:
            return results
            
        # 拆分查询词以计算匹配度
        query_terms = set(self._tokenize_text(query.lower()))
        
        # 为每个结果计算相关性得分
        def calculate_relevance(result):
            score = 0
            
            # 标题匹配权重最高
            title = result.get('title', '').lower()
            title_tokens = self._tokenize_text(title)
            title_matches = sum(1 for term in query_terms if term in title_tokens)
            score += title_matches * 3
            
            # 完整短语匹配加分
            if query.lower() in title.lower():
                score += 5
                
            # URL相关性
            url = result.get('url', '').lower()
            for term in query_terms:
                if term in url:
                    score += 1
            
            # 描述匹配
            snippet = result.get('description', '').lower()
            snippet_tokens = self._tokenize_text(snippet)
            snippet_matches = sum(1 for term in query_terms if term in snippet_tokens)
            score += snippet_matches * 1.5
            
            # 考虑结果的原始排名
            original_index = results.index(result)
            score += max(0, (len(results) - original_index) / len(results) * 2)
            
            return score
            
        # 根据相关性得分排序
        return sorted(results, key=calculate_relevance, reverse=True)
        
    def _tokenize_text(self, text):
        """
        将文本分词为单词列表，去除常见停用词
        
        参数:
            text (str): 要分词的文本
            
        返回:
            list: 分词后的单词列表
        """
        # 简单的分词，仅按空格和标点符号分割
        tokens = re.findall(r'\b\w+\b', text)
        
        # 常见停用词
        stop_words = {'the', 'a', 'an', 'and', 'or', 'but', 'is', 'are', 'was', 
                      'were', 'be', 'been', 'being', 'in', 'on', 'at', 'to', 'for',
                      'with', 'by', 'about', 'of', 'from'}
                      
        # 过滤停用词并返回
        return [token.lower() for token in tokens if token.lower() not in stop_words]
    
    def clear_cache(self):
        """清除搜索缓存"""
        self.cache = {}
        self.search_results = {}
        logger.info("搜索缓存已清除")
        
    def get_cache_size(self):
        """获取缓存大小"""
        return len(self.cache)
        
    def get_cache_keys(self):
        """获取缓存中的查询关键词"""
        return list(self.cache.keys())
    
    def fetch_webpage_content(self, url):
        """
        获取网页内容并解析
        
        参数:
            url (str): 要获取的网页URL
            
        返回:
            dict: 包含标题、正文、元信息等内容的字典
        """
        # 检查缓存
        cache_key = f"webpage_{url}"
        if cache_key in self.cache:
            logger.info(f"从缓存返回网页内容: {url}")
            return self.cache[cache_key]
            
        try:
            logger.info(f"获取网页内容: {url}")
            response = self._make_request(url)
            
            if not response or response.status_code != 200:
                logger.warning(f"获取网页失败，状态码: {response.status_code if response else 'None'}")
                return {"error": "获取网页失败", "status_code": response.status_code if response else None}
            
            # 检测编码
            encoding = response.encoding
            if encoding == 'ISO-8859-1':
                # 尝试从内容中检测编码
                encoding = self._detect_encoding(response.content) or 'utf-8'
            
            # 使用lxml加速解析
            try:
                soup = BeautifulSoup(response.content, 'lxml', from_encoding=encoding)
            except:
                soup = BeautifulSoup(response.content, 'html.parser', from_encoding=encoding)
            
            # 清理页面
            for tag in soup(["script", "style", "iframe", "noscript"]):
                tag.extract()
            
            # 提取标题
            title = soup.title.get_text(strip=True) if soup.title else "无标题"
            
            # 提取元信息
            meta_info = self._extract_meta_info(soup)
            
            # 提取正文内容
            main_content = self._extract_main_content(soup)
            
            # 准备结果
            result = {
                "url": url,
                "title": title,
                "meta_info": meta_info,
                "content": main_content,
                # 避免保存过大的HTML
                "html": str(soup)[:100000] + ("..." if len(str(soup)) > 100000 else "")
            }
            
            # 缓存结果
            self.cache[cache_key] = result
            
            return result
            
        except Exception as e:
            logger.error(f"获取网页内容时出错: {str(e)}")
            return {"error": f"获取网页内容时出错: {str(e)}"}
    
    def _detect_encoding(self, content):
        """尝试从HTML内容中检测编码"""
        try:
            charset_re = re.compile(r'<meta.*?charset=["\']*(.+?)["\'>]', re.I)
            pragma_re = re.compile(r'<meta.*?content=["\']*;?charset=(.+?)["\'>]', re.I)
            xml_re = re.compile(r'^<\?xml.*?encoding=["\']*(.+?)["\'>]', re.I)
            
            # 尝试不同的正则表达式
            for regex in [charset_re, pragma_re, xml_re]:
                match = regex.search(content[:1000].decode('ascii', errors='ignore'))
                if match:
                    return match.group(1).lower()
                    
            return None
        except Exception:
            return None
    
    def _extract_meta_info(self, soup):
        """提取页面元信息"""
        meta_info = {}
        
        try:
            # 一次提取所有meta标签，然后按需处理
            meta_tags = soup.find_all("meta")
            
            # 创建属性到标签的映射
            for tag in meta_tags:
                # 提取描述
                if tag.get("name") == "description" and tag.get("content"):
                    meta_info["description"] = tag["content"]
                
                # 提取关键词
                elif tag.get("name") == "keywords" and tag.get("content"):
                    meta_info["keywords"] = tag["content"]
                
                # 提取作者
                elif tag.get("name") == "author" and tag.get("content"):
                    meta_info["author"] = tag["content"]
                
                # 提取发布日期
                elif tag.get("property") == "article:published_time" and tag.get("content"):
                    meta_info["published_date"] = tag["content"]
                    
                # Open Graph元数据
                elif tag.get("property") and tag.get("property").startswith("og:") and tag.get("content"):
                    key = tag["property"][3:]  # 移除"og:"前缀
                    meta_info[f"og_{key}"] = tag["content"]
            
            return meta_info
        except Exception as e:
            logger.debug(f"提取元信息出错: {e}")
            return meta_info
    
    def _extract_main_content(self, soup):
        """
        智能提取网页主要内容
        使用启发式方法，尝试找到包含最多文本的主要内容区域
        """
        try:
            # 尝试常见的内容容器ID和类
            content_ids = ['content', 'main', 'article', 'post', 'body', 'entry']
            content_classes = ['content', 'main', 'article', 'post', 'body', 'entry', 'text']
            
            potential_content_tags = []
            
            # 根据ID查找
            for id_name in content_ids:
                tag = soup.find(id=re.compile(f".*{id_name}.*", re.I))
                if tag:
                    potential_content_tags.append(tag)
            
            # 根据类名查找
            for class_name in content_classes:
                tags = soup.find_all(class_=re.compile(f".*{class_name}.*", re.I))
                potential_content_tags.extend(tags)
            
            # 查找特定元素
            for tag_name in ['article', 'main', 'section']:
                tags = soup.find_all(tag_name)
                potential_content_tags.extend(tags)
            
            # 过滤掉None值和太小的内容
            potential_content_tags = [tag for tag in potential_content_tags if tag and len(tag.get_text(strip=True)) > 200]
            
            if potential_content_tags:
                # 找到文本最多的容器
                main_content_tag = max(potential_content_tags, key=lambda tag: len(tag.get_text(strip=True)))
                content = main_content_tag.get_text(separator='\n', strip=True)
                return content
            
            # 如果没有找到明确的内容标签，尝试从正文段落提取
            paragraphs = soup.find_all('p')
            if paragraphs:
                # 筛选掉太短的段落，这些可能是导航或者菜单项
                valid_paragraphs = [p for p in paragraphs if len(p.get_text(strip=True)) > 30]
                
                if valid_paragraphs:
                    content = '\n\n'.join(p.get_text(strip=True) for p in valid_paragraphs)
                    return content
            
            # 后备方案：提取所有可见文本
            return self._extract_visible_text(soup)
            
        except Exception as e:
            logger.debug(f"提取主要内容出错: {e}")
            # 出错时尝试最简单的提取方式
            return soup.get_text(separator='\n', strip=True)
    
    def _extract_visible_text(self, soup):
        """提取网页中的可见文本，忽略导航和菜单等部分"""
        # 移除导航、页脚、侧边栏等常见的非主要内容区域
        for tag in soup.find_all(['nav', 'footer', 'sidebar', 'widget']):
            tag.extract()
            
        for tag in soup.find_all(class_=re.compile(r'(nav|menu|footer|sidebar|widget|comment)', re.I)):
            tag.extract()
            
        # 提取所有剩余文本
        text_blocks = []
        for tag in soup.find_all(['p', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'li']):
            text = tag.get_text(strip=True)
            if text and len(text) > 20:  # 只保留有意义的文本块
                text_blocks.append(text)
                
        return '\n\n'.join(text_blocks)

    def extract_key_sentences(self, content, keywords, max_sentences=10):
        """
        从内容中提取包含关键词的关键句子
        
        参数:
            content (str): 文本内容
            keywords (list): 关键词列表
            max_sentences (int): 最大句子数量
            
        返回:
            list: 关键句子列表
        """
        if not content or not keywords:
            return []
        
        # 分割成句子 - 使用更精确的句子分割
        sentence_pattern = re.compile(r'(?<=[.!?])\s+(?=[A-Z0-9])')
        sentences = sentence_pattern.split(content)
        
        # 过滤短句子和过长句子
        sentences = [s.strip() for s in sentences if 20 <= len(s.strip()) <= 250]
        
        # 如果没有关键词，返回前几个句子
        if not keywords:
            return sentences[:max_sentences]
        
        # 找出包含关键词的句子，并计算其权重
        sentence_scores = []
        for sentence in sentences:
            sentence_lower = sentence.lower()
            # 计算有多少关键词出现在句子中
            matched_keywords = [keyword for keyword in keywords 
                               if keyword.lower() in sentence_lower]
            
            if matched_keywords:
                # 权重 = 匹配关键词数量 / 句子长度(归一化)
                weight = len(matched_keywords) / (len(sentence) ** 0.5)
                sentence_scores.append((sentence, weight))
        
        # 按权重排序
        sentence_scores.sort(key=lambda x: x[1], reverse=True)
        key_sentences = [s for s, _ in sentence_scores[:max_sentences]]
        
        # 如果关键句太少，添加前几个句子作为上下文
        if len(key_sentences) < max_sentences and sentences:
            context_sentences = [s for s in sentences[:max_sentences - len(key_sentences)]
                               if s not in key_sentences]
            key_sentences = context_sentences + key_sentences
        
        # 截断到最大句子数
        return key_sentences[:max_sentences]

    def summarize_results(self, results, keywords=None, detailed=False):
        """
        汇总搜索结果，为Agent提供简洁摘要
        
        参数:
            results (list): 搜索结果列表
            keywords (list): 可选的关键词列表用于突出显示
            detailed (bool): 是否包含详细内容
            
        返回:
            str: 格式化的摘要文本
        """
        if not results:
            return "未找到搜索结果。"
        
        summary = []
        
        for i, result in enumerate(results):
            title = result.get("title", "无标题")
            url = result.get("url", "")
            description = result.get("description", "无描述")
            
            # 截断过长的描述
            if len(description) > 300:
                description = description[:297] + "..."
            
            # 突出显示关键词
            if keywords:
                for keyword in keywords:
                    # 使用单一正则表达式提高性能
                    keyword_regex = re.compile(f"({re.escape(keyword)})", re.IGNORECASE)
                    title = keyword_regex.sub(r"**\1**", title)
                    description = keyword_regex.sub(r"**\1**", description)
            
            # 使用更简洁的格式
            result_text = f"{i+1}. **{title}**\n   {url}\n   {description}"
            
            if detailed and "content" in result:
                # 提取内容摘要
                content_preview = result["content"][:200] + "..." if len(result["content"]) > 200 else result["content"]
                result_text += f"\n   内容: {content_preview}"
            
            summary.append(result_text)
        
        return "\n\n".join(summary)


# 搜索工具函数接口 - 注册到工具注册表使用
def web_search(query, num_results=5, filter_adult=True, keywords=None, sort_by_relevance=True, match_all_keywords=False):
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
    max_total_time = 60  # 整个搜索过程最多60秒
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
    num_results = max(1, min(30, num_results))
    
    try:
        # 创建搜索工具实例
        search_tool = WebSearchTool()
        search_tool.timeout = 10  # 单次请求超时10秒
        
        # 记录搜索已经开始
        logger.info(f"搜索开始: '{query}'")
        
        # 执行搜索
        results = search_tool.search(query, num_results=num_results, keywords=keywords, 
                                     sort_by_relevance=sort_by_relevance, match_all_keywords=match_all_keywords)
        
        # 如果没有找到结果且还有时间，尝试调整查询
        if not results and (time.time() - start_time) < max_total_time - 20:
            logger.warning(f"搜索 '{query}' 未找到结果，尝试调整查询")
            
            # 将查询分成多个备选方案
            alternate_queries = []
            
            # 1. 添加引号进行精确匹配
            if '"' not in query:
                alternate_queries.append((f'"{query}"', "精确匹配"))
            
            # 2. 去掉特殊字符，保留主要关键词
            clean_query = re.sub(r'[^\w\s]', ' ', query).strip()
            clean_query = re.sub(r'\s+', ' ', clean_query)  # 合并多个空格
            if clean_query and clean_query != query:
                alternate_queries.append((clean_query, "去除特殊字符"))
            
            # 3. 提取主要关键词
            words = query.split()
            if len(words) > 3:
                # 只用前三个词
                short_query = ' '.join(words[:3])
                alternate_queries.append((short_query, "简化查询"))
            
            # 4. 尝试重新排列主要关键词
            if len(words) >= 3:
                shuffled_query = ' '.join(random.sample(words[:4], min(3, len(words))))
                alternate_queries.append((shuffled_query, "重排关键词"))
            
            # 逐个尝试调整后的查询
            for adjusted_query, adjustment_type in alternate_queries:
                # 检查总时间
                if time.time() - start_time > max_total_time - 15:
                    logger.warning("接近总时间限制，停止尝试调整查询")
                    break
                    
                logger.info(f"尝试{adjustment_type}搜索: '{adjusted_query}'")
                adjusted_results = search_tool.search(adjusted_query, num_results=num_results, 
                                                       keywords=keywords, sort_by_relevance=sort_by_relevance, 
                                                       match_all_keywords=match_all_keywords)
                
                if adjusted_results:
                    logger.info(f"使用{adjustment_type}搜索成功找到结果")
                    results = adjusted_results
                    break
                    
        elapsed_time = time.time() - start_time
        logger.info(f"搜索完成，用时: {elapsed_time:.2f}秒，找到结果数: {len(results)}")
        
        # 根据结果生成合适的消息
        if results:
            message = f"找到 {len(results)} 个搜索结果"
            if keywords:
                message += f"，已根据 {'所有' if match_all_keywords else '任一'} 关键词 ({', '.join(keywords)}) 进行过滤"
            if sort_by_relevance:
                message += "，并按相关性排序"
            # 生成摘要
            summary = search_tool.summarize_results(results, keywords)
        else:
            message = "未找到相关搜索结果，请尝试使用不同的关键词"
            # 为空结果提供一个友好的摘要
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
        logger.exception("搜索错误详情:")
        
        # 检查是否是超时错误
        if "timeout" in str(e).lower() or elapsed_time > max_total_time * 0.8:
            error_msg = f"搜索超时，请稍后重试或使用更简单的关键词 (用时: {elapsed_time:.2f}秒)"
            error_type = "超时错误"
        else:
            error_type = type(e).__name__
        
        return {
            "status": "error",
            "query": query,
            "error": error_msg,
            "error_type": error_type,
            "results": [],
            "results_count": 0,
            "summary": f"搜索\"{query}\"时遇到了问题。这可能是由于网络连接问题、搜索服务暂时不可用或关键词格式问题导致的。\n\n建议：\n- 稍后重试\n- 使用更简单的关键词\n- 检查网络连接",
            "message": "搜索失败，请稍后重试",
            "elapsed_time": f"{elapsed_time:.2f}秒"
        }

def fetch_webpage(url, extract_keywords=None):
    """
    获取特定网页内容
    
    参数:
        url (str): 网页URL
        extract_keywords (list): 可选关键词列表，用于提取关键句子
        
    返回:
        dict: 包含网页内容的字典
    """
    try:
        logger.info(f"获取网页内容: {url}")
        
        # URL验证和格式化
        if not url.startswith(('http://', 'https://')):
            url = 'https://' + url
            
        # 检查URL是否有效
        parsed_url = urlparse(url)
        if not parsed_url.netloc:
            return {
                "status": "error",
                "url": url,
                "error": "无效的URL格式",
                "message": "无法获取网页内容，URL格式无效"
            }
        
        search_tool = WebSearchTool()
        result = search_tool.fetch_webpage_content(url)
        
        # 检查是否有错误
        if "error" in result:
            logger.warning(f"获取网页内容失败: {result.get('error')}")
            return {
                "status": "error",
                "url": url,
                "error": result.get("error", "获取网页内容失败"),
                "message": "无法获取网页内容，请检查URL是否有效"
            }
        
        # 如果提供了关键词，则提取关键句子
        key_sentences = []
        if extract_keywords and "content" in result and result["content"]:
            # 确保关键词是列表类型
            if isinstance(extract_keywords, str):
                extract_keywords = [extract_keywords]
                
            key_sentences = search_tool.extract_key_sentences(
                result["content"], 
                extract_keywords
            )
            result["key_sentences"] = key_sentences
        
        # 创建内容摘要 - 截取前500个字符
        content_preview = result.get("content", "")[:500] + "..." if len(result.get("content", "")) > 500 else result.get("content", "")
        
        # 移除HTML内容以减少响应大小
        if "html" in result:
            del result["html"]
        
        return {
            "status": "success",
            "url": url,
            "title": result.get("title", ""),
            "content": result.get("content", ""),
            "content_preview": content_preview,
            "meta_info": result.get("meta_info", {}),
            "key_sentences": key_sentences,
            "message": f"成功获取网页内容: {result.get('title', '')}"
        }
    except Exception as e:
        error_msg = f"获取网页内容时出错: {str(e)}"
        logger.error(error_msg)
        logger.exception("获取网页错误详情:")
        
        return {
            "status": "error",
            "url": url,
            "error": error_msg,
            "error_type": type(e).__name__,
            "message": "获取网页失败，请稍后重试或检查URL是否有效"
        }

def filter_search_results(results, keywords, match_all=False):
    """
    根据关键词筛选搜索结果
    
    参数:
        results (list): 搜索结果列表
        keywords (list): 关键词列表
        match_all (bool): 是否要求匹配所有关键词
        
    返回:
        dict: 筛选后的结果信息
    """
    try:
        # 确保keywords是列表类型
        if isinstance(keywords, str):
            keywords = [keywords]
            
        if not keywords:
            return {
                "status": "error",
                "message": "未提供筛选关键词",
                "filter_keywords": [],
                "results": results,
                "results_count": len(results)
            }
            
        if not results:
            return {
                "status": "error",
                "message": "没有搜索结果可供筛选",
                "filter_keywords": keywords,
                "results": [],
                "results_count": 0
            }
        
        logger.info(f"筛选搜索结果，关键词: {keywords}，匹配模式: {'全部' if match_all else '任一'}")
        search_tool = WebSearchTool()
        filtered_results = search_tool._filter_results_by_keywords(
            results, 
            keywords, 
            match_all_keywords=match_all
        )
        
        # 生成摘要，突出显示关键词
        summary = search_tool.summarize_results(filtered_results, keywords)
        
        # 构建返回信息
        match_type = "所有" if match_all else "任一"
        if filtered_results:
            message = f"找到 {len(filtered_results)} 个匹配{match_type}关键词的结果 (从 {len(results)} 个结果中筛选)"
            if not match_all and len(filtered_results) == len(results):
                message += "。建议使用更具体的关键词或选择'匹配所有关键词'模式以获得更精确的筛选结果。"
        else:
            message = f"没有找到匹配{match_type}关键词的结果"
            if match_all and len(keywords) > 1:
                message += "。建议尝试'匹配任一关键词'模式或减少关键词数量。"
        
        return {
            "status": "success",
            "filter_keywords": keywords,
            "match_all": match_all,
            "results_count": len(filtered_results),
            "results": filtered_results,
            "summary": summary,
            "message": message
        }
    except Exception as e:
        error_msg = f"筛选搜索结果时出错: {str(e)}"
        logger.error(error_msg)
        
        return {
            "status": "error",
            "filter_keywords": keywords,
            "error": error_msg,
            "results": results,
            "results_count": len(results),
            "message": "筛选过程中出错，返回原始结果"
        } 