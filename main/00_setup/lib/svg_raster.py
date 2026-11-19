#!/usr/bin/env python3
"""svg_raster.py — SVG を「目標 dpi を保証して」PNG にラスタライズする共通モジュール。

docs/architecture.md §2.1 / §2.5、docs/profile-schema.md。`docs/journal-bhi.md` §5 (G5)。

【なぜ要るか】`rsvg-convert -d <dpi> -p <dpi>` の dpi 指定が
画素数に効くのは **SVG ルートの width/height が物理単位 (pt/mm/cm/in/pc) のときだけ**である
(実測)。px 単位・単位なしの SVG (手書き図・pdf2svg 由来・
mermaid 出力) では 1:1 で描画され、指定した dpi は**画素数に一切反映されない**。
BioHealth Informatics は "image files should have a minimum of 300 dpi" を課すため、
dpi 指定に頼ると規定違反物を無警告で出すことになる。

【本モジュールの方針】
  1. SVG ルートの width/height/viewBox を解析して**図の物理サイズ (inch)** を決める。
     - 物理単位 (pt/mm/cm/in/pc/Q) を持つ → その値をそのまま inch に換算する。
     - px / 単位なし / `%` → **CSS px = 1/96 inch** とみなして換算する (viewBox も同じ扱い)。
       換算根拠は呼び出し側のログに出す (どの経路で寸法を決めたかを追えるようにするため)。
  2. 物理サイズ × 目標 dpi = **必要画素数**を計算し、`rsvg-convert -w/-h` で明示指定する。
     切り上げ (ceil) するので、実効 dpi が目標を下回ることはない。
  3. 生成後に **PNG の IHDR から実画素数を読み直して検算**する。目標に届かなければ
     警告ではなく **例外 (SvgRasterError)** にする — 規定違反物を黙って出さないため。
  4. PNG に **pHYs チャンク (物理解像度)** を書き込み、Word・査読者の環境で「300 dpi の画像」と
     認識されるようにする。**コンテナに Pillow も ImageMagick も exiftool も入っていない**
     (実測) ため、標準ライブラリ (struct + zlib.crc32) で自前実装する。

【表示サイズ (重要)】pandoc は PNG の pHYs を読んで図の表示寸法を決める。pHYs の無い PNG は
既定 72dpi として扱われ、320 画素の図は 4.44in で置かれる。pHYs (300dpi) を書くので、図は
**SVG の公称サイズどおり (320 CSS px = 3.33in)** に置かれる。pHYs の無い PNG と比べると
**docx 上の図は小さくなる。** 縮小率は図の書き方で変わる:
  - px/単位なしの図: 約 25% 減 (実測 4.444in -> 3.333in)
  - 物理単位の図: 公称サイズそのものになるためさらに大きい (実測 60mm の図が 5.833in -> 2.363in)
    — pHYs が無いと 709 画素 ÷ 72dpi = 9.85in と算出され、本文幅で切り詰められるため。
原稿側の `{width=...}` でいつでも上書きできる。詳細は `docs/architecture.md` §2.1。
**図を大きく見せるために pHYs を外さないこと** (300dpi の申告が消える。大きさは `{width=...}` で決める)。
本モジュールの寸法解析は pptx 図の生成 (svg_pptx) も使っている。

【使う側】
  - `main/step01_figures/process_figures.py` : docx 埋込用 PNG フォールバック (`*.svg.png`)
  - `main/step05_package/package.py`         : 最終提出図 (`figures/FigureN.png`)
  どちらも同じ換算規則・同じ検算を通す (提出図と草稿図で解像度規則がずれない)。
"""

import math
import os
import re
import stat
import struct
import subprocess
import tempfile
import zlib
from pathlib import Path

# CSS 単位 → inch。px / 単位なしは CSS px (1/96 inch) とみなす (SVG 1.1 / CSS の既定)。
CSS_PX_PER_INCH = 96.0
UNIT_TO_INCH = {
    "": 1.0 / CSS_PX_PER_INCH,
    "px": 1.0 / CSS_PX_PER_INCH,
    "pt": 1.0 / 72.0,
    "pc": 1.0 / 6.0,
    "mm": 1.0 / 25.4,
    "cm": 1.0 / 2.54,
    "in": 1.0,
    "q": 1.0 / 101.6,          # CSS の Q (1/4 mm)
}
PHYSICAL_UNITS = ("pt", "pc", "mm", "cm", "in", "q")

