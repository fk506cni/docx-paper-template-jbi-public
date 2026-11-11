#!/bin/bash
# check-csl.sh — 雑誌 CSL の出力を規定の公式例と突き合わせる受入テスト (driver)
#
# BioHealth Informatics の引用様式は投稿可否に直結するため、規定 p.11 の
# 出力例そのものを期待値として持ち、citeproc の実出力と 1 文字ずつ照合する。
# 本体は main/step02_build/check_csl.py (docx-paper-template-pandoc コンテナ内で実行)。
#
# 使い方:
#   scripts/check-csl.sh                                  # bhi を data/dummy/bhi-csl で検証
#   scripts/check-csl.sh --journal bhi --fixture data/dummy/bhi-csl
#   scripts/check-csl.sh --docx data/step02_build/main.docx   # OOXML の上付きも実測する
#
# --docx を付けると docx の w:vertAlign を直接見て「`1)` が丸ごと上付きか」を検査する。
# 先に対象のフィクスチャを docx 化しておくこと:
#   bash scripts/build.sh --input data/dummy/bhi-csl --journal bhi --article-type original
#
# 終了コード: 0 = 全件一致 / 1 = 不一致あり (差異は行内 diff と相違文字のコードポイントで出る)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

COMPOSE_FILE="docker/docker-compose.yml"
JOURNAL="bhi"
FIXTURE="data/dummy/bhi-csl"
DOCX=""

usage() {
    cat <<'EOF'
使い方: scripts/check-csl.sh [オプション]

オプション:
  --journal <id>    雑誌プロファイル (data/journals/<id>)。既定: bhi
  --fixture <dir>   main.md / ref.bib / expected.txt を置いたフィクスチャ。
                    既定: data/dummy/bhi-csl
  --docx <path>     ビルド済み docx の OOXML も実測する (`1)` が丸ごと上付きか)
EOF
}

while [ $# -gt 0 ]; do
    case "$1" in
        --journal) JOURNAL="${2:?--journal に id を指定してください}"; shift 2 ;;
        --fixture) FIXTURE="${2:?--fixture にディレクトリを指定してください}"; shift 2 ;;
        --docx)    DOCX="${2:?--docx に docx のパスを指定してください}"; shift 2 ;;
        -h|--help) usage; exit 0 ;;
        *)         echo "エラー: 不明な引数 '$1'" >&2; usage; exit 1 ;;
    esac
done

if [ ! -d "data/journals/$JOURNAL" ]; then
    echo "エラー: 雑誌プロファイル 'data/journals/$JOURNAL' がありません。" >&2
    exit 1
fi
if [ ! -f "$FIXTURE/expected.txt" ]; then
    echo "エラー: フィクスチャ '$FIXTURE/expected.txt' がありません。" >&2
    exit 1
fi

if [ -n "$DOCX" ] && [ ! -f "$DOCX" ]; then
    echo "エラー: docx '$DOCX' がありません。" >&2
    echo "  先に 'bash scripts/build.sh --input $FIXTURE --journal $JOURNAL' を実行してください。" >&2
    exit 1
fi

docker compose -f "$COMPOSE_FILE" run --rm -u "$(id -u):$(id -g)" pandoc \
    python3 main/step02_build/check_csl.py --journal "$JOURNAL" --fixture "$FIXTURE" \
    ${DOCX:+--docx "$DOCX"}
