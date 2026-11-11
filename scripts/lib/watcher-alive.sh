# watcher-alive.sh — watcher の生存記録 (.watcher-alive) の 2 行目以降を読む【唯一の定義】
#
# ⚠ これは実行スクリプトではなく、source されるライブラリである。
#   利用側: scripts/check-pdf-path.sh, scripts/roundtrip.sh
#
# 生存記録の形式 (main/step04_pdf/windows/watch-and-convert.ps1 が 60 秒ごとに書く。CRLF):
#   1 行目   時刻 (ISO 8601)。稼働の判定はこの行 (または更新時刻) で行う
#   2 行目〜 key=value
#     script_md5=<watcher が起動時に読んだ .ps1 の md5>
#     convert_timeout_sec=<1 ファイルあたりの変換タイムアウト (秒)>
#     nondefault=none | <起動引数で既定と違う設定。例: ConvertTimeoutSec=30,SimulateHang>
#   2 行目以降を持たない記録は、変換タイムアウトを持たない以前の watcher が書いたもの。
#
# なぜ md5 を見るか: 実行中の watcher はスクリプトをメモリに持ち続けるので、
#   push-win-tools.sh で Drive 上の .ps1 を差し替えても、窓を開き直すまで古い版が動く。
#   Drive 上のファイルの照合 (rclone check) だけでは、この「再起動忘れ」に気づけない。
# なぜ nondefault を見るか: 試験用の起動 (-SimulateHang など) のまま放置すると、
#   以後の変換がすべて打ち切られて error/ へ送られる。roundtrip.sh は待ちのタイムアウトで
#   初めて止まるので、待つ前に分かるようにする。
#
# 前提: source する前に PROJECT_ROOT を設定しておくこと (ローカルの .ps1 の md5 を取るため)。

WATCHER_PS1_LOCAL="main/step04_pdf/windows/watch-and-convert.ps1"

# alive_meta_value <生存記録の全文> <key>
#   key の値を出す (無ければ空)。
alive_meta_value() {
    printf '%s\n' "$1" | tr -d '\r' | sed -n "s/^$2=//p" | head -1
}

# alive_meta_report <生存記録の全文>
#   判定を 1 行ずつ "LEVEL<TAB>本文" で標準出力に出す (LEVEL = OK / INFO / WARN)。
#   ログの出し方と警告の数え方は呼び出し側に任せる。
alive_meta_report() {
    local content="$1" md5 timeout nondef local_md5
    md5="$(alive_meta_value "$content" script_md5)"
    timeout="$(alive_meta_value "$content" convert_timeout_sec)"
    nondef="$(alive_meta_value "$content" nondefault)"

    if [[ -z "$md5" && -z "$timeout" && -z "$nondef" ]]; then
        printf 'WARN\t%s\n' "生存記録に watcher の版と設定がありません (変換タイムアウトを持たない以前の watcher が動いている)"
        printf 'WARN\t%s\n' "  → bash scripts/push-win-tools.sh で送り、Windows 側で watcher の窓を閉じて watch-and-convert.bat を起動し直す"
        return 0
    fi

    local_md5="$(md5sum "$PROJECT_ROOT/$WATCHER_PS1_LOCAL" 2>/dev/null | cut -d' ' -f1)" || local_md5=""
    if [[ -z "$md5" || "$md5" == "unknown" ]]; then
        printf 'WARN\t%s\n' "watcher が自分の md5 を記録できなかったため、版を照合できません"
    elif [[ "$md5" == "$local_md5" ]]; then
        printf 'OK\t%s\n' "実行中の watcher はローカルの watch-and-convert.ps1 と同じ版 (md5 ${md5:0:12}…)"
    else
        printf 'WARN\t%s\n' "実行中の watcher はローカルの watch-and-convert.ps1 と別の版です (実行中 ${md5:-不明} / ローカル ${local_md5:-不明})"
        printf 'WARN\t%s\n' "  → push-win-tools.sh で送ったなら、watcher の窓を閉じて watch-and-convert.bat で起動し直す (実行中の watcher はスクリプトをメモリに持つ)"
        printf 'WARN\t%s\n' "    ローカルを編集したまま送っていないなら、先に bash scripts/push-win-tools.sh"
    fi

    if [[ -n "$nondef" && "$nondef" != "none" ]]; then
        printf 'WARN\t%s\n' "watcher が既定と違う起動引数で動いています: ${nondef}"
        printf 'WARN\t%s\n' "  → 試験用の起動のままなら、窓を閉じて watch-and-convert.bat で起動し直す"
    fi

    if [[ -n "$timeout" ]]; then
        printf 'INFO\t%s\n' "1 ファイルあたりの変換タイムアウト: ${timeout} 秒"
    fi
}
