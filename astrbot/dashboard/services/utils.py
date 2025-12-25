import traceback
from typing import Any

from astrbot.core import logger
from astrbot.core.config.astrbot_config import AstrBotConfig
from astrbot.core.config.default import CONFIG_METADATA_2, DEFAULT_VALUE_MAP


def try_cast(value: Any, type_: str):
    if type_ == "int":
        try:
            return int(value)
        except (ValueError, TypeError):
            return None
    elif (
        type_ == "float"
        and isinstance(value, str)
        and value.replace(".", "", 1).isdigit()
    ) or (type_ == "float" and isinstance(value, int)):
        return float(value)
    elif type_ == "float":
        try:
            return float(value)
        except (ValueError, TypeError):
            return None


def validate_config(data, schema: dict, is_core: bool) -> tuple[list[str], dict]:
    errors = []

    def validate(data: dict, metadata: dict = schema, path=""):
        for key, value in data.items():
            if key not in metadata:
                continue
            meta = metadata[key]
            if "type" not in meta:
                logger.debug(f"配置项 {path}{key} 没有类型定义, 跳过校验")
                continue
            # null 转换
            if value is None:
                data[key] = DEFAULT_VALUE_MAP[meta["type"]]
                continue
            if meta["type"] == "list" and not isinstance(value, list):
                errors.append(
                    f"错误的类型 {path}{key}: 期望是 list, 得到了 {type(value).__name__}",
                )
            elif (
                meta["type"] == "list"
                and isinstance(value, list)
                and value
                and "items" in meta
                and isinstance(value[0], dict)
            ):
                # 当前仅针对 list[dict] 的情况进行类型校验，以适配 AstrBot 中 platform、provider 的配置
                for item in value:
                    validate(item, meta["items"], path=f"{path}{key}.")
            elif meta["type"] == "object" and isinstance(value, dict):
                validate(value, meta["items"], path=f"{path}{key}.")

            if meta["type"] == "int" and not isinstance(value, int):
                casted = try_cast(value, "int")
                if casted is None:
                    errors.append(
                        f"错误的类型 {path}{key}: 期望是 int, 得到了 {type(value).__name__}",
                    )
                data[key] = casted
            elif meta["type"] == "float" and not isinstance(value, float):
                casted = try_cast(value, "float")
                if casted is None:
                    errors.append(
                        f"错误的类型 {path}{key}: 期望是 float, 得到了 {type(value).__name__}",
                    )
                data[key] = casted
            elif meta["type"] == "bool" and not isinstance(value, bool):
                errors.append(
                    f"错误的类型 {path}{key}: 期望是 bool, 得到了 {type(value).__name__}",
                )
            elif meta["type"] in ["string", "text"] and not isinstance(value, str):
                errors.append(
                    f"错误的类型 {path}{key}: 期望是 string, 得到了 {type(value).__name__}",
                )
            elif meta["type"] == "list" and not isinstance(value, list):
                errors.append(
                    f"错误的类型 {path}{key}: 期望是 list, 得到了 {type(value).__name__}",
                )
            elif meta["type"] == "object" and not isinstance(value, dict):
                errors.append(
                    f"错误的类型 {path}{key}: 期望是 dict, 得到了 {type(value).__name__}",
                )

    if is_core:
        meta_all = {
            **schema["platform_group"]["metadata"],
            **schema["provider_group"]["metadata"],
            **schema["misc_config_group"]["metadata"],
        }
        validate(data, meta_all)
    else:
        validate(data, schema)

    return errors, data


def save_config(post_config: dict, config: AstrBotConfig, is_core: bool = False):
    """验证并保存配置"""
    errors = None
    logger.info(f"Saving config, is_core={is_core}")
    try:
        if is_core:
            errors, post_config = validate_config(
                post_config,
                CONFIG_METADATA_2,
                is_core,
            )
        else:
            errors, post_config = validate_config(
                post_config, getattr(config, "schema", {}), is_core
            )
    except BaseException as e:
        logger.error(traceback.format_exc())
        logger.warning(f"验证配置时出现异常: {e}")
        raise ValueError(f"验证配置时出现异常: {e}")
    if errors:
        raise ValueError(f"格式校验未通过: {errors}")

    config.save_config(post_config)
