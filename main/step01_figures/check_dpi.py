#!/usr/bin/env python3
"""check_dpi.py — ラスタ図が目標 dpi を満たしているかの受入テスト (コンテナ内本体)。

`scripts/check-figures.sh` が driver。BioHealth Informatics は図に "a minimum of 300 dpi" を課すが、
**目視では画素数不足を検知できない** (Word 上では同じ大きさに表示され、印刷・組版で初めて粗さが出る)。
そこで SVG の物理サイズから期待画素数を計算し、生成済み PNG の IHDR (実画素数) と pHYs (物理解像度) を
1 件ずつ突き合わせる。

検査するもの:
  A) 図ツリー (--tree。既定 data/step01_figures/figs)
     A-1) `figs/**/*.svg` ごとに `<svg>.svg.png` を探し、
            - 実画素数 >= ceil(物理サイズ x 目標 dpi)
            - pHYs の dpi が目標 dpi と一致 (整数 px/m への丸め分は許容)
          を検査する。PNG が無ければ失敗 (step01 が生成するはずのもの)。
     A-2) **執筆者が直接置いた生ラスタ図** (figs/**/*.png|jpg|jpeg|tif|tiff。`*.svg.png` を除く) は
          svg_raster の生成経路を通らないので **300dpi の保証対象外**である。元 SVG が無く期待画素数を
          出せないため、実画素数と pHYs を読んで**注意として報告する** (終了コードは変えない)。
          `*.svg` だけを走査すると、図ツリーに写真があっても「合格: N 件すべてが 300dpi を
          満たしています」と表示してしまう — 実際の投稿原稿で解像度要件に引っかかりやすいのは
          線画ではなく**写真**であり、いちばん危ない図が検査から漏れる。
  B) 分離出力した図 (--figures-dir。例 data/output/bhi/figures)
     ラスタ図ごとに pHYs を読み、目標 dpi と一致するかを検査する。ここには元 SVG が無いので
     画素数の期待値は出せず、**pHYs と実寸法の報告に留める** (A で経路が保証されている前提)。
     SVG から生成した図は不合格判定、原寸複製された生ラスタ図は注意扱いとする
     (走査対象は 5 拡張子 — 原寸複製は元の拡張子を保つので、`*.png` だけを見ると
     `.jpg` / `.tif` がどちらのモードでも一度も検査されない)。
  B-2) **pptx 図** (--figures-dir の `*.pptx`。ベクター提出)
     書庫を開いて次を検査する:
       - スライドの `a:blip` に SVG 拡張 (`a:ext@uri` + `asvg:svgBlip@r:embed`) が正しい位置にあること
       - **その関係 ID が解決でき、参照先が書庫内に実在する `.svg` であること**
         (**ベクターが届く経路になっているかの検査**)
       - **`a:blip@r:embed` が指す PNG が書庫内に実在し**、その pHYs が目標 dpi を満たすこと
       - **`ppt/presentation.xml` からそのスライドへ到達できること**

     太字の 3 点が要るのは、
     「rId が rels に在るか」と「ppt/media のどこかに .svg が在るか」を**別々に**見るだけでは、
     `asvg:svgBlip` の参照先を PNG に付け替えた pptx (= ベクターが 1 バイトも届かない) を
     `[OK] ベクター SVG 同梱` と表示してしまうためである。またスライドを書庫から直接読むと、
     プレゼンテーションから到達できない pptx (開くと白紙) も合格になる。どちらも実測で確認した。
     PNG フォールバックを検査するのは、**SVG のネイティブ表示に対応するのが Microsoft 365 /
     Office 2019 以降だけ**で、買い切り版 Office 2016 と投稿系の査読用 PDF 変換では PNG 側が
     描画されるためである (docs/journal-bhi.md §5.1.3 リスク 1)。
     案 A (執筆者が PowerPoint で作った図の無変換コピー) は中身がテンプレの検査対象外なので、
     SVG 拡張が無くても**不合格にせず注意**にする。
  C) **Word / PowerPoint でだけ崩れる SVG の疑い** (図ツリーの `*.svg` が対象)
     解像度とは別の「注意」として出す。どれも実際の投稿原稿で起き、体裁の計測
     (A4・余白・行番号) でも本テストの画素数の検算でも見つからなかったもの
     (SVG としては正しく、ブラウザでも PNG フォールバックでも正常に見える):
       - 1 つの SVG に `<g class='svglite'>` が 2 つ以上 → Word が**文字だけ**を片方のパネルの
         位置に寄せて描く (図形は正しい位置のまま。Windows 実機で 5 通り試して確認された条件)
       - 1 つの SVG の中で `id` が重複 → `clipPath` の参照先を取り違え、片方のパネルが
         誤った範囲で切り取られる (svglite の `id` は座標から作るので、寸法を揃えて連結すると一致する)
       - 塗り・線の色が `hsl()` / `hsla()` → Word も PowerPoint も**その図形を黒く塗る**
         (Microsoft 365 で実測。CSS のクラスで塗っても `fill` 属性に書いても同じ)。Mermaid でテーマの色を
         変えるとサブグラフの枠などがこの形で出る。本テンプレの Mermaid 経路 (`docker/mermaid/convert.sh`)
         は 16 進に直してから出すので、ここで掛かるのは**別の場所で作って置いた SVG**である
     **確認されていない条件 (入れ子 `<svg>` だけ、小数の `rgb()` だけ、など) は検出しない**。

終了コード: 0 = 全件合格 / 1 = 不合格あり / 2 = 対象が 1 件も無い (テストが空振りした)
  注意 (保証対象外の図・Word / PowerPoint でだけ崩れる疑い) は終了コードを変えない。合格表示の最終行に件数を必ず出す。
"""

