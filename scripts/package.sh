#!/bin/bash
# package.sh — 投稿パッケージ組立 オーケストレータ (step05)
#
# docs/architecture.md §2.5 / §3。雑誌プロファイル profile.yaml に従い、ビルド済み docx (step02) と差分 docx
# (step03)・図 (step01) を整形・命名・集約して data/output/<journal>/ に提出一式を作る。
#
# モード:
#   draft (草稿) : 図を埋め込んだ manuscript.docx を提出。
#   final (最終) : manuscript から図を分離し figures/ に雑誌指定の形式/解像度/命名で出力。
#   既定は profile.figures.embed (true→draft / false→final)。--mode で上書き。
#
# 図の最終形式が pdf のときは非 mermaid svg を docx-paper-template-svg-converter で svg→pdf 化する
# (mermaid は step01 の mmdc 正本 pdf を保持)。png のときは pandoc コンテナ内 rsvg で生成し、
# SVG の物理サイズから画素数を計算して要求 dpi を保証する (届かなければエラーで停止)。
# pptx のときは 1 図 = 1 pptx = 1 スライドで SVG をベクターのまま埋め込む。
# figures.pptx.text_to_path=true のときだけ svg-converter で svg→アウトライン svg も作る。
#
# INPUT_ROOT は .development マーカーで切替 (docs/architecture.md §4): 有り->data/dummy / 無し->src。
#
# 使い方:
#   scripts/package.sh [--journal <id>] [--article-type <id>] [--mode draft|final] [--input <dir>]
#                      [--format <fmt>] [--dpi <n>] [--font-handling outline|embed]
#                      [--slide-fit figure|fixed] [--keep-figures] [--no-validate] [--build]
#
# 出力: data/output/<journal>/ (manuscript / figures / revise-report / cover-letter [+ manuscript-diff])
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

COMPOSE_FILE="docker/docker-compose.yml"
JOURNAL="_default"
ARTICLE_TYPE=""
MODE=""
INPUT_OVERRIDE=""
FORMAT=""
DPI=""
FONT_HANDLING=""
SLIDE_FIT=""
KEEP_FIGURES=0
ALLOW_DISALLOWED=0
NO_VALIDATE=0
RUN_BUILD=0

usage() {
    cat <<'EOF'
使い方: scripts/package.sh [オプション]

オプション:
  --journal <id>          雑誌プロファイル (data/journals/<id>)。既定: _default
  --article-type <id>     記事種別 (profile の article_types を持つ誌のみ。例: bhi の original)。
                          limits/abstract を種別値で解決して検証する。既定: profile.article_type
  --mode draft|final      図の扱い。既定: profile.figures.embed (true->draft / false->final)
  --input <dir>           入力ルートを明示 (既定: .development 有り->data/dummy / 無し->src)
  --format <fmt>          図形式の上書き (pdf/png/pptx/tiff/eps)。tiff->png, eps->pdf に代替
                          (代替先が profile.submission.figure_formats に無い誌ではエラー停止)。
                          pptx は 1 図 = 1 pptx = 1 スライドのベクター提出。
                          jpeg は生成非対応 — 指定するとエラーで止まる (線画には png を使う)。
                          上記以外の綴りもエラーで止まる (黙って pdf などに代替しない)
  --dpi <n>               ラスタ図 (png) の dpi 上書き。SVG の物理サイズから画素数を計算して保証する
                          (物理単位を持たない SVG は 96dpi の CSS px とみなす)。
                          pptx 経路では同梱する PNG フォールバックの解像度になる
  --font-handling <h>     最終図 svg->pdf のフォント処理 (outline=text-to-path / embed)
  --slide-fit <f>         pptx のスライド寸法 (figure=図の実寸 / fixed=既定サイズに中央配置)。
                          既定は profile.figures.pptx.slide_fit。図の実寸が PowerPoint の規格
                          (1〜56 インチ) を外れると figure ではエラーになるので fixed へ退避する
  --keep-figures          最終モードでも図を manuscript に残す (分離しない)
  --allow-disallowed-format
                          誌の受入形式 (submission.figure_formats) 外の図を承知のうえで生成する。
                          既定では停止する — BHI で --format png と --format pdf を打ち間違えると、
                          止めなければ規定違反の図一式が終了コード 0 で揃うため。
                          受入形式を宣言していない誌には影響しない
  --no-validate           語数等の検証をしない
  --build                 先に scripts/build.sh を実行してから集約する

出力: data/output/<journal>/
EOF
}

