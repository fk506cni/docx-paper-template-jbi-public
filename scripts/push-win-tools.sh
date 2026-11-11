#!/usr/bin/env bash
# push-win-tools.sh — Windows 側の PDF 変換ツール（bat/ps1）を Google Drive へ送る
#
# 目的: docx → PDF は LibreOffice ではテキストボックスを忠実に描画できず、Windows 上の
#   Microsoft Word (Word COM) でしか成立しない。その Windows 側で動かす 3 ファイルを
#   rclone で送出先フォルダへ送り、内容がローカルと一致することまで確かめる。
#
#   [Linux] 本スクリプト
#     → gdrive:tmp/<repo名>/ に watch-and-convert.ps1 / .bat / word-to-pdf.bat を配置
#       → [Windows] 同期フォルダで watch-and-convert.bat をダブルクリック（watcher 起動）
#         → 以後 ./scripts/roundtrip.sh が docx を送ると PDF が返ってくる
#
# 送出先は scripts/roundtrip.sh と完全に同一（scripts/lib/gdrive-dest.sh が唯一の定義）。
# 認証情報はスクリプトに含めず rclone 設定に委ねる。
#
# Usage:
#   ./scripts/push-win-tools.sh [OPTIONS]
# Options:
#   --dry-run       rclone を一切呼ばず予定のみ表示（live アップロードなし）
#   -h, --help      ヘルプ表示
# Env:
#   RCLONE_REMOTE      rclone リモート名（既定 gdrive:）
#   GDRIVE_BASE_PATH   ベースパス（既定 tmp）
#   GDRIVE_SUBDIR      サブフォルダ（既定なし＝ tmp/<repo名>/ 直下）

set -euo pipefail

# --- プロジェクトルート ---
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# ヘルプは cd の前に絶対パスを控えてから読む。cd の後に相対パスの $0 を読むと、
#   scripts/ の中から起動したとき自分自身を見つけられず、何も表示せず終了コード 2 で落ちる。
SCRIPT_SELF="$SCRIPT_DIR/$(basename "${BASH_SOURCE[0]}")"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

# --- ヘルプは lib の読み込みより前に処理する（lib が欠けていても使い方は読める）---
for _arg in "$@"; do
    case "$_arg" in
        -h|--help) sed -n '2,/^$/p' "$SCRIPT_SELF"; exit 0 ;;
    esac
done

# --- 送出先（roundtrip.sh と共有。二重定義しない）---
if [ ! -f "$SCRIPT_DIR/lib/gdrive-dest.sh" ]; then
    echo "[ERROR] scripts/lib/gdrive-dest.sh がありません（送出先を算出できません）" >&2
    exit 1
fi
# shellcheck source=lib/gdrive-dest.sh
. "$SCRIPT_DIR/lib/gdrive-dest.sh"

# --- 送るファイル（Windows 側 PDF 変換に必要な 3 点）---
# ⚠ Windows ツールは scripts/ ではなく main/step04_pdf/windows/ に置く
#   (CLAUDE.md「各ステップのコードは main/stepNN_name/」の規約に従う)。
WIN_TOOLS_DIR="main/step04_pdf/windows"
WIN_TOOLS=(
    "$WIN_TOOLS_DIR/watch-and-convert.ps1"   # 同期フォルダを監視し Word COM で docx→PDF
    "$WIN_TOOLS_DIR/watch-and-convert.bat"   # 上記 ps1 の起動用ランチャ（ダブルクリック）
    "$WIN_TOOLS_DIR/word-to-pdf.bat"         # 単発変換用（docx をドラッグ&ドロップ）
)

# --- フラグ ---
DRY_RUN=false

# --- ヘルパー（roundtrip.sh と同じ流儀）---
log_info()  { echo "[INFO]  $(date '+%H:%M:%S') $1"; }
log_warn()  { echo "[WARN]  $(date '+%H:%M:%S') $1"; }
log_error() { echo "[ERROR] $(date '+%H:%M:%S') $1" >&2; }
log_ok()    { echo "[OK]    $(date '+%H:%M:%S') $1"; }
separator() { echo "========================================"; }

# rclone を retry 付きで実行（Google Drive の一時的応答遅延に耐える）
RCLONE_MAX_RETRIES="${RCLONE_MAX_RETRIES:-3}"
RCLONE_RETRY_SLEEP="${RCLONE_RETRY_SLEEP:-5}"
# ⚠ この形を崩さないこと。`if timeout ...; then return 0; fi` の直後に `local rc=$?` を
#   置くと、**if 文は条件が偽で else が無いとき自身の終了コードとして 0 を返す**ため、
#   $? が拾うのはその 0 であって timeout の終了コードではない。結果、試行を使い切っても
#   常に成功(0)を返し、送出が全滅しても「push 完了」と表示して終了コード 0 で終わる。
#   roundtrip.sh / check-pdf-path.sh の同名関数と**完全に同じ形**にすること
#   （片方だけ直すと写し直されて戻る）。
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
        --dry-run)  DRY_RUN=true; shift ;;
        -h|--help)  sed -n '2,/^$/p' "$SCRIPT_SELF"; exit 0 ;;   # 通常は上で処理済み
        *)          log_error "不明なオプション: $1"; exit 1 ;;
    esac
done

# --- 送るファイルの存在確認（dry-run でも行う）---
check_sources() {
    local missing=0 f
    for f in "${WIN_TOOLS[@]}"; do
        if [[ -f "$f" ]]; then
            log_info "  ✓ $f ($(du -h "$f" | cut -f1))"
        else
            log_error "  ✗ $f が見つかりません"
            missing=$((missing + 1))
        fi
    done
    if [[ $missing -gt 0 ]]; then
        log_error "送るファイルが ${missing} 件不足しています"; exit 1
    fi
}

