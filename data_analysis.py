import pandas as pd
import os

# 文件路径映射
data_files = {
    'data_1.csv': '原文件1（含中文名）',
    'data_2.csv': '原文件2（含中文名）',
    'data_3.csv': '原文件3（含中文名）',
    'data_4.csv': '原文件4（含中文名）'
}

# 读取数据
data_frames = {}
for alias, original in data_files.items():
    file_path = os.path.join('C:\\Users\\17924\\Desktop', alias)
    try:
        data_frames[original] = pd.read_csv(file_path, encoding='gb2312')
        print(f'成功读取文件: {original}')
    except Exception as e:
        print(f'读取文件 {original} 失败: {e}')

# 数据预处理
for name, df in data_frames.items():
    # 处理缺失值
    df.fillna(method='ffill', inplace=True)  # 前向填充
    # 处理重复值
    df.drop_duplicates(inplace=True)
    print(f'预处理完成: {name}')

# 保存预处理后的数据
for name, df in data_frames.items():
    output_path = os.path.join('C:\\Users\\17924\\Desktop', f'cleaned_{name}.csv')
    df.to_csv(output_path, index=False, encoding='gb2312')
    print(f'已保存预处理文件: {output_path}')