from astrbot import logger
from astrbot.core.astrbot_config_mgr import AstrBotConfigManager
from astrbot.core.db.po import Persona, PersonaFolder
from astrbot.core.db.protocols import PersonaStore
from astrbot.core.persona_runtime.models import Personality
from astrbot.core.platform.message_session import MessageSession
from astrbot.core.sentinels import NOT_GIVEN
from astrbot.core.utils.shared_preferences import SharedPreferences

DEFAULT_PERSONALITY = Personality(
    prompt="You are a helpful and friendly assistant.",
    name="default",
    begin_dialogs=[],
    tools=None,
    skills=None,
    custom_error_message=None,
    _begin_dialogs_processed=[],
)


class PersonaManager:
    def __init__(
        self,
        db_helper: PersonaStore,
        acm: AstrBotConfigManager,
        preferences: SharedPreferences,
    ) -> None:
        self.db = db_helper
        self.acm = acm
        self.preferences = preferences
        default_ps = acm.default_conf.get("provider_settings", {})
        self.default_persona: str = default_ps.get("default_personality", "default")
        self.personas: list[Persona] = []
        self.runtime_personas: list[Personality] = []
        self.selected_runtime_persona: Personality | None = None

    async def initialize(self) -> None:
        self.personas = await self.get_all_personas()
        self._refresh_runtime_personas()
        logger.info("Loaded %s personas.", len(self.personas))

    async def get_persona(self, persona_id: str):
        """获取指定 persona 的信息"""
        persona = await self.db.get_persona_by_id(persona_id)
        if not persona:
            raise ValueError(f"Persona with ID {persona_id} does not exist.")
        return persona

    def get_runtime_persona_by_id(self, persona_id: str | None) -> Personality | None:
        """Resolve a runtime persona object by id.

        - None/empty id returns None.
        - "default" maps to in-memory DEFAULT_PERSONALITY.
        - Otherwise search in runtime_personas by persona name.
        """
        if not persona_id:
            return None
        if persona_id == "default":
            return DEFAULT_PERSONALITY
        return next(
            (
                persona
                for persona in self.runtime_personas
                if persona["name"] == persona_id
            ),
            None,
        )

    async def get_default_runtime_persona(
        self,
        umo: str | MessageSession | None = None,
    ) -> Personality:
        """获取默认 persona"""
        cfg = self.acm.get_conf(umo)
        default_persona_id = cfg.get("provider_settings", {}).get(
            "default_personality",
            "default",
        )
        return self.get_runtime_persona_by_id(default_persona_id) or DEFAULT_PERSONALITY

    async def resolve_selected_persona(
        self,
        *,
        umo: str | MessageSession,
        conversation_persona_id: str | None,
        platform_name: str,
        provider_settings: dict | None = None,
    ) -> tuple[str | None, Personality | None, str | None, bool]:
        """解析当前会话最终生效的人格。

        Returns:
            tuple:
                - selected persona_id
                - selected persona object
                - force applied persona_id from session rule
                - whether use webchat special default persona
        """
        session_service_config = (
            await self.preferences.get_async(
                scope="umo",
                scope_id=str(umo),
                key="session_service_config",
                default={},
            )
            or {}
        )

        force_applied_persona_id = session_service_config.get("persona_id")
        persona_id = force_applied_persona_id

        if not persona_id:
            persona_id = conversation_persona_id
            if persona_id == "[%None]":
                pass
            elif persona_id is None:
                persona_id = (provider_settings or {}).get("default_personality")

        persona = next(
            (item for item in self.runtime_personas if item["name"] == persona_id),
            None,
        )

        use_webchat_special_default = False
        if not persona and platform_name == "webchat" and persona_id != "[%None]":
            persona_id = "_chatui_default_"
            use_webchat_special_default = True

        return (
            persona_id,
            persona,
            force_applied_persona_id,
            use_webchat_special_default,
        )

    async def delete_persona(self, persona_id: str) -> None:
        """删除指定 persona"""
        if not await self.db.get_persona_by_id(persona_id):
            raise ValueError(f"Persona with ID {persona_id} does not exist.")
        await self.db.delete_persona(persona_id)
        self.personas = [p for p in self.personas if p.persona_id != persona_id]
        self._refresh_runtime_personas()

    async def update_persona(
        self,
        persona_id: str,
        system_prompt: str | None = None,
        begin_dialogs: list[str] | None = None,
        tools: list[str] | None | object = NOT_GIVEN,
        skills: list[str] | None | object = NOT_GIVEN,
        custom_error_message: str | None | object = NOT_GIVEN,
    ):
        """更新指定 persona 的信息。tools 参数为 None 时表示使用所有工具，空列表表示不使用任何工具"""
        existing_persona = await self.db.get_persona_by_id(persona_id)
        if not existing_persona:
            raise ValueError(f"Persona with ID {persona_id} does not exist.")
        update_kwargs = {}
        if tools is not NOT_GIVEN:
            update_kwargs["tools"] = tools
        if skills is not NOT_GIVEN:
            update_kwargs["skills"] = skills
        if custom_error_message is not NOT_GIVEN:
            update_kwargs["custom_error_message"] = custom_error_message

        persona = await self.db.update_persona(
            persona_id,
            system_prompt,
            begin_dialogs,
            **update_kwargs,
        )
        if persona:
            for i, p in enumerate(self.personas):
                if p.persona_id == persona_id:
                    self.personas[i] = persona
                    break
        self._refresh_runtime_personas()
        return persona

    async def get_all_personas(self) -> list[Persona]:
        """获取所有 personas"""
        return await self.db.get_personas()

    async def get_personas_by_folder(
        self, folder_id: str | None = None
    ) -> list[Persona]:
        """获取指定文件夹中的 personas

        Args:
            folder_id: 文件夹 ID，None 表示根目录
        """
        return await self.db.get_personas_by_folder(folder_id)

    async def move_persona_to_folder(
        self, persona_id: str, folder_id: str | None
    ) -> Persona | None:
        """移动 persona 到指定文件夹

        Args:
            persona_id: Persona ID
            folder_id: 目标文件夹 ID，None 表示移动到根目录
        """
        persona = await self.db.move_persona_to_folder(persona_id, folder_id)
        if persona:
            for i, p in enumerate(self.personas):
                if p.persona_id == persona_id:
                    self.personas[i] = persona
                    break
        return persona

    # ====
    # Persona Folder Management
    # ====

    async def create_folder(
        self,
        name: str,
        parent_id: str | None = None,
        description: str | None = None,
        sort_order: int = 0,
    ) -> PersonaFolder:
        """创建新的文件夹"""
        return await self.db.insert_persona_folder(
            name=name,
            parent_id=parent_id,
            description=description,
            sort_order=sort_order,
        )

    async def get_folder(self, folder_id: str) -> PersonaFolder | None:
        """获取指定文件夹"""
        return await self.db.get_persona_folder_by_id(folder_id)

    async def get_folders(self, parent_id: str | None = None) -> list[PersonaFolder]:
        """获取文件夹列表

        Args:
            parent_id: 父文件夹 ID，None 表示获取根目录下的文件夹
        """
        return await self.db.get_persona_folders(parent_id)

    async def get_all_folders(self) -> list[PersonaFolder]:
        """获取所有文件夹"""
        return await self.db.get_all_persona_folders()

    async def update_folder(
        self,
        folder_id: str,
        name: str | None = None,
        parent_id: str | None | object = NOT_GIVEN,
        description: str | None | object = NOT_GIVEN,
        sort_order: int | None = None,
    ) -> PersonaFolder | None:
        """更新文件夹信息"""
        return await self.db.update_persona_folder(
            folder_id=folder_id,
            name=name,
            parent_id=parent_id,
            description=description,
            sort_order=sort_order,
        )

    async def delete_folder(self, folder_id: str) -> None:
        """删除文件夹

        Note: 文件夹内的 personas 会被移动到根目录
        """
        await self.db.delete_persona_folder(folder_id)

    async def batch_update_sort_order(self, items: list[dict]) -> None:
        """批量更新 personas 和/或 folders 的排序顺序

        Args:
            items: 包含以下键的字典列表：
                - id: persona_id 或 folder_id
                - type: "persona" 或 "folder"
                - sort_order: 新的排序顺序值
        """
        await self.db.batch_update_sort_order(items)
        # 刷新缓存
        self.personas = await self.get_all_personas()
        self._refresh_runtime_personas()

    async def get_folder_tree(self) -> list[dict]:
        """获取文件夹树形结构

        Returns:
            树形结构的文件夹列表，每个文件夹包含 children 子列表
        """
        all_folders = await self.get_all_folders()
        folder_map: dict[str, dict] = {}

        # 创建文件夹字典
        for folder in all_folders:
            folder_map[folder.folder_id] = {
                "folder_id": folder.folder_id,
                "name": folder.name,
                "parent_id": folder.parent_id,
                "description": folder.description,
                "sort_order": folder.sort_order,
                "children": [],
            }

        # 构建树形结构
        root_folders = []
        for folder_id, folder_data in folder_map.items():
            parent_id = folder_data["parent_id"]
            if parent_id is None:
                root_folders.append(folder_data)
            elif parent_id in folder_map:
                folder_map[parent_id]["children"].append(folder_data)

        # 递归排序
        def sort_folders(folders: list[dict]) -> list[dict]:
            folders.sort(key=lambda f: (f["sort_order"], f["name"]))
            for folder in folders:
                if folder["children"]:
                    folder["children"] = sort_folders(folder["children"])
            return folders

        return sort_folders(root_folders)

    async def create_persona(
        self,
        persona_id: str,
        system_prompt: str,
        begin_dialogs: list[str] | None = None,
        tools: list[str] | None = None,
        skills: list[str] | None = None,
        custom_error_message: str | None = None,
        folder_id: str | None = None,
        sort_order: int = 0,
    ) -> Persona:
        """创建新的 persona。

        Args:
            persona_id: Persona 唯一标识
            system_prompt: 系统提示词
            begin_dialogs: 预设对话列表
            tools: 工具列表，None 表示使用所有工具，空列表表示不使用任何工具
            skills: Skills 列表，None 表示使用所有 Skills，空列表表示不使用任何 Skills
            folder_id: 所属文件夹 ID，None 表示根目录
            sort_order: 排序顺序
        """
        if await self.db.get_persona_by_id(persona_id):
            raise ValueError(f"Persona with ID {persona_id} already exists.")
        new_persona = await self.db.insert_persona(
            persona_id,
            system_prompt,
            begin_dialogs,
            tools=tools,
            skills=skills,
            custom_error_message=custom_error_message,
            folder_id=folder_id,
            sort_order=sort_order,
        )
        self.personas.append(new_persona)
        self._refresh_runtime_personas()
        return new_persona

    def _refresh_runtime_personas(self) -> None:
        runtime_personas: list[Personality] = []
        selected_runtime_persona: Personality | None = None

        for persona in self.personas:
            begin_dialogs = persona.begin_dialogs or []
            bd_processed = []
            if begin_dialogs:
                if len(begin_dialogs) % 2 != 0:
                    logger.error(
                        f"{persona.persona_id} 人格情景预设对话格式不对，条数应该为偶数。",
                    )
                    begin_dialogs = []
                user_turn = True
                for dialog in begin_dialogs:
                    bd_processed.append(
                        {
                            "role": "user" if user_turn else "assistant",
                            "content": dialog,
                            "_no_save": True,  # 不持久化到 db
                        },
                    )
                    user_turn = not user_turn

            try:
                runtime_persona = Personality(
                    prompt=persona.system_prompt,
                    name=persona.persona_id,
                    begin_dialogs=begin_dialogs,
                    tools=persona.tools,
                    skills=persona.skills,
                    custom_error_message=persona.custom_error_message,
                    _begin_dialogs_processed=bd_processed,
                )
                if runtime_persona["name"] == self.default_persona:
                    selected_runtime_persona = runtime_persona
                runtime_personas.append(runtime_persona)
            except Exception as e:
                logger.error(f"解析 Persona 配置失败：{e}")

        if not selected_runtime_persona and runtime_personas:
            selected_runtime_persona = runtime_personas[0]

        if not selected_runtime_persona:
            selected_runtime_persona = DEFAULT_PERSONALITY
            runtime_personas.append(selected_runtime_persona)

        self.runtime_personas = runtime_personas
        self.selected_runtime_persona = selected_runtime_persona
