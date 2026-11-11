#!/usr/bin/env python3
"""validate.py — 原稿を雑誌プロファイルの limits / lint と照合し警告する (提出前の機械検査)。

docs/architecture.md §2.5 / §5、docs/profile-schema.md。語数・抄録語数・文献数を profile.yaml の limits と比べ、超過を警告
として返す (エラーにはしない。最終判断は実物で行う)。package.py から import され、単独でも動く。

【数え方は近似】Markdown 段階の語数なので、docx レンダリング後のページ数や厳密な語数とは
ずれうる。あくまで提出前の目安。本文 = メタ Div (Title/Author/Affiliation/Corresponding/
Keywords/Abstract/**Legend**) と References 節を除いた散文。抄録 = Abstract custom-style Div の
中身。文献数 = 本文中の一意な引用キー (@key) 数 (相互参照 @fig:/@tbl:/@eq:/@sec: は除外)。

【読むファイル】語数・文献数・lint の大半は `<INPUT_ROOT>/main.md` だけを読む。**例外は記入欄
`<<...>>` の残存検査だけ**で、`cover-letter.md` / `revise-report.md` も読む (どちらも編集部に
届く提出物であるため)。

【語数の数え方と lint】(docs/journal-bhi.md §7.7)
  - 本文語数から**図表の凡例 (`custom-style="Legend"` Div) を除外**する。
  - **BHI lint 群**: タイトル語数・タイトル中の略語・キーワード数・抄録内引用・Declarations の
    6 項目・Abbreviations 節の位置・合成文字 (℃ 等)・数値の桁区切りカンマ・記入欄 `<<...>>` の
    残存・図表の合計点数・図表の題 15 語 / 凡例 300 語・`Legend` Div の `for` 属性と配置・
    `Legend` Div の中身が段落だけか・References が本文の最終節か・連絡著者ブロック。
  - 出力を **「規定違反の可能性 (要修正)」と「参考情報」に区分**する (戻り値は Finding の list)。
  - lint 規則はすべて profile 駆動。**一般作法 (合成文字・単位系・記入欄・凡例の配置) は
    基底 (`journal_profile.DEFAULTS`) に置き**、雑誌側は上書き・追加のみとする 2 層構成
    (判断の記録は docs/profile-schema.md / docs/journal-bhi.md §7.7)。

使い方 (単独):
    python3 validate.py --input-root data/dummy --journal _default
    python3 validate.py --input-root data/dummy/bhi --journal bhi --article-type original
"""

import argparse
import re
import sys
from collections import namedtuple
from pathlib import Path

# profile の読み込み・既定値・記事種別解決は共通モジュールに集約 (docs/profile-schema.md)
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "00_setup" / "lib"))
import journal_profile  # noqa: E402

# ---------------------------------------------------------------------
# 指摘の区分
#
# LEVEL_MUST … 規定違反の可能性。投稿前に直すことを想定する (上限超過・必須記載の欠落・
#              禁止表記・提出物の構造が壊れる配置規則違反)。
# LEVEL_INFO … 参考情報。判断が要る / 機械では断定できない / 規定に照らして「望ましい」止まり。
#
# どちらも**エラーにはしない** (validate は終了コードを 0 のまま返す)。最終判断は実物で行う
# という §2.5 の方針を変えないため。
# ---------------------------------------------------------------------
#
# origin … 検査規則の出所。**基底 (journal_profile.DEFAULTS) 由来のときだけ
#              文字列が入り**、指摘の文末に添えられる。lint の 2 層構成では、合成文字・記入欄・
#              凡例の配置は基底では「欧文組版の一般則」「本テンプレの記法の規約」に過ぎず、
#              その誌の規定を調べた結果ではない。それを「規定違反の可能性」の見出しの下に
#              素のまま並べると、規定に無い事柄を規定違反として突きつけることになる
#              (誤検出と同じく lint への信頼を損なう)。区分そのものは変えず、出所を注記で添える
#              (2 区分は SUBMISSION.md の「規定チェック」節と文書が前提にしているため)。
# ---------------------------------------------------------------------
LEVEL_MUST = "要修正"
LEVEL_INFO = "参考"

Finding = namedtuple("Finding", "level message origin")
Finding.__new__.__defaults__ = (None,)

ORIGIN_BASE = "本テンプレ共通の作法"


def must(msg, origin=None):
    return Finding(LEVEL_MUST, msg, origin)


def info(msg, origin=None):
    return Finding(LEVEL_INFO, msg, origin)


def _origin_note(profile, key):
    """lint.<key> が基底由来なら ORIGIN_BASE を返す (誌が宣言していれば None)。

    `journal_profile.resolve()` が控えた `_lint_declared` (その誌の profile.yaml が自分で
    書いた lint キーの一覧) を見る。控えが無い (resolve() を通していない) profile では None を返し、
    注記を付けない。
    """
    declared = profile.get("_lint_declared")
    if declared is None:
        return None
    return None if key in declared else ORIGIN_BASE


def finding_text(finding):
    """指摘 1 件の表示文 (出所の注記込み)。画面とマニフェストで共用する。"""
    return finding.message + (f" ({finding.origin})" if finding.origin else "")


# custom-style Div のうち本文語数から除外するメタ領域
#
# corresponding (連絡著者ブロック) も除外する。氏名・住所全文・電話・E-mail は
# 規定上 Title page の構成要素であって本文ではない。
#
# legend (図表の凡例) も除外する。判断は「**図の凡例も表の凡例も除外する**」。
# 根拠 (docs/journal-bhi.md §7.7 に同じ記録がある):
#   (a) 規定が本文語数から除外するのは「表・図 / 文献 / 図キャプション」で、**図キャプションは
#       明示的に除外**されている。本テンプレの書き分け規約では凡例が画像記法の外 (Legend Div)
#       にあるので、明示的に落とさないと本文に算入されてしまう。
#   (b) **表の凡例は規定に明示が無い**。ただし規定は表の題を「表の上」・凡例を「表の下」と
#       定めており、題も凡例も**表という提出物の構成要素**として書かれている。除外対象の
#       「表」に題と凡例が含まれると読むのが素直で、図と表で扱いを変える根拠が規定に無い。
#   (c) 図と表の凡例は同じ `Legend` 段落スタイルを共有するため、算入/除外を分けるには
#       「直前が図か表か」の判定に語数計算を依存させることになる。その判定は配置規則が
#       守られている前提に立つので、**規則違反があると語数が静かにずれる**。
# 除外は**費用の見積もりを甘くする側**に効く (超過ページは 1 ページ 2 万円 + 税) ため、
# 除外した語数は概算行に**内訳として必ず表示する** — 編集室の数え方が違ったときに
# 足し戻せるようにするため。
META_STYLES = {"title", "author", "affiliation", "keywords", "abstract", "corresponding", "legend"}

LEGEND_STYLE = "legend"


# =====================================================================
# テキスト前処理
# =====================================================================

def _read_main(input_root):
    md = Path(input_root) / "main.md"
    if not md.is_file():
        return None
    return md.read_text(encoding="utf-8")


def _blank_out(m):
    """マッチを同じ行数の空行に置き換える (行番号を原文と一致させたまま中身だけ落とす)。"""
    return "\n" * m.group(0).count("\n")


FENCE_MARK = "~~~"


def _blank_fence(m):
    """コードフェンスを**目印 1 行 + 同じ行数の空行**に潰す。

    空行に潰すと、`Legend` Div の中身にコードフェンス (本テンプレが正式に
    案内する `{=openxml}` 生ブロックを含む) を書いても、凡例の中身の検査には**空行しか見えず
    原理的に検出できない** — 除去が検査より前に走るためで、規則を足しても直らない。
    pandoc はフェンスを `SourceCode` 段落として出すので、最終パッケージの凡例の集約はそこで止まり
    以降が本文に取り残される (実測で確認した失敗モード)。

    目印に `~~~` を選んだ理由: 英数字を含まないので `_word_tokens()` が語として数えず、
    `#` / `|` / `:::` / `>` を含まないので見出し・表・Div フェンス・引用の判定にも掛からない。
    pandoc は `~~~` も正規のコードフェンス記法として認めるため、原稿に元からある `~~~` の
    フェンスも同じ目印として扱われる (副産物として穴が 1 つ減る)。
    """
    n = m.group(0).count("\n")
    return FENCE_MARK + "\n" * n if n else FENCE_MARK


def _blank_inline(m):
    """インラインコードを空白 1 個に潰す。ただし改行数は保つ。

    `re.sub(r"`[^`]*`", " ", text)` のように改行ごと 1 個の空白に置換してはいけない。
    Markdown のインラインコードは段落内で改行をまたげるので、そういう原稿では
    **以降の指摘の行番号が原文とずれる** (実測: 4 行目の合成文字が L3 と報告された)。
    `_strip_noise` の他の 3 経路も行数を保つ。
    """
    return " " + "\n" * m.group(0).count("\n")


def _strip_noise(text):
    """YAML フロントマター・HTML コメント・コードフェンス・インラインコードを除去。

    YAML フロントマターを除去する (メタ値や連絡先メールが本文語数・文献数に
    紛れ込むのを防ぐ。package.py の _strip_yaml_and_code と挙動を揃える)。

    複数行にまたがる構文は**削除せず、同じ行数の空行に潰す**。
    lint は指摘に行番号を添えるので、除去で行がずれると原稿の別の場所を指してしまう。
    語数・文献数の計算結果は空行が増えても変わらない。
    HTML コメントを落とすのは骨格のためでもある — 骨格
    `data/journals/bhi/skeleton/main.md` は執筆の手引きをコメントで持っており、これを写した原稿には
    日本語の解説文が残る。pandoc は docx に出さないので実害は無いが、Markdown 層の lint は素通しに
    読むため誤検出源になる (禁止文字・記入欄 `<<...>>`・桁区切りカンマのいずれもコメントに現れうる)。
    """
    text = re.sub(r"^---\n.*?\n---\n", _blank_out, text, count=1, flags=re.DOTALL)
    text = re.sub(r"<!--.*?-->", _blank_out, text, flags=re.DOTALL)
    # フェンスは空行ではなく目印 (~~~) に潰す。凡例の中身の検査から
    # 見えなくなるのを防ぐため (下の _blank_fence の説明を参照)。
    text = re.sub(r"```.*?```", _blank_fence, text, flags=re.DOTALL)
    text = re.sub(r"`[^`]*`", _blank_inline, text)
    return text


