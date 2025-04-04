import asyncio
import sys
import time
import threading
import signal
from typing import Optional, Tuple

# 用于存储全局状态的变量
_input_state = {"received": False, "value": None, "cancel_requested": False}

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

async def get_user_input_async(prompt: str, timeout: int = 30) -> Optional[str]:
    """
    增强版异步获取用户输入，支持超时和可视化倒计时
    
    Args:
        prompt: 提示用户的文本
        timeout: 等待用户输入的最大秒数，默认30秒
        
    Returns:
        用户输入的文本，如果超时则返回None
    """
    # 重置状态
    _input_state["received"] = False
    _input_state["value"] = None
    _input_state["cancel_requested"] = False
    
    # 创建停止事件用于控制倒计时线程
    countdown_stop = threading.Event()
    
    # 突出显示提示，增加用户注意度
    print("\n" + "="*50)
    print(f"⏰ {prompt}")
    print(f"⌛ 请在{timeout}秒内输入，按回车确认")
    print(f"💡 提示: 确保输入后按下回车键")
    print("="*50)
    sys.stdout.flush()  # 确保提示消息立即显示
    
    # 启动倒计时显示线程
    countdown_thread = None
    if timeout > 5:  # 只在超时设置大于5秒时显示倒计时
        countdown_thread = threading.Thread(
            target=_show_countdown, 
            args=(timeout, countdown_stop)
        )
        countdown_thread.daemon = True
        countdown_thread.start()
    
    try:
        # 记录开始等待输入的时间
        start_time = time.time()
        
        # 简化的事件循环处理 - 统一使用get_running_loop或创建新循环
        try:
            try:
                # 首先尝试获取当前运行的事件循环
                loop = asyncio.get_running_loop()
            except RuntimeError:
                # 如果没有运行中的循环，创建一个新的
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
            
            # 执行输入任务
            input_task = loop.run_in_executor(None, lambda: input(""))
            result = await asyncio.wait_for(input_task, timeout=timeout)
            
        except (RuntimeError, OSError) as e:
            # 如果上述方法失败，使用简单的阻塞输入作为后备
            print(f"\n事件循环输入方法失败: {str(e)}")
            print("使用备用输入方法，请输入:")
            
            # 备用方法使用简单的阻塞输入
            result = input("")
        
        # 停止倒计时线程
        countdown_stop.set()
        if countdown_thread and countdown_thread.is_alive():
            countdown_thread.join(1)  # 等待倒计时线程结束，最多1秒
        
        # 记录实际接收到输入的时间
        elapsed_time = time.time() - start_time
        
        # 输入确认信息
        if result:
            print(f"\n✅ 成功接收到输入: '{result}' (耗时: {elapsed_time:.2f}秒)")
            _input_state["received"] = True
            _input_state["value"] = result
        else:
            print("\n⚠️ 接收到空输入 (用户只按了回车)")
            _input_state["received"] = True
            _input_state["value"] = ""
            
        return result
        
    except asyncio.TimeoutError:
        # 停止倒计时线程
        countdown_stop.set()
        if countdown_thread and countdown_thread.is_alive():
            countdown_thread.join(1)
            
        elapsed_time = time.time() - start_time
        print(f"\n⏱️ 输入超时 (已等待: {elapsed_time:.2f}秒)，继续执行...")
        return None
        
    except Exception as e:
        # 停止倒计时线程
        countdown_stop.set()
        if countdown_thread and countdown_thread.is_alive():
            countdown_thread.join(1)
            
        print(f"\n❌ 获取用户输入时出错: {str(e)}")
        print("尝试最简单的输入方法...")
        
        # 最后的备用方法：直接使用阻塞输入
        try:
            print("\n请重新输入:")
            result = input("")
            print(f"接收到: {result}")
            return result
        except Exception as backup_error:
            print(f"所有输入方法均失败: {str(backup_error)}")
            return None
            
    finally:
        # 确保停止倒计时线程
        countdown_stop.set()

# 测试函数
async def test_input():
    result = await get_user_input_async("这是一个测试提示，请输入一些内容", 30)
    print(f"测试结果: {result}")

# 允许直接运行此文件进行测试
if __name__ == "__main__":
    print("测试输入工具...")
    asyncio.run(test_input()) 