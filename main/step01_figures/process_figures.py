#!/usr/bin/env python3
"""Step 01 図前処理 — コンテナ内 (docx-paper-template-pandoc) で実行する本体。

docs/architecture.md §2.1。<INPUT_ROOT>/figs の手書き SVG・PDF 図と、figures.sh が先に
data/step01_figures/figs/mermaid/ へ生成した Mermaid SVG を取り込み、
data/step01_figures/figs に「正規化済み図ツリー」を作る:

  1. SVG テキストクリップ修正 (fix_svg_clips, 冪等)
  2. PDF -> SVG 変換 (pdf2svg)
  2.5 生ラスタ図 (PNG/JPEG/TIFF) はそのまま複製 (変換不要・相対構造保持)
  3. SVG -> PNG 300dpi フォールバック (svg_raster。物理サイズから画素数を計算し -w/-h で明示)

【パス解決規約 (最重要)】
  pandoc の図パス解決は basename ではなく --resource-path との「フルパス連結」。
  原稿は figs/<rel>.svg を参照し、generic-style.lua が figs/<rel>.svg.png に書換える。
  よって出力は data/step01_figures/figs/<rel> の相対構造を【保持】しなければならない
  (basename へフラット化すると figs/<rel>.svg.png が解決できず図が出ない)。
  本スクリプトは入力 figs/ 以下の相対パスをそのまま出力ツリーへ写す。
  (docs/architecture.md §2.1)

【コンテナ分担】本スクリプトは pandoc コンテナ内。Mermaid 作図と最終図 svg->pdf は
  別コンテナで、figures.sh がホストから driver する。本スクリプトは subprocess で
  pdf2svg / rsvg-convert (pandoc コンテナに同梱) のみ呼ぶ。

使い方 (通常は figures.sh 経由):
    python3 main/step01_figures/process_figures.py <INPUT_ROOT> [OUT_ROOT]
      INPUT_ROOT: 原稿ルート (data/dummy または src)。既定 src
      OUT_ROOT  : 出力ルート。既定 data/step01_figures
"""

import os
import re
import subprocess
import sys
from pathlib import Path

# 同ディレクトリの fix_svg_clips を import (コンテナ cwd=/workspace 想定)
sys.path.insert(0, str(Path(__file__).resolve().parent))
from fix_svg_clips import fix_svg_clips  # noqa: E402

# 300dpi を保証するラスタライズは共通モジュールに集約 (step05_package と同じ規則)
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "00_setup" / "lib"))
import svg_raster  # noqa: E402

PNG_DPI = 300  # 旧 Word 向け PNG フォールバックの解像度


def run(cmd):
    """subprocess 実行。失敗時は stderr を見せて例外送出。"""
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        sys.stderr.write(
            f"  [失敗] {' '.join(cmd)}\n"
            f"    stdout: {res.stdout.strip()}\n"
            f"    stderr: {res.stderr.strip()}\n"
        )
        raise SystemExit(1)
    return res


def svg_to_png(svg_path):
    """SVG -> <svg>.svg.png (旧 Word 向け PNG フォールバック)。

    命名は generic-style.lua の *.svg->*.svg.png 書換と一致させる。

    【画素数の決め方】`rsvg-convert -d/-p` に dpi を渡しても、画素数に効くのは SVG ルートの
      width/height が物理単位 (pt/mm/in/cm) のときだけで、px/無単位の SVG
      (手書き図・pdf2svg 由来・mermaid 出力) は 1:1 描画のままになる。そこで svg_raster が
      物理サイズから必要画素数を計算して -w/-h で明示し、生成後に実画素数を検算する (不足はエラー)。
      あわせて pHYs (物理解像度) を書き込む。
      **pHYs があるので、docx 上の図は SVG の公称サイズどおりに置かれる**。pHYs の無い PNG は
      pandoc が 72dpi とみなすため、320 画素の図が 4.44in で置かれる (公称サイズは 3.33in)
      (`docs/architecture.md` §2.1)。原稿側の `{width=...}` で上書きできる。
      寸法不明 (width/height も viewBox も無い) の SVG は、**本段では停止させず警告に留める**。
      300dpi 要件は「提出」への制約であり、本段が作るのは共著者に配る草稿の
      docx 埋込用フォールバックだからである。提出図を作る step05 (`package.py`) は
      エラーで停止するので、規定違反物を出さないという目的はそちらで達成される。
      本段で止めると、寸法不明の SVG が 1 枚あるだけで **docx が 1 つも生成されず**、その図より後ろの
      正常な図も処理されない (rsvg は寸法不明の SVG も既定の大きさで描画できる)。
    """
    png_path = str(svg_path) + ".png"
    try:
        r = svg_raster.render_png_at_dpi(svg_path, png_path, PNG_DPI, log=print,
                                         allow_unknown_size=True)
    except svg_raster.SvgRasterError as exc:
        # 寸法以外の失敗 (rsvg 異常終了・画素数不足) は停止する
        sys.stderr.write(f"  [失敗] png フォールバック生成: {exc}\n")
        raise SystemExit(1) from exc
    if not r.get("guaranteed", True):
        sys.stderr.write(
            f"  [警告] {svg_path}: 寸法が決められないため {PNG_DPI}dpi を保証できません。\n"
            "         rsvg の既定描画で PNG を作りました (pHYs は書いていません)。草稿はこのまま\n"
            "         進められますが、**提出図の生成 (package.sh --mode final) はエラーで停止します**。\n"
            "         SVG ルートに width/height (できれば mm/pt などの物理単位) か viewBox を付けてください。\n"
        )
    return png_path


