"""
从 Python 源文件中提取 logger / print / click.echo / raise XxxError 的消息，
转换为 FTL 格式，并将含变量的调用重写为 t("id", key=val) 形式。
所有提取的条目统一输出到 astrbot/i18n/locales/zh-cn/i18n_messages.ftl。
"""

import ast
import hashlib
import re
from pathlib import Path

# ---------------------------------------------------------------------------
# ID 生成：取消息内容的 MD5 前8位，相同内容永远生成同一个 id（幂等）
# ---------------------------------------------------------------------------


def make_id(ftl_value: str) -> str:
    digest = hashlib.md5(ftl_value.encode()).hexdigest()[:8]
    return f"msg-{digest}"


# ---------------------------------------------------------------------------
# 字符串表达式解析：提取 FTL 值 + 变量参数列表
# 返回 (ftl_value, kwargs) 或 None
#   ftl_value : FTL 格式字符串，如 "{$date}相反的你和我"
#   kwargs    : [(参数名, 源码表达式)] 列表，如 [("date", "date")]
# 纯字符串常量返回 ("原始字符串", [])，kwargs 为空表示无需替换
# ---------------------------------------------------------------------------


def flatten_str_concat(node):
    """递归展开字符串拼接 "a" + "b" + ... → 合并后的字符串常量节点（仅当所有部分都是常量时）"""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left = flatten_str_concat(node.left)
        right = flatten_str_concat(node.right)
        if left is not None and right is not None:
            return left + right
    return None


def extract_string_expr(node):
    # 纯字符串常量
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value, []

    # 多行字符串拼接："aaa" "bbb" 或 "aaa" + "bbb"（全部为常量时合并处理）
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        merged = flatten_str_concat(node)
        if merged is not None:
            return merged, []

    # f-string
    if isinstance(node, ast.JoinedStr):
        return parse_fstring(node)

    # "..." % var 或 "..." % (var1, var2)
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Mod):
        return parse_percent_format(node)

    # "...".format(...)
    if (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "format"
        and isinstance(node.func.value, ast.Constant)
        and isinstance(node.func.value.value, str)
    ):
        return parse_str_format(node)

    # 裸变量：logger.info(var) → "{$var}"
    if isinstance(node, ast.Name):
        return "{$" + node.id + "}", [(node.id, node.id)]

    # 裸函数调用：logger.info(get_msg()) → "{$res}"
    if isinstance(node, ast.Call):
        return "{$res}", [("res", ast.unparse(node))]

    return None


def parse_fstring(node: ast.JoinedStr):
    res_counter = [0]
    parts = []
    kwargs = []

    for value in node.values:
        if isinstance(value, ast.Constant):
            parts.append(str(value.value))
        elif isinstance(value, ast.FormattedValue):
            param, src = get_param_and_src(value.value, res_counter)
            parts.append("{$" + param + "}")
            kwargs.append((param, src))

    return "".join(parts), kwargs


def parse_percent_format(node: ast.BinOp):
    if not (isinstance(node.left, ast.Constant) and isinstance(node.left.value, str)):
        return None

    template = node.left.value
    right = node.right
    arg_nodes = list(right.elts) if isinstance(right, ast.Tuple) else [right]

    res_counter = [0]
    kwargs = []

    def replacer(m):
        fmt_letter = m.group(0)[-1]
        if fmt_letter == "%":
            return "%"
        if arg_nodes:
            param, src = get_param_and_src(arg_nodes.pop(0), res_counter, fmt_letter)
            kwargs.append((param, src))
            return "{$" + param + "}"
        return m.group(0)

    ftl_value = re.sub(r"%(?:\(\w+\))?[-+0-9*.]*[sdfrx%]", replacer, template)
    return ftl_value, kwargs


def parse_str_format(node: ast.Call):
    template = node.func.value.value
    res_counter = [0]

    # 命名占位符映射：占位符名 → (参数名, 源码表达式)
    kw_map = {}
    for kw in node.keywords:
        if kw.arg:
            kw_map[kw.arg] = (kw.arg, ast.unparse(kw.value))

    # 位置参数列表
    pos_args = [get_param_and_src(a, res_counter, "val") for a in node.args]

    kwargs = []

    def replacer(m):
        field = m.group(1).split(":")[0].strip()
        if field == "" or field.isdigit():
            idx = int(field) if field.isdigit() else 0
            param, src = pos_args[idx] if idx < len(pos_args) else ("arg", "arg")
        else:
            param, src = kw_map.get(field, (field, field))
        kwargs.append((param, src))
        return "{$" + param + "}"

    ftl_value = re.sub(r"\{([^{}]*)\}", replacer, template)
    return ftl_value, kwargs