import argparse
import math
import re
import xml.etree.ElementTree as ET
from collections import Counter
import posixpath
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "00_setup" / "lib"))
import svg_raster  # noqa: E402
import journal_profile  # noqa: E402
import ooxml_svg  # noqa: E402

# 執筆者が直接置ける生ラスタ図の拡張子 (process_figures.py の RASTER_SUFFIXES と揃える)
RASTER_SUFFIXES = (".png", ".jpg", ".jpeg", ".tif", ".tiff")
# 図ツリーに置かれるが「原稿の図」ではない派生物。
#   *.outline.svg = step05 が figures.pptx.text_to_path=true のときに作る提出用 SVG。
# これらは step01 の生成物ではないので代替表示 PNG (`<名前>.svg.png`) を持たない。
# 図ツリーの `*.svg` を無条件に「原稿の図」とみなすと、text_to_path を有効にしたとき
# **必ず不合格 (終了コード 1)** になる (提出物自体は正しく、検査だけが誤る)。
# しかも text_to_path はフォント崩れが起きたときの逃げ道なので、いちばん切迫した場面で赤くなる。
#
# step05 は派生物を `data/step05_package/` へ出すので、通常の運用では図ツリーに現れない。
# 本除外を残すのは、**古い版の step05 が図ツリーに残した残骸**が `--skip-figures` で
# 消されずに残っている場合に、検査が誤って赤くなるのを防ぐため (figures.sh は毎回 figs/ を
# 作り直すので、図前処理を走らせれば残骸は消える)。
DERIVED_SVG_SUFFIXES = (".outline.svg",)
# pHYs を持ちうるのは PNG だけ。JPEG/TIFF は本モジュールでは解像度を機械判定できない
PHYS_READABLE = (".png",)

# pHYs は「1 メートルあたりの画素数 (整数)」なので dpi を厳密には表せない。svg_raster は
# 切り上げて書く (300dpi -> 11812 px/m -> 300.02 dpi) — 切り捨てで読む実装 (pandoc がそう読む)
# でも目標を下回らせないため。したがって判定は「目標を下回らない かつ 1px/m 分を超えて過大でない」。
DPI_UNDER = 0.001      # 下回りは実質ゼロ許容 (300dpi 未満は規定違反になりうる)
DPI_OVER = 0.1         # 切り上げ 1px/m 分の過大 (300dpi で +0.03) を許容する


def _dpi_ok(phys, dpi):
    """pHYs から読んだ (dpi_x, dpi_y) が目標を満たすか。下回りは不可・僅かな過大は可。"""
    return all(dpi - DPI_UNDER <= v <= dpi + DPI_OVER for v in phys)


def _phys_note(png, dpi):
    """生ラスタ図の pHYs を「注意」の 1 行にする。"""
    act_w, act_h = svg_raster.png_pixel_size(png)
    state, value = svg_raster.read_png_phys(png)
    if state == "dpi":
        ok = "満たす" if _dpi_ok(value, dpi) else f"**{dpi}dpi を下回る**"
        return (f"{act_w}x{act_h} px / pHYs {value[0]:.2f}dpi ({ok})。"
                f"= {act_w / value[0]:.2f}x{act_h / value[1]:.2f} in で配置したときの解像度")
    if state == "unitless":
        # 「pHYs が無い」と混同させない
        return (f"{act_w}x{act_h} px / pHYs はあるが単位が『なし』({value[0]}:{value[1]} = 縦横比のみ) "
                "で解像度を表していない。配置幅から実効解像度を自分で確かめること")
    return (f"{act_w}x{act_h} px / pHYs (物理解像度) が無いため、何 dpi の画像かを機械判定できない。"
            f"配置幅で割った値が {dpi}dpi 以上になるかを自分で確かめること")


def check_raster_figures(paths, dpi, label_of):
    """生ラスタ図を「注意」として一覧にする。返り値 (件数, 注意メッセージ list)。

    300dpi 保証 (svg_raster) は svg→png 経路にしか掛からない。ここで扱うのは執筆者が直接置いた
    画像なので、ツール側で解像度を作り直すことはできない。**不合格にはせず**、見えるようにする。
    """
    notices = []
    checked = 0
    for p in paths:
        checked += 1
        rel = label_of(p)
        if p.suffix.lower() in PHYS_READABLE:
            notices.append(f"{rel}: {_phys_note(p, dpi)}")
        else:
            notices.append(
                f"{rel}: {p.suffix.lstrip('.').upper()} は本テストで解像度を読めない "
                f"(pHYs は PNG の仕組み)。{dpi}dpi 以上で書き出したかを執筆者が確かめること")
        print(f"  [注意] {rel}: {dpi}dpi 保証の対象外 (執筆者が直接置いたラスタ図)")
    return checked, notices


_SVG_COMPOSITION_ADVICE = ("多パネル図は作図側で 1 枚として出力し (R なら cowplot / patchwork などで"
                           "まとめてから 1 回だけ書き出す)、Word / PowerPoint で図を拡大して目視すること")


# 図形の塗り・線に効く性質だけを見る (Mermaid の既定テーマは図に描かれないツールチップの CSS に
# `background:hsl(…)` を持つので、background 系まで見ると誤検出になる)
_PAINT_PROPS = ("fill", "stroke", "stop-color", "flood-color", "lighting-color")
_RE_HSL_DECL = re.compile(r"(?<![\w-])(" + "|".join(_PAINT_PROPS) + r")\s*:\s*hsla?\(", re.I)
_RE_HSL_VALUE = re.compile(r"^\s*hsla?\(", re.I)