# 暴走ガード: 目標画素数がこれを超えたら止める (A4 全面 1200dpi ≒ 139 MP を通す余裕を残す)。
#
# 【この値はメモリの実効上限ではない】
# 2 億画素は描画時のメモリで 1 画素 4 バイト = 約 800 MB に相当し、PNG の圧縮前後の作業領域が
# さらに乗る。コンテナへの割り当てによっては**この上限に達する前に rsvg-convert が
# メモリ不足で落ちる**。そのときは returncode != 0 の一般的な失敗になるため、下の
# render_png_at_dpi は失敗時のエラー文に**目標画素数を併記**して原因を辿れるようにしてある。
# 上限値そのものを下げていないのは、本テンプレの実運用で到達する図が無いためである
# (最大の mermaid 由来図が公称 21.2 インチ幅 = 300dpi で 4.5 MP / 1200dpi でも 71 MP)。
MAX_PIXELS = 200_000_000

_LEN_RE = re.compile(r"^\s*([+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?)\s*([a-zA-Z%]*)\s*$")


class SvgRasterError(RuntimeError):
    """SVG の寸法が決められない / 目標 dpi に届かない / rsvg-convert が失敗した。"""


# =====================================================================
# SVG の物理サイズ解析
# =====================================================================

def _parse_length(value):
    """SVG の長さ属性を (数値, 単位小文字) で返す。解釈できなければ None。

    `%` は「親要素に対する割合」で単体では解決できないため None を返す (viewBox へ倒す)。

    0 / 負値も None を返す (= 指定なし扱い) が、これは `%` と違って
    **執筆者の書き間違いである可能性が高い**。無警告で viewBox から補完されると、意図と違う
    大きさで図が置かれたときに原因に気づけないため、`_parse_length_noted` が理由を持ち帰る。
    """
    parsed, _ = _parse_length_noted(value)
    return parsed


def _parse_length_noted(value):
    """`_parse_length` に「なぜ解釈できなかったか」の注記を添えて返す。

    返り値: ((数値, 単位) または None, 注記 str または None)
    """
    if value is None:
        return None, None
    m = _LEN_RE.match(str(value))
    if not m:
        return None, f"'{value}' は長さとして解釈できない"
    num, unit = float(m.group(1)), m.group(2).lower()
    if unit == "%":
        return None, None            # 設計どおり viewBox へ倒す (注記不要)
    if unit not in UNIT_TO_INCH:
        return None, f"'{value}' の単位 '{unit}' は未対応"
    if num == 0:
        return None, f"'{value}' は 0 (SVG 仕様では非描画) のため指定なしとして扱う"
    if num < 0:
        return None, f"'{value}' は負値のため指定なしとして扱う"
    return (num, unit), None


def _parse_viewbox(value):
    """viewBox="minx miny w h" を (w, h) で返す。解釈できなければ None。"""
    if not value:
        return None
    nums = re.split(r"[\s,]+", str(value).strip())
    if len(nums) != 4:
        return None
    try:
        vals = [float(x) for x in nums]
    except ValueError:
        return None
    if vals[2] <= 0 or vals[3] <= 0:
        return None
    return vals[2], vals[3]


# ルート要素だけを読むための走査上限。
_SVG_HEAD_CHUNK = 64 * 1024        # 1 回に読み込むバイト数
_SVG_HEAD_MAX_ELEMENTS = 1000      # <svg> が見つからないまま走査してよい要素数