# =====================================================================
# ブロック走査
#
# lint の多くは「凡例 Div の直前が図か表か」「Abbreviations 節が Abstract と Introduction の
# 間にあるか」のように **文書順の位置関係**を見る。行単位の正規表現では位置関係を持てないので、
# 原稿を文書順のブロック列に均す層を 1 つ置く。
#
# 走査は `.textbox` / `.grid` / `#refs` のような**構造 Div の中へは入り**、
# custom-style Div (Title / Abstract / Legend …) の中へは入らない (中身は散文なので
# ブロックに割る意味がない)。テキストボックスの中に入ったブロックには in_textbox 印を付ける —
# 本文の流れの外なので、図表の点数にも最終パッケージの移設にも数えないため。
# =====================================================================

_RE_DIV_OPEN = re.compile(r"^(:::+)\s*(\{.*\})\s*$")
_RE_DIV_CLOSE = re.compile(r"^:::+\s*$")
_RE_HEADING = re.compile(r"^(#+)\s+(.*?)\s*$")
_RE_TABLE_ROW = re.compile(r"^\s*\|")
_RE_TBL_CAPTION = re.compile(r"^\s*:\s+(\S.*?)\s*$")
_RE_IMAGE = re.compile(r"!\[(?P<alt>[^\]]*)\]\((?P<src>[^)]*)\)(?:\{(?P<attr>[^}]*)\})?")


def _custom_style(attr):
    m = re.search(r'custom-style\s*=\s*"([^"]+)"', attr)
    return m.group(1).strip() if m else None


def _attr_ident(attr):
    m = re.search(r"#([A-Za-z][\w:.-]*)", attr or "")
    return m.group(1) if m else None


def _div_attrs(attr):
    m = re.search(r'\bfor\s*=\s*"([^"]*)"', attr)
    return {
        "style": _custom_style(attr),
        "classes": re.findall(r"\.([A-Za-z][\w-]*)", attr),
        "for": m.group(1).strip() if m else None,
        "ident": _attr_ident(attr),
    }


def _split_ident(caption):
    """`題 {#tbl:x}` を (題, 識別子) に割る。"""
    m = re.search(r"\{([^}]*)\}\s*$", caption)
    if not m:
        return caption.strip(), None
    return caption[:m.start()].strip(), _attr_ident(m.group(1))


def _find_div_close(lines, i, end):
    depth = 1
    while i < end:
        if _RE_DIV_OPEN.match(lines[i]):
            depth += 1
        elif _RE_DIV_CLOSE.match(lines[i]):
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return end        # 閉じ忘れ: 領域の終わりまでを中身とみなす


def _scan_region(lines, start, end, in_textbox, out):
    i = start
    while i < end:
        line = lines[i]

        m = _RE_DIV_OPEN.match(line)
        if m:
            attr = m.group(2)
            close = _find_div_close(lines, i + 1, end)
            a = _div_attrs(attr)
            out.append({"kind": "div", "line": i, "attr": attr, "style": a["style"],
                        "classes": a["classes"], "for": a["for"], "ident": a["ident"],
                        "inner": "\n".join(lines[i + 1:close]), "in_textbox": in_textbox})
            if a["style"] is None:      # 構造 Div (.textbox / .grid / #refs) は中身も走査する
                _scan_region(lines, i + 1, close,
                             in_textbox or "textbox" in a["classes"], out)
            i = close + 1
            continue

        if _RE_DIV_CLOSE.match(line):   # 対応しない閉じフェンス (壊れた入力) は読み飛ばす
            i += 1
            continue

        if not line.strip():
            i += 1
            continue

        m = _RE_HEADING.match(line)
        if m:
            out.append({"kind": "heading", "line": i, "level": len(m.group(1)),
                        "text": m.group(2).strip(), "in_textbox": in_textbox})
            i += 1
            continue

        if _RE_TABLE_ROW.match(line):
            j = i
            while j < end and _RE_TABLE_ROW.match(lines[j]):
                j += 1
            out.append({"kind": "table", "line": i, "title": None, "ident": None,
                        "title_line": None, "in_textbox": in_textbox})
            i = j
            continue

        m = _RE_TBL_CAPTION.match(line)
        if m:
            cap, ident = _split_ident(m.group(1))
            out.append({"kind": "table_caption", "line": i, "text": cap, "ident": ident,
                        "in_textbox": in_textbox})
            i += 1
            continue

        # 段落 (空行 / フェンス / 見出し / 表 / キャプション行のいずれかまで)
        j, buf = i, []
        while j < end:
            nxt = lines[j]
            if (not nxt.strip() or _RE_DIV_OPEN.match(nxt) or _RE_DIV_CLOSE.match(nxt)
                    or _RE_HEADING.match(nxt) or _RE_TABLE_ROW.match(nxt)
                    or _RE_TBL_CAPTION.match(nxt)):
                break
            buf.append(nxt)
            j += 1
        para = "\n".join(buf)
        images = [{"alt": im.group("alt"), "src": im.group("src"),
                   "ident": _attr_ident(im.group("attr") or "")}
                  for im in _RE_IMAGE.finditer(para)]
        out.append({"kind": "image" if images else "para", "line": i, "text": para,
                    "images": images, "in_textbox": in_textbox})
        i = j


def scan_blocks(text):
    """原稿を文書順のブロック列に均す。

    表のキャプション行は隣接する表に畳んで消す — pandoc は `: 題 {#tbl:x}` を表の**前にも後にも**
    書けるので (実際 data/dummy/main.md は後、data/dummy/bhi/main.md は前)、畳まないと
    「凡例 Div の直前が表か」の判定がキャプションの位置で変わってしまう。
    """
    blocks = []
    lines = text.splitlines()
    _scan_region(lines, 0, len(lines), False, blocks)
    for idx, b in enumerate(blocks):
        if b["kind"] != "table":
            continue
        for j in (idx - 1, idx + 1):
            if 0 <= j < len(blocks) and blocks[j]["kind"] == "table_caption" \
                    and not blocks[j].get("_merged"):
                b["title"] = blocks[j]["text"]
                b["ident"] = blocks[j]["ident"]
                b["title_line"] = blocks[j]["line"]
                blocks[j]["_merged"] = True
                break
    return [b for b in blocks if not b.get("_merged")]


def _iter_divs(blocks):
    """pandoc fenced Div を (attr_text, inner) で yield する (文書順)。

    走査は scan_blocks に一本化してあり、**入れ子の Div も yield する** — そうしないと
    `.textbox` の中に置いた `Legend` Div が本文語数の除外対象から漏れる
    (回帰フィクスチャ data/dummy/regression/ が実際にその形を持つ)。

    引数は**走査済みの blocks** (呼び出し側が 1 回だけ走査したもの) を取る。
    """
    for b in blocks:
        if b["kind"] == "div":
            yield b["attr"], b["inner"]


# =====================================================================
# 語数
# =====================================================================

def _word_tokens(text):
    """英数字を含むトークンを語として数える (記号のみのトークンは除外)。

    画像記法の除去は**属性ブロック `{#fig:x}` まで含める**。
    規定が本文語数から除外する「図の題」は `![…](…)` 全体を落とせば除外できるが、
    識別子は括弧の外にあるので、それも落とさないと `{#fig:workflow}` が記号除去後に
    `fig` `workflow` の **2 語**として数えられる (1 図あたり 2 語)。
    """
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)(\{[^}]*\})?", " ", text)   # 画像 (属性ブロック込み)
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)     # リンクはテキストのみ
    text = re.sub(r"[#>*_~|`:]", " ", text)                  # markdown 記号
    return [t for t in text.split() if re.search(r"[0-9A-Za-z]", t)]


def _div_inner(blocks, style):
    """指定 custom-style の Div の中身を文書順に返す (list[str])。

    引数は走査済みの blocks (呼び出し側が 1 回だけ走査したもの)。
    """
    return [b["inner"] for b in blocks
            if b["kind"] == "div" and (b["style"] or "").lower() == style]


def _abstract_inner(blocks):
    """Abstract custom-style Div の中身を返す (無ければ None)。"""
    inners = _div_inner(blocks, "abstract")
    return inners[0] if inners else None


def count_abstract_words(blocks):
    inner = _abstract_inner(blocks)
    if inner is None:
        return None
    # "**Background:**" 等のラベルも語に含む (誌の数え方に近い側へ倒す)
    return len(_word_tokens(inner))


def count_legend_words(floats):
    """図表の凡例 (`Legend` Div) の語数を (図, 表, 対応不明) に分けて返す。

    本文語数からは 3 つとも除外する (META_STYLES の判断記録を参照)。分けて数えるのは
    **除外した内訳を概算行に出す**ためで、編集室の数え方が違ったときに足し戻せるようにする。
    振り分けは「凡例 Div の直前のブロックが画像か表か」で行う — 図と表の凡例は同じ
    `Legend` スタイルを共有しており、他に手がかりが無い。
    「対応不明」は配置規則を破った凡例で、lint が別途 要修正として指摘する。

    floats (analyze_floats() の結果) は必須引数 (走査は呼び出し側で 1 回だけ行う)。
    """
    fig = tbl = other = 0
    for leg in floats["legends"]:
        n = len(_word_tokens(leg["inner"]))
        if leg["target_kind"] == "fig":
            fig += n
        elif leg["target_kind"] == "tbl":
            tbl += n
        else:
            other += n
    return fig, tbl, other


def _drop_abbreviations_section(text, blocks):
    """`Abbreviations` 見出しから、同レベル以上の次の見出しの直前までを落とす。

    正規表現 1 本 (`^#+\\s*Abbreviations\\b.*?(?=^#\\s|\\Z)`) では先読みが
    **第 1 レベルの見出し `^#\\s` に固定**される。節見出しを `##` で書いた原稿では
    Abbreviations から文書末尾までがまるごと落ち、**本文語数が 0 語になりうる**
    (実測 22 語 → 0 語)。そこで走査層の見出し列を使ってレベルで範囲を決める
    (`lint_declarations` が節の範囲を切るのと同じ流儀)。

    blocks は呼び出し側が走査済みのものを渡す。

    **必ず加工前の `text` に対して最初に呼ぶこと**。本関数は `blocks` が持つ
    行番号で切る範囲を決めるので、`text` を先に別の加工に掛けると行番号がずれる。
    しかも本関数は落とした範囲を**1 行の空白に潰す**ため、呼んだ後の文字列は `blocks` の
    行番号と一致しなくなる。ずれてもエラーにはならず略語一覧の除去範囲が別の場所に移るだけなので、
    気づけない形の壊れ方になる (現状の `count_body_words` は `out = text` の直後に呼ぶので一致する)。
    """
    heads = [b for b in blocks if b["kind"] == "heading" and not b["in_textbox"]]
    start = next((b for b in heads if _is_abbrev_heading(b["text"])), None)
    if start is None:
        return text
    lines = text.splitlines()
    end = next((b["line"] for b in heads
                if b["line"] > start["line"] and b["level"] <= start["level"]), len(lines))
    return "\n".join(lines[:start["line"]] + [" "] + lines[end:])


