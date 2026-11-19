#!/usr/bin/env python3
"""svg_safe.py — CSS に頼らない「自己完結の SVG」へ書き換える。

【なぜ要るか】
提出した pptx の図を投稿系がどの描画系で描くか (PNG フォールバックか、SVG を描き直すか) は、投稿規定にも
公開の情報にも無い。SVG を描く描画系には、文書内の CSS (`<style>`) を適用しないものがある
(例: Aspose.Slides。評価版で確かめた)。R の svglite が書く SVG は、図形の既定の体裁を CSS
(`.svglite rect { fill: none; stroke: #000000; ... }`) で与え、個々の要素には塗りの指定を書かない。
CSS を適用しない描画系では、塗りの指定が無い四角形が SVG の既定値 = **黒で塗られ**、ggplot のパネルの
枠線 (中身の**上に**描かれる) がパネルを隠す。本テンプレートは、どの描画系で描かれても同じ見た目に
なるよう、CSS を各要素の `style` 属性へ書き出す (BHI のプロファイルの既定。figures.pptx.inline_css)。

【何をするか】
  1. `<style>` の CSS 規則を、当てはまる各要素 (ルートの `<svg>` を含む) の `style` 属性へ書き込む。
     優先は CSS の規則どおり: 詳細度 (ID 数・クラスと属性の数・要素名の数) → 記述順 (複数の `<style>` を
     文書の順に通して数える)。`!important` の宣言はその上に立ち、要素自身の `style` (インライン) は
     `!important` でない規則より強い。`fill="…"` のような表示属性は CSS より弱いので、CSS の値を `style` に書く。
     1 つの規則の中で同じ性質を 2 回以上書いた宣言 (`fill: blue; fill: notacolor` のような代替) は、
     どれが効くかを描画系に任せるため、記述の順のまま全部書く。一括指定の `marker` は
     `marker-start` / `marker-mid` / `marker-end` に展開してから重ねる (個別の指定との上書きの順を CSS どおりにする)。
  2. 値が `inherit` の宣言: 継承する性質 (fill・stroke・font-* など) なら、要素の表示属性を外して親から
     受け継がせる (表示属性が無ければ何も書かない)。継承しない性質 (opacity など) の `inherit` は止める。
  3. `white-space: pre` を受けたテキストに `xml:space="preserve"` を付ける (SVG 1.1 の書き方)。
  4. **テキストに文字色を明示する** (`fill` が自身にも祖先にも無ければ既定の黒 `#000000`。`inherit` は
     さらに上をたどる)。文字を輪郭化 (text-to-path) すると `<text>` が `<path>` になり、
     `.svglite path { fill: none }` が当たって**文字が透明になる**ため (Inkscape は既定の黒を書き出さない。実測)。
     `<defs>` / `<symbol>` の中の文字と、`<use>` から参照される文字 (自身か祖先の id が参照されているもの) は、
     `<use>` の側の色を受け継ぐので明示しない。
  5. 幅か高さを持たない `<rect>` を取り除く。幅と高さは属性 (`width="…"`) か CSS の性質 (SVG 2 では
     `width` / `height` を CSS でも与えられる) で決まり、どちらにも無いか 0 の四角は描かれない。描画系によっては
     (例: Aspose.Slides の評価版) 表示域いっぱいの四角として描き、図を覆う (Mermaid はラベルの背景に `<rect/>` を出す)。
     書き出した後の `style` の値も見る (CSS で寸法を与えた四角を消さないため)。id で参照されているものは残す。
  6. 色の値 `rgba()` / `hsl()` / `hsla()` (と不透明度つきの `rgb()`) を、16 進の色と不透明度
     (`fill-opacity` / `stroke-opacity` / `stop-opacity` / `flood-opacity`。元から自身か祖先にあれば掛け合わせる) に、
     値の数が奇数の `stroke-dasharray` (`2` や `5,3,2`) を、規則どおり 2 回繰り返した偶数の並び (`2, 2`) に、
     合計が 0 の `stroke-dasharray` (`0` や Mermaid が出す `0 0`。規則では実線と同じ) を `none` に、
     色名の `grey` 系の綴り (`lightgrey` など) を 16 進に書き換える。線の無い図形が `opacity` と `fill-opacity` を
     両方持つときは、`opacity` を `fill-opacity` に掛け合わせて外す。
     どれも CSS を読む描画系では同じ見た目で、描画系によっては (例: Aspose.Slides の評価版) `rgba()` / `hsl()` と
     `grey` 系の色名を黒で塗り、値が 1 つの点線を実線で描き、0 を含む点線があると図全体を描かず、
     `fill-opacity` と並ぶ `opacity` を無視するため。
  7. 要素の `style` に残った `!important` を外す。`<style>` を外した後は要素の `style` より強い指定が無いので、
     見た目は変わらない。描画系によっては (例: Aspose.Slides の評価版) `!important` の付いた宣言を無効として扱い、
     塗りを黒にし、点線なら図全体を描かないため (Mermaid の `classDef` / `style` が `!important` 付きで書く)。
  8. `<style>` 要素を取り除く (書き込み済みなので、残すと解釈の揺れの元になる)。

【対応する CSS】svglite・Mermaid (本テンプレートの経路)・matplotlib が書く範囲:
  セレクタ = 要素名・`*`・クラス・ID・属性 (`[a]` / `[a="v"]` / `[a~="v"]` / `[a|="v"]` / `[a^="v"]` / `[a$="v"]` /
  `[a*="v"]`、大小無視の `i`) の組み合わせと、子孫結合子 (空白)・子の結合子 (`>`)。
  `@keyframes` (動きの定義。静止画には効かない) は読み飛ばし、`@charset` は無視する。
  CSS の変数 (`--名前`) は、定義を集めて `var()` を値に置き換える (規則の宣言と、要素自身の `style` の両方)。
  定義だけの規則 (Mermaid の `:root`) はその後で捨てる。定義が無ければ `var()` の代わりの値を使う
  (Mermaid のシーケンス図・状態遷移図・クラス図・gitGraph の CSS がこれらを使う)。
  定義を受け付けるのは、ルートに当たるセレクタ (`:root` / `svg` / ルートの ID) の規則とルート要素の `style` だけで、
  変数の名前は大文字と小文字を区別する (定義した場所によって効く範囲が変わる形を、全体で 1 つの値として扱わないため)。
  宣言は、引用符と括弧の中の `;` では切らない (`url("data:…;…")` を壊さないため)。
それ以外 (`+` `~` の結合子・`:hover` などの擬似クラス・`@media` などの @ 規則・一括指定の `font`・
`media` 属性つきの `<style>`・内部 DTD の実体参照・定義も代わりの値も無い変数・同じ名前に違う値のある変数・
ルート以外の規則や要素の `style` での変数の定義・
`foreignObject` の中の (SVG でない) 要素に当たる規則 (Mermaid の journey 図)・外部の CSS を読む `<?xml-stylesheet?>`)
を見つけたら **ValueError で止める** (黙って一部だけ書き込むと、見た目が変わったことに気づけないため)。
文字色の明示・`<rect>` の除去・色の書き換えは SVG の名前空間の要素にだけ行う (`<metadata>` の中の RDF などに触れない)。

【確かめてある範囲】図の種類・描画系ごとの範囲と既知の制限は docs/journal-bhi.md の「inline_css」の節にまとめてある
(書き換えの前後を librsvg と Chromium で描いて画素が一致すること、Aspose.Slides の評価版と PowerPoint で描いた結果)。

使い方 (CLI): python3 svg_safe.py <in.svg> <out.svg>
"""