while [ $# -gt 0 ]; do
    case "$1" in
        --journal)       JOURNAL="${2:?--journal に id を指定してください}"; shift 2 ;;
        --article-type)  ARTICLE_TYPE="${2:?--article-type に種別 id を指定してください}"; shift 2 ;;
        --mode)          MODE="${2:?--mode に draft|final を指定してください}"; shift 2 ;;
        --input)         INPUT_OVERRIDE="${2:?--input にディレクトリを指定してください}"; shift 2 ;;
        --format)        FORMAT="${2:?--format に形式を指定してください}"; shift 2 ;;
        --dpi)           DPI="${2:?--dpi に数値を指定してください}"; shift 2 ;;
        --font-handling) FONT_HANDLING="${2:?--font-handling に outline|embed を指定してください}"; shift 2 ;;
        --slide-fit)     SLIDE_FIT="${2:?--slide-fit に figure|fixed を指定してください}"; shift 2 ;;
        --keep-figures)  KEEP_FIGURES=1; shift ;;
        --allow-disallowed-format) ALLOW_DISALLOWED=1; shift ;;
        --no-validate)   NO_VALIDATE=1; shift ;;
        --build)         RUN_BUILD=1; shift ;;
        -h|--help)       usage; exit 0 ;;
        *)               echo "エラー: 不明な引数 '$1'" >&2; usage; exit 1 ;;
    esac
done

# --- INPUT_ROOT 解決 (環境変数 > --input > .development。build.sh と同一規則) ---
if [ -n "${INPUT_ROOT:-}" ]; then
    :
elif [ -n "$INPUT_OVERRIDE" ]; then
    INPUT_ROOT="$INPUT_OVERRIDE"
elif [ -e ".development" ]; then
    INPUT_ROOT="data/dummy"
else
    INPUT_ROOT="src"
fi

if [ ! -f "$INPUT_ROOT/main.md" ]; then
    echo "エラー: 原稿 '$INPUT_ROOT/main.md' がありません。" >&2
    echo "  ダミーで検証するには 'echo dev > .development' で data/dummy/ に切替えてください (docs/architecture.md §4)。" >&2
    exit 1
fi
if [ ! -d "data/journals/$JOURNAL" ]; then
    echo "エラー: 雑誌プロファイル 'data/journals/$JOURNAL' がありません。" >&2
    exit 1
fi

RUN="docker compose -f $COMPOSE_FILE run --rm -u $(id -u):$(id -g) -T pandoc"

# --- 任意: 先にビルド ---
if [ "$RUN_BUILD" -eq 1 ]; then
    echo "-- 先に scripts/build.sh を実行 (--build)"
    INPUT_ROOT="$INPUT_ROOT" bash scripts/build.sh --journal "$JOURNAL" \
        ${ARTICLE_TYPE:+--article-type "$ARTICLE_TYPE"}
fi

if [ ! -f "data/step02_build/main.docx" ]; then
    echo "エラー: data/step02_build/main.docx がありません。" >&2
    echo "  先に 'bash scripts/build.sh' を実行するか、--build を付けてください。" >&2
    exit 1
fi

# package.py へ渡す共通オプション
COMMON_OPTS=(--input-root "$INPUT_ROOT" --journal "$JOURNAL")
[ -n "$ARTICLE_TYPE" ]  && COMMON_OPTS+=(--article-type "$ARTICLE_TYPE")
[ -n "$MODE" ]          && COMMON_OPTS+=(--mode "$MODE")
[ -n "$FORMAT" ]        && COMMON_OPTS+=(--format "$FORMAT")
[ -n "$FONT_HANDLING" ] && COMMON_OPTS+=(--font-handling "$FONT_HANDLING")
# figure-plan も slide_fit を見る (アウトライン化の要否は pptx 経路かどうかで決まるため、
# 片方だけ違う設定で動くと計画と生成が食い違う)。
[ -n "$SLIDE_FIT" ]     && COMMON_OPTS+=(--slide-fit "$SLIDE_FIT")
# figure-plan にも渡す。図を分離しないのに形式検査で止まるのを防ぐため
# (assemble 側も --keep-figures を形式検査の対象外にしている)。
[ "$KEEP_FIGURES" -eq 1 ] && COMMON_OPTS+=(--keep-figures)
# 受入形式外の図を出す明示同意。figure-plan / assemble の両方が同じ判定をするので
# COMMON_OPTS で渡す (片方だけ止まる組合せを作らないため)。
[ "$ALLOW_DISALLOWED" -eq 1 ] && COMMON_OPTS+=(--allow-disallowed-format)

