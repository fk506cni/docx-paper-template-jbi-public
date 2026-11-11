#!/usr/bin/env bash
# check-pdf-path.sh — Windows PDF 変換経路が生きているかを診断する
#
# 背景: Windows 側の変換は、手でダブルクリックして開いた PowerShell の窓が閉じるまでしか
#   動かない。窓が今も開いているかを Linux 側から確かめる手段が無いと、Windows の前に座って
#   いる人以外は経路の健全性を確認できず、roundtrip.sh の 10 分のタイムアウトを待って初めて
#   止まっていたと分かる。そこで、待つ前に状態が分かるようにする。
#
# 既定では **読み取りだけ**を行う（Drive の内容を変えない・数秒で終わる）。
#   1. rclone があるか
#   2. 送出先に到達できるか
#   3. Windows 側 3 ファイルが揃い、ローカルと一致するか（rclone check）
#   4. 監視スクリプトの生存記録 .watcher-alive が新しいか。あわせて、実行中の watcher が
#      ローカルの watch-and-convert.ps1 と同じ版か・試験用の起動引数のままでないか
#      (生存記録の 2 行目以降。読み方は scripts/lib/watcher-alive.sh)
#   5. --full のときだけ docx を送って PDF の往復まで確かめる
#
# Usage:
#   ./scripts/check-pdf-path.sh [OPTIONS]
# Options:
#   --full          docx を送って PDF が返るまで確かめる（Drive に書き込む）
#   --docx PATH     --full で送る docx（既定 data/step02_build/main.docx）
#   --wait SEC      --full の待ち時間（既定 300 秒）
#   --stale SEC     生存記録をこの秒数より古いと「停止の疑い」とする（既定 300 秒）
#   -h, --help      ヘルプ表示
# Env:
#   RCLONE_REMOTE      rclone リモート名（既定 gdrive:）
#   GDRIVE_BASE_PATH   ベースパス（既定 tmp）
#   GDRIVE_SUBDIR      サブフォルダ（既定なし＝ tmp/<repo名>/ 直下）

set -euo pipefail

# --- プロジェクトルート ---
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPT_SELF="$SCRIPT_DIR/$(basename "${BASH_SOURCE[0]}")"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

# --- ヘルプは lib の読み込みより前に処理する（push-win-tools.sh と同じ流儀）---
for _arg in "$@"; do
    case "$_arg" in
        -h|--help) sed -n '2,/^$/p' "$SCRIPT_SELF"; exit 0 ;;
    esac
done

# --- 送出先（roundtrip.sh / push-win-tools.sh と共有。二重定義しない）---
if [ ! -f "$SCRIPT_DIR/lib/gdrive-dest.sh" ]; then
    echo "[ERROR] scripts/lib/gdrive-dest.sh がありません（送出先を算出できません）" >&2
    exit 1
fi
# shellcheck source=lib/gdrive-dest.sh
. "$SCRIPT_DIR/lib/gdrive-dest.sh"
# 生存記録の 2 行目以降 (watcher の版と設定) の読み方 (check-pdf-path.sh / roundtrip.sh で共有)
if [ ! -f "$SCRIPT_DIR/lib/watcher-alive.sh" ]; then
    echo "[ERROR] scripts/lib/watcher-alive.sh がありません" >&2
    exit 1
fi
# shellcheck source=lib/watcher-alive.sh
. "$SCRIPT_DIR/lib/watcher-alive.sh"

# --- Windows 側に置かれているべきファイル（push-win-tools.sh と同じ 3 点）---
# ⚠ Windows ツールは scripts/ ではなく main/step04_pdf/windows/ に置く
#   (CLAUDE.md「各ステップのコードは main/stepNN_name/」の規約)。rclone check の比較元もここ。
WIN_TOOLS_DIR="main/step04_pdf/windows"
WIN_TOOLS=(
    "$WIN_TOOLS_DIR/watch-and-convert.ps1"
    "$WIN_TOOLS_DIR/watch-and-convert.bat"
    "$WIN_TOOLS_DIR/word-to-pdf.bat"
)
ALIVE_NAME=".watcher-alive"