import colorsys
import re
import sys

from lxml import etree

SVG_NS = "http://www.w3.org/2000/svg"
XML_SPACE = "{http://www.w3.org/XML/1998/namespace}space"

# 複合セレクタの部品: 要素名か *、続いて .クラス / #ID / [属性] / [属性 演算子 "値" (i)] の並び
# (属性の演算子 ~= |= ^= $= *= と大小無視の i は、Mermaid のシーケンス図・状態遷移図・クラス図が使う)
_TYPE = re.compile(r"\*|[A-Za-z][\w-]*")
_SUB = re.compile(r"""\.(?P<cls>[\w-]+)|\#(?P<id>[\w-]+)"""
                  r"""|\[\s*(?P<attr>[\w-]+)\s*(?:(?P<op>[~|^$*]?=)\s*(?:"(?P<dq>[^"]*)"|'(?P<sq>[^']*)'|(?P<bare>[\w-]+))"""
                  r"""\s*(?P<flag>[iIsS])?\s*)?\]""")
# 扱う結合子は子孫 (空白) と子 (>)。隣接 (+) と後続 (~) は止める
_COMBINATORS = re.compile(r"[+~]")

# 継承する性質 (SVG 1.1 / CSS。inherit を「表示属性を外す」で表せるもの)
_INHERITED = {
    "fill", "fill-opacity", "fill-rule", "stroke", "stroke-width", "stroke-linecap", "stroke-linejoin",
    "stroke-miterlimit", "stroke-dasharray", "stroke-dashoffset", "stroke-opacity",
    "font-family", "font-size", "font-style", "font-variant", "font-weight", "font-stretch",
    "color", "visibility", "text-anchor", "letter-spacing", "word-spacing", "writing-mode",
    "direction", "white-space", "dominant-baseline", "glyph-orientation-vertical", "kerning",
    "clip-rule", "color-interpolation", "color-rendering", "image-rendering", "shape-rendering",
    "text-rendering", "pointer-events", "cursor", "marker", "marker-start", "marker-mid", "marker-end",
}
# 文字色の明示を省く (<use> の側の色を受け継ぐ) 祖先
_REUSED = {"defs", "symbol"}
# 一括指定の marker を展開する先
_MARKER_LONGHANDS = ("marker-start", "marker-mid", "marker-end")
# 不透明度つきの色を書き換える性質と、その不透明度の性質
_COLOR_OPACITY = {"fill": "fill-opacity", "stroke": "stroke-opacity",
                  "stop-color": "stop-opacity", "flood-color": "flood-opacity"}
# 継承する不透明度 (stop-opacity / flood-opacity は継承しない)
_INHERITED_OPACITY = {"fill-opacity", "stroke-opacity"}
# 色名の grey 系の綴り (gray 系と同じ色)。描画系によっては (例: Aspose.Slides の評価版) 黒で塗るので 16 進にする
_GREY_NAMES = {"grey": "#808080", "lightgrey": "#d3d3d3", "darkgrey": "#a9a9a9", "dimgrey": "#696969",
               "slategrey": "#708090", "lightslategrey": "#778899", "darkslategrey": "#2f4f4f"}
