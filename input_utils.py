import asyncio
import sys
import time
import threading
import signal
import concurrent.futures
from typing import Optional, List, Tuple, Dict, Any
import os
import logging
import weakref
import atexit

# 设置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("input_system")

# 设置第三方库的日志级别更高，以隐藏不必要的消息
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)
logging.getLogger("requests").setLevel(logging.WARNING)
logging.getLogger("asyncio").setLevel(logging.WARNING)
logging.getLogger("openai").setLevel(logging.WARNING)  # 禁止OpenAI库的INFO级别日志
logging.getLogger("openai._base_client").setLevel(logging.WARNING)  # 特别禁止基础客户端的日志

# 检测是否为Windows平台
IS_WINDOWS = sys.platform.startswith('win')

# 在Windows平台上导入特定模块
if IS_WINDOWS:
    try:
        import msvcrt
    except ImportError:
        logger.warning("无法导入msvcrt模块，可能影响Windows平台某些功能")

# 全局资源管理 - 简化版本
class ResourceManager:
    """资源管理器，确保所有资源可以正确清理"""
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(ResourceManager, cls).__new__(cls)
            cls._instance._initialize()
        return cls._instance
    
    def _initialize(self):
        """初始化资源管理器"""
        # 使用单一全局线程池而不是多个
        self._thread_pool = concurrent.futures.ThreadPoolExecutor(max_workers=2)
        self._timer_threads = set()  # 简单集合而非弱引用集合，减少开销
        self._cleanup_registered = False
        
        # 只在第一次初始化时注册清理函数
        if not self._cleanup_registered:
            atexit.register(self.cleanup_all)
            self._setup_signal_handlers()
            self._cleanup_registered = True
    
    def _setup_signal_handlers(self):
        """设置信号处理器以确保资源清理"""
        try:
            # 只处理最关键的信号
            for sig in [signal.SIGINT, signal.SIGTERM]:
                old_handler = signal.getsignal(sig)
                
                def handler(signum, frame, old_handler=old_handler):
                    self.cleanup_all()
                    if callable(old_handler) and old_handler not in (signal.SIG_IGN, signal.SIG_DFL):
                        old_handler(signum, frame)
                    elif old_handler == signal.SIG_DFL:
                        signal.default_int_handler(signum, frame)
                
                signal.signal(sig, handler)
        except Exception:
            pass  # 简化错误处理
    
    def get_thread_pool(self):
        """获取全局线程池"""
        return self._thread_pool
    
    def register_timer_thread(self, timer):
        """注册计时器线程"""
        self._timer_threads.add(timer)
        return timer
    
    def cleanup_thread_pools(self):
        """清理线程池"""
        if hasattr(self, '_thread_pool') and self._thread_pool:
            try:
                self._thread_pool.shutdown(wait=False)
                self._thread_pool = None
            except Exception:
                pass
    
    def cleanup_timer_threads(self):
        """清理所有计时器线程"""
        for timer in list(self._timer_threads):
            try:
                if hasattr(timer, 'stop'):
                    timer.stop()
            except Exception:
                pass
        self._timer_threads.clear()
    
    def cleanup_all(self):
        """清理所有注册的资源"""
        self.cleanup_timer_threads()
        self.cleanup_thread_pools()


# 全局资源管理器实例
_resource_manager = ResourceManager()

def get_thread_pool(max_workers=None):
    """获取线程池，使用全局共享的线程池"""
    # 忽略max_workers参数，始终使用全局池
    return _resource_manager.get_thread_pool()


class SafeTimer:
    """安全可靠的计时器实现，防止资源泄漏"""
    
    def __init__(self, timeout, callback):
        self.timeout = timeout
        self.callback = callback
        self.stopped = threading.Event()
        self._start_time = None
        self._thread = None
    
    def start(self):
        """启动计时器"""
        if self._thread is not None:
            return False
        
        self._start_time = time.time()
        self._thread = threading.Thread(
            target=self._run, 
            daemon=True
        )
        self._thread.start()
        
        # 注册到资源管理器
        _resource_manager.register_timer_thread(self)
        return True
    
    def _run(self):
        """线程主循环，实现定时器功能"""
        while not self.stopped.is_set():
            if time.time() - self._start_time > self.timeout:
                if self.callback and not self.stopped.is_set():
                    try:
                        self.callback()
                    except Exception:
                        pass  # 简化错误处理
                break
            
            # 使用较短的等待时间，以便快速响应停止请求
            self.stopped.wait(0.2)  # 增加间隔时间减少CPU使用
    
    def stop(self):
        """停止计时器"""
        self.stopped.set()


