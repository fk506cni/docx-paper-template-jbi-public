#!/bin/bash
# docx-paper-template — 最終提出図の変換 (Inkscape)
#   既定       : SVG → PDF (text-to-path フォントアウトライン化)
#   --outline-svg: SVG → SVG (plain-svg + text-to-path。pptx 提出でフォント依存を消すため)
#
# 使い方: docker/svg-conversion/convert.sh <input.svg> [output] [--rebuild] [--embed-fonts] [--outline-svg]
#   省略時の出力は <input>.pdf (--outline-svg のときは <input>.outline.svg。入力と同じディレクトリ)。
#   output にディレクトリ付きパスを与えるとその場所へ出力する。
#   --rebuild: 既存イメージがあっても再ビルドする (Dockerfile/版を更新したとき)。
#   --embed-fonts: 既定の text-to-path (アウトライン化) ではなくフォントを PDF に埋め込む
#                  (inkscape の --export-text-to-path を外す)。雑誌が outline でなく font 埋込を
#                  要求する場合に使う (profile.figures.font_handling=embed。docs/profile-schema.md / step05)。
#                  注: 字形を保つにはコンテナにそのフォントが居ること (MS Core Fonts / fonts/ 同梱分)。
#                  --outline-svg とは併用できない (アウトライン化するのが目的の経路のため)。
#   --outline-svg: PDF ではなく **アウトライン化した SVG** を出す。pptx に埋め込む SVG を
#                  profile.figures.pptx.text_to_path=true で作るときに使う。受け側に同じフォントが
#                  無くても字送りが崩れなくなる代わりに、文字は選択・検索できなくなる。
#                  ※ BHI の既定は text_to_path=false (受理後に組版会社が組み直すため。
#                    docs/journal-bhi.md §5.1.3 リスク 3)。
# 設計: docs/architecture.md §1.2.3。未ビルド時は自動ビルド (context = リポジトリルートで fonts/ 同梱)。
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

IMAGE_NAME="docx-paper-template-svg-converter"

usage() {
    cat <<'EOF'
使い方: docker/svg-conversion/convert.sh <SVGファイル> [出力ファイル] [--rebuild] [--embed-fonts] [--outline-svg]

オプション:
  --rebuild       既存イメージがあっても再ビルドする (Dockerfile/版を更新したとき)
  --embed-fonts   text-to-path (アウトライン化) ではなくフォントを PDF に埋め込む
                  (profile.figures.font_handling=embed 用)
  --outline-svg   PDF ではなく **アウトライン化した SVG** を出す (既定出力は
                  <入力>.outline.svg)。pptx 提出で profile.figures.pptx.text_to_path=true の
                  ときに使う。--embed-fonts とは併用できない

例:
  docker/svg-conversion/convert.sh src/figs/fig1.svg
  docker/svg-conversion/convert.sh src/figs/fig1.svg fig1-final.pdf
  docker/svg-conversion/convert.sh src/figs/fig1.svg out/fig1.pdf
  docker/svg-conversion/convert.sh src/figs/fig1.svg out/fig1.outline.svg --outline-svg
EOF
}

# --- 引数解析 (フラグと位置引数を分離) ---
REBUILD=0
EMBED_FONTS=0
OUTLINE_SVG=0
positional=()
for arg in "$@"; do
    case "$arg" in
        --rebuild)      REBUILD=1 ;;
        --embed-fonts)  EMBED_FONTS=1 ;;
        --outline-svg)  OUTLINE_SVG=1 ;;
        -h|--help)      usage; exit 0 ;;
        *)              positional+=("$arg") ;;
    esac
done
set -- ${positional[@]+"${positional[@]}"}

