import asyncio

class WebChatQueueMgr:
    def __init__(self) -> None:
        self.queues = {}
        """Conversation ID to asyncio.Queue mapping"""
        self.back_queues = {}
        """Conversation ID to asyncio.Queue mapping for responses"""

    def get_or_create_queue(self, conversation_id: str) -> asyncio.Queue:
        """Get or create a queue for the given conversation ID"""
        if conversation_id not in self.queues:
            self.queues[conversation_id] = asyncio.Queue()
        return self.queues[conversation_id]

    def get_or_create_back_queue(self, conversation_id: str) -> asyncio.Queue:
        """Get or create a back queue for the given conversation ID"""
        if conversation_id not in self.back_queues:
            self.back_queues[conversation_id] = asyncio.Queue()
        return self.back_queues[conversation_id]

    def remove_queues(self, conversation_id: str):
        """Remove queues for the given conversation ID"""
        if conversation_id in self.queues:
            del self.queues[conversation_id]
        if conversation_id in self.back_queues:
            del self.back_queues[conversation_id]

    def has_queue(self, conversation_id: str) -> bool:
        """Check if a queue exists for the given conversation ID"""
        return conversation_id in self.queues

webchat_queue_mgr = WebChatQueueMgr()
