# 手写数字识别实验报告

## 实验概述
本实验使用卷积神经网络(CNN)在MNIST数据集上进行手写数字识别任务。

## 实验配置
- 框架: TensorFlow/Keras
- 模型架构:
  - 2个卷积层(32和64个滤波器)
  - 2个最大池化层
  - 1个全连接层(128个神经元)
  - 输出层(10个神经元)
- 训练参数:
  - 训练轮次: 5
  - 批量大小: 64
  - 优化器: Adam
  - 损失函数: 稀疏分类交叉熵

## 实验结果
训练过程指标:
```
Epoch 1 - loss: {loss1} - accuracy: {acc1} - val_loss: {val_loss1} - val_accuracy: {val_acc1}
Epoch 2 - loss: {loss2} - accuracy: {acc2} - val_loss: {val_loss2} - val_accuracy: {val_acc2}
Epoch 3 - loss: {loss3} - accuracy: {acc3} - val_loss: {val_loss3} - val_accuracy: {val_acc3}
Epoch 4 - loss: {loss4} - accuracy: {acc4} - val_loss: {val_loss4} - val_accuracy: {val_acc4}
Epoch 5 - loss: {loss5} - accuracy: {acc5} - val_loss: {val_loss5} - val_accuracy: {val_acc5}
```

最终模型在测试集上的准确率: {final_acc}

## 结果可视化
训练过程中的准确率和损失变化曲线已保存为图像文件:
`handwriting_recognition_results.png`

## 结论
该CNN模型能够有效识别手写数字，经过5轮训练后达到较好性能。# 手写数字识别实验报告

## 实验概述
本实验使用卷积神经网络(CNN)在MNIST数据集上进行手写数字识别任务。

## 实验配置
- 框架: TensorFlow/Keras
- 模型架构:
  - 2个卷积层(32和64个滤波器)
  - 2个最大池化层
  - 1个全连接层(128个神经元)
  - 输出层(10个神经元)
- 训练参数:
  - 训练轮次: 5
  - 批量大小: 64
  - 优化器: Adam
  - 损失函数: 稀疏分类交叉熵

## 实验结果
训练过程指标:
```
Epoch 1 - loss: 0.1621 - accuracy: 0.9505 - val_loss: 0.0604 - val_accuracy: 0.9800
Epoch 2 - loss: 0.0523 - accuracy: 0.9838 - val_loss: 0.0461 - val_accuracy: 0.9851
Epoch 3 - loss: 0.0362 - accuracy: 0.9887 - val_loss: 0.0379 - val_accuracy: 0.9880
Epoch 4 - loss: 0.0268 - accuracy: 0.9915 - val_loss: 0.0342 - val_accuracy: 0.9910
Epoch 5 - loss: 0.0193 - accuracy: 0.9939 - val_loss: 0.0385 - val_accuracy: 0.9899
```

最终模型在测试集上的准确率: 98.99%

## 结果可视化
训练过程中的准确率和损失变化曲线已保存为图像文件:
`handwriting_recognition_results.png`

## 结论
该CNN模型能够有效识别手写数字，经过5轮训练后测试准确率达到98.99%，表现出色。