_COLOR_PROPS = ("fill", "stroke", "stop-color", "flood-color", "color")
# opacity を fill-opacity に掛け合わせてよい図形 (子を持たない。線が無いときだけ)
_FOLD_OPACITY_SHAPES = {"rect", "circle", "ellipse", "polygon", "polyline", "path"}


def _local(tag):
    return tag.rsplit("}", 1)[-1] if isinstance(tag, str) else ""


def _is_svg(el):
    return isinstance(el.tag, str) and etree.QName(el).namespace in (None, SVG_NS)


def _split_decls(text):
    """宣言の並びを `;` で切る。引用符と括弧の中の `;` では切らない。"""
    out, buf, depth, quote = [], [], 0, None
    for ch in text or "":
        if quote:
            if ch == quote:
                quote = None
        elif ch in "\"'":
            quote = ch
        elif ch == "(":
            depth += 1
        elif ch == ")" and depth:
            depth -= 1
        elif ch == ";" and not depth:
            out.append("".join(buf))
            buf = []
            continue
        buf.append(ch)
    out.append("".join(buf))
    return out


def _parse_decls(text):
    """`a: b; c: d !important` → 順序つき dict {prop: ([value, …], important)} (キーは小文字)。

    同じ性質の宣言が並べば値を記述の順に持つ (代替の値を描画系に任せる)。`!important` の宣言があれば
    そちらだけを残す (CSS では !important が同じ規則の中の後の宣言にも勝つ)。一括指定の `marker` は
    marker-start / marker-mid / marker-end に展開する。
    CSS の変数 (`--名前`) の名前は大文字と小文字を区別するので、小文字にしない。
    """
    out = {}
    for decl in _split_decls(text):
        if ":" not in decl:
            continue
        k, v = decl.split(":", 1)
        k, v = k.strip(), v.strip()
        if not k.startswith("--"):
            k = k.lower()
        if not k:
            continue
        important = False
        m = re.search(r"!\s*important\s*$", v, re.I)
        if m:
            important, v = True, v[:m.start()].rstrip()
        for prop in (_MARKER_LONGHANDS if k == "marker" else (k,)):
            if prop not in out:
                out[prop] = ([v], important)
                continue
            vals, imp = out[prop]
            if important and not imp:
                out[prop] = ([v], True)
            elif important == imp:
                out[prop] = (vals + [v], imp)
    return out


def _parse_style(text):
    """要素の style 属性 → 順序つき dict {prop: [value, …]} と、!important の性質の集合。"""
    decls = _parse_decls(text)
    return {k: v for k, (v, _imp) in decls.items()}, {k for k, (_v, imp) in decls.items() if imp}


def _format_style(d):
    return "; ".join(f"{k}: {v}" for k, vals in d.items() for v in vals) + (";" if d else "")


def _parse_compound(token, sel):
    """`rect.cls#id[a="v"]` → (tag|None, classes, id|None, [(attr, op|None, value|None, 大小無視)])。対応外なら ValueError。"""
    pos, tag = 0, None
    m = _TYPE.match(token)
    if m:
        tag = None if m.group(0) == "*" else m.group(0)
        pos = m.end()
    classes, ident, attrs = set(), None, []
    while pos < len(token):
        m = _SUB.match(token, pos)
        if not m:
            raise ValueError(f"対応していない CSS セレクタです: {sel!r}")
        if m.group("cls"):
            classes.add(m.group("cls"))
        elif m.group("id"):
            ident = m.group("id")
        else:
            val = next((m.group(g) for g in ("dq", "sq", "bare") if m.group(g) is not None), None)
            attrs.append((m.group("attr"), m.group("op"), val, (m.group("flag") or "").lower() == "i"))
        pos = m.end()
    if pos == 0:
        raise ValueError(f"対応していない CSS セレクタです: {sel!r}")
    return tag, classes, ident, attrs


def _parse_selector(sel):
    """`#my-svg .node > rect` → ((部品の並び, 結合子の並び), 詳細度)。対応外なら ValueError。

    結合子の並びは部品と同じ長さで、i 番目は部品 i-1 と i の間の結合子 (" " = 子孫 / ">" = 子。0 番目は使わない)。
    """
    sel = sel.strip()
    bare = re.sub(r"\[[^\]]*\]", "", sel)
    if not sel or _COMBINATORS.search(bare) or ":" in bare:
        raise ValueError(f"対応していない CSS セレクタです: {sel!r}")
    # 属性の値の中の空白と > で切らないよう、[...] を伏せてから、> の前後に空白を入れて空白で分ける
    masked = re.sub(r"\[[^\]]*\]", lambda m: m.group(0).replace(" ", "\x00").replace(">", "\x01"), sel)
    toks = masked.replace(">", " > ").split()
    parts, combs, pending = [], [], None
    for tok in toks:
        if tok == ">":
            if not parts or pending is not None:
                raise ValueError(f"対応していない CSS セレクタです: {sel!r}")
            pending = ">"
            continue
        parts.append(_parse_compound(tok.replace("\x00", " ").replace("\x01", ">"), sel))
        combs.append(pending or " ")
        pending = None
    if not parts or pending is not None:
        raise ValueError(f"対応していない CSS セレクタです: {sel!r}")
    ids = sum(1 for _t, _c, i, _a in parts if i)
    cls = sum(len(c) + len(a) for _t, c, _i, a in parts)
    types = sum(1 for t, _c, _i, _a in parts if t)
    return (parts, combs), (ids, cls, types)


