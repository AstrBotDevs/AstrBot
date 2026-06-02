import asyncio
import contextvars
import time
import traceback
import os
from astrbot.api import logger
from astrbot.api.message_components import Plain, At, Image, Video, Record, Face
from astrbot.core.message.message_event_result import MessageChain

# 协程局部锁，防止转发时产生无限递归
_forwarding_lock = contextvars.ContextVar("forwarding_lock", default=False)
_is_timer_execution = contextvars.ContextVar("is_timer_execution", default=False)

class CommandTrigger:
    def __init__(self, context, config=None):
        self.context = context
        self.config = config or {}
        self.monitor_timeout = self.config.get('monitor_timeout', 60)
        self.captured_messages = []

    def _get_original_session_id(self, session_id: str) -> str:
        if "_" in session_id and ":" in session_id:
            parts = session_id.rsplit(":", 1)
            if len(parts) == 2 and "_" in parts[1]:
                group_id, _ = parts[1].rsplit("_", 1)
                return f"{parts[0]}:{group_id}"
        return session_id

    def _clean_path(self, path_str: str) -> str:
        """清洗路径，去掉 file:// 等协议头，防止路径冲突"""
        if not path_str: return path_str
        if path_str.startswith("file:///"):
            return path_str[8:]
        if path_str.startswith("file:/"):
            return path_str[6:]
        return path_str

    async def trigger_and_forward_command(self, unified_msg_origin: str, item: dict, command: str):
        target_dest = self._get_original_session_id(unified_msg_origin)
        
        from .event_factory import EventFactory
        factory = EventFactory(self.context)
        event = factory.create_event(
            unified_msg_origin, 
            command, 
            item.get('created_by', 'timer'), 
            item.get('creator_name', 'Timer')
        )

        # 记录原始方法
        original_send = event.send
        original_call = None

        # 设置当前协程的定时任务标记
        token_timer = _is_timer_execution.set(True)

        # --- 核心转发函数 ---
        async def do_forward(chain, source_info):
            if _forwarding_lock.get(): return 
            
            token = _forwarding_lock.set(True)
            try:
                if chain and hasattr(chain, 'chain') and chain.chain:
                    logger.info(f"[拦截成功] {source_info} -> 正在转发: {command}")
                    self.captured_messages.append(chain)
                    
                    # 确保转发时携带正确的 Bot self_id
                    if not hasattr(chain, 'self_id') or not chain.self_id:
                        chain.self_id = getattr(event, 'self_id', None)
                    
                    await self.context.send_message(target_dest, chain)
            except Exception:
                logger.error(f"[转发失败] {source_info} 发生异常:\n{traceback.format_exc()}")
            finally:
                _forwarding_lock.reset(token)

        # 1. 劫持 event.send
        async def intercepted_send(message_chain):
            if _forwarding_lock.get(): return await original_send(message_chain)
            await do_forward(message_chain, "event.send")
            event._has_send_oper = True
            return True
        event.send = intercepted_send

        # 2. 劫持 bot.api.call_action
        if hasattr(event, 'bot') and hasattr(event.bot, 'api'):
            original_call = event.bot.api.call_action
            
            async def intercepted_call(action, **params):
                # 核心安全校验：
                # 1. 必须在标记了 _is_timer_execution 的协程上下文中运行
                # 2. 必须是发送消息类的 API
                # 3. 必须是同一个 bot 实例 (self_id 匹配)
                
                if not _is_timer_execution.get():
                    return await original_call(action, **params)
                
                current_self_id = params.get("self_id") or (getattr(event.bot, 'self_id', None))
                target_self_id = getattr(event, 'self_id', None)
                
                is_msg_api = action in ["send_msg", "send_group_msg", "send_private_msg", "send_private_forward_msg", "send_group_forward_msg"]
                is_same_bot = str(current_self_id) == str(target_self_id)
                
                if _forwarding_lock.get() or not (is_msg_api and is_same_bot):
                    return await original_call(action, **params)

                # 提取消息内容
                raw_msg = params.get("message")
                if not raw_msg:
                    return await original_call(action, **params)

                # 解析消息
                msg_chain = MessageChain()
                
                if isinstance(raw_msg, dict):
                    msg_elements = [raw_msg]
                elif isinstance(raw_msg, list):
                    msg_elements = raw_msg
                else:
                    msg_elements = [{"type": "text", "data": {"text": str(raw_msg)}}]

                for seg in msg_elements:
                    if not isinstance(seg, dict): continue
                    stype = seg.get("type")
                    data = seg.get("data", {})
                    
                    try:
                        if stype == "text":
                            msg_chain.chain.append(Plain(data.get("text", "")))
                        elif stype in ["image", "video", "record"]:
                            # 获取路径或URL
                            file_val = data.get("file") or data.get("url")
                            if not file_val: continue
                            
                            file_str = str(file_val)
                            is_url = file_str.startswith("http")
                            clean_val = self._clean_path(file_str)
                            
                            if stype == "image":
                                msg_chain.chain.append(Image.fromURL(clean_val) if is_url else Image.fromFileSystem(clean_val))
                            elif stype == "video":
                                msg_chain.chain.append(Video.fromURL(clean_val) if is_url else Video.fromFileSystem(clean_val))
                            elif stype == "record":
                                msg_chain.chain.append(Record.fromURL(clean_val) if is_url else Record.fromFileSystem(clean_val))
                        elif stype == "at":
                            msg_chain.chain.append(At(qq=data.get("qq")))
                        elif stype == "face":
                            msg_chain.chain.append(Face(id=data.get("id")))
                    except Exception as conv_err:
                        logger.error(f"组件转换异常({stype}): {conv_err}")

                if msg_chain.chain:
                    await do_forward(msg_chain, f"API:{action}")
                
                event._has_send_oper = True
                return {"status": "ok", "retcode": 0, "data": {"message_id": int(time.time())}, "message_id": int(time.time())}

            event.bot.api.call_action = intercepted_call

        try:
            self.context.get_event_queue().put_nowait(event)
            await asyncio.sleep(self.monitor_timeout)
        except asyncio.CancelledError:
            raise
        finally:
            # 恢复环境
            event.send = original_send
            if original_call and hasattr(event, 'bot') and hasattr(event.bot, 'api'):
                event.bot.api.call_action = original_call
            logger.info(f"[任务结束] {command} 监控退出")