echo "== Step 05 投稿パッケージ =="
echo "  INPUT_ROOT = $INPUT_ROOT"
echo "  JOURNAL    = $JOURNAL"
[ -n "$ARTICLE_TYPE" ] && echo "  TYPE       = $ARTICLE_TYPE"
echo "  MODE       = ${MODE:-(profile 既定)}"

# --- 図変換計画 (最終モード + pdf 形式のとき非 mermaid svg を svg-conversion で pdf 化) ---
echo "-- 図変換計画を取得 (figure-plan)"
# package.py figure-plan は TSV (src_svg<TAB>out<TAB>embed<TAB>kind) のみ stdout に出す。
# kind: pdf = svg→pdf / outline-svg = svg→アウトライン化 svg。
# 診断と終了状態を捨てない (`2>/dev/null || true` にすると、「禁止形式へは代替せず停止」の
#   エラー文が表示されず、計画が空になった結果「(svg→pdf 変換は不要: 草稿モード or png 形式)」
#   という実態と食い違う行が出る。最終的には assemble 側で停止するが、停止理由が利用者に届かない)。
#   診断は stderr へ通し、異常終了ならここで理由を添えて止める。
set +e
PLAN="$($RUN python3 main/step05_package/package.py figure-plan "${COMMON_OPTS[@]}")"
PLAN_RC=$?
set -e
if [ "$PLAN_RC" -ne 0 ]; then
    echo "エラー: 図変換計画の作成に失敗しました (package.py figure-plan が終了状態 $PLAN_RC で停止)。" >&2
    echo "  上の診断を確認してください (受入形式外への代替なら --format で受入形式内を指定します)。" >&2
    exit "$PLAN_RC"
fi

if [ -n "$PLAN" ]; then
    echo "-- 図変換 (docx-paper-template-svg-converter)"
    while IFS=$'\t' read -r src out embed kind; do
        # TSV 行のみ処理 (空行・診断行を弾く)。src は必ず図ツリー (step01) の svg。
        # 出力先 out は kind で変わる: pdf は図ツリー内、outline-svg は data/step05_package/
        # (step05 の派生物を原稿の図の隣 = 図ツリーに置かない。convert.sh が出力先ディレクトリを
        #  mkdir -p するので事前準備は要らない)。
        case "$src" in
            data/step01_figures/*) : ;;
            *) continue ;;
        esac
        [ -n "$out" ] || continue
        case "$out" in
            data/step01_figures/*|data/step05_package/*) : ;;
            *)
                echo "エラー: figure-plan が想定外の出力先 '$out' を返しました" >&2
                exit 1 ;;
        esac
        conv_opts=()
        case "${kind:-pdf}" in
            outline-svg)
                # pptx へ埋め込む SVG のアウトライン化 (figures.pptx.text_to_path=true)
                conv_opts+=(--outline-svg) ;;
            pdf)
                # --embed-fonts は pdf 経路だけの選択肢 (アウトライン化と目的が相反するため)
                [ "${embed:-0}" = "1" ] && conv_opts+=(--embed-fonts) ;;
            *)
                echo "エラー: figure-plan が未知の変換種別 '$kind' を返しました" >&2
                exit 1 ;;
        esac
        echo "   [${kind:-pdf}] $src -> $out ${conv_opts[*]:-}"
        bash docker/svg-conversion/convert.sh "$src" "$out" ${conv_opts[@]+"${conv_opts[@]}"}
    done <<< "$PLAN"
else
    echo "   (svg-conversion は不要: 草稿モード / png 形式 / text_to_path=false の pptx 形式)"
fi

# --- 集約 (assemble) ---
ASM_OPTS=("${COMMON_OPTS[@]}")
[ -n "$DPI" ]            && ASM_OPTS+=(--dpi "$DPI")
[ "$NO_VALIDATE" -eq 1 ]  && ASM_OPTS+=(--no-validate)

echo ""
$RUN python3 main/step05_package/package.py assemble "${ASM_OPTS[@]}"

echo ""
echo "== パッケージ完了: data/output/$JOURNAL/ =="
find "data/output/$JOURNAL" -type f | sort | sed 's/^/  /'
