---
name: anki-deck-production
description: Use when turning source word lists, PDFs, or study notes into Anki-ready decks with TSV output, import instructions, sales copy, and reusable QA checks for Chinese exam-prep vocabulary projects.
---

# Anki Deck Production

## Purpose

Use this skill for projects that transform Chinese study material into Anki decks, especially vocabulary, idioms, or exam-prep word lists.

## Workflow

1. Identify the source type.
   - Text or Markdown: parse directly.
   - PDF with text layer: try text extraction first.
   - Scanned PDF or image-heavy handout: use vision extraction and verify a small page range before full extraction.

2. Normalize the word list.
   - Keep one entry per line.
   - Remove page headers, footers, sequence numbers, duplicate words, and non-target terms.
   - Preserve Chinese punctuation only when it is part of the expression.
   - Save the cleaned list separately from the generated deck.

3. Generate Anki fields.
   - Prefer TSV for broad compatibility.
   - Standard fields: front, back, tags.
   - For Chinese exam-prep idioms, use: `词语<TAB>解释<TAB>标签`.
   - Keep explanations short enough for repeated review; avoid essay-style notes.

4. Resume and audit long runs.
   - Use resumable generation when an API call may fail mid-run.
   - After generation, check row count, duplicate fronts, empty backs, tab count, and encoding.
   - Spot-check examples against the source and expected explanation style.

5. Package user-facing assets.
   - Include a concise README or import note.
   - Include PC and mobile import instructions.
   - If selling the deck, prepare title options, short pitch, full listing copy, and FAQ replies.

## QA Checks

Run these checks before delivery:

```bash
wc -l output/words.txt output/anki.tsv
awk -F '\t' 'NF != 3 { print NR ":" $0 }' output/anki.tsv
cut -f1 output/anki.tsv | sort | uniq -d
```

For generated Chinese decks, manually inspect at least 10 cards across the beginning, middle, and end of the TSV.

## Import Guidance

For Anki desktop import:

- File type: tab-separated text.
- Field 1 maps to front.
- Field 2 maps to back.
- Field 3 maps to tags.

For mobile use:

- Prefer importing on desktop, then syncing through AnkiWeb.
- If importing directly on mobile, use the system share sheet or file manager to open the TSV with Anki/AnkiDroid.

## Reusable Lessons

- Tutorial images with Chinese interface text should be deterministic SVG/HTML screenshots rather than generative raster images, because text accuracy matters.
- Keep generated sales copy separate from the technical README so the repository remains useful to both buyers and maintainers.
- Keep raw source, cleaned word list, generated TSV, and marketing/tutorial assets as separate artifacts.
- Do not overwrite user-edited decks during reruns; write to a new filename or use resumable output.
