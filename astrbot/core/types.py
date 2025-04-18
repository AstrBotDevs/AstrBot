from typing import TypeAlias

ConfigValue: TypeAlias = str | int | float | bool | list[str | int | float | bool] | dict[str, "ConfigValue"] | None
JsonValue: TypeAlias = str | int | float | bool | list["JsonValue"] | dict[str, "JsonValue"] | None
