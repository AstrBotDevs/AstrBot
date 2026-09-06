from typing import TextIO

class YAMLError(Exception): ...

def safe_load(stream: str | TextIO) -> object: ...
def dump(
    data: object,
    stream: TextIO | None = ...,
    *args: object,
    **kwargs: object,
) -> str | None: ...
