#!/usr/bin/env python3
"""build_docx.py — 1 つの Markdown 原稿を投稿用 docx へ変換する (コンテナ内本体)。

docs/architecture.md §2.2。pandoc (crossref → generic-style.lua → citeproc) で docx 化し、postprocess.py で
OOXML 後処理 (表罫線・ネイティブ SVG 埋込・テキストボックス) を適用する。
docx-paper-template-pandoc コンテナ内で実行する (scripts/build.sh が driver)。

雑誌プロファイル (data/journals/<id>/profile.yaml) から reference.docx と CSL を解決する。
profile の csl / reference_doc が null・不在なら _default のものを継承する (docs/profile-schema.md)。

使い方:
    python3 build_docx.py --input-root data/dummy --journal _default \
        --doc main.md --out data/step02_build/main.docx [--no-embed-svg] [--no-relocate]
"""

import argparse
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import postprocess  # noqa: E402

# profile の読み込み・既定値・記事種別解決は共通モジュールに集約 (docs/profile-schema.md)
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "00_setup" / "lib"))
import journal_profile  # noqa: E402

JOURNALS_DIR = Path("data/journals")
DEFAULT_ID = "_default"
DEFAULTS_YAML = "main/00_setup/defaults.yaml"
GENERIC_FILTER = "main/00_setup/filters/generic-style.lua"


def _inherited_layout_mismatches(journal_id):
    """journal_id の体裁キーが _default と食い違う箇所を [(キー, 誌の値, _default の値)] で返す。

    reference.docx を _default から継承すると、profile.yaml に書いた体裁は
    一切効かない。どのキーが効いていないのかを名前で示さないと利用者が気づけない。
    体裁キーの一覧と値の解釈は journal_profile 側が正 (docs/profile-schema.md)。
    """
    own = journal_profile.load(journal_id)
    default = journal_profile.load(DEFAULT_ID)
    out = []
    for key in journal_profile.LAYOUT_KEYS:
        mine, theirs = own.get(key), default.get(key)
        if mine is not None and str(mine).strip().lower() != str(theirs).strip().lower():
            out.append((key, mine, theirs))
    return out


def _warn_stale_reference(journal_id, reference_doc):
    """雑誌固有 reference.docx の実体裁が profile.yaml とずれていたら警告する。

    体裁は reference.docx に焼き込む設計なので、profile.yaml を編集して
    make-reference.sh の再実行を忘れると古い体裁のまま投稿まで進む。_inherited_layout_mismatches の
    警告は「_default を継承した」場合しか捕まえられないため、「自誌の reference.docx はあるが古い」
    場合をここで捕まえる (BHI は行間・行番号・ページ番号がいずれも規定必須)。
    """
    profile = journal_profile.load(journal_id)
    for key, want, got in journal_profile.layout_mismatches(profile, reference_doc):
        print(f"  警告: {reference_doc} の体裁が profile.yaml と食い違っています "
              f"({key}: profile={want!r} != reference.docx={got!r})。"
              f"'bash data/journals/make-reference.sh {journal_id}' で再生成してください")


def _resolve_asset(journal_id, profile_value, default_rel, kind):
    """雑誌アセット (reference.docx / CSL) を解決する。

    profile_value が指す雑誌固有ファイルがあればそれを、無ければ _default のものを返す。
    """
    if profile_value:
        cand = JOURNALS_DIR / journal_id / profile_value
        if cand.is_file():
            if kind == "reference_doc":
                # 焼き込み済みの体裁が profile.yaml とずれていないか検算する
                _warn_stale_reference(journal_id, cand)
            return cand
        print(f"  警告: {kind}='{cand}' が無いため _default を使用します")
    elif kind == "csl":
        # csl: null は _default (AMA 11th) を継承する。誌の規定が別の引用様式 (角括弧の
        # Vancouver など) のとき、黙って継承すると規定と異なる引用表記が警告なしに出るので、
        # 継承したことを必ず知らせる。重要度は上のフォールバックと揃えて「警告:」とする。
        print("  警告: csl 未指定。_default (AMA 11th) を継承します。"
              "雑誌規定と一致するか確認してください")
    elif kind == "reference_doc":
        # reference_doc: null は _default の体裁を継承する (csl と対称に扱う)。
        # 体裁は reference.docx に焼き込む設計なので、継承した時点で profile.yaml の体裁値は
        # 効いていない。たとえば profile.yaml に single / 行番号なし / 10.5pt / 15mm と書いても、
        # 出力は _default の double / 連続行番号 / 12pt / 25mm になる。継承したことと、
        # 効いていないキー名を必ず知らせる。
        print("  警告: reference_doc 未指定。_default の体裁 "
              "(double / 連続行番号 / Times New Roman 12pt / 余白 25mm / A4) を継承します。"
              "雑誌規定と一致するか確認してください")
        mismatches = _inherited_layout_mismatches(journal_id)
        if mismatches:
            detail = ", ".join(f"{k}: profile={v!r} != _default={d!r}" for k, v, d in mismatches)
            print(f"  警告: profile.yaml の体裁が _default と食い違っています ({detail})。"
                  f"これらは出力に反映されません — "
                  f"'bash data/journals/make-reference.sh {journal_id}' で "
                  f"reference.docx を生成し reference_doc を切り替えてください")
    default_path = JOURNALS_DIR / DEFAULT_ID / default_rel
    if not default_path.is_file():
        sys.exit(f"エラー: 既定 {kind} {default_path} がありません "
                 f"(_default の reference.docx は make-reference.sh で生成してください)")
    return default_path


