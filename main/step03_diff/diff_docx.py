#!/usr/bin/env python3
"""diff_docx.py — 旧/新 2 版の Markdown から全領域差分 docx を生成する (コンテナ内本体)。

docs/architecture.md §2.3 / docs/design-fullarea-diff.md。pandiff は使わない。処理は次の通り:

  1. 旧版・新版を各 `pandoc -t json` で AST 化する (pandoc は全構造を無損失で保持)。
     フィルタは掛けない (crossref/citeproc は描画段で掛ける)。reader は defaults.yaml の
     `markdown+east_asian_line_breaks`、crossref メタも defaults から両版に注入される。
  2. ast_diff.diff_documents() で構造保持 二層差分 → マージ AST (構造温存 + 差分 span)。
  3. マージ AST を `pandoc -f json` で docx 化する。引数は build (§2.2) と同粒度:
     crossref → generic-style.lua → citeproc → color-diff.lua の順でフィルタを掛け、
     reference.docx / CSL / bibliography / resource-path / defaults.yaml を渡す。
  4. OOXML 後処理 (step02 共用 postprocess): 表罫線・ネイティブ SVG 埋込・textbox。
     さらに生成 docx の word/styles.xml へ文字スタイル DiffAdd/DiffDel を冪等注入する
     (雑誌提供テンプレが 2 スタイルを持たなくても差分色が出る)。注入定義は
     reference.docx を焼く patch_reference_docx.inject_diff_styles と同一 (単一の真実)。

雑誌プロファイル解決 (reference.docx / CSL の _default 継承) は build_docx と共通実装を流用する。

使い方 (通常は scripts/diff.sh 経由):
    python3 diff_docx.py --input-root data/dummy --journal _default \
        --old jank/old.md --new data/dummy/main.md \
        --out data/step03_diff/main_diff.docx [--no-embed-svg] [--no-relocate]
"""

import argparse
import io
import subprocess
import sys
import zipfile
from pathlib import Path

from lxml import etree

# step02_build (build_docx の profile 解決 / postprocess) と 00_setup/lib (styles 注入) を import 可能に
_THIS = Path(__file__).resolve().parent
sys.path.insert(0, str(_THIS))
sys.path.insert(0, str(_THIS.parent / "step02_build"))
sys.path.insert(0, str(_THIS.parent / "00_setup" / "lib"))

import panflute as pf  # noqa: E402

import ast_diff  # noqa: E402
import postprocess  # noqa: E402
import patch_reference_docx as prd  # noqa: E402
# profile は共通モジュール journal_profile で読む (build_docx の内部の読み込み関数は借りない)。
#   profile を読む処理を使う側は build_docx / package / validate と本ファイルの 4 箇所あり、
#   共通モジュール経由に揃えることで、差分経路もスキーマ既定値と記事種別の解決を通るようにする。
import journal_profile  # noqa: E402
from build_docx import _resolve_asset  # noqa: E402

DEFAULTS_YAML = "main/00_setup/defaults.yaml"
GENERIC_FILTER = "main/00_setup/filters/generic-style.lua"
COLOR_DIFF_FILTER = "main/00_setup/filters/color-diff.lua"


def _pandoc_to_ast(md_path):
    """Markdown を pandoc -t json でフィルタ無し AST 化し panflute Doc を返す。

    defaults.yaml を渡すので reader 拡張 (east_asian_line_breaks) と crossref メタが入る。
    crossref / citeproc / generic-style は描画段で掛けるため、ここでは掛けない。
    """
    cmd = ["pandoc", str(md_path), "--defaults", DEFAULTS_YAML, "-t", "json"]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        sys.exit(f"エラー: pandoc -t json が失敗しました ({md_path})\n{res.stderr}")
    return pf.load(io.StringIO(res.stdout))


def _inject_diff_styles_into_docx(docx_path):
    """生成 docx の word/styles.xml へ DiffAdd/DiffDel を冪等注入する。

    定義は patch_reference_docx.inject_diff_styles と共通 (単一の真実)。_default の
    reference.docx は既に 2 スタイルを持つが、雑誌提供テンプレ (持たない) でも差分色が出るよう
    描画後にも必ず注入する。inject_diff_styles は同 id を一度消してから付け直すため冪等。
    """
    with zipfile.ZipFile(docx_path, "r") as zin:
        parts = {item.filename: zin.read(item.filename) for item in zin.infolist()}
    styles_name = "word/styles.xml"
    if styles_name not in parts:
        print("  警告: word/styles.xml が無く DiffAdd/DiffDel を注入できません")
        return
    root = etree.fromstring(parts[styles_name])
    prd.inject_diff_styles(root)
    parts[styles_name] = etree.tostring(root, xml_declaration=True, encoding="UTF-8",
                                        standalone=True)
    with zipfile.ZipFile(docx_path, "w", zipfile.ZIP_DEFLATED) as zout:
        for name, data in parts.items():
            zout.writestr(name, data)
    print("  DiffAdd/DiffDel を styles.xml へ注入 (冪等)")


