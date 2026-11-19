#!/bin/bash
# build.sh — 原稿ビルド オーケストレータ (図前処理 step01 → docx 化 step02)
#
# docs/architecture.md §2.2。INPUT_ROOT の main.md を投稿用 docx へ変換する。図前処理 (step01) を先に走らせ、
# pandoc + OOXML 後処理 (表罫線 / ネイティブ SVG 埋込 / textbox) を docx-paper-template-pandoc
# コンテナ内で実行する。revise-report.md / cover-letter.md があれば同機構で docx 化する。
#
# INPUT_ROOT は .development マーカーで切替 (docs/architecture.md §4):
#   .development 有り -> data/dummy / 無し -> src   (環境変数 INPUT_ROOT または --input で上書き可)
#
# 使い方:
#   scripts/build.sh [--journal <id>] [--article-type <id>] [--input <dir>] [--skip-figures]
#                    [--no-embed-svg] [--no-relocate]
#
# 出力: data/step02_build/{main,revise-report,cover-letter}.docx
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

COMPOSE_FILE="docker/docker-compose.yml"
OUT_DIR="data/step02_build"
JOURNAL="_default"
ARTICLE_TYPE=""
INPUT_OVERRIDE=""
SKIP_FIGURES=0
EMBED_FLAG=""
RELOCATE_FLAG=""

usage() {
    cat <<'EOF'
使い方: scripts/build.sh [オプション]

オプション:
  --journal <id>        雑誌プロファイル (data/journals/<id>)。既定: _default
  --article-type <id>   記事種別 (profile の article_types を持つ誌のみ。例: bhi の original)。
                        build は種別で出力を変えない — 未知種別の早期エラーと
                        data/step02_build/.journal への記録 (provenance) のために受ける
  --input <dir>         入力ルートを明示 (既定: .development 有り->data/dummy / 無し->src)
  --skip-figures        図前処理 (step01) をスキップ (data/step01_figures を再利用)
  --no-embed-svg        ネイティブ SVG 埋込をしない (PNG フォールバックのみ)
  --no-relocate         textbox の page 配置移動をしない (自然な文書フロー位置に置く)

出力: data/step02_build/{main,revise-report,cover-letter}.docx
EOF
}

while [ $# -gt 0 ]; do
    case "$1" in
        --journal)      JOURNAL="${2:?--journal に id を指定してください}"; shift 2 ;;
        --article-type) ARTICLE_TYPE="${2:?--article-type に種別 id を指定してください}"; shift 2 ;;
        --input)        INPUT_OVERRIDE="${2:?--input にディレクトリを指定してください}"; shift 2 ;;
        --skip-figures) SKIP_FIGURES=1; shift ;;
        --no-embed-svg) EMBED_FLAG="--no-embed-svg"; shift ;;
        --no-relocate)  RELOCATE_FLAG="--no-relocate"; shift ;;
        -h|--help)      usage; exit 0 ;;
        *)              echo "エラー: 不明な引数 '$1'" >&2; usage; exit 1 ;;
    esac
done

# --- INPUT_ROOT 解決 (環境変数 > --input > .development。figures.sh と同一規則) ---
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

# reference.docx は make-reference.sh が profile.yaml から作る生成物。無ければここで作る
# (_default と、自前の reference.docx を使う設定の対象誌。scripts/lib/ensure-reference.sh)
# shellcheck source=lib/ensure-reference.sh
. "$SCRIPT_DIR/lib/ensure-reference.sh"
ensure_reference_docx "$JOURNAL"

RUN="docker compose -f $COMPOSE_FILE run --rm -u $(id -u):$(id -g) pandoc"

echo "== Step 02 原稿ビルド =="
echo "  INPUT_ROOT = $INPUT_ROOT"
echo "  JOURNAL    = $JOURNAL"
echo "  OUT_DIR    = $OUT_DIR"

