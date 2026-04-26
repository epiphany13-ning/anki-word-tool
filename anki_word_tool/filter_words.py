from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from anki_word_tool.cli import clean_word, get_client, parse_json_words, response_text, write_words


def chunks(items: list[str], size: int) -> list[list[str]]:
    return [items[index : index + size] for index in range(0, len(items), size)]


def load_words(path: Path) -> list[str]:
    words: list[str] = []
    seen: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        word = clean_word(line)
        if len(word) != 4 or word in seen:
            continue
        seen.add(word)
        words.append(word)
    return words


def filter_batch(client, model: str, words: list[str]) -> list[str]:
    prompt = (
        "你是公考成语词表清洗助手。给你一组四字中文字符串，请只保留适合做公考成语/四字词语记忆卡片的条目。"
        "保留：成语、熟语、典型固定四字词语、明显可作为公考言语理解词汇考点的四字表达。"
        "删除：普通说明短语、学科领域名词、政策/概念搭配、元说明文字、解释性片段、临时搭配、不是词条标题的短语。"
        "遇到可疑项时宁可删除，不要为了凑数量保留。"
        "例如应删除：物质载体、传播方式、具体场景、抽象层面、底层逻辑、组织形式、政策实施、科技创新、生活舒适、精神层面。"
        "例如可保留：源远流长、薪火相传、具体而微、自然而然、顺其自然、犹豫不决、接连不断、意气相投。"
        "只输出 JSON 数组，数组元素必须来自输入原词，不要改写，不要解释，不要 Markdown。"
    )
    response = client.responses.create(
        model=model,
        input=[
            {"role": "system", "content": prompt},
            {"role": "user", "content": json.dumps(words, ensure_ascii=False)},
        ],
    )
    kept = parse_json_words(response_text(response))
    allowed = set(words)
    return [word for word in kept if word in allowed]


def main() -> int:
    parser = argparse.ArgumentParser(description="Filter extracted words with an OpenAI-compatible model.")
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--model", default="gpt-5.5")
    parser.add_argument("--batch-size", type=int, default=120)
    parser.add_argument("--delay", type=float, default=0.0)
    args = parser.parse_args()

    source_words = load_words(Path(args.input))
    output_path = Path(args.output)
    existing = load_words(output_path) if output_path.exists() else []
    kept: list[str] = list(existing)
    seen: set[str] = set(existing)
    processed = len(existing)
    client = get_client()

    for batch in chunks(source_words[processed:], args.batch_size):
        filtered = filter_batch(client, args.model, batch)
        for word in filtered:
            if word not in seen:
                seen.add(word)
                kept.append(word)
        processed += len(batch)
        write_words(kept, output_path)
        print(f"Processed {processed}/{len(source_words)} input words; kept {len(kept)}.", flush=True)
        if args.delay:
            time.sleep(args.delay)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
