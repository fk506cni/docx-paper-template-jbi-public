# gdrive-dest.sh — Google Drive 送出先（GDRIVE_DEST）の算出【唯一の定義】
#
# ⚠ これは実行スクリプトではなく、source されるライブラリである。
#   利用側: scripts/roundtrip.sh, scripts/push-win-tools.sh, scripts/check-pdf-path.sh
#
# なぜ 1 か所か: 3 本がそれぞれ送出先を算出すると、GDRIVE_SUBDIR の規約を変えたときに
#   どれかが取り残される。**送出先のずれはビルドの成否に現れず、「Windows 側で PDF が
#   出ない」という形でしか露見しない**。そのため算出はここにだけ書く。
#
# 前提: source する前に PROJECT_ROOT を設定しておくこと。
# 出力: RCLONE_REMOTE / GDRIVE_BASE_PATH / GDRIVE_SUBDIR / PROJECT_DIRNAME / GDRIVE_DEST
#
# ⚠ 呼び出し側は `set -euo pipefail` を前提とする。
#   下の PROJECT_ROOT 未設定チェックは `return 1 2>/dev/null || exit 1` で、
#   ・`set -e` の下で source した場合 → エラー表示して終了コード 1 で止まる
#   ・直接実行した場合                 → 同上
#   ・`. lib/gdrive-dest.sh || exit 1`  → 戻り値 1 を呼び出し側が受け取れる
#   のいずれでも意図どおり動く。ただし **`set -e` が無く、かつ戻り値も見ない**呼び出し方では
#   エラー表示の後も処理が続き、GDRIVE_DEST が未設定のまま進む。その形で使わないこと。
#
# 既定値では GDRIVE_DEST = gdrive:tmp/<repo 名>/ となる。
# ⚠ <repo 名> は作業ツリーのディレクトリ名なので、別名で clone すると送出先も変わる。
#   Windows 側の同期フォルダ（watcher を置く場所）もそれに合わせること。
# 認証情報はここに書かない。rclone 設定に委ねる。

if [ -z "${PROJECT_ROOT:-}" ]; then
    echo "[ERROR] gdrive-dest.sh: PROJECT_ROOT が未設定です（source する前に設定すること）" >&2
    return 1 2>/dev/null || exit 1
fi

# --- 設定（env で上書き可）---
RCLONE_REMOTE="${RCLONE_REMOTE:-gdrive:}"
GDRIVE_BASE_PATH="${GDRIVE_BASE_PATH:-tmp}"
PROJECT_DIRNAME="$(basename "$PROJECT_ROOT")"            # 例: docx-paper-template-jbi-public
# Windows watcher を置くフォルダ。既定はリポジトリ直下 tmp/<repo>/（サブフォルダなし）。
# 別フォルダにしたい場合は GDRIVE_SUBDIR=roundtrip 等を env で指定する。
GDRIVE_SUBDIR="${GDRIVE_SUBDIR:-}"
if [ -n "$GDRIVE_SUBDIR" ]; then
    GDRIVE_DEST="${RCLONE_REMOTE}${GDRIVE_BASE_PATH}/${PROJECT_DIRNAME}/${GDRIVE_SUBDIR}"
else
    GDRIVE_DEST="${RCLONE_REMOTE}${GDRIVE_BASE_PATH}/${PROJECT_DIRNAME}"
fi
