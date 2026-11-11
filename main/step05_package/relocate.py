#!/usr/bin/env python3
"""relocate.py — 最終提出 docx の構成組み替えと表の体裁 lint (コンテナ内本体)。

`package.py` (step05) から呼ばれる。BioHealth Informatics のように「原稿本体は
Title page / Abstract / Main text / Declarations / References / **Figure legends** /
**Tables** の順」と定める誌のために、ビルド済み docx を **OOXML レベルで**組み替える。
原稿 (`src/main.md`) は雑誌非依存に保つ (図表は本文中の自然な位置に書く) という本テンプレの
方針上、順序の入れ替えは提出物を作る側の仕事になる。

【発火条件 (profile 駆動。キー未指定の誌では何もしない)】
  - `tables.placement: end`         → 本文中の表を文書末尾へ移し、元位置に `[Table N about here]`
  - `tables.placement: separate`    → 本文中の表を**本文から外して呼び出し側へ返す** (1 表 1 ファイルの
                                      書き出しは package.py)。元位置の扱いは end と同じで、本文は
                                      テキストだけになる (BHI の規定は本文末尾・別ファイルの
                                      どちらも認めており、BHI のプロファイルは別ファイルを既定にする)
  - `figures.legends_section: <題>` → 図の題+凡例を References の後の新ページへ集約
  ※ **`figures.placement` は発火条件に使わない**。値を持つプロファイルがあるが、
    コードからは一度も読まれない予約キーで、これで発火させると、図を別ファイルで出すだけで
    凡例の集約までは求めない誌でも図凡例の集約が動いてしまう。

【移設の単位 (図表の題と凡例を書き分ける記法。docs/journal-bhi.md §7.6)】
  題 = キャプション段落 / 凡例 = 直後に連続する `Legend` 段落**すべて**。
    図: `CaptionedFigure`(画像) → `ImageCaption`(題) → `Legend`(凡例) …
    表: `TableCaption`(題)     → `w:tbl`            → `Legend`(凡例) …
  - **凡例段落は複数になりうる**。凡例 Div の中で段落を分けると `Legend` が
    複数並ぶ。単数前提で実装すると 2 段落目が本文に取り残され、見た目が本文と変わらないため
    校正刷りまで気づけない。
  - 図の集約では `CaptionedFigure` 段落 (= `strip_inline_figures` が `[Figure N about here]` に
    置換済み) は**動かさない**。本文の元位置に残すのが規定の要求である。

【テキストボックス内は対象外】
  `.textbox` の中身は本文の流れの外にある。本モジュールは **`w:body` の直接の子だけ**を走査
  するので、`w:p/w:r/mc:AlternateContent/…/w:txbxContent/` の下に入るテキストボックス内容は
  構造的に対象外になる (`_in_body_flow` で二重に確かめる)。

【挿入位置は常に `w:sectPr` の直前】
  `w:sectPr` は `w:body` の**最後の子でなければならない**。素直に `body.append()` すると
  sectPr の後ろに要素が並び、Word が修復を促す。

【移設順序は Figure Legends → Tables】
  規定の要求順が References → Figure legends → Tables であるため、末尾へ順次差し込む本実装
  では Figure Legends を先に置く。References の「後」は、References が本文の最終節である以上
  sectPr 直前に差し込めば自動的に満たされる (見出しの位置を探しには行かない)。

【ブックマークは動かさない】
  pandoc-crossref は `fig:x` / `tbl:x` のブックマークを図表の前後に置き、本文の "Fig. 1" /
  "Table 1" はそこへの `w:hyperlink` になっている (実測)。移設対象の段落だけを抜き、
  `w:bookmarkStart` / `w:bookmarkEnd` は元位置に残すので、
    - ブックマークの開始/終了の対応が壊れない (片方だけ動かす事故が起きない)
    - 本文の相互参照リンクは `[Figure N about here]` / `[Table N about here]` の位置に着地する
  表では、外したキャプション+表の位置にプレースホルダ段落を差し込むため、ブックマークは
  空にならずプレースホルダを包む (図と同じ形になる)。
"""

import re
import sys

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
WP_NS = "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"
XML_NS = "http://www.w3.org/XML/1998/namespace"


