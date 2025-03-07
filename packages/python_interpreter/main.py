import os
import json
import shutil
import aiohttp
import uuid
import asyncio
import re
import aiodocker
import time
import astrbot.api.star as star
from collections import defaultdict
from astrbot.api.event import AstrMessageEvent, MessageEventResult
from astrbot.api import llm_tool, logger
from astrbot.api.event import filter
from astrbot.api.provider import ProviderRequest
from astrbot.api.message_components import Image, File
from astrbot.core.utils.io import download_image_by_url, download_file

PROMPT = """
## Task
You need to generate python codes to solve user's problem: {prompt}

{extra_input}

## Limit
1. Available libraries:
    - standard libs
    - `Pillow`
    - `requests`
    - `numpy`
    - `matplotlib`
    - `scipy`
    - `scikit-learn`
    - `beautifulsoup4`
    - `pandas`
    - `opencv-python`
    - `python-docx`
    - `python-pptx`
    - `pymupdf` (Do not use fpdf, reportlab, etc.)
    - `mplfonts`
    You can only use these libraries and the libraries that they depend on.
2. Do not generate malicious code.
3. Use given `shared.api` package to output the result.
   It has 3 functions: `send_text(text: str)`, `send_image(image_path: str)`, `send_file(file_path: str)`.
   For Image and file, you must save it to `output` folder.
4. You must only output the code, do not output the result of the code and any other information.
5. The output language is same as user's input language.
6. Please first provide relevant knowledge about user's problem appropriately.

## Example
1. User's problem: `please solve the fabonacci sequence problem.`
Output:
```python
from shared.api import send_text, send_image, send_file

def fabonacci(n):
    if n <= 1:
        return n
    else:
        return fabonacci(n-1) + fabonacci(n-2)

result = fabonacci(10)
send_text("The fabonacci sequence is a series of numbers in which each number is the sum of the two preceding ones, starting from 0 and 1.")
send_text("Let's calculate the fabonacci sequence of 10: " + result) # send_text is a function to send pure text to user
```

2. User's problem: `please draw a sin(x) function.`
Output:
```python
from shared.api import send_text, send_image, send_file
import numpy as np
import matplotlib.pyplot as plt

x = np.linspace(0, 2*np.pi, 100)
y = np.sin(x)
plt.plot(x, y)
plt.savefig("output/sin_x.png")
send_text("The sin(x) is a periodic function with a period of 2π, and the value range is [-1, 1]. The following is the image of sin(x).")
send_image("output/sin_x.png") # send_image is a function to send image to user
send_text("If you need more information, please let me know :)")
```

{extra_prompt}
"""

DEFAULT_CONFIG = {
    "sandbox": {
        "image": "soulter/astrbot-code-interpreter-sandbox",
        "docker_mirror": "",  # cjie.eu.org
    },
    "docker_host_astrbot_abs_path": "",
}
PATH = "data/config/python_interpreter.json"