# 自定义输入函数，解决标准input()无法接收多行输入的问题
def custom_input():
    """自定义输入函数，支持多行输入"""
    lines = []
    line = ""
    while True:
        char = sys.stdin.read(1)
        if char == '\n':
            if line.strip() == "":  # 空行表示输入结束
                break
            lines.append(line)
            line = ""
        else:
            line += char
    return "\n".join(lines)


def _show_countdown(total_seconds: int, stop_event: threading.Event):
    """在单独线程中显示倒计时"""
    try:
        start_time = time.time()
        last_displayed = 0
        
        while not stop_event.is_set() and (time.time() - start_time) < total_seconds:
            remaining = total_seconds - int(time.time() - start_time)
            
            # 减少更新频率，每10秒显示一次提示（或在剩余10秒内每2秒显示）
            if (last_displayed - remaining >= 10) or (remaining <= 10 and last_displayed - remaining >= 2):
                if remaining > 1:
                    print(f"\r等待用户输入... 还剩 {remaining} 秒    ", end="", flush=True)
                else:
                    print(f"\r等待用户输入... 最后 {remaining} 秒    ", end="", flush=True)
                last_displayed = remaining
                
            # 使用等待而不是sleep，以便能快速响应停止事件
            stop_event.wait(0.5)  # 增加间隔时间减少CPU使用
        
        # 清除倒计时行
        if not stop_event.is_set():
            print("\r" + " " * 40 + "\r", end="", flush=True)
    except Exception:
        pass  # 简化错误处理


async def _get_input_in_thread(loop, stop_event, result_future):
    """
    在线程中获取用户输入，此函数在线程池中运行
    使用较低级别的输入机制以确保在高压力下也能工作
    """
    try:
        # 简化逻辑，直接使用标准输入方式
        user_input = input()
        
        # 安全地设置结果
        if not stop_event.is_set() and not result_future.done():
            loop.call_soon_threadsafe(result_future.set_result, user_input)
    except Exception as e:
        if not stop_event.is_set() and not result_future.done():
            loop.call_soon_threadsafe(result_future.set_exception, e)


# 取消当前活跃的输入任务的函数 - 已弃用但保持兼容性
def cancel_active_input():
    """
    此功能已弃用，仅为保持兼容性
    """
    # 在新实现中，输入会在超时后自动取消
    print("📢 输入取消请求已记录，但输入系统已重新设计，不需要手动取消")
    return True


# 加强版的异步用户输入函数
async def get_user_input_async(prompt: str, timeout: int = 30) -> Optional[str]:
    """
    异步获取用户输入，支持超时和取消
    
    Args:
        prompt: 提示用户的文本
        timeout: 等待用户输入的最大秒数，默认30秒
        
    Returns:
        用户输入的文本，如果超时则返回None
    """
    # 安全打印提示
    try:
        print(f"\n{prompt}")
        print(f"(等待用户输入，{timeout}秒后自动继续...)")
    except Exception:
        print("\n等待用户输入...")
    
    # 如果没有事件循环，创建一个
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        # 如果没有运行中的循环，创建一个新的
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    
    # 创建结果Future和停止事件
    result_future = loop.create_future()
    stop_event = threading.Event()
    
    # 简化倒计时函数，不再实时显示剩余时间，避免CPU占用
    countdown_stop_event = threading.Event()
    
    # 启动倒计时线程
    countdown_thread = threading.Thread(
        target=_show_countdown,
        args=(timeout, countdown_stop_event),
        daemon=True
    )
    countdown_thread.start()
    
    # 定义在线程中执行的输入函数
    def threaded_input():
        try:
            # 简单地调用input()获取用户输入
            user_input = input()
            
            # 安全地设置结果
            if not stop_event.is_set() and not result_future.done():
                loop.call_soon_threadsafe(result_future.set_result, user_input)
        except Exception as e:
            # 如果发生异常，将异常传递给Future
            if not stop_event.is_set() and not result_future.done():
                loop.call_soon_threadsafe(result_future.set_exception, e)
    
    # 获取线程池并提交输入任务
    executor = get_thread_pool()
    try:
        # 在线程池中执行输入操作
        input_thread = threading.Thread(target=threaded_input, daemon=True)
        input_thread.start()
        
        # 创建超时计时器
        def timeout_callback():
            if not result_future.done():
                loop.call_soon_threadsafe(result_future.set_result, None)
            stop_event.set()
        
        # 使用简单的计时器而非SafeTimer
        timer = threading.Timer(timeout, timeout_callback)
        timer.daemon = True
        timer.start()
        
        # 等待结果
        try:
            # 使用asyncio.wait_for等待Future完成，支持超时
            result = await asyncio.wait_for(result_future, timeout)
            return result
        except asyncio.CancelledError:
            # 如果任务被取消，确保资源释放
            stop_event.set()
            return None
        except asyncio.TimeoutError:
            # 超时处理
            return None
        finally:
            # 无论如何停止倒计时和计时器
            countdown_stop_event.set()
            
            # 停止计时器
            timer.cancel()
            
            # 等待输入线程结束
            try:
                stop_event.set()
            except Exception:
                pass
    except Exception as e:
        print(f"获取用户输入时出错: {str(e)}")
        return None


