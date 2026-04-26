# Anki 成语释义工具

这个工具用于把词语资料转换成 Anki 可导入的 TSV：

1. 从文本或 PDF 中抽取四字词语。
2. 按统一 prompt 调用 OpenAI 生成成语解释。
3. 导出 `词语<TAB>解释<TAB>标签` 格式，Anki 可以直接按制表符导入。

## 安装

```bash
cd /Users/epiphany/Downloads/epi-agent/公考/成语anki工具
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r requirements.txt
```

设置 API key：

```bash
export OPENAI_API_KEY="你的 key"
```

如果使用 OpenAI 兼容网关，可以设置 base URL：

```bash
export OPENAI_BASE_URL="https://api.gptsapi.net"
```

可选设置模型：

```bash
export OPENAI_EXTRACT_MODEL="gpt-5-mini"
export OPENAI_GENERATE_MODEL="gpt-5-mini"
```

## 推荐流程

先抽词，人工检查词表：

```bash
python3 -m anki_word_tool.cli extract \
  --input "../高频800词记忆版--（白色底图）.pdf" \
  --output output/words.txt \
  --mode vision \
  --pages 1-3
```

上一级目录里的 `高频800词记忆版--（白色底图）.pdf` 是扫描页，文本层抽取结果为空，所以建议直接使用 `--mode vision`。

确认 `output/words.txt` 没问题后生成 Anki 文件：

```bash
python3 -m anki_word_tool.cli generate \
  --words output/words.txt \
  --output output/anki.tsv \
  --resume
```

一次跑完：

```bash
python3 -m anki_word_tool.cli all \
  --input "../高频800词记忆版--（白色底图）.pdf" \
  --words-output output/words.txt \
  --output output/anki.tsv \
  --mode vision \
  --extract-model gpt-5-mini \
  --generate-model gpt-5-mini \
  --resume
```

## 说明

- `--mode text`：只读文本层，适合 `.txt`、`.md` 或带文本层的 PDF。
- `--mode vision`：把扫描 PDF 页面渲染成图片，再调用 OpenAI 从图中抽词。
- `--mode auto`：先尝试文本层，抽不到词时对 PDF 自动转视觉抽取。
- `--pages 1,3-5`：只处理指定页，适合先小批量验证。
- `--limit 10`：生成阶段只处理前 10 个新词，适合试跑。
- `--resume`：如果已有输出文件，跳过已经生成过的词。
- `--extract-model`：`all` 命令中用于扫描页抽词的模型。
- `--generate-model`：`all` 命令中用于生成成语释义的模型。

默认 prompt 存在 `anki_word_tool/config/idiom_prompt.txt`，就是当前这版成语释义风格。

## 导入 Anki

在 Anki 中选择导入 `output/anki.tsv`，分隔符选 Tab。字段映射：

1. 正面：词语
2. 背面：解释
3. 标签：成语