def _svg_root_attrs(svg_path):
    """SVG ルート要素の属性 dict を返す。

    必要なのは width / height / viewBox の 3 つだけなので、**最初の `<svg>` の開始タグを
    読んだ時点で解析を打ち切る**。

    SVG 全体を `etree.parse(..., recover=True, huge_tree=True, resolve_entities=False)` で
    構文解析する方式は採らない。`huge_tree=True` は解析器が持つ「深さ・要素数の上限」という
    **安全装置を外す**指定で、mermaid の大きな出力を全体で読むには必要になる。**ルートが `<svg>` で
    あれば**最初の開始タグで返るので上限に触れず、**安全装置を外す必要が無い** (huge_tree=False)。
    数メガバイトある mermaid 出力を図の枚数だけ全部読む無駄も無い。

    ただし「上限に当たりようがない」わけではない。上限が掛かるのは「最初の `<svg>` **より前に
    読む部分**」なので、その前に何かがあれば当たる。全体を huge_tree=True で読む方式と
    13 通りの入力で比べると、次の 3 通りだけ
    **本方式が失敗する** (いずれも実在する SVG では起こりにくいので、この設計のままとする):
      - `<svg>` に到達する前の入れ子が **256 段**を超える (huge_tree=False で復活した深さ上限)
      - `<svg>` より前に **10MB** を超える文字データがある (1 ノードあたりの文字数上限)
      - `<svg>` より前に `_SVG_HEAD_MAX_ELEMENTS` 個を超える要素がある (下の意図した打ち切り)

    壊れた SVG でも寸法だけは拾えるよう `recover=True` は残す。外部実体参照は
    `resolve_entities=False` + `no_network=True` で遮断する。
    ルートが `<svg>` でない場合 (XML 宣言 + DOCTYPE + コメント + ラッパ要素) は後続の
    開始タグを走査して最初の `<svg>` を探す — ただし走査は `_SVG_HEAD_MAX_ELEMENTS` 要素
    までで打ち切る (SVG でないファイルを渡されたときに全体を読まないため)。

    **失敗時は走査した開始タグの数を添える**。`recover=True` は上限に
    当たっても例外にせず黙って読み進めるのをやめるため、「`<svg>` 要素が見つかりません」だけでは
    「SVG に `<svg>` が無い」という誤った結論に導く。走査数が出れば
    「0 個 = SVG でないファイル」と「258 個で止まった = 深さ上限」を区別できる。
    `parser.error_log` を添える案は**採らなかった** — 本コンテナの lxml では
    `XMLPullParser` + `recover=True` の error_log が常に空で、深さ上限・文字数上限・
    先頭のゴミテキストのいずれでも 1 件も積まれないことを実測した (`close()` も例外を出さない)。
    """
    from lxml import etree
    parser = etree.XMLPullParser(events=("start",), recover=True,
                                 resolve_entities=False, huge_tree=False, no_network=True)
    scanned = 0
    try:
        with open(svg_path, "rb") as fh:
            while True:
                chunk = fh.read(_SVG_HEAD_CHUNK)
                if chunk:
                    parser.feed(chunk)
                else:
                    parser.close()        # 末尾まで来たら残りのイベントを吐き出させる
                for _, elem in parser.read_events():
                    if etree.QName(elem).localname == "svg":
                        return dict(elem.attrib)
                    scanned += 1
                    if scanned >= _SVG_HEAD_MAX_ELEMENTS:
                        raise SvgRasterError(
                            f"<svg> 要素が見つかりません (先頭 {scanned} 要素まで走査): {svg_path}")
                if not chunk:
                    break
    except (OSError, etree.XMLSyntaxError) as exc:
        raise SvgRasterError(f"SVG を読めません: {svg_path} ({exc})") from exc
    raise SvgRasterError(
        f"<svg> 要素が見つかりません: {svg_path}\n"
        f"  末尾まで読み、開始タグ {scanned} 個を走査しました。"
        "SVG でないファイルを指しているか、解析器が途中で読み進めるのをやめています "
        "(<svg> より前の入れ子が 256 段を超える / 文字データが 10MB を超える場合。"
        "recover=True はこれを例外にせず黙って打ち切る)")


