#!/usr/bin/env python3
"""compare-snapshots.py — `jank/baseline/` の 2 スナップショットを【内容】で比較する。

回帰判定の受入テスト。`scripts/baseline.sh` / `scripts/baseline-bhi.sh` が撮った
スナップショットの対を比べ、成果物の中身が変わっていないかを見る。

    python3 scripts/compare-snapshots.py <比較元の接尾辞> <比較先の接尾辞>
    例: python3 scripts/compare-snapshots.py before after

docx は zip で、pandoc がエントリのタイムスタンプと docProps/core.xml の作成/更新日時を
毎回入れるためバイト比較では必ず差が出る。回帰判定は「zip 内の各パートの中身が同じか」で行う。
比較対象から外すもの:
  - docProps/core.xml (作成/更新日時)
  - ログ中の一時ファイル名 (jank/diff_old_<pid>.md) と Inkscape の時刻つき警告

【置き場所】道具は git で追跡する `scripts/` に置き、**スナップショットの実体 (数百 MB) は
`jank/baseline/` に置く** (git 管理外)。
"""
import glob
import re
import sys
import zipfile
from pathlib import Path

IGNORE_PARTS = {"docProps/core.xml"}
# PDF は Ghostscript/Inkscape が生成時刻と文書 ID を毎回書くため、そこだけ潰して比較する
PDF_NOISE = re.compile(rb"(/CreationDate|/ModDate)\s*\([^)]*\)|<[0-9A-Fa-f]{32}>")
NOISE = [
    (re.compile(r"jank/diff_old_\d+\.md"), "jank/diff_old_<pid>.md"),
    (re.compile(r"\(inkscape:\d+\): WARNING \*\*: \d+:\d+:\d+\.\d+"), "(inkscape): WARNING <t>"),
    # reference.docx を持たない作業ツリー (clone した直後) で撮った回だけに出る行。成果物は変わらない
    (re.compile(r"^-- data/journals/[^/\n]+/reference\.docx が無いので生成します[^\n]*\n?", re.M), ""),
    # リポジトリの絶対パス (別のディレクトリで撮ったスナップショット同士・ホストとコンテナのパスの違い)
    (re.compile(r"(?<![\w.~:/-])/(?:[^\s/'\"]+/)+?(?=(?:data|jank|docker|main|scripts|src|publish)/)"), "<ROOT>/"),
]


def norm_log(text):
    for pat, rep in NOISE:
        text = pat.sub(rep, text)
    return text


def docx_parts(path):
    with zipfile.ZipFile(path) as z:
        return {n: z.read(n) for n in sorted(z.namelist()) if n not in IGNORE_PARTS}


def compare(a, b):
    diffs = []
    files_a = {p.relative_to(a) for p in a.rglob("*") if p.is_file()}
    files_b = {p.relative_to(b) for p in b.rglob("*") if p.is_file()}
    for only, side in ((files_a - files_b, a), (files_b - files_a, b)):
        for f in sorted(only):
            diffs.append(f"片側のみ ({side.name}): {f}")
    for f in sorted(files_a & files_b):
        pa, pb = a / f, b / f
        if pa.suffix.lower() in (".docx", ".pptx", ".xlsx"):
            if docx_parts(pa) != docx_parts(pb):
                pda, pdb = docx_parts(pa), docx_parts(pb)
                changed = [k for k in set(pda) | set(pdb) if pda.get(k) != pdb.get(k)]
                diffs.append(f"docx 内容差: {f} -> {sorted(changed)}")
        elif pa.suffix.lower() in (".log", ".txt", ".md", ".tsv", ".yaml", ".csl"):
            ta = norm_log(pa.read_text(encoding="utf-8", errors="replace"))
            tb = norm_log(pb.read_text(encoding="utf-8", errors="replace"))
            if ta != tb:
                import difflib
                d = list(difflib.unified_diff(ta.splitlines(), tb.splitlines(),
                                              str(f) + " (pre)", str(f) + " (post)", lineterm="", n=0))
                diffs.append("テキスト差: " + "\n    ".join(d))
        elif pa.suffix.lower() == ".pdf":
            if PDF_NOISE.sub(b"X", pa.read_bytes()) != PDF_NOISE.sub(b"X", pb.read_bytes()):
                diffs.append(f"PDF 内容差: {f}")
        else:
            if pa.read_bytes() != pb.read_bytes():
                diffs.append(f"バイナリ差: {f}")
    return diffs


def main():
    base = Path("jank/baseline")
    pre_suffix, post_suffix = sys.argv[1], sys.argv[2]
    total = 0
    # 対象誌は名前を固定で持たず、jank/baseline/<誌>__<suffix> のディレクトリから拾う。
    # bhi は入力ルートが data/dummy/bhi なので別スクリプト (scripts/baseline-bhi.sh) で撮るが、
    # 比較は同じ物差しで行いたい。誌を固定のリストで持つと、bhi を撮っても黙って比較対象外になり、
    # 『差分 0 件』という誤った安心を得る。
    # どちらか片方にしか無い誌は「スナップショットがありません」として差分に数える。
    journals: set[str] = set()
    for suffix in (pre_suffix, post_suffix):
        tail = f"__{suffix}"
        for d in base.glob(f"*{glob.escape(tail)}"):
            if d.is_dir():
                journals.add(d.name[: -len(tail)])
    if not journals:
        print(f"スナップショットがありません: {base}/*__{pre_suffix} / {base}/*__{post_suffix}")
        print("\n== 差分 1 件 ==")
        return 1
    # 表示順は _default を先頭に、残りは名前順 (baseline.sh → baseline-bhi.sh の撮影順とは限らない)
    for j in sorted(journals, key=lambda x: (x != "_default", x)):
        a, b = base / f"{j}__{pre_suffix}", base / f"{j}__{post_suffix}"
        print(f"===== {j} =====")
        if not a.is_dir() or not b.is_dir():
            print(f"  スナップショットがありません: {a} / {b}")
            total += 1
            continue
        diffs = compare(a, b)
        if not diffs:
            print("  差分なし (内容一致)")
        for d in diffs:
            print(f"  {d}")
            total += 1
    print(f"\n== 差分 {total} 件 ==")
    return 1 if total else 0


if __name__ == "__main__":
    sys.exit(main())
