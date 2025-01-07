import os
import aiohttp
import uuid
import asyncio
import re
import astrbot.api.star as star
import aiodocker
from astrbot.api.event import AstrMessageEvent
from astrbot.api import llm_tool, logger
from astrbot.api.message_components import Image

PROMPT = """
## Task
You need to generate python codes to solve user's problem: {prompt}

{extra_input}

## Limit
1. The python libraries you can use include python standard libraries and `Pillow`, `requests`, `numpy`, `matplotlib`.
2. You must not generate malicious code.
3. You can only output text, image. For Image, you need save it to `output` folder.
4. Use given `shared.api` package to output the result.
5. Your must only output the code, do not output the result of the code and other any information.
6. The output language is same as the user's input language.

## Example
1. The user's problem is: `please solve the fabonacci sequence problem.`
Output:
```python
from shared.api import send_text, send_image

def fabonacci(n):
    if n <= 1:
        return n
    else:
        return fabonacci(n-1) + fabonacci(n-2)
        
result = fabonacci(10)
# introduce the fabonacci sequence briefly
send_text("The fabonacci sequence is a series of numbers in which each number is the sum of the two preceding ones, starting from 0 and 1.")
send_text("Let's calculate the fabonacci sequence of 10: " + result) # send_text is a function to send pure text to user
```

2. The user's problem is: `please draw a sin(x) function.`
Output:
```python
from shared.api import send_text, send_image
import numpy as np
import matplotlib.pyplot as plt

x = np.linspace(0, 2*np.pi, 100)
y = np.sin(x)
plt.plot(x, y)
plt.savefig("output/sin_x.png")
send_text("The sin(x) is a periodic function with a period of 2π, and the value range is [-1, 1]. The following is the image of sin(x).") # introduce the sin(x) function briefly
send_image("output/sin_x.png") # send_image is a function to send image to user
send_text("If you need more information, please let me know :)")
```

{extra_prompt}
"""