def pdf_to_svg(pdf_path, svg_out):
    """PDF -> SVG (pdf2svg)。

    崩れる場合のフォールバック方針 (実装メモ):
      pdf2svg は単純なベクター PDF には十分だが、複雑な PDF (透明・特殊フォント
      サブセット・複数ページ) で崩れることがある。その場合の代替経路:
        (a) pdftocairo -svg input.pdf out.svg  (poppler。pdf2svg より堅牢なことがある)
        (b) Inkscape (svg-conversion コンテナ) で PDF->SVG: inkscape in.pdf
            --export-type=svg -o out.svg  (フォントをパス化でき再現性が高い)
        (c) 元データから SVG を直接書き出す (R: svglite / matplotlib: savefig svg)
      いずれも本ツリーの figs/<rel>.svg として置けば以降同経路で扱える。
    複数ページ PDF は 1 ページ目のみ変換される (図は単一ページ前提)。
    """
    run(["pdf2svg", str(pdf_path), str(svg_out)])


# --- pdf2svg 出力の寸法を pt として解釈する -------------------------
#
# 【なぜ要るか】pdf2svg は PDF の MediaBox を SVG ルートの width/height にそのまま写すが、
# MediaBox の単位は **pt (1/72 インチ)** なのに対し、書き出される値は**単位なしの数値**である。
# SVG の規約では単位なし = CSS px (1/96 インチ) なので、本テンプレの寸法解析 (svg_raster) は
# **PDF 由来の図をすべて 72/96 = 75% の大きさとして登録する**。
#
# 例 (実測): MediaBox 648x504 pt = 9.00x7.00 in の PDF 図は
#   → 6.75x5.25 in と登録され 300dpi 要求で 2025x1575 px を生成する
#   → 本来の 9.00 in で刷ると **実効 225 dpi**
# つまり、このままでは「300dpi の保証」が PDF 経路では成り立たず、しかも検算は
# 「登録された公称サイズ」に対して行われるため **`--mode final` は合格と報告してしまう**。
# 執筆規約が勧める「SVG に物理単位で寸法を書く」も、この SVG は step01 が生成するので
# 執筆者には書けない。
#
# 【対処】pdf2svg 直後に width/height へ `pt` を付ける。viewBox は据え置き
# (viewBox はユーザー座標の宣言で単位を持たない。比が変わらないので描画は不変)。
# **pdf2svg を通った図だけ**が対象で、手書き SVG の単位なしは CSS px のままにする
# — そちらは SVG の規約どおりの解釈であり、回帰フィクスチャ
# `data/dummy/figs/fig-overview.svg` (320x120 px) がその経路を担っている。
_RE_SVG_START_TAG = re.compile(r"<svg\b[^>]*>", re.IGNORECASE | re.DOTALL)


def _bare_length_re(name):
    """`width="225"` のように**単位を持たない数値**の属性にだけ当たる正規表現。"""
    return re.compile(rf"""(\b{name}\s*=\s*(?P<q>["']))\s*(?P<num>[0-9]*\.?[0-9]+)\s*(?P=q)""")


