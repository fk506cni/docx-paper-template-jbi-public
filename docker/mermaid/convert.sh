#!/bin/bash
# docx-paper-template — Mermaid (.mmd) → SVG/PDF 変換
# 使い方: docker/mermaid/convert.sh <input.mmd> [svg|pdf|both] [--force] [--rebuild]
#   出力は入力 .mmd と同じディレクトリに <name>.svg / <name>.pdf を生成する。
#   注意: 出力先に同名ファイルがあると上書きの危険があるため、既定では中止する。
#         意図した上書きは --force で明示する。
#   注意: 生成 svg は入力 .mmd と同じ場所 (例: src/figs/mermaid/) に出る。ビルドの図前処理は
#         figs/mermaid/*.mmd を自分で描くので、原稿の figs/ の中で単独に描く必要は無い (確かめるだけなら
#         jank/ などへ写して描く)。残った <名前>.svg / .pdf は前処理が読み飛ばして警告する (docs/architecture.md §2.1)。
#         data/dummy/ 配下で実行すると生成物が git 追跡対象になりうる点に留意する。
# 設計: docs/architecture.md §1.2.2。未ビルド時は自動ビルド。Puppeteer は --no-sandbox。
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

IMAGE_NAME="docx-paper-template-mermaid"

usage() {
    cat <<'EOF'
使い方: docker/mermaid/convert.sh <Mermaidファイル(.mmd)> [出力形式] [--force] [--rebuild]

出力形式:
  svg   - SVG のみ
  pdf   - PDF のみ
  both  - SVG と PDF 両方 (デフォルト)

オプション:
  --force    出力先の同名ファイルを上書きする (既定は中止)
  --rebuild  既存イメージがあっても再ビルドする (Dockerfile/版を更新したとき)

例:
  docker/mermaid/convert.sh src/figs/mermaid/flow.mmd
  docker/mermaid/convert.sh src/figs/mermaid/flow.mmd both --force
EOF
}

# --- 引数解析 (フラグと位置引数を分離) ---
FORCE=0
REBUILD=0
positional=()
for arg in "$@"; do
    case "$arg" in
        --force)   FORCE=1 ;;
        --rebuild) REBUILD=1 ;;
        -h|--help) usage; exit 0 ;;
        *)         positional+=("$arg") ;;
    esac
done
set -- ${positional[@]+"${positional[@]}"}

if [ $# -eq 0 ]; then
    usage
    exit 1
fi

INPUT_FILE="$1"
OUTPUT_FORMAT="${2:-both}"

case "$OUTPUT_FORMAT" in
    svg|pdf|both) ;;
    *) echo "エラー: 不正な出力形式 '$OUTPUT_FORMAT' (svg|pdf|both)" >&2; exit 1 ;;
esac

