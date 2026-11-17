# 其他

## 人格设定管理器

`PersonaManager` 负责统一加载、缓存并提供所有人格（Persona）的增删改查接口，同时兼容 AstrBot 4.x 之前的旧版人格格式（v3）。  
初始化时会自动从数据库读取全部人格，并生成一份 v3 兼容数据，供旧代码无缝使用。

```py
persona_mgr = self.context.persona_manager
```

### 主要方法

#### `get_persona`

- __Usage__
  获取根据人格 ID 获取人格数据。
- __Arguments__
  - `persona_id: str` – 人格 ID
- __Returns__
  `Persona` – 人格数据，若不存在则返回 None
- __Raises__
  `ValueError` – 当不存在时抛出

#### `get_all_personas`

- __Usage__  
  一次性获取数据库中所有人格。
- __Returns__  
  `list[Persona]` – 人格列表，可能为空

#### `create_persona`

- __Usage__  
  新建人格并立即写入数据库，成功后自动刷新本地缓存。
- __Arguments__  
  - `persona_id: str` – 新人格 ID（唯一）  
  - `system_prompt: str` – 系统提示词  
  - `begin_dialogs: list[str]` – 可选，开场对话（偶数条，user/assistant 交替）  
  - `tools: list[str]` – 可选，允许使用的工具列表；`None`=全部工具，`[]`=禁用全部
- __Returns__  
  `Persona` – 新建后的人格对象
- __Raises__  
  `ValueError` – 若 `persona_id` 已存在

#### `update_persona`

- __Usage__  
  更新现有人格的任意字段，并同步到数据库与缓存。
- __Arguments__  
  - `persona_id: str` – 待更新的人格 ID  
  - `system_prompt: str` – 可选，新的系统提示词  
  - `begin_dialogs: list[str]` – 可选，新的开场对话  
  - `tools: list[str]` – 可选，新的工具列表；语义同 `create_persona`
- __Returns__  
  `Persona` – 更新后的人格对象
- __Raises__  
  `ValueError` – 若 `persona_id` 不存在

#### `delete_persona`

- __Usage__  
  删除指定人格，同时清理数据库与缓存。
- __Arguments__  
  - `persona_id: str` – 待删除的人格 ID
- __Raises__  
  `ValueError` – 若 `persona_id` 不存在

#### `get_default_persona_v3`

- __Usage__  
  根据当前会话配置，获取应使用的默认人格（v3 格式）。  
  若配置未指定或指定的人格不存在，则回退到 `DEFAULT_PERSONALITY`。
- __Arguments__  
  - `umo: str | MessageSession | None` – 会话标识，用于读取用户级配置
- __Returns__  
  `Personality` – v3 格式的默认人格对象

::: details Persona / Personality 类型定义

```py
class Persona(SQLModel, table=True):
    """Persona is a set of instructions for LLMs to follow.

    It can be used to customize the behavior of LLMs.
    """

    __tablename__ = "personas"

    id: int = Field(primary_key=True, sa_column_kwargs={"autoincrement": True})
    persona_id: str = Field(max_length=255, nullable=False)
    system_prompt: str = Field(sa_type=Text, nullable=False)
    begin_dialogs: Optional[list] = Field(default=None, sa_type=JSON)
    """a list of strings, each representing a dialog to start with"""
    tools: Optional[list] = Field(default=None, sa_type=JSON)
    """None means use ALL tools for default, empty list means no tools, otherwise a list of tool names."""
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column_kwargs={"onupdate": datetime.now(timezone.utc)},
    )

    __table_args__ = (
        UniqueConstraint(
            "persona_id",
            name="uix_persona_id",
        ),
    )


class Personality(TypedDict):
    """LLM 人格类。

    在 v4.0.0 版本及之后，推荐使用上面的 Persona 类。并且， mood_imitation_dialogs 字段已被废弃。
    """

    prompt: str
    name: str
    begin_dialogs: list[str]
    mood_imitation_dialogs: list[str]
    """情感模拟对话预设。在 v4.0.0 版本及之后，已被废弃。"""
    tools: list[str] | None
    """工具列表。None 表示使用所有工具，空列表表示不使用任何工具"""
```

:::
