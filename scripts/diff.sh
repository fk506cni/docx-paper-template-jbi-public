#!/bin/bash
# diff.sh — 全領域差分 オーケストレータ (構造保持 AST 差分。step03)
#
# docs/architecture.md §2.3 / docs/design-fullarea-diff.md。旧版・新版の main.md を pandoc -t json で AST 化し、
# Python+panflute の二層差分で「構造を壊さず変更語句だけを色 span で包む」マージ AST を作り、
# pandoc で docx 化する (タイトル/著者/抄録/キーワード/本文/表/テキストボックス内表まで全領域)。
# pandiff は使わない。処理本体は docx-paper-template-pandoc コンテナ内 (diff_docx.py)。
#
# 2 つの入力モード:
#   scripts/diff.sh [REVISION]       git revision (既定 HEAD~1) の main.md を旧版、作業ツリーを新版
#   scripts/diff.sh old.md new.md    明示した 2 ファイルを旧版・新版
#
# INPUT_ROOT は .development マーカーで切替 (build.sh と同一規則。docs/architecture.md §4):
#   .development 有り -> data/dummy / 無し -> src   (環境変数 INPUT_ROOT または --input で上書き可)
#   revision モードの旧版は <INPUT_ROOT>/main.md を git revision から取り出す。
#   図 (data/step01_figures) と文献 (<INPUT_ROOT>/ref.bib) は新版基準で解決する。
#
# 使い方:
#   scripts/diff.sh [REVISION | old.md new.md]
#                   [--journal <id>] [--article-type <id>] [--input <dir>] [--skip-figures]
#                   [--no-embed-svg] [--no-relocate]
#
# 出力: data/step03_diff/main_diff.docx
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

COMPOSE_FILE="docker/docker-compose.yml"
OUT_DIR="data/step03_diff"
OUT="$OUT_DIR/main_diff.docx"
JOURNAL="_default"
ARTICLE_TYPE=""
INPUT_OVERRIDE=""
SKIP_FIGURES=0
EMBED_FLAG=""
RELOCATE_FLAG=""
POSITIONAL=()

usage() {
    cat <<'EOF'
使い方: scripts/diff.sh [REVISION | old.md new.md] [オプション]

入力モード:
  (引数なし)        HEAD~1 の main.md を旧版、作業ツリーの main.md を新版として差分
  REVISION          指定 git revision (例 HEAD~3) の main.md を旧版に
  old.md new.md     明示した 2 ファイルを旧版・新版に (両方とも実在ファイル)

オプション:
  --journal <id>        雑誌プロファイル (data/journals/<id>)。既定: _default
  --article-type <id>   記事種別 (profile の article_types を持つ誌のみ。例: bhi の original)。
                        差分は種別で出力を変えない — 未知種別の早期エラーと build.sh との
                        引数の統一のために受ける
  --input <dir>         入力ルートを明示 (既定: .development 有り->data/dummy / 無し->src)
  --skip-figures        図前処理 (step01) をスキップ (data/step01_figures を再利用)
  --no-embed-svg        ネイティブ SVG 埋込をしない (PNG フォールバックのみ)
  --no-relocate         textbox の page 配置移動をしない

出力: data/step03_diff/main_diff.docx
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
        --)             shift; while [ $# -gt 0 ]; do POSITIONAL+=("$1"); shift; done ;;
        -*)             echo "エラー: 不明なオプション '$1'" >&2; usage; exit 1 ;;
        *)              POSITIONAL+=("$1"); shift ;;
    esac
done

# --- INPUT_ROOT 解決 (環境変数 > --input > .development。build.sh と同一規則) ---
if [ -n "${INPUT_ROOT:-}" ]; then
    :
elif [ -n "$INPUT_OVERRIDE" ]; then
    INPUT_ROOT="$INPUT_OVERRIDE"
elif [ -e ".development" ]; then
    INPUT_ROOT="data/dummy"
else
    INPUT_ROOT="src"
fi

if [ ! -d "data/journals/$JOURNAL" ]; then
    echo "エラー: 雑誌プロファイル 'data/journals/$JOURNAL' がありません。" >&2
    exit 1
fi
# reference.docx は make-reference.sh が profile.yaml から作る生成物。無ければここで作る
# (build.sh と同じ。scripts/lib/ensure-reference.sh)
# shellcheck source=lib/ensure-reference.sh
. "$SCRIPT_DIR/lib/ensure-reference.sh"
ensure_reference_docx "$JOURNAL"

