#!/bin/bash
# build.sh — 原稿ビルド オーケストレータ (図前処理 step01 → docx 化 step02)
#
# docs/architecture.md §2.2。INPUT_ROOT の main.md を投稿用 docx へ変換する。図前処理 (step01) を先に走らせ、
# pandoc + OOXML 後処理 (表罫線 / ネイティブ SVG 埋込 / textbox) を docx-paper-template-pandoc
# コンテナ内で実行する。revise-report.md / cover-letter.md があれば同機構で docx 化する。
#
# INPUT_ROOT は .development マーカーで切替 (docs/architecture.md §4):
#   .development 有り -> data/dummy / 無し -> src   (環境変数 INPUT_ROOT または --input で上書き可)
#
# 使い方:
#   scripts/build.sh [--journal <id>] [--article-type <id>] [--input <dir>] [--skip-figures]
#                    [--no-embed-svg] [--no-relocate]
#
# 出力: data/step02_build/{main,revise-report,cover-letter}.docx
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

COMPOSE_FILE="docker/docker-compose.yml"
OUT_DIR="data/step02_build"
JOURNAL="_default"
ARTICLE_TYPE=""
INPUT_OVERRIDE=""
SKIP_FIGURES=0
EMBED_FLAG=""
RELOCATE_FLAG=""

usage() {
    cat <<'EOF'
使い方: scripts/build.sh [オプション]

オプション:
  --journal <id>        雑誌プロファイル (data/journals/<id>)。既定: _default
  --article-type <id>   記事種別 (profile の article_types を持つ誌のみ。例: bhi の original)。
                        build は種別で出力を変えない — 未知種別の早期エラーと
                        data/step02_build/.journal への記録 (provenance) のために受ける
  --input <dir>         入力ルートを明示 (既定: .development 有り->data/dummy / 無し->src)
  --skip-figures        図前処理 (step01) をスキップ (data/step01_figures を再利用)
  --no-embed-svg        ネイティブ SVG 埋込をしない (PNG フォールバックのみ)
  --no-relocate         textbox の page 配置移動をしない (自然な文書フロー位置に置く)

出力: data/step02_build/{main,revise-report,cover-letter}.docx
EOF
}

while [ $# -gt 0 ]; do
    case "$1" in
        --journal)      JOURNAL="${2:?--journal に id を指定してください}"; shift 2 ;;
        --article-type) ARTICLE_TYPE="${2:?--article-type に種別 id を指定してください}"; shift 2 ;;
        --input)        INPUT_OVERRIDE="${2:?--input にディレクトリを指定してください}"; shift 2 ;;
        --skip-figures) SKIP_FIGURES=1; shift ;;
        --no-embed-svg) EMBED_FLAG="--no-embed-svg"; shift ;;
        --no-relocate)  RELOCATE_FLAG="--no-relocate"; shift ;;
        -h|--help)      usage; exit 0 ;;
        *)              echo "エラー: 不明な引数 '$1'" >&2; usage; exit 1 ;;
    esac
done

# --- INPUT_ROOT 解決 (環境変数 > --input > .development。figures.sh と同一規則) ---
if [ -n "${INPUT_ROOT:-}" ]; then
    :
elif [ -n "$INPUT_OVERRIDE" ]; then
    INPUT_ROOT="$INPUT_OVERRIDE"
elif [ -e ".development" ]; then
    INPUT_ROOT="data/dummy"
else
    INPUT_ROOT="src"
fi

if [ ! -f "$INPUT_ROOT/main.md" ]; then
    echo "エラー: 原稿 '$INPUT_ROOT/main.md' がありません。" >&2
    echo "  ダミーで検証するには 'echo dev > .development' で data/dummy/ に切替えてください (docs/architecture.md §4)。" >&2
    exit 1
fi

if [ ! -d "data/journals/$JOURNAL" ]; then
    echo "エラー: 雑誌プロファイル 'data/journals/$JOURNAL' がありません。" >&2
    exit 1
fi

# reference.docx は make-reference.sh が profile.yaml から作る生成物。無ければここで作る
# (_default と、自前の reference.docx を使う設定の対象誌。scripts/lib/ensure-reference.sh)
# shellcheck source=lib/ensure-reference.sh
. "$SCRIPT_DIR/lib/ensure-reference.sh"
ensure_reference_docx "$JOURNAL"

