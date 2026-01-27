from astrbot import logger
from astrbot.core.astrbot_config_mgr import AstrBotConfigManager
from astrbot.core.db import BaseDatabase
from astrbot.core.db.po import Persona, PersonaFolder, Personality
from astrbot.core.platform.message_session import MessageSession

DEFAULT_PERSONALITY = Personality(
    prompt="You are a helpful and friendly assistant.",
    name="default",
    begin_dialogs=[],
    mood_imitation_dialogs=[],
    tools=None,
    skills=None,
    _begin_dialogs_processed=[],
    _mood_imitation_dialogs_processed="",
)


class PersonaManager:
    def __init__(self, db_helper: BaseDatabase, acm: AstrBotConfigManager):
        self.db = db_helper
        self.acm = acm
        default_ps = acm.default_conf.get("provider_settings", {})
        self.default_persona: str = default_ps.get("default_personality", "default")
        self.personas: list[Persona] = []
        self.selected_default_persona: Persona | None = None

        self.personas_v3: list[Personality] = []
        self.selected_default_persona_v3: Personality | None = None
        self.persona_v3_config: list[dict] = []

    async def initialize(self):
        self.personas = await self.get_all_personas()
        self.get_v3_persona_data()
        logger.info(f"已加载 {len(self.personas)} 个人格。")

    async def get_persona(self, persona_id: str):
        """获取指定 persona 的信息"""
        persona = await self.db.get_persona_by_id(persona_id)
        if not persona:
            raise ValueError(f"Persona with ID {persona_id} does not exist.")
        return persona

    async def get_default_persona_v3(
        self,
        umo: str | MessageSession | None = None,
    ) -> Personality:
        """获取默认 persona"""
        cfg = self.acm.get_conf(umo)
        default_persona_id = cfg.get("provider_settings", {}).get(
            "default_personality",
            "default",
        )
        if not default_persona_id or default_persona_id == "default":
            return DEFAULT_PERSONALITY
        try:
            return next(p for p in self.personas_v3 if p["name"] == default_persona_id)
        except Exception:
            return DEFAULT_PERSONALITY

    async def delete_persona(self, persona_id: str):
        """删除指定 persona"""
        if not await self.db.get_persona_by_id(persona_id):
            raise ValueError(f"Persona with ID {persona_id} does not exist.")
        await self.db.delete_persona(persona_id)
        self.personas = [p for p in self.personas if p.persona_id != persona_id]
        self.get_v3_persona_data()

    async def update_persona(
        self,
        persona_id: str,
        system_prompt: str | None = None,
        begin_dialogs: list[str] | None = None,
        tools: list[str] | None = None,
        skills: list[str] | None = None,
    ):
        """更新指定 persona 的信息。tools 参数为 None 时表示使用所有工具，空列表表示不使用任何工具"""
        existing_persona = await self.db.get_persona_by_id(persona_id)
        if not existing_persona:
            raise ValueError(f"Persona with ID {persona_id} does not exist.")
        persona = await self.db.update_persona(
            persona_id,
            system_prompt,
            begin_dialogs,
            tools=tools,
            skills=skills,
        )
        if persona:
            for i, p in enumerate(self.personas):
                if p.persona_id == persona_id:
                    self.personas[i] = persona
                    break
        self.get_v3_persona_data()
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
        parent_id: str | None = None,
        description: str | None = None,
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
        self.get_v3_persona_data()

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
            folder_id=folder_id,
            sort_order=sort_order,
        )
        self.personas.append(new_persona)
        self.get_v3_persona_data()
        return new_persona

    def get_v3_persona_data(
        self,
    ) -> tuple[list[dict], list[Personality], Personality]:
        """获取 AstrBot <4.0.0 版本的 persona 数据。

        Returns:
            - list[dict]: 包含 persona 配置的字典列表。
            - list[Personality]: 包含 Personality 对象的列表。
            - Personality: 默认选择的 Personality 对象。

        """
        v3_persona_config = [
            {
                "prompt": persona.system_prompt,
                "name": persona.persona_id,
                "begin_dialogs": persona.begin_dialogs or [],
                "mood_imitation_dialogs": [],  # deprecated
                "tools": persona.tools,
                "skills": persona.skills,
            }
            for persona in self.personas
        ]

        personas_v3: list[Personality] = []
        selected_default_persona: Personality | None = None

        for persona_cfg in v3_persona_config:
            begin_dialogs = persona_cfg.get("begin_dialogs", [])
            bd_processed = []
            if begin_dialogs:
                if len(begin_dialogs) % 2 != 0:
                    logger.error(
                        f"{persona_cfg['name']} 人格情景预设对话格式不对，条数应该为偶数。",
                    )
                    begin_dialogs = []
                user_turn = True
                for dialog in begin_dialogs:
                    bd_processed.append(
                        {
                            "role": "user" if user_turn else "assistant",
                            "content": dialog,
                            "_no_save": None,  # 不持久化到 db
                        },
                    )
                    user_turn = not user_turn

            try:
                persona = Personality(
                    **persona_cfg,
                    _begin_dialogs_processed=bd_processed,
                    _mood_imitation_dialogs_processed="",  # deprecated
                )
                if persona["name"] == self.default_persona:
                    selected_default_persona = persona
                personas_v3.append(persona)
            except Exception as e:
                logger.error(f"解析 Persona 配置失败：{e}")

        if not selected_default_persona and len(personas_v3) > 0:
            # 默认选择第一个
            selected_default_persona = personas_v3[0]

        if not selected_default_persona:
            selected_default_persona = DEFAULT_PERSONALITY
            personas_v3.append(selected_default_persona)

        self.personas_v3 = personas_v3
        self.selected_default_persona_v3 = selected_default_persona
        self.persona_v3_config = v3_persona_config
        self.selected_default_persona = Persona(
            persona_id=selected_default_persona["name"],
            system_prompt=selected_default_persona["prompt"],
            begin_dialogs=selected_default_persona["begin_dialogs"],
            tools=selected_default_persona["tools"] or None,
            skills=selected_default_persona["skills"] or None,
        )

        return v3_persona_config, personas_v3, selected_default_persona