# --- 旧版 (OLD_MD) / 新版 (NEW_MD) の決定 ---
TMP_OLD=""
cleanup() { [ -n "$TMP_OLD" ] && rm -f "$TMP_OLD" || true; }
trap cleanup EXIT

npos="${#POSITIONAL[@]}"
if [ "$npos" -eq 2 ] && [ -f "${POSITIONAL[0]}" ] && [ -f "${POSITIONAL[1]}" ]; then
    # --- 2 ファイル明示モード ---
    OLD_MD="${POSITIONAL[0]}"
    NEW_MD="${POSITIONAL[1]}"
    echo "== Step 03 全領域差分 (2 ファイルモード) =="
    echo "  OLD = $OLD_MD"
    echo "  NEW = $NEW_MD"
else
    # --- git revision モード ---
    if [ "$npos" -gt 1 ]; then
        echo "エラー: 引数が多すぎます (revision を 1 つ、または実在する old.md new.md の 2 つ)。" >&2
        usage; exit 1
    fi
    REVISION="${POSITIONAL[0]:-HEAD~1}"
    NEW_MD="$INPUT_ROOT/main.md"
    if [ ! -f "$NEW_MD" ]; then
        echo "エラー: 新版原稿 '$NEW_MD' がありません。" >&2
        echo "  ダミーで検証するには 'echo dev > .development' で data/dummy/ に切替えてください (docs/architecture.md §4)。" >&2
        exit 1
    fi
    if ! git rev-parse --verify "$REVISION" >/dev/null 2>&1; then
        echo "エラー: git revision '$REVISION' が見つかりません。" >&2
        exit 1
    fi
    if ! git cat-file -e "$REVISION:$NEW_MD" 2>/dev/null; then
        echo "エラー: '$NEW_MD' は revision '$REVISION' に存在しません (新規ファイル?)。" >&2
        echo "  2 ファイルモード 'scripts/diff.sh old.md new.md' を使ってください。" >&2
        exit 1
    fi
    mkdir -p jank
    TMP_OLD="jank/diff_old_$$.md"
    git show "$REVISION:$NEW_MD" > "$TMP_OLD"
    OLD_MD="$TMP_OLD"
    echo "== Step 03 全領域差分 (git revision モード) =="
    echo "  REVISION = $REVISION  (旧版 = $REVISION:$NEW_MD)"
    echo "  NEW      = $NEW_MD (作業ツリー)"
fi

echo "  INPUT_ROOT = $INPUT_ROOT"
echo "  JOURNAL    = $JOURNAL"
echo "  OUT        = $OUT"

# --- 図前処理 (step01) — 新版基準。SVG 埋込・PNG フォールバックに必要 ---
if [ "$SKIP_FIGURES" -eq 0 ]; then
    echo "-- 図前処理 (step01) を実行 (--skip-figures で省略可)"
    INPUT_ROOT="$INPUT_ROOT" bash main/step01_figures/figures.sh
else
    echo "-- 図前処理をスキップ (既存 data/step01_figures を再利用)"
    if [ -d "$INPUT_ROOT/figs" ] && [ -d "data/step01_figures/figs" ]; then
        newest_in="$(find "$INPUT_ROOT/figs" -type f -printf '%T@\n' 2>/dev/null | sort -n | tail -1)"
        newest_out="$(find "data/step01_figures/figs" -type f -printf '%T@\n' 2>/dev/null | sort -n | tail -1)"
        if [ -n "$newest_in" ] && [ -n "$newest_out" ] \
           && awk "BEGIN{exit !($newest_in > $newest_out)}"; then
            echo "  警告: $INPUT_ROOT/figs に data/step01_figures/figs より新しい図があります。" >&2
            echo "        --skip-figures を外して再生成することを検討してください。" >&2
        fi
    fi
fi

mkdir -p "$OUT_DIR"

RUN="docker compose -f $COMPOSE_FILE run --rm -u $(id -u):$(id -g) pandoc"

echo ""
$RUN python3 main/step03_diff/diff_docx.py \
    --input-root "$INPUT_ROOT" --journal "$JOURNAL" \
    ${ARTICLE_TYPE:+--article-type "$ARTICLE_TYPE"} \
    --old "$OLD_MD" --new "$NEW_MD" --out "$OUT" $EMBED_FLAG $RELOCATE_FLAG

# どの誌・どの原稿 (新版) から作った差分かを記録する。package.py が照合し、別の原稿の差分が
# 提出物に混ざったときに SUBMISSION.md の注意に載せる
printf '%s\n%s\n' "$JOURNAL" "$NEW_MD" > "$OUT_DIR/.main_diff.source"

echo ""
echo "== 差分生成 完了: $OUT =="