def count_body_words(text, blocks, drop_abbreviations=False, keep_legends=()):
    """本文 (メタ Div と References 節を除いた散文) の概算語数。

    keep_legends に渡した中身を持つ `Legend` Div は**除去せず本文語数に算入する**。
    想定する用途は「対応不明の凡例」= 配置規則を破って直前に図表が無い
    凡例で、最終パッケージの集約から漏れて**提出物では本文に残る**ため、語数の側も実態に
    合わせる。すべての `Legend` を落とすと、規則を破った原稿でだけ語数が実際より少なく出る
    (超過ページは 1 ページ 2 万円 + 税なので、甘い側の誤差になる)。

    drop_abbreviations=True のとき 'Abbreviations' 節 (次の同レベル以上の見出しまで) も除く。
    BHI では「本文語数に抄録と Abbreviations は含まない (Declarations は含む)」として数える
    (規定の文面だけでは決まらない部分の本テンプレートの扱い)。誌が declarations.abbreviations_section: true を
    持つ場合にのみ除外する (同キーを持たない誌では除外しない)。
    """
    # メタ Div を内容ごと除去
    out = text
    if drop_abbreviations:
        # 'Abbreviations' 見出しから次の同レベル以上の見出しの直前までを落とす
        out = _drop_abbreviations_section(out, blocks)
    keep = {s for s in keep_legends if s}
    for attr, inner in _iter_divs(blocks):
        style = (_custom_style(attr) or "").lower()
        if style == LEGEND_STYLE and inner in keep:
            continue                    # 対応不明の凡例は算入する
        if style in META_STYLES:
            # 空の inner だと str.replace("", " ") が全文を 1 文字ずつ分断して
            # 破壊するためスキップ。置換も最初の 1 回に限定して偶然一致の過剰除去を防ぐ。
            if not inner.strip():
                continue
            out = out.replace(inner, " ", 1)
    # References 節以降を除去 (見出し '# References' から末尾)
    out = re.split(r"^#+\s*References\b.*$", out, maxsplit=1, flags=re.MULTILINE | re.IGNORECASE)[0]
    # refs Div ({#refs}) を除去
    out = re.sub(r"^:::+\s*\{#refs\}.*?^:::+\s*$", " ", out, flags=re.DOTALL | re.MULTILINE)
    # 表行・キャプション行・Div フェンス行を落とす
    kept = []
    for line in out.splitlines():
        if re.match(r"^\s*\|", line):            # 表
            continue
        if re.match(r"^:::+", line):             # Div フェンス
            continue
        if re.match(r"^\s*:\s+\S", line):        # 表/図キャプション (: caption)
            continue
        kept.append(line)
    return len(_word_tokens("\n".join(kept)))


def count_references(text):
    """本文中の一意な引用キー数 (相互参照 fig:/tbl:/eq:/sec: は除外)。"""
    # refs Div を除外
    body = re.sub(r"^:::+\s*\{#refs\}.*?^:::+\s*$", " ", text, flags=re.DOTALL | re.MULTILINE)
    keys = set()
    for m in re.finditer(r"@([A-Za-z0-9_][\w:.-]*)", body):
        # @ の直前が英数字ならメール (user@example.com) とみなし除外。
        if m.start() > 0 and body[m.start() - 1].isalnum():
            continue
        key = m.group(1).rstrip(".")     # 末尾ピリオド (@key.) を落とす (ハイフンは bibkey の一部なので残す)
        if not key:
            continue
        if key.split(":", 1)[0].lower() in ("fig", "tbl", "eq", "sec", "lst"):
            continue
        keys.add(key)
    return len(keys)


def _citation_keys(text):
    """引用キーの出現位置つき一覧 (相互参照・メールアドレスは除外)。"""
    out = []
    for m in re.finditer(r"@([A-Za-z0-9_][\w:.-]*)", text):
        if m.start() > 0 and text[m.start() - 1].isalnum():
            continue
        key = m.group(1).rstrip(".")
        if not key or key.split(":", 1)[0].lower() in ("fig", "tbl", "eq", "sec", "lst"):
            continue
        out.append(key)
    return out


# =====================================================================
# 図・表・凡例の対応づけ
# =====================================================================

def analyze_floats(blocks):
    """図・表・凡例を文書順に拾い、凡例を直前の図表へ結びつける。

    対応づけの根拠は **位置だけ**である。`for="fig:x"` 属性は docx に出ず、
    最終パッケージの集約 (relocate.py) も位置しか見ない。つまり `for` は「冗長だが検算に使える情報」であり、
    ここで位置と突き合わせて初めて意味を持つ。

    凡例が図表の直後に無い場合 (前置き / 間に本文段落 / 節の頭) は target を結びつけず
    orphan として返す — その凡例は最終パッケージの集約から漏れて本文に取り残される。
    """
    figures, tables, legends = [], [], []
    last_float = None
    prev = None       # 直前の意味のあるブロックの種別
    for b in blocks:
        kind = b["kind"]
        if kind == "image":
            for im in b["images"]:
                rec = {"kind": "fig", "ident": im["ident"], "title": im["alt"],
                       "line": b["line"], "in_textbox": b["in_textbox"], "legends": []}
                figures.append(rec)
                last_float = rec
            # kind == "image" は「画像が 1 つ以上ある」ことを意味するので b["images"] では分岐しない
            # (`"float" if b["images"] else "para"` の else 側には到達しない)。
            prev = "float"
        elif kind == "table":
            rec = {"kind": "tbl", "ident": b["ident"], "title": b["title"],
                   "line": b["line"], "title_line": b["title_line"],
                   "in_textbox": b["in_textbox"], "legends": []}
            tables.append(rec)
            last_float = rec
            prev = "float"
        elif kind == "div" and (b["style"] or "").lower() == LEGEND_STYLE:
            leg = {"line": b["line"], "for": b["for"], "inner": b["inner"],
                   "in_textbox": b["in_textbox"], "target": None, "target_kind": None}
            # 直前が図表そのものか、直前が同じ図表に付いた凡例なら結びつける
            # (凡例 Div を 2 つ続けて書いてもよい。最終パッケージは「直後に連続する Legend 段落すべて」を
            #  1 組として動かすので、複数 Div でも同じ扱いになる)
            #
            # **テキストボックスの内外をまたぐ結合はしない**。
            # 走査層は構造 Div の中へ入るので、箱の中の図表と外の図表が同じ列に並ぶ。またいで結合すると、
            # 箱を閉じた直後に置いた凡例が箱の中の図に結びつき、`for` を書いていない原稿では
            # **指摘が 1 件も出ないまま**その凡例が本文に取り残される (最終パッケージの集約は箱の中を
            # 対象外にするため)。しかも語数だけは除外されるので本文語数が過少になる。
            # 結合しなければ「直前に図・表がありません」が要修正として出る。
            if (prev in ("float", "legend") and last_float is not None
                    and last_float["in_textbox"] == b["in_textbox"]):
                leg["target"] = last_float
                leg["target_kind"] = last_float["kind"]
                last_float["legends"].append(leg)
            legends.append(leg)
            prev = "legend"
        elif kind == "table_caption":
            # 表に畳めなかった孤立キャプション (表と隣接していない)。図表としては数えない
            prev = "para"
        else:
            prev = "para"
            last_float = None
    return {"figures": figures, "tables": tables, "legends": legends}


# =====================================================================
# lint 群 (すべて profile 駆動。キーが無い雑誌では発火しない)
# =====================================================================

def _norm(s):
    """見出し・項目名の照合用に正規化する (小文字化 / 空白の畳み込み / アポストロフィ統一)。"""
    s = (s or "").replace("’", "'").replace("‘", "'")
    s = re.sub(r"[*_`]", "", s)
    return re.sub(r"\s+", " ", s).strip().lower().rstrip(":.")


def _loc(line):
    """指摘に添える位置 (1 始まりの行番号)。_strip_noise が行数を保つので原文と一致する。

    「行数を保つ」は 4 経路すべてで成り立つ。ただし**対応の取れない引用符**
    (奇数個のバックティック等) のような壊れた入力では、除去範囲そのものが意図とずれるため
    一致を保証しない。
    """
    return f"L{line + 1}"


def lint_title(blocks, profile):
    """タイトルの語数と、略語らしき全大文字語。

    **どちらも `limits.title_words` を持つ誌でだけ掛ける**。規定でタイトルの語数制限と
    「略語は分野で一般的なもの以外不可」は同じ Title 節にあり、片方だけ定める誌が考えにくいため、
    略語の検査に別キーを起こさず同じキーで発火させる (キー増殖を避ける)。
    """
    out = []
    limit = (profile.get("limits") or {}).get("title_words")
    inners = _div_inner(blocks, "title")
    if not inners:
        return out
    title = inners[0]
    words = _word_tokens(title)
    if limit and len(words) > int(limit):
        out.append(must(f"タイトルの語数 {len(words)} が上限 {limit} 語を超過しています"))
    if limit:
        # 略語の可否は「分野で一般的か」の判断が要るので参考情報に留める (規定 Title 節)。
        # 2 文字以上の全大文字語だけを拾う (I / A などの 1 文字は落とす)。
        abbrs = sorted({w for w in re.findall(r"\b[A-Z][A-Z0-9-]{1,}\b", title)})
        if abbrs:
            out.append(info(f"タイトルに略語らしき語があります ({', '.join(abbrs)})。"
                            "規定は「分野で一般的なもの以外は不可」としています"))
    return out


def lint_keywords(blocks, profile):
    """キーワード数が limits.keywords ([下限, 上限]) の範囲内か。

    Keywords Div の中身は `**Keywords:** a; b; c` のようなラベル込みの自由文なので、
    (1) 先頭のラベル (`**Keywords:**` / `Keywords:`) を落とし、
    (2) `;` があれば `;` で、無ければ `,` で割る、という規約にした。
        医学用語 (MeSH) は "Drug-Related Side Effects and Adverse Reactions" のように
        語中にカンマを含みうるので、セミコロンを優先する。
    """
    rng = (profile.get("limits") or {}).get("keywords")
    if not rng:
        return []
    lo, hi = (list(rng) + [None, None])[:2] if isinstance(rng, (list, tuple)) else (1, rng)
    inners = _div_inner(blocks, "keywords")
    if not inners:
        return [must("Keywords の Div (custom-style=\"Keywords\") が見当たりません")]
    body = re.sub(r"^\s*\**\s*key\s*words?\s*\**\s*[:：]\s*\**\s*", "", inners[0].strip(),
                  flags=re.IGNORECASE)
    sep = ";" if ";" in body else ","
    words = [w.strip(" .　") for w in body.split(sep)]
    words = [w for w in words if w]
    n = len(words)
    if (lo and n < int(lo)) or (hi and n > int(hi)):
        return [must(f"キーワード数 {n} が規定の {lo}〜{hi} 語の範囲外です "
                     f"(区切りは '{sep}' とみなしました: {' / '.join(words)})")]
    return []


