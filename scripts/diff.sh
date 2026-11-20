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

# --- 旧版・新版の原稿と入力ルートの文献・図が、変換を行うコンテナから見えるかを確かめる (build.sh と同じ考え方) ---
# コンテナにはリポジトリしかマウントしないので、リポジトリの外のファイルや絶対パスで指したファイルは、ホストでは見えても
# コンテナの中で「原稿が見つかりません」になる。見えないものを名指しして先に止める。
# reference.docx の生成 (コンテナを使う) より前に行い、Docker が動いていないときの案内をここで出す
diff_inputs=("$OLD_MD" "$NEW_MD")
for f in ref.bib figs; do
    if [ -e "$INPUT_ROOT/$f" ]; then
        diff_inputs+=("$INPUT_ROOT/$f")
    fi
done
# 見えない入力は package.py が「inputs-visible: パス …」の行で知らせる。その行が無い失敗は Docker 自体の失敗
if ! vis_out="$(docker compose -f "$COMPOSE_FILE" run --rm -T -u "$(id -u):$(id -g)" pandoc \
        python3 main/step05_package/package.py inputs-visible --input-root . "${diff_inputs[@]}" 2>&1)"; then
    unseen="$(printf '%s\n' "$vis_out" | tr -d '\r' | sed -n 's/^inputs-visible: //p' | tail -n 1)"
    if [ -z "$unseen" ]; then
        echo "エラー: 変換を行うコンテナ (pandoc) を起動できませんでした: $(printf '%s\n' "$vis_out" | tr -d '\r' | tail -n 1)" >&2
        echo "  Docker (Docker Desktop) が動いているか、イメージを作ったか ('docker compose -f docker/docker-compose.yml build') を確かめてください。" >&2
        exit 1
    fi
    echo "エラー: 次の入力は、ホストからは見えますが変換を行うコンテナからは見えません: $unseen" >&2
    echo "  コンテナからはリポジトリの中しか見えません。旧版・新版の原稿と入力ルートはリポジトリの中に置き、" >&2
    echo "  リポジトリのルートからの相対パスで指定してください (絶対パスや、リポジトリの外を指すリンクは使えません)。" >&2
    exit 1
fi

# reference.docx は make-reference.sh が profile.yaml から作る生成物。無ければここで作る
# (build.sh と同じ。scripts/lib/ensure-reference.sh)
# shellcheck source=lib/ensure-reference.sh
. "$SCRIPT_DIR/lib/ensure-reference.sh"
ensure_reference_docx "$JOURNAL"

# --- 同じ作業ツリーでの build / diff / package の同時実行を止める ---
# diff も step01 の図を作り直すので、build の最中に回すと、build の記録と main.docx が一致したまま別の原稿の図が入りうる
. "$SCRIPT_DIR/lib/build-lock.sh"
take_build_lock diff.sh

# --- 図前処理 (step01) — 新版基準。SVG 埋込・PNG フォールバックに必要 ---
if [ "$SKIP_FIGURES" -eq 0 ]; then
    echo "-- 図前処理 (step01) を実行 (--skip-figures で省略可)"
    INPUT_ROOT="$INPUT_ROOT" bash main/step01_figures/figures.sh
else
    echo "-- 図前処理をスキップ (既存 data/step01_figures を再利用)"
    # 既存の前処理の結果が、今の入力ルートの今の figs/ から作ったものかを照合し、違えば止める (build.sh と同じ)
    if ! fig_problem="$(docker compose -f "$COMPOSE_FILE" run --rm -T -u "$(id -u):$(id -g)" pandoc \
            python3 main/step05_package/package.py figures-source check --input-root "$INPUT_ROOT" 2>&1)"; then
        echo "エラー: --skip-figures を付けましたが、$(printf '%s\n' "$fig_problem" | tail -n 1)。" >&2
        echo "  --skip-figures を外して、図の前処理からやり直してください。" >&2
        exit 1
    fi
fi

mkdir -p "$OUT_DIR"

RUN="docker compose -f $COMPOSE_FILE run --rm -u $(id -u):$(id -g) pandoc"

# 差分の記録は、差分が成功した後にだけ書く。先に消さないと、失敗したときに直前の記録が残り、
# package が直前の原稿の差分として扱う (記録が無ければ package は SUBMISSION.md に注意を出す)
rm -f "$OUT_DIR/.main_diff.source"

# 差分の前に原稿の SHA-256 を取る。差分の後に取り直して違えば (差分の最中に原稿が変わった) 記録を書かずに止める。
# 差分は変わる前の原稿から作られているので、変わった後の原稿の SHA-256 を記録すると、古い差分が今の原稿のものとして
# 提出物に入る。旧版がファイルのとき (old.md new.md の形) は旧版も同じく見る
NEW_SHA_BEFORE=$(sha256sum "$NEW_MD" | cut -d' ' -f1)
OLD_SHA_BEFORE=$(sha256sum "$OLD_MD" | cut -d' ' -f1)