def _split_blocks(css):
    """CSS 文字列 → [(prelude, body)]。@keyframes などの入れ子のブロックはまとめて 1 つにする。"""
    out, i, n = [], 0, len(css)
    while i < n:
        j = i
        while j < n and css[j] not in "{};":
            j += 1
        prelude = css[i:j].strip()
        if j >= n:
            if prelude:
                raise ValueError(f"CSS を解釈できません: {prelude[:60]!r}")
            break
        if css[j] == ";":                      # @charset "UTF-8"; などの文
            out.append((prelude, None))
            i = j + 1
            continue
        if css[j] == "}":
            raise ValueError(f"CSS を解釈できません: {css[i:j + 1][:60]!r}")
        depth, k = 1, j + 1
        while k < n and depth:
            depth += {"{": 1, "}": -1}.get(css[k], 0)
            k += 1
        if depth:
            raise ValueError(f"CSS の括弧が閉じていません: {prelude[:60]!r}")
        out.append((prelude, css[j + 1:k - 1]))
        i = k
    return out


def _clean_css(css):
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    return css.replace("<![CDATA[", "").replace("]]>", "")


# var(--名前) と var(--名前, 代わりの値) (代わりの値の中の括弧は 1 段まで)
_VAR = re.compile(r"var\(\s*(--[\w-]+)\s*(?:,\s*((?:[^()]|\([^()]*\))*))?\)", re.I)


def _is_root_selector(sel, root_id):
    """図全体の変数の定義として受け付けるセレクタか。

    `svg` / `#ルートの ID` / `svg#ルートの ID` と、最後の部品が `:root` のもの (`:root` と、Mermaid が書く `#my-svg :root`。
    後者は CSS の規則ではどの要素にも当たらないが、Mermaid は同じ書体を `#my-svg` にも書くので、図全体の定義として扱っても
    見た目は変わらない。書き換えの前後を Chromium で描いて確かめた)。
    """
    s = " ".join(sel.split())
    if re.fullmatch(r"(?:.*[\s>])?(?:svg)?:root", s, re.I) or s.lower() == "svg":
        return True
    return bool(root_id) and s in (f"#{root_id}", f"svg#{root_id}")


def _add_variable(out, k, v):
    if k in out and out[k] != v:
        raise ValueError(f"CSS の変数 {k} に違う値の定義が複数あります (どの要素に効くかを決められないため)")
    out[k] = v


def _collect_variables(css, root_id=None):
    """CSS の変数 (`--名前`) の定義を集める (Mermaid は `:root` で書体などを定義する)。

    同じ名前に違う値の定義があれば ValueError (どの要素にどちらが効くかを静的に決められないため)。
    定義はルートに当たるセレクタの規則だけで受け付け、ほかの規則 (クラス・擬似クラス・結合子つきなど) での定義は
    ValueError (定義した要素とその子孫にしか効かないのに、全体に効かせてしまうため)。
    """
    out = {}
    for prelude, body in _split_blocks(_clean_css(css)):
        if body is None or prelude.startswith("@"):
            continue
        defs = {k: vals for k, (vals, _imp) in _parse_decls(body).items() if k.startswith("--")}
        if not defs:
            continue
        if not all(_is_root_selector(sel, root_id) for sel in prelude.split(",")):
            raise ValueError(f"ルート以外のセレクタで CSS の変数を定義する規則には対応していません: {prelude[:60]!r}")
        for k, vals in defs.items():
            _add_variable(out, k, vals[-1].strip())
    return out


def _resolve_vars(value, variables, depth=0):
    """値の中の var() を定義の値 (無ければ代わりの値) に置き換える。どちらも無ければ ValueError。"""
    if "var(" not in value.lower():
        return value
    if depth > 10:
        raise ValueError("CSS の変数の参照が深すぎるか、循環しています")

    def repl(m):
        name, fallback = m.group(1), m.group(2)
        if name in variables:
            return _resolve_vars(variables[name], variables, depth + 1)
        if fallback is not None:
            return _resolve_vars(fallback.strip(), variables, depth + 1)
        raise ValueError(f"定義の無い CSS の変数を使っています: {name}")

    return _resolve_vars(_VAR.sub(repl, value), variables, depth + 1)