def lint_abstract_citations(blocks, profile):
    """抄録内の文献引用 (abstract.citations_allowed: false のとき)。"""
    if (profile.get("abstract") or {}).get("citations_allowed", True):
        return []
    inner = _abstract_inner(blocks)
    if inner is None:
        return []
    keys = _citation_keys(inner)
    if not keys:
        return []
    return [must(f"抄録に文献引用があります ({', '.join(sorted(set(keys)))})。"
                 "この雑誌は抄録での引用を認めていません")]


def _norm_item(s):
    """項目名の照合用の正規化 (アポストロフィ除去 + 単複の畳み込み)。

    `Authors' contributions` と `Author contributions` を同じものとして扱うために、
    アポストロフィを落とし、4 文字以上の語の末尾 `s` を落とす
    (`authors' contributions` → `author contribution`)。両辺に同じ処理を掛けるので
    単複の取り違えだけが吸収され、別語同士が一致することはない。
    """
    s = _norm(s).replace("'", "")
    return " ".join(w[:-1] if len(w) > 3 and w.endswith("s") else w for w in s.split())


def _item_matches(present, want):
    """原稿の見出し present が要求項目 want に相当するか (双方向の前方一致)。

    `present == want or present.startswith(want)` の一方向だけでは、原稿の見出しが
    要求名より**短い**ときに一致しない。`Author contributions` (単数) や
    `Data availability` (statement なし) という医学系誌で普通の表記が「欠落」と報告されてしまう。
    逆向きの前方一致を許すと `Data` のような 1 語の見出しまで通ってしまうので、
    短い側が 2 語以上のときに限る。
    """
    if present == want or present.startswith(want):
        return True
    return want.startswith(present) and len(present.split()) >= 2


def lint_declarations(blocks, profile):
    """Declarations の必須 6 項目が見出しとして揃っているか。"""
    required = (profile.get("declarations") or {}).get("required")
    if not required:
        return []
    # テキストボックス内の見出しを除く (本文の流れの外にあるものを
    # 必須節と数えないため)。lint_abbreviations / lint_references_last と規則を揃えた。
    headings = [b for b in blocks if b["kind"] == "heading" and not b["in_textbox"]]
    out = []
    # Declarations 節の範囲 (見出し 'Declarations' から次の同レベル以上の見出しまで) を切る
    start = next((i for i, h in enumerate(headings) if _norm(h["text"]) == "declarations"), None)
    if start is None:
        out.append(must("Declarations 節の見出しが見当たりません "
                        "(規定は 6 項目すべてを必須としています)"))
        scope = headings
    else:
        level = headings[start]["level"]
        end = next((i for i in range(start + 1, len(headings))
                    if headings[i]["level"] <= level), len(headings))
        scope = headings[start + 1:end]
    present = [_norm_item(h["text"]) for h in scope]
    missing = [str(r) for r in required
               if not any(_item_matches(p, _norm_item(r)) for p in present)]
    if missing:
        out.append(must("Declarations の必須項目が見当たりません: " + " / ".join(missing)
                        + " (該当が無い場合も \"Not applicable\" と書く必要があります)"))
    return out


def _is_abbrev_heading(heading_text):
    """`Abbreviations` / `Abbreviations and acronyms` のような見出しか。"""
    return _norm(heading_text).startswith("abbreviations")


def lint_abbreviations(text, blocks, profile):
    """Abbreviations 節が Abstract と Introduction の間にあるか。

    **節そのものが無い場合は参考情報に留める** — 規定は「Abstract と Introduction の間に置く」と
    いう**配置**を定めており、略語を使わない原稿にまで一覧を要求してはいないため。
    節はあるが位置が違う場合は規定の配置に反するので要修正にする。

    位置は「Abbreviations が文書の最初の見出しか」(`idx != 0`) ではなく
    **「Abbreviations の直後の見出しが Introduction か」**で判定する。前者は本テンプレの規約
    (タイトル・抄録を見出しではなく Div で書く) に暗黙に依存しており、原稿に `# Abstract` という
    見出しを 1 つ足しただけで、配置が規定どおりでも要修正が出る (実測)。「位置」ではなく
    「見出しの順番の番号」を見ることになるためである。
    """
    if not (profile.get("declarations") or {}).get("abbreviations_section"):
        return []
    headings = [b for b in blocks if b["kind"] == "heading" and not b["in_textbox"]]
    idx = next((i for i, h in enumerate(headings) if _is_abbrev_heading(h["text"])), None)
    if idx is None:
        return [info("Abbreviations 節が見当たりません。略語を使う場合は "
                     "Abstract と Introduction の間に一覧を置いてください")]
    out = []
    loc = _loc(headings[idx]["line"])
    nxt = headings[idx + 1] if idx + 1 < len(headings) else None
    if nxt is None:
        out.append(must(f"Abbreviations 節 ({loc}) の後ろに節がありません。"
                        "規定は Abstract と Introduction の間に置くよう定めています"))
    elif not _norm(nxt["text"]).startswith("introduction"):
        out.append(must(f"Abbreviations 節 ({loc}) の直後の節が "
                        f"'{nxt['text']}' です。規定は Abstract と Introduction の"
                        "間に置くよう定めています"))
    abs_div = next((b for b in blocks if b["kind"] == "div"
                    and (b["style"] or "").lower() == "abstract"), None)
    if abs_div is not None and abs_div["line"] > headings[idx]["line"]:
        out.append(must(f"Abbreviations 節 ({loc}) が Abstract "
                        f"({_loc(abs_div['line'])}) より前にあります"))
    return out


# 合成 1 文字 → 規定が求める書き方 (Units 節 4: 度記号 "°" + 大文字 "C" で書く)
_FORBID_HINTS = {"℃": "°C", "℉": "°F", "㎎": "mg", "㎏": "kg", "㎜": "mm",
                 "㎝": "cm", "㎡": "m^2^", "㎥": "m^3^", "㎕": "µL", "㎖": "mL", "㎗": "dL"}


def lint_forbidden_chars(text, profile):
    """lint.forbid_chars に挙げた合成文字の使用。"""
    chars = (profile.get("lint") or {}).get("forbid_chars")
    if not chars:
        return []
    origin = _origin_note(profile, "forbid_chars")
    lines = text.splitlines()
    hits = {}
    for i, line in enumerate(lines):
        for ch in chars:
            if ch and ch in line:
                hits.setdefault(ch, []).append(_loc(i))
    out = []
    for ch, locs in hits.items():
        hint = _FORBID_HINTS.get(ch)
        out.append(must(f"合成 1 文字 '{ch}' を使っています ({', '.join(locs[:8])}"
                        + ("…" if len(locs) > 8 else "") + ")"
                        + (f" — '{hint}' と書いてください" if hint else ""), origin))
    return out


_RE_URL = re.compile(r"https?://\S+|www\.\S+")
# 全角カンマ (，) による桁区切りも拾う (日本語入力で書かれた原稿では起こりうる)。
_RE_THOUSANDS = re.compile(r"(?<![\w.,，])\d{1,3}(?:[,，]\d{3})+(?![\w])")


def lint_thousands_separator(text, profile):
    """数値の桁区切りカンマ (tables.thousands_separator: false のとき)。

    誤検出の除外範囲:
      - **HTML コメント / コードは `_strip_noise` が既に落としている** (骨格の日本語解説文が
        誤検出源になるため)。
      - **URL** は行から取り除いてから照合する (クエリ文字列に `1,000` 形式が現れうる)。
      - **References 節と `#refs` Div** は照合しない (文献の巻号ページに桁区切りは出ないが、
        原稿側で手書きした文献リストを持つ誌もあるため範囲から外す)。
      - パターンは `1,234` / `12,345,678` のような**桁区切りの形をしたものだけ**に絞る
        (前後が英数字なら拾わない)。`^1,2^` のような上付き所属番号や日付は掛からない。
    **表の中も照合する** — 規定は Tables 節でこの規則を述べているが、同じ原稿の本文だけ
    カンマ区切りにする理由が無く、実際 BHI の検証用ダミーは本文でも "12 000" と書いている。
    """
    if (profile.get("tables") or {}).get("thousands_separator", True):
        return []
    body = re.split(r"^#+\s*References\b.*$", text, maxsplit=1,
                    flags=re.MULTILINE | re.IGNORECASE)[0]
    body = re.sub(r"^:::+\s*\{#refs\}.*?^:::+\s*$", " ", body, flags=re.DOTALL | re.MULTILINE)
    hits = []
    for i, line in enumerate(body.splitlines()):
        for m in _RE_THOUSANDS.finditer(_RE_URL.sub(" ", line)):
            hits.append(f"{m.group(0)} ({_loc(i)})")
    if not hits:
        return []
    return [must("数値の桁区切りカンマを使っています: " + ", ".join(hits[:8])
                 + ("…" if len(hits) > 8 else "")
                 + " — 規定は空白区切り (10 000) を求めています")]


# 記入欄は**改行をまたぐ**ことがある (骨格 main.md に 3 件 / cover-letter.md に 3 件。実測)。
# 行単位で照合すると取りこぼすので全文に対して掛ける。中身に `<` `>` が単独で現れても
# (引用ブロックの `> ` など) 拾えるよう、境界は `<<` / `>>` の不在で表す。
#
# 境界には**空行 (段落の切れ目)** も使う。境界が「`<<` と `>>` が一定の文字数以内に
# あること」だけだと、本文に単独で現れた `<<`
# (左シフト演算子や「はるかに小さい」の意味) が、段落をまたいで無関係な `>>` と対になり、
# 巨大な文字列を記入欄として要修正で報告する (実測)。骨格の記入欄は改行はまたぐが
# 空行はまたがないので、この境界で誤検出だけが落ちる。上限は 2000 文字
# (段落境界が効くので暴走の心配が無い。400 文字では長い記入欄を
# **1 件も報告せず取り逃す**)。
_RE_PLACEHOLDER = re.compile(r"<<(?:(?!<<|>>|\n[ \t]*\n).){1,2000}>>", re.DOTALL)

# 記入欄が残ったまま提出される文書 (validate が読むのは main.md だけなので、任意文書はここで補う)
_PLACEHOLDER_FILES = ("cover-letter.md", "revise-report.md")