# --- フラグ ---
FULL=false
# --full で送る docx の既定はビルド成果。
# 無ければ --docx PATH で指定するか、先に bash scripts/build.sh を回すこと。
DOCX="data/step02_build/main.docx"
WAIT_SEC=300
STALE_SEC=300

# --- ヘルパー（roundtrip.sh と同じ流儀）---
log_info()  { echo "[INFO]  $(date '+%H:%M:%S') $1"; }
log_warn()  { echo "[WARN]  $(date '+%H:%M:%S') $1"; }
log_error() { echo "[ERROR] $(date '+%H:%M:%S') $1" >&2; }
log_ok()    { echo "[OK]    $(date '+%H:%M:%S') $1"; }
separator() { echo "========================================"; }

# 数値の引数は正の整数だけを受け付ける (0・負数・小数・空・次のオプション名を弾く)。
#   検査が無いと `set -u` の「未割り当ての変数です」で落ちるか、0 のまま進んで即座に打ち切る。
require_posint() {
    local opt="$1" val="${2-}"
    if [[ ! "$val" =~ ^[1-9][0-9]{0,5}$ ]]; then
        log_error "${opt} には正の整数を指定してください (指定値: '${val}')"
        exit 1
    fi
}

RCLONE_MAX_RETRIES="${RCLONE_MAX_RETRIES:-3}"
RCLONE_RETRY_SLEEP="${RCLONE_RETRY_SLEEP:-5}"
# roundtrip.sh / push-win-tools.sh と完全に同じ形（崩してはならない理由は roundtrip.sh の同名関数のコメント）
rclone_with_retry() {
    local to="$1"; shift
    local attempt=1 rc=0
    while :; do
        rc=0
        timeout "$to" "$@" || rc=$?
        if [[ $rc -eq 0 ]]; then
            return 0
        fi
        if [[ $attempt -ge $RCLONE_MAX_RETRIES ]]; then
            return $rc
        fi
        log_warn "rclone 実行失敗 (exit $rc, try $attempt/$RCLONE_MAX_RETRIES)。${RCLONE_RETRY_SLEEP}秒後に再試行"
        sleep "$RCLONE_RETRY_SLEEP"
        attempt=$((attempt + 1))
    done
}

# --- 引数解析 ---
while [[ $# -gt 0 ]]; do
    case $1 in
        --full)     FULL=true; shift ;;
        --docx)     [[ -n "${2-}" ]] || { log_error "--docx には送る docx のパスを指定してください"; exit 1; }
                    DOCX="$2"; shift 2 ;;
        --wait)     require_posint "$1" "${2-}"; WAIT_SEC="$2"; shift 2 ;;
        --stale)    require_posint "$1" "${2-}"; STALE_SEC="$2"; shift 2 ;;
        -h|--help)  sed -n '2,/^$/p' "$SCRIPT_SELF"; exit 0 ;;
        *)          log_error "不明なオプション: $1"; exit 1 ;;
    esac
done

FAILED=0
WARNED=0
fail() { log_error "$1"; FAILED=$((FAILED + 1)); }
warn() { log_warn "$1"; WARNED=$((WARNED + 1)); }

echo ""
separator
log_info "check-pdf-path: Windows PDF 変換経路の診断"
log_info "dest = ${GDRIVE_DEST}"
[[ "$FULL" == true ]] && log_info "(--full: docx の往復まで確認する)"
separator; echo ""

# ============================================================
# 1. rclone があるか
# ============================================================
log_info "[1/5] rclone の確認"
if ! command -v rclone &>/dev/null; then
    fail "rclone がインストールされていません"
    echo ""; log_error "以降の確認は行えません"; exit 1
fi
log_ok "  rclone: $(rclone version 2>/dev/null | head -1)"
echo ""

# ============================================================
# 2. 送出先に到達できるか
# ============================================================
log_info "[2/5] 送出先への到達"
if ! rclone_with_retry 60 rclone lsf "${GDRIVE_DEST}/" --max-depth 1 &>/dev/null; then
    fail "送出先に到達できません: ${GDRIVE_DEST}"
    log_error "  ① rclone config reconnect ${RCLONE_REMOTE} を試す"
    log_error "  ② 送出先が正しいか確認する（repo のディレクトリ名から決まるため、別名の clone では変わる）"
    echo ""; log_error "以降の確認は行えません"; exit 1
