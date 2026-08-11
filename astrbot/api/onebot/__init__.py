"""Official OneBot/NapCat plugin SDK.

Only stable contracts and event-bound facades are exported.  Adapter classes,
generated Pydantic models, websocket connections, and arbitrary raw actions
are intentionally absent from this namespace.
"""

from .actions import (
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
from .client import (
    NapCatQQ,
    OneBotClient,
    OneBotDirectory,
    OneBotGroups,
    OneBotHistory,
    OneBotMessages,
    OneBotRequests,
)
from .errors import (
    OneBotActionRejected,
    OneBotActionTimeout,
    OneBotActionUnavailable,
    OneBotActionValidationError,
    OneBotCapabilityUnavailable,
    OneBotError,
    OneBotTransportError,
)
from .events import (
    OneBotEvent,
    OneBotMessageEvent,
    OneBotMetaEvent,
    OneBotNoticeEvent,
    OneBotRequestEvent,
    OneBotSegment,
    OneBotSender,
)

__all__ = [
    "OneBotEvent",
    "OneBotMessageEvent",
    "OneBotNoticeEvent",
    "OneBotRequestEvent",
    "OneBotMetaEvent",
    "OneBotSegment",
    "OneBotSender",
    "OneBotActionResult",
    "OneBotActionInput",
    "OneBotMessageReceipt",
    "OneBotFileResult",
    "OneBotGroupInfo",
    "OneBotMemberInfo",
    "OneBotHistoryPage",
    "PlatformCapabilityDescriptor",
    "PlatformActionDescriptor",
    "ONEBOT_CAPABILITIES",
    "ONEBOT_V11_ACTIONS",
    "NAPCAT_QQ_ACTIONS",
    "OneBotError",
    "OneBotCapabilityUnavailable",
    "OneBotActionUnavailable",
    "OneBotActionValidationError",
    "OneBotActionRejected",
    "OneBotTransportError",
    "OneBotActionTimeout",
    "OneBotClient",
    "OneBotMessages",
    "OneBotDirectory",
    "OneBotGroups",
    "OneBotRequests",
    "OneBotHistory",
    "NapCatQQ",
    "ONEBOT_SDK_VERSION",
]
