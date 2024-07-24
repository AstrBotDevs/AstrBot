import aiohttp
import uuid

class ImageUploader():
    def __init__(self) -> None:
        self.S3_URL = "https://s3.neko.soulter.top/astrbot-s3"
        
    async def upload_image(self, image_path: str) -> str:
        '''
        上传图像文件到S3
        '''
        with open(image_path, "rb") as f:
            image = f.read()
        
        image_url = f"{self.S3_URL}/{uuid.uuid4().hex}.jpg"
        
        async with aiohttp.ClientSession(headers = {"Accept": "application/json"}) as session:
            async with session.put(image_url, data=image) as resp:
                if resp.status != 200:
                    raise Exception(f"Failed to upload image: {resp.status}")
                return image_url
