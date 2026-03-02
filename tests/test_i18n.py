import ast
import os
from pathlib import Path

import pytest
from fluent.syntax import FluentParser
from fluent.syntax import ast as fluent_ast


def get_files(path):
    for root, dirs, files in os.walk(path):
        for file in files:
            if file.endswith(".ftl"):
                yield Path(root) / file

def extract_params_from_node(node, params):
    """递归地从 AST 节点中提取参数。"""
    if node is None:
        return

    if isinstance(node, fluent_ast.VariableReference):
        params.add(node.id.name)
    
    elif isinstance(node, fluent_ast.SelectExpression):
        if node.selector:
            extract_params_from_node(node.selector, params)
        for variant in node.variants:
            extract_params_from_node(variant.value, params)
            
    elif isinstance(node, fluent_ast.Placeable):
        extract_params_from_node(node.expression, params)
        
    elif isinstance(node, fluent_ast.Pattern):
        for element in node.elements:
            extract_params_from_node(element, params)
            
    elif isinstance(node, fluent_ast.FunctionReference):
        # 如果函数参数是变量，则处理它们
        if node.arguments:
            if node.arguments.positional:
                for arg in node.arguments.positional:
                    extract_params_from_node(arg, params)
            if node.arguments.named:
                for arg in node.arguments.named:
                    extract_params_from_node(arg.value, params)

def scan_locales(locale_dir):
    parser = FluentParser()
    results = {} # {locale: {filename: {id: [params]}}}

    if not locale_dir.exists():
        return results

    for file_path in get_files(locale_dir):
        # file_path 类似于 .../locales/zh-cn/main.ftl
        try:
            rel_path = file_path.relative_to(locale_dir)
        except ValueError:
            continue
            
        parts = rel_path.parts
        if len(parts) < 2:
            continue
            
        locale = parts[0]
        filename = parts[1]
        
        if locale not in results:
            results[locale] = {}
        if filename not in results[locale]:
            results[locale][filename] = {}

        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
            resource = parser.parse(content)
            
            for entry in resource.body:
                if isinstance(entry, fluent_ast.Message):
                    msg_id = entry.id.name
                    params = set()
                    if entry.value:
                        extract_params_from_node(entry.value, params)
                    results[locale][filename][msg_id] = sorted(list(params))
                elif isinstance(entry, fluent_ast.Junk):
                    # 处理带下划线等非法字符的消息定义
                    import re
                    content_str = entry.content
                    # 匹配 id = ...
                    id_match = re.match(r"^([a-zA-Z0-9_-]+)\s*=", content_str)
                    if id_match:
                        msg_id = id_match.group(1)
                        # 匹配所有的 {$param_name}，支持带下划线的变量
                        params = set(re.findall(r"\{\s*\$([a-zA-Z0-9_-]+)\s*\}", content_str))
                        results[locale][filename][msg_id] = sorted(list(params))
                    
    return results

def find_t_usages(file_path):
    """
    解析 Python 文件，查找 t('msg-id', param=val) 的调用。
    返回列表: [(line, msg_id, set(param_names)), ...]
    """
    usages = []
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            tree = ast.parse(f.read(), filename=str(file_path))
    except Exception:
        # 如果解析失败（例如语法错误），跳过
        return usages

    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            # 检查函数名是否为 't'
            is_t = False
            if isinstance(node.func, ast.Name) and node.func.id == "t":
                is_t = True
            
            if is_t:
                # 检查第一个参数是否为字符串常量
                if node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
                    msg_id = node.args[0].value
                    
                    # 提取关键字参数名
                    params = set()
                    for keyword in node.keywords:
                        params.add(keyword.arg)
                    
                    usages.append((node.lineno, msg_id, params))
    return usages