def lint_placeholders(text, profile, input_root=None):
    """骨格の記入欄 `<<...>>` の残存。

    タイトルや所属が記入欄のまま編集部へ届くと形式審査で差し戻される。骨格の解説は
    HTML コメントで書かれており `_strip_noise` が落とすので、コメント中の `<<...>>` は掛からない。

    **pandoc の扱いは記入欄の中身によって 3 通りに分かれる** (実測。骨格
    `data/journals/bhi/skeleton/main.md` の記入欄 34 種 = 48 箇所を pandoc に通して確認した。
    種類 = 同じ文面の記入欄を 1 つに数えたもの):
      (a) そのまま残る … 中身にカンマ・日本語・先頭が数字 のいずれかがある場合
          (`<<Title of the Manuscript in Title Case, Not Exceeding 30 Words>>` など 18 種)
      (b) **中身が消えて `<>` だけが残る** … 中身が HTML タグとして解釈できる場合
          (`<<Given-name Family-name>>` `<<Department>>` など **15 種 = 28 箇所**。pandoc が
          `<Given-name Family-name>` を生の HTML タグとみなし docx 出力で捨てる)
      (c) メールリンクになる … `<<name@example.org>>` (pandoc の自動リンク)
    **危ないのは (b)** である — 記入欄が消えて `<>` だけになるので、docx を通し読みしても
    「書き忘れ」ではなく組版のごみに見え、著者名や所属が空欄のまま投稿されうる。
    「記入欄はそのまま docx に出るので見れば分かる」は (a) にしか当てはまらない。
    **Markdown 層で捕まえるほかない**。
    """
    if not (profile.get("lint") or {}).get("placeholder_markers"):
        return []
    origin = _origin_note(profile, "placeholder_markers")
    targets = [("main.md", text)]
    out = []
    if input_root:
        for name in _PLACEHOLDER_FILES:
            path = Path(input_root) / name
            if not path.is_file():
                continue
            # 読み込みを例外処理で囲む。read_text をそのまま
            # 呼ぶと、任意提出物が UTF-8 でない / 読み取り権限が無いだけで validate が
            # 例外で落ち、提出物を組み立てる最終工程 (package.sh) が異常終了する。
            try:
                targets.append((name, _strip_noise(path.read_text(encoding="utf-8"))))
            except OSError as e:
                out.append(info(f"{name} を読めなかったので記入欄の検査をしていません ({e})"))
            except UnicodeDecodeError:
                out.append(info(f"{name} が UTF-8 として読めなかったので"
                                "記入欄の検査をしていません"))
    for name, body in targets:
        hits = []
        for m in _RE_PLACEHOLDER.finditer(body):
            frag = re.sub(r"\s+", " ", m.group(0)).strip()
            hits.append(f"{frag[:60]}{'…' if len(frag) > 60 else ''} "
                        f"({_loc(body.count(chr(10), 0, m.start()))})")
        if hits:
            out.append(must(f"{name} に骨格の記入欄 `<<...>>` が {len(hits)} 箇所残っています: "
                            + ", ".join(hits[:6]) + ("…" if len(hits) > 6 else ""), origin))
    return out


# 凡例 Div の中身は段落だけであること。箇条書き・表・見出し・引用・入れ子 Div は
# pandoc が `Legend` 以外の段落スタイルを付けるため、最終パッケージの凡例の集約がそこで止まる。
#
# 見落としやすいのは次の 3 つで、いずれも生成 docx で `Legend` の間に別スタイルの段落が
# 挟まることを実測した。
#   - コードフェンス (` ``` ` / `~~~`)  → `SourceCode`。**目印 `~~~` で拾う** (_blank_fence)
#   - 空白 4 個以上の字下げ            → `SourceCode`。長い凡例を読みやすくしようとして
#                                        **偶然起きる**のがいちばん厄介である
#   - 定義リスト (`用語` の次行に `: 説明`) → `DefinitionTerm` / `Definition`。
#                                        「凡例で略語を再定義する」という BHI の要求を
#                                        素直に書くと出てくる形である
# 脚注定義と水平線も同じ理由で拾う (どちらも段落にならない)。
#
# **判定は pandoc の読み方に合わせてある**。正解は pandoc 3.6.4 の AST で決めた (候補 約 200 行 × 位置)。
#   - **番号つきリストは数字だけではない**。凡例を `(A) …` で
#     始めると pandoc は `OrderedList (UpperAlpha, TwoParens)` として読み、段落スタイルが `Legend`
#     でなくなって**集約されずに本文へ取り残される**。pandoc の fancy list
#     (英字 1 字・ローマ数字・`#`・`@`、区切り `.` / `)` / `(…)`) を `_ordered_list_start()` で見る。
#   - **規則を全行に掛けると、段落の途中の行で誤検出する**。pandoc の markdown は
#     リスト・見出し・引用・字下げのコードブロック・表・脚注定義・水平線を**ブロックの先頭でしか
#     始めない** (段落の途中の行は前の行の続きとして読む)。長い凡例を折り返した行が
#     `2020. Data were …` や `(A) and (B) …` で始まっても、それは段落の続きであって事故ではない。
#     そこで規則ごとに「どの位置の行に掛けるか」を持たせた (下の _LEGEND_RULES の 3 列目)。
#     「長い凡例の**続きの行**を字下げするとコードブロックになる」は誤りで、
#     続きの行の字下げは段落に吸収される (生成 docx でも `Legend` 1 段落のまま)。
#     コードブロックになるのは**空行のあとの字下げ** (= 字下げした新しい段落) である。
#   - 位置によってだけ現れる構造も拾う: 1 行だけの段落の直後の `===` / `---` (setext 見出し)、
#     `***` / `___` / `* * *` (水平線)、`~ 説明` (定義リストのもう 1 つの記法)。
_ROMAN_RE = r"M*(?:CM)?D?(?:CD)?C*(?:XC)?L?(?:XL)?X*(?:IX)?V?(?:IV)?I*"
# 区切りの前までの「番号」。pandoc の読み方 (Text.Pandoc.Parsing の anyOrderedListMarker) に揃える:
# 数字 (ASCII) / `#` / `@` + ラベル / 英字 1 字 / ローマ数字 (大小どちらか一方で綴ったもの)。
_RE_OL_MARKER = re.compile(
    r" {0,3}(?P<open>\()?"
    r"(?P<num>[0-9]+|#|@[\w-]*|[A-Za-z]|(?=[ivxlcdm])" + _ROMAN_RE.lower()
    + r"|(?=[IVXLCDM])" + _ROMAN_RE + r")"
    r"(?P<delim>[.)])(?P<rest>.*)")
_ROMAN_VALUE = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100, "D": 500, "M": 1000}


def _roman_value(s):
    vals = [_ROMAN_VALUE[c] for c in s.upper()]
    return sum(-v if i + 1 < len(vals) and v < vals[i + 1] else v for i, v in enumerate(vals))


def _ordered_list_start(line):
    """ブロックの先頭にあるこの行を、pandoc が番号つきリストの始まりとして読むか。

    pandoc 3.6.4 の AST を正解にして決めた規則:
      - 番号: 数字 / `#` / `@` (+ 英数字・`_`・`-` のラベル) / 英字 1 字 (a〜z・A〜Z) /
        ローマ数字 (`iv` `XII` など。`IIV` `ivx` のような綴りの崩れたものは読まない)
      - 区切り: `X.` / `X)` / `(X)`。直後は空白か行末でなければならない (`(A)x` `(A):` は段落)
      - **大文字 1 字 + ピリオドは空白が 2 個要る** (`A. Smith` のような頭文字を誤読しないため)。
        ローマ数字で値が 1 / 5 / 10 / 50 / 100 / 500 / 1000 のもの (`I.` `C.` …) も同じ扱い。
        行末で終わる場合はリストになる (`A.` だけの行)
      - `p. 5` (小文字の p・ピリオド・空白 1 個・数字) はページ番号とみなしてリストにしない
      - 行頭の空白は 3 個まで (4 個以上は字下げのコードブロック)
    タブは呼び出し側で 4 桁の位置へ展開しておくこと (pandoc も読む前に展開する)。
    """
    if re.match(r" {0,3}p\. [0-9]", line):
        return False
    m = _RE_OL_MARKER.match(line)
    if not m or not m.group("num"):
        return False
    num, delim, rest = m.group("num"), m.group("delim"), m.group("rest")
    if m.group("open") and delim != ")":
        return False
    if delim == "." and not m.group("open") and num.isalpha() and num.isupper() \
            and (len(num) == 1 or _roman_value(num) in _ROMAN_VALUE.values()):
        return rest.strip() == "" or rest.startswith("  ")
    return rest == "" or rest[0] == " "


# 凡例 Div の中身の規則: (判定, 種類, どの位置の行に掛けるか)。**1 行につき先に当たった 1 つ**を採る
# (`* * *` を箇条書きと水平線の両方に数えないため。字下げのコードブロックを最初に置くのは、
# 空白 4 個以上で始まる行は中身が何であれコードブロックになるため)。
#   "start" … ブロックの先頭 (Div の 1 行目か、空行の直後の行)
#   "setext" … 1 行だけの段落の 2 行目 (直前の行がブロックの先頭で、この行がブロックの先頭でない)
#   "deflist" … 直前の空行でない行が 1 行だけの段落で、間の空行が 1 行以下
#   "any" … どこでも (コードフェンスは段落の途中でも始まる。Div のフェンスは外側の Div を閉じうる)
#   表は区切りの行で見分ける (pandoc の 3 つの書き方。docx ではどれも `Legend` の外の表になり、題の無い表として
#   末尾へ移される): pipe table の区切り (`---|---`。先頭の `|` の有無を問わない) と simple table の区切り
#   (`----  ----`) はブロックの 2 行目、grid table の罫線 (`+---+---+`) はブロックの先頭。
#   先頭が `|` の 1 行だけ (行ブロック) と脚注の定義 (`[^n]: …`) は docx でも `Legend` 段落のまま並ぶので拾わない。
#   単独の画像の段落 (`![…](…)`) は docx で図とキャプションになり、集約がそこで止まる。
_LEGEND_RULES = [
    (re.compile(r"~~~").match, "コードブロック", "any"),
    (re.compile(r":::+").match, "入れ子の Div", "any"),
    (re.compile(r" {4,}\S").match, "字下げのコードブロック", "start"),
    (re.compile(r" {0,3}\+(?:[-=:]+\+)+[ \t]*$").match, "表", "start"),
    (re.compile(r" {0,3}([-*_])(?:[ \t]*\1){2,}[ \t]*$").match, "水平線", "start"),
    (re.compile(r" {0,3}[-*+](?:[ \t]|$)").match, "箇条書き", "start"),
    (_ordered_list_start, "番号つきリスト", "start"),
    (re.compile(r" {0,3}!\[").match, "画像", "start"),
    (re.compile(r"#+(?:[ \t]|$)").match, "見出し", "start"),
    (re.compile(r" {0,3}\|?[ \t]*:?-+:?[ \t]*(?:\|[ \t]*:?-+:?[ \t]*)+\|?[ \t]*$").match, "表", "setext"),
    (re.compile(r" {0,3}-{2,}(?:[ \t]+-{2,})+[ \t]*$").match, "表", "setext"),
    (re.compile(r"(?:=+|-+)[ \t]*$").match, "見出し", "setext"),
    (re.compile(r" {0,3}>").match, "引用ブロック", "start"),
    (re.compile(r" {0,2}[:~][ \t]").match, "定義リスト", "deflist"),
]


