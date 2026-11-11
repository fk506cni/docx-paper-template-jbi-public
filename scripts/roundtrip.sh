#!/usr/bin/env bash
# roundtrip.sh — build → Google Drive push → Windows で PDF 変換待ち → pull (step04)
#
# 目的: docx → PDF は最終体裁の再現性を最優先するため、Windows 上の Microsoft Word
#   (Word COM) でのみ行う。LibreOffice での PDF 化は採用しない (CLAUDE.md 設計確定事項)。
#   本スクリプトは Google Drive を中継して、その Word 変換を Linux から一括実行する。
#
#   [Linux] scripts/build.sh で docx 生成
#     → [Linux] docx を gdrive: の送出先フォルダへ push (rclone)
#       → [Windows] 同期フォルダで watch-and-convert.ps1 が docx を検知し
#                   Word COM で【同じフォルダに】同名 PDF を作る (docx は processed/ へ移動)
#         → [Linux] gdrive: に現れた PDF を検知して pull (data/products/ へ)
#           → [Linux] 提出パッケージを gdrive:<送出先>/submission-<journal>/ へ届ける (Phase 5)
#
# **提出パッケージの配送 (Phase 5)**。
#   投稿系 (ScholarOne) へ上げるファイルを Google Drive から選ぶ運用のため。Drive の processed/ には
#   watcher が変換を終えた docx が時刻付きの名前で並ぶだけなので、**草稿形の main_… と提出用の
#   bhi-manuscript_… を取り違えやすい**。そこで roundtrip の最後に、提出パッケージ data/output/<journal>/
#   (package.sh --mode final の出力) を **submission-<journal>/ という専用のサブフォルダ**へ置く。
#     - 中身はパッケージと完全に一致させる (rclone sync)。消えた・置き換わったファイルは
#       __archives/submission-<journal>_<時刻>/ へ退避する (削除はしない)。
#     - tables/ と figures/ の中身は 1 階層に並べる (ファイル選択の画面で一覧になるように)。
#       それ以外のサブフォルダ (supplementary/ など) はそのまま。
#     - 提出用本文と表 (manuscript.docx / tables/*.docx) は <journal>-manuscript.docx などの名前で
#       PDF 変換にも回す (Word で体裁を確かめるために手で一時コピーする必要は無い。docs/usage-guide.md §8.4)。
#     - watcher は送出先の【直下】の *.docx しか見ない (Get-ChildItem -File、再帰なし) ので、
#       サブフォルダの docx が変換・移動されることはない。
#   対象のパッケージ: 既定は data/output/*/SUBMISSION.md を持つもの全部 (= 提出マニフェストを書く誌。
#   既存 4 誌は持たないので従来どおり何も起きない)。--package <journal> で絞る / 明示、--no-package で止める。
#   **送る前に止める条件** (エラーで終了。何も送らない):
#     (a) SUBMISSION.md が「このパッケージは提出用ではない」(草稿モード / --keep-figures) と言っている
#     (b) パッケージより新しい原稿・ビルド・誌プロファイルがある (= パッケージが古い)。
#         作業ツリーに前の版のパッケージが残っていることはよくあり、黙って送ると、
#         それが「投稿用」として Drive に並ぶ
#
#   - PDF は【送出先フォルダの直下】に現れる (watcher が docx の隣に作る)。
#   - 送出先は gdrive:tmp/<repo 名>。算出は scripts/lib/gdrive-dest.sh が唯一の定義で、
#     push-win-tools.sh / check-pdf-path.sh と共有する。
#   - 待つ前に watcher の生存記録 (.watcher-alive) を見る。止まっていれば警告する
#     (止まったまま待つと、タイムアウトまで無言になるため)。
#   - 送出先に同じ名前の docx が残っていれば (前回の分が変換待ち・変換中) push しない。
#   - data/output/ に集めた docx は【何本でもまとめて】送り、全部の PDF が揃うまで待つ
#     (main / cover-letter / diff / 提出用 manuscript を一度に流す運用がある。
#     docs/usage-guide.md §8.4)。
#   配置・診断・既知の制限は docs/roundtrip-windows-watcher.md を参照。
#
# 事前準備 (Windows 側・1 回):
#   1. Google Drive デスクトップで <マイドライブ>/tmp/<repo 名>/ を同期させる
#   2. bash scripts/push-win-tools.sh で watcher 一式を送る
#   3. 同期フォルダの watch-and-convert.bat をダブルクリックして watcher を起動
#   経路の診断: bash scripts/check-pdf-path.sh
#
# Usage:
#   scripts/roundtrip.sh [OPTIONS]
# Options:
#   --skip-build    Phase 1 (ビルド) をスキップ。既存 data/step02_build / data/step03_diff を集約
#   --skip-push     Phase 2-3 (集約/push) をスキップし PDF 待ち + pull のみ実行
#   --timeout MIN   PDF 待ちタイムアウト (分。既定 10。Drive 同期遅延の裾で 5 分超があるため)
#   --poll SEC      ポーリング間隔 (秒。既定 10)
#   --dry-run       rclone を一切呼ばず予定のみ表示 (Phase 1 のビルドもスキップ)
#   --package ID    提出パッケージ data/output/<ID>/ を PDF 化と配送の対象にする (複数回指定可)。
#                   既定は SUBMISSION.md を持つパッケージ全部 (Phase 5)
#   --no-package    提出パッケージを扱わない (PDF 化にも配送にも回さない)
#   -h, --help      ヘルプ表示
# Env:
#   RCLONE_REMOTE      rclone リモート名 (既定 gdrive:)
#   GDRIVE_BASE_PATH   ベースパス (既定 tmp)
#   GDRIVE_SUBDIR      サブフォルダ (既定なし = tmp/<repo 名>/ 直下)

