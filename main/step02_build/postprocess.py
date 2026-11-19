#!/usr/bin/env python3
"""postprocess.py — pandoc 生成 docx の OOXML 後処理 (build / diff 共用)。

docs/architecture.md §2.2。pandoc + generic-style.lua が出した docx を lxml で直接編集し、次を行う:

  1. 表の罫線: 既定は booktabs (三本線)。直前に GRID_TABLE マーカーがある表は全罫線 (.grid)。
  2. ネイティブ SVG 埋込: a:blip に asvg:svgBlip を注入し word/media に SVG を同梱する
     (Microsoft 365 / Office 2019 以降はベクター表示 / 買い切り版 Office 2016 を含む旧 Word は
      PNG フォールバック。SVG 対応は購読版 Office 365 で追加され、買い切り版は 2019 以降である)。
     【誤埋込防止 (docs/architecture.md §2.2)】位置一致のみに頼らず、原稿の画像順と docx の図 (a:blip) 順を
       1 対 1 で対応付け、件数を検証し、各図の docPr@descr (= "Figure N: キャプション") に
       原稿キャプションが含まれることを照合してから埋め込む。
     【埋め込む SVG は修正済み (docs/architecture.md §2.1)】原稿の素 SVG ではなく、pandoc と同じ
       --resource-path 解決で得た data/step01_figures/figs/<rel>.svg (Step 01 で修正・変換済み) を同梱する。
  3. テキストボックス: generic-style.lua が置いた TEXTBOX_START/END マーカー区間を
     DrawingML の浮動テキストボックス (wp:anchor > wps:wsp > w:txbxContent) へ変換し、
     page 属性で配置する。

【lxml 採用】xml.etree.ElementTree ではルートの名前空間宣言が再シリアライズで欠落し、
  正規表現でルートタグを復元するしかなくなる。
  本実装は lxml を使い (docs/architecture.md §1.2.1)、名前空間宣言を保持する。テキストボックスが使う
  wps / wp14 / mc / SVG 埋込が使う asvg はルート nsmap へ明示追加する。

使い方 (通常は build_docx.py / diff.sh 経由):
    python3 postprocess.py <docx> [--source <main.md>] \
        [--resource-path a:b:c] [--no-embed-svg] [--no-relocate]
"""

import argparse
import os
import re
import sys
import zipfile
from io import BytesIO
from pathlib import Path

from lxml import etree

# SVG ネイティブ埋込の docx/pptx 共通部は共通モジュールへ切り出した。
# 拡張識別子・要素名・Content_Types への svg 登録を docx と pptx で二重に持たないため。
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "00_setup" / "lib"))
import ooxml_svg  # noqa: E402

# --- 名前空間 ---
NS = {
    "w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
    "r": ooxml_svg.R_NS,
    "wp": "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing",
    "wp14": "http://schemas.microsoft.com/office/word/2010/wordprocessingDrawing",
    "wps": "http://schemas.microsoft.com/office/word/2010/wordprocessingShape",
    "a": ooxml_svg.A_NS,
    "mc": "http://schemas.openxmlformats.org/markup-compatibility/2006",
    "asvg": ooxml_svg.ASVG_NS,
}
MC_IGNORABLE = f"{{{NS['mc']}}}Ignorable"
# 注: パッケージ関係・Content_Types・image 関係型・SVG 拡張識別子 (RELS_NS / CT_NS /
# REL_IMAGE / SVG_EXT_URI) は ooxml_svg に置く。ここに別名を置くと
# 「同じ値が 2 箇所にある」状態になるので置かない — 必要なら ooxml_svg.<名前> を直接使うこと。


def W(tag):
    return f"{{{NS['w']}}}{tag}"


def A(tag):
    return f"{{{NS['a']}}}{tag}"


def WP(tag):
    return f"{{{NS['wp']}}}{tag}"


def WPS(tag):
    return f"{{{NS['wps']}}}{tag}"


# =====================================================================
# 名前空間の整備
# =====================================================================

