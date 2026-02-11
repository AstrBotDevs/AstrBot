import re

from astrbot.api import star
from astrbot.api.event import AstrMessageEvent, MessageEventResult

from ._node_binding import get_node_target, list_nodes_with_config


class ProviderCommands:
    def __init__(self, context: star.Context) -> None:
        self.context = context

    @staticmethod
    def _split_tokens(message: str) -> list[str]:
        parts = [p for p in message.strip().split() if p]
        if parts and parts[0].startswith("/"):
            parts = parts[1:]
        if parts and parts[0] == "provider":
            parts = parts[1:]
        return parts

    @staticmethod
    def _parse_kind(token: str | None) -> str:
        token = (token or "").strip().lower()
        if token in ("", "llm", "agent", "chat"):
            return "llm"
        if token in ("tts", "stt"):
            return token
        return "llm"

    @staticmethod
    def _kind_to_node_name(kind: str) -> str:
        return {"llm": "agent", "tts": "tts", "stt": "stt"}[kind]

    def _providers_by_kind(self, kind: str):
        if kind == "llm":
            return list(self.context.get_all_providers())
        if kind == "tts":
            return list(self.context.get_all_tts_providers())
        return list(self.context.get_all_stt_providers())

    def _resolve_provider(self, kind: str, token: str):
        providers = self._providers_by_kind(kind)
        if token.isdigit():
            idx = int(token)
            if 1 <= idx <= len(providers):
                return providers[idx - 1]
            return None
        for prov in providers:
            if prov.meta().id == token:
                return prov
        return None

    def _render_node_bindings(self, event: AstrMessageEvent) -> str:
        rows: list[str] = []
        mapping = {"llm": "agent", "tts": "tts", "stt": "stt"}
        for kind, node_name in mapping.items():
            targets = list_nodes_with_config(self.context, event, node_name)
            if not targets:
                continue
            rows.append(f"[{kind}] 节点绑定：")
            for idx, target in enumerate(targets, start=1):
                bound = target.config.get("provider_id", "") or "<继承>"
                rows.append(f"  {idx}. 节点={target.node.uuid[:8]} provider={bound}")
        return "\n".join(rows) if rows else "当前 Chain 没有可绑定 provider 的节点。"

    def _render_provider_list(self) -> str:
        parts: list[str] = []
        for kind in ("llm", "tts", "stt"):
            providers = self._providers_by_kind(kind)
            if not providers:
                continue
            parts.append(f"[{kind}] 可用 provider：")
            for idx, prov in enumerate(providers, start=1):
                meta = prov.meta()
                model = getattr(meta, "model", "")
                suffix = f" ({model})" if model else ""
                parts.append(f"  {idx}. {meta.id}{suffix}")
        return "\n".join(parts) if parts else "当前没有已加载的 provider。"

    async def provider(
        self,
        event: AstrMessageEvent,
        idx: str | int | None = None,
        idx2: int | None = None,
    ):
        del idx, idx2
        chain = event.chain_config
        if not chain:
            event.set_result(MessageEventResult().message("未找到已路由的 Chain。"))
            return

        tokens = self._split_tokens(event.message_str)
        if not tokens:
            msg = [
                f"当前 Chain: {chain.chain_id}",
                self._render_provider_list(),
                "",
                self._render_node_bindings(event),
                "",
                "用法：",
                "/provider <provider_idx_or_id>  # 兼容单 agent 绑定",
                "/provider <llm|tts|stt> <provider_idx_or_id>  # 兼容单节点绑定",
                "/provider <llm|tts|stt> <node_idx|node_uuid> <provider_idx_or_id>",
                "/provider node ls",
            ]
            event.set_result(
                MessageEventResult().message("\n".join(msg)).use_t2i(False)
            )
            return

        if tokens[0] == "node" and len(tokens) >= 2 and tokens[1] == "ls":
            event.set_result(
                MessageEventResult()
                .message(self._render_node_bindings(event))
                .use_t2i(False)
            )
            return

        kind = "llm"
        remaining = tokens
        if tokens[0] in ("llm", "agent", "chat", "tts", "stt"):
            kind = self._parse_kind(tokens[0])
            remaining = tokens[1:]

        node_name = self._kind_to_node_name(kind)
        node_targets = list_nodes_with_config(self.context, event, node_name)
        if not node_targets:
            event.set_result(
                MessageEventResult().message(
                    f"当前 Chain 中没有可用于 {kind} 绑定的 `{node_name}` 节点。"
                )
            )
            return

        selector: str | None = None
        provider_token: str | None = None

        if len(remaining) == 1:
            provider_token = remaining[0]
            if len(node_targets) > 1:
                event.set_result(
                    MessageEventResult().message(
                        f"检测到多个 `{node_name}` 节点，请使用 `/provider {kind} <node_idx|node_uuid> <provider>` 指定节点。"
                    )
                )
                return
        elif len(remaining) >= 2:
            selector = remaining[0]
            provider_token = remaining[1]

        if not provider_token:
            event.set_result(MessageEventResult().message("缺少 provider 参数。"))
            return

        provider = self._resolve_provider(kind, provider_token)
        if not provider:
            event.set_result(MessageEventResult().message("provider 序号或 ID 无效。"))
            return

        target = get_node_target(
            self.context,
            event,
            node_name,
            selector=selector,
        )
        if not target:
            if selector:
                event.set_result(MessageEventResult().message("节点选择器无效。"))
            else:
                event.set_result(
                    MessageEventResult().message(
                        f"检测到多个 `{node_name}` 节点，请显式指定节点。"
                    )
                )
            return

        target.config.save_config({"provider_id": provider.meta().id})
        event.set_result(
            MessageEventResult().message(
                f"已将 {kind} provider `{provider.meta().id}` 绑定到 Chain `{chain.chain_id}` 的节点 `{target.node.uuid[:8]}`。"
            )
        )

    async def model_ls(
        self,
        message: AstrMessageEvent,
        idx_or_name: int | str | None = None,
    ):
        prov = self.context.get_chat_provider_for_event(message)
        if not prov:
            message.set_result(
                MessageEventResult().message("当前没有可用的 LLM provider。")
            )
            return
        api_key_pattern = re.compile(r"key=[^&'\" ]+")

        if idx_or_name is None:
            try:
                models = await prov.get_models()
            except BaseException as e:
                err_msg = api_key_pattern.sub("key=***", str(e))
                message.set_result(
                    MessageEventResult()
                    .message("获取模型列表失败：" + err_msg)
                    .use_t2i(False)
                )
                return

            parts = ["模型列表："]
            for i, model in enumerate(models, 1):
                parts.append(f"\n{i}. {model}")
            parts.append(f"\n当前模型：[{prov.get_model() or '-'}]")
            parts.append("\n使用 /model <index|name> 切换模型。")
            message.set_result(
                MessageEventResult().message("".join(parts)).use_t2i(False)
            )
        elif isinstance(idx_or_name, int):
            try:
                models = await prov.get_models()
            except BaseException as e:
                message.set_result(
                    MessageEventResult().message("获取模型列表失败：" + str(e))
                )
                return
            if idx_or_name > len(models) or idx_or_name < 1:
                message.set_result(MessageEventResult().message("模型序号无效。"))
                return
            new_model = models[idx_or_name - 1]
            prov.set_model(new_model)
            message.set_result(
                MessageEventResult().message(f"已切换到模型 {prov.get_model()}。")
            )
        else:
            prov.set_model(idx_or_name)
            message.set_result(
                MessageEventResult().message(f"已切换到模型 {prov.get_model()}。")
            )

    async def key(self, message: AstrMessageEvent, index: int | None = None):
        prov = self.context.get_chat_provider_for_event(message)
        if not prov:
            message.set_result(
                MessageEventResult().message("当前没有可用的 LLM provider。")
            )
            return

        if index is None:
            keys_data = prov.get_keys()
            curr_key = prov.get_current_key()
            parts = ["可用密钥："]
            for i, k in enumerate(keys_data, 1):
                parts.append(f"\n{i}. {k[:8]}")
            parts.append(f"\n当前密钥：{curr_key[:8]}")
            parts.append(f"\n当前模型：{prov.get_model()}")
            parts.append("\n使用 /key <index> 切换密钥。")
            message.set_result(
                MessageEventResult().message("".join(parts)).use_t2i(False)
            )
            return

        keys_data = prov.get_keys()
        if index > len(keys_data) or index < 1:
            message.set_result(MessageEventResult().message("密钥序号无效。"))
            return
        new_key = keys_data[index - 1]
        prov.set_key(new_key)
        message.set_result(MessageEventResult().message("密钥切换成功。"))