@star.register(
    name="astrbot-python-interpreter",
    desc="Python 代码执行器",
    author="Soulter",
    version="0.0.1",
)
class Main(star.Star):
    """基于 Docker 沙箱的 Python 代码执行器"""

    def __init__(self, context: star.Context) -> None:
        self.context = context
        self.curr_dir = os.path.dirname(os.path.abspath(__file__))

        self.shared_path = os.path.join("data", "py_interpreter_shared")
        if not os.path.exists(self.shared_path):
            # 复制 api.py 到 shared 目录
            os.makedirs(self.shared_path, exist_ok=True)
            shared_api_file = os.path.join(self.curr_dir, "shared", "api.py")
            shutil.copy(shared_api_file, self.shared_path)
        self.workplace_path = os.path.join("data", "py_interpreter_workplace")
        os.makedirs(self.workplace_path, exist_ok=True)

        self.user_file_msg_buffer = defaultdict(list)
        """存放用户上传的文件和图片"""
        self.user_waiting = {}
        """正在等待用户的文件或图片"""

        # 加载配置
        if not os.path.exists(PATH):
            self.config = DEFAULT_CONFIG
            self._save_config()
        else:
            with open(PATH, "r") as f:
                self.config = json.load(f)

    async def initialize(self):
        ok = await self.is_docker_available()
        if not ok:
            logger.info(
                "Docker 不可用，代码解释器将无法使用，astrbot-python-interpreter 将自动禁用。"
            )
            await self.context._star_manager.turn_off_plugin(
                "astrbot-python-interpreter"
            )

    async def file_upload(self, file_path: str):
        """
        上传图像文件到 S3
        """
        ext = os.path.splitext(file_path)[1]
        S3_URL = "https://s3.neko.soulter.top/astrbot-s3"
        with open(file_path, "rb") as f:
            file = f.read()

        s3_file_url = f"{S3_URL}/{uuid.uuid4().hex}{ext}"

        async with aiohttp.ClientSession(
            headers={"Accept": "application/json"}, trust_env=True
        ) as session:
            async with session.put(s3_file_url, data=file) as resp:
                if resp.status != 200:
                    raise Exception(f"Failed to upload image: {resp.status}")
                return s3_file_url

    async def is_docker_available(self) -> bool:
        """Check if docker is available"""
        try:
            docker = aiodocker.Docker()
            await docker.version()
            await docker.close()
            return True
        except BaseException as e:
            logger.info(f"检查 Docker 可用性: {e}")
            return False

    async def get_image_name(self) -> str:
        """Get the image name"""
        if self.config["sandbox"]["docker_mirror"]:
            return f"{self.config['sandbox']['docker_mirror']}/{self.config['sandbox']['image']}"
        return self.config["sandbox"]["image"]

    def _save_config(self):
        with open(PATH, "w") as f:
            json.dump(self.config, f)

    async def gen_magic_code(self) -> str:
        return uuid.uuid4().hex[:8]

    async def download_image(
        self, image_url: str, workplace_path: str, filename: str
    ) -> str:
        """Download image from url to workplace_path"""
        async with aiohttp.ClientSession(trust_env=True) as session:
            async with session.get(image_url) as resp:
                if resp.status != 200:
                    return ""
                image_path = os.path.join(workplace_path, f"{filename}.jpg")
                with open(image_path, "wb") as f:
                    f.write(await resp.read())
                return f"{filename}.jpg"

    async def tidy_code(self, code: str) -> str:
        """Tidy the code"""
        pattern = r"```(?:py|python)?\n(.*?)\n```"
        match = re.search(pattern, code, re.DOTALL)
        if match is None:
            raise ValueError("The code is not in the code block.")
        return match.group(1)

    @filter.event_message_type(filter.EventMessageType.ALL)
    async def on_message(self, event: AstrMessageEvent):
        """处理消息"""
        uid = event.get_sender_id()
        if uid not in self.user_waiting:
            return
        for comp in event.message_obj.message:
            if isinstance(comp, File):
                if comp.file.startswith("http"):
                    name = comp.name if comp.name else uuid.uuid4().hex[:8]
                    path = f"data/temp/{name}"
                    await download_file(comp.file, path)
                else:
                    path = comp.file
                self.user_file_msg_buffer[event.get_session_id()].append(path)
                logger.debug(f"User {uid} uploaded file: {path}")
                yield event.plain_result(f"代码执行器: 文件已经上传: {path}")
                if uid in self.user_waiting:
                    del self.user_waiting[uid]
            elif isinstance(comp, Image):
                image_url = comp.url if comp.url else comp.file
                if image_url.startswith("http"):
                    image_path = await download_image_by_url(image_url)
                elif image_url.startswith("file:///"):
                    image_path = image_url.replace("file:///", "")
                else:
                    image_path = image_url
                self.user_file_msg_buffer[event.get_session_id()].append(image_path)
                logger.debug(f"User {uid} uploaded image: {image_path}")
                yield event.plain_result(f"代码执行器: 图片已经上传: {image_path}")
                if uid in self.user_waiting:
                    del self.user_waiting[uid]

    @filter.on_llm_request()
    async def on_llm_req(self, event: AstrMessageEvent, request: ProviderRequest):
        if event.get_session_id() in self.user_file_msg_buffer:
            files = self.user_file_msg_buffer[event.get_session_id()]
            request.prompt += f"\nUser provided files: {files}"

    @filter.command_group("pi")
    def pi(self):
        pass

    @pi.command("absdir")
    async def pi_absdir(self, event: AstrMessageEvent, path: str = ""):
        """设置 Docker 宿主机绝对路径"""
        if not path:
            yield event.plain_result(
                f"当前 Docker 宿主机绝对路径: {self.config.get('docker_host_astrbot_abs_path', '')}"
            )
        else:
            self.config["docker_host_astrbot_abs_path"] = path
            self._save_config()
            yield event.plain_result(f"设置 Docker 宿主机绝对路径成功: {path}")

    @pi.command("mirror")
    async def pi_mirror(self, event: AstrMessageEvent, url: str = ""):
        """Docker 镜像地址"""
        if not url:
            yield event.plain_result(f"""当前 Docker 镜像地址: {self.config["sandbox"]["docker_mirror"]}。
使用 `pi mirror <url>` 来设置 Docker 镜像地址。
您所设置的 Docker 镜像地址将会自动加在 Docker 镜像名前。如: `soulter/astrbot-code-interpreter-sandbox` -> `cjie.eu.org/soulter/astrbot-code-interpreter-sandbox`。
""")
        else:
            self.config["sandbox"]["docker_mirror"] = url
            self._save_config()
            yield event.plain_result("设置 Docker 镜像地址成功。")

    @pi.command("repull")
    async def pi_repull(self, event: AstrMessageEvent):
        """重新拉取沙箱镜像"""
        docker = aiodocker.Docker()
        image_name = await self.get_image_name()
        try:
            await docker.images.get(image_name)
            await docker.images.delete(image_name, force=True)
        except aiodocker.exceptions.DockerError:
            pass
        await docker.images.pull(image_name)
        yield event.plain_result("重新拉取沙箱镜像成功。")

    @pi.command("file")
    async def pi_file(self, event: AstrMessageEvent):
        """在规定秒数(60s)内上传一个文件"""
        uid = event.get_sender_id()
        self.user_waiting[uid] = time.time()
        tip = "文件"
        yield event.plain_result(f"代码执行器: 请在 60s 内上传一个{tip}。")
        await asyncio.sleep(60)
        if uid in self.user_waiting:
            yield event.plain_result(
                f"代码执行器: {event.get_sender_name()}/{event.get_sender_id()} 未在规定时间内上传{tip}。"
            )
            self.user_waiting.pop(uid)

    @pi.command("clear", alias=["clean"])
    async def pi_file_clean(self, event: AstrMessageEvent):
        """清理用户上传的文件"""
        uid = event.get_sender_id()
        if uid in self.user_waiting:
            self.user_waiting.pop(uid)
            yield event.plain_result(
                f"代码执行器: {event.get_sender_name()}/{event.get_sender_id()} 已清理。"
            )
        else:
            yield event.plain_result(
                f"代码执行器: {event.get_sender_name()}/{event.get_sender_id()} 没有等待上传文件。"
            )

    @pi.command("list")
    async def pi_file_list(self, event: AstrMessageEvent):
        """列出用户上传的文件"""
        uid = event.get_sender_id()
        if uid in self.user_file_msg_buffer:
            files = self.user_file_msg_buffer[uid]
            yield event.plain_result(
                f"代码执行器: {event.get_sender_name()}/{event.get_sender_id()} 上传的文件: {files}"
            )
        else:
            yield event.plain_result(
                f"代码执行器: {event.get_sender_name()}/{event.get_sender_id()} 没有上传文件。"
            )

    @llm_tool("python_interpreter")
    async def python_interpreter(self, event: AstrMessageEvent):
        """Use this tool only if user really want to solve a complex problem and the problem can be solved very well by Python code.
        For example, user can use this tool to solve math problems, edit image, docx, pptx, pdf, etc.
        """
        if not await self.is_docker_available():
            yield event.plain_result("Docker 在当前机器不可用，无法沙箱化执行代码。")

        plain_text = event.message_str

        # 创建必要的工作目录和幻术码
        magic_code = await self.gen_magic_code()
        workplace_path = os.path.join(self.workplace_path, magic_code)
        output_path = os.path.join(workplace_path, "output")
        os.makedirs(workplace_path, exist_ok=True)
        os.makedirs(output_path, exist_ok=True)

        files = []
        # 文件
        for file_path in self.user_file_msg_buffer[event.get_session_id()]:
            if not file_path:
                continue
            elif not os.path.exists(file_path):
                logger.warning(f"文件 {file_path} 不存在，已忽略。")
                continue
            # cp
            file_name = os.path.basename(file_path)
            shutil.copy(file_path, os.path.join(workplace_path, file_name))
            files.append(file_name)

        logger.debug(f"user query: {plain_text}, files: {files}")

        # 整理额外输入
        extra_inputs = ""
        if files:
            extra_inputs += f"User provided files: {files}\n"

        obs = ""
        n = 5

        for i in range(n):
            if i > 0:
                logger.info(f"Try {i + 1}/{n}")

            PROMPT_ = PROMPT.format(
                prompt=plain_text,
                extra_input=extra_inputs,
                extra_prompt=obs,
            )
            provider = self.context.get_using_provider()
            llm_response = await provider.text_chat(
                prompt=PROMPT_, session_id=f"{event.session_id}_{magic_code}_{str(i)}"
            )

            logger.debug(
                "code interpreter llm gened code:" + llm_response.completion_text
            )

            # 整理代码并保存
            code_clean = await self.tidy_code(llm_response.completion_text)
            with open(os.path.join(workplace_path, "exec.py"), "w") as f:
                f.write(code_clean)

            # 启动容器
            docker = aiodocker.Docker()

            # 检查有没有image
            image_name = await self.get_image_name()
            try:
                await docker.images.get(image_name)
            except aiodocker.exceptions.DockerError:
                # 拉取镜像
                logger.info(f"未找到沙箱镜像，正在尝试拉取 {image_name}...")
                await docker.images.pull(image_name)

            yield event.plain_result(
                f"使用沙箱执行代码中，请稍等...(尝试次数: {i + 1}/{n})"
            )

            self.docker_host_astrbot_abs_path = self.config.get(
                "docker_host_astrbot_abs_path", ""
            )
            if self.docker_host_astrbot_abs_path:
                host_shared = os.path.join(
                    self.docker_host_astrbot_abs_path, self.shared_path
                )
                host_output = os.path.join(
                    self.docker_host_astrbot_abs_path, output_path
                )
                host_workplace = os.path.join(
                    self.docker_host_astrbot_abs_path, workplace_path
                )

            else:
                host_shared = os.path.abspath(self.shared_path)
                host_output = os.path.abspath(output_path)
                host_workplace = os.path.abspath(workplace_path)

            logger.debug(
                f"host_shared: {host_shared}, host_output: {host_output}, host_workplace: {host_workplace}"
            )

            container = await docker.containers.run(
                {
                    "Image": image_name,
                    "Cmd": ["python", "exec.py"],
                    "Memory": 512 * 1024 * 1024,
                    "NanoCPUs": 1000000000,
                    "HostConfig": {
                        "Binds": [
                            f"{host_shared}:/astrbot_sandbox/shared:ro",
                            f"{host_output}:/astrbot_sandbox/output:rw",
                            f"{host_workplace}:/astrbot_sandbox:rw",
                        ]
                    },
                    "Env": [f"MAGIC_CODE={magic_code}"],
                    "AutoRemove": True,
                }
            )

            logger.debug(f"Container {container.id} created.")
            logs = await self.run_container(container)

            logger.debug(f"Container {container.id} finished.")
            logger.debug(f"Container {container.id} logs: {logs}")

            # 发送结果
            pattern = r"\[ASTRBOT_(TEXT|IMAGE|FILE)_OUTPUT#\w+\]: (.*)"
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
                    elif match.group(1) == "FILE":
                        file_path = os.path.join(workplace_path, match.group(2))
                        logger.debug(f"Sending file: {file_path}")
                        file_s3_url = await self.file_upload(file_path)
                        logger.info(f"文件上传到 AstrBot 云节点: {file_s3_url}")
                        file_name = os.path.basename(file_path)
                        chain = [File(name=file_name, file=file_s3_url)]
                        yield event.set_result(MessageEventResult(chain=chain))

                elif "Traceback (most recent call last)" in log or "[Error]: " in log:
                    traceback = "\n".join(logs[idx:])

            if not ok:
                if traceback:
                    obs = f"## Observation \n When execute the code: ```python\n{code_clean}\n```\n\n Error occurred:\n\n{traceback}\n Need to improve/fix the code."
                else:
                    logger.warning(
                        f"未从沙箱输出中捕获到合法的输出。沙箱输出日志: {logs}"
                    )
                    break
            else:
                # 成功了
                self.user_file_msg_buffer.pop(event.get_session_id())
                return

        yield event.plain_result(
            "经过多次尝试后，未从沙箱输出中捕获到合法的输出，请更换问法或者查看日志。"
        )

    @pi.command("cleanfile")
    async def pi_cleanfile(self, event: AstrMessageEvent):
        """清理用户上传的文件"""
        for file in self.user_file_msg_buffer[event.get_session_id()]:
            try:
                os.remove(file)
            except BaseException as e:
                logger.error(f"删除文件 {file} 失败: {e}")

        self.user_file_msg_buffer.pop(event.get_session_id())
        yield event.plain_result(f"用户 {event.get_session_id()} 上传的文件已清理。")

    async def run_container(
        self, container: aiodocker.docker.DockerContainer, timeout: int = 20
    ) -> list[str]:
        """Run the container and get the output"""
        try:
            await container.wait(timeout=timeout)
            logs = await container.log(stdout=True, stderr=True)
            return logs
        except asyncio.TimeoutError:
            logger.warning(f"Container {container.id} timeout.")
            await container.kill()
            return [f"[Error]: Container has been killed due to timeout ({timeout}s)."]
        finally:
            await container.delete()