def svg_physical_size(svg_path):
    """SVG の物理サイズを解析して dict で返す。

    返り値:
      width_in / height_in : 物理サイズ (inch)
      basis                : 'physical' (両軸とも物理単位) / 'css-px' (両軸とも px・単位なし) /
                             'mixed'    (軸ごとに単位が違う) /
                             'viewbox'  (width/height が無い・% なので viewBox を px とみなす)
      raw                  : 元の width/height 表記 (ログ用。viewBox 経路は viewBox 値)
      unit                 : 判定に使った単位 ('mm' 等。css-px/viewbox は 'px')。
                             basis='mixed' のときは 'W/H' 形式 (例 'px/mm')
      unit_w / unit_h      : 軸ごとの単位
      notes                : 解釈上の注意の list (0 / 負値を指定なし扱いにした等)

    決定順:
      1. width/height の両方が物理単位・px で解ける → それを使う (basis=physical / css-px / mixed)
      2. 片方だけ解ける → viewBox の縦横比でもう一方を補う
      3. どちらも解けない → viewBox を CSS px とみなす (basis=viewbox)
      4. viewBox も無い → SvgRasterError (寸法不明の図は 300dpi を保証できない)

    `unit` を「幅の単位 (無ければ px)」、`basis` を「どちらか一方でも物理単位なら physical」という
    **別々の規則**で決めると、`width="320" height="30mm"` が basis='physical' / unit='px' になり、
    ログが `[物理単位 px]` という語義矛盾になる (換算は軸ごとなので画像自体は正しい)。
    そこで軸ごとの単位を持たせ、'mixed' を足してある。
    """
    attrs = _svg_root_attrs(svg_path)
    w, note_w = _parse_length_noted(attrs.get("width"))
    h, note_h = _parse_length_noted(attrs.get("height"))
    notes = [n for n in (note_w, note_h) if n]
    vb = _parse_viewbox(attrs.get("viewBox") or attrs.get("viewbox"))

    def to_inch(parsed):
        num, unit = parsed
        return num * UNIT_TO_INCH[unit]

    def _basis(uw, uh):
        pw, ph = uw in PHYSICAL_UNITS, uh in PHYSICAL_UNITS
        if pw and ph:
            return "physical"
        if not pw and not ph:
            return "css-px"
        return "mixed"

    if w and h:
        unit_w, unit_h = w[1] or "px", h[1] or "px"
        basis = _basis(unit_w, unit_h)
        return {
            "width_in": to_inch(w), "height_in": to_inch(h), "basis": basis,
            "raw": f"{attrs.get('width')}x{attrs.get('height')}",
            "unit": unit_w if basis != "mixed" else f"{unit_w}/{unit_h}",
            "unit_w": unit_w, "unit_h": unit_h, "notes": notes,
        }

    if (w or h) and vb:
        # 片側のみ指定: viewBox の縦横比で補う (SVG の既定挙動と同じ)
        ratio = vb[1] / vb[0]
        if w:
            wi = to_inch(w)
            hi = wi * ratio
            unit = w[1] or "px"
        else:
            hi = to_inch(h)
            wi = hi / ratio
            unit = h[1] or "px"
        # 補った側は指定側と同じ尺度なので、軸ごとの単位は一致する
        basis = "physical" if unit in PHYSICAL_UNITS else "css-px"
        return {
            "width_in": wi, "height_in": hi, "basis": basis,
            "raw": f"{attrs.get('width') or '-'}x{attrs.get('height') or '-'} + viewBox {vb[0]}x{vb[1]}",
            "unit": unit, "unit_w": unit, "unit_h": unit, "notes": notes,
        }

    if vb:
        return {
            "width_in": vb[0] / CSS_PX_PER_INCH, "height_in": vb[1] / CSS_PX_PER_INCH,
            "basis": "viewbox", "raw": f"viewBox {vb[0]}x{vb[1]}", "unit": "px",
            "unit_w": "px", "unit_h": "px", "notes": notes,
        }

    raise SvgRasterError(
        f"SVG の寸法が決められません (width/height も viewBox も無い): {svg_path}\n"
        "  目標 dpi の画素数を計算できないため中止します。"
        "SVG ルートに width/height (できれば mm/pt などの物理単位) か viewBox を付けてください。"
    )


def describe_size(info, dpi, px_w, px_h):
    """換算根拠の 1 行説明 (ログ用。元サイズ・単位・目標 dpi・出力画素数)。"""
    if info["basis"] == "mixed":
        # 軸ごとに単位が違うことを明示する (「物理単位 px」のような語義矛盾を出さない)
        def axis(u):
            return f"物理単位 {u}" if u in PHYSICAL_UNITS else f"{u} → CSS px (96dpi)"
        basis_note = f"単位混在: 幅 {axis(info['unit_w'])} / 高さ {axis(info['unit_h'])}"
    else:
        basis_note = {
            "physical": f"物理単位 {info['unit']}",
            "css-px": "px/単位なし → CSS px (96dpi) とみなす",
            "viewbox": "width/height 無し → viewBox を CSS px (96dpi) とみなす",
            "unknown": "寸法指定なし → rsvg の既定描画 (解像度は保証されない)",
        }[info["basis"]]
    note = "".join(f" ※{n}" for n in info.get("notes") or ())
    return (f"{info['raw']} [{basis_note}] = "
            f"{info['width_in']:.3f}x{info['height_in']:.3f} in @ {dpi}dpi -> {px_w}x{px_h} px{note}")


# =====================================================================
# PNG のチャンク操作 (標準ライブラリのみ。コンテナに画像ライブラリが無いため)
# =====================================================================

PNG_SIG = b"\x89PNG\r\n\x1a\n"
INCH_PER_METER = 39.37007874015748