def W(tag):
    return f"{{{W_NS}}}{tag}"


def WP(tag):
    return f"{{{WP_NS}}}{tag}"


TXBX_CONTENT = W("txbxContent")

# 段落スタイル (pandoc の docx writer が付ける名前。reference.docx にも同名で存在する)
STYLE_IMAGE_CAPTION = "ImageCaption"
STYLE_TABLE_CAPTIONS = ("TableCaption", "Caption")   # 表の題 (Caption は旧 pandoc 互換)
STYLE_LEGEND = "Legend"                              # 凡例 (patch_reference_docx.py が注入する段落スタイル)
STYLE_PLACEHOLDER = "BodyText"                       # プレースホルダ段落の体裁

# 走査中に「無いもの」として読み飛ばす要素。段落・表の間に挟まる注釈系で、
# 「キャプションの直後の Legend」という連続性を切らない (ブックマークが典型)。
TRANSPARENT = {
    W("bookmarkStart"), W("bookmarkEnd"),
    W("commentRangeStart"), W("commentRangeEnd"),
    W("proofErr"), W("permStart"), W("permEnd"),
}

# キャプション先頭の "Figure 1: " / "Table 1: " から番号を取る (pandoc-crossref が入れる接頭辞)。
# 接頭辞の語は defaults.yaml の figureTitle / tableTitle で決まるため語自体は縛らない。
_CAPTION_NUM = re.compile(r"^\s*\S+\s*(\d+)\s*[:：.]")
# 本文に残るプレースホルダ (strip_inline_figures が入れる文字列と対で保つこと)
_PLACEHOLDER_NUM = re.compile(r"\[Figure\s+(\d+)\s+about here\]")

# tables.placement の値
TABLE_PLACEMENTS = ("inline", "end", "separate")


def table_placement(profile):
    """`tables.placement` を正規化して返す (inline / end / separate)。

    **未知の綴りはエラーで停止する**。`== "end"` の比較だけにすると、それ以外の値が
    黙って inline (= 表を本文に残す) になり、`separate` の綴り違いで表が本文に残っても
    警告が出ない。本文をテキストだけにする誌では、それがそのまま規定に合わない提出物になる。
    図の形式で未知の綴りを停止にしたのと同じ扱い。既存 4 誌はこのキーを持たない
    (既定 inline) ので影響しない。
    """
    tables_cfg = profile.get("tables") if isinstance(profile.get("tables"), dict) else {}
    raw = tables_cfg.get("placement")
    value = str(raw or "inline").strip().lower()
    if value not in TABLE_PLACEMENTS:
        sys.exit(f"エラー: tables.placement の値 '{raw}' は不正です "
                 f"({' / '.join(TABLE_PLACEMENTS)} のいずれかを指定してください)。")
    return value


# =====================================================================
# 小道具
# =====================================================================

def _pstyle(el):
    """段落の pStyle 値 (段落でない・スタイル無しなら None)。"""
    if el.tag != W("p"):
        return None
    st = el.find(f"{W('pPr')}/{W('pStyle')}")
    return st.get(W("val")) if st is not None else None


def _text(el):
    """要素配下の w:t を連結した文字列。"""
    return "".join(t.text or "" for t in el.iter(W("t")))


def _localname(el):
    """`{名前空間}top` → `w:top` (警告文に出す用)。"""
    tag = el.tag if isinstance(el.tag, str) else str(el.tag)
    return "w:" + tag.rsplit("}", 1)[-1]


def _in_body_flow(el):
    """el が本文の流れの上にあるか (テキストボックス内なら False)。

    本モジュールは w:body の直接の子しか走査しないので通常は常に True になるが、
    「テキストボックス内は対象外」という要求を実装側でも明示しておく。
    """
    p = el.getparent()
    while p is not None:
        if p.tag == TXBX_CONTENT:
            return False
        p = p.getparent()
    return True


def _caption_number(text):
    """キャプション本文から番号を取る。取れなければ None。"""
    m = _CAPTION_NUM.match(text or "")
    return int(m.group(1)) if m else None


def _next_significant(children, i):
    """children[i] の次にある「読み飛ばさない」要素の添字 (無ければ len)。"""
    j = i + 1
    while j < len(children) and children[j].tag in TRANSPARENT:
        j += 1
    return j


