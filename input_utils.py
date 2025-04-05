import asyncio
import sys
import time
import threading
import signal
import concurrent.futures
from typing import Optional, Tuple
import os  # 添加导入以检测操作系统

# 检测是否为Windows平台
IS_WINDOWS = sys.platform.startswith('win')

# 在Windows平台上导入特定模块
if IS_WINDOWS:
    try:
        import msvcrt
    except ImportError:
        pass

# 全局变量用于跟踪当前活跃的输入任务
_current_input_task = None
_current_executor = None
_active_input_lock = threading.Lock()

# 用于存储全局状态的变量
_input_state = {"received": False, "value": None, "cancel_requested": False}

# 初始化用于跟踪线程池的列表
if not hasattr(sys.modules[__name__], 'executors'):
    sys.modules[__name__].executors = []

# 自定义输入函数，解决标准input()无法接收多行输入的问题
def custom_input():
    """自定义输入函数，支持多行输入"""
    lines = []
    line = ""
    
    if IS_WINDOWS:
        # Windows平台使用msvcrt获取单个字符
        try:
            # 清空现有的输入缓冲区
            while msvcrt.kbhit():
                msvcrt.getch()
                
            last_was_cr = False  # 跟踪上一个字符是否为回车
            empty_line = False   # 跟踪是否为空行
            
            while True:
                ch = msvcrt.getch()
                
                # 退格键
                if ch == b'\x08':
                    if line:
                        line = line[:-1]
                        # 清除上一个字符
                        print("\b \b", end="", flush=True)
                    continue
                
                # 回车键 - Windows上通常是 \r\n
                if ch == b'\r':
                    print()  # 打印换行
                    last_was_cr = True
                    
                    # 如果是空行且已有内容，这是结束信号
                    if not line and lines:
                        empty_line = True
                    else:
                        empty_line = False
                        
                    # 保存当前行
                    lines.append(line)
                    line = ""
                    
                    # 如果是空行，第二个回车，等待换行符并结束
                    if empty_line:
                        # 读取可能的换行符
                        if msvcrt.kbhit():
                            next_ch = msvcrt.getch()
                            if next_ch == b'\n':
                                pass  # 忽略LF
                        break
                    
                    continue
                
                # 处理LF（有些键盘可能直接发送\n）
                if ch == b'\n':
                    if last_was_cr:
                        # 这是CR后的LF，忽略
                        last_was_cr = False
                        continue
                    
                    # 单独的LF处理为回车
                    print()  # 打印换行
                    
                    # 如果是空行且已有内容，这是结束信号
                    if not line and lines:
                        break
                        
                    # 保存当前行
                    lines.append(line)
                    line = ""
                    continue
                
                # 不是回车键，重置标志
                last_was_cr = False
                
                # 控制字符 - 例如方向键、功能键等
                if ch < b' ':
                    continue
                
                # 其他可打印字符
                try:
                    ch_str = ch.decode('utf-8', errors='ignore')
                    line += ch_str
                    print(ch_str, end="", flush=True)
                except:
                    # 忽略无法解码的字符
                    pass
                
        except Exception as e:
            print(f"\n输入处理错误: {str(e)}")
            if lines or line:
                # 已有一些内容，返回现有内容
                if line:
                    lines.append(line)
                return "\n".join(lines)
            return ""
    else:
        # 非Windows平台使用基本的input方法，通过重复输入处理多行
        print("", end="", flush=True)  # 确保提示光标在正确位置
        
        while True:
            try:
                user_input = input()
                
                # 如果输入为空且已经有内容，结束输入
                if not user_input and lines:
                    break
                    
                # 保存输入行
                lines.append(user_input)
                
            except EOFError:
                break
            except KeyboardInterrupt:
                return ""
    
    # 如果当前行有内容，也添加到结果中
    if line:
        lines.append(line)
        
    # 合并所有输入行
    result = "\n".join(lines)
    return result

