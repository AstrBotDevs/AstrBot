from typing import ClassVar

class Draft202012Validator:
    META_SCHEMA: ClassVar[dict[str, object]]

def validate(instance: object, schema: object) -> None: ...