def _png_bytes(src):
    """PNG の中身を bytes で返す。**パスでもバイト列でも受ける**。

    書庫 (pptx) の中の PNG を検査するとき、パスしか受けないと一時ファイルへ書き出す必要があり、
    その置き場所が**提出ディレクトリの中**だと、強制終了したときに出所不明の PNG が提出物一式に
    残りうる。バイト列のまま解析できるようにして、一時ファイル自体を無くす。
    """
    if isinstance(src, (bytes, bytearray, memoryview)):
        return bytes(src)
    return Path(src).read_bytes()


def _png_chunk_spans(data):
    """PNG のチャンク境界を [(type, start, end), ...] と「IEND 以降の残りバイト数」で返す。

    **終端 (IEND) の存在を検証する**。`while pos + 8 <= len(data)` で走るだけだと、
      - 書き込み中に中断されてチャンク境界でちょうど切れた PNG が「正常な PNG」として通り、
        画素数の検算も IHDR しか見ないので合格してしまう
      - 末尾に 8 バイト未満の端数があると黙って無視され、`set_png_dpi` が書き戻す際に
        その端数が消える (読み書きしたつもりで内容が変わる)
    ため、IEND を必須にし、IEND 以降の残りは**捨てずに数えて返す**。

    走査は境界 (オフセット) だけを見るので、チャンク本体を複製しない
    (200 MP 級の PNG でもメモリが 2 倍にならない)。
    """
    if data[:8] != PNG_SIG:
        raise SvgRasterError("PNG シグネチャが不正です (生成に失敗している可能性)")
    spans = []
    pos = 8
    while pos + 8 <= len(data):
        (length,) = struct.unpack(">I", data[pos:pos + 4])
        ctype = data[pos + 4:pos + 8]
        end = pos + 12 + length
        if end > len(data):
            raise SvgRasterError("PNG が途中で切れています (チャンク長が不正)")
        spans.append((ctype, pos, end))
        pos = end
        if ctype == b"IEND":
            break
    if not spans or spans[-1][0] != b"IEND":
        raise SvgRasterError(
            "PNG に終端 (IEND) がありません — 書き込みが中断された壊れたファイルの可能性があります")
    return spans, len(data) - pos


def _iter_png_chunks(data):
    """PNG のチャンクを (type, raw_bytes) で yield する。raw は length+type+data+crc の全体。

    構造の検証 (シグネチャ / チャンク長 / IEND の存在) は yield の前にまとめて行う。
    generator を途中で捨てる呼び出し側 — `png_pixel_size` は IHDR で
    return する — でも検証が効くようにするためで、while ループの中で
    検証すると「先頭だけ読む経路では壊れた PNG が通る」という差が生まれる。
    """
    spans, _trailing = _png_chunk_spans(data)
    for ctype, start, end in spans:
        yield ctype, data[start:end]


def _png_chunk(ctype, payload):
    return (struct.pack(">I", len(payload)) + ctype + payload
            + struct.pack(">I", zlib.crc32(ctype + payload) & 0xFFFFFFFF))


def png_pixel_size(png_path):
    """PNG の IHDR から (幅, 高さ) を読む。引数はパスでもバイト列でもよい。"""
    data = _png_bytes(png_path)
    for ctype, raw in _iter_png_chunks(data):
        if ctype == b"IHDR":
            return struct.unpack(">II", raw[8:16])
    raise SvgRasterError(f"PNG に IHDR がありません: {png_path}")


def read_png_dpi(png_path):
    """PNG の pHYs から (dpi_x, dpi_y) を読む。pHYs 無し / 単位不明なら None。

    `read_png_phys` の薄い包み (dpi だけが要る呼び出し側のため)。
    """
    state, value = read_png_phys(png_path)
    return value if state == "dpi" else None


def read_png_phys(png_path):
    """PNG の pHYs を状態つきで読む。

    返り値 (state, value):
      ('dpi', (dpi_x, dpi_y)) : 単位がメートル (unit=1) = 解像度として読める
      ('unitless', (x, y))    : pHYs はあるが単位が「なし」(unit=0) = 縦横比のみで解像度ではない
      ('missing', None)       : pHYs が無い

    `read_png_dpi` は上の 2 つ目と 3 つ目をどちらも None で返すので、それだけで判定すると
    受入テストが一律に「pHYs (物理解像度) がありません」と表示し、**pHYs はあるが単位が
    『なし』だった**場合と**そもそも pHYs が無い**場合が同じ文言になる (対処が違うのに、
    利用者が誤った方向に調べることになる)。

    引数はパスでもバイト列でもよい。
    """
    data = _png_bytes(png_path)
    for ctype, raw in _iter_png_chunks(data):
        if ctype == b"pHYs":
            ppu_x, ppu_y, unit = struct.unpack(">IIB", raw[8:17])
            if unit != 1:          # 1 = meter。0 (単位なし=縦横比のみ) は dpi を表さない
                return "unitless", (ppu_x, ppu_y)
            return "dpi", (ppu_x / INCH_PER_METER, ppu_y / INCH_PER_METER)
    return "missing", None