fi
log_ok "  到達 OK: ${GDRIVE_DEST}"
echo ""

# ============================================================
# 3. Windows 側 3 ファイルの存在と一致
# ============================================================
log_info "[3/5] Windows 側ツール ${#WIN_TOOLS[@]} 件の照合"
inc=(); for f in "${WIN_TOOLS[@]}"; do inc+=(--include "/$(basename "$f")"); done
remote_list="$(rclone_with_retry 60 rclone lsf "${GDRIVE_DEST}/" --max-depth 1 --files-only)" \
    || remote_list=""
remote_list="$(printf '%s\n' "$remote_list" | sort -u)"

missing=0
for f in "${WIN_TOOLS[@]}"; do
    if printf '%s\n' "$remote_list" | grep -qx "$(basename "$f")"; then
        log_ok "  ✓ $(basename "$f")"
    else
        fail "  ✗ $(basename "$f") が送出先にありません"
        missing=$((missing + 1))
    fi
done
if [[ $missing -gt 0 ]]; then
    log_error "  → bash scripts/push-win-tools.sh を実行してください"
else
    # 内容まで一致しているか（名前だけでは古い版が置かれていても気づけない）
    if rclone_with_retry 120 rclone check "$WIN_TOOLS_DIR/" "${GDRIVE_DEST}/" "${inc[@]}" --one-way &>/dev/null; then
        log_ok "  内容もローカルと一致（rclone check --one-way）"
    else
        warn "  送出先のツールがローカルと一致しません（古い版が置かれている可能性）"
        log_warn "  → bash scripts/push-win-tools.sh で送り直してください"
    fi
fi
echo ""

# ============================================================
# 4. 監視スクリプトの生存記録
# ============================================================
log_info "[4/5] 監視スクリプトの稼働（${ALIVE_NAME}）"
alive_full="$(rclone_with_retry 60 rclone cat "${GDRIVE_DEST}/${ALIVE_NAME}" 2>/dev/null)" || alive_full=""
alive_raw="$(printf '%s' "$alive_full" | tr -d '\r' | head -1)"

if [[ -z "${alive_raw//[[:space:]]/}" ]]; then
    warn "  生存記録がありません"
    log_warn "  考えられる原因は 2 つあります:"
    log_warn "    ① 生存記録に未対応の古い watch-and-convert.ps1 が動いている"
    log_warn "       → bash scripts/push-win-tools.sh で送り直し、Windows 側で watcher を再起動する"
    log_warn "    ② watcher が起動していない"
    log_warn "       → 同期フォルダで watch-and-convert.bat をダブルクリックする"
    log_warn "  ⚠ どちらであるかは、この診断だけでは区別できません。"
    log_warn "     確実に確かめるには --full を付けて docx の往復を試してください。"
else
    alive_epoch="$(date -d "$alive_raw" +%s 2>/dev/null || echo "")"
    if [[ -z "$alive_epoch" ]]; then
        warn "  生存記録を読めませんでした（内容: ${alive_raw}）"
    else
        age=$(( $(date +%s) - alive_epoch ))
        if [[ $age -lt 0 ]]; then age=0; fi
        if [[ $age -le $STALE_SEC ]]; then
            log_ok "  稼働中（${age} 秒前に更新。しきい値 ${STALE_SEC} 秒）"
        else
            fail "  停止の疑い（${age} 秒前が最後の更新。しきい値 ${STALE_SEC} 秒）"
            log_error "  → Windows 側で watch-and-convert.bat を起動し直してください"
            log_error "     （Google Drive の同期遅延でも古く見えることがあります）"
        fi
    fi
    # 実行中の watcher の版と設定（生存記録の 2 行目以降）
    while IFS=$'\t' read -r lv msg; do
        case "$lv" in
            OK)   log_ok "  $msg" ;;
            WARN) warn "  $msg" ;;
            *)    log_info "  $msg" ;;
        esac
    done < <(alive_meta_report "$alive_full")
