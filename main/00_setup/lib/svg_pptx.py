#!/usr/bin/env python3
"""svg_pptx.py — 1 図 = 1 pptx = 1 スライドの生成器 (案 B = svg-blob)。

docs/architecture.md §2.5、docs/profile-schema.md。`docs/journal-bhi.md` §5.1 / §5.3。

【なぜ要るか】BioHealth Informatics の図の受入形式は JPEG / TIF / PNG / PowerPoint の 4 つで、
**ベクターを保持できるのは PowerPoint だけ**である (受け付ける形式は JPEG / TIF / PNG / PowerPoint で、SVG / PDF / EPS は挙がっていない)。
本テンプレの図は SVG が正本なので、ベクター情報を届ける経路は pptx しかない。

【方式】OOXML の SVG ネイティブ埋込は docx と pptx で同一機構である (共通部は `ooxml_svg`)。
スライドに `p:pic` を 1 つ置き、`a:blip` が PNG フォールバックを、その下の `asvg:svgBlip` が
SVG 本体を指す。SVG 対応環境ではベクターが、非対応環境では PNG が描画される。

【骨格 pptx の入手】`pandoc --print-default-data-file reference.pptx`
を取り出して加工する (**追加依存ゼロ**)。`data/journals/make-reference.sh` が reference.docx で
使っているのと同じ流儀。python-pptx の導入 (現コンテナに無い) も、最小 pptx のリポジトリ同梱も
採らない。選定理由は `docs/journal-bhi.md` §5.3。骨格は 4 スライド + ノートを持つので、

  - `ppt/slides/slide2..4` / `ppt/notesSlides/*` / `ppt/notesMasters/*` / `ppt/theme/theme2.xml` を削除
  - `ppt/slides/slide1.xml` を「図 1 枚だけのスライド」に差し替え (レイアウトは Blank = slideLayout7)
  - `ppt/presentation.xml` の `p:sldIdLst` / `p:notesMasterIdLst` / `p:sldSz` を作り直す
  - `docProps/core.xml` / `docProps/app.xml` を中立な内容に書き直す
    (骨格には pandoc 開発者の氏名と作成日時が入っている。**投稿物にそのまま載せない**)

としたうえで、`ppt/media/` に SVG と PNG を入れる。slideMaster / slideLayout / theme1 は
そのまま使う (自前で書くと PowerPoint の互換性検証を丸ごと引き受けることになるため)。

【スライド寸法】ECMA-376 の `ST_SlideSizeCoordinate` は **914400〜51206400 EMU (1〜56 インチ)**
に制限されている。単位を持たない小さな SVG (72×72 px = 0.75 インチ) はそのままだと下限を割り、
**規格違反の pptx** になって PowerPoint が修復を促す。本モジュールは範囲外を検出したら
**エラーで停止**し、`slide_fit: fixed` (骨格の既定サイズに中央配置) への退避を案内する。

【余白について (誤解しやすい)】`slide_fit: figure` が保証するのは「**スライド側**に余分な余白を
作らない」ことだけである。BHI の "closely cropped to minimize white space" は**図の描画内容の
周囲の白を削れ**という要求で、SVG の viewBox が描画内容より広ければ白余白はそのままスライドに
載る。**余白のトリミングは執筆規約 (人手) の担当**である。

【書庫の再現性】zip の各項目に**固定時刻 (1980-01-01)** を与え、書き出し順も固定する。
docs/architecture.md §4 の「再実行しても md5 が完全一致」を pptx でも満たすため。
"""

import contextlib
import io
import subprocess
import tempfile
import zipfile
from pathlib import Path

from lxml import etree

import ooxml_svg
import svg_raster

# --- 単位 ---
EMU_PER_INCH = 914400
# ECMA-376 Part 1, ST_SlideSizeCoordinate: 914400 (1in) 〜 51206400 (56in)
SLIDE_MIN_EMU = 914400
SLIDE_MAX_EMU = 51206400

# 骨格から使うレイアウト (11 種のうち "Blank" = プレースホルダのないもの)。
# 図だけを載せるので、タイトル枠のあるレイアウトを使うと空の枠が PowerPoint 上に見える。
BLANK_LAYOUT = "ppt/slideLayouts/slideLayout7.xml"