if [ $# -eq 0 ]; then
    usage
    exit 1
fi

if [ "$OUTLINE_SVG" -eq 1 ] && [ "$EMBED_FONTS" -eq 1 ]; then
    echo "エラー: --outline-svg と --embed-fonts は併用できません" >&2
    echo "  --outline-svg は文字をパス化するための経路で、フォント埋込とは目的が相反します。" >&2
    exit 1
fi

INPUT_SVG="$1"
if [ "$OUTLINE_SVG" -eq 1 ]; then
    OUTPUT_PDF="${2:-${INPUT_SVG%.svg}.outline.svg}"
else
    OUTPUT_PDF="${2:-${INPUT_SVG%.svg}.pdf}"
fi

# 入力の絶対パスを解決 (相対パスはカレントディレクトリ基準)
if [[ "$INPUT_SVG" = /* ]]; then
    INPUT_FULLPATH="$INPUT_SVG"
else
    INPUT_FULLPATH="$(realpath "$INPUT_SVG")"
fi

if [ ! -f "$INPUT_FULLPATH" ]; then
    echo "エラー: SVG ファイル '$INPUT_FULLPATH' が見つかりません" >&2
    exit 1
fi

# 出力の絶対パスを解決 (存在しなくてよい)。出力先ディレクトリ指定を尊重する。
if [[ "$OUTPUT_PDF" = /* ]]; then
    OUTPUT_FULLPATH="$OUTPUT_PDF"
else
    OUTPUT_FULLPATH="$(realpath -m "$OUTPUT_PDF")"
fi

INPUT_BASENAME="$(basename "$INPUT_FULLPATH")"
INPUT_DIR="$(dirname "$INPUT_FULLPATH")"
OUTPUT_BASENAME="$(basename "$OUTPUT_FULLPATH")"
OUTPUT_DIR="$(dirname "$OUTPUT_FULLPATH")"
mkdir -p "$OUTPUT_DIR"

# --- イメージ準備 (未ビルド時または --rebuild 時にビルド。context = リポジトリルート、Dockerfile を -f で明示) ---
if [ "$REBUILD" -eq 1 ] || ! docker image inspect "$IMAGE_NAME" >/dev/null 2>&1; then
    if [ "$REBUILD" -eq 1 ]; then
        echo "--rebuild 指定: イメージ '$IMAGE_NAME' を再ビルドします..."
    else
        echo "イメージ '$IMAGE_NAME' が無いためビルドします..."
    fi
    # MS Core Fonts の取得可否は環境変数で上書き可能。
    # 例: FETCH_MSCOREFONTS=false で取得スキップ (fonts/ に vendoring 済みの場合)。
    build_args=()
    if [ -n "${FETCH_MSCOREFONTS:-}" ]; then
        build_args+=(--build-arg "FETCH_MSCOREFONTS=$FETCH_MSCOREFONTS")
    fi
    docker build -t "$IMAGE_NAME" -f "$SCRIPT_DIR/Dockerfile" \
        ${build_args[@]+"${build_args[@]}"} "$PROJECT_ROOT"
fi

if [ "$OUTLINE_SVG" -eq 1 ]; then
    echo "SVG → SVG (plain-svg + text-to-path) 変換: $INPUT_FULLPATH → $OUTPUT_FULLPATH"
elif [ "$EMBED_FONTS" -eq 1 ]; then
    echo "SVG → PDF (フォント埋込) 変換: $INPUT_FULLPATH → $OUTPUT_FULLPATH"
else
    echo "SVG → PDF (text-to-path) 変換: $INPUT_FULLPATH → $OUTPUT_FULLPATH"
fi

# 生成物の所有権をホストユーザに保つため -u を付け、書込可能な HOME を /tmp に向ける
# (inkscape のプロファイル/キャッシュ書込先確保のため)。入力/出力ディレクトリを別マウントし、
# ファイル名は -e でコンテナへ渡してダブルクオート参照する (空白等を含む名でも壊れない)。
# TEXT_OPT: 既定は --export-text-to-path (アウトライン化)。--embed-fonts 指定時は外して
# inkscape の既定 (使用フォントを PDF に埋込) に任せる (字形保持にはコンテナにフォントが要る。docs/profile-schema.md)。
docker run --rm \
    -u "$(id -u):$(id -g)" \
    -e HOME=/tmp \
    -e IN="$INPUT_BASENAME" \
    -e OUT="$OUTPUT_BASENAME" \
    -e EMBED_FONTS="$EMBED_FONTS" \
    -e OUTLINE_SVG="$OUTLINE_SVG" \
    -v "$INPUT_DIR:/in" \
    -v "$OUTPUT_DIR:/out" \
    "$IMAGE_NAME" bash -c '
        set -e
        export FONTCONFIG_PATH=/etc/fonts
        if [ "$OUTLINE_SVG" = "1" ]; then
            # pptx へ埋め込む SVG のアウトライン化。--export-plain-svg で
            # Inkscape 独自名前空間を落とし、--export-text-to-path で文字をパスにする。
            # 幅・高さ・viewBox は保たれるので、後段の寸法解析 (svg_raster) はそのまま通る。
            inkscape --export-type=svg --export-plain-svg --export-text-to-path \
                "/in/$IN" -o "/out/$OUT"
        else
            if [ "$EMBED_FONTS" = "1" ]; then
                TEXT_OPT=""
            else
                TEXT_OPT="--export-text-to-path"
            fi
            inkscape --export-type=pdf --export-pdf-version=1.4 $TEXT_OPT \
                "/in/$IN" -o "/out/$OUT"
        fi
    '

echo "完了: $OUTPUT_FULLPATH ($(du -h "$OUTPUT_FULLPATH" | cut -f1))"
