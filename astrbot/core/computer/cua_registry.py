from astrbot.core.computer.sandbox_registry import SandboxRegistry


class CuaSandboxRegistry(SandboxRegistry):
    def load(self) -> None:
        super().load()
        for record in self._payload["sandboxes"].values():
            if record.get("managed"):
                record["controller_session_id"] = None
                record["controller_user_id"] = None
                record["lease_expires_at"] = None
        self._prune_default_references()
