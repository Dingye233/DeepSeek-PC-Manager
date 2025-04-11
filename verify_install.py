import pkg_resources
try:
    pkg_resources.require(['paramiko==2.12.0', 'pywin32==306', 'gitpython==3.1.32'])
    print('所有依赖验证通过')
except Exception as e:
    print(f'验证失败: {str(e)}')