def ensure_root_namespaces(root):
    """ルート要素の nsmap に textbox / SVG 埋込で使う名前空間を加えて返す。

    pandoc の document.xml は w/r/wp/a 等は宣言するが wps/wp14/mc/asvg は宣言しない。
    lxml は宣言済みの接頭辞を再利用するため、ルートに wps/wp14/mc/asvg を正しい接頭辞名で
    宣言しておくと、後で挿入する要素が ns0 等の自動接頭辞ではなく wps:/asvg: を使う。
    mc:Ignorable="wps wp14" は接頭辞名を文字列で参照するため、接頭辞名の一致が必須。

    lxml は既存要素の nsmap を変更できないので、同タグ・同属性・同子の新ルートを作り直す。
    既存宣言に不足が無ければそのまま返す (無駄な作り直しを避ける)。
    """
    need = {p: u for p, u in NS.items() if u not in root.nsmap.values()}
    if not need:
        return root
    new_nsmap = dict(root.nsmap)
    new_nsmap.update(need)
    new_root = etree.Element(root.tag, nsmap=new_nsmap)
    for k, v in root.attrib.items():
        new_root.set(k, v)
    for child in root:
        new_root.append(child)
    return new_root


# =====================================================================
# 1. 表の罫線 (booktabs / .grid 全罫線)
# =====================================================================

def _is_marker(para, text=None):
    """段落が TextBoxMarker スタイルか (text 指定時はその隠しテキストか) を判定。"""
    if para.tag != W("p"):
        return False
    ppr = para.find(W("pPr"))
    if ppr is None:
        return False
    pstyle = ppr.find(W("pStyle"))
    if pstyle is None or pstyle.get(W("val")) != "TextBoxMarker":
        return False
    if text is None:
        return True
    return _marker_text(para) == text


def _marker_text(para):
    for t in para.iter(W("t")):
        if t.text:
            return t.text
    return ""


def _set_cell_borders(tc, top, bottom, left, right):
    """セル罫線を設定する。各引数は 'single' / 'nil'。"""
    tcpr = tc.find(W("tcPr"))
    if tcpr is None:
        tcpr = etree.Element(W("tcPr"))
        tc.insert(0, tcpr)
    old = tcpr.find(W("tcBorders"))
    if old is not None:
        tcpr.remove(old)
    tcb = etree.SubElement(tcpr, W("tcBorders"))
    for side, val in (("top", top), ("left", left), ("bottom", bottom), ("right", right)):
        e = etree.SubElement(tcb, W(side))
        if val == "single":
            e.set(W("val"), "single")
            e.set(W("sz"), "4")
            e.set(W("space"), "0")
            e.set(W("color"), "auto")
        else:
            e.set(W("val"), "nil")


def _reset_table_look(tbl, look_val):
    """tblPr の tblLook を整え、表レベル tblBorders は除去する (セル単位で制御するため)。"""
    tblpr = tbl.find(W("tblPr"))
    if tblpr is None:
        tblpr = etree.Element(W("tblPr"))
        tbl.insert(0, tblpr)
    look = tblpr.find(W("tblLook"))
    if look is None:
        look = etree.SubElement(tblpr, W("tblLook"))
    look.set(W("val"), look_val)
    tb = tblpr.find(W("tblBorders"))
    if tb is not None:
        tblpr.remove(tb)


def _apply_booktabs(tbl):
    """三本線 (上端・ヘッダ下・最下端のみ横罫) を適用する。"""
    _reset_table_look(tbl, "04A0")
    rows = tbl.findall(W("tr"))
    if not rows:
        return
    for ri, row in enumerate(rows):
        is_header = (row.find(f"{W('trPr')}/{W('tblHeader')}") is not None) or (ri == 0)
        is_last = (ri == len(rows) - 1)
        for tc in row.findall(W("tc")):
            if is_header:
                _set_cell_borders(tc, top="single", bottom="single", left="nil", right="nil")
            elif is_last:
                _set_cell_borders(tc, top="nil", bottom="single", left="nil", right="nil")
            else:
                _set_cell_borders(tc, top="nil", bottom="nil", left="nil", right="nil")


def _apply_grid(tbl):
    """全セル四辺に罫線を引く (.grid 指定時)。"""
    _reset_table_look(tbl, "0000")
    for row in tbl.findall(W("tr")):
        for tc in row.findall(W("tc")):
            _set_cell_borders(tc, top="single", bottom="single", left="single", right="single")