# 骨格から落とすパート (4 スライド構成 + ノート由来のもの)
_DROP_PREFIXES = (
    "ppt/slides/slide2.xml", "ppt/slides/slide3.xml", "ppt/slides/slide4.xml",
    "ppt/slides/_rels/slide2.xml.rels", "ppt/slides/_rels/slide3.xml.rels",
    "ppt/slides/_rels/slide4.xml.rels",
    "ppt/notesSlides/", "ppt/notesMasters/",
    "ppt/theme/theme2.xml",          # notesMaster 専用テーマ
    "docProps/",                     # 中立な内容で書き直す (骨格の氏名・日時を持ち込まない)
)

# 書庫の項目に与える固定時刻 (zip の下限。docs/architecture.md §4 の冪等性を pptx でも満たすため)
FIXED_ZIP_TIME = (1980, 1, 1, 0, 0, 0)

# 骨格に必ず在ることを前提にしているパート。
# 前提を「そうなっているはず」で通さず、ここに挙げたものはすべて確かめる。
# pandoc の版を上げて構成が変わったときに**黙って壊れる**のではなく**止まる**ようにする。
_REQUIRED_SKELETON_PARTS = (
    "[Content_Types].xml",
    "_rels/.rels",
    "ppt/presentation.xml",
    "ppt/_rels/presentation.xml.rels",
    "ppt/slides/slide1.xml",
    "ppt/slides/_rels/slide1.xml.rels",
    BLANK_LAYOUT,
)

# 骨格で 1 枚目のスライドが置かれているパス (presentation.xml.rels の Target 表記)
SKELETON_SLIDE1_TARGET = "slides/slide1.xml"

P_NS = "http://schemas.openxmlformats.org/presentationml/2006/main"
CT_NS = ooxml_svg.CT_NS
RELS_NS = ooxml_svg.RELS_NS
REL_SLIDE_LAYOUT = ("http://schemas.openxmlformats.org/officeDocument/2006/"
                    "relationships/slideLayout")
REL_SLIDE = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide"
REL_NOTES_MASTER = ("http://schemas.openxmlformats.org/officeDocument/2006/"
                    "relationships/notesMaster")

_NSMAP = {
    "a": ooxml_svg.A_NS,
    "r": ooxml_svg.R_NS,
    "p": P_NS,
    "asvg": ooxml_svg.ASVG_NS,
}


class SvgPptxError(RuntimeError):
    """pptx を作れない (骨格が取れない / スライド寸法が規格外 / 一次 pptx が規約違反)。"""


def P(tag):
    return f"{{{P_NS}}}{tag}"


def A(tag):
    return ooxml_svg.A(tag)


# =====================================================================
# 骨格 pptx の入手
# =====================================================================

_skeleton_cache = None


def load_skeleton():
    """`pandoc --print-default-data-file reference.pptx` を dict(パス -> bytes) で返す (プロセス内で 1 回)。"""
    global _skeleton_cache
    if _skeleton_cache is not None:
        return _skeleton_cache
    cmd = ["pandoc", "--print-default-data-file", "reference.pptx"]
    res = subprocess.run(cmd, capture_output=True)
    if res.returncode != 0 or not res.stdout:
        raise SvgPptxError(
            "骨格 pptx を取り出せません: " + " ".join(cmd) + "\n"
            f"  {res.stderr.decode('utf-8', 'ignore').strip()}\n"
            "  pandoc が入ったコンテナ内で実行してください "
            "(docker compose -f docker/docker-compose.yml run --rm pandoc ...)。"
        )
    try:
        with zipfile.ZipFile(io.BytesIO(res.stdout)) as z:
            parts = {i.filename: z.read(i.filename) for i in z.infolist()}
    except zipfile.BadZipFile as exc:
        raise SvgPptxError(f"骨格 pptx が zip として読めません ({exc})") from exc
    # 骨格の前提は BLANK_LAYOUT の有無だけでなく、すべてここで確かめる。とくに「1 枚目のスライドを
    # 指す関係 ID」を固定値 (rId2) と決めつけると、pandoc の版を上げて関係の並びが変わったときに、
    # 生成も受入テストも LibreOffice の読み込みも通るのに
    # **プレゼンテーションからスライドへ到達できない pptx** ができる (実測: 出力 PDF は白紙 1 ページ)。
    # 前提が外れたら黙って進まずに停止する。
    missing = [p for p in _REQUIRED_SKELETON_PARTS if p not in parts]
    if missing:
        raise SvgPptxError(
            "骨格 pptx に必要なパートがありません: " + " / ".join(missing) + "\n"
            "  pandoc の既定 pptx の構成が変わった可能性があります "
            "(本モジュールは pandoc の reference.pptx を骨格として加工しています)。\n"
            "  docker/pandoc/Dockerfile の PANDOC_VERSION を確認し、"
            "svg_pptx.py の間引き規則 (_DROP_PREFIXES) と合わせて見直してください。"
        )
    _slide_rid(parts)          # 引けなければここで停止する (返り値は build 時に採り直す)
    _skeleton_cache = parts
    return parts


