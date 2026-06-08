from .auth import router as auth_router
from .chat import router as chat_router
from .conversations import router as conversations_router
from .files import router as files_router
from .knowledge_bases import router as knowledge_bases_router
from .personas import router as personas_router
from .sessions import router as sessions_router
from .system import router as system_router

compat_routers = [
    auth_router,
    chat_router,
    files_router,
    conversations_router,
    system_router,
    sessions_router,
    personas_router,
    knowledge_bases_router,
]