def build(input_root, journal_id, doc, out, embed_svg=True, no_relocate=False,
          article_type=None):
    input_root = Path(input_root)
    out = Path(out)
    src_md = input_root / doc
    if not src_md.is_file():
        sys.exit(f"エラー: 原稿が見つかりません: {src_md}")

    # 記事種別を解決する (build は種別で出力を変えないが、未知の種別を早くエラーにするためここで解決)
    profile = journal_profile.load_resolved(journal_id, article_type)
    reference_doc = _resolve_asset(journal_id, profile.get("reference_doc"),
                                   "reference.docx", "reference_doc")
    csl = _resolve_asset(journal_id, profile.get("csl"), "_default.csl", "csl")

    resource_path = ["data/step01_figures", str(input_root / "figs"), "."]
    bib = input_root / "ref.bib"

    out.parent.mkdir(parents=True, exist_ok=True)

    # 画像マニフェスト: generic-style.lua が pandoc AST から出現順に画像を書き出し、
    # postprocess.py が件数照合・埋込対象 SVG 解決に使う。
    manifest = str(out) + ".images.tsv"

    cmd = [
        "pandoc", str(src_md),
        "--defaults", DEFAULTS_YAML,
        "-M", f"image-manifest={manifest}",
        "--to", "docx",
        f"--reference-doc={reference_doc}",
        f"--resource-path={':'.join(resource_path)}",
        "--filter", "pandoc-crossref",
        "--lua-filter", GENERIC_FILTER,
        "--citeproc",
        f"--csl={csl}",
        f"--output={out}",
    ]
    if bib.is_file():
        cmd.append(f"--bibliography={bib}")
    else:
        print(f"  注意: {bib} が無いため文献解決なし (引用があるなら ref.bib を用意してください)")

    print(f"== ビルド: {src_md} -> {out} ==")
    print(f"  journal={journal_id}  reference={reference_doc}  csl={csl}")
    print("  pandoc " + " ".join(cmd[1:]))
    res = subprocess.run(cmd)
    if res.returncode != 0:
        sys.exit(f"エラー: pandoc が失敗しました (exit {res.returncode})")

    # --- 行番号の適用範囲 ---
    # line_numbers_scope: all (既定) / manuscript (本文 main.md だけに行番号を付ける)。
    # 行番号は査読者が**本文**の位置を指し示すための体裁なので、カバーレターや査読対応レポートに
    # まで付くのは筋が悪い (build は 3 文書を同じ reference.docx で変換するため実際に付く)。
    # 未指定なら全文書に付く。
    # 既定値は journal_profile.DEFAULTS が敷く ("all")。`or "all"` は明示 null への保険。
    scope = str(profile.get("line_numbers_scope") or "all").lower()
    if scope not in ("all", "manuscript"):
        print(f"  警告: line_numbers_scope の値 '{profile.get('line_numbers_scope')}' は不正です "
              "(有効: all / manuscript)。'all' (既定) として扱います")
        scope = "all"
    no_line_numbers = (scope == "manuscript" and doc != "main.md")

    # --- OOXML 後処理 (表罫線 / SVG 埋込 / textbox / 行番号の除去) ---
    postprocess.process_docx(
        str(out),
        source_md=str(src_md),
        resource_path=resource_path,
        embed_svg=embed_svg,
        no_relocate=no_relocate,
        image_manifest=manifest,
        no_line_numbers=no_line_numbers,
    )
    # manifest は削除せず保持する。step05 (package.py) が図の数え方を build と一致させるため
    # main.docx.images.tsv を読む (原稿を素の正規表現で数えると取りこぼす図があるため)。
    # data/step02_build/* は gitignored。
    print(f"  画像マニフェスト保持: {manifest} (step05 が参照)")
    print(f"== 完了: {out} ==")


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--input-root", required=True, help="原稿ルート (data/dummy または src)")
    p.add_argument("--journal", default=DEFAULT_ID, help="雑誌プロファイル id (既定 _default)")
    p.add_argument("--doc", default="main.md", help="原稿ファイル (input-root 相対。既定 main.md)")
    p.add_argument("--out", required=True, help="出力 docx パス")
    p.add_argument("--no-embed-svg", action="store_true", help="ネイティブ SVG 埋込をしない")
    p.add_argument("--no-relocate", action="store_true", help="textbox の page 配置移動をしない")
    # 注意: build が profile から読むのは reference_doc / csl の 2 キーだけで、記事種別は出力を
    # 変えない。--article-type は (1) 未知種別の早期エラー (2) build.sh の provenance 記録
    # (data/step02_build/.journal の 2 行目) のために受ける。
    p.add_argument("--article-type", default=None,
                   help="記事種別 (article_types を持つ誌のみ。build の出力は変えない)")
    args = p.parse_args(argv)
    build(
        args.input_root, args.journal, args.doc, args.out,
        embed_svg=not args.no_embed_svg, no_relocate=args.no_relocate,
        article_type=args.article_type,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