def _prev_significant(children, i):
    """children[i] の前にある「読み飛ばさない」要素の添字 (無ければ -1)。"""
    j = i - 1
    while j >= 0 and children[j].tag in TRANSPARENT:
        j -= 1
    return j


def _make_paragraph(etree, text, style=None, page_break_before=False):
    """段落 (w:p) を 1 つ作る。"""
    p = etree.Element(W("p"))
    if style or page_break_before:
        ppr = etree.SubElement(p, W("pPr"))
        # CT_PPr の要素順は pStyle → keepNext → keepLines → pageBreakBefore … (ECMA-376)。
        # 順序を守らないと Word が読み込みを拒む。
        if style:
            etree.SubElement(ppr, W("pStyle")).set(W("val"), style)
        if page_break_before:
            etree.SubElement(ppr, W("pageBreakBefore"))
    if text:
        r = etree.SubElement(p, W("r"))
        t = etree.SubElement(r, W("t"))
        t.set(f"{{{XML_NS}}}space", "preserve")
        t.text = text
    return p


def _set_page_break_before(etree, el):
    """段落に pageBreakBefore を立てる。段落でなければ False を返す (呼び側が別手段を採る)。

    **前提: pStyle を持つ段落に対してのみ呼ぶこと**。CT_PPr の要素順は
    pStyle → keepNext → keepLines → pageBreakBefore … なので、pStyle があればその直後に挿せば
    必ず正しい位置になる。pStyle が無い場合は先頭に挿すため、keepNext / keepLines を持つ段落
    では順序が規格から外れる。現在の呼び出し元は「末尾へ移した表のかたまりの先頭」だけで、
    そこは必ず `TableCaption` 段落 (pStyle あり) か `w:tbl` (段落でないので False で別経路) の
    どちらかになるため到達しない。別の場所から呼ぶときは挿入位置の計算を見直すこと。
    """
    if el.tag != W("p"):
        return False
    ppr = el.find(W("pPr"))
    if ppr is None:
        ppr = etree.Element(W("pPr"))
        el.insert(0, ppr)
    if ppr.find(W("pageBreakBefore")) is not None:
        return True
    # pStyle の直後 (無ければ先頭) に入れる
    style = ppr.find(W("pStyle"))
    node = etree.Element(W("pageBreakBefore"))
    if style is not None:
        style.addnext(node)
    else:
        ppr.insert(0, node)
    return True


def _appender(body):
    """本文の末尾 (w:sectPr の直前) へ 1 要素ずつ差し込む関数を返す。

    **添字ではなく要素を基準にする**こと。移設は「元位置から抜いて末尾へ入れる」操作なので、
    抜いた要素が挿入位置より前にあると添字が 1 ずれる。添字で `body.insert()` すると、
    ずれた分だけ sectPr の**後ろ**に要素が並び、`w:sectPr` が w:body の最後の子でなくなる
    (Word が文書の修復を促す。実測)。
    """
    sect_pr = body.find(W("sectPr"))     # body 直下の sectPr は 1 個 (段落内のものは w:pPr 配下)
    if sect_pr is not None:
        return lambda el: sect_pr.addprevious(el)
    return body.append


# =====================================================================
# 移設対象の収集
# =====================================================================

def collect_figure_groups(body):
    """図の「題 + 凡例」の組を文書順に集める。

    返り値: [{"caption": <w:p ImageCaption>, "legends": [<w:p Legend>, ...], "number": int|None}]
    `CaptionedFigure` (画像=プレースホルダ) は組に含めない (本文に残すため)。
    """
    children = list(body)
    groups = []
    for i, el in enumerate(children):
        if _pstyle(el) != STYLE_IMAGE_CAPTION or not _in_body_flow(el):
            continue
        legends = []
        j = _next_significant(children, i)
        while j < len(children) and _pstyle(children[j]) == STYLE_LEGEND:
            legends.append(children[j])
            j = _next_significant(children, j)
        groups.append({"caption": el, "legends": legends,
                       "number": _caption_number(_text(el))})
    return groups


