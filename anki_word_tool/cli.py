from __future__ import annotations

import argparse
import base64
import csv
import json
import os
import re
import sys
import tempfile
import time
from pathlib import Path
from typing import Iterable, Sequence

try:
    from openai import OpenAI
except ImportError:  # pragma: no cover - handled at runtime
    OpenAI = None


CHINESE_RUN = re.compile(r"[\u4e00-\u9fff]{2,8}")
DEFAULT_PROMPT = Path(__file__).with_name("config") / "idiom_prompt.txt"


def read_text(path: Path) -> str:
    if path.suffix.lower() == ".pdf":
        return read_pdf_text(path)
    return path.read_text(encoding="utf-8")


def read_pdf_text(path: Path) -> str:
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise RuntimeError("Reading PDF text requires pypdf. Install requirements.txt first.") from exc

    reader = PdfReader(str(path))
    pages = []
    for page in reader.pages:
        pages.append(page.extract_text() or "")
    return "\n".join(pages)


def clean_word(value: str) -> str:
    return re.sub(r"[^\u4e00-\u9fff]", "", value).strip()


def extract_candidates(text: str, min_len: int = 4, max_len: int = 4) -> list[str]:
    seen: set[str] = set()
    words: list[str] = []
    for match in CHINESE_RUN.finditer(text):
        token = clean_word(match.group(0))
        if not (min_len <= len(token) <= max_len):
            continue
        if token in seen:
            continue
        seen.add(token)
        words.append(token)
    return words


def parse_page_range(raw: str | None, page_count: int) -> list[int]:
    if not raw:
        return list(range(page_count))
    selected: set[int] = set()
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            start, end = part.split("-", 1)
            selected.update(range(int(start) - 1, int(end)))
        else:
            selected.add(int(part) - 1)
    return [page for page in sorted(selected) if 0 <= page < page_count]


def normalize_base_url(base_url: str | None) -> str | None:
    if not base_url:
        return None
    cleaned = base_url.rstrip("/")
    if cleaned.endswith("/v1"):
        return cleaned
    return f"{cleaned}/v1"


def get_client() -> OpenAI:
    if OpenAI is None:
        raise RuntimeError("OpenAI SDK is not installed. Run: python3 -m pip install -r requirements.txt")
    if not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError("OPENAI_API_KEY is not set.")
    base_url = normalize_base_url(os.getenv("OPENAI_BASE_URL"))
    if base_url:
        return OpenAI(base_url=base_url)
    return OpenAI()


def response_text(response: object) -> str:
    text = getattr(response, "output_text", None)
    if isinstance(text, str):
        return text.strip()
    raw = str(response).strip()
    parsed = parse_sse_response_text(raw)
    return parsed or raw


def parse_sse_response_text(raw: str) -> str:
    if "event: response." not in raw or "data:" not in raw:
        return ""

    deltas: list[str] = []
    final_text = ""
    for line in raw.splitlines():
        if not line.startswith("data:"):
            continue
        payload = line.removeprefix("data:").strip()
        if not payload or payload == "[DONE]":
            continue
        try:
            data = json.loads(payload)
        except json.JSONDecodeError:
            continue
        event_type = data.get("type")
        if event_type == "response.output_text.done" and isinstance(data.get("text"), str):
            final_text = data["text"]
        elif event_type == "response.output_text.delta" and isinstance(data.get("delta"), str):
            deltas.append(data["delta"])
    return (final_text or "".join(deltas)).strip()


def extract_words_from_pdf_images(
    pdf_path: Path,
    model: str,
    pages: str | None,
    delay: float,
    checkpoint_path: Path | None = None,
) -> list[str]:
    try:
        import fitz
    except ImportError as exc:
        raise RuntimeError("Vision extraction from PDFs requires PyMuPDF. Install requirements.txt first.") from exc

    client = get_client()
    words: list[str] = read_words(checkpoint_path) if checkpoint_path and checkpoint_path.exists() else []
    seen: set[str] = set(words)

    doc = fitz.open(str(pdf_path))
    for index in parse_page_range(pages, len(doc)):
        page = doc[index]
        pixmap = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
        image_bytes = pixmap.tobytes("png")
        data_url = "data:image/png;base64," + base64.b64encode(image_bytes).decode("ascii")

        prompt = (
            "从这页词语资料中提取所有汉语成语或四字词语。"
            "只输出 JSON 数组，数组元素是字符串；不要输出解释、序号或 Markdown。"
        )
        response = client.responses.create(
            model=model,
            input=[
                {
                    "role": "user",
                    "content": [
                        {"type": "input_text", "text": prompt},
                        {"type": "input_image", "image_url": data_url, "detail": "high"},
                    ],
                }
            ],
        )
        page_words = parse_json_words(response_text(response))
        for word in page_words:
            word = clean_word(word)
            if len(word) != 4 or word in seen:
                continue
            seen.add(word)
            words.append(word)
        if checkpoint_path:
            write_words(words, checkpoint_path)
        if delay:
            time.sleep(delay)
    return words


def parse_json_words(raw: str) -> list[str]:
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        return extract_candidates(cleaned)
    if not isinstance(data, list):
        return []
    return [str(item) for item in data]


def read_words(path: Path) -> list[str]:
    words: list[str] = []
    seen: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        word = clean_word(line)
        if not word or word in seen:
            continue
        seen.add(word)
        words.append(word)
    return words


def write_words(words: Sequence[str], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(words) + "\n", encoding="utf-8")


def load_done_words(path: Path) -> set[str]:
    if not path.exists():
        return set()
    done: set[str] = set()
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.reader(handle, delimiter="\t")
        for row in reader:
            if row:
                done.add(row[0])
    return done


