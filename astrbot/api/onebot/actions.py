"""Action result DTOs and capability descriptors for OneBot plugins."""

from astrbot.core.platform.contracts.onebot import (
    NAPCAT_QQ_ACTIONS,
    ONEBOT_CAPABILITIES,
    ONEBOT_SDK_VERSION,
    ONEBOT_V11_ACTIONS,
    OneBotActionInput,
    OneBotActionResult,
    OneBotFileResult,
    OneBotGroupInfo,
    OneBotHistoryPage,
    OneBotMemberInfo,
    OneBotMessageReceipt,
    PlatformActionDescriptor,
    PlatformCapabilityDescriptor,
)

__all__ = [
    "OneBotActionResult",
    "OneBotActionInput",
    "OneBotMessageReceipt",
    "OneBotFileResult",
    "OneBotGroupInfo",
    "OneBotMemberInfo",
    "OneBotHistoryPage",
    "PlatformActionDescriptor",
    "PlatformCapabilityDescriptor",
    "ONEBOT_CAPABILITIES",
    "ONEBOT_V11_ACTIONS",
    "NAPCAT_QQ_ACTIONS",
    "ONEBOT_SDK_VERSION",
]