def apply_table_borders(root):
    """全表に罫線を適用する。直前が GRID_TABLE マーカーの表は全罫線、それ以外は booktabs。

    罫線適用後、用済みの GRID_TABLE マーカー段落を除去する (雑誌テンプレが TextBoxMarker
    スタイルを持たない場合に "GRID_TABLE" の文字が露出するのを防ぐ)。
    """
    grid_markers = []
    for tbl in list(root.iter(W("tbl"))):
        prev = tbl.getprevious()
        if prev is not None and _is_marker(prev, "GRID_TABLE"):
            _apply_grid(tbl)
            grid_markers.append(prev)
        else:
            _apply_booktabs(tbl)
    for m in grid_markers:
        parent = m.getparent()
        if parent is not None:
            parent.remove(m)


# =====================================================================
# 2. ネイティブ SVG 埋込
# =====================================================================

def _strip_yaml_and_code(md_text):
    """YAML フロントマターとフェンスドコードブロックを除去 (画像構文の誤検出を防ぐ)。"""
    md_text = re.sub(r"^---\n.*?\n---\n", "", md_text, count=1, flags=re.DOTALL)
    md_text = re.sub(r"```.*?```", "", md_text, flags=re.DOTALL)
    return md_text


def _norm(text):
    """キャプション照合用の正規化 (英数字のみ小文字化)。"""
    return re.sub(r"[^0-9a-z]+", "", text.lower())


# 図キャプション中の引用・相互参照 (`[@key]` / `[@fig:x]` / `[@a; @b]`)。
# lua フィルタが書くマニフェストは citeproc / crossref を通す【前】の AST から採るため
# 生の `[@...]` が残るが、docx の docPr@descr は描画後で番号に置換済みになる。
_CITE_RE = re.compile(r"\[[^\]]*@[^\]]*\]")


def _caption_matches(caption, descr):
    """原稿キャプションが docx の descr に対応しているかを判定する。

    BHI は図・表の凡例中の引用を明示的に認めている (規定 References 節
    "Identify references in text, tables, and legends")。キャプションに引用や相互参照が
    あると原稿側は `[@key]`・docx 側は `3)` となり、単純な部分一致では必ず外れて
    「図の対応が疑わしい」が出続ける。
    引用・参照を境に分割し、残りの断片が descr に【順に】現れることで判定する。
    """
    fragments = [f for f in (_norm(x) for x in _CITE_RE.split(caption)) if f]
    if not fragments:
        return True  # 照合材料なし (空キャプション / 引用だけのキャプション) → 位置合わせに委ねる
    descr_n = _norm(descr)
    pos = 0
    for frag in fragments:
        idx = descr_n.find(frag, pos)
        if idx < 0:
            return False
        pos = idx + len(frag)
    return True


def _resolve_in_resource_path(rel_path, resource_path):
    """pandoc と同じ規則 (各 resource-path エントリ + 相対パス) で実体を探す。先勝ち。"""
    for base in resource_path:
        cand = os.path.normpath(os.path.join(base, rel_path))
        if os.path.isfile(cand):
            return cand
    return None


def _load_images(source_md, image_manifest):
    """原稿の画像を出現順に (caption, path) で取得する。

    生 Markdown 正規表現はキャプション内の角括弧・引用・参照形式画像で
    取りこぼし、件数不一致でビルドを中止させてしまう。generic-style.lua が pandoc AST から
    書き出すマニフェスト (src <TAB> caption) があればそれを優先し、無ければ正規表現へ
    フォールバックする (postprocess.py 単独実行・将来の diff 経路の互換のため)。
    """
    if image_manifest and os.path.isfile(image_manifest):
        images = []
        with open(image_manifest, "r", encoding="utf-8") as f:
            for line in f:
                line = line.rstrip("\n")
                if not line:
                    continue
                # マニフェストは 3 列 (src <TAB> caption <TAB> in_textbox)。`line.split("\t", 1)` の
                # ように 2 列で割ると 2 列目に 3 列目の in_textbox がまるごと混入し
                # (caption = "Figure 1: ...\t0" となる)、後段のキャプション照合 (embed_svg_native) が
                # 末尾の "0" のぶん常に外れて位置合わせに退避する
                # (「図の対応が疑わしい (位置で続行)」)。列をすべて割って caption 列だけを取る
                # (generic-style.lua が caption 内のタブは空白へ置換済みなので caption にタブは無い)。
                cols = line.split("\t")
                src = cols[0]
                caption = cols[1] if len(cols) > 1 else ""
                images.append((caption, src))
        return images
    with open(source_md, "r", encoding="utf-8") as f:
        md_text = _strip_yaml_and_code(f.read())
    return re.findall(r"!\[([^\]]*)\]\(([^)\s]+)", md_text)