# --- 原稿が必ず使う入力が、コンテナから見えない場所を指すリンクなら止める ---
# コンテナにはリポジトリしかマウントしないので、絶対パスのリンクやリポジトリの外を指すリンクの先を pandoc は読めない
# (ref.bib なら、文献の無い docx が黙ってできる)。figs の中の個々のファイルは、原稿が使わないものもあるので見ない
# リンクを 1 段ずつたどり、絶対パスのリンク (コンテナの中ではそのパスが無い) か、リポジトリの外に出るリンクなら止める。
# 外に出たかは物理パス (cd -P / pwd -P) で見る — 途中のディレクトリのリンクや論理パスの .. で外に出る形も止める
# (論理パスで見ると、外を指すディレクトリのリンクの下の ref.bib を見逃し、文献の無い docx が黙ってできるため)。
# ループ・深すぎるリンク・行き先の無いリンクも止める
root_p="$(cd -P "$PROJECT_ROOT" && pwd -P)"
for f in main.md ref.bib cover-letter.md revise-report.md figs; do
    p="$INPUT_ROOT/$f"
    [ -e "$p" ] || [ -L "$p" ] || continue
    hops=0; bad=""
    while :; do
        dir_p="$(cd -P "$(dirname -- "$p")" 2>/dev/null && pwd -P)" \
            || { bad="たどれないリンクの下にあるパス"; break; }
        p="$dir_p/$(basename -- "$p")"
        case "$p" in
            "$root_p"/*) ;;
            *) bad="リポジトリの外にあるパス ($p)"; break ;;
        esac
        [ -L "$p" ] || break
        [ "$hops" -lt 20 ] || { bad="深すぎるかループしているリンク"; break; }
        link="$(readlink -- "$p")"
        case "$link" in
            /*) bad="絶対パスのリンク ($link)"; break ;;
        esac
        p="$dir_p/$link"
        hops=$((hops + 1))
    done
    if [ -z "$bad" ] && [ ! -e "$p" ]; then
        bad="行き先の無いリンク"
    fi
    if [ -n "$bad" ]; then
        echo "エラー: $INPUT_ROOT/$f は$badです。" >&2
        echo "  変換はコンテナの中で行い、コンテナからはリポジトリの中しか見えないので、リンクの先を読めません。" >&2
        echo "  実体をリポジトリの中に置くか、リポジトリの中を指す相対リンクにしてください。" >&2
        exit 1
    fi
done
# ホストで見える入力が、コンテナの中からも見えるかを確かめる。途中のディレクトリが「リポジトリの中を指す絶対パスのリンク」の
# 形は、物理パスではリポジトリの中なので上の判定を通るが、コンテナからは読めない
host_seen=()
for f in main.md ref.bib cover-letter.md revise-report.md figs; do
    [ -e "$INPUT_ROOT/$f" ] && host_seen+=("$f")
done
if ! unseen="$(docker compose -f "$COMPOSE_FILE" run --rm -T -u "$(id -u):$(id -g)" pandoc \
        python3 main/step05_package/package.py inputs-visible --input-root "$INPUT_ROOT" "${host_seen[@]}" 2>&1)"; then
    echo "エラー: $INPUT_ROOT の次の入力は、ホストからは見えますが変換を行うコンテナからは見えません: $(printf '%s\n' "$unseen" | tail -n 1 | sed 's/^inputs-visible: //')" >&2
    echo "  コンテナからはリポジトリの中しか見えません。絶対パスの入力ルートや、途中に絶対パスのリンクを挟むパスは使えません。" >&2
    echo "  実体をリポジトリの中に置くか、リポジトリの中を指す相対リンクにしてください。" >&2
    exit 1
fi

# --- 同じ作業ツリーでの build / diff / package の同時実行を止める ---
# (build に加えて diff と package も同じロックを取る)
# 2 つが data/step01_figures/ と data/step02_build/ (画像の一覧 main.docx.images.tsv など) を取り合うと、
# 記録と main.docx が一致したまま別の原稿の図が入りうるため。flock が無い環境では警告だけにする
. "$SCRIPT_DIR/lib/build-lock.sh"
take_build_lock build.sh

# 原稿のほかの入力 (ref.bib / cover-letter.md / revise-report.md / figs/) の中身のハッシュ (main.md だけを見ると、
# 文献やカバーレターや図を直して build し直さないパッケージが照合を通ってしまうため)。
# 「相対パス<TAB>SHA-256」の行を C ロケールの順に並べた全体の SHA-256。生成物の残り (同じ名前の .mmd がある
# figs/mermaid/ の .svg / .pdf) と、*.svg.png (PNG フォールバック) は除く。
# シンボリックリンクはリンクの先の中身を数え、figs の中のディレクトリのリンクもたどる。
# 計算は package.py の _inputs_sha256() だけが持ち、ここはコンテナの中でそれを呼ぶ。ホストで別に計算すると、
# コンテナから見えないリンクの先で package.py と値が食い違い、final が必ず止まるため。
# コンテナから見えないリンクの先 (絶対パス・リポジトリの外) は数えない (build もそのファイルを読めない)。
# -T: 端末を割り当てない (割り当てると出力の行末に CR が付く)
inputs_sha256() {
    docker compose -f "$COMPOSE_FILE" run --rm -T -u "$(id -u):$(id -g)" pandoc \
        python3 main/step05_package/package.py inputs-sha256 --input-root "$1" | tr -d '\r' | tail -n 1
}

# build の前に main.md と原稿のほかの入力のハッシュを取る。最後の記録のときに取り直し、違えば (build の最中に原稿や図が
# 変わった) 記録を書かずに止める (古い docx を「今の原稿から作った」と記録しないため)
MAIN_SHA_BEFORE="$(sha256sum < "$INPUT_ROOT/main.md" | cut -d' ' -f1)"
if ! INPUTS_SHA_BEFORE="$(inputs_sha256 "$INPUT_ROOT")" || ! [[ "$INPUTS_SHA_BEFORE" =~ ^[0-9a-f]{64}$ ]]; then
    echo "エラー: 原稿のほかの入力のハッシュを計算できませんでした (package.py inputs-sha256: '${INPUTS_SHA_BEFORE:-}')" >&2
    exit 1
fi

# --- 図前処理 (step01) ---
if [ "$SKIP_FIGURES" -eq 0 ]; then
    echo "-- 図前処理 (step01) を実行 (--skip-figures で省略可)"
    INPUT_ROOT="$INPUT_ROOT" bash main/step01_figures/figures.sh
else
    echo "-- 図前処理をスキップ (既存 data/step01_figures を再利用)"
    # 既存の前処理の結果が、今の入力ルートの今の figs/ から作ったものかを照合し、違えば止める。
    # 更新時刻を比べるだけでは、別の入力ルートの前処理の結果が残っているとその図が警告なしに main.docx に入る
    # (記録は figures.sh が書く data/step01_figures/.figures.source)
    if ! fig_problem="$(docker compose -f "$COMPOSE_FILE" run --rm -T -u "$(id -u):$(id -g)" pandoc \
            python3 main/step05_package/package.py figures-source check --input-root "$INPUT_ROOT" 2>&1)"; then
        echo "エラー: --skip-figures を付けましたが、$(printf '%s\n' "$fig_problem" | tail -n 1)。" >&2
        echo "  --skip-figures を外して、図の前処理からやり直してください。" >&2
        exit 1
    fi
fi

mkdir -p "$OUT_DIR"

# --- 原稿を docx 化 (main.md は必須。revise-report.md / cover-letter.md は任意) ---
build_one() {
    local doc="$1" out="$2" sha_out="${3:-}"
    echo ""
    $RUN python3 main/step02_build/build_docx.py \
        --input-root "$INPUT_ROOT" --journal "$JOURNAL" \
        ${ARTICLE_TYPE:+--article-type "$ARTICLE_TYPE"} \
        ${sha_out:+--sha256-out "$sha_out"} \
        --doc "$doc" --out "$out" $EMBED_FLAG $RELOCATE_FLAG
}

# どの原稿から build したかの記録は、すべての文書の build が成功した最後に書く。
# 先に消しておかないと、build が途中で失敗したときに前回の記録が残り、package が失敗した版の本文を
# 前回の原稿のものとして照合を通してしまう (失敗した後に原稿を元に戻すとそうなる)
rm -f "$OUT_DIR/.build.source"

# この build が書いた main.docx の SHA-256 の受け渡し (プロセスごとの名前。build_docx.py が置き換える直前に書く)
MAIN_DOCX_SHA_FILE="$OUT_DIR/.main.docx.sha256.$$"
trap 'rm -f "$MAIN_DOCX_SHA_FILE"' EXIT
build_one "main.md" "$OUT_DIR/main.docx" "$MAIN_DOCX_SHA_FILE"

# どの雑誌で build したかを記録する (package.py が --journal と照合し、
# 雑誌体裁の取り違えを警告するため)。--article-type 指定時は 2 行目に
# 種別も記録する (provenance のみ。build の出力は種別で変わらないため照合はしない)。
if [ -n "$ARTICLE_TYPE" ]; then
    printf '%s\n%s\n' "$JOURNAL" "$ARTICLE_TYPE" > "$OUT_DIR/.journal"
else
    printf '%s\n' "$JOURNAL" > "$OUT_DIR/.journal"
fi

for opt in revise-report cover-letter; do
    if [ -f "$INPUT_ROOT/$opt.md" ]; then
        build_one "$opt.md" "$OUT_DIR/$opt.docx"
    elif [ -f "$OUT_DIR/$opt.docx" ]; then
        # 出力先を掃除する。「無いのでスキップ」と言うだけで前回の出力を残すと、
        # 入力ルートを切り替えたときに **別の原稿でビルドした docx** が data/step02_build に
        # 居座り、package が [OK] で提出物 (data/output/<id>/) に並べてしまう (実測)。
        # $OUT_DIR は生成物のディレクトリ (gitignored) なので消してよい。
        rm -f "$OUT_DIR/$opt.docx" "$OUT_DIR/$opt.docx.images.tsv"
        echo "-- $INPUT_ROOT/$opt.md は無し → 前回の $OUT_DIR/$opt.docx を削除 (別原稿の残置を防ぐ)"
    else
        echo "-- $INPUT_ROOT/$opt.md は無し (スキップ)"
    fi
done

# どの原稿から build したかを、すべての文書の build が成功した最後に記録する。package.py が今回の入力ルートと main.md の
# SHA-256 で照合し、提出用 (final) の本文と規定チェックが別の原稿を指すパッケージを作らないようにする
# (「--input で build し、--input なしで package する」「原稿を直して build し直さずに package する」を止める)。
# 書式は「キー<TAB>値」の行。package.py が読むので変えるときは両方を直すこと。
# main_docx_sha256 は、この build が書いた main.docx そのもののハッシュ (build_docx.py が置き換える直前に取ったもの)。
# 同じ作業ツリーで 2 つの build を同時に回すと、記録と main.docx が別の build のものになりうるので、package.py が
# main.docx と照合する
MAIN_DOCX_SHA="$(head -n 1 "$MAIN_DOCX_SHA_FILE" 2>/dev/null || true)"
if [ -z "$MAIN_DOCX_SHA" ]; then
    echo "エラー: build した main.docx のハッシュ ($MAIN_DOCX_SHA_FILE) がありません" >&2
    exit 1
fi
if ! INPUTS_SHA="$(inputs_sha256 "$INPUT_ROOT")" || ! [[ "$INPUTS_SHA" =~ ^[0-9a-f]{64}$ ]]; then
    echo "エラー: 原稿のほかの入力のハッシュを計算できませんでした (package.py inputs-sha256: '${INPUTS_SHA:-}')" >&2
    exit 1
fi
MAIN_SHA="$(sha256sum < "$INPUT_ROOT/main.md" | cut -d' ' -f1)"
if [ "$MAIN_SHA" != "$MAIN_SHA_BEFORE" ] || [ "$INPUTS_SHA" != "$INPUTS_SHA_BEFORE" ]; then
    echo "エラー: build の最中に $INPUT_ROOT の原稿か図・文献などの入力が変わりました。もう一度 build してください" >&2
    echo "  (今の docx は変わる前の原稿から作った可能性があるので、出所の記録を書きません)。" >&2
    exit 1
fi
printf 'input_root\t%s\nmain_sha256\t%s\njournal\t%s\narticle_type\t%s\ninputs_sha256\t%s\nmain_docx_sha256\t%s\n' \
    "$INPUT_ROOT" "$MAIN_SHA" "$JOURNAL" "$ARTICLE_TYPE" \
    "$INPUTS_SHA" "$MAIN_DOCX_SHA" \
    > "$OUT_DIR/.build.source"

echo ""
echo "== ビルド完了: $OUT_DIR 配下 =="
find "$OUT_DIR" -maxdepth 1 -name '*.docx' | sort | sed 's/^/  /'