# --- 送出 ---
phase_push() {
    if [[ "$DRY_RUN" == true ]]; then
        log_info "(dry-run) 以下を push する予定:"
        local f
        for f in "${WIN_TOOLS[@]}"; do
            log_info "    ${f} → ${GDRIVE_DEST}/$(basename "$f")"
        done
        echo ""
        return 0
    fi

    if ! command -v rclone &>/dev/null; then
        log_error "rclone がインストールされていません"; exit 1
    fi
    if ! rclone_with_retry 60 rclone lsf "${GDRIVE_DEST}/" --max-depth 1 &>/dev/null; then
        # フォルダ未作成の可能性 → 作成を試す
        log_info "送出先が見つからないため作成します: ${GDRIVE_DEST}"
        rclone_with_retry 60 rclone mkdir "${GDRIVE_DEST}" || {
            log_error "rclone リモート '${GDRIVE_DEST}' に接続できません"
            log_error "  rclone config reconnect ${RCLONE_REMOTE} を試してください"; exit 1
        }
    fi

    # --include で 3 件を指定した 1 回の copy にまとめる。1 件ずつ copy すると、途中で
    # 止まったときに新しい .ps1 と古い .bat が混在しうる。
    local inc=() f
    for f in "${WIN_TOOLS[@]}"; do inc+=(--include "/$(basename "$f")"); done

    rclone_with_retry 120 rclone copy "$WIN_TOOLS_DIR/" "${GDRIVE_DEST}/" \
        "${inc[@]}" --stats-one-line -v
    log_ok "push: ${#WIN_TOOLS[@]} 件"

    # 名前の一覧だけでは古い版が残っていても気づけないので、rclone check で内容の一致まで
    # 検証し、合わなければ非 0 で終わる。
    log_info "送出内容を照合中 (rclone check)..."
    if ! rclone_with_retry 120 rclone check "$WIN_TOOLS_DIR/" "${GDRIVE_DEST}/" \
            "${inc[@]}" --one-way; then
        log_error "送出したファイルがローカルと一致しません: ${GDRIVE_DEST}"
        log_error "  再実行するか、rclone lsl ${GDRIVE_DEST}/ で状態を確認してください"
        exit 1
    fi
    log_ok "照合 OK: ${#WIN_TOOLS[@]} 件ともローカルと一致"

    echo ""
    log_info "送出先の内容:"
    rclone_with_retry 60 rclone lsf "${GDRIVE_DEST}/" --max-depth 1 || true
    echo ""
}

# --- Windows 側の操作手順 ---
print_windows_steps() {
    local win_path="${GDRIVE_BASE_PATH}/${PROJECT_DIRNAME}"
    [[ -n "$GDRIVE_SUBDIR" ]] && win_path="${win_path}/${GDRIVE_SUBDIR}"
    win_path="${win_path//\//\\}"

    separator
    echo "Windows 実機での操作（ここから先は人手）"
    separator
    echo ""
    echo "  1. Google Drive デスクトップの同期が終わるのを待つ"
    echo "     （エクスプローラで開く: <マイドライブ>\\${win_path}\\ ）"
    echo ""
    echo "  2. そのフォルダに次の 3 ファイルが見えることを確認する"
    for f in "${WIN_TOOLS[@]}"; do
        echo "       - $(basename "$f")"
    done
    echo ""
    echo "  3. watch-and-convert.bat をダブルクリックする"
    echo "     → PowerShell の窓が開き、フォルダの監視が始まる（閉じない）"
    echo "     ※ 初回は実行ポリシーの警告が出ることがある。bat が回避指定つきで"
    echo "        起動するため、通常はそのまま動く"
    echo ""
    echo "  4. Linux 側から docx を置くと、同名の PDF が同じフォルダに現れる"
    echo "     経路の診断: bash scripts/check-pdf-path.sh          （読み取りのみ・数秒）"
    echo "     往復の確認: bash scripts/check-pdf-path.sh --full   （docx を送って PDF を待つ）"
    echo ""
    echo "  5. 本番の往復:"
    echo "       bash scripts/roundtrip.sh --skip-build     # 既存 docx を集約して変換"
    echo "     BHI の提出体裁を見るときは先に集約元へ置く（docs/usage-guide.md §8.4）:"
    echo "       cp data/output/bhi/manuscript.docx data/step03_diff/bhi-manuscript.docx"
    echo ""
    echo ""
}

# ============================================================
# メイン
# ============================================================
echo ""
separator
log_info "push-win-tools: Windows 側 PDF 変換ツールを Google Drive へ送る"
[[ "$DRY_RUN" == true ]] && log_info "(dry-run モード: rclone 呼び出しなし)"
log_info "dest = ${GDRIVE_DEST}"
separator; echo ""

log_info "送るファイル (${#WIN_TOOLS[@]} 件):"
check_sources
echo ""

phase_push

if [[ "$DRY_RUN" == true ]]; then
    log_ok "dry-run 完了（何も送っていません）"
    echo ""
    # --dry-run は rclone を一切呼ばない仕様を保つため、rclone の有無も送出先への到達性も
    # 確かめていない。dry-run の成功は本番の成功を保証しない。
    if ! command -v rclone &>/dev/null; then
        log_warn "rclone が見つかりません。本番実行の前に導入してください"
    fi
    log_info "⚠ dry-run は送出先への到達性を確かめていません（rclone を呼ばない仕様のため）。"
    log_info "  到達性まで見る: ./scripts/check-pdf-path.sh"
    log_info "  本番実行:       ./scripts/push-win-tools.sh"
    echo ""
else
    log_ok "push 完了: ${GDRIVE_DEST}"
    echo ""
    print_windows_steps
fi
