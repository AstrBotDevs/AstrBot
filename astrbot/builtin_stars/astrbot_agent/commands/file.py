import os

import astrbot.api.message_components as Comp
from astrbot.api import logger
from astrbot.api.all import Context
from astrbot.api.event import AstrMessageEvent, MessageChain
from astrbot.core.utils.session_waiter import (
    SessionController,
    session_waiter,
)

from ..sandbox_client import SandboxClient


class FileCommand:
    def __init__(self, context: Context) -> None:
        self.context = context
        self.user_file_uploads: dict[str, list[str]] = {}  # umo -> file_path
        self.user_file_uploaded_files: dict[str, list[str]] = {}  # umo -> file_path
        """记录用户上传过的文件，保存了文件在沙箱中的路径。这个在用户下一次 LLM 请求时会被用到，然后清空。"""

    async def _upload_file_to_sandbox(self, event: AstrMessageEvent) -> list[str]:
        """将用户上传的文件上传到沙箱"""
        sender_id = event.get_sender_id()
        sb = await SandboxClient().get_ship(event.unified_msg_origin)
        fpath_ls = self.user_file_uploads[sender_id]
        errors = []
        for path in fpath_ls:
            try:
                fname = os.path.basename(path)
                data = await sb.upload_file(path, fname)
                success = data.get("success", False)
                if not success:
                    raise Exception(f"Upload failed: {data}")
                file_path = data.get("file_path", "")
                logger.info(f"File {fname} uploaded to sandbox at {file_path}")
                self.user_file_uploaded_files.setdefault(sender_id, []).append(
                    file_path
                )
            except Exception as e:
                errors.append((path, str(e)))
                logger.error(f"Error uploading file {path}: {e}")

        # clean up files
        for path in fpath_ls:
            try:
                os.remove(path)
            except Exception as e:
                logger.error(f"Error removing temp file {path}: {e}")

        return errors

    async def file(self, event: AstrMessageEvent):
        """等待用户上传文件或图片"""
        await event.send(
            MessageChain().message(
                f"请上传一个或多个文件(或图片)，使用 /endupload 结束上传。(请求者 ID: {event.get_sender_id()})"
            )
        )
        try:

            @session_waiter(timeout=600, record_history_chains=False)  # type: ignore
            async def empty_mention_waiter(
                controller: SessionController, event: AstrMessageEvent
            ):
                idiom = event.message_str
                sender_id = event.get_sender_id()

                if idiom == "endupload":
                    files = self.user_file_uploads.get(sender_id, [])
                    if not files:
                        await event.send(
                            event.plain_result("你没有上传任何文件，上传已取消。")
                        )
                        controller.stop()
                        return
                    await event.send(
                        event.plain_result(f"开始上传 {len(files)} 个文件到沙箱...")
                    )
                    errors = await self._upload_file_to_sandbox(event)
                    if errors:
                        error_msgs = "\n".join(
                            [f"{path}: {err}" for path, err in errors]
                        )
                        await event.send(
                            event.plain_result(
                                f"上传中出现错误:\n{error_msgs}\n其他文件已成功上传。"
                            )
                        )
                    else:
                        await event.send(
                            event.plain_result(
                                f"上传完毕，共上传 {len(files)} 个文件。文件信息已被保存，下一次 LLM 请求时会自动将信息附上。"
                            )
                        )
                    self.user_file_uploads.pop(sender_id, None)
                    controller.stop()
                    return

                # 解析文件或图片消息
                for comp in event.message_obj.message:
                    if isinstance(comp, (Comp.File, Comp.Image)):
                        if isinstance(comp, Comp.File):
                            path = await comp.get_file()
                            self.user_file_uploads.setdefault(
                                event.get_sender_id(), []
                            ).append(path)
                        elif isinstance(comp, Comp.Image):
                            path = await comp.convert_to_file_path()
                            self.user_file_uploads.setdefault(
                                event.get_sender_id(), []
                            ).append(path)
                        fname = os.path.basename(path)
                        await event.send(
                            event.plain_result(
                                f"已接收文件: {fname}，继续上传或发送 /endupload 结束。"
                            )
                        )

            try:
                await empty_mention_waiter(event)
            except TimeoutError as _:
                await event.send(event.plain_result("等待上传超时，上传已取消。"))
            except Exception as e:
                await event.send(
                    event.plain_result("发生错误，请联系管理员: " + str(e))
                )
            finally:
                event.stop_event()
        except Exception as e:
            logger.error("handle_empty_mention error: " + str(e))
