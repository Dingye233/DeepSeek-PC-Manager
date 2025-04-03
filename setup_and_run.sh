#!/bin/bash

# 一键配置和启动项目的脚本

# 检查是否以root用户运行
if [ "$(id -u)" -ne 0 ]; then
    echo "请使用sudo运行此脚本！"
    exit 1
fi

# 安装Miniconda（如果未安装）
if ! command -v conda &> /dev/null; then
    echo "Miniconda未安装，正在安装..."
    wget https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh -O miniconda.sh
    bash miniconda.sh -b -p $HOME/miniconda
    rm miniconda.sh
    export PATH="$HOME/miniconda/bin:$PATH"
    echo 'export PATH="$HOME/miniconda/bin:$PATH"' >> ~/.bashrc
    source ~/.bashrc
    echo "Miniconda安装完成！"
else
    echo "Miniconda已安装，跳过安装步骤。"
fi

# 创建并激活虚拟环境
echo "正在创建虚拟环境..."
conda env create -f environment.yml
if [ $? -eq 0 ]; then
    echo "虚拟环境创建成功！"
else
    echo "虚拟环境创建失败，请检查environment.yml文件！"
    exit 1
fi

# 激活虚拟环境
source activate pc_agent
if [ $? -eq 0 ]; then
    echo "虚拟环境激活成功！"
else
    echo "虚拟环境激活失败！"
    exit 1
fi

# 启动项目
echo "正在启动项目..."
python main.py  # 替换为你的项目启动命令
if [ $? -eq 0 ]; then
    echo "项目启动成功！"
else
    echo "项目启动失败，请检查启动文件！"
    exit 1
fi