fi
echo ""

# ============================================================
# 5. docx → PDF の往復（--full のときだけ）
# ============================================================
log_info "[5/5] docx → PDF の往復"
if [[ "$FULL" != true ]]; then
    log_info "  (--full 未指定のため省略。確実に確かめるには --full を付ける)"
else
    if [[ ! -f "$DOCX" ]]; then
        fail "  送る docx がありません: $DOCX"
    else
        stem="$(basename "$DOCX")"; stem="${stem%.docx}"
        pdf="${stem}.pdf"
        log_info "  送信: $DOCX ($(du -h "$DOCX" | cut -f1)) → ${GDRIVE_DEST}/"

        # 同名の古い PDF があると誤検知するので先に退避する（roundtrip.sh と同じ考え方）
        ts="$(date '+%Y%m%d_%H%M%S')"
        old="$(rclone_with_retry 60 rclone lsf "${GDRIVE_DEST}" --include "${pdf}" \
            --max-depth 1 --files-only)" || old=""
        if [[ -n "${old//[[:space:]]/}" ]]; then
            log_info "  古い ${pdf} を __archives/ へ退避..."
            rclone mkdir "${GDRIVE_DEST}/__archives" 2>/dev/null || true
            if ! timeout 60 rclone moveto "${GDRIVE_DEST}/${pdf}" \
                    "${GDRIVE_DEST}/__archives/${stem}_${ts}.pdf" >/dev/null 2>&1; then
                fail "  古い ${pdf} の退避に失敗しました。誤検知を避けるため中止します"
                echo ""; separator; log_error "診断: 失敗 ${FAILED} 件 / 警告 ${WARNED} 件"; separator
                exit 1
            fi
        fi

        rclone_with_retry 300 rclone copyto "$DOCX" "${GDRIVE_DEST}/${stem}.docx" --stats-one-line -v
        log_ok "  送信完了。PDF を最大 ${WAIT_SEC} 秒待ちます..."

        deadline=$((SECONDS + WAIT_SEC)); found=false; t0=$SECONDS
        while [[ $SECONDS -lt $deadline ]]; do
            if rclone_with_retry 60 rclone lsf "${GDRIVE_DEST}" --include "${pdf}" \
                    --max-depth 1 --files-only 2>/dev/null | grep -q .; then
                found=true; break
            fi
            printf "\r  待機中... (%d 秒経過)  " "$((SECONDS - t0))"
            sleep 10
        done
        echo ""

        if [[ "$found" == true ]]; then
            log_ok "  PDF を検出: ${pdf}（$((SECONDS - t0)) 秒）"
            log_info "  後片付け: ${pdf} を __archives/ へ退避"
            rclone mkdir "${GDRIVE_DEST}/__archives" 2>/dev/null || true
            timeout 60 rclone moveto "${GDRIVE_DEST}/${pdf}" \
                "${GDRIVE_DEST}/__archives/${stem}_${ts}_check.pdf" >/dev/null 2>&1 \
                || log_warn "  後片付けに失敗しました（${pdf} が残っています）"
            log_ok "  経路は生きています"
        else
            fail "  ${WAIT_SEC} 秒待っても ${pdf} が現れませんでした"
            log_error "  → Windows 側で watch-and-convert.bat が起動しているか確認してください"
            log_error "     送出先: ${GDRIVE_DEST}"
        fi
    fi
fi
echo ""

# ============================================================
# 判定
# ============================================================
separator
if [[ $FAILED -gt 0 ]]; then
    log_error "診断: 失敗 ${FAILED} 件 / 警告 ${WARNED} 件 — 経路は使えない可能性が高い"
    separator; echo ""
    exit 1
elif [[ $WARNED -gt 0 ]]; then
    log_warn "診断: 失敗 0 件 / 警告 ${WARNED} 件 — 上の警告を確認してください"
    separator; echo ""
    exit 0
else
    log_ok "診断: 問題なし"
    [[ "$FULL" != true ]] && log_info "（往復まで確かめるには --full を付けてください）"
    separator; echo ""
    exit 0
fi