def collect_table_groups(body):
    """表の「題 + 表 + 凡例」の組を文書順に集める。

    返り値: [{"caption": <w:p>|None, "table": <w:tbl>, "legends": [...], "number": int|None,
              "tbl_caption": str|None}]
    """
    children = list(body)
    groups = []
    for i, el in enumerate(children):
        if el.tag != W("tbl") or not _in_body_flow(el):
            continue
        caption = None
        k = _prev_significant(children, i)
        if k >= 0 and _pstyle(children[k]) in STYLE_TABLE_CAPTIONS:
            caption = children[k]
        legends = []
        j = _next_significant(children, i)
        while j < len(children) and _pstyle(children[j]) == STYLE_LEGEND:
            legends.append(children[j])
            j = _next_significant(children, j)
        # w:tblPr/w:tblCaption は pandoc がキャプション本文を複製して入れる代替テキスト。
        # 題の段落と一緒に動かす限り食い違わないが、移設時に検算する。
        tbl_cap = None
        node = el.find(f"{W('tblPr')}/{W('tblCaption')}")
        if node is not None:
            tbl_cap = node.get(W("val"))
        groups.append({"caption": caption, "table": el, "legends": legends,
                       "number": _caption_number(_text(caption)) if caption is not None else None,
                       "tbl_caption": tbl_cap})
    return groups


def body_placeholder_numbers(body):
    """本文に残る `[Figure N about here]` の番号を文書順に返す (strip_inline_figures の結果)。"""
    return [n for n, _ in body_placeholders(body)]


def body_placeholders(body):
    """本文のプレースホルダを文書順に [(番号, 題を持つか)] で返す。

    **なぜ「題を持つか」まで要るか**: 分離出力した図のファイル名 (`FigureN`) は
    プレースホルダ番号 = 本文の inline 図の出現順で決まるのに対し、集約する題の番号は
    pandoc-crossref が**題を持つ図だけ**に振る。したがって題の無い画像が本文の**途中**にあると、
    その位置より後ろの図ファイルがすべて凡例と 1 つずつずれる。末尾にまとまっているだけなら
    ずれは起きない。両者は対処も被害の大きさも違うので書き分ける必要がある。

    番号列どうしを `ph[:len(cap)] == cap` で比べても見分けられない。`ph` も `cap` も常に 1 から
    始まる連番なのでこの条件は**恒真**になり、危険なほう (途中に紛れている) の分岐に一度も
    到達しない (実測: 図 1 の直前に題の無い画像を 1 枚入れると全図がずれるのに、
    「題の無い図ファイルが並ぶ」という軽いほうの文面しか出なかった)。

    判定は番号ではなく**配置**で行う。pandoc は題つきの図を
    `CaptionedFigure`(画像) → `ImageCaption`(題) の 2 段落で出すので、
    プレースホルダを載せた段落が `CaptionedFigure` で、その次の意味のある要素が
    `ImageCaption` なら「題を持つ」と判定できる。題の無い画像は本文段落の中に
    inline で入る (1 段落に複数個入ることもある)。
    """
    children = list(body)
    out = []
    for i, el in enumerate(children):
        if el.tag != W("p"):
            continue
        nums = [int(m.group(1)) for m in _PLACEHOLDER_NUM.finditer(_text(el))]
        if not nums:
            continue
        j = _next_significant(children, i)
        titled = (_pstyle(el) == "CaptionedFigure"
                  and j < len(children) and _pstyle(children[j]) == STYLE_IMAGE_CAPTION)
        # 1 段落に複数のプレースホルダがある = inline の無題画像が並んでいる形なので、
        # そのときは題つきとみなさない (題つきは 1 段落 1 図。CLAUDE.md の執筆規約)。
        if len(nums) > 1:
            titled = False
        out.extend((n, titled) for n in nums)
    return out


# =====================================================================
# 番号の検算
# =====================================================================

