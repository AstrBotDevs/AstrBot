""" exception hook """

import traceback
import multiprocessing
import threading
import inspect
import sys
from rich.console import Console
from rich.text import Text
from rich.panel import Panel

console = Console()

def format_stack_trace(exctype, value, tb, max_depth=15, nested=False) -> Text:
    tb_list = traceback.extract_tb(tb)
    exception_info = Text()

    if nested:
        exception_info.append(f"{exctype.__name__}: {value}\n", style="bold red")
    else:
        # 获取当前进程和线程名称
        process_name = multiprocessing.current_process().name
        thread_name = threading.current_thread().name
        exception_info.append(
            f"Exception in process: {process_name}, thread: {thread_name}; {exctype.__name__}: {value}\n",
            style="bold red"
        )
        exception_info.append("Traceback (most recent call last):\n", style="bold")

    # 限制堆栈跟踪的深度
    limited_tb_list = tb_list[:max_depth]
    more_frames = len(tb_list) - max_depth

    for i, (filename, lineno, funcname, line) in enumerate(limited_tb_list):
        # 获取函数所在的模块名
        module_name = inspect.getmodulename(filename)
        exception_info.append(
            f"  at {module_name}.{funcname} in ({filename}:{lineno})\n",
            style="yellow"
        )

    if more_frames > 0:
        exception_info.append(f"  ... {more_frames} more ...\n", style="dim")

    # 检查是否有原因和其他信息
    cause = getattr(value, '__cause__', None)
    context = getattr(value, '__context__', None)
    
    if cause:
        exception_info.append("Caused by: \n", style="bold red")
        exception_info.append(format_stack_trace(type(cause), cause, cause.__traceback__, nested=True))
    if context and not cause:
        exception_info.append("Original exception: \n", style="bold red")
        exception_info.append(format_stack_trace(type(context), context, context.__traceback__, nested=True))
    
    return exception_info

def ExtractException(exctype, value, tb, panel: bool = True, rich_printable: bool = False) -> Text | Panel | None:
    """
    - panel: 是否以Panel形式返回异常信息
    - rich_printable: 是否以可打印的格式返回异常信息 (把rich转换为普通print或者 stdout | stderr等控制台输出有效果的格式)
    """
    # 获取回溯信息并格式化为字符串
    _exc_info = None
    if all(x is None for x in (exctype, value, tb)):
        return None
    tb_str = format_stack_trace(exctype, value, tb)
    # 返回异常信息
    if panel:
        _exc_info = Panel(tb_str, title="[bold red]Exception Occurred[/bold red]", border_style="red")
    if rich_printable:
        with console.capture() as capture:
            console.print(_exc_info)
        return capture.get()
    return tb_str

def sys_excepthook(exctype, value, tb):
    # 获取异常信息并打印到控制台
    exception_info = ExtractException(exctype, value, tb , panel=True)
    if exception_info:
        console.print(exception_info)

def set_exechook():
    """
    设置全局异常处理函数
    """
    sys.excepthook = sys_excepthook

def GetStackTrace(vokedepth: int = 1) -> str:
    """
    获取堆栈跟踪信息
    """
    # 获取当前调用栈信息的前两层
    stack = traceback.extract_stack(limit=vokedepth)
    stack_info = Text("Stack Trace:\n", style="bold")
    for frame in stack[:-vokedepth+1]:
        filename = frame.filename
        line = frame.lineno
        funcname = frame.name
        stack_info.append(f"  at {funcname} in ({filename}:{line})\n", style="yellow")
    return stack_info

if __name__ == '__main__':
    
    set_exechook()
