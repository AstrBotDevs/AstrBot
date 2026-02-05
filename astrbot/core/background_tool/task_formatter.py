"""任务结果格式化器

提供统一的任务结果格式化函数，供LLM工具和通知系统使用。
"""

from .task_state import BackgroundTask


def build_task_result(
    task_id: str, task: BackgroundTask, output: str | None = None
) -> str:
    """构建任务结果的完整信息

    Args:
        task_id: 任务ID
        task: 任务对象
        output: 输出日志（可选）

    Returns:
        格式化的任务结果信息，包含：
        - 任务状态
        - 输出日志（如果提供）
        - 最终结果
        - 错误信息
        - 通知消息
    """
    status = task.status.value
    result_text = f"Task {task_id} ({task.tool_name}, {status}):\n"

    # 如果有输出日志，显示日志
    if output:
        result_text += f"\n{output}\n"

    # 如果任务已完成，显示最终结果
    if task.is_finished():
        if task.result:
            result_text += f"\n[FINAL RESULT]\n{task.result}"
        elif task.error:
            result_text += f"\n[ERROR]\n{task.error}"

    if not output and not task.is_finished():
        return f"Task {task_id} ({task.tool_name}, {status}): No output yet."

    return result_text