def set_png_dpi(png_path, dpi, log=None):
    """PNG に pHYs (物理解像度) を書き込む。既存 pHYs は置換する (冪等)。

    pHYs は IHDR の後・IDAT の前に置く必要がある (PNG 仕様)。ここでは IHDR の直後に入れる。
    単位は meter (unit=1)、値は pixels per meter。

    【切り上げる理由 (実測)】pHYs は「1 メートルあたりの画素数」の**整数**なので、dpi を厳密には
    表せない (300dpi = 11811.02 px/m)。四捨五入して 11811 px/m を書くと、これを dpi へ戻す側が
    切り捨てで読むと **299 dpi** になる。実際 pandoc は 11811 px/m の PNG を 299 dpi と解釈した
    (docx の `wp:extent` が 1000px ÷ 299dpi = 3.3445in 相当の 3058193 EMU になることで確認)。
    雑誌の投稿系が「300 dpi 以上」を機械判定する場合、299 dpi は**規定違反と判定されうる**。
    そこで **切り上げ (ceil)** し、どの読み手でも目標 dpi を下回らないようにする
    (300dpi → 11812 px/m → 300.02 dpi。過大側の誤差は 0.03 dpi 未満)。

    書き戻しの 2 点:
      - **IEND 以降の端数バイトを捨てない**。PNG としては意味を持たないが、
        「読み書きしたつもりが内容が変わっている」のは避ける。
        そのまま書き戻し、`log` が渡されていれば存在を知らせる。
      - **同じパスへ直接書き戻さない**。途中で中断されると元の PNG が壊れた状態で残るため、
        同じディレクトリの一時ファイルへ書いてから `os.replace` で差し替える
        (同一ファイルシステム内なので原子的に入れ替わる。標準ライブラリのみ)。

    **差し替え前に元ファイルの権限を一時ファイルへ写す**。
    `tempfile.mkstemp()` が作るファイルは権限が `0600` (所有者のみ) 固定で、`os.replace()` は
    その権限をそのまま引き継ぐ。権限を写さないと、`rsvg-convert` が umask に従って作った
    ファイルを差し替えた時点で**生成した PNG がすべて所有者しか読めなくなる** (実測: `0644` → `0600`。
    `--format png` で出す提出図 `data/output/<journal>/figures/*.png` も同じ)。
    同じ出力ディレクトリの pptx は `0644` なので権限が食い違い、
    出力を共有ストレージ経由で共著者に渡すと読めないファイルが混じる。
    """
    path = Path(png_path)
    data = path.read_bytes()
    orig_mode = stat.S_IMODE(path.stat().st_mode)   # 差し替えで権限を落とさない
    ppm = math.ceil(float(dpi) * INCH_PER_METER)
    phys = _png_chunk(b"pHYs", struct.pack(">IIB", ppm, ppm, 1))

    spans, trailing = _png_chunk_spans(data)
    out = bytearray(PNG_SIG)
    inserted = False
    for ctype, start, end in spans:
        if ctype == b"pHYs":
            continue                      # 既存は捨てて IHDR 直後に入れ直す (冪等)
        out += data[start:end]
        if ctype == b"IHDR":
            out += phys
            inserted = True
    if not inserted:
        raise SvgRasterError(f"PNG に IHDR が無く pHYs を挿入できません: {png_path}")
    if trailing:
        # IEND より後ろは PNG 仕様上は意味を持たないが、黙って落とさない
        out += data[len(data) - trailing:]
        if log:
            log(f"  png: {path}: IEND の後ろに {trailing} バイトの余剰データがあります "
                "(そのまま保存しました)")

    # 原子的な差し替え: 一時ファイル → os.replace
    tmp_fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), prefix=path.name + ".", suffix=".tmp")
    try:
        with os.fdopen(tmp_fd, "wb") as fh:
            fh.write(bytes(out))
        os.chmod(tmp_name, orig_mode)     # mkstemp の 0600 を引き継がせない
        os.replace(tmp_name, str(path))
    except BaseException:
        # 失敗したら一時ファイルを残さない (元の PNG は無傷のまま)
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise
    return ppm


