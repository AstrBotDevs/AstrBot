# Other APIs

## Persona Manager

`PersonaManager` is responsible for unified loading, caching, and providing CRUD interfaces for all Personas, while maintaining compatibility with the legacy persona format (v3) from before AstrBot 4.x.  
During initialization, it automatically reads all personas from the database and generates v3-compatible data for seamless use with legacy code.

```py
persona_mgr = self.context.persona_manager
```

### Main Methods

#### `get_persona`

- **Usage**
  Get persona data by persona ID.
- **Arguments**
  - `persona_id: str` – Persona ID
- **Returns**
  `Persona` – Persona data, returns None if it doesn't exist
- **Raises**
  `ValueError` – Raised when it doesn't exist

#### `get_all_personas`

- **Usage**  
  Retrieve all personas from the database at once.
- **Returns**  
  `list[Persona]` – Persona list, may be empty

#### `create_persona`

- **Usage**  
  Create a new persona and immediately write it to the database; automatically refreshes the local cache upon success.
- **Arguments**  
  - `persona_id: str` – New persona ID (unique)  
  - `system_prompt: str` – System prompt  
  - `begin_dialogs: list[str]` – Optional, opening dialogs (even number of entries, alternating user/assistant)  
  - `tools: list[str]` – Optional, list of allowed tools; `None`=all tools, `[]`=disable all
- **Returns**  
  `Persona` – Newly created persona object
- **Raises**  
  `ValueError` – If `persona_id` already exists

#### `update_persona`

- **Usage**  
  Update any fields of an existing persona and synchronize to database and cache.
- **Arguments**  
  - `persona_id: str` – Persona ID to update  
  - `system_prompt: str` – Optional, new system prompt  
  - `begin_dialogs: list[str]` – Optional, new opening dialogs  
  - `tools: list[str]` – Optional, new tool list; semantics same as `create_persona`
- **Returns**  
  `Persona` – Updated persona object
- **Raises**  
  `ValueError` – If `persona_id` doesn't exist

#### `delete_persona`

- **Usage**  
  Delete the specified persona and clean up both database and cache.
- **Arguments**  
  - `persona_id: str` – Persona ID to delete
- **Raises**  
  `ValueError` – If `persona_id` doesn't exist

#### `get_default_persona_v3`

- **Usage**  
  Get the default persona (v3 format) to use based on the current session configuration.  
  Falls back to `DEFAULT_PERSONALITY` if configuration doesn't specify one or the specified persona doesn't exist.
- **Arguments**  
  - `umo: str | MessageSession | None` – Session identifier, used to read user-level configuration
- **Returns**  
  `Personality` – Default persona object in v3 format

::: details Persona / Personality Type Definition

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
    """LLM Persona class.

    Starting from v4.0.0 and later, it's recommended to use the Persona class above. Additionally, the mood_imitation_dialogs field has been deprecated.
    """

    prompt: str
    name: str
    begin_dialogs: list[str]
    mood_imitation_dialogs: list[str]
    """Mood imitation dialog preset. Deprecated since v4.0.0 and later."""
    tools: list[str] | None
    """Tool list. None means use all tools, empty list means don't use any tools"""
```

:::
