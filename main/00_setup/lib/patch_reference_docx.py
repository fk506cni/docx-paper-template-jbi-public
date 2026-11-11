#!/usr/bin/env python3
"""patch_reference_docx.py — reference.docx に汎用投稿フォーマットの体裁を焼き込む。

pandoc の既定 reference.docx をベースに、雑誌プロファイルの体裁 (行間・行番号・本文フォント・余白) を
OOXML 直接編集で適用し、差分用の文字スタイル DiffAdd / DiffDel と隠し段落スタイル TextBoxMarker を注入する。
コンテナ内 (docx-paper-template-pandoc; lxml 同梱) で実行する。ホストの Python は使わない。

使い方 (例: _default の reference.docx を作る):
    python3 patch_reference_docx.py base.docx -o reference.docx \
        --line-spacing double --line-numbers continuous \
        --font "Times New Roman" --font-size 12 --margin 25 [--page-numbers]

設計上の位置づけ:
- 体裁 (行間/行番号/フォント/余白/ページ番号) は reference.docx 側に持たせ、main.md 本文は雑誌非依存に
  保つ (docs/architecture.md §3)。
- DiffAdd/DiffDel は _default では事前定義するが、雑誌提供テンプレ (これらを持たない) でも差分色が出るよう、
  step03/step04 の後処理が生成 docx の styles.xml へ同じ 2 スタイルを冪等注入する (docs/architecture.md §2.3)。
  本スクリプトの注入ロジックはその後処理と同じ定義を用いる (単一の真実)。
- 冪等: 同名スタイル / pgMar / lnNumType / フッタは一度削除してから付け直すため、複数回適用しても結果は同じ。
"""

import argparse
import re
import shutil
import sys
import zipfile
from pathlib import Path

from lxml import etree

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
NSMAP = {"w": W}

# OPC パッケージ側の名前空間 (フッタのパート追加に使う)
CT_NS = "http://schemas.openxmlformats.org/package/2006/content-types"
PKGREL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"

XML_NS = "http://www.w3.org/XML/1998/namespace"

FOOTER_PART = "word/footer1.xml"
FOOTER_CT = "application/vnd.openxmlformats-officedocument.wordprocessingml.footer+xml"
FOOTER_REL_TYPE = f"{R_NS}/footer"
# word/footer.xml / footer1.xml / footer2.xml ... を拾う (雑誌提供テンプレは複数持ちうる)。
# これ単独ではフッタを取りこぼす。_footer_part_names() が本正規表現に
# 加えて Override / Relationship 由来の名前も集める (パートの撤去だけを本正規表現で判定し、
# Override と Relationship を種類で判定すると、基準が食い違う)。
FOOTER_PART_RE = re.compile(r"^word/footer\d*\.xml$")

# CT_SectPr の子要素の並び (ECMA-376 Part 1)。先頭に EG_HdrFtrReferences (header/footer は
# 相互にどの順でもよい)、続いて EG_SectPrContents、最後に sectPrChange。
# pgSz/pgMar/lnNumType を sectPr の末尾へ付け足すと、
# ベース docx の sectPr に lnNumType より後ろに来る要素 (titlePg / cols / docGrid / pgNumType 等)
# があるときに順序違反になる (実測: footerReference → footnotePr → titlePg → pgSz → pgMar →
# lnNumType)。pandoc は sectPr の子要素を逐語コピーするため違反は全生成 docx へ波及する。
# 本定数で正しい位置へ挿し込み、最後に _check_sectpr_order で検算する。
SECTPR_ORDER = (
    "headerReference", "footerReference",   # EG_HdrFtrReferences (順不同なので同 rank)
    "footnotePr", "endnotePr", "type", "pgSz", "pgMar", "paperSrc", "pgBorders",
    "lnNumType", "pgNumType", "cols", "formProt", "vAlign", "noEndnote", "titlePg",
    "textDirection", "bidi", "rtlGutter", "docGrid", "printerSettings",
    "sectPrChange",
)
# headerReference / footerReference は同 rank (0)、以降は並び順そのものを rank にする
_SECTPR_RANK = {name: (0 if i < 2 else i) for i, name in enumerate(SECTPR_ORDER)}


def w(tag):
    return f"{{{W}}}{tag}"


# 差分文字スタイルの色 (docs/architecture.md §2.0 / §2.3)。後処理 (step03/04) と同一定義にすること。
DIFF_ADD_COLOR = "2E74B5"  # 青
DIFF_DEL_COLOR = "C00000"  # 赤

# 行間 (w:spacing@w:line, lineRule="auto" の 240ths/line)
LINE_VALUES = {"single": "240", "1.5": "360", "double": "480"}

MM_TO_TWIP = 1440.0 / 25.4  # 1mm → twips

# 用紙寸法 (twips)。A4=210×297mm / Letter=8.5×11in
PAPER_SIZES = {"a4": (11906, 16838), "letter": (12240, 15840)}


def _find_or_create(parent, tag, prepend=False):
    """parent 直下に <w:tag> が無ければ作って返す (冪等)。"""
    el = parent.find(w(tag))
    if el is None:
        el = etree.SubElement(parent, w(tag))
        if prepend:
            parent.remove(el)
            parent.insert(0, el)
    return el


def _localname(el):
    """要素のローカル名を返す (コメント / 処理命令なら None)。"""
    return etree.QName(el.tag).localname if isinstance(el.tag, str) else None


def _sectpr_rank(name):
    """CT_SectPr の子要素名から並び順の rank を返す (未知の要素は末尾扱い)。"""
    return _SECTPR_RANK.get(name, len(SECTPR_ORDER))


def _sectpr_insert(sect, tag):
    """sect 直下へ <w:tag> を CT_SectPr の順序位置に挿し込んで返す。"""
    el = etree.Element(w(tag))
    rank = _sectpr_rank(tag)
    pos = len(sect)
    for i, child in enumerate(sect):
        name = _localname(child)
        if name is not None and _sectpr_rank(name) > rank:
            pos = i
            break
    sect.insert(pos, el)
    return el


