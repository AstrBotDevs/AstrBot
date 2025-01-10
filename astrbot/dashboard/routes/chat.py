import uuid
import json
import os
from .route import Route, Response, RouteContext
from astrbot.core import web_chat_queue, web_chat_back_queue
from quart import request, Response as QuartResponse, g
from astrbot.core.db import BaseDatabase
import asyncio

class ChatRoute(Route):
    def __init__(self, context: RouteContext, db: BaseDatabase) -> None:
        super().__init__(context)
        self.routes = {
            '/chat/send': ('POST', self.chat),
            '/chat/new_conversation': ('GET', self.new_conversation),
            '/chat/conversations': ('GET', self.get_conversations),
            '/chat/get_conversation': ('GET', self.get_conversation),
            '/chat/delete_conversation': ('GET', self.delete_conversation),
            '/chat/get_file': ('GET', self.get_file),
            '/chat/post_image': ('POST', self.post_image)
        }
        self.db = db
        self.register_routes()
        self.imgs_dir = "data/webchat/imgs"
    
    async def get_file(self):
        filename = request.args.get('filename')
        if not filename:
            return Response().error("Missing key: filename").__dict__
        
        try:
            with open(os.path.join(self.imgs_dir, filename), "rb") as f:
                return QuartResponse(f.read(), mimetype="image/jpeg")
        except FileNotFoundError:
            return Response().error("File not found").__dict__
        
    async def post_image(self):
        post_data = await request.files
        if 'file' not in post_data:
            return Response().error("Missing key: file").__dict__
        
        file = post_data['file']
        filename = str(uuid.uuid4()) + ".jpg"
        path = os.path.join(self.imgs_dir, filename)
        await file.save(path)
        
        return Response().ok(data={
            'filename': filename
        }).__dict__

    async def chat(self):
        username = g.get('username', 'guest')
        
        post_data = await request.json
        if 'message' not in post_data and 'image_url' not in post_data:
            return Response().error("Missing key: message or image_url").__dict__
        
        if 'conversation_id' not in post_data:
            return Response().error("Missing key: conversation_id").__dict__
        
        message = post_data['message']
        conversation_id = post_data['conversation_id']
        image_url = post_data.get('image_url')
        if not message and not image_url:
            return Response().error("Message and image_url are empty").__dict__
        if not conversation_id:
            return Response().error("conversation_id is empty").__dict__
        
        await web_chat_queue.put((username, conversation_id, {
            'message': message,
            'image_url': image_url # list
        }))
        
        async def stream():
            ret = []
            while True:
                result = await web_chat_back_queue.get()
                
                if result is None:
                    break
                
                ret.append(result)
                
                yield result + '\n'
                
                await asyncio.sleep(0.5)
            
            conversation = self.db.get_webchat_conversation_by_user_id(username, conversation_id)
            try:
                history = json.loads(conversation.history)
            except BaseException as e:
                print(e)
                history = []
            
            new_his = {
                'type': 'user',
                'message': message
            }
            if image_url:
                new_his['image_url'] = image_url
            history.append(new_his)
            for r in ret:
                history.append({
                    'type': 'bot',
                    'message': r
                })
            self.db.update_webchat_conversation(username, conversation_id, history=json.dumps(history))
        
        return QuartResponse(
            stream(),
            mimetype="text/event-stream",
            headers={
                "Content-Type": "text/event-stream",
                "Transfer-Encoding": "chunked",
                "Connection": "keep-alive",
                "Access-Control-Allow-Origin": "*"  # 如果是跨域请求
            }
        )
        
    async def delete_conversation(self):
        username = g.get('username', 'guest')
        conversation_id = request.args.get('conversation_id')
        if not conversation_id:
            return Response().error("Missing key: conversation_id").__dict__
        
        self.db.delete_webchat_conversation(username, conversation_id)
        return Response().ok().__dict__
    
    async def new_conversation(self):
        username = g.get('username', 'guest')
        conversation_id = str(uuid.uuid4())
        self.db.webchat_new_conversation(username, conversation_id)
        return Response().ok(data={
            'conversation_id': conversation_id
        }).__dict__
        
    async def get_conversations(self):
        username = g.get('username', 'guest')
        conversations = self.db.get_webchat_conversations(username)
        return Response().ok(data=conversations).__dict__
    
    async def get_conversation(self):
        username = g.get('username', 'guest')
        conversation_id = request.args.get('conversation_id')
        if not conversation_id:
            return Response().error("Missing key: conversation_id").__dict__
        
        conversation = self.db.get_webchat_conversation_by_user_id(username, conversation_id)
        return Response().ok(data=conversation).__dict__