def legend_non_para_kinds(inner):
    """凡例 Div の中身 (`_strip_noise` 済みの行) から、段落にならない構造の種類を出現順に返す。"""
    lines = [ln.expandtabs(4) for ln in inner.splitlines()]
    blank = [not ln.strip() for ln in lines]
    start = [i == 0 or blank[i - 1] for i in range(len(lines))]
    kinds = []
    for i, line in enumerate(lines):
        if blank[i]:
            continue
        prev = next((j for j in range(i - 1, -1, -1) if not blank[j]), None)
        where_ok = {
            "any": True,
            "start": start[i],
            "setext": not start[i] and i > 0 and start[i - 1],
            # 用語は 1 行に限られる (2 行の段落の後の `: x` は段落の続き)。空行は 1 行まで
            "deflist": prev is not None and i - prev <= 2 and start[prev],
        }
        for match, label, where in _LEGEND_RULES:
            if where_ok[where] and match(line):
                if label not in kinds:
                    kinds.append(label)
                break
    return kinds


def lint_legend_placement(blocks, floats, profile):
    """`Legend` Div の配置規則と中身を検査する。

    この記法は「凡例 Div を対象の直後に置く」という**位置だけ**で対応関係を表しており、
    規則を破ってもビルドは正常終了し警告も出ない (実測 4 パターン)。最終パッケージの集約先の
    振り分けも下の語数検査も、この配置規則が守られている前提に立つ。
    """
    if not (profile.get("lint") or {}).get("legend_placement"):
        return []
    origin = _origin_note(profile, "legend_placement")
    out = []
    idents = {f["ident"] for f in floats["figures"] + floats["tables"] if f["ident"]}
    for leg in floats["legends"]:
        loc = _loc(leg["line"])
        # (0) 配置: 直前が図表でない凡例は最終パッケージの集約から漏れ、本文に取り残される
        if leg["target"] is None:
            out.append(must(f"凡例 Div ({loc}) の直前に図・表がありません。凡例は対象の図 "
                            "(画像段落) / 表 (題 + 表) の直後に置いてください "
                            "— この位置だと最終パッケージの集約から漏れて本文に残ります", origin))
        else:
            ref = leg["for"]
            if ref is None:
                # 対象に識別子が無ければ `for` は書きようがないので指摘しない
                if leg["target"]["ident"]:
                    out.append(info(f"凡例 Div ({loc}) に for 属性がありません "
                                    f"(for=\"{leg['target']['ident']}\" を書くと検算できます)",
                                    origin))
            elif ref not in idents:
                out.append(must(f"凡例 Div ({loc}) の for=\"{ref}\" は原稿に存在しない識別子です",
                                origin))
            elif ref != leg["target"]["ident"]:
                out.append(must(f"凡例 Div ({loc}) の for=\"{ref}\" と直前の図表 "
                                f"({leg['target']['ident'] or '識別子なし'}) が食い違っています",
                                origin))
        # (1) 中身: 段落以外を含むと最終パッケージの集約がそこで止まる
        kinds = legend_non_para_kinds(leg["inner"])
        if kinds:
            out.append(must(f"凡例 Div ({loc}) に段落以外の要素があります ({'/'.join(kinds)})。"
                            "pandoc が `Legend` 以外の段落スタイルを付けるため、最終パッケージの"
                            "集約がそこで止まり、以降が本文に取り残されます (段落だけで書いてください)",
                            origin))
    return out


def count_textbox_floats(floats):
    """`.textbox` の中の図・表を (図の list, 表の list) で返す。

    概算行の内訳表示と `lint_textbox_floats()` で共用する。数え方は本文フローの図表と同じで、
    違うのは `in_textbox` の真偽だけである。
    """
    return ([f for f in floats["figures"] if f["in_textbox"]],
            [t for t in floats["tables"] if t["in_textbox"]])


def lint_textbox_floats(floats, profile):
    """`.textbox` の中に図表があることを知らせる。

    図表の点数は本文フローのものしか数えない (`lint_float_counts` の説明)。その設計は
    最終パッケージの移設対象と揃えるためのものだが、**数えなかったことを黙っていてはいけない**
    — 全図表を箱に置いた原稿は「図 0 点・表 0 点」と報告され、上限の検査が
    無警告で空振りする。しかも箱の中の図表は提出構成の組み替え (末尾移設・図凡例の集約) の
    対象外なので、**最終提出 docx では本文に埋め込まれたまま残る**。BHI は
    "Figures must NOT be embedded within the manuscript file." を課しているので、
    これは規定違反に直結する。

    発火条件を `limits.figures_tables` の有無に掛けるのは、上限を定めている誌でこそ
    「数えなかった点数」が意味を持つためである (同キーを持たない誌では発火しない)。
    箱の中の図表を「本文に埋め込んではならない」と決めているのも、現状では同じ BHI だけである。

    **発火条件は意味的には「図の本文埋め込みを禁じているか」に紐づくべきで、いまは上限キーで
    代用している**。この指摘文が伝える 2 点 —— 「最終提出 docx では
    本文に埋め込まれたまま残る」「題・凡例の語数検査も掛からない」—— は、点数の上限を
    定めているかどうかと**関係がない**。いま両者が一致しているのは BHI が偶然どちらも
    持っているためで、「埋め込みは禁じるが点数の上限は定めない」誌を足した瞬間に
    この検査は空振りする。そうした雑誌プロファイルを足すときは
    `figures.embed_in_manuscript_allowed` のような専用キーを新設し、発火条件を
    「上限キーがある **または** 埋め込みが禁じられている」に広げること
    (既定を「未指定なら発火しない」にすれば、いまある誌の挙動は変わらない)。
    """
    limit = (profile.get("limits") or {}).get("figures_tables")
    if not limit:
        return []
    box_figs, box_tbls = count_textbox_floats(floats)
    if not (box_figs or box_tbls):
        return []
    n_body = len([f for f in floats["figures"] if not f["in_textbox"]]) \
        + len([t for t in floats["tables"] if not t["in_textbox"]])
    locs = ", ".join(_loc(it["line"]) for it in sorted(box_figs + box_tbls,
                                                       key=lambda it: it["line"]))
    return [must(
        f".textbox の中に図 {len(box_figs)} 点・表 {len(box_tbls)} 点があります ({locs})。"
        f"これらは上の合計点数 {n_body} 点 (上限 {limit} 点) に数えていないため、"
        "上限の検査はこれらを見落としています。"
        "textbox 内の図表は提出構成の組み替え (末尾移設・図凡例の集約) の対象外なので、"
        "最終提出 docx では本文に埋め込まれたまま残ります "
        "(規定は図を原稿ファイルに埋め込むことを禁じています)。"
        "題・凡例の語数検査も掛かりません。本文の流れの上に置き直してください")]


def lint_float_counts(floats, profile):
    """図表の合計点数と、図表の題 / 凡例の語数。

    点数の数え方:
      - **図** = 本文の流れの上にある画像記法の数。`{#fig:x}` の無い装飾画像も数える
        (最終モードでは同じように図ファイルとして書き出されるため)。
      - **表** = 本文の流れの上にあるパイプ表の数。**`.grid` Div の中の表は数える**
        (罫線の指定が違うだけで本文の表と同じ)。
      - **`.textbox` の中の図表は数えない** — 本文の流れの外にあり、最終パッケージの移設対象からも
        外れている (`docs/architecture.md` §2.5)。

    ただし数えなかったことは黙らない。全図表を `.textbox` に置いた原稿は
    「図 0 点・表 0 点」と報告され、**上限の検査が無警告で空振りする**
    (実測: 図表 9 点を箱に置いた原稿で、上限 8 点を超えているのに指摘が 1 件も出なかった)。
    数え方そのものを変えないのは最終パッケージの移設対象 (= 本文フローの図表) と
    定義を揃えるためなので、代わりに `limits.figures_tables` を持つ誌では
    **箱の中に図表があること自体を要修正として指摘する** (`lint_textbox_floats`)。
    """
    out = []
    figs = [f for f in floats["figures"] if not f["in_textbox"]]
    tbls = [t for t in floats["tables"] if not t["in_textbox"]]
    limit = (profile.get("limits") or {}).get("figures_tables")
    if limit and len(figs) + len(tbls) > int(limit):
        out.append(must(f"図表の合計点数 {len(figs) + len(tbls)} 点 (図 {len(figs)} / 表 {len(tbls)}) が"
                        f"上限 {limit} 点を超過しています"))
    out.extend(lint_textbox_floats(floats, profile))

    for kind, items, cfg_key in (("図", figs, "figures"), ("表", tbls, "tables")):
        cfg = (profile.get(cfg_key) or {})
        tw, lw = cfg.get("title_words"), cfg.get("legend_words")
        for it in items:
            label = it["ident"] or f"{_loc(it['line'])} の{kind}"
            if tw and it["title"]:
                # 語数は執筆者が書いたキャプション本文だけを数える
                # (pandoc-crossref が入れる "Figure 1: " は原稿に存在しない)
                n = len(_word_tokens(it["title"]))
                if n > int(tw):
                    out.append(must(f"{kind}の題 ({label}) が {n} 語で上限 {tw} 語を超過しています"))
            if lw:
                n = sum(len(_word_tokens(g["inner"])) for g in it["legends"])
                if n > int(lw):
                    out.append(must(f"{kind}の凡例 ({label}) が {n} 語で上限 {lw} 語を超過しています"))
    return out