set -euo pipefail

# --- プロジェクトルート ---
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# ヘルプは cd の前に絶対パスを控えてから読む (相対パスの $0 だと scripts/ の中から起動したとき
# 自分自身を見つけられず、何も表示せずに落ちるため)
SCRIPT_SELF="$SCRIPT_DIR/$(basename "${BASH_SOURCE[0]}")"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

# --- ヘルプは lib の読み込みより前に処理する (lib が欠けていても使い方は読める) ---
for _arg in "$@"; do
    case "$_arg" in
        -h|--help) sed -n '2,/^$/p' "$SCRIPT_SELF"; exit 0 ;;
    esac
done

# --- 送出先 (push-win-tools.sh / check-pdf-path.sh と共有。二重定義しない) ---
if [ ! -f "$SCRIPT_DIR/lib/gdrive-dest.sh" ]; then
    echo "[ERROR] scripts/lib/gdrive-dest.sh がありません (送出先を算出できません)" >&2
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

# --- 本プロジェクトのディレクトリ ---
OUTPUT_DIR="data/output"      # 集約先 = push 元
PRODUCTS_DIR="data/products"  # PDF の pull 先
ALIVE_NAME=".watcher-alive"
STALE_SEC="${STALE_SEC:-300}" # 生存記録がこれより古ければ「停止の疑い」

# 集約元: step02 (ビルド docx) と step03 (差分 docx)。
# 提出パッケージ data/output/<journal>/ (step05) の本文と表は Phase 2 が別に拾う
# (<journal>-manuscript.docx / <journal>-Table1.docx …。data/step03_diff/ へ手でコピーしなくてよい)。
BUILD_OUTPUT_DIRS=(
    "data/step02_build"
    "data/step03_diff"
)
SUBMISSION_PREFIX="submission-"   # Drive 上の配送先: ${GDRIVE_DEST}/submission-<journal>/
NOT_FOR_SUBMISSION_MARK="このパッケージは提出用ではない"   # package.py の SUBMISSION.md の文言と対

# --- フラグ ---
SKIP_BUILD=false
SKIP_PUSH=false
PACKAGE_MODE=auto     # auto = SUBMISSION.md を持つパッケージ全部 / explicit = --package / off
PACKAGE_IDS=()
TIMEOUT_MIN=10
POLL_SEC=10
DRY_RUN=false

# --- ヘルパー ---
# 進捗ログは stderr へ出す (stdout はデータ専用。コマンド置換 $(...) がログを取り込む事故を防ぐ)
log_info()  { echo "[INFO]  $(date '+%H:%M:%S') $1" >&2; }
log_warn()  { echo "[WARN]  $(date '+%H:%M:%S') $1" >&2; }
log_error() { echo "[ERROR] $(date '+%H:%M:%S') $1" >&2; }
log_ok()    { echo "[OK]    $(date '+%H:%M:%S') $1" >&2; }
separator() { echo "========================================" >&2; }

# 数値の引数は正の整数だけを受け付ける (0・負数・小数・空・次のオプション名を弾く)。
#   検査が無いと `set -u` の「未割り当ての変数です」で落ちるか、0 のまま進んで即座に打ち切る。
require_posint() {
    local opt="$1" val="${2-}"
    if [[ ! "$val" =~ ^[1-9][0-9]{0,5}$ ]]; then
        log_error "${opt} には正の整数を指定してください (指定値: '${val}')"
        exit 1
    fi
}

# rclone を retry 付きで実行 (Google Drive の一時的応答遅延に耐える)
RCLONE_MAX_RETRIES="${RCLONE_MAX_RETRIES:-3}"
RCLONE_RETRY_SLEEP="${RCLONE_RETRY_SLEEP:-5}"
# ⚠ この形を崩さないこと。`if timeout ...; then return 0; fi` の直後に
#   `local rc=$?` を置くと、**if 文は条件が偽で else が無いとき 0 を返す**ため $? が
#   timeout の終了コードにならず、送出が全滅しても「成功」を返してしまう。
#   push-win-tools.sh / check-pdf-path.sh の同名関数と**完全に同じ形**にすること。
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
        --skip-build) SKIP_BUILD=true; shift ;;
        --skip-push)  SKIP_PUSH=true; shift ;;
        --timeout)    require_posint "$1" "${2-}"; TIMEOUT_MIN="$2"; shift 2 ;;
        --poll)       require_posint "$1" "${2-}"; POLL_SEC="$2"; shift 2 ;;
        --dry-run)    DRY_RUN=true; shift ;;
        --package)
            [[ -n "${2:-}" ]] || { log_error "--package には誌の id を付けてください (例: --package bhi)"; exit 1; }
            PACKAGE_MODE=explicit; PACKAGE_IDS+=("$2"); shift 2 ;;
        --no-package) PACKAGE_MODE=off; shift ;;
        -h|--help)    sed -n '2,/^$/p' "$SCRIPT_SELF"; exit 0 ;;
        *)            log_error "不明なオプション: $1"; exit 1 ;;
    esac
