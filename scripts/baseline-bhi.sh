#!/bin/bash
# baseline-bhi.sh — BHI プロファイルのスナップショット
#
# baseline.sh は data/journals/*/profile.yaml の誌を撮るが、bhi は除いてある。
# BHI は入力ルートが data/dummy/bhi で --article-type も要るため同じループに載らない。
# 別スクリプトに切る。
#
# 使い方: bash scripts/baseline-bhi.sh [suffix]
# 比較 :  python3 scripts/compare-snapshots.py <pre の suffix> <post の suffix>
# 出力先: jank/baseline/bhi__<suffix>/  (git 管理外。実体は数百 MB になるため)
#
set -euo pipefail
cd "$(dirname "$0")/.."

usage() {
    cat <<'EOF'
使い方: bash scripts/baseline-bhi.sh [suffix]

BHI プロファイルの回帰スナップショットを撮る。動作例 data/dummy/bhi で build / diff / package (final) を回し
(--article-type original)、出力を jank/baseline/ に退避する。

  suffix 無し    jank/baseline/bhi/ に退避 (着手前のベースライン)
  suffix 有り    jank/baseline/bhi__<suffix>/ に退避 (変更後の比較用)
  -h, --help     この説明を出して終わる

diff の旧版は環境変数 DIFF_REV (既定 HEAD~1) で決まる。比較する 2 つは同じ DIFF_REV で撮ること。
clone した直後など、履歴に旧版が無いときは DIFF_REV=HEAD を付ける (差分は空になるが diff の経路は通る)。
段が失敗したら、その段の名前とログの末尾を出して止まる (ログ全体は退避先の *.log)。
bhi 以外の誌は scripts/baseline.sh で撮る。
比較: docker compose -f docker/docker-compose.yml run --rm -u "$(id -u):$(id -g)" pandoc \
          python3 scripts/compare-snapshots.py <前の suffix> <後の suffix>
EOF
}

# --help を suffix として受け取って撮り始めないように、- で始まる引数は suffix にしない
case "${1:-}" in
    -h|--help) usage; exit 0 ;;
    -*)        echo "エラー: 不明なオプション '$1' (suffix は - で始められません)" >&2; usage >&2; exit 1 ;;
esac
if [ $# -gt 1 ]; then
    echo "エラー: 引数は suffix の 1 つだけです (受け取った数: $#)" >&2; usage >&2; exit 1
fi

SUFFIX="${1:-}"
BASE="jank/baseline"
DIFF_REV="${DIFF_REV:-HEAD~1}"

# 段の出力はログに書き、失敗したら段の名前とログの末尾を画面に出して止める
# (set -e で止めるだけだと、何が失敗したかはログを開くまで分からない)
run_logged() {   # $1 = 段の名前 / $2 = ログ / $3 以降 = コマンド
    local name="$1" log="$2"; shift 2
    local rc=0
    "$@" >"$log" 2>&1 || rc=$?
    if [ "$rc" -ne 0 ]; then
        echo "エラー: $name が失敗しました (終了コード $rc)。ログ: $log" >&2
        echo "---- ログの末尾 ----" >&2
        tail -n 15 "$log" >&2
        exit "$rc"
    fi
}

# diff の旧版に原稿があるかを、撮り始める前に確かめる (clone した直後の HEAD~1 には無い)
if ! git cat-file -e "$DIFF_REV:data/dummy/bhi/main.md" 2>/dev/null; then
    echo "エラー: diff の旧版 DIFF_REV=$DIFF_REV に data/dummy/bhi/main.md がありません。" >&2
    echo "  clone した直後など、履歴に旧版が無いときは DIFF_REV=HEAD を付けて撮ってください" >&2
    echo "  (例: DIFF_REV=HEAD bash scripts/baseline-bhi.sh <suffix>。比較する 2 つは同じ DIFF_REV で撮ること)。" >&2
    exit 1
fi

out="$BASE/bhi${SUFFIX:+__$SUFFIX}"
rm -rf "$out" "data/output/bhi"
mkdir -p "$out"

echo "===== baseline: bhi -> $out ====="
run_logged "build (bhi)" "$out/build.log" \
    bash scripts/build.sh --journal bhi --article-type original --input data/dummy/bhi
cp -a data/step01_figures "$out/step01_figures"
cp -a data/step02_build "$out/step02_build"
# diff も撮る。撮らないと package が data/step03_diff に残っている**別原稿の**差分 docx を
# manuscript-diff.docx として拾い、スナップショット間で本物でない差が出る (実測)。
run_logged "diff (bhi)" "$out/diff.log" \
    bash scripts/diff.sh --journal bhi --skip-figures --input data/dummy/bhi "$DIFF_REV"
cp -a data/step03_diff "$out/step03_diff"
run_logged "package final (bhi)" "$out/package-final.log" \
    bash scripts/package.sh --journal bhi --mode final --input data/dummy/bhi
cp -a "data/output/bhi" "$out/output-final"
echo "===== baseline 完了: $out ====="
