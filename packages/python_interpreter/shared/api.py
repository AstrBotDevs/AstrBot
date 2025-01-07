import os

def _get_magic_code():
    '''防止注入攻击'''
    return os.getenv("MAGIC_CODE")

def send_text(text: str):
    print(f"[ASTRBOT_TEXT_OUTPUT#{_get_magic_code()}]: {text}")
    
def send_image(image_path: str):
    if not os.path.exists(image_path):
        raise Exception(f"Image file not found: {image_path}")
    print(f"[ASTRBOT_IMAGE_OUTPUT#{_get_magic_code()}]: {image_path}")