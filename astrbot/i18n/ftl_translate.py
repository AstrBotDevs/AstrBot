import argparse
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from fluent.syntax import ast, parse, serialize
from openai import OpenAI
from tqdm import tqdm


def translate_string(input_string: str, target_lang: str = "English") -> str:
    """使用 DeepSeek API 翻译 i18n 字符串。"""
    api_key = os.environ.get("DEEPSEEK_API_KEY")
    if not api_key:
        raise ValueError("未检测到环境变量 DEEPSEEK_API_KEY，请先设置。")

    client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")

    system_prompt = (
        f"你是一个专业的软件i18n翻译器。请将以下文本翻译为{target_lang}，保持IT语境准确。\n\n"
        "规则：\n\n"
        "1. 必须原样保留所有代码占位符（如 {$var} 等）。\n\n"
        "2. 只输出最终译文，绝对禁止包含任何解释、多余的引号或Markdown格式。"
        "3. 如果原文为中文则直接返回原文"
    )

    try:
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"待翻译文本：{input_string}"},
            ],
            temperature=1.3,
            stream=False,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"\n[Error] API 调用失败: {e}")
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
        print(f"File not found: {ftl_path}")
        return

    content = ftl_path.read_text(encoding="utf-8")
    resource = parse(content)

    # 收集所有需要翻译的 TextElement（跳过空文本）
    messages = [entry for entry in resource.body if isinstance(entry, ast.Message)]
    if not messages:
        print(f"No messages found in {ftl_path}")
        return

    # 收集所有待翻译的 (element, ) 对，保留引用以便原地修改
    elements_to_translate = []
    for msg in messages:
        if msg.value:
            for element in msg.value.elements:
                if isinstance(element, ast.TextElement) and element.value.strip():
                    elements_to_translate.append(element)

    print(
        f"共 {len(elements_to_translate)} 条文本，使用 {max_workers} 个并发线程翻译..."
    )

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
            except Exception as e:
                print(f"\n[Error] 翻译失败，保留原文: {e}")

    # 序列化并写回
    translated_content = serialize(resource)
    ftl_path.write_text(translated_content, encoding="utf-8")
    print(f"\n翻译完成，已保存到 {ftl_path}")


def main():
    parser = argparse.ArgumentParser(
        description="使用 DeepSeek 并发翻译 Fluent (FTL) 文件"
    )
    parser.add_argument(
        "--file",
        default="astrbot/i18n/locales/en-us/i18n_messages.ftl",
        help="待翻译的 FTL 文件路径",
    )
    parser.add_argument("--lang", default="English", help="目标语言（默认: English）")
    parser.add_argument(
        "--workers", type=int, default=10, help="并发线程数（默认: 10）"
    )
    args = parser.parse_args()

    if "DEEPSEEK_API_KEY" not in os.environ:
        print("错误: 请先设置 DEEPSEEK_API_KEY 环境变量。")
        print("例如: export DEEPSEEK_API_KEY='sk-xxxxxx'")
        return

    process_ftl(Path(args.file), args.lang, args.workers)


if __name__ == "__main__":
    main()