@star.register(name="astrbot-python-interpreter", desc="Python 代码执行器", author="Soulter", version="0.0.1")
class Main(star.Star):
    '''基于 Docker 沙箱的 Python 代码执行器'''
    def __init__(self, context: star.Context) -> None:
        self.context = context
        self.curr_dir = os.path.dirname(os.path.abspath(__file__))
        self.workplace_path = os.path.join(self.curr_dir, "workplace")
        self.shared_path = os.path.join(self.curr_dir, "shared")
        os.makedirs(self.workplace_path, exist_ok=True)
        
    async def gen_magic_code(self) -> str:
        return uuid.uuid4().hex[:8]
    
    async def download_image(self, image_url: str, workplace_path: str, filename: str) -> str:
        '''Download image from url to workplace_path'''
        async with aiohttp.ClientSession() as session:
            async with session.get(image_url) as resp:
                if resp.status != 200:
                    return ""
                image_path = os.path.join(workplace_path, f"{filename}.jpg")
                with open(image_path, 'wb') as f:
                    f.write(await resp.read())
                return f"{filename}.jpg"
    
    async def tidy_code(self, code: str) -> str:
        '''Tidy the code'''
        pattern = r"```(?:py|python)?\n(.*?)\n```"
        match = re.search(pattern, code, re.DOTALL)
        if match is None:
            raise ValueError("The code is not in the code block.")
        return match.group(1)

    @llm_tool("python_interpreter")
    async def python_interpreter(self, event: AstrMessageEvent):
        '''Use this tool only if user really want to solve a complex problem and the problem can be solved very well by Python code. For example, user can use this tool to solve a math problem, edit Image, etc. 
        '''
        plain_text = event.message_str

        # 创建必要的工作目录和幻术码
        magic_code = await self.gen_magic_code()
        workplace_path = os.path.join(self.workplace_path, magic_code)
        output_path = os.path.join(workplace_path, "output")
        os.makedirs(workplace_path, exist_ok=True)
        os.makedirs(output_path, exist_ok=True)
        
        # 图片
        images = []
        idx = 1
        for comp in event.message_obj.message:
            if isinstance(comp, Image):
                image_url = comp.url if comp.url else comp.file
                if image_url.startswith("http"):
                    image_path = await self.download_image(image_url, workplace_path, f"img_{idx}")
                    if image_path:
                        images.append(image_path)
                        idx += 1
                        
        obs = ""
        n = 5
        
        for i in range(n):
            if i > 0:
                logger.info(f"Try {i+1}/{n}")
            
            PROMPT_ = PROMPT.format(
                prompt=plain_text, 
                extra_input=f"User provided images: {images}",
                extra_prompt=obs,
            )
            provider = self.context.get_using_provider()
            llm_response = await provider.text_chat(prompt=PROMPT_, session_id=event.session_id)
            
            logger.debug("code interpreter llm gened code:" + llm_response.completion_text)
            
            # 整理代码并保存
            code_clean = await self.tidy_code(llm_response.completion_text)
            with open(os.path.join(workplace_path, "exec.py"), "w") as f:
                f.write(code_clean)
            
            # 启动容器
            docker = aiodocker.Docker()
            
            # 检查有没有image
            try:
                await docker.images.get("cjie.eu.org/soulter/astrbot-code-interpreter-sandbox")
            except aiodocker.exceptions.DockerError:
                # 拉取镜像
                logger.debug("Pulling image soulter/astrbot-code-interpreter-sandbo...")
                await docker.images.pull("cjie.eu.org/soulter/astrbot-code-interpreter-sandbox")
                
            yield event.plain_result(f"使用沙箱执行代码中，请稍等...(尝试次数: {i+1}/{n})")
            
            container = await docker.containers.run({
                "Image": "cjie.eu.org/soulter/astrbot-code-interpreter-sandbox",
                "Cmd": ["python", "exec.py"],
                "Memory": 512 * 1024 * 1024,
                "NanoCPUs": 1000000000,
                "HostConfig": {
                    "Binds": [
                        f"{self.shared_path}:/astrbot_sandbox/shared:ro",
                        f"{output_path}:/astrbot_sandbox/output:rw",
                        f"{workplace_path}:/astrbot_sandbox:rw",
                    ]
                },
                "Env": [
                    f"MAGIC_CODE={magic_code}"
                ],
                "AutoRemove": True
            })
            
            logger.debug(f"Container {container.id} created.")
            logs = await self.run_container(container)
            
            logger.debug(f"Container {container.id} finished.")
            logger.debug(f"Container {container.id} logs: {logs}")
            
            # 发送结果
            pattern = r"\[ASTRBOT_(TEXT|IMAGE)_OUTPUT#\w+\]: (.*)"
            ok = False
            traceback = ""
            for idx, log in enumerate(logs):
                match = re.match(pattern, log)
                if match:
                    ok = True
                    if match.group(1) == "TEXT":
                        yield event.plain_result(match.group(2))
                    elif match.group(1) == "IMAGE":
                        image_path = os.path.join(workplace_path, match.group(2))
                        logger.debug(f"Sending image: {image_path}")
                        yield event.image_result(image_path)
                elif "Traceback (most recent call last)" in log:
                    traceback = "\n".join(logs[idx:])
                    
            if not ok:
                if traceback:
                    obs = f"## Observation\When execute the code: ```python\n{code_clean}\n```\n\n Error occured:\n\n{traceback}\n Need to improve/fix the code."
                else:
                    logger.warning(f"未从沙箱输出中捕获到合法的输出。沙箱输出日志: {logs}")
                    break
            else:
                return
        
        yield event.plain_result("经过多次尝试后，未从沙箱输出中捕获到合法的输出，请更换问法或者查看日志。")
            
    
    async def run_container(self, container: aiodocker.docker.DockerContainer, timeout: int = 20) -> list[str]:
        '''Run the container and get the output'''
        try:
            await container.wait(timeout=timeout)
            logs = await container.log(stdout=True, stderr=True)
            return logs
        except asyncio.TimeoutError:
            logger.warning(f"Container {container.id} timeout.")
            await container.kill()
            return f"Container has been killed due to timeout ({timeout}s)."
        finally:
            await container.delete()