# 入力ファイルの絶対パスを解決 (相対パスはカレントディレクトリ基準)
if [[ "$INPUT_FILE" = /* ]]; then
    INPUT_FULLPATH="$INPUT_FILE"
else
    INPUT_FULLPATH="$(realpath "$INPUT_FILE")"
fi

if [ ! -f "$INPUT_FULLPATH" ]; then
    echo "エラー: Mermaid ファイル '$INPUT_FULLPATH' が見つかりません" >&2
    exit 1
fi

INPUT_BASENAME="$(basename "$INPUT_FULLPATH")"
INPUT_NAME="${INPUT_BASENAME%.*}"
INPUT_DIR="$(dirname "$INPUT_FULLPATH")"

# --- 上書きガード ---
# 生成対象のうち既存のものを洗い出し、--force が無ければ中止する。
targets=()
if [ "$OUTPUT_FORMAT" != "pdf" ]; then targets+=("$INPUT_DIR/$INPUT_NAME.svg"); fi
if [ "$OUTPUT_FORMAT" != "svg" ]; then targets+=("$INPUT_DIR/$INPUT_NAME.pdf"); fi
existing=()
for t in "${targets[@]}"; do
    if [ -e "$t" ]; then existing+=("$t"); fi
done
if [ "${#existing[@]}" -gt 0 ]; then
    if [ "$FORCE" -ne 1 ]; then
        echo "エラー: 出力先に既存ファイルがあります。上書きを避けるため中止します:" >&2
        for e in "${existing[@]}"; do echo "  - $e" >&2; done
        echo "意図した上書きなら --force を付けて再実行してください。手書き図を同名・同ディレクトリに置かないでください。" >&2
        exit 1
    fi
    echo "警告: --force 指定により既存ファイルを上書きします:" >&2
    for e in "${existing[@]}"; do echo "  - $e" >&2; done
fi

# --- イメージ準備 (未ビルド時または --rebuild 時にビルド。context = docker/mermaid) ---
if [ "$REBUILD" -eq 1 ] || ! docker image inspect "$IMAGE_NAME" >/dev/null 2>&1; then
    if [ "$REBUILD" -eq 1 ]; then
        echo "--rebuild 指定: イメージ '$IMAGE_NAME' を再ビルドします..."
    else
        echo "イメージ '$IMAGE_NAME' が無いためビルドします..."
    fi
    # 版固定 ARG は環境変数で上書き可能。未指定なら Dockerfile 既定値を使う。
    build_args=()
    if [ -n "${MERMAID_CLI_VERSION:-}" ]; then
        build_args+=(--build-arg "MERMAID_CLI_VERSION=$MERMAID_CLI_VERSION")
    fi
    docker build -t "$IMAGE_NAME" ${build_args[@]+"${build_args[@]}"} "$SCRIPT_DIR"
fi

echo "Mermaid → ${OUTPUT_FORMAT} 変換: $INPUT_FULLPATH"

# 生成物の所有権をホストユーザに保つため -u を付け、書込可能な HOME を /tmp に向ける。
# ファイル名は -e でコンテナへ渡し、コンテナ内ではダブルクオートで参照する
# (ホスト側での文字列差し込みを避け、空白等を含む名でも壊れないようにする)。
#
# 【config.json は実行時に差し込む】イメージには Dockerfile の COPY で焼いてあるが、
# それだけだと config.json を直しても**再ビルドするまで古い設定のまま動く** (しかも黙って)。
# 読み取り専用で上から被せ、リポジトリの config.json が常に効くようにする。
#
# 【SVG の後処理】postprocess-svg.js (同じく実行時に被せる) が生成 SVG をその場で直す:
#   - hsl() の色を 16 進に (テーマの色を変えると Mermaid がサブグラフの枠などを hsl() で出し、
#     PowerPoint がその箱を**黒く塗る**。Microsoft 365 で実測) / 小数の rgb() を 16 進に
#   - <text> に xml:space="preserve" (librsvg が語の間の空白を落とし PNG が「apparatusbody」になるため)
# 詳細は postprocess-svg.js の冒頭。
docker run --rm \
    -u "$(id -u):$(id -g)" \
    -e HOME=/tmp \
    -e PUPPETEER_EXECUTABLE_PATH=/usr/bin/chromium \
    -e IN_BASENAME="$INPUT_BASENAME" \
    -e IN_NAME="$INPUT_NAME" \
    -e OUT_FORMAT="$OUTPUT_FORMAT" \
    -v "$INPUT_DIR:/workspace" \
    -v "$SCRIPT_DIR/config.json:/etc/mermaid/config.json:ro" \
    -v "$SCRIPT_DIR/postprocess-svg.js:/opt/docx-paper-template/postprocess-svg.js:ro" \
    "$IMAGE_NAME" bash -c '
        set -e
        cat > /tmp/puppeteer-config.json <<JSON
{"args":["--no-sandbox","--disable-setuid-sandbox","--disable-dev-shm-usage","--disable-gpu"],"headless":true}
JSON
        opts="-p /tmp/puppeteer-config.json -c /etc/mermaid/config.json -b white -f"
        case "$OUT_FORMAT" in
            svg)  mmdc -i "$IN_BASENAME" -o "$IN_NAME.svg" $opts ;;
            pdf)  mmdc -i "$IN_BASENAME" -o "$IN_NAME.pdf" $opts ;;
            both) mmdc -i "$IN_BASENAME" -o "$IN_NAME.svg" $opts
                  mmdc -i "$IN_BASENAME" -o "$IN_NAME.pdf" $opts ;;
        esac
        if [ -f "$IN_NAME.svg" ] && [ "$OUT_FORMAT" != "pdf" ]; then
            node /opt/docx-paper-template/postprocess-svg.js "$IN_NAME.svg"
        fi
    '

# ラベルが HTML (foreignObject) のままの SVG は Word / PowerPoint / PNG フォールバックで
# **ラベルが全部消える** (箱だけが残る)。config.json の htmlLabels が効かなかったら気づけるよう警告する。
if [ "$OUTPUT_FORMAT" != "pdf" ] && [ -f "$INPUT_DIR/$INPUT_NAME.svg" ] \
        && grep -q "<foreignObject" "$INPUT_DIR/$INPUT_NAME.svg"; then
    echo "警告: $INPUT_NAME.svg にラベルが HTML (foreignObject) で出ています。Word / PowerPoint と" >&2
    echo "      PNG フォールバックではラベルが表示されません。config.json の最上位に" >&2
    echo "      \"htmlLabels\": false があるか、mermaid-cli の版でその指定が効くかを確かめてください。" >&2
fi

echo "完了:"
if [ "$OUTPUT_FORMAT" != "pdf" ] && [ -f "$INPUT_DIR/$INPUT_NAME.svg" ]; then
    echo "  SVG: $INPUT_DIR/$INPUT_NAME.svg ($(du -h "$INPUT_DIR/$INPUT_NAME.svg" | cut -f1))"
fi
if [ "$OUTPUT_FORMAT" != "svg" ] && [ -f "$INPUT_DIR/$INPUT_NAME.pdf" ]; then
    echo "  PDF: $INPUT_DIR/$INPUT_NAME.pdf ($(du -h "$INPUT_DIR/$INPUT_NAME.pdf" | cut -f1))"
fi
exit 0