def _normalize_sectpr_order(sect):
    """sect の子要素を CT_SectPr の並びへ整列する (同 rank 内の相対順は保つ)。

    ベース docx の sectPr がもとから順序違反のこともある (雑誌提供テンプレ / 手編集)。CT_SectPr の
    子要素の順序は規格で決まっているため、規格順へ並べ替えても意味は変わらない。並べ替えで救える
    ものは救い、_check_sectpr_order は最後の事後条件として残す。戻り値は並べ替えたか否か。
    """
    children = list(sect)
    ranks, last = [], -1
    for child in children:
        name = _localname(child)
        if name is not None:
            last = _sectpr_rank(name)
        ranks.append(last)   # コメント等は直前の要素に付き従わせる
    order = sorted(range(len(children)), key=lambda i: (ranks[i], i))
    if order == list(range(len(children))):
        return False
    for i in order:
        sect.append(children[i])   # append は既存ノードを末尾へ移動する
    return True


def _check_sectpr_order(sect, where):
    """sect の子要素が CT_SectPr の順序に沿っているか検算する。

    順序違反の reference.docx を pandoc に渡すと無警告で通り、出力側も同じ違反になって
    全生成 docx へ波及する。「順序は準拠している」を主張で終わらせず、
    ここで機械的に確かめて違反なら止める。
    """
    names = [n for n in (_localname(c) for c in sect) if n is not None]
    ranks = [_sectpr_rank(n) for n in names]
    if ranks != sorted(ranks):
        raise RuntimeError(
            f"{where} の sectPr の要素順が CT_SectPr に反しています: {names}\n"
            "  (ECMA-376 の並びは EG_HdrFtrReferences → footnotePr → endnotePr → type → "
            "pgSz → pgMar → … → lnNumType → pgNumType → cols → … → titlePg → … → docGrid)"
        )


def patch_styles(styles_root, *, font, font_size_pt, line_spacing, inject_diff):
    """docDefaults に本文フォント・サイズ・行間を設定し、差分/マーカースタイルを注入。"""
    # --- docDefaults (rPrDefault / pPrDefault) ---
    doc_defaults = _find_or_create(styles_root, "docDefaults", prepend=True)

    # rPrDefault → rPr → rFonts / sz / szCs
    rpr_default = _find_or_create(doc_defaults, "rPrDefault")
    rpr = _find_or_create(rpr_default, "rPr")
    rfonts = _find_or_create(rpr, "rFonts")
    for attr in ("ascii", "hAnsi", "cs"):
        rfonts.set(w(attr), font)
    # pandoc 既定 reference.docx の docDefaults rFonts はテーマ参照 (asciiTheme 等) を併せ持つ。
    # OOXML (ECMA-376 §17.3.2.26) ではテーマ属性が直接指定を上書きするため、テーマ参照を残すと
    # 本文が theme フォント (Aptos) で解決され Times が効かない。直接指定だけを残す
    # (theme1.xml 側も patch_theme で Times へ書換)。
    for attr in ("asciiTheme", "hAnsiTheme", "eastAsiaTheme", "cstheme"):
        rfonts.attrib.pop(w(attr), None)
    half = str(int(round(font_size_pt * 2)))  # pt → half-points
    _find_or_create(rpr, "sz").set(w("val"), half)
    _find_or_create(rpr, "szCs").set(w("val"), half)

    # pPrDefault → pPr → spacing (行間)
    ppr_default = _find_or_create(doc_defaults, "pPrDefault")
    ppr = _find_or_create(ppr_default, "pPr")
    spacing = _find_or_create(ppr, "spacing")
    spacing.set(w("line"), LINE_VALUES[line_spacing])
    spacing.set(w("lineRule"), "auto")
    # 段落間の余白は 0 にして「行間=規定値」を素直に見せる
    spacing.set(w("before"), "0")
    spacing.set(w("after"), "0")

    # pandoc の既定の Title スタイルは行間を single (line=240) で上書きしている。題が 2 行以上になると
    # 「全体を同じ行間で」(BHI は "double-spaced throughout") から外れるので、Title の行間も本文の行間に
    # 揃える (段落の前後の余白はそのまま)。pPr が無ければ rPr の前に作る (w:style の子の順序)
    for st in styles_root.findall(w("style")):
        if st.get(w("type")) != "paragraph" or st.get(w("styleId")) != "Title":
            continue
        st_ppr = st.find(w("pPr"))
        if st_ppr is None:
            st_ppr = etree.Element(w("pPr"))
            rpr_el = st.find(w("rPr"))
            if rpr_el is not None:
                rpr_el.addprevious(st_ppr)
            else:
                st.append(st_ppr)
        st_sp = _find_or_create(st_ppr, "spacing")
        st_sp.set(w("line"), LINE_VALUES[line_spacing])
        st_sp.set(w("lineRule"), "auto")

    if inject_diff:
        inject_diff_styles(styles_root)
    inject_textbox_marker_style(styles_root)
    inject_metadata_styles(styles_root)


# ---------------------------------------------------------------------
# 題・見出し・抄録の級数と色 (profile の text_styles。省略時は従来どおり)
#
# pandoc 既定 reference.docx は Title 28pt / Heading 1〜3 = 20/16/14pt (テーマ色 accent1 = 青) /
# Abstract 10pt を持つ。docDefaults を 12pt にしてもこれらは各スタイルの sz で上書きされたまま残る。
# BHI の規定は "12-point type face" なので、級数を本文にそろえる誌はこの段で題・見出し・抄録まで
# そろえる (roundtrip の計測は本文の最頻値しか見ないので、ここが崩れていても数字には出ない)。
# ---------------------------------------------------------------------

# 色を外す対象 (題・見出しの段落スタイルと、対応する文字スタイル)
HEADING_STYLE_IDS = frozenset(
    ("Title", "TitleChar", "Subtitle", "SubtitleChar", "TOCHeading")
    + tuple(f"Heading{i}" for i in range(1, 10))
    + tuple(f"Heading{i}Char" for i in range(1, 10))
)
# 級数をそろえると見出しの階層が級数で見分けられなくなるので、強調で見分ける。
# styleId → (太字, 斜体)。Heading 4 以下は pandoc 既定の斜体 (4/6/8) をそのまま残す。
UNIFORM_EMPHASIS = {
    "Title": (True, False), "TitleChar": (True, False),
    "Heading1": (True, False), "Heading1Char": (True, False),
    "Heading2": (True, True), "Heading2Char": (True, True),
    "Heading3": (False, True), "Heading3Char": (False, True),
}
# CT_RPr (EG_RPrBase) の子要素の並びのうち、強調の挿入位置を決めるのに要る先頭部分
_RPR_HEAD = ("rStyle", "rFonts", "b", "bCs", "i", "iCs")


