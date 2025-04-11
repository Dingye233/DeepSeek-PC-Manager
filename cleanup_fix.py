修改后的cleanup_thread_pools函数
def cleanup_thread_pools():
    """清理线程池和资源"""
    print_info(\
开始清理线程池和资源...\)
    
    try:
        # 使用input_utils中的清理函数
        from input_utils import cleanup_thread_pools as input_cleanup
        input_cleanup()
        
        # 清理所有模块中的线程池
        import sys
        for module_name in list(sys.modules.keys()):
            module = sys.modules[module_name]
            if hasattr(module, 'executor') and hasattr(module.executor, 'shutdown'):
                try:
                    module.executor.shutdown(wait=False)
                except:
                    pass
    except Exception as e:
        print_error(f\
清理线程池时出错:
str(e)
\)
    
    print_info(\
资源清理完成\)
