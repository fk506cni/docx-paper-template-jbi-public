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
#     retrying=none | <次の周回でやり直している docx の「理由:回数」。例: ATTACHED:3,CHANGED:1>
#               (ATTACHED = 既に動いていた Word につながった / CHANGED = 変換中に docx が上書きされた。
#                watcher は同じ docx のやり直しの間隔を 5 → 10 → 20 → 40 → 60 秒に延ばす。ファイル名は書かない)
#     instance=<起動ごとの識別子 (乱数。コンピュータ名やユーザー名は使わない)>
#     log_write_failures=<watch-and-convert.log に書けなかった行の数>
#   watcher は同じ内容を、起動ごとの生存記録 .watcher-alive-<識別子> にも書く (終了時に消す)。
#   .watcher-alive は最後に書いた watcher の分しか残らないので、同じフォルダを複数の watcher が見ていても
#   見分けられない (古い版の watcher が残っていても、版の照合が「同じ版」で通りうる)。
#   起動ごとの記録を数えれば見分けられる (alive_instances_report)。
#   2 行目以降を持たない記録は、版と設定を書かない watcher (変換タイムアウトを持たない) が書いたもの。
#   retrying の行を持たない記録は、やり直しの状況を書かない watcher が書いたもの (警告はしない)。
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

# alive_retry_report <生存記録の全文>
#   watcher が docx を次の周回でやり直しているなら、その旨と対処を "WARN<TAB>本文" で出す (無ければ何も出さない)。
#   roundtrip.sh は PDF の待ちが打ち切りになったときにも読み直して出す (待っている理由が分かるように)。
alive_retry_report() {
    local retrying
    retrying="$(alive_meta_value "$1" retrying)"
    [[ -z "$retrying" || "$retrying" == "none" ]] && return 0
    printf 'WARN\t%s\n' "watcher が docx を次の周回でやり直しています (理由:回数 = ${retrying})"
    if [[ "$retrying" == *ATTACHED* ]]; then
        printf 'WARN\t%s\n' "  → ATTACHED が続くなら、Windows でウィンドウの無い WINWORD.EXE をタスクマネージャで終了する (watcher が止める相手を特定できずに残した Word)"
    fi
    if [[ "$retrying" == *CHANGED* ]]; then
        printf 'WARN\t%s\n' "  → CHANGED が続くなら、Google Drive の同期が docx を書き換え続けていないかを確かめる"
    fi
    return 0
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
        printf 'WARN\t%s\n' "生存記録に watcher の版と設定がありません (版と設定を書かない watcher が動いている。push-win-tools.sh で送り直して起動し直すこと)"
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

    alive_retry_report "$content"

    if [[ -n "$timeout" ]]; then
        printf 'INFO\t%s\n' "1 ファイルあたりの変換タイムアウト: ${timeout} 秒"
    fi

    local lwf
    lwf="$(alive_meta_value "$content" log_write_failures)"
    if [[ -n "$lwf" && "$lwf" != "0" ]]; then
        printf 'WARN\t%s\n' "watcher が watch-and-convert.log に ${lwf} 行を書けませんでした (同期クライアントか別の watcher がログを掴んでいた。ログの欠けに注意)"
    fi
}

# alive_instances_report <stale_sec>
#   標準入力に送出先の `rclone lsl --include '.watcher-alive-*' --max-depth 1` の出力 (「サイズ 日付 時刻 名前」) を受け、
#   更新が stale_sec 秒以内の起動ごとの生存記録を数えて、判定を "LEVEL<TAB>本文" で出す。
#   2 個以上 = 同じフォルダを複数の watcher が見ている (別の PC で動かしたままのものを含む)。
#   watcher は同じ PC の 2 つ目の起動を断るが、別の PC の分はこれでしか分からない。
alive_instances_report() {
    local stale="$1" now n=0 old=0 names="" size d t name ep
    now="$(date +%s)"
    while read -r size d t name; do
        [[ "$name" == .watcher-alive-* ]] || continue
        ep="$(date -d "$d ${t%%.*}" +%s 2>/dev/null)" || continue
        if (( now - ep <= stale )); then
            n=$((n + 1))
            names="${names:+$names, }${name#.watcher-alive-}"
        else
            old=$((old + 1))
        fi
    done
    if (( n >= 2 )); then
        printf 'WARN\t%s\n' "watcher が ${n} 個動いています (起動ごとの生存記録: ${names})。同じフォルダを複数の watcher が見ると、同じ docx を二重に変換し、生存記録の版の照合もログも当てにならない"
        printf 'WARN\t%s\n' "  → Windows で watcher の窓をすべて閉じ (別の PC で動かしたままのものにも注意)、watch-and-convert.bat を 1 回だけ起動する"
    elif (( n == 1 )); then
        printf 'OK\t%s\n' "動いている watcher は 1 個 (起動ごとの生存記録 ${names})"
    else
        printf 'INFO\t%s\n' "起動ごとの生存記録 (.watcher-alive-*) が新しいものはありません (起動ごとの記録を書かない版の watcher が動いているか、watcher が止まっている)"
    fi
    if (( old > 0 )); then
        printf 'INFO\t%s\n' "古い起動ごとの生存記録が ${old} 個あります (落ちた watcher の残り。watcher が次の起動で消す)"
    fi
    return 0
}