def embed_svg_native(root, parts, source_md, resource_path, image_manifest=None):
    """原稿の SVG 図を Office のネイティブ SVG として埋め込む。

    ベクター表示は Microsoft 365 / Office 2019 以降。買い切り版 Office 2016 を含む旧 Word は
    PNG フォールバック表示になる。
    原稿の画像参照 (順序つき) と docx 内の図 (a:blip を含む w:drawing, 同順) を 1 対 1 対応させ、
    件数とキャプションを検証してから、SVG が指定された図にだけ asvg:svgBlip を注入する。
    埋め込む SVG は resource-path 解決で得た修正済み SVG (data/step01_figures/figs/<rel>.svg)。
    """
    images = _load_images(source_md, image_manifest)
    if not images:
        return 0

    # 図を .pdf で参照していないか (CLAUDE.md / docs/architecture.md §2.1 規約違反)。pandoc は PDF を docx 画像に
    # できず図を脱落させるため、分かりにくい件数不一致エラーになる前に明示的に止める。
    pdf_refs = [p for _, p in images if p.lower().endswith(".pdf")]
    if pdf_refs:
        raise SystemExit(
            "エラー: 図を .pdf で参照しています: " + ", ".join(pdf_refs) + "\n"
            "  PDF 図も原稿では .svg 拡張子で参照してください (Step 01 で SVG へ変換します。"
            "CLAUDE.md / docs/architecture.md §2.1)。"
        )

    # docx の図 (w:drawing) を出現順に取得。各 drawing から blip と docPr を引く。
    drawings = list(root.iter(W("drawing")))
    if len(drawings) != len(images):
        raise SystemExit(
            f"エラー: 原稿の画像数 ({len(images)}) と docx の図数 ({len(drawings)}) が一致しません。"
            " 図の対応付けが崩れるため中止します (docs/architecture.md §2.2)。\n"
            f"  原稿画像: {[p for _, p in images]}\n"
            "  ヒント: マニフェスト未使用時はキャプション内の角括弧・引用・HTML 画像・"
            "参照形式画像で件数がずれることがあります。"
        )

    # rels / Content_Types を読み、rId 採番と svg ContentType 追加の準備
    # (rId 採番と image 関係の追加は ooxml_svg の docx / pptx 共通部を使う)
    rels_path = "word/_rels/document.xml.rels"
    rels_root = etree.fromstring(parts[rels_path])
    ct_root = etree.fromstring(parts["[Content_Types].xml"])

    embedded = 0
    svg_counter = 0
    for (caption, path), drawing in zip(images, drawings):
        if not path.endswith(".svg"):
            continue  # SVG 以外 (PNG/JPG 等) はネイティブ埋込対象外

        blip = drawing.find(f".//{A('blip')}")
        docpr = drawing.find(f".//{WP('docPr')}")
        if blip is None:
            print(f"  警告: a:blip が見つからず埋込スキップ: {path}")
            continue

        # キャプション照合: docPr@descr は "Figure N: <caption>"。原稿キャプションが
        # 含まれることを確認 (純粋な位置一致だけに依存しない)。
        descr = docpr.get("descr", "") if docpr is not None else ""
        if not _caption_matches(caption, descr):
            print(
                f"  警告: 図の対応が疑わしい (位置で続行)。原稿キャプション='{caption}' / "
                f"docx descr='{descr}' / path={path}"
            )

        # 埋め込む修正済み SVG を解決
        svg_full = _resolve_in_resource_path(path, resource_path)
        if svg_full is None:
            print(
                f"  警告: 埋込用 SVG が resource-path に見つからず PNG のみ: {path}"
                f" (探索: {resource_path})"
            )
            continue
        with open(svg_full, "rb") as f:
            svg_data = f.read()

        svg_counter += 1
        media_name = f"svg{svg_counter}.svg"
        parts[f"word/media/{media_name}"] = svg_data

        new_rid = ooxml_svg.add_image_rel(rels_root, f"media/{media_name}")

        # a:blip > a:extLst > a:ext(uri) > asvg:svgBlip(r:embed)
        # この 3 要素の組み立ては pptx 経路と完全に同じなので ooxml_svg に置く
        # (docx と pptx で二重に持つと片方だけ直す事故が起きる)。
        # 要素名に注意: MS の SVG 拡張の要素名は asvg:svgBlip ("blip" = OOXML が画像参照に用いる語) で、
        #   svgBlob という要素は OOXML のどの名前空間にも存在しない。名前空間 URI と
        #   拡張識別子 (SVG_EXT_URI) が正しくても要素名を誤ると、Office は ext を uri で引き当てた後に
        #   子要素を探して見つけられず、a:blip の PNG フォールバックへ静かに戻る
        #   (ファイルは壊れず警告も出ないため「動いているように見えるが非ベクター」の状態になる)。
        ooxml_svg.inject_svg_ext(blip, new_rid)

        embedded += 1
        print(f"  SVG ネイティブ埋込: {path} -> word/media/{media_name} ({new_rid})  [{svg_full}]")

    if embedded == 0:
        return 0

    # Content_Types に svg の Default を追加 (未追加なら。ooxml_svg の docx / pptx 共通部)
    ooxml_svg.ensure_svg_content_type(ct_root)

    parts[rels_path] = etree.tostring(rels_root, xml_declaration=True, encoding="UTF-8", standalone=True)
    parts["[Content_Types].xml"] = etree.tostring(ct_root, xml_declaration=True, encoding="UTF-8", standalone=True)
    return embedded


