#!/bin/bash
# check-figures.sh — ラスタ図が要求 dpi を満たしているかの受入テスト (driver)
#
# BioHealth Informatics は図に "a minimum of 300 dpi" を課すが、画素数不足は
# **目視で検知できない** (docx 上の表示サイズは pHYs のおかげで同じになるため、粗さが出るのは
# 印刷・組版の段階)。SVG の物理サイズから期待画素数を計算し、PNG の IHDR (実画素数) と
# pHYs (物理解像度) を 1 件ずつ突き合わせる。
# 本体は main/step01_figures/check_dpi.py (docx-paper-template-pandoc コンテナ内で実行)。
#
# 使い方:
#   scripts/check-figures.sh                                     # data/step01_figures/figs を 300dpi で検査
#   scripts/check-figures.sh --dpi 600
#   scripts/check-figures.sh --tree data/step01_figures/figs
#   scripts/check-figures.sh --figures-dir data/output/bhi/figures   # 分離出力図の pHYs も見る
#
# 分離出力図が pptx (ベクター提出) のときは書庫を開き、SVG 拡張の位置・SVG 本体と
# PNG フォールバックの同梱・同梱 PNG の pHYs まで検査する。
#
# 図ツリーでは、解像度とは別に **Word / PowerPoint でだけ崩れる SVG の疑い** (svglite の出力が 2 つ /
# id の重複 / 塗りの色が hsl()) を「注意」として出す (体裁の計測では見つからない)。
#
# 先に図を生成しておくこと:
#   bash scripts/build.sh                                            # → data/step01_figures/figs
#   bash scripts/package.sh --journal bhi --mode final               # → data/output/bhi/figures (pptx)
#   bash scripts/package.sh --journal bhi --mode final --format png  # → data/output/bhi/figures (png)
#
# 終了コード: 0 = 全件合格 / 1 = 不合格あり / 2 = 対象が 1 件も無い (空振り)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

COMPOSE_FILE="docker/docker-compose.yml"
TREE=""
SELF_TEST=0
FIGURES_DIR=""
DPI=""            # 既定値は check_dpi.py 側で解決する (--journal を見るため)
JOURNAL=""
ARTICLE_TYPE=""

usage() {
    cat <<'EOF'
使い方: scripts/check-figures.sh [オプション]

オプション:
  --tree <dir>          図ツリー (*.svg と *.svg.png を突合)。既定: data/step01_figures/figs
  --figures-dir <dir>   分離出力した図のディレクトリ (例 data/output/bhi/figures)。pHYs のみ検査
  --journal <id>        雑誌プロファイル。--dpi 未指定なら profile.figures.dpi を目標にする
                        (誌によっては 600dpi を求めるので、300 固定では誤った基準で
                        「合格」が出る)
  --article-type <id>   記事種別 (--journal と併用)
  --dpi <n>             目標解像度。優先順は --dpi > --journal の figures.dpi > 300

2 つのモードは守備範囲が違う:
  --tree          … SVG の物理サイズから期待画素数を出し、**実画素数まで検算**する (本体)
  --figures-dir   … 元 SVG が無いため期待画素数を出せず、**pHYs (申告解像度) の確認のみ**
                    ただし pptx 図は書庫を開き、SVG 拡張の位置・SVG 本体と PNG
                    フォールバックの同梱・同梱 PNG の pHYs を検査する

--tree と --figures-dir は併用できる。--figures-dir だけを指定した場合、図ツリーの検査は行わない
= 画素数不足は見つけられない。提出前は両方を回すこと。

--self-test は「この受入テストに識別力があるか」を確かめるモード。
その場で pptx を 1 つ作り、意図的に 2 通り壊して (ベクターが届かない / スライドへ到達できない)、
検査がそれらを落とせることを確認する。図の検査は行わないので他の引数とは併用しない。
「図が黙って非ベクターになる」事故と同型の穴が検査側に開いていないかを見る。
EOF
}

while [ $# -gt 0 ]; do
    case "$1" in
        --tree)         TREE="${2:?--tree にディレクトリを指定してください}"; shift 2 ;;
        --figures-dir)  FIGURES_DIR="${2:?--figures-dir にディレクトリを指定してください}"; shift 2 ;;
        --journal)      JOURNAL="${2:?--journal に id を指定してください}"; shift 2 ;;
        --article-type) ARTICLE_TYPE="${2:?--article-type に種別 id を指定してください}"; shift 2 ;;
        --dpi)          DPI="${2:?--dpi に数値を指定してください}"; shift 2 ;;
        --self-test)    SELF_TEST=1; shift ;;
        -h|--help)      usage; exit 0 ;;
        *)              echo "エラー: 不明な引数 '$1'" >&2; usage; exit 1 ;;
    esac
done

if [ -n "$JOURNAL" ] && [ ! -d "data/journals/$JOURNAL" ]; then
    echo "エラー: 雑誌プロファイル 'data/journals/$JOURNAL' がありません。" >&2
    exit 1
fi

OPTS=()
[ -n "$DPI" ]          && OPTS+=(--dpi "$DPI")
[ -n "$JOURNAL" ]      && OPTS+=(--journal "$JOURNAL")
[ -n "$ARTICLE_TYPE" ] && OPTS+=(--article-type "$ARTICLE_TYPE")
[ -n "$TREE" ]         && OPTS+=(--tree "$TREE")
[ -n "$FIGURES_DIR" ]  && OPTS+=(--figures-dir "$FIGURES_DIR")
# 検査そのものの識別力を確かめるモード (他の引数とは併用しない)
[ "$SELF_TEST" -eq 1 ] && OPTS=(--self-test ${DPI:+--dpi "$DPI"})

# 引数なし (既定の図ツリー・目標 300dpi) では OPTS が空になるので、set -u でも安全な展開にする
docker compose -f "$COMPOSE_FILE" run --rm -u "$(id -u):$(id -g)" pandoc \
    python3 main/step01_figures/check_dpi.py ${OPTS[@]+"${OPTS[@]}"}
