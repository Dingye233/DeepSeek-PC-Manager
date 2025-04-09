import urllib.request
import zipfile
import os

# 创建workspace目录（如果不存在）
workspace = "D:\\DeepSeek-PC-Manager-commit\\workspace"
os.makedirs(workspace, exist_ok=True)

# 下载platform-tools
url = "https://dl.google.com/android/repository/platform-tools-latest-windows.zip"
dest = os.path.join(workspace, "platform-tools.zip")
urllib.request.urlretrieve(url, dest)

# 解压到workspace
with zipfile.ZipFile(dest, 'r') as zip_ref:
    zip_ref.extractall(workspace)

print(f"Platform-tools installed to: {workspace}\\platform-tools")