def get_param_and_src(node, res_counter: list, fmt_letter: str = "val"):
    """返回 (参数名, 源码表达式字符串)"""
    if isinstance(node, ast.Name):
        return node.id, node.id
    if isinstance(node, ast.Constant):
        return fmt_letter, repr(node.value)
    # 复杂表达式 / 函数调用
    res_counter[0] += 1
    count = res_counter[0]
    param = "res_" + str(count) if count > 1 else "res"
    return param, ast.unparse(node)


# ---------------------------------------------------------------------------
# 目标调用判断
# ---------------------------------------------------------------------------


def is_logger_call(node: ast.Call) -> bool:
    """判断是否为 logger.info / warning / warn / error / debug / critical / exception"""
    func = node.func
    return (
        isinstance(func, ast.Attribute)
        and func.attr
        in ("info", "warning", "warn", "error", "debug", "critical", "exception")
        and isinstance(func.value, ast.Name)
    )


def is_print_call(node: ast.Call) -> bool:
    """判断是否为 print(...)"""
    return isinstance(node.func, ast.Name) and node.func.id == "print"


def is_click_echo_call(node: ast.Call) -> bool:
    """判断是否为 click.echo(...)"""
    func = node.func
    return (
        isinstance(func, ast.Attribute)
        and func.attr == "echo"
        and isinstance(func.value, ast.Name)
        and func.value.id == "click"
    )


def is_exception_call(node: ast.Call) -> bool:
    """判断是否为 XxxError(...) 或 XxxException(...) 的实例化"""
    func = node.func
    # 支持 ValueError(...) 和 module.ValueError(...) 两种形式
    name = (
        func.id
        if isinstance(func, ast.Name)
        else (func.attr if isinstance(func, ast.Attribute) else "")
    )
    return name.endswith("Error") or name.endswith("Exception")


def is_message_call(node: ast.Call) -> bool:
    """判断是否为任意对象的 .message(...) 或 .error(...) 方法调用"""
    func = node.func
    if not isinstance(func, ast.Attribute):
        return False
    if func.attr not in ("message", "error"):
        return False
    # 第一个参数是函数调用结果（如 str(exc)、get_msg()）时不匹配
    if node.args and isinstance(node.args[0], ast.Call):
        return False
    return True


def is_target_call(node: ast.Call) -> bool:
    return (
        is_logger_call(node)
        or is_print_call(node)
        or is_click_echo_call(node)
        or is_exception_call(node)
        or is_message_call(node)
    )


# ---------------------------------------------------------------------------
# 核心：提取 + 重写
# ---------------------------------------------------------------------------


def extract_and_rewrite(source: str):
    """
    解析源码，找出所有含变量的目标调用，返回：
      ftl_entries : [(id, ftl_value), ...]
      new_source  : 将含变量的第一个参数替换为 t("id", key=val) 后的源码
    纯字符串（无变量）的调用保持原样不动。
    """
    try:
        tree = ast.parse(source)
    except Exception as e:
        print(f"Error parsing source: {e}")
        return [], source

    # 收集替换信息：(起始偏移, 结束偏移, 新文本, msg_id, ftl_value)
    replacements = []

    # 预计算每行的字符偏移量
    line_offsets = []
    offset = 0
    for line in source.splitlines(keepends=True):
        line_offsets.append(offset)
        offset += len(line)

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if not is_target_call(node):
            continue
        if not node.args:
            continue

        # 第一个参数已经是 t(...) 调用，说明已处理过，跳过
        first = node.args[0]
        if (
            isinstance(first, ast.Call)
            and isinstance(first.func, ast.Name)
            and first.func.id == "t"
        ):
            continue

        result = extract_string_expr(node.args[0])
        if result is None:
            continue

        ftl_value, kwargs = result
        # 保留原样的 \n 而不是直接换行
        ftl_value = ftl_value.replace("\r", "\\r").replace("\n", "\\n")

        msg_id = make_id(ftl_value)

        # 构造新的第一个参数：t("id", key=val, ...)
        kw_parts = ", ".join(f"{p}={s}" for p, s in kwargs)
        t_call = f't("{msg_id}", {kw_parts})' if kw_parts else f't("{msg_id}")'

        # 用 get_source_segment 精确获取原始参数文本（正确处理中文字符偏移）
        arg_node = node.args[0]
        original_arg = ast.get_source_segment(source, arg_node)
        if original_arg is None:
            continue

        # 在源码中定位原始参数的精确位置
        approx = line_offsets[arg_node.lineno - 1] + arg_node.col_offset
        window_start = max(0, approx - 4)
        pos = source.find(original_arg, window_start)
        if pos == -1:
            continue

        replacements.append((pos, pos + len(original_arg), t_call, msg_id, ftl_value))

    # 从后往前替换，保证偏移量不受影响
    replacements.sort(key=lambda x: x[0], reverse=True)

    new_source = source
    ftl_entries_map = {}
    for start, end, new_text, msg_id, ftl_value in replacements:
        new_source = new_source[:start] + new_text + new_source[end:]
        ftl_entries_map[msg_id] = ftl_value

    # 按出现顺序返回 FTL 条目（去重）
    ordered_ftl = []
    seen = set()
    for _, _, _, msg_id, ftl_value in sorted(replacements, key=lambda x: x[0]):
        if msg_id not in seen:
            ordered_ftl.append((msg_id, ftl_value))
            seen.add(msg_id)

    return ordered_ftl, new_source


