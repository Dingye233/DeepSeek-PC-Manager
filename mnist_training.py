# 1. 环境设置
import os
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'  # 抑制TensorFlow日志
import tensorflow as tf
from tensorflow import keras
import numpy as np
import matplotlib.pyplot as plt

# 2. 数据准备
def load_data():
    (x_train, y_train), (x_test, y_test) = keras.datasets.mnist.load_data()
    # 归一化并reshape
    x_train = x_train.astype("float32") / 255
    x_test = x_test.astype("float32") / 255
    x_train = np.expand_dims(x_train, -1)
    x_test = np.expand_dims(x_test, -1)
    # 转换为one-hot
    y_train = keras.utils.to_categorical(y_train, 10)
    y_test = keras.utils.to_categorical(y_test, 10)
    return x_train, y_train, x_test, y_test

# 3. 模型构建
def build_model():
    model = keras.Sequential([
        keras.layers.Conv2D(32, kernel_size=(3,3), activation="relu", input_shape=(28,28,1)),
        keras.layers.MaxPooling2D(pool_size=(2,2)),
        keras.layers.Flatten(),
        keras.layers.Dense(128, activation="relu"),
        keras.layers.Dense(10, activation="softmax")
    ])
    model.compile(
        loss="categorical_crossentropy",
        optimizer="adam",
        metrics=["accuracy"]
    )
    return model

# 4. 静默训练
class SilentCallback(keras.callbacks.Callback):
    def on_epoch_end(self, epoch, logs=None):
        print(f"Epoch {epoch+1} - loss: {logs['loss']:.4f} - accuracy: {logs['accuracy']:.4f}")

def train_model():
    x_train, y_train, x_test, y_test = load_data()
    model = build_model()
    
    history = model.fit(
        x_train, y_train,
        batch_size=128,
        epochs=5,
        verbose=0,  # 关闭默认进度条
        validation_split=0.1,
        callbacks=[SilentCallback()]
    )
    
    # 评估
    test_loss, test_acc = model.evaluate(x_test, y_test, verbose=0)
    print(f"\nTest accuracy: {test_acc:.4f}")
    
    return history, test_acc

# 5. 结果可视化
def plot_results(history):
    plt.figure(figsize=(8,4))
    plt.subplot(1,2,1)
    plt.plot(history.history['accuracy'], label='Training Accuracy')
    plt.plot(history.history['val_accuracy'], label='Validation Accuracy')
    plt.title('Accuracy')
    plt.legend()
    
    plt.subplot(1,2,2)
    plt.plot(history.history['loss'], label='Training Loss')
    plt.plot(history.history['val_loss'], label='Validation Loss')
    plt.title('Loss')
    plt.legend()
    
    plt.tight_layout()
    save_path = r"C:\Users\17924\Desktop\mnist_training_results.png"
    plt.savefig(save_path)
    print(f"\nResults plot saved to: {save_path}")

# 主执行流程
if __name__ == "__main__":
    history, test_acc = train_model()
    plot_results(history)