# =====================================================================
# 3. テキストボックス (TEXTBOX_START/END → wp:anchor)
# =====================================================================

def _parse_textbox_attrs(text):
    """'TEXTBOX_START:k=v;k=v' を dict へ。"""
    attrs = {}
    for pair in text[len("TEXTBOX_START:"):].split(";"):
        if "=" in pair:
            k, v = pair.split("=", 1)
            attrs[k.strip()] = v.strip()
    return attrs


def _resize_content_to_width(content, max_w_emu):
    """テキストボックス幅に収まるよう中身の画像・表を縮小する。"""
    EMU_PER_TWIP = 635
    max_w_twip = int(max_w_emu / EMU_PER_TWIP)
    for elem in content:
        for inline in elem.iter(WP("inline")):
            ext = inline.find(WP("extent"))
            if ext is not None:
                cx = int(ext.get("cx", "0"))
                cy = int(ext.get("cy", "0"))
                if cx > max_w_emu > 0:
                    ratio = max_w_emu / cx
                    ext.set("cx", str(max_w_emu))
                    ext.set("cy", str(int(cy * ratio)))
                    for a_ext in inline.iter(A("ext")):
                        acx = int(a_ext.get("cx", "0"))
                        acy = int(a_ext.get("cy", "0"))
                        if acx > max_w_emu > 0:
                            a_ext.set("cx", str(max_w_emu))
                            a_ext.set("cy", str(int(acy * (max_w_emu / acx))))
        tables = ([elem] if elem.tag == W("tbl") else []) + list(elem.iter(W("tbl")))
        for tbl in tables:
            grid = tbl.find(W("tblGrid"))
            if grid is None:
                continue
            cols = grid.findall(W("gridCol"))
            total = sum(int(c.get(W("w"), "0")) for c in cols)
            if total <= 0 or total <= max_w_twip:
                continue
            ratio = max_w_twip / total
            for c in cols:
                c.set(W("w"), str(int(int(c.get(W("w"), "0")) * ratio)))
            for tc in tbl.iter(W("tc")):
                tcw = tc.find(f"{W('tcPr')}/{W('tcW')}")
                if tcw is not None and int(tcw.get(W("w"), "0")) > 0:
                    tcw.set(W("w"), str(int(int(tcw.get(W("w"), "0")) * ratio)))


