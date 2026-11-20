#!/bin/bash
# remove-sample.sh — src/ に同梱したサンプル論文のファイルを消す (自分の論文を書き始める前に 1 回)
#
# 消すのは、サンプルの一覧 (scripts/lib/sample-files.sha256) に載っているパスにあって、中身 (SHA-256) が
# サンプルと一致するファイルだけ。書き換えたファイルや、同じ名前で置いた自分のファイルは消さずに「残した」と出す。
# 何度回しても自分のファイルは消えない。中身が空になった supplementary/ は消す (figs/ は残す)。
# コンテナは使わない (sha256sum、無ければ shasum -a 256)。
#
# package.sh は、入力ルートの main.md がサンプルではないのにサンプルのほかのファイル (カバーレター・補足資料・
# 文献・図) が残っていると、最終モードで止まってこのスクリプトを案内する (草稿モードでは注意だけ)。
#
# 使い方:
#   bash scripts/remove-sample.sh               # src/ のサンプルのファイルを消す
#   bash scripts/remove-sample.sh --dry-run     # 消すもの・残すものの一覧だけを出す (何も消さない)
#   bash scripts/remove-sample.sh --input <dir> # src/ ではなく <dir> を見る (サンプルを別の場所に写したとき)
#   bash scripts/remove-sample.sh --check       # (保守用) 一覧が今の src/ のサンプルと合っているかを確かめる。
#                                               #   合わなければ終了コード 1 (サンプルを直したら一覧を作り直す)
#
# 一覧の書式: 「SHA-256<空白 2 つ>入力ルートからの相対パス」の行 (sha256sum の出力と同じ)。同じパスの行が 2 つ以上あれば、
#   どれかと一致すればサンプルとみなす (公開した版ごとのサンプルを見分けるため)。
#   サンプルを直したら、直したファイルの行を足す (公開した版の行は消さない)。src/ で:
#     sha256sum <直したファイル> >> ../scripts/lib/sample-files.sha256   (足したら --check で確かめる)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

LIST="scripts/lib/sample-files.sha256"
ROOT="src"
MODE="remove"

usage() {
    cat <<'EOF'
使い方: bash scripts/remove-sample.sh [--dry-run | --check] [--input <dir>]

src/ に同梱したサンプル論文のファイルのうち、中身がサンプルと同じものだけを消す。
書き換えたファイル・同じ名前の自分のファイルは消さない (何度回しても自分のファイルは消えない)。

オプション:
  --dry-run       消すもの・残すものの一覧だけを出す (何も消さない)
  --input <dir>   src/ ではなく <dir> を見る (サンプルを別の場所に写したとき)
  --check         (保守用) サンプルの一覧 (scripts/lib/sample-files.sha256) が今の入力ルートの中身と
                  合っているかを確かめる。合わなければ終了コード 1
  -h, --help      この説明を出す
EOF
}

while [ $# -gt 0 ]; do
    case "$1" in
        --dry-run) MODE="dry-run"; shift ;;
        --check)   MODE="check"; shift ;;
        --input)   ROOT="${2:?--input にディレクトリを指定してください}"; shift 2 ;;
        -h|--help) usage; exit 0 ;;
        *)         echo "エラー: 不明な引数 '$1'" >&2; usage >&2; exit 1 ;;
    esac
done

if [ ! -f "$LIST" ]; then
    echo "エラー: サンプルの一覧 $LIST がありません。" >&2
    exit 1
fi
if [ ! -d "$ROOT" ]; then
    echo "エラー: $ROOT/ がありません。" >&2
    exit 1
fi

if command -v sha256sum >/dev/null 2>&1; then
    hash_of() { sha256sum < "$1" | cut -d' ' -f1; }
elif command -v shasum >/dev/null 2>&1; then
    hash_of() { shasum -a 256 < "$1" | cut -d' ' -f1; }
else
    echo "エラー: sha256sum も shasum もありません (ファイルの中身を確かめられないので、何も消しません)。" >&2
    exit 1
fi

