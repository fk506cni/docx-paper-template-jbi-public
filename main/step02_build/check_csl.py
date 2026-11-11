#!/usr/bin/env python3
"""check_csl.py — 雑誌 CSL の出力を規定の公式例と 1 文字ずつ突き合わせる受入テスト。

BioHealth Informatics の引用様式は投稿可否に直結するため (docs/journal-bhi.md §3.1)、
規定に載っている出力例そのものを期待値として持ち、citeproc の実出力と機械的に照合する。
引用書式 (CSL・bib の書き方) を変えたら再実行する。

入力:
  --fixture <dir>   main.md / ref.bib / expected.txt を置いたフィクスチャ
                    (既定: data/dummy/bhi-csl)
  --journal <id>    profile.yaml の csl を解決する雑誌 (既定: bhi)

判定:
  文献リストの各エントリを expected.txt の各行と完全一致で比較する。
  1 件でも不一致なら exit 1。差異は行内の差分 (difflib) と、最初に食い違った
  文字位置・コードポイントを出す (en dash とハイフン等、目視で判別できない差のため)。

副次の出力 (判定には使わない・記録が目的):
  本文中の引用の実出力を data-cites つきで一覧する。複数引用・連続引用の書式は
  規定に記述が無く「規定と矛盾しない」の判定ができないため、実出力の記録を残す。
  上付きは ^{...} で示す。

コンテナ内で実行する (driver: scripts/check-csl.sh)。
"""

import argparse
import difflib
import io
import re
import subprocess
import sys
import unicodedata
import zipfile
from pathlib import Path

import panflute as pf
from lxml import etree

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "00_setup" / "lib"))
import journal_profile  # noqa: E402

JOURNALS_DIR = Path("data/journals")
DEFAULT_CSL = JOURNALS_DIR / "_default" / "_default.csl"


def resolve_csl(journal_id):
    """profile.yaml の csl を解決する (build_docx.py の _resolve_asset と同じ規則)。"""
    profile = journal_profile.load(journal_id)
    value = profile.get("csl")
    if value:
        cand = JOURNALS_DIR / journal_id / value
        if cand.is_file():
            return cand
        sys.exit(f"エラー: csl='{cand}' がありません")
    print(f"  警告: {journal_id} は csl 未指定です。_default (AMA 11th) で照合します")
    return DEFAULT_CSL