def _parse_css(css, order_start, report, variables):
    """CSS 文字列 → [(selector, specificity, order, decls)]。decls は {prop: ([value, …], important)}。

    `var()` は variables (`_collect_variables`) の値に置き換える。変数の定義だけの規則は捨てる。
    """
    css = _clean_css(css)
    rules, order = [], order_start
    for prelude, body in _split_blocks(css):
        if prelude.startswith("@"):
            name = prelude[1:].split(None, 1)[0].lower() if len(prelude) > 1 else ""
            if body is None and name == "charset":
                continue
            if name.endswith("keyframes"):      # @keyframes / @-webkit-keyframes: 静止画には効かない
                report["skipped_keyframes"] += 1
                continue
            raise ValueError(f"@ 規則 ({prelude.split(None, 1)[0]}) を含む CSS には対応していません")
        if body is None:
            raise ValueError(f"CSS を解釈できません: {prelude[:60]!r}")
        decls = {k: v for k, v in _parse_decls(body).items() if not k.startswith("--")}
        if not decls:                           # 変数の定義だけ (Mermaid の :root) や空の規則は効かない
            report["skipped_empty_rules"] += 1
            continue
        for k, (vals, imp) in list(decls.items()):
            new = [_resolve_vars(v, variables) for v in vals]
            if new != vals:
                report["variables_resolved"] += 1
                decls[k] = (new, imp)
        if "font" in decls:
            raise ValueError(f"一括指定の font には対応していません: {prelude[:60]!r}")
        for sel in prelude.split(","):
            parts, spec = _parse_selector(sel)
            rules.append((parts, spec, order, decls))
            order += 1
    return rules, order


def _match_part(el, part):
    tag, classes, ident, attrs = part
    if tag and _local(el.tag) != tag:
        return False
    if classes and not classes <= set((el.get("class") or "").split()):
        return False
    if ident and el.get("id") != ident:
        return False
    for name, op, val, nocase in attrs:
        got = el.get(name)
        if got is None:
            return False
        if op is None:
            continue
        g, v = (got.lower(), val.lower()) if nocase else (got, val)
        if op == "=":
            ok = g == v
        elif op == "~=":
            ok = v in g.split()
        elif op == "|=":
            ok = g == v or g.startswith(v + "-")
        elif op == "^=":
            ok = bool(v) and g.startswith(v)
        elif op == "$=":
            ok = bool(v) and g.endswith(v)
        else:                                   # *=
            ok = bool(v) and v in g
        if not ok:
            return False
    return True


def _matches(el, selector):
    """子孫 (空白) と子 (>) の結合子のセレクタの照合 (右端 = el から左へ。子孫は祖先をさかのぼって試す)。"""
    parts, combs = selector

    def rec(node, i):
        if not _match_part(node, parts[i]):
            return False
        if i == 0:
            return True
        parent = node.getparent()
        if combs[i] == ">":
            return parent is not None and rec(parent, i - 1)
        while parent is not None:
            if rec(parent, i - 1):
                return True
            parent = parent.getparent()
        return False

    return rec(el, len(parts) - 1)


def _own_value(el, prop):
    """要素自身の値 (style が表示属性より強い。style に代替が並べば最後のもの)。無ければ None。"""
    st, _imp = _parse_style(el.get("style"))
    if prop in st:
        return st[prop][-1]
    return el.get(prop)


def _inherited_value(el, prop):
    """要素自身か祖先の値 (継承する性質。`inherit` はさらに上をたどる)。どこにも無ければ None。"""
    node = el
    while node is not None:
        if isinstance(node.tag, str):
            v = _own_value(node, prop)
            if v is not None and v.strip().lower() != "inherit":
                return v
        node = node.getparent()
    return None


# ---- 色の書き換え
_NUM = r"[+-]?(?:\d+\.?\d*|\.\d+)(?:e[+-]?\d+)?"
_COLOR_FN = re.compile(r"^\s*(rgba?|hsla?)\(\s*(.*?)\s*\)\s*$", re.I)


def _channel(tok, scale):
    """`128` / `50%` → 0〜1 (scale は数値のときの最大値)。"""
    tok = tok.strip()
    if re.fullmatch(_NUM + "%", tok, re.I):
        v = float(tok[:-1]) / 100
    elif re.fullmatch(_NUM, tok, re.I):
        v = float(tok) / scale
    else:
        raise ValueError(f"色の値を解釈できません: {tok!r}")
    return min(max(v, 0.0), 1.0)


def _hue(tok):
    m = re.fullmatch(r"(" + _NUM + r")(deg|grad|rad|turn)?", tok.strip(), re.I)
    if not m:
        raise ValueError(f"色相を解釈できません: {tok!r}")
    v, unit = float(m.group(1)), (m.group(2) or "deg").lower()
    deg = {"deg": v, "grad": v * 0.9, "rad": v * 57.29577951308232, "turn": v * 360}[unit]
    return (deg % 360) / 360


def _parse_color_fn(value):
    """`rgba(…)` / `hsl(…)` などを (#rrggbb, alpha) にする。色の関数でないか、解釈できない値 (Mermaid の
    `hsl(…, NaN%, …)` や `rgb(from …)`) なら None (書き換えない。CSS を読む描画系も解釈できない値は無視する)。"""
    m = _COLOR_FN.match(value)
    if not m:
        return None
    fn, body = m.group(1).lower(), m.group(2)
    if "/" in body:                             # rgb(232 232 232 / 0.8)
        main, alpha = body.split("/", 1)
        toks, alpha = main.replace(",", " ").split(), alpha.strip()
    else:
        toks = body.replace(",", " ").split()
        alpha = toks.pop() if len(toks) == 4 else None
    if len(toks) != 3:
        return None
    try:
        if fn.startswith("rgb"):
            r, g, b = (_channel(t, 255) for t in toks)
        else:
            h, s, light = _hue(toks[0]), _channel(toks[1], 100), _channel(toks[2], 100)
            r, g, b = colorsys.hls_to_rgb(h, light, s)
        a = 1.0 if alpha is None else _channel(alpha, 1)
    except ValueError:
        return None
    return "#%02x%02x%02x" % tuple(round(c * 255) for c in (r, g, b)), a