# =====================================================================
# ラスタライズ本体
# =====================================================================

def render_png_at_dpi(svg_path, out_png, dpi, log=None, label=None, allow_unknown_size=False,
                      place_size_in=None):
    """SVG を目標 dpi の画素数で PNG にし、pHYs を書き、実画素数を検算する。

    引数:
      svg_path           : 入力 SVG
      out_png            : 出力 PNG
      dpi                : 目標解像度 (int)
      log                : 1 行ログを受ける callable (既定 None = 出力しない)
      label              : ログに出す図の呼び名 (既定は svg のパス)
      allow_unknown_size : 真のとき、**寸法が決められない SVG を停止させず** rsvg の既定描画に
                           任せる。このとき pHYs は書かず basis='unknown' を返す。
      place_size_in      : `(幅 inch, 高さ inch)`。**図を実際に置く寸法**が公称サイズと違うとき
                           に渡す。画素数の計算・検算・pHYs の基準が
                           公称サイズではなくこの寸法になる。**省略時は公称サイズが基準**
                           (process_figures.py / package._png_at_dpi は省略して呼ぶ)。

    【place_size_in が要る理由】pptx の `slide_fit: fixed` は図を縮小して
    スライドへ置く。代替表示 PNG を**公称サイズ**でラスタ化すると、
    幅 62.5 インチの図を 10 インチに置くのに 18750 画素の PNG を作ることになり、面積で約 39 倍
    無駄になる。しかも `fixed` は「56 インチ超の図」の逃げ道としてツール自身が案内する
    経路なので、面積の大きい図 (実測 60×40 インチ = 216 MP) では MAX_PIXELS に当たって
    **逃げ道そのものが別のエラーで止まる**。置く寸法を基準にすれば両方とも解ける。
    pHYs に書く dpi は変わらない — 「その寸法で置いたときに dpi を満たす」という意味だからである。

    返り値: dict(width_px, height_px, dpi, width_in, height_in, basis, note, guaranteed)
      guaranteed=False は「目標 dpi を保証できていない」= allow_unknown_size で救済した場合。
    失敗 (寸法不明 / rsvg 失敗 / 画素数不足) は SvgRasterError。**警告で済ませない** —
    解像度不足は規定違反物の生成にあたるため。

    停止の範囲は段で分ける。300dpi 要件は**提出**への制約なので、提出図を作る
    step05 は停止させ、共著者に配る草稿を作る step01 は警告に留める
    (step01 で止めると、寸法不明の SVG が 1 枚あるだけで docx が 1 つも生成されず、その図より
    後ろの正常な図も処理されない。rsvg は寸法不明の SVG も既定の大きさで描画できる)。
    """
    svg_path, out_png = Path(svg_path), Path(out_png)
    dpi = int(dpi)
    if dpi <= 0:
        raise SvgRasterError(f"dpi は正の整数で指定してください (受け取った値: {dpi})")

    try:
        info = svg_physical_size(svg_path)
    except SvgRasterError:
        if not allow_unknown_size:
            raise
        return _render_png_unknown_size(svg_path, out_png, dpi, log, label)
    # 画素数の基準になる寸法。既定は図の公称サイズ、place_size_in を渡されたら置く寸法。
    # どちらを使ったかは下のログに出す。
    if place_size_in:
        base_w_in, base_h_in = float(place_size_in[0]), float(place_size_in[1])
        if base_w_in <= 0 or base_h_in <= 0:
            raise SvgRasterError(
                f"place_size_in は正の値で指定してください (受け取った値: {place_size_in})")
    else:
        base_w_in, base_h_in = info["width_in"], info["height_in"]
    # 切り上げ: 実効 dpi が目標を下回らないようにする (四捨五入だと 1px 足りずに違反しうる)
    px_w = max(1, math.ceil(base_w_in * dpi))
    px_h = max(1, math.ceil(base_h_in * dpi))
    if px_w * px_h > MAX_PIXELS:
        raise SvgRasterError(
            f"目標画素数が大きすぎます: {svg_path} -> {px_w}x{px_h} px "
            f"({px_w * px_h / 1e6:.0f} MP > 上限 {MAX_PIXELS / 1e6:.0f} MP)。\n"
            + (f"  画素数は**実際に置く寸法** {base_w_in:.3f}x{base_h_in:.3f} in から計算しています "
               f"(図の公称サイズは {info['raw']})。dpi ({dpi}) を下げてください。\n"
               if place_size_in else
               f"  図の公称サイズ ({info['raw']}) か dpi ({dpi}) を見直してください。\n")
        )

    out_png.parent.mkdir(parents=True, exist_ok=True)
    # -w/-h を明示するので -d/-p は渡さない (物理単位 SVG で二重に効くのを避ける)。
    cmd = ["rsvg-convert", "-w", str(px_w), "-h", str(px_h), "-o", str(out_png), str(svg_path)]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        # 目標画素数を併記する。MAX_PIXELS (上のコメント参照)
        # はメモリの実効上限ではないので、上限に達する前に rsvg-convert がメモリ不足で落ちる
        # ことがある。素の「png 生成に失敗しました」だけでは画素数が原因だと分からない。
        raise SvgRasterError(
            f"png 生成に失敗しました: {svg_path}\n  {' '.join(cmd)}\n  {res.stderr.strip()}\n"
            f"  目標 {px_w}x{px_h} 画素 ({px_w * px_h / 1e6:.1f} MP)"
            f" = {base_w_in:.3f}x{base_h_in:.3f} in @ {dpi}dpi。\n"
            "  画素数が大きいとメモリ不足で失敗することがあります"
            " (図の公称サイズを小さくするか dpi を下げてください)。"
        )

    # --- 検算: 実画素数が目標に届いているか (rsvg の丸め・アスペクト補正で減ることがある) ---
    # 実効 dpi は「画素数の基準にした寸法」で割る (place_size_in 指定時は置く寸法)
    act_w, act_h = png_pixel_size(out_png)
    eff_x = act_w / base_w_in if base_w_in > 0 else 0
    eff_y = act_h / base_h_in if base_h_in > 0 else 0
    if act_w < px_w or act_h < px_h:
        raise SvgRasterError(
            f"生成した PNG が目標解像度に届きません: {out_png}\n"
            f"  目標 {px_w}x{px_h} px ({dpi}dpi) に対し実測 {act_w}x{act_h} px "
            f"(実効 {eff_x:.1f}x{eff_y:.1f} dpi)。\n"
            f"  元 SVG: {svg_path} ({describe_size(info, dpi, px_w, px_h)})"
        )

    ppm = set_png_dpi(out_png, dpi, log=log)
    note = describe_size(info, dpi, act_w, act_h)
    if place_size_in:
        # 公称サイズと違う基準で描いたことを黙らせない
        note += (f" ※置く寸法 {base_w_in:.3f}x{base_h_in:.3f} in に合わせてラスタ化 "
                 "(公称サイズではなく配置後の寸法が基準)")
    if log:
        log(f"  png: {label or svg_path}: {note} [pHYs {ppm} px/m]")
    return {
        "width_px": act_w, "height_px": act_h, "dpi": dpi,
        "width_in": base_w_in, "height_in": base_h_in,
        "basis": info["basis"], "note": note, "guaranteed": True,
    }


