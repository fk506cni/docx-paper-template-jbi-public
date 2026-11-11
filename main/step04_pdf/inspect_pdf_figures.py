#!/usr/bin/env python3
"""inspect_pdf_figures.py — roundtrip で得た PDF の図がベクターかラスタかを客観判定する。

なぜ必要か:
    本テンプレは SVG を docx へネイティブ埋込し「劣化なしベクター」を謳うが、
    Word がその拡張を解釈できないと**警告も出さずに** PNG フォールバックへ戻る。
    つまり docx を目で見ても「ベクターで載っているか」は判別できない。
    一方 PDF に書き出すと差が構造として残る:
      - ベクター描画された図 -> PDF 内にパス描画命令として入り、画像オブジェクトにならない
      - PNG フォールバック   -> PDF 内に画像オブジェクト (XObject /Subtype /Image) として入る
    したがって **PDF 内の画像オブジェクト数**を数えれば、目視に頼らず判定できる。

判定の考え方:
    原稿の図のうち「元からラスタ (png/jpg 等)」の枚数を expected とすると、
      画像オブジェクト数 == expected        -> SVG はベクターで載っている (期待どおり)
      画像オブジェクト数 >  expected        -> SVG が PNG フォールバックされた疑い
    ※ Word はヘッダ画像やロゴも画像として埋めるため、雑誌テンプレによっては +α が出る。
      数値は「決定的証拠」ではなく「強い手がかり」として扱い、差分の内訳も見ること。

使い方 (ホストの Python を汚さないため uv で隔離する。CLAUDE.md のコンテナ運用原則):
    uv run --with pypdf python main/step04_pdf/inspect_pdf_figures.py data/products/main.pdf
    uv run --with pypdf python main/step04_pdf/inspect_pdf_figures.py data/products/main.pdf --expected-raster 1

検証データごとの期待値 (実測で確認済み):
    data/dummy            図 3 枚すべて SVG (fig-overview / fig-pipeline / mermaid/flow)
                          -> --expected-raster 0。ベクターなら画像 0 個、フォールバックなら 3 個
    data/dummy/regression 元からラスタの図は PNG 2 枚 (fig-photo.png x2)。残りはすべて SVG
                          -> --expected-raster 2

単体の図 PDF に対しても使える (経路の切り分けに有用):
    uv run --with pypdf python main/step04_pdf/inspect_pdf_figures.py \
        data/output/_default/figures/Figure1.pdf --expected-raster 0
"""

import argparse
import sys
from pathlib import Path


def inspect(pdf_path):
    """PDF を走査し、ページごとの画像オブジェクトを列挙する。

    返り値: (総画像数, [(ページ番号, 名前, 幅, 高さ, フィルタ), ...])
    """
    try:
        from pypdf import PdfReader
    except ImportError:
        print(
            "エラー: pypdf がありません。次のように uv で隔離実行してください:\n"
            "  uv run --with pypdf python main/step04_pdf/inspect_pdf_figures.py <pdf>",
            file=sys.stderr,
        )
        raise SystemExit(2)

    reader = PdfReader(str(pdf_path))
    rows = []
    for pno, page in enumerate(reader.pages, 1):
        resources = page.get("/Resources")
        if resources is None:
            continue
        xobjects = resources.get_object().get("/XObject")
        if xobjects is None:
            continue
        for name, ref in xobjects.get_object().items():
            try:
                obj = ref.get_object()
            except Exception:
                continue
            if obj.get("/Subtype") != "/Image":
                continue
            filt = obj.get("/Filter")
            rows.append(
                (
                    pno,
                    str(name),
                    int(obj.get("/Width", 0) or 0),
                    int(obj.get("/Height", 0) or 0),
                    str(filt) if filt is not None else "-",
                )
            )
    return len(rows), rows


def main():
    ap = argparse.ArgumentParser(
        description="roundtrip PDF の図がベクターかラスタかを画像オブジェクト数から判定する"
    )
    ap.add_argument("pdf", help="判定対象の PDF (例 data/products/main.pdf)")
    ap.add_argument(
        "--expected-raster",
        type=int,
        default=None,
        help="原稿中の『元からラスタ』な図の枚数。指定すると合否を判定する "
        "(data/dummy なら 1 = fig-photo.png のみ)",
    )
    args = ap.parse_args()

    pdf = Path(args.pdf)
    if not pdf.is_file():
        print(f"エラー: PDF がありません: {pdf}", file=sys.stderr)
        return 2

    total, rows = inspect(pdf)

    print(f"== 画像オブジェクトの検査: {pdf} ==")
    if rows:
        print(f"{'page':>5}  {'name':<12} {'width':>7} {'height':>7}  filter")
        for pno, name, w, h, filt in rows:
            print(f"{pno:>5}  {name:<12} {w:>7} {h:>7}  {filt}")
    else:
        print("  画像オブジェクトなし (すべてベクター描画)")
    print(f"\n画像オブジェクト総数: {total}")

    if args.expected_raster is None:
        print(
            "\n--expected-raster を指定すると合否判定します "
            "(原稿中の元からラスタな図の枚数)。"
        )
        return 0

    exp = args.expected_raster
    print(f"期待値 (元からラスタな図): {exp}")
    if total == exp:
        print("\n[OK] SVG 図はベクターとして載っています (画像オブジェクト数が期待値と一致)。")
        return 0
    if total > exp:
        print(
            f"\n[NG] 画像オブジェクトが期待より {total - exp} 個多いです。"
            "\n     SVG が PNG フォールバックされた疑いがあります。次を確認してください:"
            "\n       1. docx 側に asvg:svgBlip があるか"
            "\n          unzip -p data/step02_build/main.docx word/document.xml | grep -c asvg:svgBlip"
            "\n       2. 変換した Word の世代 (ベクター表示は Microsoft 365 / Office 2019 以降。"
            "\n          買い切り版 Office 2016 は SVG 非対応で PNG フォールバックになる)"
        )
        return 1
    print(
        f"\n[?] 画像オブジェクトが期待より {exp - total} 個少ないです。"
        "\n    元がラスタの図が欠落している可能性があります (--expected-raster の値も確認)。"
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