def build_diff(input_root, journal_id, old_md, new_md, out, embed_svg=True, no_relocate=False,
               article_type=None):
    input_root = Path(input_root)
    out = Path(out)
    old_md = Path(old_md)
    new_md = Path(new_md)
    for p in (old_md, new_md):
        if not p.is_file():
            sys.exit(f"エラー: 原稿が見つかりません: {p}")

    # 記事種別を解決する (差分は種別で出力を変えないが、未知種別の早期エラーのためここで解決。
    # build_docx.build() と同じ扱い)
    profile = journal_profile.load_resolved(journal_id, article_type)
    reference_doc = _resolve_asset(journal_id, profile.get("reference_doc"),
                                   "reference.docx", "reference_doc")
    csl = _resolve_asset(journal_id, profile.get("csl"), "_default.csl", "csl")

    resource_path = ["data/step01_figures", str(input_root / "figs"), "."]
    bib = input_root / "ref.bib"

    out.parent.mkdir(parents=True, exist_ok=True)

    # --- 1+2. 旧/新 AST 化 → 構造保持 二層差分 → マージ AST ---
    print(f"== 差分: {old_md} (旧) vs {new_md} (新) -> {out} ==")
    print(f"  journal={journal_id}  reference={reference_doc}  csl={csl}")
    old_doc = _pandoc_to_ast(old_md)
    new_doc = _pandoc_to_ast(new_md)
    merged = ast_diff.diff_documents(old_doc, new_doc)

    merged_json = str(out) + ".merged.json"
    with open(merged_json, "w", encoding="utf-8") as f:
        pf.dump(merged, f)

    # --- 3. マージ AST を docx 化 (crossref → generic-style → citeproc → color-diff) ---
    manifest = str(out) + ".images.tsv"
    cmd = [
        "pandoc", merged_json,
        "--defaults", DEFAULTS_YAML,
        "--from", "json",                     # defaults の from(markdown) を上書き
        "-M", f"image-manifest={manifest}",
        "--to", "docx",
        f"--reference-doc={reference_doc}",
        f"--resource-path={':'.join(resource_path)}",
        "--filter", "pandoc-crossref",
        "--lua-filter", GENERIC_FILTER,
        "--citeproc",
        f"--csl={csl}",
        "--lua-filter", COLOR_DIFF_FILTER,    # citeproc の後 (引用解決後に span を写像)
        f"--output={out}",
    ]
    if bib.is_file():
        cmd.append(f"--bibliography={bib}")
    else:
        print(f"  注意: {bib} が無いため文献解決なし")
    print("  pandoc " + " ".join(cmd[1:]))
    res = subprocess.run(cmd)
    if res.returncode != 0:
        sys.exit(f"エラー: pandoc (描画) が失敗しました (exit {res.returncode})")

    # --- 4. OOXML 後処理 (表罫線 / SVG 埋込 / textbox) + DiffAdd/DiffDel 注入 ---
    postprocess.process_docx(
        str(out),
        source_md=None,                       # 画像はマニフェスト (マージ AST 由来) で照合
        resource_path=resource_path,
        embed_svg=embed_svg,
        no_relocate=no_relocate,
        image_manifest=manifest,
    )
    _inject_diff_styles_into_docx(str(out))

    Path(manifest).unlink(missing_ok=True)
    Path(merged_json).unlink(missing_ok=True)
    print(f"== 完了: {out} ==")


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--input-root", required=True, help="図/文献の入力ルート (data/dummy または src)")
    p.add_argument("--journal", default="_default", help="雑誌プロファイル id (既定 _default)")
    p.add_argument("--old", required=True, help="旧版 Markdown")
    p.add_argument("--new", required=True, help="新版 Markdown")
    p.add_argument("--out", required=True, help="出力 diff docx パス")
    p.add_argument("--no-embed-svg", action="store_true", help="ネイティブ SVG 埋込をしない")
    p.add_argument("--no-relocate", action="store_true", help="textbox の page 配置移動をしない")
    # 注意: 差分が profile から読むのは reference_doc / csl の 2 キーだけで、記事種別は出力を変えない。
    # --article-type を受けるのは (1) 未知種別の早期エラー (2) build.sh と引数を揃えて README の
    # BHI 例 (diff.sh --journal bhi) で利用者が異常終了に当たらないようにするため。
    p.add_argument("--article-type", default=None,
                   help="記事種別 (article_types を持つ誌のみ。差分の出力は変えない)")
    args = p.parse_args(argv)
    build_diff(
        args.input_root, args.journal, args.old, args.new, args.out,
        embed_svg=not args.no_embed_svg, no_relocate=args.no_relocate,
        article_type=args.article_type,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
