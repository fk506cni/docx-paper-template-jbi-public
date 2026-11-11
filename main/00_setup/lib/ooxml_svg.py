#!/usr/bin/env python3
"""ooxml_svg.py — OOXML の「SVG ネイティブ埋込」のうち **docx / pptx で共通の部分**。

docs/architecture.md §2.2 / §2.5。`docs/journal-bhi.md` §5.1。

【なぜ切り出すか】Office の SVG 拡張は **docx と pptx で同一機構**である。実体を
`<package>/media/` に入れ、画像を指す `a:blip` の下に

    a:blip @r:embed="<PNG フォールバックの rId>"
     └ a:extLst
        └ a:ext uri="{96DAC541-7B7A-43D3-8B79-37D633B846F1}"   ← Office の SVG 拡張 (固定値)
           └ asvg:svgBlip @r:embed="<SVG 本体の rId>"

を注入し、`[Content_Types].xml` に `Extension="svg"` の Default を足す。この 3 点だけが共通で、
残り (どの要素を走査するか / どの rels ファイルを触るか / media の置き場所) は文書種別ごとに違う。
docx と pptx の両方で使うので、共通部を 2 箇所に書くと**一方だけ直す事故**が起きる
(要素名を 1 つ誤っても、実装が 1 箇所なら 1 箇所直せば済む)。共通部はここにだけ置く。

【要素名の出典】`asvg:svgBlip` は Microsoft の DrawingML 2016 SVG 拡張の要素名で、名前空間 URI は
`http://schemas.microsoft.com/office/drawing/2016/SVG/main`。拡張識別子
`{96DAC541-7B7A-43D3-8B79-37D633B846F1}` は Office が SVG 拡張を引き当てる固定 GUID である。
実物との突合手順は `docs/journal-bhi.md` §5.3 に記録した (自分が書いた綴りを自分で検索する形の
検査にしない)。

【使う側】
  - `main/step02_build/postprocess.py` : pandoc 生成 docx への後注入
  - `main/00_setup/lib/svg_pptx.py`    : 1 図 = 1 pptx の生成
"""

from lxml import etree

# --- 名前空間 (docx / pptx で共通のものだけ) ---
A_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
ASVG_NS = "http://schemas.microsoft.com/office/drawing/2016/SVG/main"
CT_NS = "http://schemas.openxmlformats.org/package/2006/content-types"
RELS_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
REL_IMAGE = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/image"

# Office の SVG 拡張 ext uri (固定値)。docx / pptx / xlsx で同じ。
SVG_EXT_URI = "{96DAC541-7B7A-43D3-8B79-37D633B846F1}"

SVG_CONTENT_TYPE = "image/svg+xml"
PNG_CONTENT_TYPE = "image/png"


def A(tag):
    return f"{{{A_NS}}}{tag}"


def R(tag):
    return f"{{{R_NS}}}{tag}"


def ASVG(tag):
    return f"{{{ASVG_NS}}}{tag}"


def inject_svg_ext(blip, svg_rid):
    """`a:blip` の下に SVG 拡張 (asvg:svgBlip) を注入する。

    引数:
      blip    : `a:blip` 要素 (PNG フォールバックを `r:embed` で指している状態)
      svg_rid : SVG 実体を指す関係 ID (同じパートの rels に登録済みであること)

    返り値: 追加した `asvg:svgBlip` 要素。

    既に同じ uri の `a:ext` があれば作り直さず中身を差し替える (冪等)。docx を二度後処理しても
    ext が積み上がらないようにするため。
    """
    ext_lst = blip.find(A("extLst"))
    if ext_lst is None:
        ext_lst = etree.SubElement(blip, A("extLst"))
    ext = None
    for cand in ext_lst.findall(A("ext")):
        if cand.get("uri") == SVG_EXT_URI:
            ext = cand
            break
    if ext is None:
        ext = etree.SubElement(ext_lst, A("ext"))
        ext.set("uri", SVG_EXT_URI)
    else:
        for child in list(ext):
            ext.remove(child)
    svg_blip = etree.SubElement(ext, ASVG("svgBlip"))
    svg_blip.set(R("embed"), svg_rid)
    return svg_blip


def ensure_default_content_type(ct_root, extension, content_type):
    """`[Content_Types].xml` に `<Default Extension=... ContentType=...>` を足す (既にあれば何もしない)。

    返り値: 追加したら True。
    """
    for d in ct_root.findall(f"{{{CT_NS}}}Default"):
        if d.get("Extension") == extension:
            return False
    d = etree.SubElement(ct_root, f"{{{CT_NS}}}Default")
    d.set("Extension", extension)
    d.set("ContentType", content_type)
    return True


def ensure_svg_content_type(ct_root):
    """`[Content_Types].xml` に svg の Default を足す (docx / pptx 共通)。"""
    return ensure_default_content_type(ct_root, "svg", SVG_CONTENT_TYPE)


def next_rid(rels_root, prefix="rId"):
    """rels の既存 Id を見て、衝突しない次の関係 ID を返す。"""
    max_n = 0
    for rel in rels_root:
        rid = rel.get("Id", "")
        if rid.startswith(prefix):
            try:
                max_n = max(max_n, int(rid[len(prefix):]))
            except ValueError:
                pass
    return f"{prefix}{max_n + 1}"


def add_image_rel(rels_root, target, rid=None):
    """rels に image 型の関係を足して rId を返す (`Target` は rels からの相対パス)。"""
    rid = rid or next_rid(rels_root)
    rel = etree.SubElement(rels_root, f"{{{RELS_NS}}}Relationship")
    rel.set("Id", rid)
    rel.set("Type", REL_IMAGE)
    rel.set("Target", target)
    return rid