# 询问用户是否继续的函数 - 高可靠性版本
async def ask_user_to_continue(planning_messages, is_task_complete=None):
    """
    询问用户是否继续尝试任务，即使智能体认为无法完成
    
    Args:
        planning_messages: 当前对话消息列表
        is_task_complete: 任务是否完成的标志（保留参数兼容性）
    
    Returns:
        用户的选择: 继续尝试/终止
    """
    try:
        # 安全打印突出显示的文本
        def print_highlight(text):
            try:
                print(f"\033[1;33m{text}\033[0m", flush=True)
            except:
                print(text, flush=True)
        
        print_highlight("\n===== 等待用户决策 =====")
        print_highlight("请输入您的想法或指示，按回车键提交")
        print_highlight("===========================")
        
        prompt = """
任务执行遇到困难，请选择:
1. 继续尝试 (直接输入建议或按回车)
2. 终止任务 (输入数字2或"终止")

您的选择是: """
        
        # 修复：直接调用异步函数并等待结果
        user_choice = await get_user_input_async(prompt, 60)
            
        # 如果用户输入超时，默认继续执行
        if user_choice is None:
            # 默认继续尝试而非终止
            planning_messages.append({
                "role": "user", 
                "content": "用户输入超时，系统默认继续尝试。请采用全新思路寻找解决方案。"
            })
            return "继续尝试"  # 返回默认值表示继续尝试
                
        # 用户提供了明确输入
        if user_choice.strip().lower() in ["2", "终止", "停止", "结束", "放弃", "取消", "quit", "exit", "stop", "terminate", "cancel"]:
            # 用户选择终止任务
            planning_messages.append({
                "role": "user", 
                "content": f"用户选择终止当前任务。请总结已完成的工作和遇到的主要问题，然后结束任务。"
            })
            return "终止"
        else:
            # 用户选择继续或提供了其他建议
            planning_messages.append({
                "role": "user", 
                "content": f"用户希望继续尝试解决问题，并提供了以下反馈/建议：\n\"{user_choice}\"\n\n请考虑用户的输入，采用合适的方法继续解决问题。可以尝试新思路或按用户建议调整方案。"
            })
            return user_choice or "继续尝试"  # 如果是空字符串也返回"继续尝试"
                
    except asyncio.CancelledError:
        # 清理资源并重新抛出异常
        raise
            
    except Exception as e:
        # 获取用户输入失败时的处理，默认继续执行
        print(f"错误: {str(e)}")
        planning_messages.append({
            "role": "user", 
            "content": f"系统获取用户输入时出错: {str(e)}。默认继续尝试，请采用全新思路寻找解决方案。"
        })
        return "继续尝试"  # 返回默认值表示继续尝试


# 为了向后兼容，提供旧的函数名
def cleanup_thread_pools():
    """向后兼容函数：清理所有线程池"""
    # 直接调用而不打印日志
    _resource_manager.cleanup_thread_pools()


# 清理函数
def cleanup():
    """程序退出时调用的清理函数"""
    _resource_manager.cleanup_all()


# 注册退出清理
atexit.register(cleanup)


# 测试函数
async def test_input():
    result = await get_user_input_async("这是一个测试提示，请输入一些内容", 10)


# 允许直接运行此文件进行测试
if __name__ == "__main__":
    try:
        asyncio.run(test_input())
    finally:
        # 确保清理
        cleanup() 