def svg_office_notes(svg):
    """Word / PowerPoint でだけ崩れる SVG の疑いを「注意」の文言の list で返す。

    見るのは**実機 (Word / PowerPoint) で確認された 3 条件だけ**である (モジュール冒頭の C)。
    どちらも描画を壊すのは Word / PowerPoint の側で、SVG としては正しく、rsvg-convert の PNG も
    ブラウザの表示も正常に見える — つまり**ここで知らせないと気づく機会が校正刷りまで無い**。
    ただし壊れ方は Office の版によって変わりうるので不合格にはしない (終了コードは変えない)。
    解析できない SVG は何も返さない (寸法の解析側で失敗として出る)。
    """
    try:
        root = ET.parse(svg).getroot()
    except (ET.ParseError, OSError):
        return []
    n_svglite = 0
    ids = Counter()
    id_tags = {}
    n_hsl = 0
    for el in root.iter():
        tag = el.tag.rsplit("}", 1)[-1] if isinstance(el.tag, str) else ""
        if tag == "g" and "svglite" in (el.get("class") or "").split():
            n_svglite += 1
        if tag == "style":
            n_hsl += len(_RE_HSL_DECL.findall(el.text or ""))
        n_hsl += sum(1 for a in _PAINT_PROPS if _RE_HSL_VALUE.match(el.get(a) or ""))
        n_hsl += len(_RE_HSL_DECL.findall(el.get("style") or ""))
        ident = el.get("id")
        if ident is not None:
            ids[ident] += 1
            id_tags.setdefault(ident, set()).add(tag)
    notes = []
    if n_svglite >= 2:
        notes.append(
            f"1 つの SVG に svglite の出力が {n_svglite} 個入っている (`<g class='svglite'>` が "
            f"{n_svglite} 個)。Word はこの形の SVG で**文字だけを片方のパネルの位置に寄せて描く**"
            "ことが実機で確認されている (図形は正しい位置のまま。`<g transform>` / 入れ子 `<svg>` / "
            f"CSS の統合のどれでも直らない)。{_SVG_COMPOSITION_ADVICE}")
    dups = sorted((n, i) for i, n in ids.items() if n > 1)[::-1]
    if dups:
        shown = ", ".join(f"`{i}` ×{n} ({'/'.join(sorted(id_tags[i]))})" for n, i in dups[:3])
        more = f" ほか {len(dups) - 3} 種" if len(dups) > 3 else ""
        notes.append(
            f"SVG の中で id が重複している ({shown}{more})。SVG を連結すると起きやすく "
            "(svglite の clipPath の id は座標から作るので、パネルの寸法を揃えると一致する)、"
            "参照先を取り違えて**片方のパネルが誤った範囲で切り取られる**ことがある。"
            f"{_SVG_COMPOSITION_ADVICE}")
    if n_hsl:
        notes.append(
            f"塗り・線の色が hsl() で書かれている ({n_hsl} 箇所)。Word も PowerPoint も**この色の図形を"
            "黒く塗る**ことが実機で確認されている (Microsoft 365。CSS のクラスで塗っても fill 属性に"
            "書いても同じ)。Mermaid でテーマの色を変えるとサブグラフの枠などがこの形で出る。"
            "色を 16 進 (#rrggbb) で書き直すか、Mermaid なら .mmd を src/figs/mermaid/ に置いて"
            "本テンプレの経路で作り直すこと (16 進に直してから出す。"
            "単独で直すなら node docker/mermaid/postprocess-svg.js <file.svg>)")
    return notes


def check_tree(tree, dpi):
    """図ツリーの *.svg と *.svg.png を突き合わせる。

    返り値 (合格数, 失敗メッセージ list, 生ラスタ図の件数, 注意 list, 除外した派生物の件数,
    Word / PowerPoint でだけ崩れる疑いの注意 list)。
    """
    failures = []
    composition = []
    checked = 0
    skipped_derived = 0
    for svg in sorted(Path(tree).rglob("*.svg")):
        if not svg.is_file():
            continue
        if svg.name.endswith(DERIVED_SVG_SUFFIXES):
            # step05 が作った提出用の派生物。原稿の図ではないので
            # 代替表示 PNG を要求しない。**黙って飛ばさず件数を合格表示に出す**
            # (合格表示が実際の保証より強くならないように)。
            skipped_derived += 1
            continue
        png = Path(str(svg) + ".png")
        rel = svg.relative_to(tree)
        # 解像度の判定とは独立に見る (PNG の有無や画素数の合否に左右されない)
        for note in svg_office_notes(svg):
            composition.append(f"{rel}: {note}")
            print(f"  [注意] {rel}: Word / PowerPoint でだけ崩れる疑い (下の注意を参照)")
        if not png.is_file():
            failures.append(f"{rel}: PNG フォールバック {png.name} がありません "
                            "(step01_figures が生成するはずのファイル)")
            continue
        checked += 1
        try:
            info = svg_raster.svg_physical_size(svg)
        except svg_raster.SvgRasterError as exc:
            failures.append(f"{rel}: SVG の寸法を解析できません ({exc})")
            continue
        want_w = max(1, math.ceil(info["width_in"] * dpi))
        want_h = max(1, math.ceil(info["height_in"] * dpi))
        act_w, act_h = svg_raster.png_pixel_size(png)
        state, phys = svg_raster.read_png_phys(png)
        detail = (f"{info['raw']} [{info['basis']}] = "
                  f"{info['width_in']:.3f}x{info['height_in']:.3f} in")
        if act_w < want_w or act_h < want_h:
            failures.append(
                f"{rel}: 画素数不足 実測 {act_w}x{act_h} px < 期待 {want_w}x{want_h} px "
                f"({dpi}dpi 相当。{detail})")
            continue
        # 「pHYs が無い」と「単位がメートル以外」を区別する (対処が違う)
        if state == "missing":
            failures.append(f"{rel}: PNG に pHYs (物理解像度) がありません "
                            f"({dpi}dpi と認識されません)")
            continue
        if state == "unitless":
            failures.append(
                f"{rel}: PNG に pHYs はありますが単位が『なし』({phys[0]}:{phys[1]} = 縦横比のみ) で、"
                f"解像度を表していません ({dpi}dpi と認識されません)")
            continue
        if not _dpi_ok(phys, dpi):
            failures.append(
                f"{rel}: pHYs の解像度が目標と違います 実測 {phys[0]:.2f}x{phys[1]:.2f} dpi "
                f"!= 目標 {dpi} dpi")
            continue
        print(f"  [OK] {rel}: {act_w}x{act_h} px / pHYs {phys[0]:.2f}dpi  ({detail})")

    # A-2) 執筆者が直接置いた生ラスタ図
    raw_rasters = sorted(
        p for suf in RASTER_SUFFIXES for p in Path(tree).rglob(f"*{suf}")
        if p.is_file() and not p.name.endswith(".svg.png")
    )
    n_raw, notices = check_raster_figures(
        raw_rasters, dpi, lambda p: str(p.relative_to(tree)))
    return checked, failures, n_raw, notices, skipped_derived, composition