def lint_references_last(blocks, profile):
    """References が本文の最終節か。

    最終パッケージの集約先は「References の後」ではなく **「本文の末尾 (`w:sectPr` の直前)」**であり、
    「References が最終節である以上それで規定を満たす」という前提に立っている
    (`relocate.py` の `_appender()` / `docs/architecture.md` §2.5)。前提そのものは妥当だが、検査しないと
    References の後ろに付録の節を書いたときに `References → Appendix → [改ページ] Figure Legends`
    になり、警告も出ない (実測)。**移設が働く誌でだけ**検査する。
    """
    relocating = bool((profile.get("figures") or {}).get("legends_section")) \
        or (profile.get("tables") or {}).get("placement") == "end"
    if not relocating:
        return []
    tops = [b for b in blocks if b["kind"] == "heading" and b["level"] == 1 and not b["in_textbox"]]
    idx = next((i for i, h in enumerate(tops) if _norm(h["text"]) == "references"), None)
    if idx is None or idx == len(tops) - 1:
        return []
    after = [h["text"] for h in tops[idx + 1:]]
    return [must("References の後ろに節があります (" + " / ".join(after) + ")。"
                 "最終パッケージは図凡例・表を本文の末尾へ移すため、これらの節より後ろに"
                 "置かれます (規定の並びは References → Figure Legends → Tables)")]


_RE_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_RE_TEL_LABEL = re.compile(r"\b(?:tel|phone|telephone)\b\s*[:：]?\s*(.*)", re.IGNORECASE)


def _tel_line(line):
    """電話番号の行か (ラベル + 数字 6 桁以上、または記入欄が残っている行)。

    記入欄を許すのは、`Tel: <<+81-00-0000-0000>>` のような未記入の行に対して
    「電話番号が無い」と「記入欄が残っている」の 2 つを重ねて出さないため
    (直すべき箇所は 1 つなので、指摘も 1 つにする)。
    """
    m = _RE_TEL_LABEL.search(line)
    if not m:
        return False
    rest = m.group(1)
    return len(re.findall(r"\d", rest)) >= 6 or bool(_RE_PLACEHOLDER.search(rest))


def lint_corresponding(blocks, profile):
    """連絡著者ブロックが 1 名分で、住所・電話・E-mail を備えているか。

    検出対象は `custom-style="Corresponding"` Div (reference.docx に段落スタイルを注入してあり、
    BHI の骨格では必須ブロック)。規定は corresponding author を **1 名のみ**とし、
    氏名・住所全文・電話・E-mail を Title page に書くよう求めている。
    """
    if not (profile.get("lint") or {}).get("corresponding_author"):
        return []
    inners = _div_inner(blocks, "corresponding")
    if not inners:
        return [must("連絡著者ブロック (custom-style=\"Corresponding\" Div) がありません。"
                     "規定は氏名・住所全文・電話・E-mail を Title page に求めています")]
    out = []
    if len(inners) > 1:
        out.append(must(f"連絡著者ブロックが {len(inners)} 個あります。"
                        "規定は corresponding author を 1 名のみと定めています"))
    inner = inners[0]
    labels = re.findall(r"corresponding\s+author", inner, re.IGNORECASE)
    if len(labels) > 1:
        out.append(must(f"1 つの連絡著者ブロックに 'Corresponding author' が {len(labels)} 回"
                        "現れます (1 名のみ)"))
    emails = _RE_EMAIL.findall(inner)
    if not emails:
        out.append(must("連絡著者ブロックに E-mail がありません"))
    elif len(emails) > 1:
        out.append(must(f"連絡著者ブロックに E-mail が {len(emails)} 件あります ({', '.join(emails)})"))
    if not any(_tel_line(ln) for ln in inner.splitlines()):
        out.append(must("連絡著者ブロックに電話番号 (Tel: …) がありません"))
    # 住所は形式が国ごとに違うので機械判定できない。氏名行・Tel 行・E-mail 行を除いた
    # 段落が 1 つも無ければ「住所が無い」と見なす (参考情報)。
    rest = [ln for ln in inner.splitlines()
            if ln.strip()
            and not re.search(r"corresponding\s+author", ln, re.IGNORECASE)
            and not _tel_line(ln) and not _RE_EMAIL.search(ln)]
    if not rest:
        out.append(info("連絡著者ブロックに住所らしき行がありません "
                        "(規定は住所全文 = 部門・機関・番地・市・州・郵便番号・国 を求めています)"))
    return out


# 非 SI 単位の狭い検出器。臨床慣用単位 (mmHg 等) は規定が明示的に認めているので拾わない。
# 語形は**大文字小文字を区別して**照合する — "Miles" のような固有名詞を拾わないため。
_NON_SI = [
    (re.compile(r"℉|°\s?F\b"), "°F", "°C"),
    (re.compile(r"\b[Ff]ahrenheit\b"), "Fahrenheit", "°C (摂氏)"),
    (re.compile(r"\binch(?:es)?\b"), "inch", "mm / cm"),
    (re.compile(r"\blbs?\b"), "lb", "kg"),
    (re.compile(r"\bpounds?\b"), "pound", "kg"),
    (re.compile(r"\bounces?\b|\boz\b"), "ounce", "g"),
    (re.compile(r"\bmiles?\b"), "mile", "km"),
    (re.compile(r"\bgallons?\b"), "gallon", "L"),
]


def lint_units(text, profile):
    """lint.units: SI のとき、SI でない単位らしき語を拾う (参考情報)。

    **これは「SI に準拠している」ことの証明にはならない** — 検出できるのは英米慣用単位の
    代表的な綴りだけである。臨床慣用単位 (mmHg 等) は規定が認めているので対象にしない。
    誤検出を避けるため語形は大文字小文字を区別する。
    """
    if str((profile.get("lint") or {}).get("units") or "").upper() != "SI":
        return []
    body = re.split(r"^#+\s*References\b.*$", text, maxsplit=1,
                    flags=re.MULTILINE | re.IGNORECASE)[0]
    hits = []
    for i, line in enumerate(body.splitlines()):
        for pat, label, hint in _NON_SI:
            if pat.search(line):
                hits.append(f"{label} ({_loc(i)} → {hint})")
    if not hits:
        return []
    return [info("SI でない単位らしき表記があります: " + ", ".join(sorted(set(hits))[:8])
                 + " — 規定は SI または SI 派生単位を求めています "
                 "(mmHg 等の臨床慣用単位は可)", _origin_note(profile, "units"))]


# 統計ソフトは「型番 + 製造元 + 所在地」に加えて**バージョン**も要る (規定 "Method of stating
# the names of devices")。綴りが一意なパッケージ名だけを対象にする。
_STAT_SOFTWARE = ["SPSS", "SAS", "Stata", "STATA", "MATLAB", "GraphPad", "Prism",
                  "JMP", "EZR", "S-PLUS", "R version"]
_RE_VERSION = re.compile(r"\bversion\b|\bv?\d+\.\d+", re.IGNORECASE)
_RE_VENDOR = re.compile(r"\([^)]*,[^)]*\)")


def lint_device_notation(text, profile):
    """統計ソフトにバージョンと製造元 (括弧内) が添えられているか (参考情報)。

    機器一般の「型番 + 製造元 + 所在地」は文面から機械判定できないので、規定が特に
    「バージョンも」と念を押している**統計ソフト**に絞った狭い検査にしてある。
    **この検査は不備を見逃す側に倒してある** (誤検出を避けるため) — 括弧内にカンマがあれば
    製造元の記載とみなすので、文献の括弧 `(Smith, 2020)` でも合格になる。

    (1) 同じソフト名は**出現ごとに**判定する (1 件目だけを見ると、Methods と Results の 2 箇所に
    書いて片方だけ不備がある原稿を取り逃す)。同じ文面の指摘は重複を除いてまとめる。
    (2) 窓は**段落単位**で切る (全文を空白 1 個に畳んだ 1 行で切ると、段落をまたいで隣の文の
    括弧を拾ってしまう)。
    行単位にはしない — 原稿は行を折り返して書くので、ソフト名と製造元の括弧が別の行に
    分かれているだけで不備と判定してしまう。
    """
    if not (profile.get("lint") or {}).get("device_notation"):
        return []
    body = re.split(r"^#+\s*References\b.*$", text, maxsplit=1,
                    flags=re.MULTILINE | re.IGNORECASE)[0]
    seen, out = set(), []
    for para in re.split(r"\n[ \t]*\n", body):
        flat = re.sub(r"\s+", " ", para)
        for name in _STAT_SOFTWARE:
            for m in re.finditer(rf"\b{re.escape(name)}\b", flat):
                window = flat[m.start():m.start() + 140]
                lacks = []
                if not _RE_VERSION.search(window):
                    lacks.append("バージョン")
                if not _RE_VENDOR.search(window):
                    lacks.append("製造元と所在地 (括弧内)")
                if not lacks:
                    continue
                key = (name, tuple(lacks))
                if key in seen:
                    continue
                seen.add(key)
                out.append(info(f"統計ソフト '{name}' の記載に不足があります "
                                f"({' / '.join(lacks)})。規定は「型番 + 製造元 + 所在地 "
                                "(市・州・国)」を、統計ソフトにはバージョンも求めています"))
    return out


# =====================================================================
# reference.docx との突合
# =====================================================================

def check_reference_layout(journal_id, profile):
    """雑誌固有 reference.docx の実体裁が profile.yaml とずれていたら警告文を返す。

    体裁は reference.docx に焼き込む設計なので、profile.yaml を編集して
    make-reference.sh の再実行を忘れると古い体裁のまま投稿まで進む。build 時にも同じ検査を
    出しているが (build_docx._warn_stale_reference)、提出物を組み立てる直前にもう一度掛ける。
    """
    ref = profile.get("reference_doc")
    if not ref:
        return []      # _default 継承の告知は build 側が受け持つ
    path = journal_profile.JOURNALS_DIR / journal_id / ref
    if not path.is_file():
        return []      # 不在の告知も build 側が受け持つ
    return [must(f"{path} の体裁が profile.yaml と食い違っています "
                 f"({key}: profile={want!r} != reference.docx={got!r})。"
                 f"'bash data/journals/make-reference.sh {journal_id}' で再生成してください")
            for key, want, got in journal_profile.layout_mismatches(profile, path)]


# =====================================================================
# 本体
# =====================================================================

_BIB_ENTRY_RE = re.compile(r"^\s*@(\w+)\s*\{\s*([^,\s]+)\s*,", re.MULTILINE)
_BIB_LANGID_RE = re.compile(r"\blangid\s*=\s*[{\"]\s*([^}\"]*?)\s*[}\"]", re.IGNORECASE)