RUN="docker compose -f $COMPOSE_FILE run --rm -u $(id -u):$(id -g) pandoc"

echo "== Step 02 原稿ビルド =="
echo "  INPUT_ROOT = $INPUT_ROOT"
echo "  JOURNAL    = $JOURNAL"
echo "  OUT_DIR    = $OUT_DIR"

# --- 図前処理 (step01) ---
if [ "$SKIP_FIGURES" -eq 0 ]; then
    echo "-- 図前処理 (step01) を実行 (--skip-figures で省略可)"
    INPUT_ROOT="$INPUT_ROOT" bash main/step01_figures/figures.sh
else
    echo "-- 図前処理をスキップ (既存 data/step01_figures を再利用)"
    # 陳腐化検知: 入力図のいずれかが step01 出力より新しければ警告する。
    #   --skip-figures で古い図を無言で埋め込むのを防ぐ (停止はせず、再生成を促すに留める)。
    if [ -d "$INPUT_ROOT/figs" ] && [ -d "data/step01_figures/figs" ]; then
        newest_in="$(find "$INPUT_ROOT/figs" -type f -printf '%T@\n' 2>/dev/null | sort -n | tail -1)"
        newest_out="$(find "data/step01_figures/figs" -type f -printf '%T@\n' 2>/dev/null | sort -n | tail -1)"
        if [ -n "$newest_in" ] && [ -n "$newest_out" ] \
           && awk "BEGIN{exit !($newest_in > $newest_out)}"; then
            echo "  警告: $INPUT_ROOT/figs に data/step01_figures/figs より新しい図があります。" >&2
            echo "        図が更新されている可能性があります。--skip-figures を外して再生成することを検討してください。" >&2
        fi
    fi
fi

mkdir -p "$OUT_DIR"

# --- 原稿を docx 化 (main.md は必須。revise-report.md / cover-letter.md は任意) ---
build_one() {
    local doc="$1" out="$2"
    echo ""
    $RUN python3 main/step02_build/build_docx.py \
        --input-root "$INPUT_ROOT" --journal "$JOURNAL" \
        ${ARTICLE_TYPE:+--article-type "$ARTICLE_TYPE"} \
        --doc "$doc" --out "$out" $EMBED_FLAG $RELOCATE_FLAG
}

build_one "main.md" "$OUT_DIR/main.docx"

# どの雑誌で build したかを記録する (package.py が --journal と照合し、
# 雑誌体裁の取り違えを警告するため)。--article-type 指定時は 2 行目に
# 種別も記録する (provenance のみ。build の出力は種別で変わらないため照合はしない)。
if [ -n "$ARTICLE_TYPE" ]; then
    printf '%s\n%s\n' "$JOURNAL" "$ARTICLE_TYPE" > "$OUT_DIR/.journal"
else
    printf '%s\n' "$JOURNAL" > "$OUT_DIR/.journal"
fi

for opt in revise-report cover-letter; do
    if [ -f "$INPUT_ROOT/$opt.md" ]; then
        build_one "$opt.md" "$OUT_DIR/$opt.docx"
    elif [ -f "$OUT_DIR/$opt.docx" ]; then
        # 出力先を掃除する。「無いのでスキップ」と言うだけで前回の出力を残すと、
        # 入力ルートを切り替えたときに **別の原稿でビルドした docx** が data/step02_build に
        # 居座り、package が [OK] で提出物 (data/output/<id>/) に並べてしまう (実測)。
        # $OUT_DIR は生成物のディレクトリ (gitignored) なので消してよい。
        rm -f "$OUT_DIR/$opt.docx" "$OUT_DIR/$opt.docx.images.tsv"
        echo "-- $INPUT_ROOT/$opt.md は無し → 前回の $OUT_DIR/$opt.docx を削除 (別原稿の残置を防ぐ)"
    else
        echo "-- $INPUT_ROOT/$opt.md は無し (スキップ)"
    fi
done

echo ""
echo "== ビルド完了: $OUT_DIR 配下 =="
find "$OUT_DIR" -maxdepth 1 -name '*.docx' | sort | sed 's/^/  /'
