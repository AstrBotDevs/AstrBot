from ..olayer import FileSystemComponent, PythonComponent, ShellComponent


class SandboxBooter:
    @property
    def fs(self) -> FileSystemComponent: ...

    @property
    def python(self) -> PythonComponent: ...

    @property
    def shell(self) -> ShellComponent: ...

    async def boot(self, session_id: str) -> None: ...

    async def shutdown(self) -> None: ...

    async def upload_file(self, path: str, file_name: str) -> dict:
        """Upload file to sandbox.

        Should return a dict with `success` (bool) and `file_path` (str) keys.
        """
        ...

    async def download_file(self, remote_path: str, local_path: str):
        """Download file from sandbox."""
        ...

    async def available(self) -> bool:
        """Check if the sandbox is available."""
        ...
