from datetime import datetime
from typing import Optional
from sqlmodel import Field, SQLModel


class UserQnAStats(SQLModel, table=True):
    """用户问答统计表 - 记录用户的答题统计数据"""

    __tablename__ = "user_qna_stats"
    __table_args__ = {"extend_existing": True}

    id: Optional[int] = Field(default=None, primary_key=True, description="主键ID，自增唯一标识")
    user_id: str = Field(index=True, description="用户ID")
    user_name: str = Field(index=True, description="用户名称")
    correct_count: int = Field(default=0, description="答对次数")
    wrong_count: int = Field(default=0, description="答错次数")
    tip_count: int = Field(default=0, description="提示次数")
    created_at: datetime = Field(default_factory=datetime.now, description="创建时间")
    updated_at: datetime = Field(default_factory=datetime.now, description="更新时间")


class Match(SQLModel, table=True):
    """比赛表"""
    __tablename__ = "match"
    __table_args__ = {"extend_existing": True}

    match_id: Optional[int] = Field(default=None, primary_key=True)
    group_id: str = Field(index=True, description="群ID")
    match_name: str = Field(description="比赛名称")
    is_active: bool = Field(default=True, description="是否进行中")
    question_limit: int = Field(default=0, description="答题数量限制(0不限制)")
    time_limit: int = Field(default=0, description="时间限制分钟(0不限制)")
    created_at: datetime = Field(default_factory=datetime.now)
    started_at: Optional[datetime] = Field(default=None, description="开始时间")
    ended_at: Optional[datetime] = Field(default=None, description="结束时间")


class MatchParticipant(SQLModel, table=True):
    """比赛参与者表"""
    __tablename__ = "match_participant"
    __table_args__ = {"extend_existing": True}

    id: Optional[int] = Field(default=None, primary_key=True)
    match_id: int = Field(index=True, description="比赛ID")
    user_id: str = Field(index=True, description="用户ID")
    user_name: str = Field(description="用户名称")
    correct_count: int = Field(default=0, description="答对数")
    wrong_count: int = Field(default=0, description="答错数")
    score: float = Field(default=0.0, description="得分(正确数-错误数*1/3)")
    joined_at: datetime = Field(default_factory=datetime.now)


class MatchHonor(SQLModel, table=True):
    """比赛荣誉表"""
    __tablename__ = "match_honor"
    __table_args__ = {"extend_existing": True}

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: str = Field(index=True, description="用户ID")
    match_id: int = Field(description="比赛ID")
    match_name: str = Field(description="比赛名称")
    rank: int = Field(description="名次")
    correct_count: int = Field(default=0, description="答对数")
    wrong_count: int = Field(default=0, description="答错数")
    score: float = Field(default=0.0, description="得分(正确数-错误数*1/3)")
    medal: str = Field(description="奖牌")
    created_at: datetime = Field(default_factory=datetime.now)