def _resolve_part(target, from_part):
    """rels の `Target` を書庫内の絶対パスへ解決する。

    `from_part` は関係の持ち主のパート (例 `ppt/slides/slide1.xml`)。
    `Target` はそこからの相対パス (`../media/figure.svg`) か、`/` 始まりの絶対パスである。
    """
    if target.startswith("/"):
        return target.lstrip("/")
    return posixpath.normpath(posixpath.join(posixpath.dirname(from_part), target))


def _svg_ext_target(slide_xml, rels_xml):
    """スライドの `a:blip` から SVG 拡張を辿り、参照先を返す。

    返り値 (state, detail):
      ('ok', dict)        : `a:ext@uri` + `asvg:svgBlip@r:embed` が在り、rId が解決できた。
                            dict は svg_target / svg_external / png_rid / png_target /
                            png_external を持つ
      ('no-blip', None)   : `a:blip` が無い (図が画像として載っていない = 案 A のシェイプ図など)
      ('no-ext', None)    : `a:blip` はあるが SVG 拡張が無い (= PNG しか届かない)
      ('bad-rid', rid)    : 拡張はあるが rId が rels に無い (壊れている)

    **要素名を自分で検索し直す形の検査にしない**。判定に使う URI と要素名は
    `ooxml_svg` の 1 か所だけに置き、生成側 (svg_pptx) も検査側 (ここ) もそれを参照する。

    関係 ID が rels に在ることだけを確かめて参照先を使わないと、「その関係 ID が実際に SVG を
    指しているか」を確かめないことになり、`asvg:svgBlip` の参照先を PNG に付け替えた
    pptx (= ベクターが 1 バイトも届かない) が `[OK] ベクター SVG 同梱` と表示される (実測)。
    要素名の誤記 (`svgBlob`) で黙って非ベクターになるのを防ぐための検査自身が、同じ形の失敗を
    見逃すことになる。参照先の実体まで確かめられるよう、必要な情報を辞書で返す。
    """
    from lxml import etree
    slide = etree.fromstring(slide_xml)
    blip = slide.find(f".//{ooxml_svg.A('blip')}")
    if blip is None:
        return "no-blip", None
    svg_blip = blip.find(
        f"{ooxml_svg.A('extLst')}/{ooxml_svg.A('ext')}[@uri='{ooxml_svg.SVG_EXT_URI}']/"
        f"{ooxml_svg.ASVG('svgBlip')}")
    if svg_blip is None:
        return "no-ext", None
    svg_rid = svg_blip.get(ooxml_svg.R("embed"))
    png_rid = blip.get(ooxml_svg.R("embed"))       # 代替表示 PNG (SVG 非対応環境が見る本体)
    rels = etree.fromstring(rels_xml)
    found = {rel.get("Id"): (rel.get("Target") or "", rel.get("TargetMode") == "External")
             for rel in rels}
    if svg_rid not in found:
        return "bad-rid", svg_rid
    svg_target, svg_external = found[svg_rid]
    png_target, png_external = found.get(png_rid, (None, False))
    return "ok", {
        "svg_rid": svg_rid, "svg_target": svg_target, "svg_external": svg_external,
        "png_rid": png_rid, "png_target": png_target, "png_external": png_external,
    }


