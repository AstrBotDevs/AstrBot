"""群设置管理器

提供群聊特定的 Provider 和 Persona 设置管理。
"""
import time
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class GroupSettings:
    """群设置数据类"""
    umo: str = ""
    provider_id: Optional[str] = None
    persona_id: Optional[str] = None
    model: Optional[str] = None
    set_by: Optional[str] = None
    set_at: Optional[str] = None


class GroupSettingsManager:
    """群设置管理器
    
    管理群聊特定的 Provider 和 Persona 设置。
    当前使用内存存储，实际生产环境应使用数据库。
    """
    
    def __init__(self):
        # 内存存储，格式: {umo: GroupSettings}
        self._settings: dict[str, GroupSettings] = {}
    
    async def get_settings(self, umo: str) -> GroupSettings:
        """获取指定群的设置
        
        Args:
            umo: 群的 UMO 标识
            
        Returns:
            GroupSettings: 群设置对象，如果不存在则返回空设置
        """
        if umo not in self._settings:
            return GroupSettings(umo=umo)
        return self._settings[umo]
    
    async def get_all_groups_with_settings(self) -> dict[str, GroupSettings]:
        """获取所有有设置的群
        
        Returns:
            dict: 键为 umo，值为 GroupSettings
        """
        return self._settings.copy()
    
    async def set_provider(self, umo: str, provider_id: str, set_by: str = "") -> None:
        """设置群的 Provider
        
        Args:
            umo: 群的 UMO 标识
            provider_id: Provider ID
            set_by: 设置者标识
        """
        if umo not in self._settings:
            self._settings[umo] = GroupSettings(umo=umo)
        
        self._settings[umo].provider_id = provider_id
        self._settings[umo].set_by = set_by
        self._settings[umo].set_at = str(int(time.time()))
    
    async def set_persona(self, umo: str, persona_id: str, set_by: str = "") -> None:
        """设置群的 Persona
        
        Args:
            umo: 群的 UMO 标识
            persona_id: Persona ID
            set_by: 设置者标识
        """
        if umo not in self._settings:
            self._settings[umo] = GroupSettings(umo=umo)
        
        self._settings[umo].persona_id = persona_id
        self._settings[umo].set_by = set_by
        self._settings[umo].set_at = str(int(time.time()))
    
    async def clear_settings(self, umo: str) -> None:
        """清除群的设置
        
        Args:
            umo: 群的 UMO 标识
        """
        if umo in self._settings:
            del self._settings[umo]
    
    async def remove_provider_override(self, umo: str) -> None:
        """清除群的 Provider 覆盖
        
        Args:
            umo: 群的 UMO 标识
        """
        if umo in self._settings:
            self._settings[umo].provider_id = None
            # 如果两个设置都为空，删除整个设置
            if not self._settings[umo].persona_id:
                del self._settings[umo]
    
    async def remove_persona_override(self, umo: str) -> None:
        """清除群的 Persona 覆盖
        
        Args:
            umo: 群的 UMO 标识
        """
        if umo in self._settings:
            self._settings[umo].persona_id = None
            # 如果两个设置都为空，删除整个设置
            if not self._settings[umo].provider_id:
                del self._settings[umo]