def _opacity_value(text):
    try:
        return _channel(text, 1)
    except ValueError:
        raise ValueError(f"不透明度の値 {text!r} と色の不透明度を掛け合わせられません")


def _normalize_dasharray(value):
    """stroke-dasharray を書き換える。返り値: (新しい値, 種類)。種類は "zero" / "doubled" / None (書き換えない)。

    合計が 0 の並び (`0` や Mermaid が出す `0 0`) は規則では実線と同じなので `none` にする (Aspose.Slides の評価版は、
    0 を含む 2 個以上の値の点線があると図全体を描かない。実測)。値の数が奇数の並びは 2 回繰り返す
    (`2` → `2, 2`)。数でない値・負の値・偶数で合計が 0 でない並びはそのまま。"""
    toks = [t for t in re.split(r"[\s,]+", value.strip()) if t]
    if not toks:
        return value, None
    nums = [re.fullmatch(r"(" + _NUM + r")(?:%|[a-z]{1,4})?", t, re.I) for t in toks]
    if not all(nums):
        return value, None
    vals = [float(m.group(1)) for m in nums]
    if any(v < 0 for v in vals):
        return value, None
    if sum(vals) == 0:
        return "none", "zero"
    if len(toks) % 2 == 0:
        return value, None
    return ", ".join(toks * 2), "doubled"


def _normalize_colors(root, report):
    """rgba() / hsl() と grey 系の色名を 16 進の色 (と不透明度) に、stroke-dasharray を描画系を選ばない形に書き換え、
    線の無い図形の opacity を fill-opacity に掛け合わせる。

    葉の側から書き換える (文字色の明示で子の <text> に写った rgba() を先に片づけ、親の判定を正しくするため)。
    """
    for el in reversed(list(root.iter())):
        if not _is_svg(el):
            continue
        st, imp = _parse_style(el.get("style"))
        changed = False
        for prop in _COLOR_PROPS:                   # grey 系の色名
            if prop in st:
                new = [_GREY_NAMES.get(v.strip().lower(), v) for v in st[prop]]
                if new != st[prop]:
                    st[prop] = new
                    report["named_colors_converted"] += 1
                    changed = True
            if el.get(prop) is not None and el.get(prop).strip().lower() in _GREY_NAMES:
                el.set(prop, _GREY_NAMES[el.get(prop).strip().lower()])
                report["named_colors_converted"] += 1
        for prop, op in _COLOR_OPACITY.items():
            in_style = prop in st
            vals = st[prop] if in_style else ([el.get(prop)] if el.get(prop) is not None else [])
            parsed = [_parse_color_fn(v) for v in vals]
            if not any(parsed):
                continue
            if len(vals) > 1:
                raise ValueError(f"{prop} の代替の値に rgba() / hsl() があります (不透明度に書き換えられません)")
            hexcol, alpha = parsed[0]
            if alpha < 1.0:
                # 不透明度は子に受け継がれる。子が色だけ (不透明度を持たない) か不透明度だけを持つと、
                # 書き換えの前後で子の見え方が変わるので止める (色と不透明度の両方を持つ子・どちらも持たない子・
                # 色が none の子は変わらない)
                for d in el.iterdescendants():
                    if not _is_svg(d):
                        continue
                    own_p, own_o = _own_value(d, prop), _own_value(d, op)
                    if (own_p is None) != (own_o is None) and (own_p or "").strip().lower() != "none":
                        raise ValueError(f"子が {prop} か {op} の片方だけを持つ要素の {prop} の rgba() / hsl() は"
                                         "不透明度に書き換えられません")
                # 元の不透明度は、継承する性質 (fill-opacity / stroke-opacity) なら祖先から受け継いだ値も含める
                # (自身に書くと受け継ぎが切れるため)
                base = _inherited_value(el, op) if op in _INHERITED_OPACITY else _own_value(el, op)
                new_op = alpha * (1.0 if base is None else _opacity_value(base))
                st[op] = [f"{new_op:.4g}"]
                if el.get(op) is not None:
                    el.set(op, f"{new_op:.4g}")
            st[prop] = [hexcol]
            if el.get(prop) is not None:
                el.set(prop, hexcol)
            report["colors_converted"] += 1
            changed = True
        for prop in ("stroke-dasharray",):
            if prop in st:
                res = [_normalize_dasharray(v) for v in st[prop]]
                if any(kind for _v, kind in res):
                    st[prop] = [v for v, _kind in res]
                    for _v, kind in res:
                        if kind:
                            report[f"dasharray_{kind}"] += 1
                    changed = True
            if el.get(prop) is not None:
                new, kind = _normalize_dasharray(el.get(prop))
                if kind:
                    el.set(prop, new)
                    report[f"dasharray_{kind}"] += 1
        # 線の無い図形が opacity と fill-opacity を両方持つときは、opacity を fill-opacity に掛け合わせて外す
        # (線も子も無いので同じ見た目。Aspose.Slides の評価版は fill-opacity と並ぶ opacity を無視する。実測。
        # 線や矢印の印 (marker) があると opacity はそれらにも掛かるので、掛け合わせない)
        if _local(el.tag) in _FOLD_OPACITY_SHAPES:
            def cur(p):                             # この要素の今の値 (書き換えの途中の st を含む)。無ければ親から
                v = st[p][-1] if p in st else el.get(p)
                if v is not None and v.strip().lower() != "inherit":
                    return v
                return _inherited_value(el.getparent(), p) if p != "opacity" and p != "fill-opacity" else None
            own_o, own_fo = cur("opacity"), cur("fill-opacity")
            stroke = cur("stroke")
            markers = [cur(m) for m in _MARKER_LONGHANDS]
            if own_o is not None and own_fo is not None \
                    and (stroke is None or stroke.strip().lower() == "none") \
                    and all(m is None or m.strip().lower() == "none" for m in markers):
                folded = f"{_opacity_value(own_fo) * _opacity_value(own_o):.4g}"
                for p in ("opacity", "fill-opacity"):
                    st.pop(p, None)
                    if el.get(p) is not None:
                        del el.attrib[p]
                st["fill-opacity"] = [folded]
                report["opacity_folded"] += 1
                changed = True
        if changed:
            el.set("style", _format_style(st))