def lint_langid(input_root, profile):
    """`ref.bib` に japanese 以外の `langid` を持つ文献が無いか (誌ごと。既定は無効)。

    pandoc は BibTeX の `langid` を CSL の変数 `language` に写す。CSL は変数の値を比べられない
    ので、`language` があるだけで "(in Japanese)" を付ける引用様式 (`bhi.csl`) では、
    `langid = {english}` の英語の文献にも "(in Japanese)" が付く。書誌管理ソフト
    (Zotero / Better BibTeX など) は英語の文献にも `langid` を付けて書き出すことが多く、
    そのまま使うと文献リスト全体が誤るのに、目で見ても気づきにくい。

    `@comment` / `@string` / `@preamble` は文献ではないので数えない。
    """
    if not (profile.get("lint") or {}).get("langid_japanese_only"):
        return []
    bib = Path(input_root) / "ref.bib"
    if not bib.is_file():
        return []
    src = bib.read_text(encoding="utf-8", errors="replace")
    starts = list(_BIB_ENTRY_RE.finditer(src))
    bad = []
    for i, m in enumerate(starts):
        if m.group(1).lower() in ("comment", "string", "preamble"):
            continue
        end = starts[i + 1].start() if i + 1 < len(starts) else len(src)
        lm = _BIB_LANGID_RE.search(src, m.end(), end)
        if lm and lm.group(1).strip().lower() != "japanese":
            bad.append(f"{m.group(2)} (langid = {{{lm.group(1).strip()}}})")
    if not bad:
        return []
    return [must(
        f"ref.bib に langid が japanese 以外の文献が {len(bad)} 件あります: {', '.join(bad)}。"
        "この誌の引用様式は langid があるだけで言語によらず \"(in Japanese)\" を付けます。"
        "英語の文献からは langid を消し、和文以外の非英語の文献は note = {in German} のように書いてください")]


def validate(input_root, profile, article_type=None, journal_id=None):
    """limits / lint と照合し、指摘 (list[Finding]) を返す。

    profile は生 dict / journal_profile.resolve() 済みのどちらでもよい (ここで解決する。
    解決済みなら冪等ガードで素通り)。article_type を渡すと記事種別で limits / abstract を
    上書きして検証する。journal_id を渡すと reference.docx の
    実体裁との突合も行う (省略時は体裁を見ない)。

    戻り値は list[Finding] (要修正 / 参考の区分表示のため)。
    表示は print_findings() を使う。
    """
    profile = journal_profile.resolve(profile or {}, article_type)
    findings = []
    if journal_id:
        findings.extend(check_reference_layout(journal_id, profile))
    text = _read_main(input_root)
    if text is None:
        return findings + [must(f"{Path(input_root) / 'main.md'} が無く検証できません")]
    text = _strip_noise(text)
    blocks = scan_blocks(text)
    floats = analyze_floats(blocks)

    limits = (profile.get("limits") or {})
    abstract_cfg = (profile.get("abstract") or {})

    # --- 概算 (語数・文献数・図表点数) ---
    # 略語一覧を本文語数から除くかは誌の規定次第 (BHI は除く)
    drop_abbr = bool((profile.get("declarations") or {}).get("abbreviations_section"))
    # 対応不明の凡例 (直前に図表が無い = 配置規則違反) は最終パッケージの
    # 集約から漏れて提出物の本文に残るので、本文語数にも算入する
    orphan_legends = [leg["inner"] for leg in floats["legends"] if leg["target"] is None]
    body = count_body_words(text, blocks, drop_abbreviations=drop_abbr, keep_legends=orphan_legends)
    abs_words = count_abstract_words(blocks)
    refs = count_references(text)
    leg_fig, leg_tbl, leg_other = count_legend_words(floats)
    n_fig = len([f for f in floats["figures"] if not f["in_textbox"]])
    n_tbl = len([t for t in floats["tables"] if not t["in_textbox"]])
    print(f"  概算: 本文 {body} 語 / 抄録 {abs_words if abs_words is not None else '—'} 語"
          f" / 文献 {refs} 件 / 図 {n_fig} 点・表 {n_tbl} 点")
    # 箱の中の図表は上の点数に入っていない。**入れなかったことを必ず言う**。
    # 上限の検査が空振りしていることに気づけるのはこの 1 行だけである (誌が上限を定めて
    # いなければ lint も出ないため)。
    box_figs, box_tbls = count_textbox_floats(floats)
    if box_figs or box_tbls:
        print(f"        うち .textbox 内 図 {len(box_figs)} 点・表 {len(box_tbls)} 点は"
              "上限の対象外 (本文の流れの外にあり、末尾移設の対象からも外れる)")
    # 除外した凡例の内訳を必ず出す (除外は費用の見積もりを甘くする側に効くため、
    # 編集室の数え方が違ったときに足し戻せるようにする)
    if leg_fig or leg_tbl:
        parts = [f"図の凡例 {leg_fig}"] if leg_fig else []
        if leg_tbl:
            parts.append(f"表の凡例 {leg_tbl}")
        print(f"        本文語数から除外した凡例: {' / '.join(parts)} 語 "
              f"(合計 {leg_fig + leg_tbl} 語)")
    if leg_other:
        print(f"        対応不明の凡例 {leg_other} 語は提出物の本文に残るため本文語数に"
              "算入した (配置規則違反として別途指摘する)")

    # --- 上限との照合 ---
    wc = limits.get("word_count")
    if wc and body > int(wc):
        findings.append(must(f"本文語数 {body} が上限 {wc} を超過 (概算)"))

    aw = limits.get("abstract_words")
    if aw and abs_words is not None and abs_words > int(aw):
        findings.append(must(f"抄録語数 {abs_words} が上限 {aw} を超過 (概算)"))

    rl = limits.get("references")
    if rl and refs > int(rl):
        findings.append(must(f"文献数 {refs} が上限 {rl} を超過"))

    # --- 構造化抄録の要求と原稿の体裁の食い違い ---
    if abstract_cfg.get("structured") and abs_words is not None:
        # 全文ではなく抄録 Div の中身だけでラベルを判定する
        # (本文の太字 '**Methods**' に釣られて見逃さないため)。
        # 誌が abstract.labels を定義していればそれを使う (BHI は Objective/Methods/
        # Results/Conclusion)。未定義なら既定ラベル。
        # 候補ラベルを縦棒でつないだ 1 本の正規表現を search する
        # だけでは、**4 つのうち 1 つ当たれば合格**になる。BHI (Objective/Methods/Results/
        # Conclusion) は既定ラベル (Background/Methods/Results/Conclusions) と Methods・Results
        # を共有し、大文字小文字を無視するため '**Conclusions:**' が 'Conclusion' にも当たる。
        # 結果として「他誌の癖のまま Background で書いた抄録」が BHI として無警告で通ってしまう
        # (data/dummy で実測)。誌が abstract.labels を明示している場合は全ラベルの存在を個別に
        # 確かめ、欠けたものを名指しで警告する。labels 未定義の誌は既定ラベルのいずれか 1 つで合格。
        abs_inner = _abstract_inner(blocks) or ""
        labels_cfg = abstract_cfg.get("labels")
        if labels_cfg:
            # 誌指定のラベルは語として一致させる (末尾に (?![A-Za-z]) を付ける)。前方一致のままだと
            # BHI の 'Conclusion' に既定ラベルの '**Conclusions:**' が当たってしまい、単複の取り違えを
            # 見逃す。既定ラベル側 (else 節) は前方一致のまま (labels 未定義の誌は単複を区別しない)。
            missing_labels = [str(lb) for lb in labels_cfg
                              if not re.search(rf"\*\*\s*{re.escape(str(lb))}(?![A-Za-z])",
                                               abs_inner, re.IGNORECASE)]
            if missing_labels:
                findings.append(must(
                    f"この雑誌は構造化抄録 ({'/'.join(str(lb) for lb in labels_cfg)}) を要求しますが、"
                    f"抄録に見出しラベル {'/'.join(missing_labels)} が見当たりません"
                    " (誌指定のラベルは全て必要です)"))
        else:
            # labels 未定義: 既定ラベルのいずれか 1 つでも見つかれば合格
            default_labels = ["Background", "Methods", "Results", "Conclusions"]
            pat = "|".join(re.escape(lb) for lb in default_labels)
            if not re.search(rf"\*\*\s*({pat})", abs_inner, re.IGNORECASE):
                findings.append(must(f"この雑誌は構造化抄録 ({'/'.join(default_labels)}) を"
                                     "要求しますが、抄録に見出しラベルが見当たりません"))

    # --- lint 群 (すべて profile 駆動。キーが無い雑誌では発火しない) ---
    # 走査済みの blocks / floats を渡す (走査は 1 回だけ)。各 lint が scan_blocks を呼び直すと、
    # 性能もさることながら、この層に状態 (採番など) を持たせたときに静かに壊れる。
    findings.extend(lint_title(blocks, profile))
    findings.extend(lint_keywords(blocks, profile))
    findings.extend(lint_abstract_citations(blocks, profile))
    findings.extend(lint_declarations(blocks, profile))
    findings.extend(lint_abbreviations(text, blocks, profile))
    findings.extend(lint_forbidden_chars(text, profile))
    findings.extend(lint_thousands_separator(text, profile))
    findings.extend(lint_placeholders(text, profile, input_root))
    findings.extend(lint_legend_placement(blocks, floats, profile))
    findings.extend(lint_float_counts(floats, profile))
    findings.extend(lint_references_last(blocks, profile))
    findings.extend(lint_corresponding(blocks, profile))
    findings.extend(lint_units(text, profile))
    findings.extend(lint_device_notation(text, profile))
    findings.extend(lint_langid(input_root, profile))
    return findings


def print_findings(findings, indent="  "):
    """指摘を「規定違反の可能性 (要修正)」と「参考情報」に分けて表示する。"""
    if not findings:
        print(f"{indent}限度内 (または limits 未設定)")
        return
    for level, title in ((LEVEL_MUST, "規定違反の可能性 (要修正)"), (LEVEL_INFO, "参考情報")):
        rows = [f for f in findings if f.level == level]
        if not rows:
            continue
        print(f"{indent}-- {title} ({len(rows)} 件) --")
        for f in rows:
            print(f"{indent}  [{f.level}] {finding_text(f)}")


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--input-root", required=True)
    p.add_argument("--journal", default="_default")
    p.add_argument("--article-type", default=None,
                   help="記事種別 (article_types を持つ誌のみ。limits/abstract を種別値で解決)")
    args = p.parse_args(argv)
    profile = journal_profile.load(args.journal)
    print(f"== validate: {args.input_root} vs journal={args.journal}"
          + (f" article_type={args.article_type}" if args.article_type else "") + " ==")
    findings = validate(args.input_root, profile, args.article_type, journal_id=args.journal)
    print_findings(findings)
    return 0


if __name__ == "__main__":
    sys.exit(main())