def anki_field(value: str) -> str:
    return value.replace("\t", " ").replace("\r\n", "\n").replace("\r", "\n").replace("\n", "<br>")


def generate_definition(client: OpenAI, model: str, prompt: str, word: str) -> str:
    response = client.responses.create(
        model=model,
        input=[
            {"role": "system", "content": prompt},
            {"role": "user", "content": word},
        ],
    )
    return response_text(response)


def generate_tsv(
    words: Iterable[str],
    output: Path,
    prompt_path: Path,
    model: str,
    tag: str,
    limit: int | None,
    resume: bool,
    delay: float,
) -> None:
    client = get_client()
    prompt = prompt_path.read_text(encoding="utf-8")
    output.parent.mkdir(parents=True, exist_ok=True)
    done = load_done_words(output) if resume else set()
    mode = "a" if resume and output.exists() else "w"
    count = 0

    with output.open(mode, encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        for word in words:
            if word in done:
                continue
            definition = generate_definition(client, model, prompt, word)
            writer.writerow([word, anki_field(definition), tag])
            handle.flush()
            count += 1
            if limit and count >= limit:
                break
            if delay:
                time.sleep(delay)


def command_extract(args: argparse.Namespace) -> None:
    source = Path(args.input)
    if args.mode == "vision":
        if source.suffix.lower() != ".pdf":
            raise SystemExit("--mode vision only supports PDF input.")
        words = extract_words_from_pdf_images(source, args.model, args.pages, args.delay, Path(args.output))
    else:
        try:
            text = read_text(source)
        except RuntimeError:
            if args.mode != "auto" or source.suffix.lower() != ".pdf":
                raise
            text = ""
        words = extract_candidates(text, args.min_len, args.max_len)
        if args.mode == "auto" and not words and source.suffix.lower() == ".pdf":
            words = extract_words_from_pdf_images(source, args.model, args.pages, args.delay, Path(args.output))
    write_words(words, Path(args.output))
    print(f"Wrote {len(words)} words to {args.output}")


def command_generate(args: argparse.Namespace) -> None:
    words = read_words(Path(args.words))
    generate_tsv(
        words=words,
        output=Path(args.output),
        prompt_path=Path(args.prompt),
        model=args.model,
        tag=args.tag,
        limit=args.limit,
        resume=args.resume,
        delay=args.delay,
    )
    print(f"Wrote Anki TSV to {args.output}")


def command_all(args: argparse.Namespace) -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        words_path = Path(args.words_output or Path(temp_dir) / "words.txt")
        extract_args = argparse.Namespace(
            input=args.input,
            output=str(words_path),
            mode=args.mode,
            model=args.extract_model,
            pages=args.pages,
            delay=args.delay,
            min_len=args.min_len,
            max_len=args.max_len,
        )
        command_extract(extract_args)
        generate_args = argparse.Namespace(
            words=str(words_path),
            output=args.output,
            prompt=args.prompt,
            model=args.generate_model,
            tag=args.tag,
            limit=args.limit,
            resume=args.resume,
            delay=args.delay,
        )
        command_generate(generate_args)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Extract idioms and create Anki TSV files.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    extract = subparsers.add_parser("extract", help="Extract words from text/PDF sources.")
    extract.add_argument("--input", required=True)
    extract.add_argument("--output", default="output/words.txt")
    extract.add_argument("--mode", choices=["auto", "text", "vision"], default="auto")
    extract.add_argument("--model", default=os.getenv("OPENAI_EXTRACT_MODEL", os.getenv("OPENAI_MODEL", "gpt-5-mini")))
    extract.add_argument("--pages", help="PDF pages for vision extraction, e.g. 1,3-5.")
    extract.add_argument("--min-len", type=int, default=4)
    extract.add_argument("--max-len", type=int, default=4)
    extract.add_argument("--delay", type=float, default=0.0)
    extract.set_defaults(func=command_extract)

    generate = subparsers.add_parser("generate", help="Generate Anki TSV from a word list.")
    generate.add_argument("--words", required=True)
    generate.add_argument("--output", default="output/anki.tsv")
    generate.add_argument("--prompt", default=str(DEFAULT_PROMPT))
    generate.add_argument("--model", default=os.getenv("OPENAI_GENERATE_MODEL", os.getenv("OPENAI_MODEL", "gpt-5-mini")))
    generate.add_argument("--tag", default="成语")
    generate.add_argument("--limit", type=int)
    generate.add_argument("--resume", action="store_true")
    generate.add_argument("--delay", type=float, default=0.0)
    generate.set_defaults(func=command_generate)

    all_cmd = subparsers.add_parser("all", help="Extract words and generate Anki TSV.")
    all_cmd.add_argument("--input", required=True)
    all_cmd.add_argument("--output", default="output/anki.tsv")
    all_cmd.add_argument("--words-output")
    all_cmd.add_argument("--prompt", default=str(DEFAULT_PROMPT))
    all_cmd.add_argument("--mode", choices=["auto", "text", "vision"], default="auto")
    all_cmd.add_argument("--extract-model", default=os.getenv("OPENAI_EXTRACT_MODEL", os.getenv("OPENAI_MODEL", "gpt-5-mini")))
    all_cmd.add_argument("--generate-model", default=os.getenv("OPENAI_GENERATE_MODEL", os.getenv("OPENAI_MODEL", "gpt-5-mini")))
    all_cmd.add_argument("--pages")
    all_cmd.add_argument("--min-len", type=int, default=4)
    all_cmd.add_argument("--max-len", type=int, default=4)
    all_cmd.add_argument("--tag", default="成语")
    all_cmd.add_argument("--limit", type=int)
    all_cmd.add_argument("--resume", action="store_true")
    all_cmd.add_argument("--delay", type=float, default=0.0)
    all_cmd.set_defaults(func=command_all)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        args.func(args)
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