def make_self_contained(svg_bytes):
    """SVG のバイト列を CSS に頼らない形へ書き換える。返り値: (新しいバイト列, 報告 dict)。"""
    parser = etree.XMLParser(remove_blank_text=False, strip_cdata=False, resolve_entities=False)
    root = etree.fromstring(svg_bytes, parser)
    dtd = root.getroottree().docinfo.internalDTD
    if (dtd is not None and list(dtd.iterentities())) or any(
            isinstance(n, etree._Entity) for n in root.iter()):
        raise ValueError("内部 DTD の実体参照を持つ SVG には対応していません (書き出すと整形式でなくなるため)")
    for pi in root.itersiblings(preceding=True):
        if isinstance(pi, etree._ProcessingInstruction) and pi.target == "xml-stylesheet":
            raise ValueError("外部の CSS を読む <?xml-stylesheet?> には対応していません (pptx には付いていかないため)")
    styles = [el for el in root.iter() if _local(el.tag) == "style"]
    report = {"style_blocks": len(styles), "rules": 0, "elements_changed": 0,
              "declarations_written": 0, "text_fill_added": 0, "xml_space_added": 0,
              "skipped_keyframes": 0, "skipped_empty_rules": 0, "attributes_removed": 0,
              "zero_size_removed": 0, "colors_converted": 0, "named_colors_converted": 0, "dasharray_doubled": 0,
              "dasharray_zero": 0, "opacity_folded": 0, "important_removed": 0, "variables_resolved": 0}

    for st in styles:
        if (st.get("type") or "text/css").lower() not in ("text/css", ""):
            raise ValueError(f"CSS 以外の <style> には対応していません: type={st.get('type')!r}")
        if (st.get("media") or "all").strip().lower() not in ("all", "screen", ""):
            raise ValueError(f"media 属性つきの <style> には対応していません: media={st.get('media')!r}")
    # itertext() は XML のコメントの中身を除き、その後ろの文字を含む (コメントより後ろの規則を落とさない)
    css_texts = ["".join(st.itertext()) for st in styles]
    variables = _collect_variables("\n".join(css_texts), root.get("id"))
    # 要素の style での変数の定義は、ルート要素なら全体の定義として受け付け、ほかの要素なら止める
    # (その要素と子孫にしか効かないため)
    for el in root.iter():
        if not isinstance(el.tag, str) or "--" not in (el.get("style") or ""):
            continue
        defs = {k: vals for k, vals in _parse_style(el.get("style"))[0].items() if k.startswith("--")}
        if not defs:
            continue
        if el is not root:
            raise ValueError(f"ルート以外の要素 (<{_local(el.tag)}>) の style で CSS の変数を定義する形には対応していません")
        for k, vals in defs.items():
            _add_variable(variables, k, vals[-1].strip())
    rules, order = [], 0
    for css in css_texts:
        new_rules, order = _parse_css(css, order, report, variables)
        rules.extend(new_rules)
    report["rules"] = len(rules)
    # 優先順位の低い順 (詳細度 → 記述順) に並べ、後勝ちで重ねる
    rules.sort(key=lambda r: (r[1], r[2]))

    if styles:
        # <style> を外すと、要素自身の style の var() が定義 (:root の変数) を失うので、ここで値に置き換える
        # (定義も代わりの値も無ければ止める)
        for el in root.iter():
            if isinstance(el.tag, str) and "var(" in (el.get("style") or "").lower():
                own, own_imp = _parse_style(el.get("style"))
                own = {k: [_resolve_vars(v, variables) for v in vals] for k, vals in own.items()
                       if not k.startswith("--")}
                el.set("style", "; ".join(f"{k}: {v}{' !important' if k in own_imp else ''}"
                                          for k, vals in own.items() for v in vals) + (";" if own else ""))
                report["variables_resolved"] += 1

    for el in root.iter():
        if not isinstance(el.tag, str) or _local(el.tag) == "style":
            continue
        if not _is_svg(el):
            # <metadata> の中の RDF など、SVG でない要素には書かない。ただし foreignObject の中の HTML に
            # 当たる規則は、書かずに捨てると見た目が変わるので止める
            if any(_local(a.tag) == "foreignObject" for a in el.iterancestors()) and \
                    any(_matches(el, parts) for parts, _s, _o, _d in rules):
                raise ValueError(f"foreignObject の中の要素 (<{_local(el.tag)}>) に当たる CSS には対応していません")
            continue
        normal, important = {}, {}
        for parts, _spec, _order, decls in rules:
            if _matches(el, parts):
                for prop, (vals, imp) in decls.items():
                    (important if imp else normal)[prop] = vals
        if not normal and not important:
            continue
        own, own_imp = _parse_style(el.get("style"))
        changed = False
        for prop in list(normal) + [p for p in important if p not in normal]:
            if prop in own_imp:
                continue                                    # インラインの !important が最も強い
            if prop in important:
                vals = important[prop]                      # 規則の !important はインラインより強い
            elif prop in own:
                continue                                    # インライン > 規則 (!important でないもの)
            else:
                vals = normal[prop]
            if any(v.lower() == "inherit" for v in vals):
                if len(vals) > 1:
                    raise ValueError(f"inherit と別の値を並べた宣言には対応していません: {prop}")
                if prop not in _INHERITED:
                    raise ValueError(f"継承しない性質の inherit には対応していません: {prop}")
                if prop in own:
                    del own[prop]
                    changed = True
                if el.get(prop) is not None:                # 表示属性を外して親から受け継がせる
                    del el.attrib[prop]
                    report["attributes_removed"] += 1
                    changed = True
                continue
            if prop == "white-space" and vals[-1].lower() in ("pre", "pre-wrap"):
                if el.get(XML_SPACE) != "preserve":
                    el.set(XML_SPACE, "preserve")
                    report["xml_space_added"] += 1
            if own.get(prop) != vals:
                own[prop] = list(vals)
                report["declarations_written"] += 1
                changed = True
        if changed:
            if own:
                el.set("style", _format_style(own))
            elif "style" in el.attrib:
                del el.attrib["style"]
            report["elements_changed"] += 1

    # <use> などから id で参照される要素 (文字色の明示と <rect> の除去で外す)
    referenced = set()
    for el in root.iter():
        if not isinstance(el.tag, str):
            continue
        for k, v in el.attrib.items():
            if "href" in k or "url(" in v:
                referenced.update(re.findall(r"#([\w.-]+)", v))

    # テキストの文字色を明示する (輪郭化しても色が残るように)
    for el in root.iter():
        if not _is_svg(el) or _local(el.tag) != "text" or _own_value(el, "fill") is not None:
            continue
        if any(_local(a.tag) in _REUSED for a in el.iterancestors()):
            continue
        if any(n.get("id") in referenced for n in [el, *el.iterancestors()] if n.get("id")):
            continue                                        # <use> の側の色を受け継ぐ
        node, fill = el.getparent(), None
        while node is not None:
            f = _own_value(node, "fill")
            if f is not None and f.lower() != "inherit":
                fill = f
                break
            node = node.getparent()
        own, _imp = _parse_style(el.get("style"))
        own["fill"] = [fill if fill is not None else "#000000"]
        el.set("style", _format_style(own))
        report["text_fill_added"] += 1

    # 幅か高さを持たない (0 か未指定の) <rect> を取り除く。属性にも CSS の性質にも幅か高さが
    # 無い四角は描かれない (librsvg も描かない) が、Aspose.Slides の評価版は表示域いっぱいの四角として描き、
    # Mermaid の図 (ラベルの背景の <rect/> を出す) を覆った。書き出した後の style の width / height も見る
    # (SVG 2 では CSS で寸法を与えられるので、属性だけを見ると CSS で寸法を与えた四角まで消してしまう)。
    # id で参照されているものは残す
    for el in list(root.iter()):
        if not _is_svg(el) or _local(el.tag) != "rect" or (el.get("id") and el.get("id") in referenced):
            continue
        size = [_own_value(el, "width"), _own_value(el, "height")]
        if any(v is None or re.fullmatch(r"\s*[+-]?0*\.?0*(?:e[+-]?\d+)?\s*(?:px|%|[a-z]{2})?\s*", v, re.I)
               for v in size):
            el.getparent().remove(el)
            report["zero_size_removed"] += 1

    _normalize_colors(root, report)

    # 要素の style に残った !important を外す (<style> を外すと要素の style より強い指定は無いので、見た目は変わらない。
    # Mermaid の classDef / style が !important 付きで書き、描画系によっては無効な宣言として扱うため)
    for el in root.iter():
        if not isinstance(el.tag, str) or "important" not in (el.get("style") or "").lower():
            continue
        own, own_imp = _parse_style(el.get("style"))
        if own_imp:
            el.set("style", _format_style(own))
            report["important_removed"] += 1

    for st in styles:
        parent = st.getparent()
        if st.tail and st.tail.strip():
            raise ValueError("<style> の後ろに文字があります")
        parent.remove(st)

    out = etree.tostring(root, xml_declaration=True, encoding="UTF-8")
    return out, report


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    if len(argv) != 2:
        print("使い方: svg_safe.py <in.svg> <out.svg>", file=sys.stderr)
        return 2
    with open(argv[0], "rb") as f:
        data = f.read()
    out, report = make_self_contained(data)
    with open(argv[1], "wb") as f:
        f.write(out)
    print(f"{argv[0]} -> {argv[1]}: {report}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