# 一覧を読んで、行の形を確かめる
paths=()       # 一覧のパス (重複を除いて一覧の順)
n_entries=0
while read -r sha rel || [ -n "${sha:-}" ]; do
    case "$sha" in ''|'#'*) continue ;; esac
    # 一覧の行は「入力ルートからの相対パス」だけを受け付ける (外を指す行で入力ルートの外を消さないため)
    case "$rel" in
        ''|/*|../*|*/../*|*/..|..)
            echo "エラー: $LIST の行のパスが不正です: '$rel'" >&2
            exit 1 ;;
    esac
    if ! [[ "$sha" =~ ^[0-9a-f]{64}$ ]]; then
        echo "エラー: $LIST の行の SHA-256 が不正です: '$sha'" >&2
        exit 1
    fi
    n_entries=$((n_entries + 1))
    seen=0
    for q in ${paths[@]+"${paths[@]}"}; do
        [ "$q" = "$rel" ] && seen=1
    done
    [ "$seen" -eq 1 ] || paths+=("$rel")
done < "$LIST"

if [ "$n_entries" -eq 0 ]; then
    echo "エラー: サンプルの一覧 $LIST に行がありません。" >&2
    exit 1
fi

matched=()     # 中身がサンプルと一致するファイル (消す対象)
kept=()        # 同じパスにあるが中身が違うファイル (残す)
absent=()      # 一覧にあるが無いファイル
for rel in "${paths[@]}"; do
    f="$ROOT/$rel"
    # 消すのは通常のファイルだけ (リンクはリンクの先が自分のファイルかもしれないので触らない)
    if [ -f "$f" ] && [ ! -L "$f" ]; then
        h="$(hash_of "$f")"
        if awk -v p="$rel" -v h="$h" '$1 == h && $2 == p { found = 1 } END { exit !found }' "$LIST"; then
            matched+=("$rel")
        else
            kept+=("$rel")
        fi
    elif [ -e "$f" ] || [ -L "$f" ]; then
        kept+=("$rel")
    else
        absent+=("$rel")
    fi
done

if [ "$MODE" = "check" ]; then
    if [ "${#kept[@]}" -eq 0 ] && [ "${#absent[@]}" -eq 0 ]; then
        echo "一覧 ($LIST) は $ROOT/ のサンプル ${#paths[@]} ファイルと一致します。"
        exit 0
    fi
    echo "一覧 ($LIST) が $ROOT/ と合っていません (サンプルを直したら、直したファイルの行を一覧に足してください):" >&2
    for rel in ${kept[@]+"${kept[@]}"}; do echo "  中身が違う: $ROOT/$rel" >&2; done
    for rel in ${absent[@]+"${absent[@]}"}; do echo "  無い:       $ROOT/$rel" >&2; done
    exit 1
fi

if [ "$MODE" = "dry-run" ]; then
    echo "== サンプルのファイルの一覧 ($ROOT/。--dry-run なので何も消しません) =="
else
    echo "== サンプルのファイルを消します ($ROOT/) =="
fi
for rel in ${matched[@]+"${matched[@]}"}; do
    if [ "$MODE" = "dry-run" ]; then
        echo "  消す:   $ROOT/$rel"
    else
        rm -f -- "$ROOT/$rel"
        echo "  消した: $ROOT/$rel"
    fi
done
for rel in ${kept[@]+"${kept[@]}"}; do
    if [ "$MODE" = "dry-run" ]; then
        echo "  残す:   $ROOT/$rel (中身がサンプルと違うので、あなたのファイルとみなします)"
    else
        echo "  残した: $ROOT/$rel (中身がサンプルと違うので、あなたのファイルとみなしました)"
    fi
done
if [ "${#matched[@]}" -eq 0 ]; then
    echo "  消すファイルはありません (サンプルのファイルは残っていません)。"
fi

# 中身が空になった supplementary/ は消す (補足資料が無い論文で、空のフォルダを残さないため)
supp="$ROOT/supplementary"
if [ "$MODE" = "remove" ] && [ -d "$supp" ] && [ ! -L "$supp" ] && [ -z "$(ls -A "$supp")" ]; then
    rmdir "$supp"
    echo "  消した: $supp/ (空になったため)"
fi

if [ "$MODE" = "remove" ] && [ "${#matched[@]}" -gt 0 ]; then
    echo ""
    echo "サンプルから作った生成物 (data/step01_figures/・data/step02_build/・data/step03_diff/・data/output/<誌>/) は残っています。"
    echo "自分の原稿で build・diff・package を回すと作り直されます (要らなければ消してかまいません)。"
fi
