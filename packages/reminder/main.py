import os
import json
import datetime
import astrbot.api.star as star
from astrbot.api.event import filter
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from astrbot.api.event import AstrMessageEvent, MessageEventResult
from astrbot.api import llm_tool, logger

@star.register(name="astrbot-reminder", desc="使用 LLM 待办提醒", author="Soulter", version="0.0.1")
class Main(star.Star):
    '''使用 LLM 待办提醒。只需对 LLM 说想要提醒的事情和时间即可。比如：`之后每天这个时候都提醒我做多邻国`'''
    def __init__(self, context: star.Context) -> None:
        self.context = context
        self.scheduler = AsyncIOScheduler()
        
        # set and load config
        if not os.path.exists("data/astrbot-reminder.json"):
            with open("data/astrbot-reminder.json", "w") as f:
                f.write("{}")
        with open("data/astrbot-reminder.json", "r") as f:
            self.reminder_data = json.load(f)
        
        self._init_scheduler()
        self.scheduler.start()
       
    def _init_scheduler(self):
        '''Initialize the scheduler.'''
        for group in self.reminder_data:
            for reminder in self.reminder_data[group]:
                if "datetime" in reminder:
                    self.scheduler.add_job(self._reminder_callback, 'date', args=[reminder["text"], reminder], run_date=datetime.datetime.strptime(reminder["datetime"], "%Y-%m-%d %H:%M"))
                elif "cron" in reminder:
                    self.scheduler.add_job(self._reminder_callback, 'cron', args=[reminder["text"], reminder], **self._parse_cron_expr(reminder["cron"]))
                
    async def _save_data(self):
        '''Save the reminder data.'''
        with open("data/astrbot-reminder.json", "w") as f:
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
    async def reminder_tool(self, event: AstrMessageEvent, text: str, datetime_str: str = None, cron_expression: str = None, human_readable_cron: str = None):
        '''Call this function when user ask for setting a reminder. 
        
        Args:
            text(string): The content of the reminder.
            datetime_str(string): Required when user's reminder is a single reminder. The datetime string of the reminder, Must format with %Y-%m-%d %H:%M
            cron_expression(string): Required when user's reminder is a repeated reminder. The cron expression of the reminder.
            human_readable_cron(string): Optional. The human readable cron expression of the reminder.
        '''
        if event.unified_msg_origin not in self.reminder_data:
            self.reminder_data[event.unified_msg_origin] = []
        
        if not cron_expression and not datetime_str:
            raise ValueError("The cron_expression and datetime_str cannot be both None.")
        reminder_time = ""
        if cron_expression:
            d = { "text": text, "cron": cron_expression, "cron_h": human_readable_cron }
            self.reminder_data[event.unified_msg_origin].append(d)
            self.scheduler.add_job(self._reminder_callback, 'cron', **self._parse_cron_expr(cron_expression), args=[event.unified_msg_origin, d])
            if human_readable_cron:
                reminder_time = f"{human_readable_cron}(Cron: {cron_expression})"
        else:
            d = { "text": text, "datetime": datetime_str }
            self.reminder_data[event.unified_msg_origin].append(d)
            datetime_scheduled = datetime.datetime.strptime(datetime_str, "%Y-%m-%d %H:%M")
            self.scheduler.add_job(self._reminder_callback, 'date', args=[event.unified_msg_origin, d], run_date=datetime_scheduled)
            reminder_time = datetime_str
        await self._save_data()
        yield event.plain_result("成功设置待办事项。\n内容: " + text + "\n时间: " + reminder_time + "\n\n使用 /reminder ls 查看所有待办事项。")
    
    @filter.command_group("reminder")
    def reminder(self):
        '''The command group of the reminder.'''
        pass
    
    @reminder.command("ls")
    async def reminder_ls(self, event: AstrMessageEvent):
        '''List all reminders.'''
        reminders = self.reminder_data.get(event.unified_msg_origin, [])
        if not reminders:
            yield event.plain_result("没有待办事项。")
        else:
            reminder_str = "待办事项：\n"
            for i, reminder in enumerate(reminders):
                time_ = reminder.get("datetime", "")
                if not time_:
                    cron_expr = reminder.get("cron", "")
                    time_ = reminder.get("cron_h", "") + f"(Cron: {cron_expr})"
                reminder_str += f"{i + 1}. {reminder['text']} - {time_}\n"
            reminder_str += "\n使用 /reminder rm <index> 删除待办事项。"
            yield event.plain_result(reminder_str)
            
    @reminder.command("rm")
    async def reminder_rm(self, event: AstrMessageEvent, index: int):
        '''Remove a reminder by index.'''
        reminders = self.reminder_data.get(event.unified_msg_origin, [])
        if not reminders:
            yield event.plain_result("没有待办事项。")
        elif index < 1 or index > len(reminders):
            yield event.plain_result("索引越界。")
        else:
            reminder = reminders.pop(index - 1)
            self.scheduler.remove_job(event.unified_msg_origin)
            await self._save_data()
            yield event.plain_result("成功删除待办事项：\n" + reminder["text"])
    
    async def _reminder_callback(self, unified_msg_origin: str, d: dict):
        '''The callback function of the reminder.'''
        logger.info(f"Reminder Activated: {d['text']}, created by {unified_msg_origin}")
        await self.context.send_message(unified_msg_origin, MessageEventResult().message("待办提醒: \n\n" + d['text'] + "\n时间: " + d.get("datetime", "") + d.get("cron_h", "")))