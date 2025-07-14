"""
分段回复管理器

负责管理按会话独立的分段回复队列，确保每个会话的分段回复按顺序进行，
避免多个会话的分段回复相互干扰。
"""

import asyncio
import weakref
from typing import Dict, List, Optional
from dataclasses import dataclass
from astrbot.core import logger
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.message.message_event_result import MessageChain, BaseMessageComponent


@dataclass
class SegmentedReplyTask:
    """分段回复任务"""
    event: AstrMessageEvent
    decorated_comps: List[BaseMessageComponent]
    components: List[BaseMessageComponent]
    record_comps: List[BaseMessageComponent]


class SessionSegmentedReplyQueue:
    """单个会话的分段回复队列"""

    def __init__(self, session_id: str, manager: "SegmentedReplyManager"):
        self.session_id = session_id
        self.manager = weakref.ref(manager)  # 使用弱引用避免循环引用
        self.queue: asyncio.Queue = asyncio.Queue()
        self.worker_task: Optional[asyncio.Task] = None
        self.is_processing = False
        self.last_activity = asyncio.get_event_loop().time()

    async def enqueue(self, task: SegmentedReplyTask):
        """将分段回复任务加入队列"""
        self.last_activity = asyncio.get_event_loop().time()
        await self.queue.put(task)

        # 如果工作任务还没启动，启动它
        if self.worker_task is None or self.worker_task.done():
            self.worker_task = asyncio.create_task(self._worker())

    async def _worker(self):
        """处理队列中的分段回复任务"""
        try:
            while True:
                try:
                    # 等待任务，超时时间为30秒
                    task = await asyncio.wait_for(self.queue.get(), timeout=30.0)
                    self.is_processing = True
                    self.last_activity = asyncio.get_event_loop().time()

                    await self._process_segmented_reply(task)
                    self.queue.task_done()

                except asyncio.TimeoutError:
                    # 30秒没有新任务，退出工作协程
                    logger.debug(f"会话 {self.session_id} 的分段回复队列超时，停止工作协程")
                    break
                except Exception as e:
                    logger.error(f"处理会话 {self.session_id} 的分段回复时出错: {e}")
                    self.queue.task_done()
                finally:
                    self.is_processing = False

        except Exception as e:
            logger.error(f"会话 {self.session_id} 的分段回复工作协程出错: {e}")
        finally:
            # 通知管理器清理此队列
            manager = self.manager()
            if manager:
                await manager._cleanup_session(self.session_id)

    async def _process_segmented_reply(self, task: SegmentedReplyTask):
        """处理单个分段回复任务"""
        manager = self.manager()
        if not manager:
            return

        try:
            # 先发送语音组件
            for rcomp in task.record_comps:
                interval = await manager._calc_comp_interval(rcomp)
                await asyncio.sleep(interval)
                try:
                    await task.event.send(MessageChain([rcomp]))
                except Exception as e:
                    logger.error(f"发送语音消息失败: {e}")
                    return

            # 过滤空的组件
            valid_components = []
            for comp in task.components:
                if await self._is_valid_component(comp):
                    valid_components.append(comp)

            if not valid_components:
                # 如果没有有效组件，但有装饰组件，仍然发送装饰组件
                if task.decorated_comps:
                    try:
                        await task.event.send(MessageChain(task.decorated_comps))
                    except Exception as e:
                        logger.error(f"发送装饰消息失败: {e}")
                return

            # 分段发送有效组件
            decorated_comps = task.decorated_comps.copy()
            for i, comp in enumerate(valid_components):
                interval = await manager._calc_comp_interval(comp)
                await asyncio.sleep(interval)
                try:
                    # 第一条消息包含装饰组件
                    if i == 0 and decorated_comps:
                        await task.event.send(MessageChain([*decorated_comps, comp]))
                    else:
                        await task.event.send(MessageChain([comp]))
                except Exception as e:
                    logger.error(f"发送分段消息失败: {e}")
                    return

        except Exception as e:
            logger.error(f"处理分段回复任务时出错: {e}")

    async def _is_valid_component(self, comp: BaseMessageComponent) -> bool:
        """检查组件是否为有效（非空）组件"""
        import astrbot.core.message.components as Comp

        if isinstance(comp, Comp.Plain):
            return bool(comp.text and comp.text.strip())
        elif isinstance(comp, Comp.Image):
            return bool(comp.file)
        elif isinstance(comp, Comp.Record):
            return bool(comp.file)
        elif isinstance(comp, Comp.Video):
            return bool(comp.file)
        elif isinstance(comp, Comp.At):
            return bool(comp.qq) or bool(comp.name)
        elif isinstance(comp, Comp.Reply):
            return bool(comp.id) and comp.sender_id is not None
        elif isinstance(comp, Comp.File):
            return bool(comp.file_ or comp.url)
        else:
            # 对于其他类型的组件，默认认为有效
            return True