def _check_sequence(numbers, kind, warnings):
    """番号が 1..n の連番 (= 本文の初出順) かを検算する。

    pandoc-crossref は図表を**本文の初出順**に採番し、キャプションは文書順に現れる。
    したがって「文書順に拾った番号が 1,2,3,… になっている」ことが初出順一致の必要十分条件になる。
    """
    if not numbers:
        return True
    if any(n is None for n in numbers):
        warnings.append(
            f"{kind}: 番号を読めないキャプションがあります "
            f"(拾えた番号: {[n for n in numbers if n is not None]})。"
            "移設後の並びが本文の初出順どおりか目視で確認してください。")
        return False
    if numbers != list(range(1, len(numbers) + 1)):
        warnings.append(
            f"★要注意: {kind} の番号が文書順に 1..{len(numbers)} の連番になっていません "
            f"(実際: {numbers})。移設すると本文の初出順と提出物の並びが食い違います。")
        return False
    return True


# =====================================================================
# 本体
# =====================================================================

def relocate(root, profile, log=print):
    """docx の w:document 直下を組み替える。

    **前提**: 本文の inline 図は `[Figure N about here]` に置換済みであること
    (`package.strip_inline_figures` を通した後に呼ぶ)。図が本文に埋まったまま題と凡例だけを
    末尾へ移すと図と題の対応が切れるため、呼び出し側 (`package.cmd_assemble`) は
    「最終モード かつ --keep-figures なし」でのみ本関数を呼ぶ。

    引数:
      root    : word/document.xml の根 (w:document)
      profile : 解決済み profile (journal_profile.resolve 済み)
    返り値: dict(warnings=[...], figures=N, tables=N, legends_section=str|None,
                 tables_separated=[{"number": int|None, "elements": [w:p|w:tbl, ...]}, ...])
      tables           : **末尾へ移した**表の組数 (placement: end のときだけ数える)
      tables_separated : 本文から外した表の組 (placement: separate のときだけ。文書順)。
                         elements は「題 + 表 + 凡例」で、親から外した状態で返す。
                         1 表 1 ファイルに書き出すのは呼び出し側 (package.write_table_files)
    """
    from lxml import etree

    figures_cfg = profile.get("figures") if isinstance(profile.get("figures"), dict) else {}
    tables_cfg = profile.get("tables") if isinstance(profile.get("tables"), dict) else {}
    legends_title = figures_cfg.get("legends_section")
    placement = table_placement(profile)
    tables_to_end = placement == "end"
    tables_separate = placement == "separate"
    tables_title = tables_cfg.get("section_title")

    out = {"warnings": [], "figures": 0, "tables": 0, "tables_separated": [],
           "legends_section": legends_title if legends_title else None}
    if not legends_title and not tables_to_end and not tables_separate:
        return out                      # キー未指定の誌では何もしない

    body = root.find(W("body"))
    if body is None:
        out["warnings"].append("w:body が見つからないため移設をスキップしました")
        return out
    warnings = out["warnings"]

    # --- 収集 (移設前に行う。移設すると文書順が変わるため) ---
    fig_groups = collect_figure_groups(body) if legends_title else []
    tbl_groups = collect_table_groups(body) if (tables_to_end or tables_separate) else []

    # --- 番号の検算 (移設前) ---
    if fig_groups:
        _check_sequence([g["number"] for g in fig_groups], "図 (Figure)", warnings)
        # 番号列どうしの比較 (`ph[:len(cap)] == cap`) は恒真になり、危険なほうの分岐に
        # 到達しない。**配置**で書き分ける (body_placeholders の説明を参照)。
        seq = body_placeholders(body)
        cap = [g["number"] for g in fig_groups]
        untitled = [n for n, titled in seq if not titled]
        if seq and untitled:
            # 題の無い画像が「末尾にまとまっている」か「途中に紛れている」かで被害が違う。
            n_tail = 0
            for _, titled in reversed(seq):
                if titled:
                    break
                n_tail += 1
            first_bad = untitled[0]
            if n_tail == len(untitled):
                warnings.append(
                    f"★要注意: 本文の図 {len(seq)} 件のうち **{len(untitled)} 件に題 "
                    f"(キャプション) がありません** (集約した題は {len(cap)} 個)。"
                    f"題の無い画像は末尾にまとまっている (Figure{first_bad} 以降) ので"
                    "**番号のずれは起きません**が、題の無い画像も `figures/` へ書き出されるため、"
                    "投稿系では題の無い図ファイルが並ぶことになります。"
                    "装飾目的の画像なら本文から外し、図なら `{#fig:...}` と題を付けてください。")
            else:
                warnings.append(
                    f"★要注意: 題 (キャプション) の無い画像が**本文の途中**にあります "
                    f"(最初は {first_bad} 個目。題の無い画像は全部で {len(untitled)} 件)。"
                    f"**`figures/Figure{first_bad}` 以降のファイルは、集約した凡例の "
                    f"Figure 番号と {len(untitled)} 個ずつずれます** "
                    f"(プレースホルダは {len(seq)} 個、集約した題は {len(cap)} 個)。"
                    "投稿系は**アップロードした順に図番号を割り当てる**ので、このまま出すと"
                    "図と凡例の対応が全面的に崩れます。"
                    "装飾目的の画像なら本文から外し、図なら `{#fig:...}` と題を付けてください。")
    if tbl_groups:
        # 題の無い表は番号を持たない (pandoc-crossref は採番しない) ので連番検算から外し、
        # 別立ての警告にする。両方で警告すると同じ 1 件が二重に出る。
        _check_sequence([g["number"] for g in tbl_groups if g["caption"] is not None],
                        "表 (Table)", warnings)
        for g in tbl_groups:
            if g["caption"] is None:
                warnings.append(
                    "題 (キャプション) の無い表があります。この誌は表の題を必須にしているので、"
                    "原稿側で `: 題 {#tbl:x}` を付けてください "
                    + ("(この表は番号なしのプレースホルダを残して末尾へ移します)。" if tables_to_end
                       else "(この表は番号なしのプレースホルダを残して別ファイルへ出します)。"))
            elif g["tbl_caption"] is not None and g["tbl_caption"].strip() != _text(g["caption"]).strip():
                # w:tblPr/w:tblCaption はキャプション本文の複製 (代替テキスト)。題の段落と
                # 一緒に動かすので通常は一致する。食い違うのは後処理の取り違えを示す。
                # ※ **この検査が捕まえるのは pandoc 側の生成のずれと、
                #   生 OOXML ブロックで書いた表だけ**である。移設は題の段落と表を必ず 1 組で
                #   動かすので、移設が原因のずれは構造上起こりえない (実測でも BHI ダミーの表は
                #   前後の空白を除いて完全一致した)。むしろ題に引用や数式が入ると w:t の連結結果と
                #   代替テキストがわずかに食い違って誤検知しうる。表の検査を広げるときは、
                #   対象を「代替テキストの有無」(読み上げ環境での可読性) へ振り替えるほうが実利がある。
                warnings.append(
                    f"表の代替テキスト (w:tblCaption) と題の段落が一致しません: "
                    f"{g['tbl_caption']!r} vs {_text(g['caption'])!r}")

    # --- 移設 (Figure Legends → Tables の順に sectPr の直前へ差し込む) ---
    had_sect_pr = body.find(W("sectPr")) is not None
    _append = _appender(body)

    if fig_groups:
        head = _make_paragraph(etree, str(legends_title), style="Heading1",
                               page_break_before=True)
        _append(head)
        for g in fig_groups:
            for el in [g["caption"]] + g["legends"]:
                body.remove(el)          # 元位置から抜く (ブックマークは残す)
                _append(el)
        out["figures"] = len(fig_groups)
        log(f"  relocate: 図の題+凡例 {len(fig_groups)} 組を '{legends_title}' 節へ集約 "
            f"(凡例段落 {sum(len(g['legends']) for g in fig_groups)} 個を含む)")

    def _detach_table_group(g):
        """表の組の元位置にプレースホルダを差し込み、組を本文から外して返す (end / separate 共通)。

        題 (または表) の元位置にプレースホルダを差し込んでから対象を抜く。
        こうすると pandoc-crossref のブックマーク (題と表を包む) がプレースホルダを
        包む形になり、本文の "Table 1" リンクがプレースホルダへ着地する。
        ブックマークは w:body の直接の子として題・表の外側にあるので (実測)、
        separate で組を別ファイルへ出しても本文側のリンク先は失われない。
        """
        label = (f"[Table {g['number']} about here]" if g["number"] is not None
                 else "[Untitled table about here]")
        anchor = g["caption"] if g["caption"] is not None else g["table"]
        placeholder = _make_paragraph(etree, label, style=STYLE_PLACEHOLDER)
        anchor.addprevious(placeholder)
        moved = ([g["caption"]] if g["caption"] is not None else []) \
            + [g["table"]] + g["legends"]
        for el in moved:
            body.remove(el)
        return moved

    if tbl_groups and tables_separate:
        # separate: 本文から外すだけで末尾へは足さない。改ページも見出しも置かない
        # (本文に残るのはプレースホルダだけ)。書き出しは呼び出し側。
        for g in tbl_groups:
            out["tables_separated"].append(
                {"number": g["number"], "elements": _detach_table_group(g)})
        log(f"  relocate: 表 {len(tbl_groups)} 組を本文から外した (別ファイルへ出す。"
            f"凡例段落 {sum(len(g['legends']) for g in tbl_groups)} 個を含む)")

    if tbl_groups and tables_to_end:
        # **連続する w:tbl の間には必ず段落を挟む**。OOXML では w:tbl が 2 つ続くと Word が
        # 1 つの表として結合してしまい、題の無い表を末尾へ集めたときに前の表の続きに化ける
        # (実装中に実測: 題つきの Table 1 と題の無い .grid 表を末尾へ移すと、LibreOffice の
        #  レンダリングでも 2 表の境目が消えた)。本文中では段落が挟まっているので起きない。
        last_appended = None

        def _append_table_part(el):
            nonlocal last_appended
            if el.tag == W("tbl") and last_appended is not None \
                    and last_appended.tag == W("tbl"):
                spacer = _make_paragraph(etree, "", style=STYLE_PLACEHOLDER)
                _append(spacer)
                last_appended = spacer
            _append(el)
            last_appended = el

        first_of_section = None
        if tables_title:
            head = _make_paragraph(etree, str(tables_title), style="Heading1",
                                   page_break_before=True)
            _append_table_part(head)
            first_of_section = head
        for g in tbl_groups:
            moved = _detach_table_group(g)
            for el in moved:
                _append_table_part(el)
            if first_of_section is None:
                first_of_section = moved[0]
        if last_appended is not None and last_appended.tag == W("tbl"):
            # 本文の最後が表のままだと Word が扱いにくい (Word 自身も表の後に必ず空段落を書く)。
            _append(_make_paragraph(etree, "", style=STYLE_PLACEHOLDER))
        if first_of_section is not None and not tables_title:
            # 見出しを置かない誌では、末尾の表ブロックの先頭に改ページを立てる。
            # 先頭が w:tbl (題の無い表) のときは段落が無いので改ページ専用の空段落を挟む。
            if not _set_page_break_before(etree, first_of_section):
                brk = _make_paragraph(etree, "", style=STYLE_PLACEHOLDER,
                                      page_break_before=True)
                first_of_section.addprevious(brk)
        out["tables"] = len(tbl_groups)
        log(f"  relocate: 表 {len(tbl_groups)} 組を文書末尾へ移設 "
            f"(凡例段落 {sum(len(g['legends']) for g in tbl_groups)} 個を含む)")

    # sectPr が末尾のままであることを確かめる (Word の修復ダイアログ回避)。
    # **元から sectPr が無い docx では検算しない** — 「無かったものが末尾に無い」のは不具合ではなく、
    # ここで停止すると救えない入力で必ず落ちることになる (pandoc は必ず入れるので通常は通らない道)。
    kids = list(body)
    if had_sect_pr and kids and kids[-1].tag != W("sectPr"):
        sys.exit("エラー: 移設後に w:sectPr が w:body の最後の子でなくなりました "
                 "(Word が文書の修復を促す状態)。relocate.py の挿入位置計算の不具合です。")

    return out