def _build_textbox_paragraph(attrs, content, z_order):
    """中身を浮動テキストボックスに包んだ段落 (w:p) を作る。"""
    width = int(attrs.get("width", "0"))
    height = int(attrs.get("height", "0"))
    pos_x = int(attrs.get("pos-x", "0"))
    pos_y = int(attrs.get("pos-y", "0"))
    anchor_h = attrs.get("anchor-h", "page")
    anchor_v = attrs.get("anchor-v", "page")
    wrap = attrs.get("wrap", "tight")
    behind_val = "1" if attrs.get("behind", "false") == "true" else "0"

    l_ins, t_ins, r_ins, b_ins = 45720, 0, 45720, 0  # 内側余白 (EMU)
    _resize_content_to_width(content, max(0, width - l_ins - r_ins))

    anchor = etree.Element(WP("anchor"))
    for k, v in (("distT", "0"), ("distB", "0"), ("distL", "114300"), ("distR", "114300"),
                 ("simplePos", "0"), ("relativeHeight", str(251659776 + z_order * 2)),
                 ("behindDoc", behind_val), ("locked", "0"), ("layoutInCell", "1"),
                 ("allowOverlap", "1")):
        anchor.set(k, v)

    sp = etree.SubElement(anchor, WP("simplePos"))
    sp.set("x", "0")
    sp.set("y", "0")
    ph = etree.SubElement(anchor, WP("positionH"))
    ph.set("relativeFrom", anchor_h)
    etree.SubElement(ph, WP("posOffset")).text = str(pos_x)
    pv = etree.SubElement(anchor, WP("positionV"))
    pv.set("relativeFrom", anchor_v)
    etree.SubElement(pv, WP("posOffset")).text = str(pos_y)
    ext = etree.SubElement(anchor, WP("extent"))
    ext.set("cx", str(width))
    ext.set("cy", str(height))
    ee = etree.SubElement(anchor, WP("effectExtent"))
    for s in ("l", "t", "r", "b"):
        ee.set(s, "0")

    if wrap == "tight":
        wt = etree.SubElement(anchor, WP("wrapTight"))
        wt.set("wrapText", "bothSides")
        poly = etree.SubElement(wt, WP("wrapPolygon"))
        poly.set("edited", "0")
        for idx, (x, y) in enumerate([(0, 0), (0, 21600), (21600, 21600), (21600, 0), (0, 0)]):
            pt = etree.SubElement(poly, WP("start") if idx == 0 else WP("lineTo"))
            pt.set("x", str(x))
            pt.set("y", str(y))
    elif wrap == "square":
        etree.SubElement(anchor, WP("wrapSquare")).set("wrapText", "bothSides")
    else:
        etree.SubElement(anchor, WP("wrapNone"))

    dp = etree.SubElement(anchor, WP("docPr"))
    dp.set("id", str(1000 + z_order))
    dp.set("name", f"TextBox {z_order + 1}")
    page = attrs.get("page", "")
    if page:
        dp.set("data-page", page)
    cnv = etree.SubElement(anchor, WP("cNvGraphicFramePr"))
    etree.SubElement(cnv, A("graphicFrameLocks"))

    graphic = etree.SubElement(anchor, A("graphic"))
    gd = etree.SubElement(graphic, A("graphicData"))
    gd.set("uri", NS["wps"])
    wsp = etree.SubElement(gd, WPS("wsp"))
    cnvsp = etree.SubElement(wsp, WPS("cNvSpPr"))
    cnvsp.set("txBox", "1")
    etree.SubElement(cnvsp, A("spLocks"))
    sppr = etree.SubElement(wsp, WPS("spPr"))
    xfrm = etree.SubElement(sppr, A("xfrm"))
    off = etree.SubElement(xfrm, A("off"))
    off.set("x", "0")
    off.set("y", "0")
    aext = etree.SubElement(xfrm, A("ext"))
    aext.set("cx", str(width))
    aext.set("cy", str(height))
    pgeom = etree.SubElement(sppr, A("prstGeom"))
    pgeom.set("prst", "rect")
    etree.SubElement(pgeom, A("avLst"))
    sfill = etree.SubElement(sppr, A("solidFill"))
    sysclr = etree.SubElement(sfill, A("sysClr"))
    sysclr.set("val", "window")
    sysclr.set("lastClr", "FFFFFF")
    ln = etree.SubElement(sppr, A("ln"))
    ln.set("w", "6350")
    etree.SubElement(ln, A("noFill"))

    txbx = etree.SubElement(wsp, WPS("txbx"))
    txbxc = etree.SubElement(txbx, W("txbxContent"))
    for elem in content:
        txbxc.append(elem)

    valign = attrs.get("valign", "top")
    bpr = etree.SubElement(wsp, WPS("bodyPr"))
    bpr.set("wrap", "square")
    bpr.set("anchor", "b" if valign == "bottom" else "t")
    bpr.set("lIns", str(l_ins))
    bpr.set("tIns", str(t_ins))
    bpr.set("rIns", str(r_ins))
    bpr.set("bIns", str(b_ins))

    # アンカー段落自体は高さ 0 に潰し、本文の行送りを乱さない
    p = etree.Element(W("p"))
    ppr = etree.SubElement(p, W("pPr"))
    spacing = etree.SubElement(ppr, W("spacing"))
    spacing.set(W("line"), "1")
    spacing.set(W("lineRule"), "exact")
    spacing.set(W("before"), "0")
    spacing.set(W("after"), "0")
    r = etree.SubElement(p, W("r"))
    rpr = etree.SubElement(r, W("rPr"))
    etree.SubElement(rpr, W("sz")).set(W("val"), "2")
    drawing = etree.SubElement(r, W("drawing"))
    drawing.append(anchor)
    return p


