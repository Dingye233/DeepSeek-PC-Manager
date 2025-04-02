import asyncio
from typing import Optional

async def get_user_input_async(prompt: str, timeout: int = 30) -> Optional[str]:
    """
    异步获取用户输入，支持超时
    
    Args:
        prompt: 提示用户的文本
        timeout: 等待用户输入的最大秒数，默认30秒
        
    Returns:
        用户输入的文本，如果超时则返回None
    """
    print(f"\n{prompt}")
    print(f"(等待用户输入，{timeout}秒后自动继续...)")
    
    try:
        # 创建一个任务来执行用户输入
        loop = asyncio.get_event_loop()
        input_task = loop.run_in_executor(None, input, "")
        
        # 等待任务完成，设置超时
        result = await asyncio.wait_for(input_task, timeout=timeout)
        return result
    except asyncio.TimeoutError:
        print(f"\n输入超时，继续执行...")
        return None
    except Exception as e:
        print(f"\n获取用户输入时出错: {str(e)}")
        return None 