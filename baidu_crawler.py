import requests
from pathlib import Path

def crawl_baidu():
    try:
        # 设置请求头模拟浏览器
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        
        # 发送GET请求
        response = requests.get('https://www.baidu.com', headers=headers)
        response.raise_for_status()  # 检查请求是否成功
        
        # 保存到桌面
        desktop = Path("C:/Users/17924/Desktop")
        output_path = desktop / "baidu.html"
        
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(response.text)
            
        print(f"百度网页已成功保存到 {output_path}")
        
    except Exception as e:
        print(f"爬取失败: {str(e)}")

if __name__ == "__main__":
    crawl_baidu()