class SegmentedReplyManager:
    """分段回复管理器"""

    def __init__(self):
        self.session_queues: Dict[str, SessionSegmentedReplyQueue] = {}
        self.cleanup_task: Optional[asyncio.Task] = None
        self._interval_method = "random"
        self._interval = [1.5, 3.5]
        self._log_base = 2.0

    def initialize(self, interval_method: str, interval: List[float], log_base: float):
        """初始化配置参数"""
        self._interval_method = interval_method
        self._interval = interval
        self._log_base = log_base

        # 启动定期清理任务
        if self.cleanup_task is None or self.cleanup_task.done():
            self.cleanup_task = asyncio.create_task(self._periodic_cleanup())

    async def enqueue_segmented_reply(
        self,
        event: AstrMessageEvent,
        decorated_comps: List[BaseMessageComponent],
        components: List[BaseMessageComponent],
        record_comps: List[BaseMessageComponent]
    ):
        """将分段回复任务加入对应会话的队列"""
        session_id = event.unified_msg_origin

        # 获取或创建会话队列
        if session_id not in self.session_queues:
            self.session_queues[session_id] = SessionSegmentedReplyQueue(session_id, self)
            logger.debug(f"为会话 {session_id} 创建分段回复队列")

        queue = self.session_queues[session_id]
        task = SegmentedReplyTask(
            event=event,
            decorated_comps=decorated_comps,
            components=components,
            record_comps=record_comps
        )

        await queue.enqueue(task)
        logger.debug(f"分段回复任务已加入会话 {session_id} 的队列")

    async def _calc_comp_interval(self, comp: BaseMessageComponent) -> float:
        """计算组件发送间隔时间"""
        import random
        import math
        import astrbot.core.message.components as Comp

        if self._interval_method == "log":
            if isinstance(comp, Comp.Plain):
                # 统计字数
                text = comp.text
                if all(ord(c) < 128 for c in text):
                    word_count = len(text.split())
                else:
                    word_count = len([c for c in text if c.isalnum()])

                interval = math.log(word_count + 1, self._log_base)
                return random.uniform(interval, interval + 0.5)
            else:
                return random.uniform(1, 1.75)
        else:
            # random 模式
            return random.uniform(self._interval[0], self._interval[1])

    async def _cleanup_session(self, session_id: str):
        """清理指定会话的队列"""
        if session_id in self.session_queues:
            queue = self.session_queues[session_id]
            if queue.worker_task and not queue.worker_task.done():
                queue.worker_task.cancel()
            del self.session_queues[session_id]
            logger.debug(f"已清理会话 {session_id} 的分段回复队列")

    async def _periodic_cleanup(self):
        """定期清理不活跃的会话队列"""
        while True:
            try:
                await asyncio.sleep(300)  # 每5分钟检查一次
                current_time = asyncio.get_event_loop().time()
                inactive_sessions = []

                for session_id, queue in self.session_queues.items():
                    # 如果队列超过5分钟没有活动且不在处理中，标记为可清理
                    if (current_time - queue.last_activity > 300 and
                        not queue.is_processing and
                        queue.queue.empty()):
                        inactive_sessions.append(session_id)

                # 清理不活跃的会话
                for session_id in inactive_sessions:
                    await self._cleanup_session(session_id)

                if inactive_sessions:
                    logger.debug(f"清理了 {len(inactive_sessions)} 个不活跃的分段回复队列")

            except Exception as e:
                logger.error(f"定期清理分段回复队列时出错: {e}")

    async def shutdown(self):
        """关闭管理器，清理所有资源"""
        # 取消清理任务
        if self.cleanup_task and not self.cleanup_task.done():
            self.cleanup_task.cancel()

        # 清理所有会话队列
        for session_id in list(self.session_queues.keys()):
            await self._cleanup_session(session_id)

        logger.info("分段回复管理器已关闭")