def _slide_rid(parts):
    """骨格の `ppt/_rels/presentation.xml.rels` から 1 枚目のスライドを指す関係 ID を引く。

    `rId2` のような固定値を書くと、その値が本当にスライドを指しているかを確かめられない。
    実際の関係定義から引き、期待どおり 1 件だけ見つからなければ停止する。
    """
    root = etree.fromstring(parts["ppt/_rels/presentation.xml.rels"])
    hits = [rel.get("Id") for rel in root
            if rel.get("Type") == REL_SLIDE and rel.get("Target") == SKELETON_SLIDE1_TARGET]
    if len(hits) != 1:
        raise SvgPptxError(
            f"骨格 pptx の presentation.xml.rels に '{SKELETON_SLIDE1_TARGET}' を指す関係が "
            f"{len(hits)} 件あります (1 件を期待)。\n"
            "  pandoc の既定 pptx の構成が変わった可能性があります。"
            "この前提が崩れたまま生成すると、スライドに到達できない pptx (開いても白紙) ができます。"
        )
    return hits[0]


# =====================================================================
# スライド寸法の決定
# =====================================================================

def _skeleton_slide_size(parts):
    """骨格の `p:sldSz` を (cx, cy) EMU で返す (`slide_fit: fixed` の既定サイズ)。"""
    root = etree.fromstring(parts["ppt/presentation.xml"])
    sz = root.find(P("sldSz"))
    if sz is None:
        raise SvgPptxError("骨格 pptx に p:sldSz がありません")
    return int(sz.get("cx")), int(sz.get("cy"))


def plan_layout(width_in, height_in, slide_fit, fixed_size):
    """スライド寸法と図の配置を決める。

    返り値 dict: slide_cx / slide_cy / off_x / off_y / ext_cx / ext_cy (すべて EMU) と
                 placed_w_in / placed_h_in (図が実際に占める寸法) / fit (採用した方式) /
                 pad_w_in / pad_h_in (規格下限に合わせるために足した余白。0 なら足していない)。

    slide_fit:
      "figure" … スライド = 図の物理サイズ (スライド側に余分な余白を作らない)。
      "fixed"  … スライド = 骨格の既定サイズ。図は縦横比を保って収め、中央に置く。
                 **拡大はしない** (拡大すると PNG フォールバックの実効解像度が目標を下回るため)。
                 縮小して置いた場合、代替表示 PNG も**その置いた寸法**でラスタ化する
                 (公称サイズで作ると最大 39 倍 (面積) 過大になる)。

    【下限 (1 インチ) の扱い = クランプ】ECMA-376 の `ST_SlideSizeCoordinate` の下限を割る軸だけ
    スライドを 1 インチへ広げ、図を中央に置く。0.86 インチ高の図なら足す余白は上下 0.07 インチずつで、
    `fixed` (10×5.625 インチの台紙に載せる) より圧倒的に小さい。**寸法が 1 インチ未満の図は珍しくない**
    ため (横長の流れ図の高さなど)、ここで停止させると
    ごく普通の図で提出が止まり、しかも案内先の `fixed` のほうが余白が増えて
    「closely cropped」から遠ざかる。足した余白量は呼び出し側が必ず警告に出す。

    【上限 (56 インチ) の扱い = エラー】上限側はクランプできない。スライドを 56 インチに切っても
    図は公称サイズのまま置かれるので**はみ出す**し、図を縮めれば「図の実寸をそのまま伝える」という
    `slide_fit: figure` の意味が失われる。**SvgPptxError** で停止し、`slide_fit: fixed`
    (縦横比を保って縮小配置) か SVG の寸法修正か `--format png` を案内する。
    """
    fig_cx = max(1, round(width_in * EMU_PER_INCH))
    fig_cy = max(1, round(height_in * EMU_PER_INCH))

    if slide_fit == "figure":
        over = []
        if fig_cx > SLIDE_MAX_EMU:
            over.append(f"幅 {width_in:.3f} in")
        if fig_cy > SLIDE_MAX_EMU:
            over.append(f"高さ {height_in:.3f} in")
        if over:
            raise SvgPptxError(
                "スライド寸法が PowerPoint の規格の上限 (56 インチ) を超えます: "
                + " / ".join(over) + "\n"
                "  ECMA-376 の ST_SlideSizeCoordinate は 914400〜51206400 EMU に制限されており、"
                "この範囲外のスライドを作ると PowerPoint がファイルの修復を促します。\n"
                "  上限側はスライドを切り詰めても図がはみ出すだけなので自動では直せません。\n"
                "  対処: (a) SVG ルートの width/height を物理単位で 56 インチ以内にする "
                "(推奨。図の実寸がそのまま雑誌に伝わる)、"
                "(b) '--slide-fit fixed' か profile の figures.pptx.slide_fit: fixed で"
                "既定サイズのスライドに縮小配置する、"
                "(c) '--format png' で 300dpi ラスタとして提出する。"
            )
        # 下限を割る軸だけ 1 インチへ広げる (クランプ)。広げた分は図の周りの余白になる。
        slide_cx = max(fig_cx, SLIDE_MIN_EMU)
        slide_cy = max(fig_cy, SLIDE_MIN_EMU)
        return {
            "slide_cx": slide_cx, "slide_cy": slide_cy,
            "off_x": (slide_cx - fig_cx) // 2, "off_y": (slide_cy - fig_cy) // 2,
            "ext_cx": fig_cx, "ext_cy": fig_cy,
            "placed_w_in": fig_cx / EMU_PER_INCH, "placed_h_in": fig_cy / EMU_PER_INCH,
            "fit": "figure",
            "pad_w_in": (slide_cx - fig_cx) / EMU_PER_INCH,
            "pad_h_in": (slide_cy - fig_cy) / EMU_PER_INCH,
        }

    slide_cx, slide_cy = fixed_size
    # 縦横比を保って収める (拡大はしない = 倍率の上限は 1.0)
    scale = min(1.0, slide_cx / fig_cx, slide_cy / fig_cy)
    ext_cx = max(1, round(fig_cx * scale))
    ext_cy = max(1, round(fig_cy * scale))
    return {
        "slide_cx": slide_cx, "slide_cy": slide_cy,
        "off_x": (slide_cx - ext_cx) // 2, "off_y": (slide_cy - ext_cy) // 2,
        "ext_cx": ext_cx, "ext_cy": ext_cy,
        "placed_w_in": ext_cx / EMU_PER_INCH, "placed_h_in": ext_cy / EMU_PER_INCH,
        "fit": "fixed",
        "pad_w_in": (slide_cx - ext_cx) / EMU_PER_INCH,
        "pad_h_in": (slide_cy - ext_cy) / EMU_PER_INCH,
    }