def render(md, csl, bib):
    """pandoc(crossref → citeproc) を通した AST を返す。"""
    cmd = [
        "pandoc", str(md),
        "--from", "markdown+east_asian_line_breaks",
        "--to", "json",
        "--filter", "pandoc-crossref",
        "--citeproc",
        f"--csl={csl}",
        f"--bibliography={bib}",
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        sys.exit(f"エラー: pandoc が失敗しました (exit {res.returncode})\n{res.stderr}")
    if res.stderr.strip():
        for line in res.stderr.strip().splitlines():
            print(f"  [pandoc] {line}")
    return pf.load(io.StringIO(res.stdout))


def to_text(elem):
    """上付きを ^{...} で示す stringify (引用書式の記録用)。

    panflute.stringify は書式を落とすため、Superscript / Subscript だけ手で括る。
    """
    if isinstance(elem, pf.Superscript):
        return "^{" + "".join(to_text(c) for c in elem.content) + "}"
    if isinstance(elem, pf.Subscript):
        return "_{" + "".join(to_text(c) for c in elem.content) + "}"
    if isinstance(elem, (pf.Space, pf.SoftBreak, pf.LineBreak)):
        return " "
    if isinstance(elem, pf.Str):
        return elem.text
    if hasattr(elem, "content"):
        return "".join(to_text(c) for c in elem.content)
    return pf.stringify(elem)


def collect_entries(doc):
    """文献リスト (Div.csl-entry) の各エントリを文字列で返す。"""
    entries = []

    def walk(elem, doc):
        if isinstance(elem, pf.Div) and "csl-entry" in elem.classes:
            entries.append(to_text(elem))
        return None

    doc.walk(walk)
    return entries


def split_number(text):
    """'1. Author…' から番号を落とす。番号が付いていなければそのまま返す。

    second-field-align="flush" のとき pandoc は番号を csl-left-margin span に分けるが、
    stringify すると本文と連結されるため、ここで先頭の "N." を機械的に落とす。
    """
    head, sep, rest = text.partition(".")
    if sep and head.strip().isdigit():
        return rest.strip()
    return text.strip()


def _inside_image(elem):
    """Image の alt テキスト内かどうか。

    pandoc 3 の Figure は Caption と Image を持ち、図キャプションは【両方】に入る。
    Image 側は docx では docPr@descr (代替テキスト) になり本文の run にはならないので、
    docx の上付き run と件数を突き合わせるときは数えない。
    """
    parent = getattr(elem, "parent", None)
    while parent is not None:
        if isinstance(parent, pf.Image):
            return True
        parent = getattr(parent, "parent", None)
    return False


def collect_citations(doc):
    """本文中の引用 (Cite) を (bib キー, 実出力) で返す。"""
    found = []

    def walk(elem, doc):
        if isinstance(elem, pf.Cite) and not _inside_image(elem):
            keys = " ".join(c.id for c in elem.citations)
            found.append((keys, to_text(elem)))
        return None

    doc.walk(walk)
    return found


W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def W(tag):
    return f"{{{W_NS}}}{tag}"


def docx_segments(docx_path):
    """docx の段落ごとに (テキスト, 上付きか) の連なりを返す。

    連続する同一書式の run はまとめる (pandoc は書式が変わる境目で run を割るため、
    `1)` が 2 run に分かれることがある)。
    """
    with zipfile.ZipFile(docx_path) as z:
        root = etree.fromstring(z.read("word/document.xml"))
    paras = []
    for p in root.iter(W("p")):
        segs = []
        for r in p.iter(W("r")):
            rpr = r.find(W("rPr"))
            va = rpr.find(W("vertAlign")) if rpr is not None else None
            is_sup = va is not None and va.get(W("val")) == "superscript"
            text = "".join(t.text or "" for t in r.iter(W("t")))
            if not text:
                continue
            if segs and segs[-1][1] == is_sup:
                segs[-1] = (segs[-1][0] + text, is_sup)
            else:
                segs.append((text, is_sup))
        if segs:
            paras.append(segs)
    return paras


# 引用らしい上付き断片: 数字で始まり閉じ括弧で終わる (`1)` / `1,4)` / `1–3)` / `4, p. 23)`)
# 文字集合は `p` だけでなく `a-z` にして、`sec.` / `chap.` / `para.` 等の
# locator ラベルを含む上付き (`4, sec. 3)`) も引用として数える (`p` だけだと数え落として誤って失敗する)。
CITE_SUP_RE = re.compile(r"^\d[\d,\s.a-z)–-]*\)$")
# 括弧がベースラインに落ちた形: 上付きが数字だけで終わり、直後の地の文が `)` で始まる
BARE_NUM_RE = re.compile(r"\d$")


def check_docx_superscript(docx_path, expected_citations):
    """docx の OOXML で `1)` が丸ごと上付きかを実測する。

    規定は「上付きの数字と閉じ括弧」("superscript Arabic numerals in closing parenthesis")。本テンプレートは閉じ括弧まで上付きにする。
    数字だけ上付きで閉じ括弧がベースラインに落ちていないことを、
    w:rPr/w:vertAlign val="superscript" で直接確かめる。
    """
    print("")
    print(f"-- docx の上付き実測: {docx_path} --")
    if not Path(docx_path).is_file():
        print(f"  NG: {docx_path} がありません (先に scripts/build.sh を実行してください)")
        return 1

    ng = 0
    cites = []
    for segs in docx_segments(docx_path):
        for i, (text, is_sup) in enumerate(segs):
            if not is_sup:
                continue
            nxt = segs[i + 1][0] if i + 1 < len(segs) else ""
            if BARE_NUM_RE.search(text) and nxt.startswith(")"):
                print(f"  NG: 閉じ括弧がベースラインに落ちています: 上付き='{text}' 直後='{nxt[:20]}'")
                ng += 1
            if CITE_SUP_RE.match(text):
                cites.append(text)

    for text in cites:
        print(f"  OK: 上付き run = '{text}' (数字と閉じ括弧が同一の上付き run)")

    if len(cites) < expected_citations:
        print(f"  NG: 上付きの引用が {len(cites)} 件しかありません "
              f"(AST 上の引用は {expected_citations} 件)")
        # 期待件数はフィクスチャ data/dummy/bhi-csl/main.md から数えた値なので、
        # 別原稿からビルドした docx を --docx に渡すと必ず件数が合わない。上の NG だけでは
        # 「上付きが足りない」と読め、入力の取り違えを引用様式の不具合と誤診させるのでヒントを添える。
        print("      ヒント: --docx に渡した docx がフィクスチャ data/dummy/bhi-csl から"
              "ビルドされたものか確認してください "
              "(bash scripts/build.sh --input data/dummy/bhi-csl --journal bhi --article-type original)")
        ng += 1
    else:
        print(f"  引用 {len(cites)} 件 / AST 上の引用 {expected_citations} 件")
    return ng


def load_expected(path):
    lines = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        s = raw.strip()
        if not s or s.startswith("#"):
            continue
        lines.append(s)
    return lines


# bhi.csl の language-note マクロは footgun を持つ。
#   - note を無条件に括弧で出す → 書誌管理ソフトの控えが文献リストに露出する
#   - language があるだけで "(in Japanese)" を出す → 非日本語言語が誤表示される
# CSL 側では自動で気づけないため、ここで bib を走査して助言的に警告する。
# 助言のみで exit code は変えない (note = {in German} という正規の回避策で誤失敗させないため)。
_BIB_ENTRY_RE = re.compile(r"@\w+\s*\{\s*([^,\s]+)")
_BIB_NOTE_RE = re.compile(r"^note\s*=", re.IGNORECASE)
_BIB_LANG_RE = re.compile(r"^lang(?:id|uage)\s*=\s*\{?\s*([A-Za-z][A-Za-z\-]*)", re.IGNORECASE)


def lint_bib(bib_path):
    """ref.bib の language-note 系 footgun を助言的に警告する (判定には影響しない)。"""
    warnings = []
    key = "?"
    for raw in bib_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("%"):
            continue
        m = _BIB_ENTRY_RE.match(line)
        if m:
            key = m.group(1)
            continue
        if _BIB_NOTE_RE.match(line):
            warnings.append(
                f"  警告: [{key}] に note フィールドがあります。note は文献リスト末尾へ"
                f"そのまま露出します。言語表記 (in German 等) 以外の控えが入っていないか"
                f"確認してください")
        ml = _BIB_LANG_RE.match(line)
        if ml and ml.group(1).lower() not in ("japanese", "ja", "ja-jp"):
            warnings.append(
                f"  警告: [{key}] の言語指定 '{ml.group(1)}' は出力が (in Japanese) になります"
                f" (CSL は変数の値を判定できないため)。非日本語文献は "
                f"note = {{in {ml.group(1)}}} を使ってください")
    return warnings


def first_diff(a, b):
    """最初に食い違う位置とコードポイントを返す (en dash / hyphen の見分けのため)。"""
    for i, (x, y) in enumerate(zip(a, b)):
        if x != y:
            return i, x, y
    if len(a) != len(b):
        i = min(len(a), len(b))
        x = a[i] if i < len(a) else ""
        y = b[i] if i < len(b) else ""
        return i, x, y
    return None


def describe(ch):
    if ch == "":
        return "(なし)"
    try:
        name = unicodedata.name(ch)
    except ValueError:
        name = "?"
    return f"{ch!r} U+{ord(ch):04X} {name}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fixture", default="data/dummy/bhi-csl")
    ap.add_argument("--journal", default="bhi")
    ap.add_argument("--docx", default=None,
                    help="ビルド済み docx を渡すと OOXML の上付きも実測する "
                         "(例: data/step02_build/main.docx)")
    args = ap.parse_args()

    fixture = Path(args.fixture)
    md, bib, exp = fixture / "main.md", fixture / "ref.bib", fixture / "expected.txt"
    for p in (md, bib, exp):
        if not p.is_file():
            sys.exit(f"エラー: {p} がありません")

    csl = resolve_csl(args.journal)
    print(f"== CSL 受入テスト: journal={args.journal}  csl={csl} ==")
    print(f"  fixture = {fixture}")

    doc = render(md, csl, bib)
    entries = [split_number(t) for t in collect_entries(doc)]
    expected = load_expected(exp)
    if not expected:
        sys.exit(f"エラー: {exp} に期待値が 1 件もありません (全行コメント/空)。"
                 f"受入テストが空振りするため中止します")
    citations = collect_citations(doc)

    lint_warnings = lint_bib(bib)
    if lint_warnings:
        print("")
        print("-- bib の助言的検査 (lint。判定には影響しない) --")
        for w in lint_warnings:
            print(w)

    print("")
    print("-- 本文中の引用 (実出力の記録。判定には使わない) --")
    for keys, text in citations:
        print(f"  [{keys}] -> {text}")

    print("")
    print("-- 文献リストの突合 --")
    ng = 0
    for i in range(max(len(entries), len(expected))):
        got = entries[i] if i < len(entries) else None
        want = expected[i] if i < len(expected) else None
        if got is None:
            print(f"  [{i + 1}] NG: 出力が足りません (期待: {want})")
            ng += 1
            continue
        if want is None:
            print(f"  [{i + 1}] NG: 期待値に無いエントリが出ました: {got}")
            ng += 1
            continue
        if got == want:
            print(f"  [{i + 1}] OK: {got}")
            continue
        ng += 1
        print(f"  [{i + 1}] NG")
        print(f"      期待: {want}")
        print(f"      実際: {got}")
        d = first_diff(want, got)
        if d:
            pos, w, g = d
            print(f"      最初の相違: {pos} 文字目  期待={describe(w)}  実際={describe(g)}")
        for line in difflib.unified_diff([want], [got], "expected", "actual",
                                         lineterm="", n=0):
            print(f"      {line}")

    total = max(len(entries), len(expected))
    if args.docx:
        ng += check_docx_superscript(args.docx, len(citations))
    else:
        print("")
        print("  警告: --docx 未指定のため、上付き閉じ括弧 (`1)` が丸ごと上付きか) は"
              "未検証です。")
        print("        data/step02_build/main.docx を渡すと OOXML の w:vertAlign で実測します。")

    print("")
    if ng:
        print(f"== NG {ng} 件 (文献リスト 全 {total} 件 + docx 実測) ==")
        return 1
    print(f"== 全 {len(expected)} 件が公式例と一致"
          f"{' / docx の上付きも一致' if args.docx else ''} ==")
    return 0


if __name__ == "__main__":
    sys.exit(main())