def _united_length_re(name):
    """`width="225pt"` のように**既知の単位が付いた数値**の属性に当たる正規表現。

    単位の集合は `svg_raster.UNIT_TO_INCH` から採る (二重定義を作らないため)。
    空文字のキー (= 単位なし) は `_bare_length_re` が受け持つので除く。
    """
    units = "|".join(sorted((u for u in svg_raster.UNIT_TO_INCH if u), key=len, reverse=True))
    return re.compile(rf"""\b{name}\s*=\s*(["'])\s*[0-9]*\.?[0-9]+\s*(?:{units})\s*\1""",
                      re.IGNORECASE)


def annotate_pdf_svg_units(svg_path, log=print):
    """pdf2svg が出した SVG の width/height を pt 単位つきへ書き換える。

    書き換えたときだけ dict (幅・高さの pt 値とインチ換算) を返し、書き換えなかったときは
    None を返す。**書き換えなかった場合は必ず知らせる** — pdf2svg の出力形が変われば
    この経路は黙って 25% 小さい解釈 (CSS px) に戻るので、気づけない形で 300dpi 保証が
    抜けるのを防ぐため。

    **知らせ方は 2 通りに分ける**。理由を問わず
    「CSS px として扱われる。25% 小さくなる可能性がある」と出すと、
    **いちばん起こりやすい将来のケース「pdf2svg (cairo) が最初から `pt` を付けて
    書き出すようになった」**でも警告が出る。そのとき寸法は**すでに正しい**ので、
    安心してよい場面で不安を与え、本当に危ない場面と区別が付かなくなる。
      - 既知の単位が付いていた   → `[情報]` 対処不要
      - 単位を判定できなかった   → `[警告]` 25% 小さくなる可能性がある

    **複数回適用しても安全である**。単位が付いていれば
    `_bare_length_re` が当たらないので、`225ptpt` にはならず何もせずに戻る。

    置換は SVG ルートの開始タグの中だけを対象にした**表層の文字列操作**である
    (`fix_svg_clips` と同じ流儀)。XML として読み直して書き戻すと、pdf2svg が出した
    その他の部分まで再直列化されて差分が読みにくくなるため。

    **見送った堅牢化**: `_RE_SVG_START_TAG` はファイルの先頭から
    最初に見つかった `<svg …>` に当たるので、**根要素より前のコメントに `<svg>` の字面が
    あるとコメントの中を書き換えてしまう** (しかも「pt 解釈した」と報告する)。
    厳密にするには XML の前書き (宣言 / DOCTYPE / コメント) を読み飛ばす処理が要るが、
    pdf2svg はコメントを出さないので**その処理自体が新しい壊れ方の入口になる**と判断した。
    再検討条件: **pdf2svg がコメント付きの SVG を出すようになったとき**。
    """
    path = Path(svg_path)
    text = path.read_text(encoding="utf-8")
    m = _RE_SVG_START_TAG.search(text)
    if not m:
        sys.stderr.write(f"  [警告] {svg_path}: <svg> 開始タグが見つからず pt 解釈を適用できません。\n")
        return None
    tag = m.group(0)
    hits = {}
    for name in ("width", "height"):
        hit = _bare_length_re(name).search(tag)
        if hit:
            hits[name] = hit
    if len(hits) != 2:
        united = [n for n in ("width", "height") if _united_length_re(n).search(tag)]
        if len(united) == 2:
            # 既知の単位が明示されている = 公称サイズはそのまま正しい。触らない。
            log(f"    pdf2svg: width/height に単位が明示されているのでそのまま使います "
                f"(対処不要): {svg_path}")
        else:
            sys.stderr.write(
                f"  [警告] {svg_path}: pdf2svg 出力の width/height の単位を判定できなかったため "
                "pt として解釈できませんでした。\n"
                "         この図の公称サイズは SVG の規約どおり CSS px (96dpi) として扱われます。"
                "PDF の実寸より 25% 小さくなる可能性があります。\n")
        return None
    new_tag = tag
    for name in ("width", "height"):
        hit = hits[name]
        new_tag = new_tag.replace(hit.group(0),
                                  f"{hit.group(1)}{hit.group('num')}pt{hit.group('q')}", 1)
    path.write_text(text[:m.start()] + new_tag + text[m.end():], encoding="utf-8")
    w_pt, h_pt = float(hits["width"].group("num")), float(hits["height"].group("num"))
    info = {"width_pt": w_pt, "height_pt": h_pt,
            "width_in": w_pt / 72.0, "height_in": h_pt / 72.0}
    log(f"    pdf2svg: 寸法を pt として解釈 ({_fmt(w_pt)}x{_fmt(h_pt)} pt = "
        f"{info['width_in']:.2f}x{info['height_in']:.2f} in)")
    return info