# =====================================================================
# パートの組み立て
# =====================================================================

def _xml(root):
    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)


def _build_slide(layout, name, descr):
    """図 1 枚だけを載せた `ppt/slides/slide1.xml` を組み立てる。

    構造 (docx の pic:pic と同型。共通部は ooxml_svg):
      p:pic > p:blipFill > a:blip @r:embed=PNG
                            └ a:extLst > a:ext uri=SVG拡張 > asvg:svgBlip @r:embed=SVG
            > p:spPr > a:xfrm (a:off / a:ext) + a:prstGeom
    """
    sld = etree.Element(P("sld"), nsmap=_NSMAP)
    csld = etree.SubElement(sld, P("cSld"))
    tree = etree.SubElement(csld, P("spTree"))

    nv_grp = etree.SubElement(tree, P("nvGrpSpPr"))
    cnv = etree.SubElement(nv_grp, P("cNvPr"))
    cnv.set("id", "1")
    cnv.set("name", "")
    etree.SubElement(nv_grp, P("cNvGrpSpPr"))
    etree.SubElement(nv_grp, P("nvPr"))
    grp_pr = etree.SubElement(tree, P("grpSpPr"))
    xfrm0 = etree.SubElement(grp_pr, A("xfrm"))
    etree.SubElement(xfrm0, A("off")).attrib.update({"x": "0", "y": "0"})
    etree.SubElement(xfrm0, A("ext")).attrib.update({"cx": "0", "cy": "0"})
    etree.SubElement(xfrm0, A("chOff")).attrib.update({"x": "0", "y": "0"})
    etree.SubElement(xfrm0, A("chExt")).attrib.update({"cx": "0", "cy": "0"})

    pic = etree.SubElement(tree, P("pic"))
    nv_pic = etree.SubElement(pic, P("nvPicPr"))
    c = etree.SubElement(nv_pic, P("cNvPr"))
    c.set("id", "2")
    c.set("name", name)
    if descr:
        c.set("descr", descr)
    cnv_pic = etree.SubElement(nv_pic, P("cNvPicPr"))
    etree.SubElement(cnv_pic, A("picLocks")).set("noChangeAspect", "1")
    etree.SubElement(nv_pic, P("nvPr"))

    blip_fill = etree.SubElement(pic, P("blipFill"))
    blip = etree.SubElement(blip_fill, A("blip"))
    blip.set(ooxml_svg.R("embed"), "rId2")          # PNG フォールバック
    ooxml_svg.inject_svg_ext(blip, "rId3")          # SVG 本体 (共通部)
    etree.SubElement(etree.SubElement(blip_fill, A("stretch")), A("fillRect"))

    sp_pr = etree.SubElement(pic, P("spPr"))
    xfrm = etree.SubElement(sp_pr, A("xfrm"))
    etree.SubElement(xfrm, A("off")).attrib.update(
        {"x": str(layout["off_x"]), "y": str(layout["off_y"])})
    etree.SubElement(xfrm, A("ext")).attrib.update(
        {"cx": str(layout["ext_cx"]), "cy": str(layout["ext_cy"])})
    geom = etree.SubElement(sp_pr, A("prstGeom"))
    geom.set("prst", "rect")
    etree.SubElement(geom, A("avLst"))

    clr = etree.SubElement(sld, P("clrMapOvr"))
    etree.SubElement(clr, A("masterClrMapping"))
    return _xml(sld)