# 原稿のほかの入力 (ref.bib / cover-letter.md / revise-report.md / figs/) のハッシュも差分の前と後で比べ、差分の記録に書く。
# 計算は package.py の _inputs_sha256() (build.sh の出所の記録と同じ数え方)。package が今の入力と比べ、差分を作った後に
# 文献や図を直したときに注意を出す (main.md だけを比べると、古い文献・古い図の差分 docx が注意なしで提出物に入る)。
# -T: 端末を割り当てない (割り当てると出力の行末に CR が付く)
inputs_sha256() {
    docker compose -f "$COMPOSE_FILE" run --rm -T -u "$(id -u):$(id -g)" pandoc \
        python3 main/step05_package/package.py inputs-sha256 --input-root "$1" | tr -d '\r' | tail -n 1
}
if ! INPUTS_SHA_BEFORE="$(inputs_sha256 "$INPUT_ROOT")" || ! [[ "$INPUTS_SHA_BEFORE" =~ ^[0-9a-f]{64}$ ]]; then
    echo "エラー: 原稿のほかの入力のハッシュを計算できませんでした (package.py inputs-sha256: '${INPUTS_SHA_BEFORE:-}')" >&2
    exit 1
fi

echo ""
$RUN python3 main/step03_diff/diff_docx.py \
    --input-root "$INPUT_ROOT" --journal "$JOURNAL" \
    ${ARTICLE_TYPE:+--article-type "$ARTICLE_TYPE"} \
    --old "$OLD_MD" --new "$NEW_MD" --out "$OUT" $EMBED_FLAG $RELOCATE_FLAG

# どの誌・どの原稿 (新版) から作った差分かを記録する。package.py が照合し、別の原稿の差分が
# 提出物に混ざったときに SUBMISSION.md の注意に載せる。
# 書式: 1 行目 = 誌 / 2 行目 = 新版の原稿のパス / 3 行目 = 新版の原稿の SHA-256 / 4 行目 = 記事種別 (無ければ空) /
# 5 行目 = 入力ルートの原稿のほかの入力のハッシュ (build の出所の記録の inputs_sha256 と同じ)。package.py が読むので変えるときは両方を直すこと。
# 中身のハッシュで比べるので、package.sh --build が main.docx を作り直しても「古い」とは判定しない
# 次の照合で止めるときは、作った差分 docx も消す。記録の無い差分 docx を package は注意つきで集めるが、
# 照合に通らなかった差分 docx は提出物に入れる理由が無いため
NEW_SHA=$(sha256sum "$NEW_MD" | cut -d' ' -f1)
changed_md=""
if [ "$NEW_SHA" != "$NEW_SHA_BEFORE" ]; then
    changed_md="$NEW_MD"
elif [ "$(sha256sum "$OLD_MD" | cut -d' ' -f1)" != "$OLD_SHA_BEFORE" ]; then
    changed_md="$OLD_MD"
else
    if ! INPUTS_SHA="$(inputs_sha256 "$INPUT_ROOT")" || ! [[ "$INPUTS_SHA" =~ ^[0-9a-f]{64}$ ]]; then
        rm -f "$OUT"
        echo "エラー: 原稿のほかの入力のハッシュを計算できませんでした (package.py inputs-sha256: '${INPUTS_SHA:-}')。" >&2
        echo "  作った差分 docx ($OUT) は消して、記録を書きません。" >&2
        exit 1
    fi
    if [ "$INPUTS_SHA" != "$INPUTS_SHA_BEFORE" ]; then
        changed_md="$INPUT_ROOT の ref.bib / cover-letter.md / revise-report.md / figs/ のどれか"
    fi
fi
if [ -n "$changed_md" ]; then
    rm -f "$OUT"
    echo "エラー: 差分の最中に $changed_md が変わりました。もう一度 diff を回してください" >&2
    echo "  (今の差分 docx は変わる前の原稿から作った可能性があるので、消して記録を書きません)。" >&2
    exit 1
fi
# 差分 docx に埋め込んだ図 (data/step01_figures/) も、差分の最後に図の前処理の記録と照合する (build.sh と同じ)。
# 止めた build のコンテナが記録の後に図を書くと、別の原稿の図が差分 docx に入りうるため
if ! fig_problem="$(docker compose -f "$COMPOSE_FILE" run --rm -T -u "$(id -u):$(id -g)" pandoc \
        python3 main/step05_package/package.py figures-source check --input-root "$INPUT_ROOT" 2>&1)"; then
    rm -f "$OUT"
    echo "エラー: 差分に使った図が、図の前処理の記録と食い違います: $(printf '%s\n' "$fig_problem" | tr -d '\r' | tail -n 1)。" >&2
    echo "  今の差分 docx には別の原稿の図が入った可能性があるので、消して記録を書きません。--skip-figures を付けずにもう一度 diff を回してください。" >&2
    exit 1
fi
printf '%s\n%s\n%s\n%s\n%s\n' "$JOURNAL" "$NEW_MD" "$NEW_SHA" "$ARTICLE_TYPE" "$INPUTS_SHA" > "$OUT_DIR/.main_diff.source"

echo ""
echo "== 差分生成 完了: $OUT =="