# ---------------------------------------------------------------------------
# 命令行入口：遍历整个项目目录，批量提取并重写
# ---------------------------------------------------------------------------


def main():
    import argparse
    import os

    try:
        from tqdm import tqdm
    except ImportError:

        def tqdm(iterable, **kwargs):
            return iterable

    parser = argparse.ArgumentParser(description="提取 i18n 消息并重写日志/异常调用")
    parser.add_argument("--rewrite", action="store_true", help="原地重写源文件")
    args = parser.parse_args()

    # 使用 get_astrbot_path 获取项目根目录
    root_dir = Path(".")
    ftl_base_dir = Path(f"{root_dir}/astrbot/i18n/locales/zh-cn")
    ftl_base_dir.mkdir(parents=True, exist_ok=True)

    ftl_file = ftl_base_dir / "i18n_messages.ftl"

    # 所有生成的 FTL 条目，按文件分组：rel_path -> [(msg_id, ftl_value)]
    all_files_data = {}

    # 遍历时跳过的目录
    exclude_dirs = {
        ".git",
        "__pycache__",
        ".venv",
        "venv",
        "tests",
        ".pytest_cache",
        ".ruff_cache",
        ".idea",
        ".vscode",
        "data",
    }

    all_files = []
    for root, dirs, files in os.walk(root_dir):
        dirs[:] = [d for d in dirs if d not in exclude_dirs]
        for file in files:
            if not file.endswith(".py"):
                continue
            # 跳过本脚本自身及引导文件
            if file in ("automatic_i18n.py", "runtime_bootstrap.py"):
                continue
            all_files.append(Path(root) / file)

    pbar = tqdm(all_files, desc="Processing files")
    for file_path in pbar:
        try:
            source = file_path.read_text(encoding="utf-8")
            ftl_entries, new_source = extract_and_rewrite(source)

            if not ftl_entries:
                continue

            if args.rewrite:
                import_stmt = "from astrbot.core.lang import t"
                if import_stmt not in new_source:
                    # 插入到模块 docstring 之后，否则插到文件开头
                    if new_source.startswith('"""') or new_source.startswith("'''"):
                        quote = new_source[:3]
                        end_doc = new_source.find(quote, 3)
                        if end_doc != -1:
                            insert_pos = end_doc + 3
                            new_source = (
                                new_source[:insert_pos]
                                + "\n"
                                + import_stmt
                                + new_source[insert_pos:]
                            )
                        else:
                            new_source = import_stmt + "\n" + new_source
                    else:
                        new_source = import_stmt + "\n" + new_source
                file_path.write_text(new_source, encoding="utf-8")
                tqdm.write(f"  [已重写] {file_path}")

            rel_path = str(file_path.relative_to(root_dir))
            all_files_data[rel_path] = ftl_entries

        except Exception as e:
            tqdm.write(f"  [错误] 处理 {file_path} 失败：{e}")

    # 将 FTL 条目追加写入统一的文件（跳过已存在的 msg_id）
    if all_files_data:
        existing_content = (
            ftl_file.read_text(encoding="utf-8") if ftl_file.exists() else ""
        )

        new_ftl_lines = []
        for rel_path, entries in all_files_data.items():
            header = f"### {rel_path}"
            section_lines = []
            for msg_id, ftl_value in entries:
                if f"{msg_id} =" not in existing_content:
                    section_lines.append(f"{msg_id} = {ftl_value}")

            # 只有有新条目时才写入 header
            if section_lines:
                new_ftl_lines.append(f"\n{header}")
                new_ftl_lines.extend(section_lines)

        if new_ftl_lines:
            with open(ftl_file, "a", encoding="utf-8") as f:
                f.write("\n".join(new_ftl_lines) + "\n")
            print(f"[FTL] 已更新 {ftl_file}，新增 {len(new_ftl_lines)} 行")


if __name__ == "__main__":
    main()