def _build_slide_rels():
    """`ppt/slides/_rels/slide1.xml.rels` (レイアウト + PNG + SVG)。"""
    root = etree.Element(f"{{{RELS_NS}}}Relationships", nsmap={None: RELS_NS})
    rel = etree.SubElement(root, f"{{{RELS_NS}}}Relationship")
    rel.set("Id", "rId1")
    rel.set("Type", REL_SLIDE_LAYOUT)
    rel.set("Target", "../" + BLANK_LAYOUT.split("ppt/", 1)[1])
    ooxml_svg.add_image_rel(root, "../media/figure.png", rid="rId2")
    ooxml_svg.add_image_rel(root, "../media/figure.svg", rid="rId3")
    return _xml(root)


def _build_presentation(parts, slide_cx, slide_cy, slide_rid):
    """骨格の `ppt/presentation.xml` を 1 スライド構成に作り直す。

    `slide_rid` は `_slide_rid()` が骨格の関係定義から引いた実際の関係 ID である
    (`"rId2"` のような固定値を書くと、骨格の並びが変わったときに
    存在しない関係 ID を指す = スライドへ到達できない pptx になる)。
    """
    root = etree.fromstring(parts["ppt/presentation.xml"])
    notes_lst = root.find(P("notesMasterIdLst"))
    if notes_lst is not None:
        root.remove(notes_lst)
    sld_lst = root.find(P("sldIdLst"))
    if sld_lst is None:
        raise SvgPptxError("骨格 pptx の presentation.xml に p:sldIdLst がありません")
    for child in list(sld_lst):
        sld_lst.remove(child)
    sld = etree.SubElement(sld_lst, P("sldId"))
    sld.set("id", "256")
    sld.set(ooxml_svg.R("id"), slide_rid)
    sz = root.find(P("sldSz"))
    sz.set("cx", str(slide_cx))
    sz.set("cy", str(slide_cy))
    # type は既定の画面サイズ (screen16x9 等) の名前なので、任意寸法にしたら外す
    sz.attrib.pop("type", None)
    return _xml(root)


def _build_presentation_rels(parts):
    """骨格の `ppt/_rels/presentation.xml.rels` から slide2..4 と notesMaster を落とす。"""
    root = etree.fromstring(parts["ppt/_rels/presentation.xml.rels"])
    for rel in list(root):
        rtype, target = rel.get("Type", ""), rel.get("Target", "")
        if rtype == REL_NOTES_MASTER:
            root.remove(rel)
        elif rtype == REL_SLIDE and target != SKELETON_SLIDE1_TARGET:
            root.remove(rel)
    return _xml(root)


