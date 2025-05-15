import os
import json
import datetime
import uuid
import zoneinfo
import astrbot.api.star as star
from astrbot.api.event import filter
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from astrbot.api.event import AstrMessageEvent, MessageEventResult
from astrbot.api import llm_tool, logger
from astrbot.core.utils.astrbot_path import get_astrbot_data_path


@star.register(
    name="astrbot-reminder", desc="使用 LLM 待办提醒", author="Soulter", version="0.0.1"
)
class Main(star.Star):
    """使用 LLM 待办提醒。只需对 LLM 说想要提醒的事情和时间即可。比如：`之后每天这个时候都提醒我做多邻国`"""

    def __init__(self, context: star.Context) -> None:
        self.context = context
        self.timezone = self.context.get_config().get("timezone")
        if not self.timezone:
            self.timezone = None
        try:
            self.timezone = zoneinfo.ZoneInfo(self.timezone) if self.timezone else None
        except Exception as e:
            logger.error(f"时区设置错误: {e}, 使用本地时区")
            self.timezone = None
        self.scheduler = AsyncIOScheduler(timezone=self.timezone)

        # set and load config
        reminder_file = os.path.join(get_astrbot_data_path(), "astrbot-reminder.json")
        if not os.path.exists(reminder_file):
            with open(reminder_file, "w", encoding="utf-8") as f:
                f.write("{}")
        with open(reminder_file, "r", encoding="utf-8") as f:
            self.reminder_data = json.load(f)

        self._init_scheduler()
        self.scheduler.start()

    def _init_scheduler(self):
        """Initialize the scheduler."""
        for group in self.reminder_data:
            for reminder in self.reminder_data[group]:
                if "id" not in reminder:
                    id_ = str(uuid.uuid4())
                    reminder["id"] = id_
                else:
                    id_ = reminder["id"]

                if "datetime" in reminder:
                    if self.check_is_outdated(reminder):
                        continue
                    self.scheduler.add_job(
                        self._reminder_callback,
                        id=id_,
                        trigger="date",
                        args=[group, reminder],
                        run_date=datetime.datetime.strptime(
                            reminder["datetime"], "%Y-%m-%d %H:%M"
                        ),
                        misfire_grace_time=60,
                    )
                elif "cron" in reminder:
                    self.scheduler.add_job(
                        self._reminder_callback,
                        trigger="cron",
                        id=id_,
                        args=[group, reminder],
                        misfire_grace_time=60,
                        **self._parse_cron_expr(reminder["cron"]),
                    )

    def check_is_outdated(self, reminder: dict):
        """Check if the reminder is outdated."""
        if "datetime" in reminder:
            reminder_time = datetime.datetime.strptime(
                reminder["datetime"], "%Y-%m-%d %H:%M"
            ).replace(tzinfo=self.timezone)
            return reminder_time < datetime.datetime.now(self.timezone)
        return False

    async def _save_data(self):
        """Save the reminder data."""
        reminder_file = os.path.join(get_astrbot_data_path(), "astrbot-reminder.json")
        with open(reminder_file, "w", encoding="utf-8") as f:
            json.dump(self.reminder_data, f, ensure_ascii=False)

    def _parse_cron_expr(self, cron_expr: str):
        fields = cron_expr.split(" ")
        return {
            "minute": fields[0],
            "hour": fields[1],
            "day": fields[2],
            "month": fields[3],
            "day_of_week": fields[4],
        }

    @llm_tool("reminder")
    async def reminder_tool(
        self,
        event: AstrMessageEvent,
        text: str = None,
        datetime_str: str = None,
        cron_expression: str = None,
        human_readable_cron: str = None,
    ):
        """Call this function when user is asking for setting a reminder.

        Args:
            text(string): Must Required. The content of the reminder.
            datetime_str(string): Required when user's reminder is a single reminder. The datetime string of the reminder, Must format with %Y-%m-%d %H:%M
            cron_expression(string): Required when user's reminder is a repeated reminder. The cron expression of the reminder.
            human_readable_cron(string): Optional. The human readable cron expression of the reminder.
        """
        if event.get_platform_name() == "qq_official":
            yield event.plain_result("reminder 暂不支持 QQ 官方机器人。")
            return

        if event.unified_msg_origin not in self.reminder_data:
            self.reminder_data[event.unified_msg_origin] = []

        if not cron_expression and not datetime_str:
            raise ValueError(
                "The cron_expression and datetime_str cannot be both None."
            )
        reminder_time = ""

        if not text:
            text = "未命名待办事项"

        if cron_expression:
            d = {
                "text": text,
                "cron": cron_expression,
                "cron_h": human_readable_cron,
                "id": str(uuid.uuid4()),
            }
            self.reminder_data[event.unified_msg_origin].append(d)
            self.scheduler.add_job(
                self._reminder_callback,
                "cron",
                id=d["id"],
                misfire_grace_time=60,
                **self._parse_cron_expr(cron_expression),
                args=[event.unified_msg_origin, d],
            )
            if human_readable_cron:
                reminder_time = f"{human_readable_cron}(Cron: {cron_expression})"
        else:
            d = {"text": text, "datetime": datetime_str, "id": str(uuid.uuid4())}
            self.reminder_data[event.unified_msg_origin].append(d)
            datetime_scheduled = datetime.datetime.strptime(
                datetime_str, "%Y-%m-%d %H:%M"
            )
            self.scheduler.add_job(
                self._reminder_callback,
                "date",
                id=d["id"],
                args=[event.unified_msg_origin, d],
                run_date=datetime_scheduled,
                misfire_grace_time=60,
            )
            reminder_time = datetime_str
        await self._save_data()
        yield event.plain_result(
            "成功设置待办事项。\n内容: "
            + text
            + "\n时间: "
            + reminder_time
            + "\n\n使用 /reminder ls 查看所有待办事项。\n使用 /tool off reminder 关闭此功能。"
        )

    @filter.command_group("reminder")
    def reminder(self):
        """The command group of the reminder."""
        pass

    async def get_upcoming_reminders(self, unified_msg_origin: str):
        """Get upcoming reminders."""
        reminders = self.reminder_data.get(unified_msg_origin, [])
        if not reminders:
            return []
        now = datetime.datetime.now(self.timezone)
        upcoming_reminders = [
            reminder
            for reminder in reminders
            if "datetime" not in reminder
            or datetime.datetime.strptime(
                reminder["datetime"], "%Y-%m-%d %H:%M"
            ).replace(tzinfo=self.timezone)
            >= now
        ]
        return upcoming_reminders

    @reminder.command("ls")
    async def reminder_ls(self, event: AstrMessageEvent):
        """List upcoming reminders."""
        reminders = await self.get_upcoming_reminders(event.unified_msg_origin)
        if not reminders:
            yield event.plain_result("没有正在进行的待办事项。")
        else:
            reminder_str = "正在进行的待办事项：\n"
            for i, reminder in enumerate(reminders):
                time_ = reminder.get("datetime", "")
                if not time_:
                    cron_expr = reminder.get("cron", "")
                    time_ = reminder.get("cron_h", "") + f"(Cron: {cron_expr})"
                reminder_str += f"{i + 1}. {reminder['text']} - {time_}\n"
            reminder_str += "\n使用 /reminder rm <id> 删除待办事项。\n"
            yield event.plain_result(reminder_str)

    @reminder.command("rm")
    async def reminder_rm(self, event: AstrMessageEvent, index: int):
        """Remove a reminder by index."""
        reminders = await self.get_upcoming_reminders(event.unified_msg_origin)

        if not reminders:
            yield event.plain_result("没有待办事项。")
        elif index < 1 or index > len(reminders):
            yield event.plain_result("索引越界。")
        else:
            reminder = reminders.pop(index - 1)
            job_id = reminder.get("id")

            # self.reminder_data[event.unified_msg_origin] = reminder
            users_reminders = self.reminder_data.get(event.unified_msg_origin, [])
            for i, r in enumerate(users_reminders):
                if r.get("id") == job_id:
                    users_reminders.pop(i)

            try:
                self.scheduler.remove_job(job_id)
            except Exception as e:
                logger.error(f"Remove job error: {e}")
                yield event.plain_result(
                    f"成功移除对应的待办事项。删除定时任务失败: {str(e)} 可能需要重启 AstrBot 以取消该提醒任务。"
                )
            await self._save_data()
            yield event.plain_result("成功删除待办事项：\n" + reminder["text"])

    async def _reminder_callback(self, unified_msg_origin: str, d: dict):
        """The callback function of the reminder."""
        logger.info(f"Reminder Activated: {d['text']}, created by {unified_msg_origin}")
        await self.context.send_message(
            unified_msg_origin,
            MessageEventResult().message(
                "待办提醒: \n\n"
                + d["text"]
                + "\n时间: "
                + d.get("datetime", "")
                + d.get("cron_h", "")
            ),
        )

    async def terminate(self):
        self.scheduler.shutdown()
        await self._save_data()
        logger.info("Reminder plugin terminated.")
