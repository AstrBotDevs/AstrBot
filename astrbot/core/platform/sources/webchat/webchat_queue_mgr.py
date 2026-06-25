# 导入 asyncio 模块，用于异步编程，支持协程、事件循环和异步队列等
import asyncio
# 从 collections.abc 模块导入类型提示 Awaitable 和 Callable，用于类型注解
from collections.abc import Awaitable, Callable

# 从 astrbot 包导入 logger 对象，用于记录日志
from astrbot import logger


# 定义一个 WebChat 队列管理器类，用于管理 WebChat 中的异步消息队列
class WebChatQueueMgr:
    # 初始化方法，创建队列管理器实例
    def __init__(self, queue_maxsize: int = 128, back_queue_maxsize: int = 512) -> None:
        # 存储对话ID到异步队列的映射，用于存放用户输入消息的队列
        self.queues: dict[str, asyncio.Queue] = {}
        """Conversation ID to asyncio.Queue mapping"""
        # 存储请求ID到异步队列的映射，用于存放对应响应的队列（回传队列）
        self.back_queues: dict[str, asyncio.Queue] = {}
        """Request ID to asyncio.Queue mapping for responses"""
        # 存储对话ID到其所有关联的请求ID集合的映射，用于追踪对话下的活跃请求
        self._conversation_back_requests: dict[str, set[str]] = {}
        # 存储请求ID到其所属对话ID的映射，用于快速查找请求所属对话
        self._request_conversation: dict[str, str] = {}
        # 存储对话ID到asyncio.Event的映射，用于通知监听器停止工作
        self._queue_close_events: dict[str, asyncio.Event] = {}
        # 存储对话ID到asyncio.Task的映射，用于管理每个对话的监听器协程任务
        self._listener_tasks: dict[str, asyncio.Task] = {}
        # 存储监听器回调函数，当队列有新消息时调用此异步回调处理消息
        self._listener_callback: Callable[[tuple], Awaitable[None]] | None = None
        # 设置输入队列的最大容量
        self.queue_maxsize = queue_maxsize
        # 设置回传队列的最大容量
        self.back_queue_maxsize = back_queue_maxsize

    # 获取或创建指定对话ID的输入队列
    def get_or_create_queue(self, conversation_id: str) -> asyncio.Queue:
        """Get or create a queue for the given conversation ID"""
        # 检查该对话ID是否已经有对应的队列
        if conversation_id not in self.queues:
            # 如果没有，则创建一个新的异步队列，并设置最大容量
            self.queues[conversation_id] = asyncio.Queue(maxsize=self.queue_maxsize)
            # 同时为该对话创建一个关闭事件，用于后续停止监听器
            self._queue_close_events[conversation_id] = asyncio.Event()
            # 启动监听器（如果需要且回调已设置）
            self._start_listener_if_needed(conversation_id)
        # 返回该对话ID对应的队列
        return self.queues[conversation_id]

    # 获取或创建指定请求ID的回传队列（可关联到对话）
    def get_or_create_back_queue(
        self,
        request_id: str,
        conversation_id: str | None = None,
    ) -> asyncio.Queue:
        """Get or create a back queue for the given request ID"""
        # 检查该请求ID是否已经有对应的回传队列
        if request_id not in self.back_queues:
            # 如果没有，则创建一个新的异步回传队列，并设置最大容量
            self.back_queues[request_id] = asyncio.Queue(
                maxsize=self.back_queue_maxsize
            )
        # 如果提供了对话ID，则进行关联映射
        if conversation_id:
            # 记录该请求ID属于哪个对话
            self._request_conversation[request_id] = conversation_id
            # 如果该对话ID在反向请求映射中不存在，则初始化一个空集合
            if conversation_id not in self._conversation_back_requests:
                self._conversation_back_requests[conversation_id] = set()
            # 将该请求ID添加到对话的活跃请求集合中
            self._conversation_back_requests[conversation_id].add(request_id)
        # 返回该请求ID对应的回传队列
        return self.back_queues[request_id]

    # 移除指定请求ID的回传队列及其关联关系
    def remove_back_queue(self, request_id: str):
        """Remove back queue for the given request ID"""
        # 从回传队列字典中删除该请求ID的队列，如果不存在则忽略
        self.back_queues.pop(request_id, None)
        # 从请求到对话的映射中取出该请求ID对应的对话ID
        conversation_id = self._request_conversation.pop(request_id, None)
        # 如果存在关联的对话ID
        if conversation_id:
            # 获取该对话ID下的所有请求ID集合
            request_ids = self._conversation_back_requests.get(conversation_id)
            # 如果集合存在
            if request_ids is not None:
                # 从集合中移除该请求ID
                request_ids.discard(request_id)
                # 如果移除后集合为空，说明该对话没有活跃请求了
                if not request_ids:
                    # 从反向请求映射中删除该对话ID的条目，清理内存
                    self._conversation_back_requests.pop(conversation_id, None)

    # 移除指定对话ID的所有队列，包括其关联的所有回传队列和自身队列
    def remove_queues(self, conversation_id: str) -> None:
        """Remove queues for the given conversation ID"""
        # 遍历该对话下所有活跃的请求ID列表的副本，防止在迭代中修改集合
        for request_id in list(
            self._conversation_back_requests.get(conversation_id, set())
        ):
            # 调用 remove_back_queue 方法移除每个关联的请求回传队列
            self.remove_back_queue(request_id)
        # 从反向请求映射中删除该对话ID的条目（可能在循环中已被删除，此处确保清理）
        self._conversation_back_requests.pop(conversation_id, None)
        # 调用 remove_queue 方法移除该对话的输入队列和监听器
        self.remove_queue(conversation_id)

    # 移除指定对话ID的输入队列和监听器
    def remove_queue(self, conversation_id: str):
        """Remove input queue and listener for the given conversation ID"""
        # 从队列字典中删除该对话ID的输入队列
        self.queues.pop(conversation_id, None)

        # 从关闭事件字典中取出并删除该对话ID对应的关闭事件
        close_event = self._queue_close_events.pop(conversation_id, None)
        # 如果关闭事件存在
        if close_event is not None:
            # 设置该事件，通知所有等待此事件的监听器停止运行
            close_event.set()

        # 从监听器任务字典中取出并删除该对话ID对应的监听器协程任务
        task = self._listener_tasks.pop(conversation_id, None)
        # 如果任务存在且未完成
        if task is not None:
            # 取消该协程任务的执行
            task.cancel()

    # 列出指定对话ID下所有活跃的回传请求ID
    def list_back_request_ids(self, conversation_id: str) -> list[str]:
        """List active back-queue request IDs for a conversation."""
        # 返回该对话ID对应的请求ID集合的列表形式，如果不存在则返回空列表
        return list(self._conversation_back_requests.get(conversation_id, set()))

    # 检查指定对话ID是否存在输入队列
    def has_queue(self, conversation_id: str) -> bool:
        """Check if a queue exists for the given conversation ID"""
        # 判断该对话ID是否在队列字典的键中
        return conversation_id in self.queues

    # 设置监听器回调函数，并为所有已有对话启动监听任务
    def set_listener(
        self,
        callback: Callable[[tuple], Awaitable[None]],
    ):
        # 存储传入的回调函数，用于后续处理队列中的消息
        self._listener_callback = callback
        # 遍历当前所有已有队列的对话ID列表
        for conversation_id in list(self.queues.keys()):
            # 为每个对话启动监听任务（如果尚未启动）
            self._start_listener_if_needed(conversation_id) # 启动监听任务

    # 清除监听器，停止所有监听任务并清理相关事件
    async def clear_listener(self) -> None:
        # 将监听器回调设置为 None，后续消息将不会被处理
        self._listener_callback = None
        # 获取所有关闭事件的列表副本，并遍历
        for close_event in list(self._queue_close_events.values()):
            # 设置每个关闭事件，通知监听任务退出
            close_event.set()
        # 清空关闭事件字典
        self._queue_close_events.clear()

        # 获取所有监听器任务的列表副本
        listener_tasks = list(self._listener_tasks.values())
        # 遍历所有监听器任务
        for task in listener_tasks:
            # 取消任务
            task.cancel()
        # 如果存在被取消的任务
        if listener_tasks:
            # 等待所有任务完成取消或抛出异常，并忽略这些异常
            await asyncio.gather(*listener_tasks, return_exceptions=True)
        # 清空监听器任务字典
        self._listener_tasks.clear()

    # 如果需要，为指定对话启动监听器任务（内部方法）
    def _start_listener_if_needed(self, conversation_id: str):
        # 如果监听器回调尚未设置，则直接返回，无法启动监听
        if self._listener_callback is None:
            return
        # 检查该对话是否已有监听器任务
        if conversation_id in self._listener_tasks:
            # 获取已有任务
            task = self._listener_tasks[conversation_id]
            # 如果任务未完成，说明已在运行，直接返回
            if not task.done():
                return
        # 获取该对话的输入队列
        queue = self.queues.get(conversation_id)
        # 获取该对话的关闭事件
        close_event = self._queue_close_events.get(conversation_id)
        # 如果队列或关闭事件不存在，则无法监听，直接返回
        if queue is None or close_event is None:
            return
        # 创建一个异步任务来运行监听协程 _listen_to_queue
        task = asyncio.create_task(
            # TODO 监听消息队列
            self._listen_to_queue(conversation_id, queue, close_event), # 监听消息队列
            # 为任务指定一个有意义的名字，方便调试
            name=f"webchat_listener_{conversation_id}",
        )
        # 将创建的任务保存到监听器任务字典中
        self._listener_tasks[conversation_id] = task
        # 为任务添加一个完成后的回调，用于自动清理
        task.add_done_callback(
            # 当任务完成（无论成功或异常）时，从字典中移除该任务的条目
            lambda _: self._listener_tasks.pop(conversation_id, None)
        )
        # 记录调试日志，表示监听器已启动
        logger.debug(f"Started listener for conversation: {conversation_id}")

    # 监听指定对话队列的内部协程，持续从队列中获取消息并交给回调处理
    async def _listen_to_queue(
        self,
        conversation_id: str,
        queue: asyncio.Queue,
        close_event: asyncio.Event,
    ):
        # 无限循环，持续监听队列
        while True:
            # TODO 创建一个任务，用于从队列中获取消息（这是一个异步操作，会挂起直到有消息），有消息进来时，会返回该消息
            get_task = asyncio.create_task(queue.get())
            # 创建一个任务，用于等待关闭事件被触发
            close_task = asyncio.create_task(close_event.wait())
            try:
                # 同时等待 get_task 和 close_task，返回第一个完成的任务集合
                done, pending = await asyncio.wait(
                    {get_task, close_task},
                    return_when=asyncio.FIRST_COMPLETED,
                )
                # 取消所有未完成的任务，避免资源泄露（例如，如果 get_task 先完成，则取消 close_task）
                for task in pending:
                    task.cancel()
                # 如果关闭事件任务在完成的集合中，表示需要终止监听
                if close_task in done:
                    # 跳出循环，结束协程
                    break
                # 如果 get_task 先完成，则获取队列中的数据
                data = get_task.result()
                # 在调用回调前，再次检查回调是否还存在（可能在等待期间被清除）
                if self._listener_callback is None:
                    # 如果回调不存在，则跳过处理，继续下一次循环
                    continue
                try:
                    # TODO 调用监听器回调函数处理获取到的数据，这是一个异步调用
                    await self._listener_callback(data)
                except Exception as e:
                    # 捕获并记录回调函数中发生的任何异常，避免监听任务崩溃
                    logger.error(
                        f"Error processing message from conversation {conversation_id}: {e}"
                    )
            except asyncio.CancelledError:
                # 如果当前协程被取消，则退出循环
                break
            finally:
                # 确保在每次循环结束时清理任务，防止资源泄露
                # 如果 get_task 还未完成（例如因取消循环），则取消它
                if not get_task.done():
                    get_task.cancel()
                # 如果 close_task 还未完成，则取消它
                if not close_task.done():
                    close_task.cancel()


# 创建一个 WebChatQueueMgr 类的全局单例实例
webchat_queue_mgr = WebChatQueueMgr()