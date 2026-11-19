# ensure-reference.sh — 使う直前に reference.docx が無ければ make-reference.sh で生成する
#
# ⚠ これは実行スクリプトではなく、source されるライブラリである。
#   利用側: scripts/build.sh, scripts/diff.sh
#   (scripts/package.sh は reference.docx を使わない。--build のときは build.sh を経由する)
#
# なぜ要るか: reference.docx は pandoc の既定 reference.docx に profile.yaml の体裁を焼き込んだ
#   生成物で、data/journals/make-reference.sh が何度回しても同じものを作る (zip の時刻を固定して
#   いるのでバイト単位で同じ)。生成物を置いていない作業ツリー (clone した直後など) でも build と
#   diff がそのまま通るよう、ここで作る。
#
# 生成するのは次の 2 つだけ:
#   - data/journals/_default/reference.docx (どの誌でも、継承するときの受け皿になる)
#   - 対象誌の profile.yaml の reference_doc が "reference.docx" (make-reference.sh が書く名前) で、
#     そのファイルが無いときの data/journals/<id>/reference.docx
#   reference_doc が別の名前 (雑誌が配るテンプレートなど) を指していて、そのファイルが無いときは
#   生成しない。人が置くファイルを作り物で黙って置き換えないためで、build の警告に任せる。
#
# 前提: PROJECT_ROOT に cd してから source すること。呼び出し側は `set -euo pipefail` を前提とする
#   (生成に失敗したらその場で止まる)。

# make-reference.sh を回す。標準出力は捨てる (最後の「reference_doc を切り替えると…」の案内は
# 手で新しい誌を足すときのもので、ここでは当てはまらない)。エラーは標準エラーに出る。
_ensure_reference_make() {
    echo "-- data/journals/$1/reference.docx が無いので生成します (bash data/journals/make-reference.sh $1)"
    bash data/journals/make-reference.sh "$1" >/dev/null
}

# ensure_reference_docx <journal-id>
ensure_reference_docx() {
    local journal="$1" want
    if [ ! -f "data/journals/_default/reference.docx" ]; then
        _ensure_reference_make _default
    fi
    if [ "$journal" = "_default" ] || [ -f "data/journals/$journal/reference.docx" ]; then
        return 0
    fi
    # 対象誌が自前の reference.docx を使う設定かは profile.yaml を読まないと分からない。
    # 読み方は build と同じ journal_profile に任せる (YAML を sed で読むと引用符やコメントで外れる)。
    # コンテナを 1 回起こすのはファイルが無いときだけ。
    want="$(docker compose -f docker/docker-compose.yml run --rm -T -u "$(id -u):$(id -g)" pandoc \
        python3 -c 'import sys
sys.path.insert(0, "main/00_setup/lib")
import journal_profile
print(journal_profile.load(sys.argv[1]).get("reference_doc") or "")' "$journal")"
    if [ "$want" = "reference.docx" ]; then
        _ensure_reference_make "$journal"
    fi
}