def _build_content_types(parts):
    """`[Content_Types].xml` を最終的なパート構成に合わせ、png / svg の Default を足す。

    **判定は「最終的に残ったパートに在るか」で行う** (削除したパート名の一覧では行わない)。
    骨格から一度落としたあと同じ名前で作り直すパート (`docProps/core.xml` / `docProps/app.xml`) が
    あり、削除リストで消すと**再追加したパートの Override まで失われる**ためである。
    実際それが起きていて、docProps が `.xml` の Default (`application/xml`) に落ちていた —
    OPC はコアプロパティに専用の ContentType を要求するので、正しくない状態だった。
    「全パートが何らかの ContentType を持つか」だけを見る検査では気づけない種類の不具合なので、
    構造上そもそも起こらない書き方にしておく。
    """
    root = etree.fromstring(parts["[Content_Types].xml"])
    for ov in list(root.findall(f"{{{CT_NS}}}Override")):
        name = (ov.get("PartName") or "").lstrip("/")
        if name not in parts:
            root.remove(ov)
    ooxml_svg.ensure_default_content_type(root, "png", ooxml_svg.PNG_CONTENT_TYPE)
    ooxml_svg.ensure_svg_content_type(root)
    return _xml(root)


def _build_root_rels():
    """`_rels/.rels` (officeDocument + core/app プロパティ)。骨格のものと同じ構成を自前で書く。"""
    root = etree.Element(f"{{{RELS_NS}}}Relationships", nsmap={None: RELS_NS})
    for rid, rtype, target in (
        ("rId1", "http://schemas.openxmlformats.org/officeDocument/2006/relationships/"
                 "officeDocument", "ppt/presentation.xml"),
        ("rId2", "http://schemas.openxmlformats.org/package/2006/relationships/metadata/"
                 "core-properties", "docProps/core.xml"),
        ("rId3", "http://schemas.openxmlformats.org/officeDocument/2006/relationships/"
                 "extended-properties", "docProps/app.xml"),
    ):
        rel = etree.SubElement(root, f"{{{RELS_NS}}}Relationship")
        rel.set("Id", rid)
        rel.set("Type", rtype)
        rel.set("Target", target)
    return _xml(root)


# docProps は骨格の値 (pandoc 開発者の氏名 / 2017 年の作成日時 / "Microsoft Macintosh PowerPoint")
# をそのまま投稿物に載せないよう中立な内容で書き直す。時刻は固定値 (書庫の再現性)。
FIXED_TIMESTAMP = "1980-01-01T00:00:00Z"

_CORE_XML = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties"\
 xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/"\
 xmlns:dcmitype="http://purl.org/dc/dcmitype/"\
 xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"><dc:title>{title}</dc:title>\
<dcterms:created xsi:type="dcterms:W3CDTF">{ts}</dcterms:created>\
<dcterms:modified xsi:type="dcterms:W3CDTF">{ts}</dcterms:modified></cp:coreProperties>"""

_APP_XML = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties"\
 xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes">\