def _slide_is_reachable(pptx_names, read, slide_name):
    """`ppt/presentation.xml` からそのスライドへ到達できるかを見る。

    返り値: 到達できれば None、できなければ理由の文字列。

    生成側が「1 枚目のスライドを指す関係 ID」を固定値で書いていたため、骨格の並びが変わると
    **プレゼンテーションからスライドへ到達できない pptx** ができうる。そのとき書庫にスライドの
    ファイル自体は在るので、スライドを直接読むだけの検査は通ってしまい、LibreOffice も
    「読み込み成功」で白紙の PDF を出す (実測)。ここで presentation.xml 側から辿り直す。
    """
    from lxml import etree
    pres, pres_rels = "ppt/presentation.xml", "ppt/_rels/presentation.xml.rels"
    if pres not in pptx_names or pres_rels not in pptx_names:
        return f"{pres} か {pres_rels} がありません"
    root = etree.fromstring(read(pres))
    rels = {rel.get("Id"): (rel.get("Target") or "") for rel in etree.fromstring(read(pres_rels))}
    P_NS = "http://schemas.openxmlformats.org/presentationml/2006/main"
    ids = [sld.get(ooxml_svg.R("id")) for sld in root.iter(f"{{{P_NS}}}sldId")]
    if not ids:
        return "p:sldIdLst にスライドが 1 枚も登録されていません"
    reached = set()
    for rid in ids:
        if rid not in rels:
            return (f"p:sldId が参照する関係 ID '{rid}' が {pres_rels} に定義されていません "
                    "(スライドへ到達できないため、開いても白紙になります)")
        reached.add(_resolve_part(rels[rid], pres))
    if slide_name not in reached:
        return (f"{slide_name} が p:sldIdLst から参照されていません "
                f"(登録されているのは {sorted(reached)})")
    return None


def check_pptx_figure(path, dpi):
    """pptx 図 1 件を検査する。返り値 (合格したか, 失敗 list, 注意 list)。"""
    rel = Path(path).name
    failures, notices = [], []
    try:
        with zipfile.ZipFile(path) as z:
            names = z.namelist()
            slides = sorted(n for n in names
                            if n.startswith("ppt/slides/slide") and n.endswith(".xml"))
            media = sorted(n for n in names if n.startswith("ppt/media/"))
            if len(slides) != 1:
                failures.append(f"{rel}: スライドが {len(slides)} 枚あります "
                                "(BHI は図ごとに 1 ファイル = 1 スライド)")
                return False, failures, notices
            rels_name = "ppt/slides/_rels/" + Path(slides[0]).name + ".rels"
            state, detail = _svg_ext_target(
                z.read(slides[0]), z.read(rels_name) if rels_name in names else b"<r/>")

            if state == "bad-rid":
                failures.append(f"{rel}: SVG 拡張 (asvg:svgBlip) の関係 ID '{detail}' が "
                                f"{rels_name} に定義されていません (書庫が壊れています)")
                return False, failures, notices
            if state in ("no-blip", "no-ext"):
                # 案 A (執筆者が PowerPoint で仕上げた図) はここに来る。中身は検査対象外。
                why = ("スライドに画像が無い (ネイティブシェイプで描かれている可能性)"
                       if state == "no-blip" else "画像はあるが SVG 拡張が付いていない")
                notices.append(
                    f"{rel}: {why}。**テンプレートが生成した pptx ではない**と考えられます "
                    "(案 A = 一次ソースの無変換コピー)。ベクターかどうか・解像度が足りるかは "
                    "PowerPoint 上で執筆者が確認してください")
                print(f"  [注意] {rel}: 中身がテンプレートの検査対象外 (案 A の可能性)")
                return None, failures, notices

            # --- state == "ok"。ここから先は参照先の実体の検査 ---
            # 「rId が rels に在るか」と「ppt/media のどこかに .svg が在るか」を別々に見るだけでは、
            # 両者が同じものを指しているかを確かめられない
            # (svgBlip の参照先を PNG に付け替えた pptx が合格してしまう。実測)。
            if detail["svg_external"]:
                failures.append(
                    f"{rel}: SVG 拡張の参照先 '{detail['svg_target']}' が書庫の外 "
                    "(TargetMode=External) を指しています。提出先では解決できずベクターが届きません")
                return False, failures, notices
            svg_part = _resolve_part(detail["svg_target"], slides[0])
            if svg_part not in names:
                failures.append(
                    f"{rel}: SVG 拡張が参照する '{svg_part}' が書庫にありません "
                    "(関係定義だけが残っている壊れた状態です)")
                return False, failures, notices
            if not svg_part.lower().endswith(".svg"):
                failures.append(
                    f"{rel}: SVG 拡張 (asvg:svgBlip) の参照先が SVG ではありません ({svg_part})。"
                    "**ベクターは 1 バイトも届かず、開いた人には代替表示の画像しか見えません** "
                    "(ファイルは壊れないまま黙って非ベクターになる種類の不具合です)")
                return False, failures, notices

            # 代替表示 PNG も「a:blip が実際に指しているもの」を読む (ppt/media の 1 件目ではなく)
            if not detail["png_rid"] or detail["png_target"] is None:
                failures.append(
                    f"{rel}: a:blip に代替表示 PNG の参照 (r:embed) がありません。"
                    "SVG 非対応環境 (買い切り版 Office 2016 / 査読用 PDF 変換) で図が出ません")
                return False, failures, notices
            if detail["png_external"]:
                failures.append(
                    f"{rel}: 代替表示 PNG の参照先 '{detail['png_target']}' が書庫の外を指しています")
                return False, failures, notices
            png_part = _resolve_part(detail["png_target"], slides[0])
            if png_part not in names:
                failures.append(
                    f"{rel}: 代替表示 PNG が参照する '{png_part}' が書庫にありません")
                return False, failures, notices

            # プレゼンテーション本体からこのスライドへ到達できるか
            unreachable = _slide_is_reachable(set(names), z.read, slides[0])
            if unreachable:
                failures.append(f"{rel}: {unreachable}")
                return False, failures, notices

            png_bytes = z.read(png_part)
    except (zipfile.BadZipFile, KeyError, OSError) as exc:
        failures.append(f"{rel}: pptx として読めません ({exc})")
        return False, failures, notices

    # 代替表示 PNG の pHYs を読む (バイト列のまま解析する。
    # 提出ディレクトリの中に一時ファイルを書いて読んでから消す方式だと、
    # 強制終了したときに出所不明の PNG が提出物一式に残りうる)
    try:
        act_w, act_h = svg_raster.png_pixel_size(png_bytes)
        state_p, phys = svg_raster.read_png_phys(png_bytes)
    except (svg_raster.SvgRasterError, OSError) as exc:
        failures.append(f"{rel}: 同梱 PNG の解像度を読めません ({exc})")
        return False, failures, notices

    if state_p != "dpi":
        failures.append(
            f"{rel}: 同梱 PNG フォールバックに pHYs (物理解像度) がありません "
            f"({dpi}dpi と認識されません)。SVG 非対応環境ではこの PNG が本体になります")
        return False, failures, notices
    if not _dpi_ok(phys, dpi):
        failures.append(f"{rel}: 同梱 PNG フォールバックの pHYs {phys[0]:.2f}x{phys[1]:.2f} dpi "
                        f"!= 目標 {dpi} dpi")
        return False, failures, notices
    # 「ppt/media のどこかに在る SVG」ではなく「拡張が実際に指している SVG」を出す
    print(f"  [OK] {rel}: SVG 拡張の参照先 = {svg_part} (ベクターが届く) + 代替表示 PNG "
          f"{act_w}x{act_h} px / pHYs {phys[0]:.2f}dpi")
    return True, failures, notices