done

# --- 多重起動ガード (flock) ---
# 同一 Drive フォルダ・同一 PDF 名・同一作業ツリーを共有するため多重起動不可。
if [[ "$DRY_RUN" != true ]]; then
    if command -v flock >/dev/null 2>&1; then
        mkdir -p "$PROJECT_ROOT/$PRODUCTS_DIR"
        exec 9>"$PROJECT_ROOT/$PRODUCTS_DIR/.roundtrip.lock"
        if ! flock -n 9; then
            log_error "別の roundtrip が実行中です (多重起動防止のため中止)。確認: pgrep -af roundtrip"
            exit 1
        fi
    else
        log_warn "flock 不在のため多重起動ガード無効。手動で二重起動しないこと。"
    fi
fi

mkdir -p "$OUTPUT_DIR" "$PRODUCTS_DIR"

# 期待する PDF 名の集合 (data/output/*.docx から決まる)。Phase 3/4 が共有する。
EXPECTED_PDFS=()
compute_expected_pdfs() {
    EXPECTED_PDFS=()
    local f base
    for f in "$OUTPUT_DIR"/*.docx; do
        [[ -f "$f" ]] || continue
        base="$(basename "$f" .docx)"
        EXPECTED_PDFS+=("${base}.pdf")
    done
}

# ============================================================
# 提出パッケージ (Phase 2 で本文と表を PDF 化に回し、Phase 5 で Drive へ届ける)
# ============================================================
PACKAGES=()          # 扱う誌の id (resolve_packages が決める)
PKG_SRC=()           # Phase 5 で送るファイル (手元のパス)
PKG_DST=()           #   〃 の submission-<journal>/ からの相対パス

# build.sh / package.sh と同じ規則 (環境変数 INPUT_ROOT > .development > src)。
# roundtrip には --input が無いので、動作例のパッケージを送りたいときは INPUT_ROOT=... で起動する。
resolve_input_root() {
    if [[ -n "${INPUT_ROOT:-}" ]]; then
        echo "$INPUT_ROOT"
    elif [[ -e ".development" ]]; then
        echo "data/dummy"
    else
        echo "src"
    fi
}

# 送る前に止める条件を調べる。どれかに当たれば何も送らずに終了する。
check_package() {
    local j="$1"
    local pkg="$OUTPUT_DIR/$j" manifest="$OUTPUT_DIR/$j/SUBMISSION.md"
    local want recorded=""
    want="$(resolve_input_root)"

    if [[ ! "$j" =~ ^[A-Za-z0-9_-]+$ ]]; then
        log_error "誌の id が不正です: '$j' (英数字・_・- のみ)"; exit 1
    fi
    if [[ ! -f "$pkg/manuscript.docx" ]]; then
        log_error "提出パッケージ $pkg/ に manuscript.docx がありません"
        log_error "  先に bash scripts/package.sh --journal $j --mode final を回してください"
        exit 1
    fi

    if [[ -f "$manifest" ]]; then
        # (a) 草稿モード / --keep-figures のパッケージ (図が本文に埋まっている) は送らない
        if grep -q "$NOT_FOR_SUBMISSION_MARK" "$manifest"; then
            log_error "$pkg/ は提出用のパッケージではありません (草稿モードか --keep-figures で作った。SUBMISSION.md の冒頭を参照)"
            log_error "  bash scripts/package.sh --journal $j --mode final で作り直すか、--no-package を付けてください"
            exit 1
        fi
        # どの原稿から作ったか (package.py が SUBMISSION.md に書く。書式は package.py と対)
        recorded="$(sed -n 's/^- 原稿の入力ルート: `\(.*\)`$/\1/p' "$manifest" | head -1)"
        if [[ -z "$recorded" ]]; then
            log_error "$manifest に「原稿の入力ルート」の記録がありません (入力ルートを記録しない古い package.sh で作ったパッケージ)"
            log_error "  bash scripts/package.sh --journal $j --mode final で作り直してください"
            exit 1
        fi
        if [[ "$(realpath -m "$recorded")" != "$(realpath -m "$want")" ]]; then
            log_error "$pkg/ は $recorded の原稿から作られています (今の原稿は $want)"
            log_error "  動作例などで作ったパッケージを投稿用として届けないため中止します。"
            log_error "  bash scripts/package.sh --journal $j --mode final で作り直すか、--no-package を付けてください"
            exit 1
        fi
    else
        # SUBMISSION.md を書かない誌は --package で明示したときだけここに来る
        log_warn "$manifest がありません。提出用 (final) か・どの原稿から作ったかを確かめられません"
        recorded="$want"
    fi

    # (b) パッケージより新しい原稿・ビルド・誌プロファイルがあれば、パッケージが古い
    local paths=() newer=""
    paths+=("data/step02_build")
    if [[ -d "$recorded" ]]; then paths+=("$recorded"); fi
    if [[ -d "data/journals/$j" ]]; then paths+=("data/journals/$j"); fi
    newer="$(find "${paths[@]}" -type f ! -name '.*' ! -name 'README.md' ! -name '*.images.tsv' \
                 ! -path 'data/journals/*/*/*' -newer "$pkg/manuscript.docx" 2>/dev/null | sort | head -5 || true)"
    if [[ -n "$newer" ]]; then
        log_error "提出パッケージ $pkg/ より新しいファイルがあります (パッケージが古い):"
        while IFS= read -r f; do log_error "    $f"; done <<< "$newer"
        log_error "  bash scripts/build.sh と bash scripts/package.sh --journal $j --mode final を回し直してください"
        log_error "  (roundtrip を --skip-build なしで回すと Phase 1 のビルドでこれに当たります。BHI では --skip-build を付けること)"
        exit 1
    fi
}

resolve_packages() {
    PACKAGES=()
    case "$PACKAGE_MODE" in
        off)
            log_info "提出パッケージ: 扱わない (--no-package)"
            return 0 ;;
        explicit)
            PACKAGES=("${PACKAGE_IDS[@]}") ;;
        auto)
            local d
            for d in "$OUTPUT_DIR"/*/; do
                if [[ -f "${d}SUBMISSION.md" ]]; then
                    PACKAGES+=("$(basename "$d")")
                fi
            done ;;
    esac
    if [[ ${#PACKAGES[@]} -eq 0 ]]; then
        log_info "提出パッケージ: なし (data/output/*/SUBMISSION.md が無い)"
        return 0
    fi
    local j
    for j in "${PACKAGES[@]}"; do
        check_package "$j"
    done
    log_ok "提出パッケージ: ${PACKAGES[*]} → 本文と表を PDF 化し、${GDRIVE_DEST}/${SUBMISSION_PREFIX}<journal>/ へ届ける"
}

# Drive に置く形 (tables/ と figures/ は 1 階層に並べる) を PKG_SRC / PKG_DST に組む。
# 同じ名前が 2 つできたら止める (並べたせいで片方が消えるのを防ぐ)。
plan_package_files() {
    local pkg="$OUTPUT_DIR/$1" f g name
    PKG_SRC=(); PKG_DST=()
    declare -A seen=()
    _plan_add() {
        if [[ -n "${seen[$2]:-}" ]]; then
            log_error "配送先で名前が重なります: $2 ($1 と ${seen[$2]})"; exit 1
        fi
        seen[$2]="$1"; PKG_SRC+=("$1"); PKG_DST+=("$2")
    }
    for f in "$pkg"/*; do
        name="$(basename "$f")"
        if [[ -f "$f" ]]; then
            _plan_add "$f" "$name"
        elif [[ -d "$f" ]]; then
            case "$name" in
                tables|figures)
                    for g in "$f"/*; do
                        if [[ -f "$g" ]]; then _plan_add "$g" "$(basename "$g")"; fi
                    done ;;
                *)
                    while IFS= read -r -d '' g; do
                        _plan_add "$g" "${g#"$pkg"/}"
                    done < <(find "$f" -type f -print0 | sort -z) ;;
            esac
        fi
    done
}

# ============================================================
# Phase 1: ビルド
# ============================================================
phase_build() {
    separator; log_info "Phase 1: ビルド"; separator
    if [[ "$SKIP_BUILD" == true ]]; then
        log_info "--skip-build: 既存の docx を使用"
        return 0
    fi
    # ⚠ dry-run ではビルドも行わない。build.sh は【引数なしだと _default プロファイルで
    #   書き出す】ため、ここで走らせると BHI 版の docx を黙って _default 版で上書きしてしまう。
    #   「何も壊さずに流れだけ見る」のが dry-run の役目なので、ここで止める。
    if [[ "$DRY_RUN" == true ]]; then
        log_info "(dry-run) ビルドは行いません (既存 docx を上書きしないため)"
        return 0
    fi
    # ⚠ 引数なしで呼ぶと _default プロファイルでビルドされる。BHI 版を見たいときは
    #   先に `bash scripts/build.sh --journal bhi --article-type original` を回し、
    #   本スクリプトは --skip-build で使うこと (docs/usage-guide.md §8.4)。
    bash scripts/build.sh
}

# ============================================================
# Phase 2: 成果物を data/output/ に集約
# ============================================================
phase_collect() {
    separator; log_info "Phase 2: 成果物集約 → $OUTPUT_DIR/"; separator

    # 前回の docx を掃除する (残っていると変換対象と期待 PDF 名がずれる)。
    # data/output/<journal>/ (step05 の提出パッケージ) には触らない。
    local f
    for f in "$OUTPUT_DIR"/*.docx; do
        [[ -f "$f" ]] && rm -f "$f"
    done

    local count=0 dir
    for dir in "${BUILD_OUTPUT_DIRS[@]}"; do
        [[ -d "$dir" ]] || continue
        for f in "$dir"/*.docx; do
            [[ -f "$f" ]] || continue
            cp "$f" "$OUTPUT_DIR/"
            log_info "  ← $f"
            count=$((count + 1))
        done
    done

    # 提出パッケージの本文と表も PDF 化に回す (<journal>-manuscript.docx / <journal>-Table1.docx …)。
    # 名前は従来 docs/usage-guide.md §8.4 で手でコピーしていたときと同じにしてある。
    local j dest
    for j in "${PACKAGES[@]}"; do
        for f in "$OUTPUT_DIR/$j/manuscript.docx" "$OUTPUT_DIR/$j"/tables/*.docx; do
            [[ -f "$f" ]] || continue
            dest="$OUTPUT_DIR/${j}-$(basename "$f")"
            if [[ -f "$dest" ]]; then
                log_warn "  $(basename "$dest") は集約元にもありました。提出パッケージの版で上書きします"
            else
                count=$((count + 1))
            fi
            cp "$f" "$dest"
            log_info "  ← $f (提出パッケージ → $(basename "$dest"))"
        done
    done

    if [[ $count -eq 0 ]]; then
        log_error "集約できる docx がありません: ${BUILD_OUTPUT_DIRS[*]}"
        log_error "  先に bash scripts/build.sh を回すか、--skip-build を外してください"
        exit 1
    fi
    log_ok "$count 個の docx を $OUTPUT_DIR/ に集約"
}

# ============================================================
# Phase 3: 旧 PDF の退避 → docx を push
# ============================================================
# ⚠ 退避に失敗したまま進むと、Phase 4 は【ファイル名の一致だけ】を見るため
#   前回の古い PDF を今回の成果物として持ち帰る。提出物が 1 世代前になり得るので、
#   失敗は握り潰さず中止する。
archive_old_pdfs() {
    local ts; ts="$(date '+%Y%m%d_%H%M%S')"
    local archive="${GDRIVE_DEST}/__archives"
    local pdf_list rc=0

    pdf_list="$(rclone_with_retry 60 rclone lsf "${GDRIVE_DEST}" \
        --include "*.pdf" --max-depth 1 --files-only)" || rc=$?
    if [[ $rc -ne 0 ]]; then
        log_error "送出先の一覧取得に失敗しました (exit $rc): ${GDRIVE_DEST}"
        log_error "  旧 PDF を退避できないため中止します。古い PDF が残っていると、"
        log_error "  それを今回の成果物として取得してしまう恐れがあります。"
        exit 1
    fi
    # 再試行があると各試行の出力が積み上がるため重複を落とす
    pdf_list="$(printf '%s\n' "$pdf_list" | sort -u)"

    if [[ -n "${pdf_list//[[:space:]]/}" ]]; then
        log_info "旧 PDF を __archives/ へ退避..."
        rclone mkdir "$archive" 2>/dev/null || true
        local name base
        while IFS= read -r name; do
            [[ -z "$name" ]] && continue
            base="${name%.pdf}"
            if timeout 30 rclone moveto "${GDRIVE_DEST}/${name}" \
                    "${archive}/${base}_${ts}.pdf" >/dev/null 2>&1; then
                log_info "  旧 ${name} → __archives/${base}_${ts}.pdf"
            else
                log_error "旧 PDF の退避に失敗しました: ${name}"
                log_error "  古い PDF を新しい成果物として取得する恐れがあるため中止します。"
                exit 1
            fi
        done <<< "$pdf_list"
    fi

    # 退避後、待ち受ける PDF が残っていないことを確認する。
    # ここを通れば Phase 4 の「名前が一致したら新しい成果物」という前提が成り立つ。
    local leftover pdf
    for pdf in "${EXPECTED_PDFS[@]}"; do
        leftover="$(rclone_with_retry 60 rclone lsf "${GDRIVE_DEST}" \
            --include "$pdf" --max-depth 1 --files-only)" || leftover=""
        if [[ -n "${leftover//[[:space:]]/}" ]]; then
            log_error "退避後も ${pdf} が送出先に残っています: ${GDRIVE_DEST}"
            log_error "  手動で退避するか削除してから再実行してください。"
            exit 1
        fi
    done
}

# watcher が生きているかを見る。止まっていても中止はしない (警告のみ)。
# この確認が無いと、watcher が止まっているときに Phase 4 がタイムアウトまで無言で待つ。
check_watcher() {
    local seen alive_line age now
    seen="$(rclone_with_retry 60 rclone lsf "${GDRIVE_DEST}" \
        --include "watch-and-convert.ps1" --max-depth 1 --files-only)" || seen=""
    if [[ -z "${seen//[[:space:]]/}" ]]; then
        log_warn "送出先に watch-and-convert.ps1 がありません: ${GDRIVE_DEST}"
        log_warn "  → bash scripts/push-win-tools.sh を先に実行してください"
        return 0
    fi

    # .watcher-alive の更新時刻で生存を見る (watcher が 60 秒ごとに書き換える)
    alive_line="$(rclone_with_retry 60 rclone lsl "${GDRIVE_DEST}" \
        --include "$ALIVE_NAME" --max-depth 1 2>/dev/null | head -1)" || alive_line=""
    if [[ -z "${alive_line//[[:space:]]/}" ]]; then
        log_warn "生存記録 ${ALIVE_NAME} がありません。watcher が未起動か、旧版の可能性があります"
        log_warn "  → Windows で watch-and-convert.bat を起動してください"
        return 0
    fi
    # "  <size> YYYY-MM-DD HH:MM:SS.fff <name>" の日時を秒に直す
    local ts_str; ts_str="$(awk '{print $2" "$3}' <<< "$alive_line" | cut -d. -f1)"
    now="$(date +%s)"
    age=$(( now - $(date -d "$ts_str" +%s 2>/dev/null || echo "$now") ))
    if (( age > STALE_SEC )); then
        log_warn "watcher の生存記録が ${age} 秒前で止まっています (しきい値 ${STALE_SEC} 秒)"
        log_warn "  → Windows 側で watcher が落ちている疑いがあります。起動を確認してください"
    else
        log_ok "watcher 稼働中 (生存記録は ${age} 秒前)"
    fi

    # 実行中の watcher の版と設定 (生存記録の 2 行目以降)。試験用の起動のまま放置されていると
    # 全件が打ち切られて error/ へ行き、ここで気づかないとタイムアウトまで無言で待つことになる。
    # 警告だけを出す (通常時の出力を増やさない)。中止はしない。
    # ⚠ ループの中を `[[ ... ]] && log_warn` にしないこと。最後の行が WARN 以外だと関数が 1 を返し、
    #   `set -e` の下で呼び出し元 (phase_push) ごと黙って終わる (通常時は最後の行が INFO なので毎回起きる)。
    local content lv msg
    content="$(rclone_with_retry 60 rclone cat "${GDRIVE_DEST}/${ALIVE_NAME}" 2>/dev/null)" || content=""
    if [[ -n "${content//[[:space:]]/}" ]]; then
        while IFS=$'\t' read -r lv msg; do
            if [[ "$lv" == "WARN" ]]; then
                log_warn "$msg"
            fi
        done < <(alive_meta_report "$content")
    fi
    return 0
}

# 送出先の直下に、これから送る docx と同じ名前の docx が残っていれば中止する。
# 残っているのは前回送ったものが変換を待っているか変換中だからで、そこへ同じ名前で送ると
# Google Drive はそれを【同じファイルの更新】として扱う。更新が Windows に届くのは変換が終わって
# watcher が docx を processed/ へ移した後になりやすく (実機で 2 回とも 16 秒以上遅れた)、そのときは
# 新しい版が変換されないまま processed/ に入り、送出先には古い版の PDF だけが返る。その PDF は
# 今回の push より後に書かれているので、Phase 4 の更新時刻の確かめでは古い版と見分けられない。
check_pending_docx() {
    local docx_list rc=0 pdf base found=()
    docx_list="$(rclone_with_retry 60 rclone lsf "${GDRIVE_DEST}" \
        --include "*.docx" --max-depth 1 --files-only)" || rc=$?
    if [[ $rc -ne 0 ]]; then
        log_error "送出先の一覧取得に失敗しました (exit $rc): ${GDRIVE_DEST}"
        log_error "  前回の docx が残っていないかを確かめられないため中止します。"
        exit 1
    fi
    for pdf in "${EXPECTED_PDFS[@]}"; do
        base="${pdf%.pdf}"
        if grep -qxF "${base}.docx" <<< "$docx_list"; then
            found+=("${base}.docx")
        fi
    done
    if (( ${#found[@]} > 0 )); then
        log_error "送出先に同じ名前の docx が残っています: ${found[*]} (${GDRIVE_DEST})"
        log_error "  前回送ったものが変換を待っているか、変換中です。いま同じ名前で送ると、新しい版が変換されないまま"
        log_error "  processed/ に入り、古い版の PDF を今回の成果物として持ち帰ることがあります。"
        log_error "  → 前回の PDF が送出先に返ってから再実行してください (返った古い PDF は再実行の冒頭で __archives/ へ退避されます)。"
        log_error "    watcher が止まっているなら起動するか、送出先からその docx を消してください。"
        exit 1
    fi
}

phase_push() {
    separator; log_info "Phase 3: push → ${GDRIVE_DEST}"; separator

    if [[ "$DRY_RUN" == true ]]; then
        local f
        for f in "$OUTPUT_DIR"/*.docx; do
            [[ -f "$f" ]] && log_info "(dry-run) push 予定: $f → ${GDRIVE_DEST}/$(basename "$f")"
        done
        return 0
    fi

    if ! command -v rclone &>/dev/null; then
        log_error "rclone がインストールされていません"; exit 1
    fi
    if ! rclone_with_retry 60 rclone lsf "${GDRIVE_DEST}/" --max-depth 1 &>/dev/null; then
        log_info "送出先が見つからないため作成します: ${GDRIVE_DEST}"
        rclone_with_retry 60 rclone mkdir "${GDRIVE_DEST}" || {
            log_error "rclone リモート '${GDRIVE_DEST}' に接続できません"
            log_error "  rclone config reconnect ${RCLONE_REMOTE} を試してください"; exit 1
        }
    fi

    check_watcher
    check_pending_docx
    archive_old_pdfs

    # docx だけを送る (data/output/<journal>/ を巻き込まないよう --max-depth 1)
    # push を始めた時刻を覚えておき、Phase 4 はそれより後に書かれた PDF だけを今回の成果物とする
    PUSH_START_EPOCH="$(date +%s)"
    rclone_with_retry 300 rclone copy "$OUTPUT_DIR" "${GDRIVE_DEST}" \
        --include "*.docx" --max-depth 1 --stats-one-line -v
    log_ok "push 完了: ${#EXPECTED_PDFS[@]} 件"
}

# ============================================================
# Phase 4: PDF 変換待ち → pull
# ============================================================
phase_wait_and_pull() {
    separator
    log_info "Phase 4: PDF 待ち (最大 ${TIMEOUT_MIN}分・${POLL_SEC}秒間隔) → ${PRODUCTS_DIR}/"
    separator

    if [[ ${#EXPECTED_PDFS[@]} -eq 0 ]]; then
        log_warn "待つ PDF がありません (data/output/ に docx がない)"
        return 0
    fi
    log_info "待つ PDF: ${EXPECTED_PDFS[*]}"

    if [[ "$DRY_RUN" == true ]]; then
        log_info "(dry-run) 上を待って ${PRODUCTS_DIR}/ へ pull する予定"
        return 0
    fi

    local deadline=$((SECONDS + TIMEOUT_MIN * 60))
    local remote_list pdf missing line ts_str mtime stale_warned=""
    # push より前に書かれた PDF (前回の打ち切りの後も watcher が変換を続けていた旧版など) は取り込まない。
    # Windows と本機の時計のずれは PDF_MTIME_SLACK_SEC で吸収する。--skip-push のときは push の時刻が無いので見ない
    local slack="${PDF_MTIME_SLACK_SEC:-120}"
    while [[ $SECONDS -lt $deadline ]]; do
        # 行の形: "<size> YYYY-MM-DD HH:MM:SS.fffffffff <name>" (rclone lsl。時刻は本機の時間帯)
        remote_list="$(rclone_with_retry 60 rclone lsl "${GDRIVE_DEST}" \
            --include "*.pdf" --max-depth 1 2>/dev/null)" || remote_list=""
        missing=0
        for pdf in "${EXPECTED_PDFS[@]}"; do
            line="$(awk -v n="$pdf" '{ name = $0; sub(/^ *[0-9]+ +[^ ]+ +[^ ]+ +/, "", name); if (name == n) { print; exit } }' <<< "$remote_list")"
            if [[ -z "$line" ]]; then
                missing=$((missing + 1)); continue
            fi
            if [[ -n "${PUSH_START_EPOCH:-}" ]]; then
                ts_str="$(awk '{print $2" "$3}' <<< "$line" | cut -d. -f1)"
                mtime="$(date -d "$ts_str" +%s 2>/dev/null || echo "")"
                if [[ -n "$mtime" ]] && (( mtime < PUSH_START_EPOCH - slack )); then
                    if [[ "$stale_warned" != *"|$pdf|"* ]]; then
                        echo "" >&2
                        log_warn "push より前に書かれた $pdf を無視して待ちます (${ts_str}。前回の変換の残りの疑い)"
                        stale_warned="${stale_warned}|$pdf|"
                    fi
                    missing=$((missing + 1)); continue
                fi
            fi
        done
        if [[ $missing -eq 0 ]]; then
            log_ok "PDF ${#EXPECTED_PDFS[@]} 件をすべて検出"
            break
        fi
        printf "\r  待機中... (残り %d 件 / 約 %d 分)  " \
            "$missing" "$(( (deadline - SECONDS) / 60 ))" >&2
        sleep "$POLL_SEC"
    done
    echo "" >&2

    if [[ $missing -ne 0 ]]; then
        log_error "タイムアウト: PDF が ${missing} 件そろいませんでした"
        log_error "  Windows 側 watch-and-convert.ps1 が次のフォルダで起動しているか確認してください:"
        log_error "    ${GDRIVE_DEST}"
        log_error "  診断: bash scripts/check-pdf-path.sh"
        log_error "  再開 (再アップロード不要): bash scripts/roundtrip.sh --skip-push"
        exit 1
    fi

    log_info "pull → ${PRODUCTS_DIR}/"
    for pdf in "${EXPECTED_PDFS[@]}"; do
        rclone_with_retry 300 rclone copyto "${GDRIVE_DEST}/${pdf}" \
            "${PRODUCTS_DIR}/${pdf}" --stats-one-line -v
        log_ok "  ${PRODUCTS_DIR}/${pdf} ($(du -h "${PRODUCTS_DIR}/${pdf}" | cut -f1))"
    done
    log_info "Google Drive 側の PDF は保持 (Windows での閲覧用)。次回 push 冒頭で __archives/ へ自動退避。"
}

# ============================================================
# Phase 5: 提出パッケージを Drive の submission-<journal>/ へ届ける
# ============================================================
# PDF がそろった (= Word が開けた) あとで届ける。PDF 待ちがタイムアウトしたら届けない
# (`--skip-push` で再開すれば、待ちが終わったあとに届く)。
deliver_package() {
    local j="$1"
    local stage="$PRODUCTS_DIR/${SUBMISSION_PREFIX}$j"
    local remote="${GDRIVE_DEST}/${SUBMISSION_PREFIX}$j"
    local i

    plan_package_files "$j"
    log_info "${SUBMISSION_PREFIX}$j/ に置くもの (${#PKG_DST[@]} 件):"
    for i in "${!PKG_DST[@]}"; do
        log_info "    ${PKG_DST[$i]}  ← ${PKG_SRC[$i]}"
    done
    if [[ "$DRY_RUN" == true ]]; then
        log_info "(dry-run) 手元の $stage/ に組み、rclone sync で $remote/ と一致させる予定"
        return 0
    fi

    # 手元に Drive と同じ形の写しを組む (前回の写しは作り直す。data/products/ は git 管理外の成果物置き場)
    rm -rf "$stage"
    mkdir -p "$stage"
    for i in "${!PKG_DST[@]}"; do
        mkdir -p "$stage/$(dirname "${PKG_DST[$i]}")"
        cp -p "${PKG_SRC[$i]}" "$stage/${PKG_DST[$i]}"
    done

    # Drive 側をパッケージと完全に一致させる。消えた・置き換わったファイルは削除せず退避する。
    local ts; ts="$(date '+%Y%m%d_%H%M%S')"
    rclone_with_retry 300 rclone sync "$stage" "$remote" \
        --backup-dir "${GDRIVE_DEST}/__archives/${SUBMISSION_PREFIX}${j}_${ts}" \
        --stats-one-line -v
    # 届いたものが手元と一致するか (件数・中身) を確かめる
    if ! rclone_with_retry 120 rclone check "$stage" "$remote" >/dev/null 2>&1; then
        log_error "Drive の ${SUBMISSION_PREFIX}$j/ が手元の写しと一致しません: $remote"
        log_error "  確認: rclone check $stage $remote"
        exit 1
    fi
    log_ok "配送完了: $remote/ (${#PKG_DST[@]} 件。手元の写し: $stage/)"
}

phase_deliver() {
    separator
    log_info "Phase 5: 提出パッケージの配送 → ${GDRIVE_DEST}/${SUBMISSION_PREFIX}<journal>/"
    separator
    if [[ ${#PACKAGES[@]} -eq 0 ]]; then
        log_info "届ける提出パッケージはありません"
        return 0
    fi
    local j
    for j in "${PACKAGES[@]}"; do
        deliver_package "$j"
    done
}

# ============================================================
# メイン
# ============================================================
separator
log_info "roundtrip: build → 集約 → push → PDF 待ち → pull → 提出パッケージの配送"
[[ "$DRY_RUN" == true ]] && log_info "(dry-run モード: rclone 呼び出しなし)"
log_info "dest = ${GDRIVE_DEST}"
separator

if [[ "$SKIP_PUSH" == true ]]; then
    log_info "Phase 1-3: スキップ (--skip-push)"
    resolve_packages
    compute_expected_pdfs
else
    phase_build
    # 提出パッケージの検査はビルドの【後】に行う (Phase 1 がビルドし直したらパッケージは古い)。
    # 何も送らないうちに止めるため、集約・push より前に置く。
    resolve_packages
    phase_collect
    compute_expected_pdfs
    phase_push
fi

phase_wait_and_pull
phase_deliver

separator
if [[ "$DRY_RUN" == true ]]; then
    log_ok "dry-run 完了 (何も送っていません)"
else
    log_ok "roundtrip 完了"
fi
separator
echo "docx: $OUTPUT_DIR/"
echo "PDF : $PRODUCTS_DIR/"
for _j in "${PACKAGES[@]}"; do
    echo "提出: ${GDRIVE_DEST}/${SUBMISSION_PREFIX}${_j}/  (手元の写し: $PRODUCTS_DIR/${SUBMISSION_PREFIX}${_j}/)"
done
