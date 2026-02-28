from concurrent.futures import ThreadPoolExecutor, as_completed
from fluent.syntax import ast, parse, serialize
from openai import OpenAI
from pathlib import Path
from tqdm import tqdm
import argparse
import os
from loguru import logger


def translate_string(input_string: str, target_lang: str = "English") -> str:
    """使用 DeepSeek API 翻译 i18n 字符串。"""
    api_key = os.environ.get("DEEPSEEK_API_KEY")

    client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")

    system_prompt = (
        "你是一个专业的软件国际化（i18n）翻译引擎。"

        "任务：将用户提供的文本翻译为指定目标语言，保持 IT/软件语境的准确性。"

        "【核心规则 - 按优先级严格执行】"

        "1. 【占位符保护 - 最高优先级】"
        "- 必须原样保留所有代码占位符，包括但不限于：{$var}, {{variable}}, %s, %d, {0}, {{count}}, #{name} 等"
        "- 禁止翻译、修改、增删占位符的任何字符（包括括号、符号、变量名）"
        "- 占位符在译文中的位置应符合目标语言的语法习惯"

        "2. 【输出格式 - 严格限制】"
        "- 只输出翻译后的纯文本"
        "- 禁止输出：解释、说明、引号、Markdown格式、代码块标记、序号、前缀（如\"翻译：\"）"

        "3. 【翻译质量】"
        "- 使用软件/IT行业的标准术语"
        "- 保持原文的语气和风格（正式/友好/简洁等）"
    )

    try:
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": system_prompt + f"- 目标语言：{target_lang}"},
                {"role": "user", "content": f"{input_string}"},
            ],
            temperature=0.1,
            stream=False,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        logger.error(e)
        return input_string


def translate_element(element: ast.TextElement, target_lang: str) -> str:
    """翻译单个 TextElement，返回翻译结果（供线程池调用）。"""
    original_text = element.value.strip()
    if not original_text:
        return element.value
    return translate_string(original_text, target_lang)


def process_ftl(ftl_path: Path, target_lang: str = "English", max_workers: int = 10):
    """读取、并发翻译并写回 FTL 文件。"""
    if not ftl_path.exists():
        return

    content = ftl_path.read_text(encoding="utf-8")
    resource = parse(content)

    # 收集所有需要翻译的 TextElement（跳过空文本）
    messages = [entry for entry in resource.body if isinstance(entry, ast.Message)]
    if not messages:
        return

    # 收集所有待翻译的 (element, ) 对，保留引用以便原地修改
    elements_to_translate = []
    for msg in messages:
        if msg.value:
            for element in msg.value.elements:
                if isinstance(element, ast.TextElement) and element.value.strip():
                    elements_to_translate.append(element)

    # 并发翻译：future -> element 映射，翻译完成后原地写回
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_element = {
            executor.submit(translate_element, el, target_lang): el
            for el in elements_to_translate
        }

        pbar = tqdm(
            as_completed(future_to_element),
            total=len(future_to_element),
            desc="翻译中",
            unit="条",
        )
        for future in pbar:
            element = future_to_element[future]
            try:
                element.value = future.result()
            except Exception:
                ...

    # 序列化并写回
    translated_content = serialize(resource)
    ftl_path.write_text(translated_content, encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(
        description="使用 DeepSeek 并发翻译 Fluent (FTL) 文件"
    )
    parser.add_argument(
        "--file",
        default="astrbot/i18n/locales/zh-cn/i18n_messages.ftl",
        help="待翻译的 FTL 文件路径",
    )
    parser.add_argument("--lang", default="简体中文", help="目标语言（默认: Chinese）")
    parser.add_argument(
        "--workers", type=int, default=32, help="并发线程数（默认: 10）"
    )
    args = parser.parse_args()

    process_ftl(Path(args.file), args.lang, args.workers)


if __name__ == "__main__":
    print(f"{translate_string('测试', 'English')}")
    main()