def _show_countdown(total_seconds: int, stop_event: threading.Event):
    """在单独线程中显示倒计时"""
    start_time = time.time()
    last_displayed = 0
    
    while not stop_event.is_set() and (time.time() - start_time) < total_seconds:
        remaining = total_seconds - int(time.time() - start_time)
        
        # 每5秒显示一次提示（或在剩余10秒内每秒显示）
        if (last_displayed - remaining >= 5) or (remaining <= 10 and last_displayed != remaining):
            if remaining > 1:
                print(f"\r等待用户输入... 还剩 {remaining} 秒    ", end="", flush=True)
            else:
                print(f"\r等待用户输入... 最后 {remaining} 秒    ", end="", flush=True)
            last_displayed = remaining
            
        time.sleep(0.5)
    
    # 清除倒计时行
    if not stop_event.is_set():
        print("\r" + " " * 40 + "\r", end="", flush=True)

class TimerThread(threading.Thread):
    """可停止的计时器线程，确保超时触发"""
    
    # 跟踪全局活跃线程
    active_threads = []
    
    def __init__(self, timeout, callback):
        super().__init__(daemon=True)  # 设置为守护线程
        self.timeout = timeout
        self.callback = callback
        self.stopped = threading.Event()
        # 跟踪全局线程列表
        TimerThread.active_threads.append(self)
            
    def run(self):
        """线程主循环，实现定时器功能"""
        start_time = time.time()
        while not self.stopped.is_set():
            if time.time() - start_time > self.timeout:
                if self.callback:
                    self.callback()
                break
            time.sleep(0.1)  # 睡眠以降低CPU使用率
        # 从跟踪列表中移除自己
        if self in TimerThread.active_threads:
            TimerThread.active_threads.remove(self)
            
    def stop(self):
        """停止计时器线程"""
        self.stopped.set()
        # 从跟踪列表中移除自己
        if self in TimerThread.active_threads:
            TimerThread.active_threads.remove(self)
            
    @staticmethod
    def cleanup_timer_threads():
        """清理所有活跃的TimerThread实例"""
        for thread in list(TimerThread.active_threads):
            try:
                thread.stop()
            except:
                pass
        TimerThread.active_threads.clear()

# 取消当前活跃的输入任务的简化版本
def cancel_active_input():
    """
    简化版取消函数 - 保留此函数仅为了保持API兼容性
    新的get_user_input_async已不再需要使用此函数
    """
    print("📢 说明: 输入系统已简化，不需要手动取消")
    return

# 定义一个简单的超时输入函数
async def get_user_input_async(prompt: str, timeout: int = 30) -> Optional[str]:
    """
    异步获取用户输入，支持超时
    
    Args:
        prompt: 提示用户的文本
        timeout: 等待用户输入的最大秒数，默认30秒
        
    Returns:
        用户输入的文本，如果超时则返回None
    """
    # 显示提示
    print("\n" + "="*50)
    print(f"{prompt}")
    print(f"请在{timeout}秒内输入，超时将自动继续")
    print("="*50)
    
    # 使用线程运行阻塞的input函数
    def user_input():
        try:
            return input()
        except:
            return None
    
    # 创建事件循环
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    
    # 执行输入
    try:
        with concurrent.futures.ThreadPoolExecutor() as executor:
            # 创建输入任务
            future = loop.run_in_executor(executor, user_input)
            
            # 等待输入或超时
            try:
                result = await asyncio.wait_for(future, timeout)
                return result
            except asyncio.TimeoutError:
                print(f"\n输入超时，系统将继续执行")
                return None
    except Exception as e:
        print(f"\n输入出错: {str(e)}")
        return None

# 测试函数
async def test_input():
    result = await get_user_input_async("这是一个测试提示，请输入一些内容", 10)
    print(f"测试结果: {result}")

# 允许直接运行此文件进行测试
if __name__ == "__main__":
    print("测试输入工具...")
    asyncio.run(test_input()) 