def check_figures_dir(figures_dir, dpi):
    """分離出力した図 (figures/) の pHYs を検査する。

    返り値 (件数, 失敗メッセージ list, 注意件数, 注意メッセージ list)。
    SVG から生成した図は不合格判定、原寸複製された生ラスタ図 (pHYs 無し / PNG 以外) は注意扱い。
    """
    failures = []
    notices = []
    checked = 0
    n_raw = 0
    # pptx 図 (ベクター提出) は書庫を開いて構造と同梱 PNG の解像度まで見る
    for pptx in sorted(p for p in Path(figures_dir).glob("*.pptx") if p.is_file()):
        ok, f, nt = check_pptx_figure(pptx, dpi)
        failures += f
        notices += nt
        if ok is None:
            n_raw += 1        # 中身が検査対象外 (案 A) = 「保証できていない図」として数える
        elif ok:
            checked += 1
    files = sorted(p for suf in RASTER_SUFFIXES
                   for p in Path(figures_dir).glob(f"*{suf}") if p.is_file())
    for png in files:
        rel = png.name
        if png.suffix.lower() not in PHYS_READABLE:
            # 原寸複製は元の拡張子を保つ。JPEG/TIFF は pHYs を読めない
            n_raw += 1
            notices.append(f"{rel}: {png.suffix.lstrip('.').upper()} は本テストで解像度を読めない "
                           f"(pHYs は PNG の仕組み)。原寸複製された図の可能性が高い — "
                           f"{dpi}dpi 以上で書き出したかを執筆者が確かめること")
            print(f"  [注意] {rel}: 解像度を機械判定できない形式")
            continue
        act_w, act_h = svg_raster.png_pixel_size(png)
        state, phys = svg_raster.read_png_phys(png)
        if state != "dpi":
            # pHYs が無い / 単位が「なし」= svg_raster を通っていない = 原寸複製された生ラスタ図。
            # ツール側では直せないので不合格ではなく注意にする。
            n_raw += 1
            notices.append(f"{rel}: {_phys_note(png, dpi)} (dpi 保証の経路 (svg_raster) を通っていない = "
                           "執筆者が置いた図の原寸複製と考えられる)")
            print(f"  [注意] {rel}: {dpi}dpi 保証の対象外")
            continue
        checked += 1
        if not _dpi_ok(phys, dpi):
            failures.append(f"{rel}: pHYs {phys[0]:.2f}x{phys[1]:.2f} dpi != 目標 {dpi} dpi")
            continue
        print(f"  [OK] {rel}: {act_w}x{act_h} px / pHYs {phys[0]:.2f}dpi "
              f"(= {act_w / phys[0]:.2f}x{act_h / phys[1]:.2f} in で配置したとき {dpi}dpi)")
    return checked, failures, n_raw, notices


# =====================================================================
# 自己テスト: 「この検査に識別力があるか」を毎回確かめる
# =====================================================================

# 物理単位と文字を持つ最小の SVG。自己テストはこれを一時ディレクトリに書いて pptx を作る
# (リポジトリにバイナリの固定物を置かないため。固定物は生成器を変えたときに古くなり、
#  追随を忘れると検査が形骸化する)。
_SELF_TEST_SVG = """<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="60mm" height="30mm" viewBox="0 0 60 30">
  <rect x="1" y="1" width="58" height="28" fill="#eef" stroke="#446"/>
  <text x="6" y="18" font-family="sans-serif" font-size="6">self test</text>
</svg>
"""


def _corrupt_svg_ext_target(parts):
    """`asvg:svgBlip` の参照先を同梱 PNG に差し替える (= ベクターが 1 バイトも届かない)。"""
    slide = parts["ppt/slides/slide1.xml"].decode("utf-8")
    parts["ppt/slides/slide1.xml"] = slide.replace(
        '<asvg:svgBlip r:embed="rId3"/>', '<asvg:svgBlip r:embed="rId2"/>').encode("utf-8")
    return parts


def _corrupt_slide_unreachable(parts):
    """`p:sldId` が指す関係を消す (= プレゼンテーションからスライドへ到達できない)。"""
    import re
    rels = parts["ppt/_rels/presentation.xml.rels"].decode("utf-8")
    parts["ppt/_rels/presentation.xml.rels"] = re.sub(
        r'<Relationship[^>]*Target="slides/slide1\.xml"[^>]*/>', "", rels).encode("utf-8")
    return parts