<TotalTime>0</TotalTime><Words>0</Words><Application>docx-paper-template (svg-blob)</Application>\
<PresentationFormat>Custom</PresentationFormat><Paragraphs>0</Paragraphs><Slides>1</Slides>\
<Notes>0</Notes><HiddenSlides>0</HiddenSlides><MMClips>0</MMClips><ScaleCrop>false</ScaleCrop>\
<HeadingPairs><vt:vector size="2" baseType="variant"><vt:variant><vt:lpstr>Slide Titles</vt:lpstr>\
</vt:variant><vt:variant><vt:i4>1</vt:i4></vt:variant></vt:vector></HeadingPairs>\
<TitlesOfParts><vt:vector size="1" baseType="lpstr"><vt:lpstr>{title}</vt:lpstr></vt:vector>\
</TitlesOfParts><Company></Company><LinksUpToDate>false</LinksUpToDate><SharedDoc>false</SharedDoc>\
<HyperlinksChanged>false</HyperlinksChanged><AppVersion>16.0000</AppVersion></Properties>"""


def _xml_escape(text):
    return (str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


# =====================================================================
# 書き出し
# =====================================================================

def write_pptx(path, parts):
    """dict(パス -> bytes) を pptx (zip) として書き出す。項目時刻と順序を固定する。

    [Content_Types].xml を先頭に置くのは OPC の慣行 (必須ではないが読み手に優しい)。
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    names = sorted(parts)
    if "[Content_Types].xml" in parts:
        names.remove("[Content_Types].xml")
        names.insert(0, "[Content_Types].xml")
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        for name in names:
            info = zipfile.ZipInfo(name, date_time=FIXED_ZIP_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            z.writestr(info, parts[name])
    return path


def build_figure_pptx(svg_path, out_pptx, png_path=None, dpi=300, slide_fit="figure",
                      title="Figure", descr=None, log=None):
    """SVG 1 枚から「1 スライド 1 図」の pptx を作る (案 B = svg-blob)。

    引数:
      svg_path  : 埋め込む SVG (正本。text_to_path 済みのものを渡すこともある)
      out_pptx  : 出力先
      png_path  : PNG フォールバックの生成先。**省略時は一時ディレクトリに作って捨てる**
                  (out_pptx の隣に中間ファイルを残さない)
      dpi       : PNG フォールバックの解像度 (profile の figures.pptx.png_fallback_dpi)
      slide_fit : "figure" (スライド = 図の実寸) / "fixed" (既定サイズ + 中央配置)
      title     : スライド上の図形名・ファイルプロパティのタイトル (例 "Figure 1")
      descr     : 代替テキスト (図のキャプション等。省略可)

    返り値 dict: pptx / png / slide_w_in / slide_h_in / placed_w_in / placed_h_in /
                 fit / png_width / png_height / png_dpi / effective_dpi / svg_basis

    **PNG フォールバックは保険ではなく多数の受け手が実際に見る本体**である
    (SVG のネイティブ表示は Microsoft 365 / Office 2019 以降。買い切り版 Office 2016 と
    投稿系の査読用 PDF 変換では PNG 側が描画される公算が大きい)。
    したがって PNG は 300dpi の保証経路 (`svg_raster`) を必ず通す。
    """
    svg_path = Path(svg_path)
    out_pptx = Path(out_pptx)
    parts = dict(load_skeleton())

    info = svg_raster.svg_physical_size(svg_path)      # svg_raster の寸法解析を再利用
    layout = plan_layout(info["width_in"], info["height_in"], slide_fit,
                         _skeleton_slide_size(parts))

    # --- PNG フォールバック (svg_raster の 300dpi 保証経路) ---
    # png_path の省略時は一時ディレクトリに置き、書庫へ取り込んだら捨てる。既定を
    # `out_pptx.with_suffix(".fallback.png")` のような出力の隣にすると、呼び出し側が
    # png_path を省いたときに**提出ディレクトリに中間 PNG が残る**側へ倒れる (package.py は
    # 一時ディレクトリを渡すので影響しないが、既定値が危険側だと将来の呼び出し側を誤らせる)。
    with contextlib.ExitStack() as stack:
        if png_path:
            png_path = Path(png_path)
            png_kept = str(png_path)
        else:
            png_path = Path(stack.enter_context(tempfile.TemporaryDirectory())) / "fallback.png"
            png_kept = None          # 一時ファイルなので呼び出し側へパスを返さない
        # ラスタ化の基準は**図の公称サイズ**ではなく**実際に置く寸法**にする。
        # slide_fit: figure では両者が一致する。fixed のときは画素数が減る — 公称サイズで作ると、
        # 幅 62.5 インチの図を 10 インチに置くのに 18750 画素の PNG を作ることになり (面積で約 39 倍)、
        # しかも fixed は「56 インチ超の図」の逃げ道として本モジュール自身が案内する経路なので、
        # 面積の大きい図では MAX_PIXELS に当たって逃げ道が塞がってしまう。
        r = svg_raster.render_png_at_dpi(
            svg_path, png_path, dpi, log=log, label=f"{title} (pptx フォールバック)",
            place_size_in=(layout["placed_w_in"], layout["placed_h_in"]))
        png_data = png_path.read_bytes()
    # 図はスライド上で公称サイズ以下にしか置かれない (plan_layout は拡大しない) うえ、
    # ラスタ化の基準も置く寸法なので、実効解像度はちょうど目標 dpi になる。数値で持ち帰る。
    eff_dpi = r["width_px"] / layout["placed_w_in"] if layout["placed_w_in"] > 0 else 0

    # --- 骨格の間引き ---
    dropped = [n for n in parts
               if any(n == d or n.startswith(d) for d in _DROP_PREFIXES)]
    for name in dropped:
        parts.pop(name)

    # --- 作り直すパート ---
    safe_title = _xml_escape(title)
    parts["ppt/slides/slide1.xml"] = _build_slide(layout, title, descr)
    parts["ppt/slides/_rels/slide1.xml.rels"] = _build_slide_rels()
    # 1 枚目のスライドを指す関係 ID は骨格の関係定義から引く。
    # _build_presentation_rels はこの後で走るので、ここではまだ骨格の rels を読める。
    parts["ppt/presentation.xml"] = _build_presentation(
        parts, layout["slide_cx"], layout["slide_cy"], _slide_rid(parts))
    parts["ppt/_rels/presentation.xml.rels"] = _build_presentation_rels(parts)
    parts["_rels/.rels"] = _build_root_rels()
    parts["docProps/core.xml"] = _CORE_XML.format(
        title=safe_title, ts=FIXED_TIMESTAMP).encode("utf-8")
    parts["docProps/app.xml"] = _APP_XML.format(title=safe_title).encode("utf-8")

    # --- 実体 (Content_Types は最終構成から作るので、パートを全部揃えてから組む) ---
    parts["ppt/media/figure.svg"] = svg_path.read_bytes()
    parts["ppt/media/figure.png"] = png_data

    parts["[Content_Types].xml"] = _build_content_types(parts)

    write_pptx(out_pptx, parts)
    result = {
        "pptx": str(out_pptx), "png": png_kept,
        "slide_w_in": layout["slide_cx"] / EMU_PER_INCH,
        "slide_h_in": layout["slide_cy"] / EMU_PER_INCH,
        "placed_w_in": layout["placed_w_in"], "placed_h_in": layout["placed_h_in"],
        "fit": layout["fit"], "png_width": r["width_px"], "png_height": r["height_px"],
        "png_dpi": dpi, "effective_dpi": eff_dpi, "svg_basis": info["basis"],
        "pad_w_in": layout["pad_w_in"], "pad_h_in": layout["pad_h_in"],
    }
    if log:
        log(f"  pptx: {title}: スライド {result['slide_w_in']:.3f}x{result['slide_h_in']:.3f} in "
            f"[slide_fit={result['fit']}] / 図 {result['placed_w_in']:.3f}x"
            f"{result['placed_h_in']:.3f} in / PNG {r['width_px']}x{r['height_px']} px "
            f"(置いた寸法での実効 {eff_dpi:.0f}dpi)")
    return result


# =====================================================================
# 案 A: 一次ソースが pptx のときの無変換コピー
# =====================================================================

MACRO_SUFFIXES = (".pptm", ".ppsm", ".potm")


def inspect_pptx(src):
    """提出前に一次 pptx を検査する。返り値 dict(slides, has_macro, media)。

    規約 (`CLAUDE.md` の執筆規約 / `docs/journal-bhi.md` §5.1.2):
      - **1 ファイル 1 スライド** (BHI は図ごとにアップロードし、多パネル図は 1 ファイルに合成する)
      - **マクロを含むファイルは不可** (投稿系はマクロや ActiveX を含む文書の変換に失敗すると明記)
    """
    src = Path(src)
    if src.suffix.lower() in MACRO_SUFFIXES:
        raise SvgPptxError(
            f"マクロ有効の PowerPoint ファイルは提出できません: {src.name}\n"
            "  投稿系はマクロ / ActiveX を含む文書の変換に失敗すると明記しています。"
            "マクロを外して .pptx で保存し直してください。"
        )
    try:
        with zipfile.ZipFile(src) as z:
            names = z.namelist()
    except (zipfile.BadZipFile, OSError) as exc:
        raise SvgPptxError(f"pptx として読めません: {src} ({exc})") from exc
    slides = sorted(n for n in names
                    if n.startswith("ppt/slides/slide") and n.endswith(".xml"))
    has_macro = any(n.startswith("ppt/vbaProject") for n in names)
    return {"slides": slides, "has_macro": has_macro,
            "media": sorted(n for n in names if n.startswith("ppt/media/"))}


def copy_pptx_passthrough(src, dest, log=None):
    """一次ソースの pptx を**無変換でコピー**する (案 A。劣化ゼロ)。

    スライド数と マクロの有無だけを機械検査する。分割 (複数スライドからの抽出) は実装しない —
    「1 ファイル 1 スライドにしてから置く」を執筆規約とし、違反はここで停止させる。
    """
    src, dest = Path(src), Path(dest)
    info = inspect_pptx(src)
    if info["has_macro"]:
        raise SvgPptxError(
            f"マクロ (ppt/vbaProject) を含む pptx は提出できません: {src.name}\n"
            "  投稿系はマクロ / ActiveX を含む文書の変換に失敗すると明記しています。"
        )
    if len(info["slides"]) != 1:
        raise SvgPptxError(
            f"pptx のスライドが {len(info['slides'])} 枚あります: {src.name}\n"
            "  BHI は図ごとに 1 ファイルでアップロードし、多パネル図は 1 ファイルに合成することを"
            "求めています。**1 ファイル 1 スライド**にしてから置いてください "
            "(スライド抽出はツール側で実装していません)。"
        )
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(src.read_bytes())
    if log:
        log(f"  pptx: {src} -> {dest} [案 A: 無変換コピー (劣化ゼロ) / スライド 1 枚を確認]")
    return {"pptx": str(dest), "source": str(src), "mode": "passthrough",
            "media": info["media"]}
