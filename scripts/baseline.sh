#!/bin/bash
# baseline.sh — bhi 以外の全プロファイル (data/journals/*/profile.yaml) の
# build/package 出力の退避 (回帰スナップショット。変更の前後に撮り、
# 「回帰なし」はこれとの内容一致で判定する)
#
# 使い方: bash scripts/baseline.sh [suffix]
#   suffix 無し → jank/baseline/<journal>/ に退避 (着手前ベースライン)
#   suffix 有り → jank/baseline/<journal>__<suffix>/ に退避 (変更後の比較用スナップショット)
# BHI は入力ルートが違うので scripts/baseline-bhi.sh で別に撮る。
# 比較 :  python3 scripts/compare-snapshots.py <pre の suffix> <post の suffix>
#
# 【置き場所】道具は git で追跡する scripts/ に置き、**出力先は jank/baseline/**
# (スナップショットの実体は数百 MB になるため git 管理外に置く)。
#
# 【覆う範囲の限界】通すのは build / diff / package(draft) / package(final) の 4 経路だけで、
# --keep-figures や --format を明示した経路は回帰試験の外にある。
set -euo pipefail
cd "$(dirname "$0")/.."

usage() {
    cat <<'EOF'
使い方: bash scripts/baseline.sh [suffix]

回帰スナップショットを撮る (bhi 以外の全プロファイル。対象誌は data/journals/*/profile.yaml から組む)。
同梱のサンプル (data/dummy) で build / diff / package (draft・final) を回し、出力を jank/baseline/ に退避する。

  suffix 無し    jank/baseline/<誌>/ に退避 (着手前のベースライン)
  suffix 有り    jank/baseline/<誌>__<suffix>/ に退避 (変更後の比較用)
  -h, --help     この説明を出して終わる

diff の旧版は環境変数 DIFF_REV (既定 HEAD~1) で決まる。比較する 2 つは同じ DIFF_REV で撮ること。
clone した直後など、履歴に旧版が無いときは DIFF_REV=HEAD を付ける (差分は空になるが diff の経路は通る)。
段が失敗したら、その段の名前とログの末尾を出して止まる (ログ全体は退避先の *.log)。
BHI は scripts/baseline-bhi.sh で別に撮る。
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
export INPUT_ROOT=data/dummy
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
check_diff_rev() {   # $1 = 旧版に要る原稿のパス
    if ! git cat-file -e "$DIFF_REV:$1" 2>/dev/null; then
        echo "エラー: diff の旧版 DIFF_REV=$DIFF_REV に $1 がありません。" >&2
        echo "  clone した直後など、履歴に旧版が無いときは DIFF_REV=HEAD を付けて撮ってください" >&2
        echo "  (例: DIFF_REV=HEAD bash scripts/baseline.sh <suffix>。比較する 2 つは同じ DIFF_REV で撮ること)。" >&2
        exit 1
    fi
}
check_diff_rev "$INPUT_ROOT/main.md"

# 対象誌は data/journals/*/profile.yaml から組む (雑誌プロファイルを足せば自動で対象になる)。
#   - bhi は入力ルートと --article-type が違うので scripts/baseline-bhi.sh で別に撮る
#   - 並びは LC_ALL=C で固定し、_default を必ず先頭にする。先頭の誌だけが図を処理し (下の first)、
#     残りは --skip-figures でその図を使い回すので、先頭が変わると全誌の比較元が変わる。
#     glob の並びはロケールの照合順に従い、記号を無視するロケールでは _default が先頭に来ないことがある
JOURNALS=()
[ -f data/journals/_default/profile.yaml ] && JOURNALS+=(_default)
while IFS= read -r j; do
    case "$j" in _default|bhi) continue ;; esac
    JOURNALS+=("$j")
done < <(for p in data/journals/*/profile.yaml; do basename "$(dirname "$p")"; done | LC_ALL=C sort)
if [ "${#JOURNALS[@]}" -eq 0 ]; then
    echo "エラー: 対象誌がありません (data/journals/*/profile.yaml。bhi は baseline-bhi.sh で撮る)" >&2
    exit 1
fi
echo "対象誌: ${JOURNALS[*]}"

first=1
for j in "${JOURNALS[@]}"; do
    out="$BASE/$j${SUFFIX:+__$SUFFIX}"
    rm -rf "$out"
    mkdir -p "$out"
    # 比較元と比較先を同条件にする。package.py は data/output/<j> が既に
    # あると「既存の … を再生成します」を出すため、残っていると本物でないログ差分になる。
    rm -rf "data/output/$j"
    echo "===== baseline: $j -> $out ====="
    if [ "$first" -eq 1 ]; then
        run_logged "build ($j)" "$out/build.log" bash scripts/build.sh --journal "$j"
        first=0
    else
        run_logged "build ($j)" "$out/build.log" bash scripts/build.sh --journal "$j" --skip-figures
    fi
    cp -a data/step02_build "$out/step02_build"
    # 差分生成 (step03) も退避・比較の対象にする。build と package の 2 経路だけでは、
    # diff_docx.py が起動不能になっていても見逃す。
    # 比較元/比較先で同じ旧版を見るよう revision は明示指定できるようにする (HEAD~1 は
    # worktree 側で別の commit を指してしまうため)。
    run_logged "diff ($j)" "$out/diff.log" bash scripts/diff.sh --journal "$j" --skip-figures "$DIFF_REV"
    cp -a data/step03_diff "$out/step03_diff"
    run_logged "package draft ($j)" "$out/package-draft.log" bash scripts/package.sh --journal "$j" --mode draft
    cp -a "data/output/$j" "$out/output-draft"
    run_logged "package final ($j)" "$out/package-final.log" bash scripts/package.sh --journal "$j" --mode final
    cp -a "data/output/$j" "$out/output-final"
done
echo "===== baseline 完了: $BASE/*${SUFFIX:+__$SUFFIX} ====="
