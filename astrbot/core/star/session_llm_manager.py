"""
会话LLM管理器 - 负责管理每个会话的LLM启停状态
"""

from astrbot.core import sp, logger
from typing import Dict, Optional
from astrbot.core.platform.astr_message_event import AstrMessageEvent


class SessionLLMManager:
    """管理会话级别的LLM启停状态"""
    
    @staticmethod
    def is_llm_enabled_for_session(session_id: str) -> bool:
        """检查LLM是否在指定会话中启用
        
        Args:
            session_id: 会话ID (unified_msg_origin)
            
        Returns:
            bool: True表示启用，False表示禁用
        """
        # 获取会话LLM配置
        session_llm_config = sp.get("session_llm_config", {})
        session_config = session_llm_config.get(session_id, {})
        
        # 如果配置了该会话的LLM状态，返回该状态
        llm_enabled = session_config.get("llm_enabled")
        if llm_enabled is not None:
            return llm_enabled
            
        # 如果没有配置，默认为启用（兼容性考虑）
        return True
    
    @staticmethod
    def set_llm_status_for_session(session_id: str, enabled: bool) -> None:
        """设置LLM在指定会话中的启停状态
        
        Args:
            session_id: 会话ID (unified_msg_origin)
            enabled: True表示启用，False表示禁用
        """
        # 获取当前配置
        session_llm_config = sp.get("session_llm_config", {})
        if session_id not in session_llm_config:
            session_llm_config[session_id] = {}
        
        # 设置LLM状态
        session_llm_config[session_id]["llm_enabled"] = enabled
        
        # 保存配置
        sp.put("session_llm_config", session_llm_config)
        
        logger.info(f"会话 {session_id} 的LLM状态已更新为: {'启用' if enabled else '禁用'}")
    
    @staticmethod
    def get_session_llm_config(session_id: str) -> Dict[str, bool]:
        """获取指定会话的LLM配置
        
        Args:
            session_id: 会话ID (unified_msg_origin)
            
        Returns:
            Dict[str, bool]: 包含llm_enabled的字典
        """
        session_llm_config = sp.get("session_llm_config", {})
        return session_llm_config.get(session_id, {
            "llm_enabled": True  # 默认启用
        })
    
    @staticmethod
    def should_process_llm_request(event: AstrMessageEvent) -> bool:
        """检查是否应该处理LLM请求
        
        Args:
            event: 消息事件
            
        Returns:
            bool: True表示应该处理，False表示跳过
        """
        session_id = event.unified_msg_origin
        return SessionLLMManager.is_llm_enabled_for_session(session_id)
