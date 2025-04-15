import datetime
import time
import asyncio
import zoneinfo
from typing import Optional, Union
from astrbot.core import logger


class Time:
    """
    时间类, 为Core与插件提供统一的时间接口
    """

    DateTime = datetime.datetime
    TimeDelta = datetime.timedelta

    _initialized = False
    _timezone = None

    @classmethod
    def initialize(cls, timezone_str: Optional[str] = None) -> None:
        """
        初始化时间

        Args:
            timezone_str (str): 时区字符串, 例如 "Asia/Shanghai"
        """
        if cls._initialized:
            logger.debug("Time 已初始化, 跳过重复初始化")
            return

        if not timezone_str:
            cls._timezone = None
        else:
            try:
                cls._timezone = zoneinfo.ZoneInfo(timezone_str)
                logger.info(f"Time: 时区设置为 {timezone_str}")
            except zoneinfo.ZoneInfoNotFoundError:
                logger.error(f"Time: 无效的时区字符串 {timezone_str}, 使用默认时区")
                cls._timezone = None

        cls._initialized = True

    @classmethod
    def now(cls):
        """
        获取当前时间

        Returns:

            datetime: 当前时间
        """
        return (
            datetime.datetime.now(cls._timezone)
            if cls._timezone
            else datetime.datetime.now()
        )

    @classmethod
    def time(cls) -> float:
        """
        获取当前时间

        Returns:
            float: 当前时间
        """
        return cls.timestamp() if cls._timezone else time.time()

    @classmethod
    def timestamp(cls) -> float:
        """
        获取当前时间戳(秒)

        Returns:
            float: 当前时间戳(秒)
        """
        return cls.now().timestamp() if cls._timezone else time.time()

    @classmethod
    def timestamp_ms(cls) -> int:
        """
        获取当前时间戳(毫秒)

        Returns:
            int: 当前时间戳(毫秒)
        """
        return int(cls.timestamp() * 1000) if cls._timezone else int(time.time() * 1000)

    @classmethod
    def format_datetime(
        cls, dt: Optional[datetime.datetime] = None, fmt: str = "%Y-%m-%d %H:%M:%S"
    ) -> str:
        """
        格式化时间为字符串

        Args:
            dt (datetime): 时间对象, 默认为当前时间
            fmt (str): 格式化字符串, 默认为 "%Y-%m-%d %H:%M:%S"

        Returns:
            str: 格式化后的时间字符串
        """
        if dt is None:
            dt = cls.now()
        return dt.strftime(fmt)

    @classmethod
    def parse_datetime(cls, datetime_str: str, fmt: str = "%Y-%m-%d %H:%M:%S"):
        """
        从字符串解析为datetime对象

        Args:
            datetime_str (str): 时间字符串
            fmt (str): 格式化字符串

        Returns:
            datetime.datetime: 解析后的datetime对象
        """
        return cls.DateTime.strptime(datetime_str, fmt)

    @classmethod
    def fromtimestamp(cls, timestamp: float) -> datetime.datetime:
        """
        从时间戳创建datetime对象

        Args:
            timestamp (float): 时间戳

        Returns:
            datetime.datetime: 创建的datetime对象
        """
        return (
            datetime.datetime.fromtimestamp(timestamp, cls._timezone)
            if cls._timezone
            else datetime.datetime.fromtimestamp(timestamp)
        )

    @classmethod
    def measure_time(cls, start_time: Optional[float] = None, unit: str = "s") -> float:
        """
        测量指定时间到现在经过的时间，支持不同时间单位

        Args:
            start_time (Optional[float], optional): 开始的时间戳(秒). 如果为None则返回当前时间戳.
            unit (str, optional): 返回时间的单位, 可选值: 's'(秒), 'ms'(毫秒), 默认为's'

        Returns:
            float: 经过的时间(按指定单位)或当前时间戳(秒)
        """
        if start_time is None:
            return cls.timestamp()
        if unit == "s":
            return cls.timestamp() - start_time
        elif unit == "ms":
            return cls.timestamp_ms() - start_time
        else:
            raise ValueError("无效的时间单位, 可选值: 's'(秒), 'ms'(毫秒)")

    @classmethod
    def get_timezone_str(cls) -> Optional[str]:
        """
        获取当前时区字符串

        Returns:
            Optional[str]: 当前时区字符串, 如果未设置则返回None
        """
        if cls._timezone:
            return str(cls._timezone)
        return None

    @classmethod
    def get_timezone(cls) -> Optional[zoneinfo.ZoneInfo]:
        """
        获取当前时区对象

        Returns:
            Optional[zoneinfo.ZoneInfo]: 当前时区对象, 如果未设置则返回None
        """
        return cls._timezone if cls._timezone else None

    @classmethod
    def from_timestamp(cls, timestamp: float, unit: str = "s") -> datetime.datetime:
        """
        从时间戳创建datetime对象

        Args:
            timestamp (float): 时间戳
            unit (str, optional): 时间单位, 可选值: 's'(秒), 'ms'(毫秒), 默认为's'

        Returns:
            datetime.datetime: 创建的datetime对象
        """
        if unit == "s":
            return datetime.datetime.fromtimestamp(timestamp)
        elif unit == "ms":
            return datetime.datetime.fromtimestamp(timestamp / 1000)
        else:
            raise ValueError("无效的时间单位, 可选值: 's'(秒), 'ms'(毫秒)")

    @classmethod
    def utcnow(cls) -> datetime.datetime:
        """
        获取当前UTC时间

        Returns:
            datetime.datetime: 当前UTC时间
        """
        return datetime.datetime.now(datetime.timezone.utc)

    @classmethod
    def sleep(cls, seconds: float) -> None:
        """
        同步休眠指定的秒数

        Args:
            seconds (float): 休眠的秒数
        """
        time.sleep(seconds)

    @classmethod
    async def async_sleep(cls, seconds: float) -> None:
        """
        异步休眠指定的秒数

        Args:
            seconds (float): 休眠的秒数
        """
        await asyncio.sleep(seconds)

    @classmethod
    def timedelta(
        cls,
        days: float = 0,
        seconds: float = 0,
        microseconds: float = 0,
        milliseconds: float = 0,
        minutes: float = 0,
        hours: float = 0,
        weeks: float = 0,
    ) -> datetime.timedelta:
        """
        创建时间间隔对象

        Args:
            days (float): 天数
            seconds (float): 秒数
            microseconds (float): 微秒数
            milliseconds (float): 毫秒数
            minutes (float): 分钟数
            hours (float): 小时数
            weeks (float): 周数

        Returns:
            datetime.timedelta: 创建的时间间隔对象
        """
        return datetime.timedelta(
            days=days,
            seconds=seconds,
            microseconds=microseconds,
            milliseconds=milliseconds,
            minutes=minutes,
            hours=hours,
            weeks=weeks,
        )

    @classmethod
    def add_time(
        cls, dt: datetime.datetime, delta: Union[datetime.timedelta, float]
    ) -> datetime.datetime:
        """
        在时间上添加时间间隔

        Args:
            dt (datetime.datetime): 原始时间
            delta (Union[datetime.timedelta, float]): 要添加的时间间隔(timedelta对象或秒数)

        Returns:
            datetime.datetime: 添加时间间隔后的新时间
        """
        if isinstance(delta, float) or isinstance(delta, int):
            delta = datetime.timedelta(seconds=delta)
        return dt + delta

    @classmethod
    def subtract_time(
        cls, dt: datetime.datetime, delta: Union[datetime.timedelta, float]
    ) -> datetime.datetime:
        """
        从时间中减去时间间隔

        Args:
            dt (datetime.datetime): 原始时间
            delta (Union[datetime.timedelta, float]): 要减去的时间间隔(timedelta对象或秒数)

        Returns:
            datetime.datetime: 减去时间间隔后的新时间
        """
        if isinstance(delta, float) or isinstance(delta, int):
            delta = datetime.timedelta(seconds=delta)
        return dt - delta

    @classmethod
    def time_diff(
        cls, dt1: datetime.datetime, dt2: datetime.datetime, unit: str = "s"
    ) -> float:
        """
        计算两个时间点之间的差值

        Args:
            dt1 (datetime.datetime): 第一个时间点
            dt2 (datetime.datetime): 第二个时间点
            unit (str): 返回的时间单位，'s'表示秒，'ms'表示毫秒

        Returns:
            float: 两个时间点之间的差值，单位由unit参数指定
        """
        diff_seconds = (dt1 - dt2).total_seconds()
        if unit == "s":
            return diff_seconds
        elif unit == "ms":
            return diff_seconds * 1000
        else:
            raise ValueError("无效的时间单位，可选值: 's'(秒), 'ms'(毫秒)")
