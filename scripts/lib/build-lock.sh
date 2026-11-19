# scripts/lib/build-lock.sh — 同じ作業ツリーでの build / diff / package の同時実行を止める (source して使う)
#
# build と diff は data/step01_figures/ (図の前処理) と data/step02_build/ を作り直し、package はそれを読んで
# data/step05_package/ と data/output/ を書く。2 つが同時に走ると、記録と main.docx が一致したまま別の原稿の図が
# 入りうる (build の最中の diff は step01 を作り直し、図の前処理の最中の package は図 0 枚のまま終了コード 0 になりうる)。
# 3 つとも同じロックを排他で取る (package どうしも data/output/ を取り合うため)。
# ロックはプロセスが終われば外れる (割り込みや終了の合図でも残らない)。roundtrip.sh は fd 9 を自分のロックに
# 使うので、ここでは fd 8 を使う。package.sh --build は build.sh を回し終えてからロックを取る (入れ子にしない)。
#
# 使い方: . scripts/lib/build-lock.sh; take_build_lock <スクリプト名>   (作業ディレクトリはリポジトリのルート)

take_build_lock() {
    local who="$1" dir="data/step02_build"
    mkdir -p "$dir"
    if ! command -v flock >/dev/null 2>&1; then
        echo "  警告: flock が無いので、同じ作業ツリーでの build / diff / package の同時実行を止められません。" \
             "同時に回さないでください。" >&2
        return 0
    fi
    exec 8>"$dir/.build.lock"
    if ! flock -n 8; then
        echo "エラー: 同じ作業ツリーで別の build / diff / package が実行中です ($dir/.build.lock)。" \
             "終わってから $who を回してください。" >&2
        exit 1
    fi
}
