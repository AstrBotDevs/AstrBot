from astrbot.core.db import BaseDatabase
from astrbot.core.db.po import Persona, Personality
from astrbot.core.config import AstrBotConfig
from astrbot import logger


class PersonaManager:
    def __init__(self, db_helper: BaseDatabase, astrbot_config: AstrBotConfig):
        self.db = db_helper
        self.config = astrbot_config
        _ps: dict = astrbot_config["provider_settings"]
        self.default_persona: str = _ps.get("default_personality", "default")
        self.personas: list[Persona] = []

    async def initialize(self):
        self.personas = await self.get_all_personas()
        logger.info(f"已加载 {len(self.personas)} 个人格。")

    async def get_persona(self, persona_id: str):
        """获取指定 persona 的信息"""
        persona = await self.db.get_persona_by_id(persona_id)
        if not persona:
            raise ValueError(f"Persona with ID {persona_id} does not exist.")
        return persona

    async def delete_persona(self, persona_id: str):
        """删除指定 persona"""
        if not await self.db.get_persona_by_id(persona_id):
            raise ValueError(f"Persona with ID {persona_id} does not exist.")
        await self.db.delete_persona(persona_id)
        self.personas = [p for p in self.personas if p.persona_id != persona_id]

    async def update_persona(
        self,
        persona_id: str,
        system_prompt: str = None,
        begin_dialogs: list[str] = None,
    ):
        """更新指定 persona 的信息"""
        existing_persona = await self.db.get_persona_by_id(persona_id)
        if not existing_persona:
            raise ValueError(f"Persona with ID {persona_id} does not exist.")
        persona = self.db.update_persona(persona_id, system_prompt, begin_dialogs)
        if persona:
            for i, p in enumerate(self.personas):
                if p.persona_id == persona_id:
                    self.personas[i] = persona
                    break
        return persona

    async def get_all_personas(self) -> list[Persona]:
        """获取所有 personas"""
        return await self.db.get_personas()

    async def create_persona(
        self, persona_id: str, system_prompt: str, begin_dialogs: list[str] = None
    ) -> Persona:
        """创建新的 persona"""
        if await self.db.get_persona_by_id(persona_id):
            raise ValueError(f"Persona with ID {persona_id} already exists.")
        new_persona = await self.db.insert_persona(
            persona_id, system_prompt, begin_dialogs
        )
        self.personas.append(new_persona)
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
            }
            for persona in self.personas
        ]

        v3_personas: list[Personality] = []
        selected_default_persona: Personality | None = None

        for persona in v3_persona_config:
            begin_dialogs = persona.get("begin_dialogs", [])
            bd_processed = []
            if begin_dialogs:
                if len(begin_dialogs) % 2 != 0:
                    logger.error(
                        f"{persona['name']} 人格情景预设对话格式不对，条数应该为偶数。"
                    )
                    begin_dialogs = []
                user_turn = True
                for dialog in begin_dialogs:
                    bd_processed.append(
                        {
                            "role": "user" if user_turn else "assistant",
                            "content": dialog,
                            "_no_save": None,  # 不持久化到 db
                        }
                    )
                    user_turn = not user_turn

            try:
                persona = Personality(
                    **persona,
                    _begin_dialogs_processed=bd_processed,
                    _mood_imitation_dialogs_processed="",  # deprecated
                )
                if persona["name"] == self.default_persona:
                    selected_default_persona = persona
                v3_personas.append(persona)
            except Exception as e:
                logger.error(f"解析 Persona 配置失败：{e}")

        if not selected_default_persona and len(v3_personas) > 0:
            # 默认选择第一个
            selected_default_persona = v3_personas[0]

        if not selected_default_persona:
            selected_default_persona = Personality(
                prompt="You are a helpful and friendly assistant.",
                name="default",
                _begin_dialogs_processed=[],
            )
            v3_personas.append(selected_default_persona)

        return v3_persona_config, v3_personas, selected_default_persona