def wrap_textboxes(root, no_relocate=False):
    """body 直下の TEXTBOX_START..END 区間をテキストボックス段落へ置換する。"""
    body = root.find(W("body"))
    if body is None:
        return 0
    children = list(body)

    regions = []
    i = 0
    while i < len(children):
        child = children[i]
        if _is_marker(child) and _marker_text(child).startswith("TEXTBOX_START:"):
            attrs = _parse_textbox_attrs(_marker_text(child))
            start = i
            content = []
            i += 1
            while i < len(children):
                if _is_marker(children[i], "TEXTBOX_END"):
                    regions.append((start, i, attrs, content))
                    break
                content.append(children[i])
                i += 1
        i += 1

    if not regions:
        return 0

    # 末尾の region から処理してインデックスのずれを避ける
    for z, (start, end, attrs, content) in enumerate(reversed(regions)):
        actual_z = len(regions) - 1 - z
        for j in range(end, start - 1, -1):
            body.remove(children[j])
        tb_para = _build_textbox_paragraph(attrs, content, actual_z)
        body.insert(start, tb_para)
        children = list(body)

    if not no_relocate:
        _relocate_textbox_by_page(root)

    # textbox があるので mc:Ignorable を立てる (旧コンシューマは wps/wp14 を無視)
    ig = root.get(MC_IGNORABLE)
    existing = ig.split() if ig else []
    for n in ("wps", "wp14"):
        if n not in existing:
            existing.append(n)
    root.set(MC_IGNORABLE, " ".join(existing))
    return len(regions)