def _set_rpr_toggle(rpr, tag, on=True):
    """rPr に <w:tag/> (on) / <w:tag w:val="0"/> (off) を順序制約どおりの位置で置く。

    on=True で既にあれば w:val を外してオンにする。on=False は要素が無いときだけ足す
    (継承した強調の打ち消し用。スタイル自身の明示値は尊重する)。
    """
    el = rpr.find(w(tag))
    if el is not None:
        if on:
            el.attrib.pop(w("val"), None)
        return
    el = etree.Element(w(tag))
    if not on:
        el.set(w("val"), "0")
    rank = _RPR_HEAD.index(tag)
    pos = 0
    for i, child in enumerate(rpr):
        name = _localname(child)
        if name in _RPR_HEAD and _RPR_HEAD.index(name) < rank:
            pos = i + 1
    rpr.insert(pos, el)


def normalize_text_styles(styles_root, *, font_size_pt, uniform_size, heading_color):
    """題・見出し・抄録などの級数を本文にそろえ、題・見出しの色を黒にする。

    uniform_size: 級数 (sz / szCs) を明示しているスタイルをすべて本文の級数にする
                  (Title / Subtitle / Author / Date / AbstractTitle / Abstract / Heading 1〜3 と
                  その文字スタイル / VerbatimChar)。あわせて UNIFORM_EMPHASIS で階層を付ける。
    heading_color: "black" なら HEADING_STYLE_IDS の w:color を外す (= 自動色。テーマの青を消す)。
                   "keep" なら触らない。リンク (Hyperlink) と差分 (DiffAdd / DiffDel) の色は対象外。
    戻り値は変更したスタイルの一覧 (表示用)。
    """
    half = str(int(round(font_size_pt * 2)))
    changed = []
    for st in styles_root.findall(w("style")):
        sid = st.get(w("styleId"))
        rpr = st.find(w("rPr"))
        if rpr is None:
            continue
        notes = []
        if uniform_size:
            for tag in ("sz", "szCs"):
                el = rpr.find(w(tag))
                if el is not None and el.get(w("val")) != half:
                    if tag == "sz":
                        notes.append(f"{int(el.get(w('val'))) / 2:g}pt→{font_size_pt:g}pt")
                    el.set(w("val"), half)
            bold, italic = UNIFORM_EMPHASIS.get(sid, (False, False))
            if bold:
                _set_rpr_toggle(rpr, "b")
                _set_rpr_toggle(rpr, "bCs")
                notes.append("太字")
            if italic:
                _set_rpr_toggle(rpr, "i")
                _set_rpr_toggle(rpr, "iCs")
                notes.append("斜体")
        if heading_color == "black" and sid in HEADING_STYLE_IDS:
            color = rpr.find(w("color"))
            if color is not None:
                rpr.remove(color)
                notes.append("色を外す")
        if notes:
            changed.append(f"{sid}({', '.join(notes)})")

    # 強調を付けたスタイルを basedOn にしている他のスタイルは、その強調を継承してしまう
    # (実測: Author / Date / Subtitle は Title を basedOn に持つため、題を太字にすると著者行まで
    #  太字になった)。強調の対象でない子には、継承した太字・斜体を明示的に打ち消す。
    if uniform_size:
        for st in styles_root.findall(w("style")):
            sid = st.get(w("styleId"))
            based = st.find(w("basedOn"))
            parent = based.get(w("val")) if based is not None else None
            if sid in UNIFORM_EMPHASIS or parent not in UNIFORM_EMPHASIS:
                continue
            pbold, pitalic = UNIFORM_EMPHASIS[parent]
            rpr = st.find(w("rPr"))
            if rpr is None:
                rpr = etree.SubElement(st, w("rPr"))
            notes = []
            if pbold and rpr.find(w("b")) is None:
                _set_rpr_toggle(rpr, "b", on=False)
                _set_rpr_toggle(rpr, "bCs", on=False)
                notes.append("継承した太字を打ち消す")
            if pitalic and rpr.find(w("i")) is None:
                _set_rpr_toggle(rpr, "i", on=False)
                _set_rpr_toggle(rpr, "iCs", on=False)
                notes.append("継承した斜体を打ち消す")
            if notes:
                changed.append(f"{sid}({', '.join(notes)})")
    return changed


def uniform_line_spacing(styles_root):
    """段落スタイルが個別に持つ行送り (w:spacing の w:line / w:lineRule) を外す。

    外したスタイルは docDefaults の行送り (BHI はダブル = 480) を継承する。段落前後の空き
    (w:before / w:after) は行送りではないので残す。
    pandoc 既定の reference.docx は `Title` に `w:line="240"` (シングル) を持ち、`Author` /
    `Date` / `Subtitle` はそれを basedOn で継承する。`patch_styles()` は Title の行送りを本文の
    行送りに書き換えるが、この関数は Title に限らず個別の行送りをすべて外す (`TOCHeading` なども
    docDefaults を継ぐ)。BHI の規定 "typed double-spaced throughout" を、スタイルごとの指定に
    頼らずに満たすため。戻り値は変更したスタイルの一覧 (表示用)。
    """
    changed = []
    for st in styles_root.findall(w("style")):
        if st.get(w("type")) != "paragraph":
            continue
        sp = st.find(f"{w('pPr')}/{w('spacing')}")
        if sp is None or sp.get(w("line")) is None:
            continue
        old = sp.get(w("line"))
        for attr in ("line", "lineRule"):
            sp.attrib.pop(w(attr), None)
        if not sp.attrib:
            sp.getparent().remove(sp)
        changed.append(f"{st.get(w('styleId'))}(行送り {old}→継承)")
    return changed


