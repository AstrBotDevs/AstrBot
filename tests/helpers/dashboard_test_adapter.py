from collections.abc import Iterable
from typing import Any

import httpx
from fastapi import FastAPI


class DashboardTestHeaders:
    def __init__(self, headers) -> None:
        self._headers = headers

    def getlist(self, key: str) -> list[str]:
        values = self._headers.get_list(key)
        if key.lower() == "set-cookie":
            return [value.replace('=""', "=") for value in values]
        return values

    def get(self, key: str, default: Any = None):
        value = self._headers.get(key, default)
        if isinstance(value, str) and key.lower() == "set-cookie":
            return value.replace('=""', "=")
        return value

    def __getitem__(self, key: str):
        return self._headers[key]

    def __contains__(self, key: str) -> bool:
        return key in self._headers


class DashboardTestResponse:
    def __init__(self, response) -> None:
        self._response = response
        self.status_code = response.status_code
        self.headers = DashboardTestHeaders(response.headers)
        self.data = response.content
        self.content = response.content
        self.text = response.text

    async def get_json(self):
        return self._response.json()

    async def get_data(self):
        return self._response.content


class DashboardTestClient:
    def __init__(self, app: FastAPI) -> None:
        app.state.dashboard_testing = True
        self._client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        )

    @staticmethod
    def _is_file_storage(value: Any) -> bool:
        return hasattr(value, "stream") and hasattr(value, "filename")

    @classmethod
    def _file_tuple(cls, value: Any):
        stream = value.stream
        if hasattr(stream, "seek"):
            stream.seek(0)
        content = stream.read()
        filename = getattr(value, "filename", "upload.bin")
        content_type = getattr(value, "content_type", None)
        return filename, content, content_type

    @classmethod
    def _normalize_data(cls, data: Any):
        if not isinstance(data, dict):
            return data, None

        form: dict[str, Any] = {}
        files: list[tuple[str, tuple]] = []
        for key, value in data.items():
            if cls._is_file_storage(value):
                files.append((key, cls._file_tuple(value)))
                continue
            if isinstance(value, Iterable) and not isinstance(
                value, str | bytes | dict
            ):
                values = list(value)
                if values and all(cls._is_file_storage(item) for item in values):
                    files.extend((key, cls._file_tuple(item)) for item in values)
                    continue
            form[key] = value
        return form, files or None

    @classmethod
    def _normalize_files(cls, files: Any):
        if isinstance(files, dict):
            items = files.items()
        elif isinstance(files, Iterable) and not isinstance(files, str | bytes):
            items = files
        else:
            return files

        normalized_files: list[tuple[str, Any]] = []
        for key, value in items:
            if cls._is_file_storage(value):
                normalized_files.append((key, cls._file_tuple(value)))
                continue
            if isinstance(value, Iterable) and not isinstance(
                value, str | bytes | dict
            ):
                values = list(value)
                if values and all(cls._is_file_storage(item) for item in values):
                    normalized_files.extend(
                        (key, cls._file_tuple(item)) for item in values
                    )
                    continue
            normalized_files.append((key, value))
        return normalized_files

    async def request(self, method: str, url: str, **kwargs):
        data = kwargs.pop("data", None)
        if data is not None and "files" not in kwargs:
            normalized_data, files = self._normalize_data(data)
            kwargs["data"] = normalized_data
            if files:
                kwargs["files"] = files
        elif data is not None:
            kwargs["data"] = data
        if "files" in kwargs:
            kwargs["files"] = self._normalize_files(kwargs["files"])
        response = await self._client.request(method, url, **kwargs)
        return DashboardTestResponse(response)

    async def get(self, url: str, **kwargs):
        return await self.request("GET", url, **kwargs)

    async def post(self, url: str, **kwargs):
        return await self.request("POST", url, **kwargs)

    async def put(self, url: str, **kwargs):
        return await self.request("PUT", url, **kwargs)

    async def patch(self, url: str, **kwargs):
        return await self.request("PATCH", url, **kwargs)

    async def delete(self, url: str, **kwargs):
        return await self.request("DELETE", url, **kwargs)

    async def aclose(self) -> None:
        await self._client.aclose()