# =====================================================================
# 表の体裁 lint (docx 層でしか見えないもの)
# =====================================================================

# 「色が付いていない」とみなす値。w:shd は val=clear + fill=auto が pandoc の既定。
_NEUTRAL_FILLS = {"auto", "ffffff", "none", ""}
_NEUTRAL_COLORS = {"auto", "000000", ""}


def _shading_of(el):
    """w:shd が実際に色を塗っているなら (val, fill) を返す。無彩色なら None。

    `w:fill="auto"` のままテーマ色 (`w:themeFill`) だけを持つ形も色と数える。
    Word の画面から色を付けると通常は `w:fill` にも実際の色が入るが、生 OOXML ブロックで
    書いた表ではテーマ色だけを指定できるので、w:fill だけを見るとこれを無彩色として見逃す。
    """
    val = (el.get(W("val")) or "").strip().lower()
    fill = (el.get(W("fill")) or "").strip().lower()
    theme = (el.get(W("themeFill")) or "").strip().lower()
    if theme:
        return (val or "(なし)", f"themeFill={theme}")
    if val in ("nil", "clear", "") and fill in _NEUTRAL_FILLS:
        return None
    return (val or "(なし)", fill or "(なし)")


def _outermost_tables(body):
    """本文・テキストボックスを問わず、**入れ子でない (最も外側の)** w:tbl だけを返す。

    `body.iter(W("tbl"))` は表の中の表も拾うので、そのすべてを起点にすると
    (1) 外側の表を調べるときに内側の色まで数え、(2) 内側を調べるときにもう一度数えて
    同じ 1 件を二重に報告し、(3)「本文の表 N 個目」の番号も内側の表を 1 つと数えてしまう。
    markdown からは入れ子の表を書けないので、生 OOXML ブロックを使ったときだけ起きる。
    """
    out = []
    for tbl in body.iter(W("tbl")):
        p = tbl.getparent()
        nested = False
        while p is not None:
            if p.tag == W("tbl"):
                nested = True
                break
            p = p.getparent()
        if not nested:
            out.append(tbl)
    return out


