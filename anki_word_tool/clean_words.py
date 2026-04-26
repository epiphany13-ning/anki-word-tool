from __future__ import annotations

import argparse
from pathlib import Path

from anki_word_tool.cli import clean_word, read_words, write_words


BLOCKLIST = {
    "大的图像",
    "文字文本",
    "作为条目",
    "词条标题",
    "输出结果",
    "中的选项",
    "只要条目",
    "包括解释",
    "事物变化",
    "由简到繁",
    "更高更强",
    "自然科学",
    "社会科学",
    "日常生活",
    "表演艺术",
    "很多词条",
    "你要的是",
    "四字短语",
    "如果愿意",
}


def merge_and_clean(inputs: list[Path]) -> list[str]:
    words: list[str] = []
    seen: set[str] = set()
    for path in inputs:
        for raw_word in read_words(path):
            word = clean_word(raw_word)
            if len(word) != 4 or word in BLOCKLIST or word in seen:
                continue
            seen.add(word)
            words.append(word)
    return words


def main() -> int:
    parser = argparse.ArgumentParser(description="Merge and clean extracted word lists.")
    parser.add_argument("--input", action="append", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    words = merge_and_clean([Path(path) for path in args.input])
    write_words(words, Path(args.output))
    print(f"Wrote {len(words)} words to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