_SELF_TEST_CASES = (
    ("正常に生成した pptx", None, True),
    ("SVG 拡張の参照先を同梱 PNG に差し替えた pptx", _corrupt_svg_ext_target, False),
    ("スライドへの関係を削除した pptx", _corrupt_slide_unreachable, False),
)


def run_self_test(dpi=300):
    """pptx 検査に識別力があるかを確かめる。返り値: 終了コード。

    **なぜ要るか**: 要素名を `svgBlob` のように書き間違えると Office が拡張を見つけられず、
    ファイルは壊れないまま**黙って非ベクター**になる。pptx 検査はそれを機械的に防ぐためのものだが、
    検査自身が「関係 ID が実在するか」しか見ておらず**参照先が SVG かを確かめていない**、
    ということも起こりうる (実測: ベクターが 1 バイトも届かない pptx が `[OK]` になった)。
    検査を直しただけでは同じことがまた起きるので、**検査が壊れた入力を本当に落とせるか**を
    毎回確かめられるようにする。

    リポジトリに壊した pptx を同梱する方式は採らない — 生成器を変えると固定物が古くなり、
    追随を忘れた時点で検査が形骸化する。**その場で現行の生成器に作らせて、その場で壊す。**
    """
    import shutil
    import tempfile
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "00_setup" / "lib"))
    import svg_pptx  # noqa: PLC0415

    print("== 受入テストの自己テスト (pptx 検査に識別力があるか) ==")
    ok = True
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        svg = tmp / "self-test.svg"
        svg.write_text(_SELF_TEST_SVG, encoding="utf-8")
        try:
            svg_pptx.build_figure_pptx(svg, tmp / "good.pptx", dpi=dpi, title="Figure 1")
        except (svg_pptx.SvgPptxError, svg_raster.SvgRasterError) as exc:
            print(f"エラー: 自己テスト用の pptx を作れませんでした ({exc})", file=sys.stderr)
            print("  pandoc と rsvg-convert が入ったコンテナ内で実行してください。", file=sys.stderr)
            return 2

        for label, corrupt, expect_pass in _SELF_TEST_CASES:
            target = tmp / ("good.pptx" if corrupt is None else "broken.pptx")
            if corrupt is not None:
                with zipfile.ZipFile(tmp / "good.pptx") as z:
                    parts = {n: z.read(n) for n in z.namelist()}
                parts = corrupt(parts)
                svg_pptx.write_pptx(target, parts)
            verdict, failures, _ = check_pptx_figure(target, dpi)
            passed = verdict is True
            good = passed == expect_pass
            ok = ok and good
            want = "合格" if expect_pass else "不合格"
            got = "合格" if passed else "不合格"
            mark = "期待どおり" if good else "★期待と違う"
            print(f"  [自己テスト] {label} -> {got} (期待 {want}。{mark})")
            if not passed and failures:
                print(f"      検出内容: {failures[0]}")
            if target.name == "broken.pptx":
                target.unlink(missing_ok=True)
        shutil.rmtree(tmp, ignore_errors=True)

    print("")
    if ok:
        print(f"== 自己テスト合格: {len(_SELF_TEST_CASES)} 件すべてで期待どおり判定した ==")
        print("  検査は「ベクターが届かない pptx」と「スライドへ到達できない pptx」を"
              "落とせる状態にある。")
        return 0
    print("== 自己テスト不合格: 検査が期待どおりに判定していない ==", file=sys.stderr)
    print("  pptx 検査の識別力が失われている。check_pptx_figure / _svg_ext_target を確認すること。",
          file=sys.stderr)
    return 1


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--tree", default=None,
                   help="図ツリー (既定 data/step01_figures/figs)。*.svg と *.svg.png を突合")
    p.add_argument("--figures-dir", default=None,
                   help="分離出力した図のディレクトリ (例 data/output/bhi/figures)。pHYs のみ検査")
    p.add_argument("--dpi", type=int, default=None, help="目標解像度 (既定 300)")
    # 目標 dpi を雑誌プロファイルから採れるようにする。300 固定だと、
    # figures.dpi=600 の誌の図を 300 の基準で「合格」と表示してしまう。
    p.add_argument("--journal", default=None,
                   help="雑誌プロファイル id。--dpi 未指定なら profile.figures.dpi を目標にする")
    p.add_argument("--article-type", default=None, help="記事種別 (--journal と併用)")
    # 検査そのものに識別力があるかを毎回確かめられるようにする
    p.add_argument("--self-test", action="store_true",
                   help="pptx 検査の識別力を確かめる (その場で pptx を作り、壊し、落とせるか見る)")
    args = p.parse_args(argv)

    if args.self_test:
        return run_self_test(args.dpi if args.dpi is not None else 300)

    # 目標 dpi の解決: --dpi > --journal の figures.dpi > 300 (どこから採ったかを 1 行表示する)
    if args.dpi is not None:
        dpi, dpi_src = args.dpi, "--dpi"
    elif args.journal:
        try:
            prof = journal_profile.load_resolved(args.journal, args.article_type)
        except SystemExit:
            raise
        except Exception as exc:                          # noqa: BLE001
            print(f"エラー: 雑誌プロファイル '{args.journal}' を読めません ({exc})", file=sys.stderr)
            return 2
        fig = prof.get("figures") or {}
        raw = fig.get("dpi") if isinstance(fig, dict) else None
        if raw is None:
            dpi, dpi_src = 300, f"既定 (--journal {args.journal} に figures.dpi が無い)"
        else:
            try:
                dpi = int(raw)
            except (TypeError, ValueError):
                print(f"エラー: profile.figures.dpi の値 '{raw}' が整数ではありません", file=sys.stderr)
                return 2
            if dpi <= 0:
                print(f"エラー: profile.figures.dpi の値 '{raw}' は正の整数で指定してください",
                      file=sys.stderr)
                return 2
            dpi_src = f"--journal {args.journal} の figures.dpi"
    else:
        dpi, dpi_src = 300, "既定 (--dpi も --journal も未指定)"
    args.dpi = dpi
    print(f"目標解像度: {dpi}dpi  (出所: {dpi_src})")

    tree = args.tree
    if tree is None and args.figures_dir is None:
        tree = "data/step01_figures/figs"

    total_checked = 0
    failures = []
    notices = []          # 保証対象外の図 (終了コードは変えない)
    composition = []      # Word / PowerPoint でだけ崩れる疑い (終了コードは変えない)
    total_raw = 0
    # 合格メッセージをモード別にする。両モードを合算して
    # 「N 件すべてが 300dpi を満たしています」と出すと、--figures-dir には元 SVG が無く
    # 画素数の期待値を出せない (pHYs の申告値しか見ていない) ので、表示が保証より強くなる。
    checked_by_mode = []

    if tree:
        print(f"== 図ツリーの解像度検査: {tree} (目標 {args.dpi}dpi) ==")
        if not Path(tree).is_dir():
            print(f"エラー: 図ツリー '{tree}' がありません "
                  "(先に 'bash scripts/build.sh' を実行してください)", file=sys.stderr)
            return 2
        n, f, nr, nt, n_derived, comp = check_tree(Path(tree), args.dpi)
        total_checked += n
        failures += f
        total_raw += nr
        notices += nt
        composition += comp
        checked_by_mode.append(
            f"図ツリー {n} 件 (実画素数まで検算)"
            + (f" + 生ラスタ図 {nr} 件 (保証対象外・注意)" if nr else "")
            # 除外した派生物を黙らせない
            # step05 は data/step05_package/ へ出すので、ここに出るのは
            # 古い版の step05 が残した残骸である (図前処理を走らせれば消える)。
            + (f" / 提出用の派生物 {n_derived} 件は検査対象外 "
               f"({'/'.join(DERIVED_SVG_SUFFIXES)} = 古い版の step05 が図ツリーに"
               "残したもの。図前処理を走らせれば消えます)" if n_derived else ""))

    if args.figures_dir:
        print(f"== 分離出力図の解像度検査: {args.figures_dir} (目標 {args.dpi}dpi) ==")
        if not Path(args.figures_dir).is_dir():
            print(f"エラー: '{args.figures_dir}' がありません "
                  "(先に 'bash scripts/package.sh --mode final --format png' を実行してください)",
                  file=sys.stderr)
            return 2
        n, f, nr, nt = check_figures_dir(Path(args.figures_dir), args.dpi)
        total_checked += n
        failures += f
        total_raw += nr
        notices += nt
        checked_by_mode.append(f"分離出力図 {n} 件 (pHYs の申告値のみ。元 SVG が無く画素数の"
                               "期待値を出せないため。pptx 図は SVG 拡張の位置と同梱 PNG も検査)"
                               + (f" + 保証対象外 {nr} 件 (注意)" if nr else ""))

    print("")
    # 保証対象外の図は不合格にしないが、必ず見えるところに出す
    if notices:
        print(f"-- 注意 {len(notices)} 件 ({args.dpi}dpi 保証の対象外) --")
        for msg in notices:
            print(f"  [注意] {msg}")
        # 注意の対象は 2 種類 (執筆者が直接置いたラスタ図 / 案 A の pptx) なので、両方に当てはまる文言にする。
        print("  いずれも**中身をツール側で作り直せない図**である "
              "(執筆者が直接置いたラスタ図 / 案 A で無変換コピーした pptx)。")
        print("  雑誌が dpi 要件を課す場合は、元画像を要求解像度で書き出し直すか、"
              "PowerPoint 上で解像度とベクターかどうかを確かめること。")
        print("")
    # 解像度とは別の注意。見出しを分けるのは、上の注意 (作り直せない図) と対処が違うため
    if composition:
        print(f"-- 注意 {len(composition)} 件 (Word / PowerPoint でだけ崩れる SVG の疑い) --")
        for msg in composition:
            print(f"  [注意] {msg}")
        print("  SVG としては正しく、ブラウザや PNG フォールバックでは正常に見えるので、"
              "**体裁の計測では見つからない**。")
        print("")
    if failures:
        print(f"-- 不合格 {len(failures)} 件 --")
        for msg in failures:
            print(f"  [NG] {msg}")
        return 1
    if total_checked == 0 and total_raw == 0:
        print("エラー: 検査対象の図が 1 件もありませんでした (テストが空振りしています)")
        return 2
    print(f"== 合格: {total_checked} 件 / 目標 {args.dpi}dpi ==")
    for line in checked_by_mode:
        print(f"  - {line}")
    if total_raw:
        print(f"  ※ **解像度を保証できない図が {total_raw} 件ある** (上の注意を参照)。"
              f"「合格」の {total_checked} 件にこれらは含まれない。")
    if composition:
        print(f"  ※ **Word / PowerPoint でだけ崩れる疑いが {len(composition)} 件ある** (上の注意を参照)。"
              "「合格」は解像度の判定であって、Word / PowerPoint での見え方を保証しない。")
    if args.figures_dir and not tree:
        print("  ※ 分離出力図だけを検査した。画素数の検算は引数なしの "
              "'bash scripts/check-figures.sh' (図ツリー) で行うこと。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