def test_i18n_consistency():
    """
    扫描所有语言环境文件并确保跨语言的一致性。
    检查项：
    1. 所有语言环境应具有相同的文件集合。
    2. 所有文件应具有相同的消息 ID 集合。
    3. 所有消息应具有相同的参数。
    """
    base_dir = Path(__file__).parent.parent / "astrbot" / "i18n" / "locales"
    data = scan_locales(base_dir)
    
    assert data, "未找到语言环境数据"
    
    locales = sorted(data.keys())
    reference_locale = "zh-cn" # 使用 zh-cn 作为基准
    
    if reference_locale not in locales:
        pytest.fail(f"在 {locales} 中未找到基准语言环境 '{reference_locale}'")
        
    reference_data = data[reference_locale]
    
    errors = []
    
    for locale in locales:
        if locale == reference_locale:
            continue
            
        current_data = data[locale]
        
        # 1. 检查缺失或多余的文件
        ref_files = set(reference_data.keys())
        curr_files = set(current_data.keys())
        
        missing_files = ref_files - curr_files
        extra_files = curr_files - ref_files
        
        if missing_files:
            errors.append(f"[{locale}] 缺失文件: {missing_files}")
        if extra_files:
            errors.append(f"[{locale}] 多余文件: {extra_files}")
            
        # 比较共同的文件
        common_files = ref_files & curr_files
        for filename in common_files:
            ref_msgs = reference_data[filename]
            curr_msgs = current_data[filename]

            # 如果当前语言的文件是空的（即没有任何翻译条目），则跳过比对
            if not curr_msgs:
                continue

            ref_ids = set(ref_msgs.keys())
            curr_ids = set(curr_msgs.keys())
            
            # 2. 检查缺失或多余的消息 ID
            missing_ids = ref_ids - curr_ids
            extra_ids = curr_ids - ref_ids
            
            if missing_ids:
                errors.append(f"[{locale}][{filename}] 缺失 ID: {missing_ids}")
            if extra_ids:
                errors.append(f"[{locale}][{filename}] 多余 ID: {extra_ids}")
                
            # 3. 检查参数不匹配
            common_ids = ref_ids & curr_ids
            for msg_id in common_ids:
                ref_params = ref_msgs[msg_id]
                curr_params = curr_msgs[msg_id]
                
                if ref_params != curr_params:
                    errors.append(
                        f"[{locale}][{filename}][{msg_id}] 参数不匹配: "
                        f"预期 {ref_params}, 实际 {curr_params}"
                    )

    if errors:
        pytest.fail("\n".join(errors))

def test_code_i18n_usage():
    """
    扫描代码中的 t('id', ...) 调用，确保：
    1. ID 存在于 locales/zh-cn 中。
    2. 传入的参数与 locales 中定义的一致。
    """
    project_root = Path(__file__).parent.parent
    locale_dir = project_root / "astrbot" / "i18n" / "locales"
    
    # 1. 加载 zh-cn 数据作为基准
    data = scan_locales(locale_dir)
    if "zh-cn" not in data:
        pytest.fail("未找到 zh-cn 语言包数据")
        
    # 构建 ID -> 参数集合 的映射 (扁平化)
    valid_msgs = {}
    for filename, msgs in data["zh-cn"].items():
        for msg_id, params in msgs.items():
            valid_msgs[msg_id] = set(params)

    # 2. 扫描所有 Python 文件
    errors = []
    for root, dirs, files in os.walk(project_root):
        # 忽略 .git, .venv, tests, build, dist 等目录
        if any(ignore in root for ignore in ["/.git", "/.venv", "/__pycache__", "/tests", "/build", "/dist", "/.idea", "/.vscode"]):
            continue
            
        for file in files:
            if file.endswith(".py"):
                file_path = Path(root) / file
                
                # 查找 t() 调用
                usages = find_t_usages(file_path)
                
                for line, msg_id, params in usages:
                    # 检查 ID 是否存在
                    if msg_id not in valid_msgs:
                        errors.append(f"{file_path}:{line} 未知的消息 ID '{msg_id}'")
                        continue
                        
                    # 检查参数是否匹配
                    expected_params = valid_msgs[msg_id]
                    if params != expected_params:
                        # 允许的情况：代码中没传参，但 FTL 也不需要参数 (expected为空，params为空 -> 匹配)
                        # 错误的情况：
                        # 1. 缺参数 (expected - params 不为空)
                        # 2. 多参数 (params - expected 不为空)
                        missing = expected_params - params
                        extra = params - expected_params
                        
                        error_parts = []
                        if missing:
                            error_parts.append(f"缺少参数: {missing}")
                        if extra:
                            error_parts.append(f"多余参数: {extra}")
                            
                        if error_parts:
                            errors.append(
                                f"{file_path}:{line} 消息 '{msg_id}' 参数不匹配. "
                                f"{'; '.join(error_parts)}. "
                                f"(预期: {expected_params}, 实际: {params})"
                            )

    if errors:
        pytest.fail("\n" + "\n".join(errors))