def _fmt(v):
    """648.0 -> '648' / 82.5 -> '82.5' (ログの読みやすさのため)。"""
    return f"{v:g}"


def iter_files(root, suffix):
    """root 以下を再帰し、指定拡張子のファイルを (path, relpath) で yield。"""
    if not root.is_dir():
        return
    for p in sorted(root.rglob(f"*{suffix}")):
        if p.is_file():
            yield p, p.relative_to(root)


def main():
    if len(sys.argv) < 2:
        sys.stderr.write(__doc__)
        raise SystemExit(2)

    input_root = Path(sys.argv[1])
    out_root = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("data/step01_figures")

    figs_in = input_root / "figs"
    figs_out = out_root / "figs"

    if not figs_in.is_dir():
        sys.stderr.write(f"エラー: 入力図ディレクトリが見つかりません: {figs_in}\n")
        raise SystemExit(1)

    figs_out.mkdir(parents=True, exist_ok=True)

    # --- 同名 SVG / PDF 併存チェック ---
    #     figs/foo.svg と figs/foo.pdf が併存すると、後段 (PDF->SVG) の出力先が figs/foo.svg で
    #     手書き SVG と衝突し、PDF 由来 SVG が手書き SVG を無言で上書きしてしまう。事前に検知して止める。
    #     mermaid/ 配下は別経路 (figures.sh が生成) なので除外する。
    def _non_mermaid(rel):
        return not (rel.parts and rel.parts[0] == "mermaid")

    svg_stems = {rel.with_suffix("") for _, rel in iter_files(figs_in, ".svg") if _non_mermaid(rel)}
    pdf_stems = {rel.with_suffix("") for _, rel in iter_files(figs_in, ".pdf") if _non_mermaid(rel)}
    clash = sorted(str(s) for s in (svg_stems & pdf_stems))
    if clash:
        sys.stderr.write(
            "エラー: 同名の SVG と PDF が併存します (出力先 figs/<name>.svg が衝突し無言上書きになります):\n"
            + "".join(f"  - figs/{c}.svg と figs/{c}.pdf\n" for c in clash)
            + "  どちらか一方に統一するか、リネームしてください。\n"
        )
        raise SystemExit(1)

    counts = {"svg_fixed": 0, "svg_copied": 0, "pdf2svg": 0, "png": 0,
              "mermaid_svg": 0, "raster_copied": 0, "pdf_pt": 0}
    produced = []

    # --- Mermaid の単独描画の残骸 ---
    #     `docker/mermaid/convert.sh figs/mermaid/<名前>.mmd both` を単独で回すと、.mmd の隣に
    #     <名前>.svg / <名前>.pdf が残る。下の PDF のループがそれを拾うと、figures.sh が .mmd から
    #     作り直した図を古い PDF 由来の SVG で黙って上書きし、.mmd を直しても古い図のまま提出される。
    #     .mmd がある以上その .svg / .pdf は作り直せる残骸なので、読み飛ばして警告する
    #     (ビルドは止めない)。.mmd の無い mermaid/ 配下の PDF は従来どおり扱う。
    mmd_stems = {rel.with_suffix("") for _, rel in iter_files(figs_in, ".mmd")
                 if rel.parts and rel.parts[0] == "mermaid"}

    def _mermaid_leftover(rel):
        return bool(rel.parts) and rel.parts[0] == "mermaid" and rel.with_suffix("") in mmd_stems

    def _warn_leftover(rel):
        sys.stderr.write(
            f"  [警告] Mermaid の単独描画の残骸を無視しました: figs/{rel} "
            f"(figs/{rel.with_suffix('.mmd')} から作り直した図を使います。この残骸は消してよい)\n")

    # --- 1. 手書き SVG: figs/<rel>.svg を出力ツリーへ複製 -> fix -> png ---
    #     mermaid/ 配下は figures.sh が別途生成 (後段 3) するためここでは除外する。
    for src_svg, rel in iter_files(figs_in, ".svg"):
        if rel.parts and rel.parts[0] == "mermaid":
            if _mermaid_leftover(rel):
                _warn_leftover(rel)
            continue
        dst = figs_out / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(src_svg.read_bytes())
        counts["svg_copied"] += 1
        n = fix_svg_clips(str(dst))
        if n:
            counts["svg_fixed"] += n
            print(f"  fix-svg-clips: {rel} ({n} text)")
        svg_to_png(dst)
        counts["png"] += 1
        produced.append(str(dst))

    # --- 2. PDF 図: figs/<rel>.pdf -> figs/<rel>.svg (pdf2svg) -> fix -> png ---
    for src_pdf, rel in iter_files(figs_in, ".pdf"):
        if _mermaid_leftover(rel):
            _warn_leftover(rel)
            continue
        svg_rel = rel.with_suffix(".svg")
        dst = figs_out / svg_rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        pdf_to_svg(src_pdf, dst)
        counts["pdf2svg"] += 1
        print(f"  pdf2svg: {rel} -> figs/{svg_rel}")
        # MediaBox は pt なので、単位なしで書き出された寸法に pt を付ける。
        # ここで付けないと以降 (docx 上の表示寸法・300dpi の画素数計算・pptx のスライド寸法) が
        # すべて 25% 小さい公称サイズを前提に動く。
        if annotate_pdf_svg_units(dst):
            counts["pdf_pt"] += 1
        fix_svg_clips(str(dst))
        svg_to_png(dst)
        counts["png"] += 1
        produced.append(str(dst))

    # --- 2.5. 生ラスタ図 (PNG/JPEG/TIFF): figs/<rel> をそのまま出力ツリーへ複製 ---
    #     原稿が figs/foo.png のようにラスタ図を直接参照する場合、step01 が複製しないと pandoc の
    #     resource-path に解決されず "Could not fetch resource" で図が欠落し、image-manifest の画像数と
    #     docx の図数がずれて build が中止する (回帰フィクスチャ data/dummy/regression で確かめる)。
    #     ベクター (svg/pdf) と違い変換は不要なので相対構造を保ってそのまま写す。生成フォールバック
    #     (*.svg.png) と mermaid/ 配下は除外する。
    RASTER_SUFFIXES = (".png", ".jpg", ".jpeg", ".tif", ".tiff")
    seen_raster = set()
    for suffix in RASTER_SUFFIXES:
        for src_raster, rel in iter_files(figs_in, suffix):
            if rel.parts and rel.parts[0] == "mermaid":
                continue
            if str(rel).endswith(".svg.png"):  # 生成済 PNG フォールバックは複製しない
                continue
            if rel in seen_raster:             # 同一ファイルの二重処理ガード
                continue
            seen_raster.add(rel)
            dst = figs_out / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_bytes(src_raster.read_bytes())
            counts["raster_copied"] += 1
            print(f"  raster: {rel} -> figs/{rel}")
            produced.append(str(dst))

    # --- 3. Mermaid 生成 SVG: figures.sh が figs/mermaid/ に出力済 -> png のみ ---
    #     fix_svg_clips は svglite の textLength/clip 不具合専用で mermaid には無益。mermaid SVG は
    #     ダブルクオート属性のため _transform_text が no-op となり、clipPath を出す作図種別 (sequence 等)
    #     では <text> だけ移設されて図が崩れる恐れがある。よって mermaid には fix を適用しない。
    mermaid_out = figs_out / "mermaid"
    for svg, rel in iter_files(mermaid_out, ".svg"):
        counts["mermaid_svg"] += 1
        svg_to_png(svg)
        counts["png"] += 1
        produced.append(str(svg))

    print(
        "図前処理 完了: "
        f"手書きSVG {counts['svg_copied']} / PDF->SVG {counts['pdf2svg']} "
        f"(うち pt 解釈 {counts['pdf_pt']}) / "
        f"mermaidSVG {counts['mermaid_svg']} / ラスタ {counts['raster_copied']} / "
        f"PNG {counts['png']} / clip修正 {counts['svg_fixed']}"
    )
    if not produced:
        sys.stderr.write(
            "警告: 処理対象の図が 1 件もありませんでした "
            f"({figs_in} に *.svg / *.pdf / *.png 等 / mermaid svg が無い)。\n"
        )


if __name__ == "__main__":
    main()
