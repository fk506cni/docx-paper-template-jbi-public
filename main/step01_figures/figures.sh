#!/bin/bash
# docx-paper-template — Step 01 図前処理オーケストレータ (ホスト側エントリ)
#
# docs/architecture.md §2.1。入力 <INPUT_ROOT>/figs (*.svg / *.pdf / *.png 等ラスタ / mermaid/*.mmd) を処理し、
# data/step01_figures/figs に正規化済み図ツリー (修正済 SVG / PDF 由来 SVG / 複製ラスタ / *.svg.png) を作る。
# 生ラスタ図 (PNG/JPEG/TIFF) は変換せずそのまま複製する。
#
# コンテナ分担:
#   - Mermaid 作図 (.mmd->svg/pdf) : docx-paper-template-mermaid    (docker/mermaid/convert.sh)
#   - 主処理 (fix-clip / pdf2svg / png): docx-paper-template-pandoc (compose run + process_figures.py)
#   - 最終図 svg->pdf (任意, --final-pdf): docx-paper-template-svg-converter (docker/svg-conversion/convert.sh)
#
# INPUT_ROOT は .development マーカーで切替 (docs/architecture.md §4):
#   .development 有り -> data/dummy / 無し -> src   (環境変数 INPUT_ROOT で上書き可)
#
# 使い方:
#   main/step01_figures/figures.sh [--final-pdf] [--input <dir>]
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$PROJECT_ROOT"

COMPOSE_FILE="docker/docker-compose.yml"
OUT_ROOT="data/step01_figures"
FINAL_PDF=0
INPUT_OVERRIDE=""

usage() {
    cat <<'EOF'
使い方: main/step01_figures/figures.sh [--final-pdf] [--input <dir>]

オプション:
  --final-pdf     出力 SVG を svg-conversion コンテナで text-to-path PDF にも変換 (最終図確認用)
  --input <dir>   入力ルートを明示 (既定: .development 有り->data/dummy / 無し->src)

出力: data/step01_figures/figs/ (figs/<rel> 構造を保持。pandoc のフルパス解決のため)
EOF
}

# --- 引数解析 ---
while [ $# -gt 0 ]; do
    case "$1" in
        --final-pdf) FINAL_PDF=1; shift ;;
        --input)     INPUT_OVERRIDE="${2:?--input にディレクトリを指定してください}"; shift 2 ;;
        -h|--help)   usage; exit 0 ;;
        *)           echo "エラー: 不明な引数 '$1'" >&2; usage; exit 1 ;;
    esac
done

# --- INPUT_ROOT 解決 (環境変数 > --input > .development) ---
if [ -n "${INPUT_ROOT:-}" ]; then
    : # 環境変数を尊重
elif [ -n "$INPUT_OVERRIDE" ]; then
    INPUT_ROOT="$INPUT_OVERRIDE"
elif [ -e ".development" ]; then
    INPUT_ROOT="data/dummy"
else
    INPUT_ROOT="src"
fi

if [ ! -d "$INPUT_ROOT/figs" ]; then
    echo "エラー: 入力図ディレクトリ '$INPUT_ROOT/figs' がありません。" >&2
    echo "  ダミーで検証するには 'echo dev > .development' で data/dummy/ に切替えてください (docs/architecture.md §4)。" >&2
    exit 1
fi

echo "== Step 01 図前処理 =="
echo "  INPUT_ROOT = $INPUT_ROOT"
echo "  OUT_ROOT   = $OUT_ROOT"

# --- 出力ツリーを掃除して作り直す (冪等な再生成。mermaid 生成より前に行う) ---
rm -rf "${OUT_ROOT:?}/figs"
mkdir -p "$OUT_ROOT/figs"

# --- 0. Mermaid 作図: .mmd を出力ツリーへ複製して変換 (入力ツリーを汚さない) ---
#     convert.sh は入力と同じディレクトリに svg/pdf を出すため、出力ツリー側の複製で実行する。
shopt -s nullglob
mmd_files=("$INPUT_ROOT"/figs/mermaid/*.mmd)
shopt -u nullglob
if [ ${#mmd_files[@]} -gt 0 ]; then
    mkdir -p "$OUT_ROOT/figs/mermaid"
    for mmd in "${mmd_files[@]}"; do
        base="$(basename "$mmd")"
        staged="$OUT_ROOT/figs/mermaid/$base"
        cp "$mmd" "$staged"
        echo "-- Mermaid 作図: figs/mermaid/$base -> svg/pdf"
        bash docker/mermaid/convert.sh "$staged" both
        rm -f "$staged"   # 一次ソース .mmd の複製は残さない (svg/pdf のみ残す)
    done
else
    echo "-- Mermaid: $INPUT_ROOT/figs/mermaid/*.mmd は無し (スキップ)"
fi

# --- 1-3. 主処理 (fix-clip / pdf2svg / png) を pandoc コンテナ内で実行 ---
echo "-- 主処理 (fix-svg-clips / pdf2svg / png) @ docx-paper-template-pandoc"
docker compose -f "$COMPOSE_FILE" run --rm -u "$(id -u):$(id -g)" pandoc \
    python3 main/step01_figures/process_figures.py "$INPUT_ROOT" "$OUT_ROOT"

# --- 4. (任意) 最終図 svg->pdf (text-to-path フォントアウトライン化) ---
#     雑誌が PDF/EPS を要求する場合の最終図経路 (本来は step05 が雑誌要件で駆動)。ここでは
#     svg-conversion コンテナで text-to-path PDF を生成できることの確認に留める。
#     【mermaid は除外】mermaid SVG は埋込 CSS を持ち inkscape のCSSパーサが取りこぼす
#       (parsing error 警告 + 体裁劣化)。mermaid 図の最終 PDF は mmdc が直接出した
#       figs/mermaid/<name>.pdf (手順 0 で生成済) が正本なので、inkscape で上書きしない。
if [ "$FINAL_PDF" -eq 1 ]; then
    echo "-- 最終図 svg->pdf (text-to-path) @ docx-paper-template-svg-converter (mermaid は除外)"
    shopt -s globstar nullglob
    svgs=("$OUT_ROOT"/figs/**/*.svg)
    shopt -u globstar nullglob
    for svg in "${svgs[@]}"; do
        case "$svg" in
            */mermaid/*) echo "   skip (mermaid 正本 pdf を保持): $svg"; continue ;;
        esac
        out_pdf="${svg%.svg}.pdf"
        bash docker/svg-conversion/convert.sh "$svg" "$out_pdf"
    done
fi

echo "== 完了: $OUT_ROOT/figs 配下 =="
find "$OUT_ROOT/figs" -type f | sort | sed 's/^/  /'
