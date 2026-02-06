import re

from astrbot.api import star
from astrbot.api.event import AstrMessageEvent, MessageEventResult

from ._node_binding import get_node_target, list_nodes_with_config


class ProviderCommands:
    def __init__(self, context: star.Context):
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
            rows.append(f"[{kind}] nodes:")
            for idx, target in enumerate(targets, start=1):
                bound = target.config.get("provider_id", "") or "<inherit>"
                rows.append(f"  {idx}. {target.node.uuid[:8]} provider={bound}")
        return (
            "\n".join(rows) if rows else "No provider-capable nodes in current chain."
        )

    def _render_provider_list(self) -> str:
        parts: list[str] = []
        for kind in ("llm", "tts", "stt"):
            providers = self._providers_by_kind(kind)
            if not providers:
                continue
            parts.append(f"[{kind}] providers:")
            for idx, prov in enumerate(providers, start=1):
                meta = prov.meta()
                model = getattr(meta, "model", "")
                suffix = f" ({model})" if model else ""
                parts.append(f"  {idx}. {meta.id}{suffix}")
        return "\n".join(parts) if parts else "No providers loaded."

    async def provider(
        self,
        event: AstrMessageEvent,
        idx: str | int | None = None,
        idx2: int | None = None,
    ):
        del idx, idx2
        chain = event.chain_config
        if not chain:
            event.set_result(MessageEventResult().message("No routed chain found."))
            return

        tokens = self._split_tokens(event.message_str)
        if not tokens:
            msg = [
                f"Chain: {chain.chain_id}",
                self._render_provider_list(),
                "",
                self._render_node_bindings(event),
                "",
                "Usage:",
                "/provider <provider_idx_or_id>  # single-agent compatibility",
                "/provider <llm|tts|stt> <provider_idx_or_id>  # single-node compatibility",
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
                    f"Current chain has no `{node_name}` node for {kind} provider binding."
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
                        f"Multiple `{node_name}` nodes found. Use `/provider {kind} <node_idx|node_uuid> <provider>`."
                    )
                )
                return
        elif len(remaining) >= 2:
            selector = remaining[0]
            provider_token = remaining[1]

        if not provider_token:
            event.set_result(MessageEventResult().message("Missing provider argument."))
            return

        provider = self._resolve_provider(kind, provider_token)
        if not provider:
            event.set_result(
                MessageEventResult().message("Invalid provider index or id.")
            )
            return

        target = get_node_target(
            self.context,
            event,
            node_name,
            selector=selector,
        )
        if not target:
            if selector:
                event.set_result(MessageEventResult().message("Invalid node selector."))
            else:
                event.set_result(
                    MessageEventResult().message(
                        f"Multiple `{node_name}` nodes found. Please specify a node selector."
                    )
                )
            return

        target.config.save_config({"provider_id": provider.meta().id})
        event.set_result(
            MessageEventResult().message(
                f"Bound {kind} provider `{provider.meta().id}` to node `{target.node.uuid[:8]}` in chain `{chain.chain_id}`."
            )
        )

    async def model_ls(
        self,
        message: AstrMessageEvent,
        idx_or_name: int | str | None = None,
    ):
        prov = self.context.get_using_provider(message.unified_msg_origin)
        if not prov:
            message.set_result(MessageEventResult().message("No active LLM provider."))
            return
        api_key_pattern = re.compile(r"key=[^&'\" ]+")

        if idx_or_name is None:
            try:
                models = await prov.get_models()
            except BaseException as e:
                err_msg = api_key_pattern.sub("key=***", str(e))
                message.set_result(
                    MessageEventResult()
                    .message("Failed to load models: " + err_msg)
                    .use_t2i(False)
                )
                return

            parts = ["Models:"]
            for i, model in enumerate(models, 1):
                parts.append(f"\n{i}. {model}")
            parts.append(f"\nCurrent model: [{prov.get_model() or '-'}]")
            parts.append("\nUse /model <index|name> to switch model.")
            message.set_result(
                MessageEventResult().message("".join(parts)).use_t2i(False)
            )
        elif isinstance(idx_or_name, int):
            try:
                models = await prov.get_models()
            except BaseException as e:
                message.set_result(
                    MessageEventResult().message("Failed to load models: " + str(e))
                )
                return
            if idx_or_name > len(models) or idx_or_name < 1:
                message.set_result(MessageEventResult().message("Invalid model index."))
                return
            new_model = models[idx_or_name - 1]
            prov.set_model(new_model)
            message.set_result(
                MessageEventResult().message(f"Switched model to {prov.get_model()}")
            )
        else:
            prov.set_model(idx_or_name)
            message.set_result(
                MessageEventResult().message(f"Switched model to {prov.get_model()}")
            )

    async def key(self, message: AstrMessageEvent, index: int | None = None):
        prov = self.context.get_using_provider(message.unified_msg_origin)
        if not prov:
            message.set_result(MessageEventResult().message("No active LLM provider."))
            return

        if index is None:
            keys_data = prov.get_keys()
            curr_key = prov.get_current_key()
            parts = ["Keys:"]
            for i, k in enumerate(keys_data, 1):
                parts.append(f"\n{i}. {k[:8]}")
            parts.append(f"\nCurrent key: {curr_key[:8]}")
            parts.append(f"\nCurrent model: {prov.get_model()}")
            parts.append("\nUse /key <index> to switch key.")
            message.set_result(
                MessageEventResult().message("".join(parts)).use_t2i(False)
            )
            return

        keys_data = prov.get_keys()
        if index > len(keys_data) or index < 1:
            message.set_result(MessageEventResult().message("Invalid key index."))
            return
        new_key = keys_data[index - 1]
        prov.set_key(new_key)
        message.set_result(MessageEventResult().message("Switched key successfully."))