def _remove_styles_by_id(styles_root, style_ids):
    for st in styles_root.findall(w("style")):
        if st.get(w("styleId")) in style_ids:
            styles_root.remove(st)


def inject_diff_styles(styles_root):
    """DiffAdd (青) / DiffDel (赤+取消線) 文字スタイルを冪等注入する。

    step03/step04 の後処理が任意 reference.docx へ注入するのと同じ定義 (docs/architecture.md §2.3)。
    pandoc は custom-style="DiffAdd" を <w:rStyle w:val="...styleId..."/> へ写像し、styleId は w:name で照合する。
    """
    _remove_styles_by_id(styles_root, {"DiffAdd", "DiffDel"})

    add = etree.SubElement(styles_root, w("style"))
    add.set(w("type"), "character")
    add.set(w("customStyle"), "1")
    add.set(w("styleId"), "DiffAdd")
    etree.SubElement(add, w("name")).set(w("val"), "DiffAdd")
    add_rpr = etree.SubElement(add, w("rPr"))
    etree.SubElement(add_rpr, w("color")).set(w("val"), DIFF_ADD_COLOR)

    dele = etree.SubElement(styles_root, w("style"))
    dele.set(w("type"), "character")
    dele.set(w("customStyle"), "1")
    dele.set(w("styleId"), "DiffDel")
    etree.SubElement(dele, w("name")).set(w("val"), "DiffDel")
    del_rpr = etree.SubElement(dele, w("rPr"))
    etree.SubElement(del_rpr, w("color")).set(w("val"), DIFF_DEL_COLOR)
    etree.SubElement(del_rpr, w("strike"))


def inject_textbox_marker_style(styles_root):
    """TextBoxMarker 段落スタイル (隠し) を冪等注入。generic-style.lua の境界マーカー用。"""
    _remove_styles_by_id(styles_root, {"TextBoxMarker"})
    st = etree.SubElement(styles_root, w("style"))
    st.set(w("type"), "paragraph")
    st.set(w("customStyle"), "1")
    st.set(w("styleId"), "TextBoxMarker")
    etree.SubElement(st, w("name")).set(w("val"), "TextBoxMarker")
    rpr = etree.SubElement(st, w("rPr"))
    etree.SubElement(rpr, w("vanish"))


def inject_metadata_styles(styles_root):
    """custom-style Div 用の Affiliation / Keywords / Corresponding / Legend 段落スタイルを冪等注入する。

    pandoc 既定 reference.docx は Title/Author/Abstract を持つが Affiliation/Keywords を持たず、
    定義が無いと pandoc が空スタイルを自動生成する。テンプレ提供物として明示定義しておく。
    _default は投稿フォーマット (素の体裁) のため、体裁は本文同等とし
    (左寄せ・本文フォント/サイズ/行間を Normal から継承)、独自の見た目は与えない。スタイル定義を
    残すのは構造保持差分 (step03 diff) がこれらを温存・差分化するため。

    Corresponding (連絡著者ブロック: 氏名・住所全文・電話・E-mail を 1 名分) は必須にしてある。
    validate.py の連絡著者検査は
    `custom-style="Corresponding"` Div を検出対象にするため、スタイル定義が無いと検査そのものが
    成立しない。誌に依存しない構造要素なので _default にも入れる (体裁は他のメタ Div と同じく素)。

    Legend (図表の凡例ブロック): BHI は図表の【題】(15 語以内) と
    【凡例】(300 語以内) を別物として要求するが、pandoc のキャプションは図にも表にも 1 本しか
    付けられない。そこで「題=キャプション / 凡例=直後の custom-style='Legend' Div」を原稿記法に
    定めた (執筆規約「図表の題と凡例の書き分け」)。docx 側にこの段落スタイルが
    あって初めて、relocate.py の Figure Legends 集約が凡例段落を pStyle で特定でき、validate.py の
    語数検査が題と凡例を別々に数えられる。pandoc の Caption 系 (ImageCaption / TableCaption /
    CaptionedFigure / Caption) とは styleId が衝突しないことを確認済み。
    凡例は誌に依存しない構造要素なので _default にも入れる (体裁は他のメタ Div と同じく素)。
    """
    _remove_styles_by_id(styles_root, {"Affiliation", "Keywords", "Corresponding", "Legend"})
    for style_id in ("Affiliation", "Keywords", "Corresponding", "Legend"):
        st = etree.SubElement(styles_root, w("style"))
        st.set(w("type"), "paragraph")
        st.set(w("customStyle"), "1")
        st.set(w("styleId"), style_id)
        etree.SubElement(st, w("name")).set(w("val"), style_id)
        etree.SubElement(st, w("basedOn")).set(w("val"), "Normal")
        etree.SubElement(st, w("next")).set(w("val"), "BodyText")
        etree.SubElement(st, w("qFormat"))


# ---------------------------------------------------------------------
# ページ番号フッタ (profile の page_numbers: true で有効化)
#
# BHI は "Line and page numbers must be indicated" = 行番号とページ番号の【両方】を要求する
# (docs/journal-bhi.md §2 / G2)。行番号は sectPr の lnNumType で足りるが、ページ番号は
# フッタのパート自体が要る。pandoc 3.6.4 は reference.docx の word/footer1.xml を出力へ
# 引き継ぎ、Override と Relationship を作り直し rId も振り直す (実測)。
# ---------------------------------------------------------------------


def _footer_rpr(parent, font, half_pt):
    """フッタ用の rPr (本文フォントとサイズ) を parent の末尾に足す。

    rFonts → sz → szCs の順は CT_ParaRPr / EG_RPrBase の順序制約に従う。
    本関数は行間を触らない (行間の設定と、なぜ single に上書きするかの説明は
    build_footer_part の w:spacing 側にある)。
    """
    rpr = etree.SubElement(parent, w("rPr"))
    rfonts = etree.SubElement(rpr, w("rFonts"))
    for attr in ("ascii", "hAnsi", "cs"):
        rfonts.set(w(attr), font)
    etree.SubElement(rpr, w("sz")).set(w("val"), half_pt)
    etree.SubElement(rpr, w("szCs")).set(w("val"), half_pt)
    return rpr