# 罫線の色は要素ではなく**属性** (`<w:top w:color="FF0000"/>`) なので、
# `tbl.iter(W("color"))` には掛からない。枠の親要素をたどって拾う。
_BORDER_PARENTS = (W("tblBorders"), W("tcBorders"))


def lint_tables(root, profile, label=None):
    """表の網掛け・文字色・セル色を検出して警告文のリストを返す。

    `tables.allow_color: false` の誌 (BHI) でのみ動く。**数値の桁区切りカンマは扱わない** —
    層の切り分けは「表の体裁は docx 層 (ここ) / 数値表記は Markdown 層 (validate.py)」とする。

    label: 警告文で表の場所を示す名前 (例 "tables/Table1.docx の表")。省略時は従来どおり
           「本文の表 N 個目」(別ファイルへ出した表にも掛けるため)。
    """
    tables_cfg = profile.get("tables") if isinstance(profile.get("tables"), dict) else {}
    if tables_cfg.get("allow_color") is not False:
        return []
    body = root.find(W("body"))
    if body is None:
        return []

    warnings = []
    n_body = 0
    # 入れ子の表を二重に数えないよう、最も外側の表だけを起点にする。
    for tbl in _outermost_tables(body):
        if _in_body_flow(tbl):
            n_body += 1
            where = label if label else f"本文の表 {n_body} 個目"
        else:
            where = "テキストボックス内の表"
        hits = []
        for shd in tbl.iter(W("shd")):
            got = _shading_of(shd)
            if got:
                hits.append(f"網掛け (w:shd val={got[0]} fill={got[1]})")
        for color in tbl.iter(W("color")):
            val = (color.get(W("val")) or "").strip().lower()
            if val not in _NEUTRAL_COLORS:
                hits.append(f"文字色 (w:color val={val})")
        for hl in tbl.iter(W("highlight")):
            val = (hl.get(W("val")) or "").strip().lower()
            if val and val != "none":
                hits.append(f"蛍光ペン (w:highlight val={val})")
        # 罫線の色 (属性なので上の w:color 走査には掛からない)
        for parent_tag in _BORDER_PARENTS:
            for borders in tbl.iter(parent_tag):
                for side in borders:
                    val = (side.get(W("color")) or "").strip().lower()
                    if val and val not in _NEUTRAL_COLORS:
                        hits.append(f"罫線の色 ({_localname(side)} w:color={val})")
        if hits:
            uniq = sorted(set(hits))
            warnings.append(
                f"{where}に色・網掛けがあります ({', '.join(uniq)})。"
                "この誌は表の色・網掛けを禁じています "
                "(強調は上付き・番号・記号・太字で行い、意味は凡例で説明してください)。")
    return warnings
