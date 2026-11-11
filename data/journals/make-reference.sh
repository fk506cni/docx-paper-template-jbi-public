#!/bin/bash
# make-reference.sh — 任意の雑誌プロファイルの reference.docx を profile.yaml から生成する (汎用版)。
#
# docs/architecture.md §3。pandoc 既定 reference.docx をベースに、<id>/profile.yaml の体裁値 (line_spacing /
# line_numbers / page_numbers / font / font_size / margins / paper_size) と差分スタイル
# DiffAdd/DiffDel を焼き込む。
# すべて docx-paper-template-pandoc コンテナ内で実行する (ホスト Python は汚さない)。
#
# 新規雑誌の追加手順 (docs/usage-guide.md §4):
#   1. mkdir data/journals/<id> && cp data/journals/_default/profile.yaml data/journals/<id>/
#      (profile.yaml だけを写す。ディレクトリごと写すと _default 専用の make-reference.sh と
#       _default.csl まで付いてくる)
#   2. data/journals/<id>/profile.yaml を実規定に合わせて編集
#   3. bash data/journals/make-reference.sh <id>      ← 本スクリプト
#      (雛形の reference_doc: reference.docx のままなら省いてよい。無ければ build / diff が生成する)
#   (引用様式が違う場合は <id>.csl を置き csl: <id>.csl に。null なら _default の AMA を継承し、そのことを警告する)
#
# 使い方:  bash data/journals/make-reference.sh <id>     (id 既定: _default)
# 出力:    data/journals/<id>/reference.docx
#
# 注: profile.margins は四辺一律の代表値として解釈する (非対称余白の誌は patch 側の拡張が要る)。
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$PROJECT_ROOT"

ID="${1:-_default}"
PROFILE="data/journals/$ID/profile.yaml"
PATCH="main/00_setup/lib/patch_reference_docx.py"

if [ ! -f "$PROFILE" ]; then
    echo "エラー: $PROFILE がありません (data/journals/$ID/ を作りましたか)" >&2
    exit 1
fi

RUN="docker compose -f docker/docker-compose.yml run --rm -u $(id -u):$(id -g) -T pandoc"

echo "[1/3] pandoc 既定 reference.docx を取り出す ($ID)"
$RUN sh -c "pandoc -o /workspace/data/journals/$ID/.base-reference.docx --print-default-data-file reference.docx"

echo "[2/3] profile.yaml の体裁 + 差分スタイルを焼き込む"
# profile.yaml を読んで patch_reference_docx.py の引数へ変換し実行する (コンテナ内 python)。
# JID はコンテナへ -e で明示的に渡す (docker compose run はホスト環境変数を自動転送しない)。
docker compose -f docker/docker-compose.yml run --rm -u "$(id -u):$(id -g)" -T \
    -e JID="$ID" pandoc python3 - <<'PY'
import os, subprocess, sys

# 値の解釈 (真偽値 / 列挙 / 単位つき数値) は main/00_setup/lib/journal_profile.py に 1 つだけ置き、
# 焼き込み側 (本スクリプト) と検査側 (build / validate) で共有する。ここに写しを置くと
# 既定値が二重に定義され、片方だけ直したときに焼き込みと検査が食い違う。
sys.path.insert(0, "main/00_setup/lib")
import journal_profile as jp

jid = os.environ["JID"]
prof = jp.load(jid)

ls = jp.as_choice(prof.get("line_spacing"), {"single", "1.5", "double"}, "double")
ln = jp.as_choice(prof.get("line_numbers"), {"none", "continuous", "per-page"}, "continuous")
pn = jp.as_flag(prof.get("page_numbers"), "page_numbers")
font = str(prof.get("font") or "Times New Roman")
fs = jp.as_number(prof.get("font_size"), "12")
mg = jp.as_number(prof.get("margins"), "25")
paper = jp.as_choice(prof.get("paper_size"), {"a4", "letter"}, "a4")

base = f"data/journals/{jid}/.base-reference.docx"
out = f"data/journals/{jid}/reference.docx"
cmd = ["python3", "main/00_setup/lib/patch_reference_docx.py", base, "-o", out,
       "--line-spacing", ls, "--line-numbers", ln, "--font", font,
       "--font-size", str(fs), "--margin", str(mg), "--paper", paper]
if pn:
    cmd.append("--page-numbers")
# 題・見出し・抄録の級数と色。text_styles が無い誌は引数を足さない = 従来どおり
ts = prof.get("text_styles") or {}
if jp.as_flag(ts.get("uniform_size"), "text_styles.uniform_size"):
    cmd.append("--uniform-style-size")
hc = jp.as_choice(ts.get("heading_color"), {"keep", "black"}, "keep")
if hc != "keep":
    cmd += ["--heading-color", hc]
# 段落スタイルが個別に持つ行送りを外し、文書全体の行送りにそろえる
if jp.as_flag(ts.get("uniform_line_spacing"), "text_styles.uniform_line_spacing"):
    cmd.append("--uniform-line-spacing")
print("  " + " ".join(cmd))
subprocess.run(cmd, check=True)
PY

echo "[3/3] 中間物を片付ける"
rm -f "data/journals/$ID/.base-reference.docx"

echo "done: data/journals/$ID/reference.docx"
# reference_doc が既に reference.docx を指していれば案内は要らない (build / diff が自動で生成するときも同じ)
ref_doc=$(sed -n 's/^reference_doc:[[:space:]]*\([^[:space:]#]*\).*/\1/p' "$PROFILE" | head -n 1)
if [ "$ref_doc" != "reference.docx" ]; then
    echo "  → data/journals/$ID/profile.yaml の reference_doc を 'reference.docx' に変更すると build/diff で使われます"
    echo "    (いまの値: '${ref_doc:-(未指定)}')"
fi