def build_footer_part(font, font_size_pt):
    """中央揃えの PAGE フィールドだけを持つ word/footer1.xml を組み立てて bytes で返す。

    要素順は CT_PPrBase 準拠 (suppressLineNumbers → spacing → jc → rPr)。PAGE フィールドは
    begin → instrText → separate → 結果 → end の 5 run で書く (結果 run は Word が再計算する)。

    行間を single に上書きしているのは、フッタ段落も docDefaults を継承するためである。
    上書きしないと本文のダブルスペースがそのまま効いてフッタが 2 行分の高さになる
    (行間は本関数の w:spacing で設定する。_footer_rpr は行間を触らない)。

    段落に w:suppressLineNumbers を入れて行番号の対象から明示的に外す。
    Word の行番号は本文のみが対象とされるが、LibreOffice はフッタ段落にも行番号を振ることが
    実測されている (左余白に 1、中央にページ番号が並ぶ)。「Word では出ないはず」という
    推測に頼らず、本要素で実装によらず抑止する。
    """
    half = str(int(round(font_size_pt * 2)))

    ftr = etree.Element(w("ftr"), nsmap=NSMAP)
    para = etree.SubElement(ftr, w("p"))

    ppr = etree.SubElement(para, w("pPr"))
    etree.SubElement(ppr, w("suppressLineNumbers"))
    spacing = etree.SubElement(ppr, w("spacing"))
    spacing.set(w("before"), "0")
    spacing.set(w("after"), "0")
    spacing.set(w("line"), LINE_VALUES["single"])
    spacing.set(w("lineRule"), "auto")
    etree.SubElement(ppr, w("jc")).set(w("val"), "center")
    _footer_rpr(ppr, font, half)

    def run():
        r = etree.SubElement(para, w("r"))
        _footer_rpr(r, font, half)
        return r

    etree.SubElement(run(), w("fldChar")).set(w("fldCharType"), "begin")
    instr = etree.SubElement(run(), w("instrText"))
    instr.set(f"{{{XML_NS}}}space", "preserve")
    instr.text = " PAGE "
    etree.SubElement(run(), w("fldChar")).set(w("fldCharType"), "separate")
    etree.SubElement(run(), w("t")).text = "1"
    etree.SubElement(run(), w("fldChar")).set(w("fldCharType"), "end")

    return etree.tostring(ftr, xml_declaration=True, encoding="UTF-8", standalone=True)


def _footer_part_names(parts, ct_root, rels_root):
    """既存フッタのパート名を 3 系統 (Override / Relationship / 名前) から集める。

    パートの撤去だけを名前の正規表現 FOOTER_PART_RE で判定し、
    Override と Relationship を種類 (ContentType / Type) で判定すると、判定基準が食い違う。
    word/footerFirst.xml のように命名規則から外れたフッタでは、パートが残るのに Override と
    Relationship だけが消え、種類宣言と実体が合わない孤立パートになる (実測。
    警告にも出ない)。3 系統の和集合を撤去対象にして基準を揃える。
    """
    names = set()
    for override in ct_root.findall(f"{{{CT_NS}}}Override"):
        if override.get("ContentType") == FOOTER_CT:
            names.add((override.get("PartName") or "").lstrip("/"))
    for rel in rels_root.findall(f"{{{PKGREL_NS}}}Relationship"):
        if rel.get("Type") == FOOTER_REL_TYPE:
            target = (rel.get("Target") or "").lstrip("/")
            if target:
                names.add(target if target.startswith("word/") else f"word/{target}")
    names |= {n for n in parts if FOOTER_PART_RE.match(n)}
    return {n for n in names if n}


def install_page_number_footer(parts, parser, *, font, font_size_pt):
    """word/footer1.xml + Content_Types Override + Relationship を冪等に追加し rId を返す。

    冪等性は本スクリプトの既存 idiom (「一旦削除してから付け直す」) に揃える。既存のフッタ
    パート・Override・Relationship をすべて撤去してから 1 枚だけ入れ直すため、複数回適用しても
    結果は同じになる。雑誌提供テンプレが独自のフッタを持っていた場合は置き換わるので警告する
    (--page-numbers はオプトインであり、テンプレのフッタを活かすなら渡さない運用になる)。

    警告は「撤去したフッタが本スクリプトの生成物と違う」ときだけ出す。
    撤去したフッタが自分で入れた word/footer1.xml でも同じ警告を出すと、冪等性を
    確認する再適用で毎回「既存のフッタを置き換えます」が出る。重大な場面 (テンプレの
    フッタを壊した) の警告が無害な場面と同じ文面になると読み飛ばされる。
    """
    ct_root = etree.fromstring(parts["[Content_Types].xml"], parser)
    rels_name = "word/_rels/document.xml.rels"
    if rels_name not in parts:
        raise RuntimeError(f"{rels_name} が無いためフッタを関連付けできません (壊れた docx?)")
    rels_root = etree.fromstring(parts[rels_name], parser)

    new_footer = build_footer_part(font, font_size_pt)
    removed = sorted(_footer_part_names(parts, ct_root, rels_root))
    # 本スクリプトが前回入れたものと内容が違うフッタ = テンプレ由来。これだけを警告する
    foreign = [n for n in removed if n in parts and parts[n] != new_footer]
    for name in removed:
        parts.pop(name, None)
        parts.pop(f"word/_rels/{Path(name).name}.rels", None)
    if foreign:
        print(f"  警告: テンプレ由来のフッタを置き換えます: {', '.join(foreign)}")

    # --- [Content_Types].xml の Override ---
    for override in ct_root.findall(f"{{{CT_NS}}}Override"):
        if override.get("ContentType") == FOOTER_CT:
            ct_root.remove(override)
    override = etree.SubElement(ct_root, f"{{{CT_NS}}}Override")
    override.set("PartName", f"/{FOOTER_PART}")
    override.set("ContentType", FOOTER_CT)
    parts["[Content_Types].xml"] = etree.tostring(
        ct_root, xml_declaration=True, encoding="UTF-8", standalone=True
    )

    # --- word/_rels/document.xml.rels の Relationship (未使用の rId を採る) ---
    used = set()
    for rel in rels_root.findall(f"{{{PKGREL_NS}}}Relationship"):
        if rel.get("Type") == FOOTER_REL_TYPE:
            rels_root.remove(rel)
        else:
            used.add(rel.get("Id") or "")
    nums = [int(m.group(1)) for m in (re.fullmatch(r"rId(\d+)", i) for i in used) if m]
    rid = f"rId{max(nums, default=0) + 1}"
    rel = etree.SubElement(rels_root, f"{{{PKGREL_NS}}}Relationship")
    rel.set("Id", rid)
    rel.set("Type", FOOTER_REL_TYPE)
    rel.set("Target", Path(FOOTER_PART).name)
    parts[rels_name] = etree.tostring(
        rels_root, xml_declaration=True, encoding="UTF-8", standalone=True
    )

    # --- パート本体 ---
    parts[FOOTER_PART] = new_footer
    return rid