def _render_png_unknown_size(svg_path, out_png, dpi, log, label):
    """寸法が決められない SVG を rsvg の既定描画で PNG にする。

    `-w/-h` を渡さない (rsvg の既定の大きさで描く)。目標 dpi は達成できないので
    **pHYs は書かない** (書くと「300dpi の画像」だと偽ることになる)。呼び出し側は
    返り値の guaranteed=False で「保証できていない図」を識別し、警告を出す。
    """
    out_png.parent.mkdir(parents=True, exist_ok=True)
    cmd = ["rsvg-convert", "-o", str(out_png), str(svg_path)]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        raise SvgRasterError(
            f"png 生成に失敗しました: {svg_path}\n  {' '.join(cmd)}\n  {res.stderr.strip()}"
        )
    act_w, act_h = png_pixel_size(out_png)
    note = (f"寸法指定なし (width/height も viewBox も無い) → rsvg の既定描画 {act_w}x{act_h} px。"
            f"**{dpi}dpi は保証されない** — 提出前に SVG ルートへ物理単位の width/height を付けること")
    if log:
        log(f"  png: {label or svg_path}: {note} [pHYs なし]")
    return {
        "width_px": act_w, "height_px": act_h, "dpi": None,
        "width_in": None, "height_in": None,
        "basis": "unknown", "note": note, "guaranteed": False,
    }
