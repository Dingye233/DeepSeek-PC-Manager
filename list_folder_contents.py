import os

def list_folder_contents(folder_path):
    try:
        files = os.listdir(folder_path)
        return files
    except Exception as e:
        return str(e)

if __name__ == "__main__":
    folder_path = r"C:\Users\17924\Desktop\新建文件夹"
    print(list_folder_contents(folder_path))