# drawingml (テーマ) 名前空間
A_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"


def _a(tag):
    return f"{{{A_NS}}}{tag}"


def patch_theme(theme_root, font):
    """テーマの major/minor フォント (latin) を指定フォントへ書き換える (冪等)。

    pandoc 既定テーマは latin=Aptos / Aptos Display。Title・Heading 系スタイルは
    asciiTheme="majorHAnsi" 等のテーマ参照のみを持つため、テーマ側を直さないと Times にならない
    本文 docDefaults はテーマ参照を除去済みだが、テーマも揃えて二重に担保する。
    """
    fs = theme_root.find(f".//{_a('fontScheme')}")
    if fs is None:
        return False
    changed = False
    for slot in ("majorFont", "minorFont"):
        fnt = fs.find(_a(slot))
        if fnt is None:
            continue
        latin = fnt.find(_a("latin"))
        if latin is not None:
            latin.set("typeface", font)
            latin.attrib.pop("panose", None)   # Aptos の panose は Times と不一致なので除去
            changed = True
    return changed


def patch_document(document_root, *, margin_mm, line_numbers, paper, footer_rid=None):
    """本文 sectPr に用紙寸法 (pgSz)・余白 (pgMar)・行番号 (lnNumType) を設定する (冪等)。

    要素順は CT_SectPr 準拠で footerReference → footnotePr → pgSz → pgMar → lnNumType になるよう、
    既存の pgSz/pgMar/lnNumType を一旦除去してから SECTPR_ORDER の位置へ挿し直す
    最後に _check_sectpr_order で順序を検算する。

    footer_rid が与えられたとき (--page-numbers) だけ footerReference を貼り直す。pandoc は
    sectPr の子要素を逐語コピーするため、順序違反の reference.docx を渡すと出力側も同じ順序違反に
    なり全生成 docx へ波及する。footerReference は CT_SectPr の EG_HdrFtrReferences に属し
    footnotePr より前なので sectPr の先頭へ入れる。
    footer_rid が None のときは既存 footerReference に触らない (雑誌提供テンプレのフッタを壊さない)。

    footerReference は**文書内のすべての sectPr** から撤去する。
    docx では最後の節以外の設定が段落内の sectPr (`w:p/w:pPr/w:sectPr`) に入るため、表紙と本文で
    フッタを分けているテンプレはこの形になる。body 直下の sectPr しか掃除しないと、
    install_page_number_footer がフッタの関係定義を全撤去した後に段落内 sectPr の footerReference
    だけが残り、**消えた rId を指す壊れた docx** ができる (実測。適用前は開けたのに
    適用後は LibreOffice が読み込みを拒否した)。入出力を同じパスにすると .tmp 退避も消えるため
    テンプレ本体を失う経路でもある。
    """
    body = document_root.find(w("body"))
    if body is None:
        raise RuntimeError("word/document.xml に <w:body> が無い")
    sect = body.find(w("sectPr"))
    if sect is None:
        sect = etree.SubElement(body, w("sectPr"))

    # 段落内 sectPr (= 最後の節より前の節) の一覧。体裁の焼き込みは本文 sectPr にしか効かない
    inner_sects = [s for s in document_root.iter(w("sectPr")) if s is not sect]

    # ベースがもとから順序違反のこともあるので、まず規格順へ整列する
    for target in [sect] + inner_sects:
        if _normalize_sectpr_order(target):
            print("  注: sectPr の要素順を CT_SectPr の並びへ整列しました")

    for tag in ("pgSz", "pgMar", "lnNumType"):
        for old in sect.findall(w(tag)):
            sect.remove(old)

    # --- フッタ参照 (footerReference) --- default 以外 (first/even) も、段落内 sectPr の分も撤去する
    # (install_page_number_footer がフッタのパートと関係定義を 1 枚に置き換えているため、参照だけ
    #  残ると存在しない rId を指す)
    if footer_rid is not None:
        for target in [sect] + inner_sects:
            for old in target.findall(w("footerReference")):
                target.remove(old)
        ref = _sectpr_insert(sect, "footerReference")
        ref.set(w("type"), "default")
        ref.set(f"{{{R_NS}}}id", footer_rid)
        if inner_sects:
            print(f"  警告: 段落内 sectPr が {len(inner_sects)} 個あります。"
                  "体裁 (用紙/余白/行番号) の焼き込みは最後の節にしか効きません")

    # --- 用紙寸法 (pgSz) --- A4/Letter を明示し環境依存 (用紙未指定) を排除
    pw, ph = PAPER_SIZES[paper]
    pgsz = _sectpr_insert(sect, "pgSz")
    pgsz.set(w("w"), str(pw))
    pgsz.set(w("h"), str(ph))

    # --- 余白 (pgMar) ---
    twip = int(round(margin_mm * MM_TO_TWIP))
    # ヘッダ/フッタの用紙端からの距離。708 twips (約 12.5mm) 固定にすると、余白が 12.5mm を
    # 下回る誌ではページ番号が本文領域に食い込む
    # (実測: --margin 10 で w:bottom=567 < w:footer=708)。本文余白の半分で上限を掛けて必ず内側に収める
    # (--margin 25 では 1417//2 = 708 で、上限の 708 と同じ値になる)。
    hf = min(708, max(0, twip // 2))
    if hf != 708:
        print(f"  注: 余白 {margin_mm}mm に合わせてヘッダ/フッタ余白を {hf} twips へ縮めました")
    pgmar = _sectpr_insert(sect, "pgMar")
    for side in ("top", "right", "bottom", "left"):
        pgmar.set(w(side), str(twip))
    pgmar.set(w("header"), str(hf))
    pgmar.set(w("footer"), str(hf))
    pgmar.set(w("gutter"), "0")

    # --- 行番号 (lnNumType) ---
    #
    # w:start は **"0"** にする (Word 実機で確かめた)。
    # Word はこの属性を「1 行目に振る番号」ではなく「**最初の行の 1 つ前の番号**」として扱う。
    # w:start="1" では原稿の 1 行目 (タイトル行) に番号が付かず、行番号が 2 から始まる
    # (規定 "Line and page numbers must be indicated." は満たすが、査読者が line 1 を指せない)。
    #
    # **机上では決められない挙動なので実機で比べた** (roundtrip = Windows の Word COM 変換)。
    # 同一原稿 data/dummy/bhi/main.md を 2 通りの reference.docx でビルドし、Windows の
    # Word COM が返した PDF の左余白の数字を読んだ:
    #     w:start="1" → 2〜164 (163 個・欠番なし)
    #     w:start="0" → 1〜163 (163 個・欠番なし)
    # 番号の個数は同じで開始値だけが 1 ずれる = **"0 から始まる" のではなく "1 行目が 1 になる"**。
    # 雑誌プロファイルの reference.docx は `bash data/journals/make-reference.sh <id>` で
    # 作り直せば、この値で焼き込まれる。
    if line_numbers != "none":
        ln = _sectpr_insert(sect, "lnNumType")
        ln.set(w("countBy"), "1")
        ln.set(w("start"), "0")
        ln.set(w("restart"), "continuous" if line_numbers == "continuous" else "newPage")

    _check_sectpr_order(sect, "word/document.xml (本文)")


def read_layout(docx_path):
    """reference.docx に【実際に焼き込まれている】体裁を profile.yaml と同じキーで読み出す。

    体裁は profile.yaml (意図) と reference.docx (実体) の二重管理になる。
    ずれても誰も気づけないため、実体側を読み出して突き合わせられるようにする。読み出しを
    書き込みと同じモジュールに置くのは、焼き込む値と読み出す値の定義 (LINE_VALUES / PAPER_SIZES /
    MM_TO_TWIP / FOOTER_PART_RE) を 1 箇所に保つためである。

    返す dict のキーは profile.yaml と同名 (line_spacing / line_numbers / page_numbers / font /
    font_size / margins / paper_size)。読み取れなかったキーは None にする (欠落と不一致を
    呼び出し側が区別できるようにする)。
    """
    layout = dict.fromkeys(
        ("line_spacing", "line_numbers", "page_numbers", "font", "font_size",
         "margins", "paper_size"))
    with zipfile.ZipFile(docx_path, "r") as zin:
        names = set(zin.namelist())
        styles = etree.fromstring(zin.read("word/styles.xml")) if "word/styles.xml" in names else None
        doc = etree.fromstring(zin.read("word/document.xml")) if "word/document.xml" in names else None
        ct = zin.read("[Content_Types].xml").decode("utf-8", "ignore") if "[Content_Types].xml" in names else ""

    # --- フッタ (ページ番号) --- パートの実在と Override の両方を見る
    layout["page_numbers"] = bool(
        any(FOOTER_PART_RE.match(n) for n in names) or FOOTER_CT in ct)

    if styles is not None:
        defaults = styles.find(w("docDefaults"))
        if defaults is not None:
            ppr = defaults.find(f"{w('pPrDefault')}/{w('pPr')}")
            spacing = ppr.find(w("spacing")) if ppr is not None else None
            if spacing is not None:
                line = spacing.get(w("line"))
                rev = {v: k for k, v in LINE_VALUES.items()}
                layout["line_spacing"] = rev.get(line, line)
            rpr = defaults.find(f"{w('rPrDefault')}/{w('rPr')}")
            if rpr is not None:
                rfonts = rpr.find(w("rFonts"))
                if rfonts is not None:
                    layout["font"] = rfonts.get(w("ascii"))
                sz = rpr.find(w("sz"))
                if sz is not None and (sz.get(w("val")) or "").isdigit():
                    layout["font_size"] = int(sz.get(w("val"))) / 2.0  # half-point → pt

    if doc is not None:
        body = doc.find(w("body"))
        sect = body.find(w("sectPr")) if body is not None else None
        if sect is not None:
            pgsz = sect.find(w("pgSz"))
            if pgsz is not None:
                dims = (pgsz.get(w("w")), pgsz.get(w("h")))
                for name, (pw, ph) in PAPER_SIZES.items():
                    if dims == (str(pw), str(ph)):
                        layout["paper_size"] = name
                        break
            pgmar = sect.find(w("pgMar"))
            if pgmar is not None and (pgmar.get(w("top")) or "").isdigit():
                layout["margins"] = int(pgmar.get(w("top"))) / MM_TO_TWIP
            ln = sect.find(w("lnNumType"))
            layout["line_numbers"] = (
                "none" if ln is None
                else ("continuous" if ln.get(w("restart")) == "continuous" else "per-page"))
    return layout


def check_relationships(document_root, rels_bytes):
    """document.xml が参照する rId が document.xml.rels に実在するか検算する。

    宙に浮いた参照 (関係定義が無い rId) を含む docx は Word / LibreOffice のいずれも開けない。
    壊れたファイルを黙って書き出さないための最後の関門として、書き出し前に必ず通す。
    """
    rels_root = etree.fromstring(rels_bytes)
    defined = {r.get("Id") for r in rels_root.findall(f"{{{PKGREL_NS}}}Relationship")}
    missing = set()
    for el in document_root.iter():
        if not isinstance(el.tag, str):
            continue
        for name, value in el.attrib.items():
            if name.startswith(f"{{{R_NS}}}") and value and value not in defined:
                missing.add((_localname(el), value))
    if missing:
        detail = ", ".join(f"{tag}→{rid}" for tag, rid in sorted(missing))
        raise RuntimeError(
            "word/document.xml が関係定義に存在しない rId を参照しています "
            f"(壊れた docx になるため中止): {detail}")


def process(in_path, out_path, args):
    in_path = Path(in_path)
    out_path = Path(out_path)
    if in_path.resolve() == out_path.resolve():
        # 同一パスはまず一時退避してから書き戻す
        tmp = in_path.with_suffix(in_path.suffix + ".tmp")
        shutil.copy2(in_path, tmp)
        in_path = tmp

    with zipfile.ZipFile(in_path, "r") as zin:
        parts = {item.filename: zin.read(item.filename) for item in zin.infolist()}

    parser = etree.XMLParser(remove_blank_text=False)

    styles_root = etree.fromstring(parts["word/styles.xml"], parser)
    patch_styles(
        styles_root,
        font=args.font,
        font_size_pt=args.font_size,
        line_spacing=args.line_spacing,
        inject_diff=not args.no_diff_styles,
    )
    # 題・見出し・抄録の級数と色。どちらの引数も無ければ何もしない (既存誌の出力は不変)
    text_style_changes = []
    if args.uniform_style_size or args.heading_color != "keep":
        text_style_changes = normalize_text_styles(
            styles_root,
            font_size_pt=args.font_size,
            uniform_size=args.uniform_style_size,
            heading_color=args.heading_color,
        )
    # 行送りの個別指定を外す。引数が無ければ何もしない (既存誌の出力は不変)
    if args.uniform_line_spacing:
        text_style_changes += uniform_line_spacing(styles_root)
    parts["word/styles.xml"] = etree.tostring(
        styles_root, xml_declaration=True, encoding="UTF-8", standalone=True
    )

    # ページ番号フッタ。sectPr の footerReference が指す rId を先に確定させる
    footer_rid = None
    if args.page_numbers:
        footer_rid = install_page_number_footer(
            parts, parser, font=args.font, font_size_pt=args.font_size
        )

    doc_root = etree.fromstring(parts["word/document.xml"], parser)
    patch_document(doc_root, margin_mm=args.margin, line_numbers=args.line_numbers,
                   paper=args.paper, footer_rid=footer_rid)
    parts["word/document.xml"] = etree.tostring(
        doc_root, xml_declaration=True, encoding="UTF-8", standalone=True
    )

    # 宙に浮いた rId が無いことを書き出し前に検算する
    check_relationships(doc_root, parts["word/_rels/document.xml.rels"])

    # テーマフォント (Aptos) を本文フォントへ書き換える
    theme_name = "word/theme/theme1.xml"
    if theme_name in parts:
        theme_root = etree.fromstring(parts[theme_name], parser)
        patch_theme(theme_root, args.font)
        parts[theme_name] = etree.tostring(
            theme_root, xml_declaration=True, encoding="UTF-8", standalone=True
        )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as zout:
        for name, data in parts.items():
            # パート名だけを渡すと zipfile が格納時刻に「その時の時刻」を
            # 入れるため、パートの内容がまったく同じでも生成のたびにバイト列が変わっていた
            # (実測: 同じ引数で作り直した _default/reference.docx は長さまで同じ 11,160 バイトなのに
            #  バイト一致しない)。生成物を git 管理する方針なので、これでは「意味のある変更」と
            #  「作り直しただけ」を後から読む人が区別できない。時刻を固定して再現可能にする
            #  (ZIP の最小値である 1980-01-01。scripts/compare-snapshots.py が言うとおり
            #   pandoc 出力の docx は依然バイト比較できないが、本スクリプトの生成物は比較できる)。
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o600 << 16
            zout.writestr(info, data)

    if str(in_path).endswith(".tmp"):
        in_path.unlink(missing_ok=True)

    print(f"wrote {out_path}")
    print(
        f"  font={args.font} {args.font_size}pt  spacing={args.line_spacing}  "
        f"line-numbers={args.line_numbers}  page-numbers={'yes' if args.page_numbers else 'no'}  "
        f"margin={args.margin}mm  paper={args.paper}  "
        f"diff-styles={'no' if args.no_diff_styles else 'yes'}"
    )
    if text_style_changes:
        print(f"  text-styles: uniform-size={'yes' if args.uniform_style_size else 'no'}  "
              f"heading-color={args.heading_color}  "
              f"uniform-line-spacing={'yes' if args.uniform_line_spacing else 'no'}")
        print("    " + " / ".join(text_style_changes))


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("input", help="ベース reference.docx (pandoc 既定など)")
    p.add_argument("-o", "--output", required=True, help="出力 reference.docx")
    p.add_argument("--line-spacing", choices=["single", "1.5", "double"], default="double")
    p.add_argument("--line-numbers", choices=["none", "continuous", "per-page"], default="continuous")
    p.add_argument("--page-numbers", action="store_true",
                   help="フッタに中央揃えの PAGE フィールドを入れる (既定 off。profile の page_numbers)")
    p.add_argument("--font", default="Times New Roman", help="本文フォント (既定: Times New Roman)")
    p.add_argument("--font-size", type=float, default=12.0, help="本文フォントサイズ pt (既定: 12)")
    p.add_argument("--margin", type=float, default=25.0, help="四辺余白 mm (既定: 25)")
    p.add_argument("--paper", choices=["a4", "letter"], default="a4", help="用紙寸法 (既定: a4)")
    p.add_argument("--no-diff-styles", action="store_true", help="DiffAdd/DiffDel を注入しない")
    p.add_argument("--uniform-style-size", action="store_true",
                   help="題・見出し・抄録など級数を持つスタイルをすべて本文の級数にそろえ、見出しの階層を "
                        "太字/斜体で付ける (既定 off。profile の text_styles.uniform_size)")
    p.add_argument("--heading-color", choices=["keep", "black"], default="keep",
                   help="題・見出しの色。black でテーマ色 (青) を外す (既定 keep。profile の "
                        "text_styles.heading_color)")
    p.add_argument("--uniform-line-spacing", action="store_true",
                   help="段落スタイルが個別に持つ行送りを外し、文書全体の行送り (--line-spacing) に "
                        "そろえる (既定 off。profile の text_styles.uniform_line_spacing。題の Title は "
                        "pandoc 既定でシングル)")
    args = p.parse_args(argv)
    process(args.input, args.output, args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