def _relocate_textbox_by_page(root):
    """page 属性つきテキストボックスを目標ページ位置へ概算移動する (best-effort)。

    実際のページ送りはレンダリングしないと分からないため、本文段落数からページ境界を
    見積もって近い位置へアンカー段落を移す。アンカーは relativeFrom="page" なので、
    アンカー段落が載るページに浮動表示される。
    """
    body = root.find(W("body"))
    if body is None:
        return
    children = list(body)

    body_start = 0
    for i, child in enumerate(children):
        if child.tag == W("p"):
            sect = child.find(f"{W('pPr')}/{W('sectPr')}")
            if sect is not None:
                body_start = i + 1
                break
    body_end = len(children)
    for i in range(len(children) - 1, body_start - 1, -1):
        if children[i].tag == W("sectPr"):
            body_end = i
            break

    header_para_count = sum(1 for i in range(body_start) if children[i].tag == W("p"))

    body_paras = []
    for i in range(body_start, body_end):
        if children[i].tag == W("p") and children[i].find(f".//{WP('anchor')}") is None:
            body_paras.append(i)
    if not body_paras:
        return

    page_breaks = [body_paras[0]]
    for idx in body_paras:
        for br in children[idx].iter(W("br")):
            if br.get(W("type")) == "page":
                page_breaks.append(idx)
                break

    textboxes = []
    max_page = 1
    for i, child in enumerate(children):
        if child.tag != W("p"):
            continue
        anchor = child.find(f".//{WP('anchor')}")
        if anchor is None:
            continue
        docpr = anchor.find(WP("docPr"))
        if docpr is None or "TextBox" not in docpr.get("name", ""):
            continue
        textboxes.append((i, child))
        page_str = docpr.get("data-page", "")
        if page_str.isdigit():
            max_page = max(max_page, int(page_str))
    if not textboxes:
        return

    page_offset = 2 if (body_start > 0 and header_para_count > 2) else 0
    num_pages = max(max_page + page_offset, len(page_breaks))
    if len(page_breaks) < num_pages and len(body_paras) > 1:
        seg = max(1, len(body_paras) // num_pages)
        page_breaks = [body_paras[min(p * seg, len(body_paras) - 1)] for p in range(num_pages)]
    elif len(page_breaks) < 2:
        page_breaks.append(body_paras[len(body_paras) // 2])

    moves = []
    for orig_idx, para in textboxes:
        docpr = para.find(f".//{WP('docPr')}")
        page_str = docpr.get("data-page", "") if docpr is not None else ""
        if not page_str.isdigit():
            continue
        target_page = int(page_str)
        if target_page < 1:
            continue
        eff = min(target_page + page_offset, len(page_breaks))
        target_idx = page_breaks[eff - 1] if eff <= len(page_breaks) else page_breaks[-1]
        if orig_idx != target_idx:
            moves.append((orig_idx, target_idx, para))

    moves.sort(key=lambda x: x[0], reverse=True)
    for _orig, target_idx, para in moves:
        body.remove(para)
        cur = list(body)
        body.insert(min(target_idx, len(cur)), para)


# =====================================================================
# エントリポイント
# =====================================================================

def drop_line_numbers(root):
    """本文 sectPr の w:lnNumType を落として行番号を消す。

    行番号は「査読者が本文の位置を指し示すため」の体裁なので、カバーレターのような本文以外の
    文書には要らない。`build.sh` は main.md / revise-report.md / cover-letter.md を**同じ
    reference.docx** で変換するため、放っておくとカバーレターにも連続行番号が付く (実測)。

    体裁は reference.docx に焼き込む設計なので、本来は「行番号なしの reference.docx」を別に
    持つのが筋だが、それは雑誌ごとに 2 つ目の binary を git に置くことになる。行番号の指定は
    sectPr の子要素 1 個 (`w:lnNumType`) なので、**焼き込み済みの体裁から 1 要素だけ外す**
    ほうが構造に手を入れずに済む (雑誌プロファイルの構造に手を入れる改修が要らない)。
    ページ番号 (フッタの PAGE フィールド) は自然なので残す。

    返り値: 落とした個数。
    """
    n = 0
    for sect in root.iter(W("sectPr")):
        for ln in sect.findall(W("lnNumType")):
            sect.remove(ln)
            n += 1
    return n


def process_docx(docx_path, source_md=None, resource_path=None, embed_svg=True,
                 no_relocate=False, image_manifest=None, no_line_numbers=False):
    """docx を読み、罫線・SVG 埋込・テキストボックスを適用して上書き保存する。"""
    resource_path = resource_path or ["."]
    with zipfile.ZipFile(docx_path, "r") as zin:
        parts = {item.filename: zin.read(item.filename) for item in zin.infolist()}

    parser = etree.XMLParser(remove_blank_text=False)
    root = etree.fromstring(parts["word/document.xml"], parser)
    root = ensure_root_namespaces(root)

    apply_table_borders(root)

    n_svg = 0
    if embed_svg and (source_md or image_manifest):
        n_svg = embed_svg_native(root, parts, source_md, resource_path, image_manifest)

    n_tb = wrap_textboxes(root, no_relocate=no_relocate)

    n_ln = drop_line_numbers(root) if no_line_numbers else 0

    parts["word/document.xml"] = etree.tostring(
        root, xml_declaration=True, encoding="UTF-8", standalone=True
    )

    with zipfile.ZipFile(docx_path, "w", zipfile.ZIP_DEFLATED) as zout:
        for name, data in parts.items():
            zout.writestr(name, data)

    extra = f" / 行番号除去 {n_ln}" if no_line_numbers else ""
    print(f"後処理 完了: {docx_path} (SVG 埋込 {n_svg} / textbox {n_tb}{extra})")


def _parse_args(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("docx", help="後処理する docx")
    p.add_argument("--source", help="原稿 main.md (SVG 埋込のキャプション照合・経路抽出に使う)")
    p.add_argument("--image-manifest", help="generic-style.lua が出す画像マニフェスト (src<TAB>caption)")
    p.add_argument("--resource-path", default=".", help="図解決パス (コロン区切り。pandoc と同じ順)")
    p.add_argument("--no-embed-svg", action="store_true", help="ネイティブ SVG 埋込をしない")
    p.add_argument("--no-relocate", action="store_true", help="textbox の page 配置移動をしない")
    return p.parse_args(argv)


def main(argv=None):
    args = _parse_args(argv)
    process_docx(
        args.docx,
        source_md=args.source,
        resource_path=args.resource_path.split(":"),
        embed_svg=not args.no_embed_svg,
        no_relocate=args.no_relocate,
        image_manifest=args.image_manifest,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
