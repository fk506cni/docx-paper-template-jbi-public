#!/usr/bin/env python3
"""package.py — 投稿パッケージ組立 (コンテナ内本体)。

docs/architecture.md §2.5 / §3。雑誌プロファイル (data/journals/<id>/profile.yaml) に従い、ビルド済みの
docx (step02) と差分 docx (step03)・図 (step01) を整形・命名・集約して
data/output/<journal>/ に提出一式を作る。docx-paper-template-pandoc コンテナ内で実行する
(scripts/package.sh が driver)。

【モード (図の扱い)】profile.figures.embed と --mode で決まる:
  - draft (草稿, embed=true)  : 図を埋め込んだ manuscript.docx をそのまま提出 (data/step02_build/main.docx)。
  - final (最終, embed=false) : manuscript から図を取り除き [Figure N about here] のプレースホルダに置換し
                                (図キャプション=凡例は残す)、図を雑誌指定の形式/解像度/命名で figures/ に分離出力。
  --mode で profile を上書きできる (ダミーで両モードを検証するため)。

【図形式の対応状況 (docs/profile-schema.md)】図の生成経路は svg→pdf (svg-conversion) / svg→png (rsvg) /
  svg→pptx (svg_pptx) の 3 つ。profile.figures.formats の先頭を「主形式」とし、
  pdf→PDF / png→PNG / pptx→PPTX。tiff は PNG、eps は PDF へフォールバックし警告する
  (経路追加は将来。docs/profile-schema.md)。ただし代替先が profile.submission.figure_formats
  (定義時) に無い場合は警告でなくエラーで停止する。
  **生成経路が無い形式 (未知の綴り) は pdf へ代替せずエラーで停止する**
  (既定の代替先を pdf にすると、PDF 図を禁じる誌でも注意 1 行だけで PDF 図が出てしまうため)。
  png は svg_raster が物理サイズから画素数を計算して 300dpi 等を保証する (届かなければエラー)。
  pptx は 1 図 = 1 pptx = 1 スライドで SVG をベクターのまま埋め込み、同じ svg_raster で作った PNG
  フォールバックを同梱する。**元がラスタの図は pptx に包まず画像ファイルのまま出す**
  (規定は PowerPoint を受け付ける形式に挙げるだけで、画像を包むことは求めていない)。一次ソースの pptx が図の隣に在れば**無変換でコピー**する (案 A)。
  Inkscape が要る変換 (pdf 化 / text_to_path のアウトライン化) は svg-conversion コンテナで行うため
  figure-plan サブコマンドが必要な変換を列挙し、package.sh (ホスト) が駆動する。

サブコマンド:
  package.py figure-plan --input-root <dir> --journal <id> [--mode m] [--format f] [--font-handling h]
      [--slide-fit f] [--keep-figures]
      → 最終モードで svg-conversion が要る変換を TSV (src<TAB>out<TAB>embed<TAB>kind) で stdout に列挙。
        kind=pdf         : svg→pdf (「非 mermaid svg」のみ。mermaid は mmdc 正本 pdf を保持)
        kind=outline-svg : svg→アウトライン化 svg (pptx 経路で figures.pptx.text_to_path=true のとき)
        embed=1 なら convert.sh --embed-fonts。診断は stderr。
  package.py assemble --input-root <dir> --journal <id> [--mode m] [--format f] [--dpi n]
      [--font-handling h] [--slide-fit f] [--keep-figures] [--no-validate]
      → data/output/<journal>/ に manuscript / figures / revise-report / cover-letter (+ diff) を集約。

【提出構成の組み替え】最終モードでは profile に応じて manuscript.docx の構成も変える
  (実装は relocate.py):
    tables.placement: end          → 本文中の表を末尾へ移し `[Table N about here]` を残す
    tables.placement: separate     → 本文中の表を外し `[Table N about here]` を残して、
                                     `tables/TableN.docx` に 1 表 1 ファイルで出す
                                     (題 + 表 + 凡例。write_table_files)
    figures.legends_section: <題>  → 図の題+凡例を References の後の新ページへ集約
    tables.allow_color: false      → 表の網掛け・文字色・セル色を検出して警告 (docx 層の lint。
                                     数値の桁区切りカンマは Markdown 層 = validate.py の担当)
  あわせて `<INPUT_ROOT>/supplementary/` を無変換で複製し (動画は limits.video_mb を検査)、
  `submission` ブロックを持つ誌には提出マニフェスト `SUBMISSION.md` を書く。
  **これらのキーを持たない誌では何も起きない**。
"""

import argparse
import re
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import validate as validate_mod  # noqa: E402
# 提出構成の組み替え (表末尾移設 / Figure Legends 集約) と表の体裁 lint は relocate.py に分けてある
import relocate as relocate_mod  # noqa: E402

# profile の読み込み・既定値・記事種別解決は共通モジュールに集約 (docs/profile-schema.md)
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "00_setup" / "lib"))
import journal_profile  # noqa: E402
# 300dpi を保証する svg→png は step01 と共通モジュールを使う
import svg_raster  # noqa: E402
# ベクター提出 (1 図 = 1 pptx = 1 スライド) は共通モジュールへ
import svg_pptx  # noqa: E402

# profile.yaml の探索は journal_profile.JOURNALS_DIR が持つ (本モジュールには JOURNALS_DIR を置かない)。
DEFAULT_ID = "_default"
FIG_ROOT = Path("data/step01_figures")          # 正規化済み図ツリー (figs/<rel>)
BUILD_DIR = Path("data/step02_build")
DIFF_DIR = Path("data/step03_diff")
# step05 が作る中間派生物 (`<stem>.outline.svg` など) の置き場。これは step01 の生成物ではないので
# 図ツリー (FIG_ROOT) には書かない — 「コードとデータを分離し、ステップごとに data/stepNN_*/ へ出す」
# という本テンプレの規約 (CLAUDE.md 「Step-by-Step Pipeline」) に従うため。図ツリーに置くと、
# 原稿の図の隣に提出用の派生物が混ざり、図ツリーを走査する受入テスト (check_dpi) が派生物を
# 名前で除外しなければならなくなる。
PKG_DIR = Path("data/step05_package")
OUTPUT_ROOT = Path("data/output")

# OOXML 名前空間 (図除去で使う最小限)
W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
WP_NS = "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"


def W(tag):
    return f"{{{W_NS}}}{tag}"


def WP(tag):
    return f"{{{WP_NS}}}{tag}"


# =====================================================================
# プロファイル解決
# =====================================================================

def load_profile(journal_id, article_type=None):
    """profile.yaml を読み、既定値と記事種別を解決した dict を返す (journal_profile へ委譲)。"""
    return journal_profile.load_resolved(journal_id, article_type)


def _figures_cfg(profile):
    fig = profile.get("figures") or {}
    return fig if isinstance(fig, dict) else {}


def resolve_mode(profile, mode_override):
    """draft / final を解決する。--mode 優先、無ければ profile.figures.embed (true→draft)。"""
    if mode_override in ("draft", "final"):
        return mode_override
    embed = _figures_cfg(profile).get("embed", True)
    return "draft" if embed else "final"


def resolve_format(profile, fmt_override):
    """図の主形式 (profile.figures.formats[0] か --format)。小文字化して返す。"""
    if fmt_override:
        fmt = fmt_override.lower()
        # --format の受入値を検証する。受入値を絞らないと、綴り違い ('pnj' 等) が
        # 既定の代替に落ちて**黙って別の形式に化ける**。指定できる値は「生成経路がある形式 +
        # 生成非対応と分かっている形式」に限り、それ以外は打鍵ミスとして即座に止める。
        if fmt not in KNOWN_FORMATS:
            # 第 1 文で列挙するのは「いま使える値」だけにする。KNOWN_FORMATS を全部並べると、
            # 指定すると別の理由で必ず停止する値 (jpeg/jpg) まで候補に見え、打鍵ミスを直そうとして
            # いる利用者が使えない値へ打ち直して 2 度目のエラーを踏む。
            unusable = sorted(KNOWN_FORMATS - GENERATABLE_FORMATS)
            sys.exit(
                f"エラー: --format '{fmt_override}' は認識できません。\n"
                f"  いま使えるのは {'/'.join(sorted(GENERATABLE_FORMATS))} です。\n"
                f"  ({'/'.join(unusable)} は綴りとしては認識しますが、指定すると停止します — "
                "線画に不向きなため生成非対応)。"
            )
    else:
        formats = _figures_cfg(profile).get("formats") or ["pdf"]
        if isinstance(formats, str):
            formats = [formats]
        fmt = str(formats[0]).lower() if formats else "pdf"
    # jpeg/jpg は「代替」として黙って png に落とさず、明示エラーにする。
    # 本テンプレが作る図は SVG のベクター線画で、JPEG は非可逆圧縮のため
    # 線・文字の輪郭が劣化する = 線画に最も不向きな形式である。BHI は PNG / TIF も受け付けるので
    # 「jpeg 指定で png が出る」という紛らわしい選択肢は置かない
    # (submission.figure_formats に jpeg を残すのは「投稿系が受け付ける形式」の記録であって
    # 生成できるという意味ではない)。
    if fmt in ("jpeg", "jpg"):
        sys.exit(
            "エラー: 図形式 'jpeg' は生成できません。本テンプレが線画 (SVG) から"
            "作れるラスタは PNG のみで、JPEG は非可逆圧縮のため線・文字の輪郭が劣化します。\n"
            "  BHI が受け付ける PNG / TIF のうち、--format png を使ってください。"
        )
    return fmt


# 主形式 -> (実際に生成する形式, フォールバックか否か)。
# 生成経路は pdf (svg→pdf。svg-conversion) / png (svg_raster。rsvg) / pptx (svg_pptx) の 3 つ。
_EXPORT_ROUTES = {
    "pdf":  ("pdf", False),
    "png":  ("png", False),
    "pptx": ("pptx", False),    # 1 図 = 1 pptx = 1 スライド (SVG 埋込 + PNG フォールバック)
    "eps":  ("pdf", True),      # ベクター: pdf を代替 (EPS ネイティブ経路は未実装)
    "tiff": ("png", True),      # ラスタ: png を代替 (TIFF ネイティブ経路は意図的に用意していない。docs/profile-schema.md)
    "tif":  ("png", True),
}
GENERATABLE_FORMATS = frozenset(_EXPORT_ROUTES)          # --format で生成まで行ける値
KNOWN_FORMATS = GENERATABLE_FORMATS | {"jpeg", "jpg"}    # 綴りとして認識する値


def resolved_export(fmt):
    """主形式 -> 実際に生成する形式 (pdf / png) と、フォールバックか否か。

    **未知の形式を pdf に代替しない**。既定の代替先を pdf にすると、PDF を明確に禁止する誌 (BHI) で
    プロファイルを置いた直後に `--mode final` を回したときに**規定違反の PDF 図**が
    `figures/Figure1.pdf` として生成される (停止を check_export_allowed の受入形式照合だけに
    頼ると、`submission.figure_formats` を持たない誌では素通りする)。

    生成経路が無い形式に対しては **(None, True)** を返す。実際に図を出す直前で
    `require_export_route()` がエラー停止させる。ここで即座に sys.exit しないのは、
    草稿モード (--mode draft) や --keep-figures では図を生成しないため — 主形式に生成経路が
    無くても草稿ビルドは通す必要がある。
    """
    fmt = (fmt or "pdf").lower()
    return _EXPORT_ROUTES.get(fmt, (None, True))


def require_export_route(fmt, export):
    """図を実際に生成する直前に、生成経路の無い形式で停止する。

    「落ちずに規定違反物を出す」ことを防ぐのが目的なので、既定代替 (pdf) は用意しない。
    """
    if export is not None:
        return
    # ここに来るのは「未知の綴り」だけ (pdf / png / pptx はすべて生成経路を持つ)。
    sys.exit(
        f"エラー: 図形式 '{fmt}' の生成経路がありません。\n"
        f"  生成できるのは {'/'.join(sorted(GENERATABLE_FORMATS))} です。"
        "'--format' で明示指定してください (未知の形式を pdf などへ黙って代替することはしません)。"
    )


# 図形式の表記ゆれ (submission.figure_formats との照合用)
_FMT_ALIASES = {"tif": "tiff", "jpg": "jpeg"}


def check_export_allowed(profile, fmt, export, fallback, allow_disallowed=False):
    """実際に生成する図形式を誌の受入形式 (submission.figure_formats) と照合する。

    代替 (tiff→png / eps→pdf) の先を受け付けない誌 (BHI は PDF を受け付けない) では、「規定が
    禁止する形式の図が注意 1 行だけで生成される」事故が起きる。禁止形式へは黙って代替せず停止する。
    submission.figure_formats 未定義の誌は警告つきフォールバックのまま。

    照合は**代替が起きたときに限らず**、「実際に生成する形式」に対して常に行う。代替のときだけ
    照合すると、BHI で `--format pdf` のように「規定が禁止しているが本テンプレが生成できる形式」を
    明示指定したときに代替に当たらず、受入形式外の図が警告 1 行も無く生成される (実測)。
    外れたときの扱いは経路で分ける:
      - fallback=True  (作れないので代用した) → エラーで停止
      - fallback=False (利用者が明示指定し、その形式を生成できる) → **確認の一段を要求する**
        `--allow-disallowed-format` があれば停止せず警告を返す。

    fallback=False のときに警告どまりで生成すると、BHI で `--format pdf` だけが終了コード 0 で
    `Figure1.pdf` / `Figure2.pdf` を出す (実測)。`png` と `pdf` は 2 文字違いで、警告は出るものの
    最後は「パッケージ完了」で終わるため、**打ち間違いで規定違反の図一式が揃う**。
    「利用者の明示指定を尊重する」は維持しつつ (専用オプションを付ければ通る)、
    *打ち間違い* と *意図した指定* を区別できるようにする。
    `submission.figure_formats` を持たない誌は冒頭で None を返すため無影響。
    返り値: 警告メッセージ (str) または None。停止する場合は返らない。
    """
    allowed = (profile.get("submission") or {}).get("figure_formats")
    if not allowed:
        return None
    norm = {_FMT_ALIASES.get(str(a).lower(), str(a).lower()) for a in allowed}
    if _FMT_ALIASES.get(export, export) in norm:
        return None
    if fallback:
        sys.exit(
            f"エラー: 図形式 '{fmt}' の生成経路は未実装で、代替の '{export}' はこの誌の"
            f"受入形式 {allowed} に含まれません (禁止形式へ黙って代替しません)。\n"
            f"  受入形式内で生成できる形式 (例: --format png) を指定してください。"
        )
    if not allow_disallowed:
        sys.exit(
            f"エラー: 図形式 '{export}' はこの誌の受入形式 {allowed} に含まれません"
            f"。このまま出しても投稿系で受け付けられません。\n"
            f"  提出用には受入形式内の形式を指定してください (例: --format png)。\n"
            f"  受入形式外と承知のうえで生成する場合だけ '--allow-disallowed-format' を付けてください。"
        )
    return (
        f"★要注意: 生成する図形式 '{export}' はこの誌の受入形式 {allowed} に含まれません "
        f"(--allow-disallowed-format による明示同意あり)。"
        f"このまま提出しても投稿系で受け付けられません。"
        f"提出用には受入形式内 (例: --format png) を指定してください。"
    )


def resolve_dpi(profile, dpi_override):
    # dpi は画素数計算に直結するので、非数値・非正値を
    # トレースバックでなくエラーメッセージで止める。
    #
    # プロファイル側も --dpi と同じ基準で検証する。
    # `(_figures_cfg(profile).get("dpi") or 300)` のように書くと (a) `dpi: 0` が or 演算で 300 に化けて
    # 「正の整数で指定してください」に到達せず、(b) `dpi: 300.5` を int() が黙って 300 に
    # 切り捨てる (同じ値を --dpi で渡すとエラーになるので挙動が非対称になる)。
    # 解像度は画素数に直結するので、黙って別の値になることは避ける。
    if dpi_override is not None:
        src, raw = "--dpi", dpi_override
    else:
        cfg = _figures_cfg(profile)
        if "dpi" in cfg and cfg["dpi"] is not None:
            src, raw = "profile.figures.dpi", cfg["dpi"]
        else:
            return 300
    # 小数表記 (300.5 / 300.0) は --dpi と同じ基準で弾く。int(float) の黙った切り捨てを防ぐ。
    if not re.fullmatch(r"\s*[+-]?\d+\s*", str(raw)):
        sys.exit(f"エラー: {src} の値 '{raw}' が整数ではありません。")
    dpi = int(str(raw).strip())
    if dpi <= 0:
        sys.exit(f"エラー: {src} の値 '{raw}' は正の整数で指定してください。")
    return dpi


def resolve_font_handling(profile, fh_override):
    if fh_override in ("outline", "embed"):
        return fh_override
    return str(_figures_cfg(profile).get("font_handling") or "outline").lower()


# --- pptx 経路の設定 (profile.figures.pptx。既定は journal_profile.DEFAULTS) ---
PPTX_MODES = ("svg-blob", "passthrough", "native-shapes")
PPTX_SLIDE_FITS = ("figure", "fixed")


def resolve_pptx_cfg(profile, dpi, slide_fit_override=None):
    """profile.figures.pptx を解決して dict(mode, slide_fit, png_fallback_dpi, text_to_path) を返す。

    値の検証はここで一括して行い、綴り違いを黙って既定へ倒さない
    (図形式の解決と同じ方針。`--format pnj` が黙って別の形式に化けるのを防ぐのと同じ理由)。
    `png_fallback_dpi` の null → `figures.dpi` 継承は journal_profile.resolve() が済ませている
    (値を 2 か所で定義しないため)。ここでは resolve を通していない生 profile でも
    落ちないよう `dpi` を最終の落とし先にする。
    """
    cfg = _figures_cfg(profile).get("pptx")
    cfg = cfg if isinstance(cfg, dict) else {}

    mode = str(cfg.get("mode") or "svg-blob").lower()
    if mode not in PPTX_MODES:
        sys.exit(f"エラー: profile.figures.pptx.mode の値 '{cfg.get('mode')}' は不正です "
                 f"(有効: {'/'.join(PPTX_MODES)})。")
    if mode == "native-shapes":
        sys.exit(
            "エラー: profile.figures.pptx.mode: native-shapes (案 B′ = PowerPoint ネイティブ"
            "シェイプへの変換) は未実装です (docs/journal-bhi.md §5.1.4 で初期スコープ外と"
            "判断したもの)。\n"
            "  黙って案 B (SVG 埋込) へ落とすと『編集可能なシェイプ』という要求に応えたことに"
            "ならないため停止します。\n"
            "  mode: svg-blob (SVG をベクターのまま埋め込む) か mode: passthrough "
            "(利用者が PowerPoint で仕上げた図をそのまま出す) を選んでください。"
        )

    slide_fit = (slide_fit_override or cfg.get("slide_fit") or "figure")
    slide_fit = str(slide_fit).lower()
    if slide_fit not in PPTX_SLIDE_FITS:
        src = "--slide-fit" if slide_fit_override else "profile.figures.pptx.slide_fit"
        sys.exit(f"エラー: {src} の値 '{slide_fit}' は不正です "
                 f"(有効: {'/'.join(PPTX_SLIDE_FITS)})。")

    raw_dpi = cfg.get("png_fallback_dpi")
    if raw_dpi is None:
        png_dpi = dpi
    elif not re.fullmatch(r"\s*[+-]?\d+\s*", str(raw_dpi)):
        sys.exit(f"エラー: profile.figures.pptx.png_fallback_dpi の値 '{raw_dpi}' が整数ではありません。")
    else:
        png_dpi = int(str(raw_dpi).strip())
        if png_dpi <= 0:
            sys.exit("エラー: profile.figures.pptx.png_fallback_dpi は正の整数で指定してください "
                     f"(受け取った値: {raw_dpi})。")

    return {
        "mode": mode,
        "slide_fit": slide_fit,
        "png_fallback_dpi": png_dpi,
        "text_to_path": journal_profile.as_flag(
            cfg.get("text_to_path"), "figures.pptx.text_to_path", default=False),
    }


def figure_label(profile, n):
    """numbering.figure (例 'Figure %d.' / 'Fig. %d') に番号を当てたラベル。"""
    numbering = profile.get("numbering") or {}
    pat = numbering.get("figure") or "Figure %d."
    try:
        return pat % n if "%d" in pat else f"{pat} {n}"
    except (TypeError, ValueError):
        return f"Figure {n}"


def figure_basename(profile, n):
    """ラベルからファイル名 (拡張子なし) を作る。'Figure 1.'→'Figure1', 'Fig. 1'→'Fig1'。"""
    base = re.sub(r"[^0-9A-Za-z]+", "", figure_label(profile, n))
    # ラテン文字を含まない書式 (例 '図%d'→'1') はファイル名が数字のみ ('1.pdf') に
    # 縮退し図と分かりにくいため 'Figure{n}' に倒す (空のときだけでなく、ラテン文字が無いときも)。
    if not re.search(r"[A-Za-z]", base):
        return f"Figure{n}"
    return base


# =====================================================================
# 原稿の図参照を出現順に取得
# =====================================================================

def _strip_yaml_and_code(md_text):
    md_text = re.sub(r"^---\n.*?\n---\n", "", md_text, count=1, flags=re.DOTALL)
    md_text = re.sub(r"<!--.*?-->", "", md_text, flags=re.DOTALL)   # HTML コメント
    md_text = re.sub(r"```.*?```", "", md_text, flags=re.DOTALL)    # コードフェンス
    return md_text


MANIFEST = BUILD_DIR / "main.docx.images.tsv"   # build_docx.py が保持する画像マニフェスト


def manuscript_figures(input_root, body_only=False):
    """原稿の図参照を出現順に [rel_path] で返す。

    body_only=True のとき、テキストボックス (.textbox) 内の図を除いた**本文の図だけ**を返す。
    これは strip_inline_figures が `_in_textbox` で温存する図集合と一致し、
    `[Figure N about here]` のプレースホルダ番号と `figures/FigureN` の対応を揃えるために使う。
    判定にはマニフェスト第 3 列 (in_textbox = 1|0) を用いる。第 3 列が無いマニフェスト
    (古いビルドの残り) では全図を本文図とみなす。

    build (postprocess) と図の数え方を一致させるため、build_docx.py が保持する
    image-manifest (data/step02_build/main.docx.images.tsv = src<TAB>caption) を**優先**して読む。これで
    素の正規表現がキャプション内の角括弧・参照形式画像で取りこぼす不一致を package でも回避し、
    strip / export / build が同一の図集合・順序を共有する。マニフェストが無いときだけ正規表現に
    フォールバックする (postprocess.py 単独実行・古いビルドとの互換)。
    """
    if MANIFEST.is_file():
        figs = []
        for line in MANIFEST.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            cols = line.split("\t")
            # 第 3 列 (in_textbox) が無い古いマニフェストは "0" 扱い。
            in_textbox = len(cols) > 2 and cols[2].strip() == "1"
            if body_only and in_textbox:
                continue
            figs.append(cols[0])
        return figs
    md = Path(input_root) / "main.md"
    if not md.is_file():
        return []
    text = _strip_yaml_and_code(md.read_text(encoding="utf-8"))
    return [m.group(1) for m in re.finditer(r"!\[[^\]]*\]\(([^)\s]+)", text)]


def _resolve_fig_sources(rel, input_root=None):
    """原稿の図参照 rel (例 figs/fig-overview.svg) を step01 の実体に解決する。

    返り値 dict: svg / pdf / png / outline_svg / src_pptx のフルパス (存在は呼び出し側で確認)。
    mermaid (figs/mermaid/<n>.svg) も同規則。pdf は <stem>.pdf (mermaid は mmdc 正本)。

    pptx 経路のための派生物:
      outline_svg : `<stem>.outline.svg` = svg-conversion で文字をパス化した提出用 SVG
                    (figures.pptx.text_to_path=true のときだけ作る。figure-plan が計画する)
                    **置き場は `data/step05_package/`** (図ツリーには置かない)。
                    step05 の生成物を図ツリーに置くと、原稿の図と提出用の派生物が同じ場所に
                    混ざり、図ツリーを走査する受入テストが名前で除外せざるを得なくなる。
      src_pptx    : 執筆者が置いた一次ソースの pptx (案 A の無変換コピー元)。step01 は pptx を
                    図ツリーへ写さないので、図ツリー → 入力ルートの順に探す (非 svg 図の
                    実体探索と同じ規則)。原稿は `.svg` プレビューを参照し、隣に同名の
                    `.pptx` を置く運用 (CLAUDE.md の執筆規約)。
      src_macro   : 同じ場所に置かれた**マクロ有効の PowerPoint ファイル** (`.pptm` / `.ppsm` /
                    `.potm`)。`.pptx` しか探さないと、執筆者が `.pptm` を置いても
                    一次ソースとして見つからず、`svg_pptx.inspect_pptx` が持っている拒否メッセージ
                    にも到達せず、**黙って案 B (SVG からの生成) に落ちる**。置いた本人は
                    自分の PowerPoint 作業が提出物に反映されたと思い込む。
    """
    rel_path = Path(rel)
    svg = FIG_ROOT / rel_path
    pdf = FIG_ROOT / rel_path.with_suffix(".pdf")
    png = FIG_ROOT / (str(rel_path) + ".png")    # generic-style.lua の *.svg.png 規約
    # 提出用の派生物は step05 の領域へ (図ツリーには置かない)
    outline_svg = PKG_DIR / (str(rel_path.with_suffix("")) + ".outline.svg")

    def _sibling(suffix):
        """図と同じ場所の <stem><suffix> を図ツリー → 入力ルートの順に探す。"""
        cand_rel = rel_path.with_suffix(suffix)
        found = FIG_ROOT / cand_rel
        if not found.is_file() and input_root:
            alt = Path(input_root) / cand_rel
            if alt.is_file():
                return alt
        return found

    src_pptx = _sibling(".pptx")
    src_macro = next((p for p in (_sibling(s) for s in svg_pptx.MACRO_SUFFIXES) if p.is_file()),
                     None)
    is_mermaid = len(rel_path.parts) >= 2 and "mermaid" in rel_path.parts
    return {"svg": svg, "pdf": pdf, "png": png, "outline_svg": outline_svg,
            "src_pptx": src_pptx, "src_macro": src_macro,
            "is_mermaid": is_mermaid, "rel": rel}


# =====================================================================
# figure-plan: 最終モードで svg-conversion (Inkscape) が要る変換を列挙 (host が駆動)
#
# TSV: src_svg <TAB> out <TAB> embed(0/1) <TAB> kind(pdf|outline-svg)
#   4 列目 kind があるのは、pptx 提出で figures.pptx.text_to_path=true のとき
#   pdf ではなく **アウトライン化した SVG** (convert.sh --outline-svg) が要るため。
#   package.sh が kind を見て convert.sh の呼び分けをする。
# =====================================================================

def cmd_figure_plan(args):
    profile = load_profile(args.journal, args.article_type)
    mode = resolve_mode(profile, args.mode)
    fmt = resolve_format(profile, args.format)
    export, fallback = resolved_export(fmt)
    if mode == "final" and not args.keep_figures:
        # 生成経路が無い形式はここで停止する (pdf などへの既定代替はしない)
        require_export_route(fmt, export)
        # 代替なら停止、明示指定は明示同意を要求
        w = check_export_allowed(profile, fmt, export, fallback, args.allow_disallowed_format)
        if w:
            print(f"  figure-plan: {w}", file=sys.stderr)
    embed = "1" if resolve_font_handling(profile, args.font_handling) == "embed" else "0"

    # pptx 経路で text_to_path=true のときだけ svg→svg (アウトライン化) を計画する。
    # false (BHI の既定) では pptx 経路で Inkscape を一切呼ばない (駆動対象は pdf 経路だけ)。
    kind = None
    if mode == "final" and not args.keep_figures:
        if export == "pdf":
            kind = "pdf"
        elif export == "pptx":
            pptx_cfg = resolve_pptx_cfg(profile, resolve_dpi(profile, None), args.slide_fit)
            if pptx_cfg["text_to_path"] and pptx_cfg["mode"] == "svg-blob":
                kind = "outline-svg"

    if kind is None:
        # png 経路 / text_to_path=false の pptx 経路 / 草稿モード・--keep-figures では
        # svg-conversion (Inkscape) は不要
        print(f"  figure-plan: mode={mode} export={export} → svg-conversion は不要",
              file=sys.stderr)
        return 0

    # export_figures と同じ図集合 (テキストボックス内図を除く) を対象にする。
    # 分離出力しない図の変換を走らせても無駄なため。
    for rel in manuscript_figures(args.input_root, body_only=True):
        if not rel.endswith(".svg"):
            continue
        src = _resolve_fig_sources(rel, args.input_root)
        if kind == "pdf" and src["is_mermaid"]:
            # mermaid は mmdc 正本 pdf を保持 (inkscape で上書きしない。step01 と同方針)。
            # ※ outline-svg は「正本」が別に無い派生物なので mermaid も対象にする。
            print(f"  figure-plan: skip mermaid (正本 pdf 保持): {rel}", file=sys.stderr)
            continue
        if kind == "outline-svg" and src["src_pptx"].is_file():
            # 案 A で無変換コピーする図はアウトライン化しない (中身に触らないのが目的のため)
            print(f"  figure-plan: skip 一次 pptx あり (案 A で無変換コピー): {rel}", file=sys.stderr)
            continue
        if not src["svg"].is_file():
            print(f"  figure-plan: 警告 svg 不在のためスキップ: {src['svg']}", file=sys.stderr)
            continue
        out = src["pdf"] if kind == "pdf" else src["outline_svg"]
        print(f"{src['svg']}\t{out}\t{embed}\t{kind}")
    return 0


# =====================================================================
# 最終モード: manuscript から inline 図を除去しプレースホルダ化
# =====================================================================

TXBX_CONTENT = "{%s}txbxContent" % W_NS


def _in_textbox(elem):
    """elem の祖先に w:txbxContent (テキストボックス内) が在るか。"""
    p = elem.getparent()
    while p is not None:
        if p.tag == TXBX_CONTENT:
            return True
        p = p.getparent()
    return False


def lint_manuscript_tables(docx_path, profile):
    """docx を**読むだけ**で表の体裁 lint を掛ける (草稿 / --keep-figures 経路)。

    草稿の manuscript.docx は `shutil.copyfile` でそのまま複製する (書き換えると
    草稿出力が build の docx とバイト単位で一致しなくなる)。lint は読み取り専用
    なので複製後の docx をもう一度開いて掛ける。色・網掛けの禁止は草稿でも直しておく価値がある
    (最終だけで警告すると、投稿直前に表を作り直すことになる)。
    """
    from lxml import etree
    with zipfile.ZipFile(docx_path, "r") as z:
        root = etree.fromstring(z.read("word/document.xml"))
    return relocate_mod.lint_tables(root, profile)


def _drop_orphan_media(parts, doc_xml_bytes):
    """document から参照されなくなった image 型 rels と word/media/* を削除する。

    図除去後、本文 (document.xml) のどこにも rId が現れない image 関係だけを孤立とみなし、関係定義と
    メディア実体を消す。残る図 (テキストボックス内図など) の rId は文字列照合で保護する。header/footer の
    画像は別 rels ファイルにあるため対象外。
    """
    from lxml import etree
    rels_path = "word/_rels/document.xml.rels"
    if rels_path not in parts:
        return 0
    doc_text = doc_xml_bytes.decode("utf-8", "ignore")
    rels_root = etree.fromstring(parts[rels_path])
    removed = 0
    for rel in list(rels_root):
        if not rel.get("Type", "").endswith("/image"):
            continue
        rid = rel.get("Id", "")
        # rId が document.xml の属性値として現れれば使用中 (閉じ引用符まで含め誤一致を防ぐ)
        if rid and (f'"{rid}"' in doc_text):
            continue
        target = rel.get("Target", "")
        media_part = target.lstrip("/") if target.startswith("/") else "word/" + target
        parts.pop(media_part, None)
        rels_root.remove(rel)
        removed += 1
    if removed:
        parts[rels_path] = etree.tostring(
            rels_root, xml_declaration=True, encoding="UTF-8", standalone=True
        )
    return removed


def table_file_name(group, index):
    """別ファイルへ出す表のファイル名 (`Table1.docx`)。題の無い表は通し番号で区別する。"""
    if group.get("number") is not None:
        return f"Table{group['number']}.docx"
    return f"Table-untitled{index}.docx"


def write_table_files(parts, root, groups, tables_dir, profile, log=print):
    """本文から外した表を 1 表 1 ファイルの docx に書き出す (tables.placement: separate)。

    本文をテキストだけにして、表を表ファイルとして別に上げる提出の形のため。
    BHI の規定は本文末尾・別ファイルのどちらも認めており、BHI のプロファイルは別ファイルを既定にする。

    作り方: **組み替え後の manuscript.docx の書庫をそのまま複製し、`w:body` の中身だけを
    その表の組 (題 + `w:tbl` + 凡例) と元の `w:sectPr` に置き換える**。styles / numbering /
    rels / フッタを本文と共有するので、題・凡例・表の体裁が本文と同じになる
    (別の reference.docx から組み立て直すと、本文と表で体裁がずれうる)。
      - 題は表の上・凡例は表の下 (pandoc の出力順そのまま。BHI 規定の並び)。
      - 行番号は `line_numbers_scope: manuscript` なら外す (表ファイルは本文 main.md ではない。
        カバーレターから行番号を外すのと同じ扱い)。`all` なら本文と同じく残す。
      - ページ番号 (フッタ) は残す。
      - 本文の相互参照 ("Table 1") のブックマークは本文側に残る (relocate の説明を参照)。
      - 最後が `w:tbl` で終わるなら空段落を足す (Word 自身も表の後に必ず段落を置く)。

    返り値: (written=[(ファイル名, パス)], lint=[警告文])
    """
    import copy
    from lxml import etree

    tables_dir = Path(tables_dir)
    tables_dir.mkdir(parents=True, exist_ok=True)
    scope = str(profile.get("line_numbers_scope") or "all").lower()
    written, lint = [], []
    for index, g in enumerate(groups, start=1):
        name = table_file_name(g, index)
        doc = copy.deepcopy(root)
        body = doc.find(W("body"))
        sect = body.find(W("sectPr"))
        for el in list(body):
            if el is not sect:
                body.remove(el)
        add = (lambda el, s=sect: s.addprevious(el)) if sect is not None else body.append
        for el in g["elements"]:
            add(copy.deepcopy(el))
        if g["elements"] and g["elements"][-1].tag == W("tbl"):
            add(relocate_mod._make_paragraph(etree, "", style=relocate_mod.STYLE_PLACEHOLDER))
        if scope == "manuscript" and sect is not None:
            for ln in sect.findall(W("lnNumType")):
                sect.remove(ln)
        doc_bytes = etree.tostring(doc, xml_declaration=True, encoding="UTF-8", standalone=True)
        tparts = dict(parts)
        tparts["word/document.xml"] = doc_bytes
        _drop_orphan_media(tparts, doc_bytes)
        dest = tables_dir / name
        with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as zout:
            for part_name, data in tparts.items():
                zout.writestr(part_name, data)
        lint.extend(relocate_mod.lint_tables(doc, profile, label=f"tables/{name} の表"))
        written.append((name, dest))
    if written:
        log(f"  tables: {len(written)} 件を {tables_dir}/ に 1 表 1 ファイルで出力 "
            f"({', '.join(n for n, _ in written)})")
    return written, lint


def strip_inline_figures(docx_in, docx_out, profile=None, log=print, tables_dir=None):
    """inline 図 (wp:inline を含む w:drawing) を除去し [Figure N about here] に置換する。

    図キャプション (ImageCaption 段落=凡例) は残す。テキストボックス (wp:anchor) 自体は図ではないので
    対象外。(a) 1 段落に複数図があっても先頭で打ち切らず**全件**処理する、
    (b) テキストボックス内 (w:txbxContent 配下) の inline 図は
    フロート図表として温存し除去しない。除去後に参照されなくなった media/rels は
    掃除する (残すと最終 docx が肥大し、匿名版にも図データが残る)。
    番号 N は本文中 inline 図の出現順 (= postprocess が manifest 順に埋め込んだ図順) と一致する。

    **同じ 1 回の書庫の開閉で提出構成の組み替えと表の lint も済ませる** (relocate.py)。
    docx を 2 度開き直さないため、および「図をプレースホルダ化してから題と凡例を集約する」という
    順序の前提を関数の中に閉じ込めるため (relocate は図が本文に残ったままでは呼べない)。
    profile を渡さなければ図の除去だけを行う。

    `tables.placement: separate` では本文から外した表を `tables_dir` へ
    1 表 1 ファイルで書き出す (write_table_files)。表ファイルは本文と同じ書庫から作るので、
    この関数の中で (= 本文の書庫を閉じる前に) 行う。

    返り値: dict(stripped=図の件数, figures=集約した図の組数, tables=移設した表の組数,
                 legends_section=集約先の見出し名 or None, warnings=[...], lint=[...],
                 tables_files=[(ファイル名, パス)]  ← separate のときだけ非空)
    """
    from lxml import etree
    with zipfile.ZipFile(docx_in, "r") as zin:
        parts = {i.filename: zin.read(i.filename) for i in zin.infolist()}

    root = etree.fromstring(parts["word/document.xml"])
    body = root.find(W("body"))
    n = 0
    if body is not None:
        # 先に対象 drawing を確定してから変更する (走査中の木の変更を避ける)。
        targets = [dr for dr in body.iter(W("drawing"))
                   if dr.find(WP("inline")) is not None and not _in_textbox(dr)]
        for drawing in targets:
            n += 1
            run = drawing.getparent()                   # 図を載せた w:r
            # run 内の drawing を消し、同 run にプレースホルダ text を入れる (rPr は温存)
            run.remove(drawing)
            t = etree.SubElement(run, W("t"))
            t.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
            t.text = f"[Figure {n} about here]"

    result = {"stripped": n, "figures": 0, "tables": 0,
              "legends_section": None, "warnings": [], "lint": [], "tables_files": []}
    separated = []
    if profile is not None:
        # 表末尾移設 / Figure Legends 集約 (profile 駆動。未指定の誌では何もしない)
        rel = relocate_mod.relocate(root, profile, log=log)
        result.update({k: rel[k] for k in ("figures", "tables", "legends_section")})
        result["warnings"] = rel["warnings"]
        result["lint"] = relocate_mod.lint_tables(root, profile)
        separated = rel.get("tables_separated") or []

    doc_bytes = etree.tostring(
        root, xml_declaration=True, encoding="UTF-8", standalone=True
    )
    parts["word/document.xml"] = doc_bytes
    _drop_orphan_media(parts, doc_bytes)

    Path(docx_out).parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(docx_out, "w", zipfile.ZIP_DEFLATED) as zout:
        for name, data in parts.items():
            zout.writestr(name, data)

    if separated:
        if tables_dir is None:
            sys.exit("エラー: tables.placement: separate で外した表の出力先 (tables_dir) が "
                     "渡されていません (package.py の呼び出し側の不具合)。")
        written, lint = write_table_files(parts, root, separated, tables_dir, profile, log=log)
        result["tables_files"] = written
        result["lint"].extend(lint)
    return result


# =====================================================================
# 図の分離出力 (final mode)
# =====================================================================

def _png_at_dpi(svg_path, out_png, dpi, label=None):
    """svg→png を「指定 dpi を保証して」生成する (pandoc コンテナ内)。

    `rsvg-convert -d/-p` に dpi を渡すだけでは、この指定が画素数に
    効くのは物理単位 (pt/mm/in/cm) を持つ SVG のときだけである。
    px/無単位 SVG (手書き・pdf2svg・mermaid 出力の多く) は 1:1 描画のままになり、BHI の
    "minimum of 300 dpi" を**満たさない図が警告 1 行で出てしまう**。
    そこで svg_raster が物理サイズから必要画素数を計算して -w/-h で明示し、生成後に実画素数を
    検算して pHYs を書き込む。**目標 dpi に届かない場合は警告ではなくエラーで停止**する
    (規定違反物を出さないため)。

    返り値: svg_raster.render_png_at_dpi の結果 dict。失敗時は sys.exit で停止する。
    """
    try:
        return svg_raster.render_png_at_dpi(svg_path, out_png, dpi, log=print, label=label)
    except svg_raster.SvgRasterError as exc:
        sys.exit(
            f"エラー: 図の png 生成に失敗しました ({label or svg_path})。\n  {exc}\n"
            "  解像度要件を満たさない図を提出しないため停止します "
            "(dpi を下げるか SVG の寸法指定を見直してください)。"
        )


def _raster_resolution_note(path, dpi):
    """原寸複製した生ラスタ図の解像度の状態を 1 行にする。

    pHYs を読めるのは PNG だけなので、それ以外は「機械判定できない」と正直に書く。
    """
    if Path(path).suffix.lower() != ".png":
        return (f"{Path(path).suffix.lstrip('.').upper()} は解像度を機械判定できない形式です "
                f"({dpi}dpi 以上で書き出したか確認してください)")
    try:
        w, h = svg_raster.png_pixel_size(path)
        state, value = svg_raster.read_png_phys(path)
    except svg_raster.SvgRasterError as exc:
        return f"解像度を読めませんでした ({exc})"
    if state == "dpi":
        judge = "要件を満たします" if value[0] >= dpi - 0.001 else f"**{dpi}dpi を下回ります**"
        return f"実測 {w}x{h} px / pHYs {value[0]:.2f}dpi — {judge}"
    if state == "unitless":
        return (f"実測 {w}x{h} px / pHYs はありますが単位が『なし』(縦横比のみ) で解像度を"
                f"表していません ({dpi}dpi と認識されません)")
    return (f"実測 {w}x{h} px / pHYs (物理解像度) が無いため何 dpi の画像か機械判定できません "
            f"(配置幅で割った値が {dpi}dpi 以上か確認してください)")


def _pptx_source_svg(src, pptx_cfg, index):
    """pptx へ埋め込む SVG を決める (text_to_path=true ならアウトライン化済みのもの)。

    `text_to_path: true` を指定したのに素の SVG を黙って埋め込むと、
    「フォント依存を消したつもりが消えていない」状態を検知できないので停止する
    (図形式を「黙って別形式に代替しない」のと同じ理由)。
    """
    if not pptx_cfg["text_to_path"]:
        return src["svg"]
    if src["outline_svg"].is_file():
        return src["outline_svg"]
    sys.exit(
        f"エラー: Figure {index}: text-to-path 済み SVG {src['outline_svg']} がありません "
        "(figures.pptx.text_to_path=true)。\n"
        "  素の SVG を黙って埋め込むとフォント依存が残ったまま提出されるため停止します。\n"
        "  'bash scripts/package.sh' 経由で実行してください (figure-plan が svg-conversion に"
        "アウトライン化を依頼します)。package.py を直に呼ぶ場合は\n"
        f"    bash docker/svg-conversion/convert.sh {src['svg']} {src['outline_svg']} --outline-svg\n"
        "  を先に実行してください。"
    )


def _export_one_pptx(src, dest, pptx_cfg, index, rel, warnings, profile):
    """図 1 枚を pptx として出す (案 A の無変換コピー or 案 B の SVG 埋込生成)。

    返り値: True なら 1 件生成した。
    """
    has_src_pptx = src["src_pptx"].is_file()

    # マクロ有効のファイル (.pptm 等) を置かれたときは黙って案 B に落とさない
    # (`.pptx` しか探さないと、拒否メッセージにすら到達しない)。
    if not has_src_pptx and src.get("src_macro"):
        sys.exit(
            f"エラー: Figure {index}: マクロ有効の PowerPoint ファイルは提出できません "
            f"({src['src_macro']})。\n"
            "  投稿系はマクロ / ActiveX を含む文書の変換に失敗すると明記しています。\n"
            "  マクロを外して同じ場所に <name>.pptx として保存し直してください "
            "(そのまま置いても案 A の無変換コピーには使われません)。\n"
            "  SVG から生成してよい場合は、そのファイルを図の隣から移動してください。"
        )

    # --- 案 A: 一次ソースが pptx なら無変換でコピーする (劣化ゼロ) ---
    if has_src_pptx or pptx_cfg["mode"] == "passthrough":
        if not has_src_pptx:
            sys.exit(
                f"エラー: Figure {index}: figures.pptx.mode: passthrough は一次ソースの pptx を"
                f"求めますが {src['src_pptx']} がありません。\n"
                "  原稿が参照する図と同じ場所・同じ名前で <name>.pptx を置いてください "
                "(原稿側は .svg のプレビューを参照したままにします)。\n"
                "  SVG から pptx を生成する場合は figures.pptx.mode: svg-blob にしてください。"
            )
        try:
            svg_pptx.copy_pptx_passthrough(src["src_pptx"], dest, log=print)
        except svg_pptx.SvgPptxError as exc:
            sys.exit(f"エラー: Figure {index} ({rel}) の pptx を提出できません。\n  {exc}")
        note = ("一次ソースの pptx をそのまま提出します (案 A。変換していないので劣化ゼロ)"
                if pptx_cfg["mode"] == "passthrough" else
                "一次ソースの pptx があったため SVG からの生成 (案 B) ではなく**無変換コピー**"
                "しました (案 A。変換を挟まないほうが劣化しないため)")
        warnings.append(
            f"Figure {index}: {note}。中身はテンプレートの検査対象外です — "
            "フォントの環境依存・余白・凡例キーは執筆者が PowerPoint 上で確認してください。")
        return True

    # --- 案 B: SVG から 1 スライドの pptx を生成する ---
    if not src["svg"].is_file():
        warnings.append(f"Figure {index}: svg {src['svg']} 不在のためスキップ")
        return False
    embed_svg = _pptx_source_svg(src, pptx_cfg, index)
    with tempfile.TemporaryDirectory() as tmp:
        # PNG フォールバックは pptx の中身なので figures/ には置かない (提出物に混ぜない)
        try:
            # descr に `rel` (= `figs/fig-workflow.svg` という
            # **リポジトリ内の相対パス**) を渡すと、提出する pptx の代替テキストに内部の
            # ディレクトリ構成がそのまま載る。docProps から pandoc 開発者の氏名と作成日時を
            # 消した判断 (svg_pptx の骨格加工) と揃えて、図番号だけの中立な代替テキストにする。
            # (原稿のキャプションを代替テキストにするのが理想だが、この関数はキャプションを
            #  受け取っていないため、今後の課題とする)
            r = svg_pptx.build_figure_pptx(
                embed_svg, dest, png_path=Path(tmp) / "fallback.png",
                dpi=pptx_cfg["png_fallback_dpi"], slide_fit=pptx_cfg["slide_fit"],
                title=dest.stem, descr=figure_label(profile, index).rstrip("."), log=print)
        except svg_pptx.SvgPptxError as exc:
            sys.exit(f"エラー: Figure {index} ({rel}) の pptx 生成に失敗しました。\n  {exc}")
        except svg_raster.SvgRasterError as exc:
            sys.exit(
                f"エラー: Figure {index} ({rel}) の PNG フォールバック生成に失敗しました。\n  {exc}\n"
                "  pptx の PNG フォールバックは『多数の受け手が実際に見る本体』なので "
                "(Microsoft 365 / Office 2019 未満では PNG 側が描画され、投稿系の査読用 PDF 変換でも描画されうる)、"
                "解像度を保証できないまま出さずに停止します。")
    print(f"  figures: Figure {index} ({rel}) -> {dest}  "
          f"[pptx {r['slide_w_in']:.2f}x{r['slide_h_in']:.2f} in / PNG "
          f"{r['png_width']}x{r['png_height']} px @ {r['effective_dpi']:.0f}dpi]")
    if r["fit"] == "fixed":
        warnings.append(
            f"Figure {index}: slide_fit=fixed のため、スライドは既定サイズ "
            f"({r['slide_w_in']:.2f}x{r['slide_h_in']:.2f} in) で図を中央に置きました "
            f"(図の占める寸法 {r['placed_w_in']:.2f}x{r['placed_h_in']:.2f} in)。"
            "スライドに余白が残るので、余白を嫌う誌では SVG 側の寸法を見直してください。")
    elif r["pad_w_in"] > 0 or r["pad_h_in"] > 0:
        # 規格下限 (1 インチ) に合わせてスライドを広げた = 図の周りに余白ができた。
        # 量は小さいが「余白を最小化せよ」という規定があるので黙らせない。
        warnings.append(
            f"Figure {index}: 図が {r['placed_w_in']:.3f}x{r['placed_h_in']:.3f} in と小さく、"
            "PowerPoint のスライド寸法の下限 (1 インチ) を割るため、スライドを "
            f"{r['slide_w_in']:.3f}x{r['slide_h_in']:.3f} in へ広げて図を中央に置きました "
            f"(足した余白は幅 {r['pad_w_in']:.3f} in / 高さ {r['pad_h_in']:.3f} in)。"
            "余白を無くしたい場合は SVG ルートの width/height を 1 インチ以上にしてください。")
    return True


def export_figures(input_root, profile, out_fig_dir, fmt, export, fallback, dpi,
                   pptx_cfg=None):
    """原稿の図を雑誌指定の形式/解像度/命名で out_fig_dir に分離出力する。

    返り値: (生成数, 警告リスト, **書き出した順のリスト** [(表示名, パス), ...])。

    3 要素目は `SUBMISSION.md` の図の表の順序に使う。ディレクトリを
    `sorted(fig_dir.iterdir())` で**読み直して**はいけない。
    ファイル名は `figure_basename()` が作る `Figure1` / `Figure2` … で 0 埋めが無いため、
    `sorted()` は文字列として比較する。図が 10 枚を超えると
    `Figure1 → Figure10 → Figure11 → Figure12 → Figure2 → …` の順になり、
    マニフェストが「**本文の初出順にアップロードする (下表の順)**」と書いている表が
    初出順でなくなる (図 12 枚で実測)。投稿系は上げた順に図番号を割り当てるため、
    指示どおりに上げると全図が凡例と食い違う。本リストは `figs` (= 本文の初出順) を
    そのまま辿って積むので、命名規則 (`numbering.figure`) を変えても順序が壊れない。
    """
    warnings = []
    # 全図 (svg に限らない) を出現順 (manifest 順) に番号付け、
    # strip のプレースホルダ番号と一致させる。
    # body_only=True でテキストボックス内図を除外する。manifest の
    # 全件を分離対象にすると、strip_inline_figures が温存する textbox 内図まで FigureN として
    # 書き出し、プレースホルダ番号と figures/ の番号が (textbox 図の位置以降) 全部ずれる。
    figs = manuscript_figures(input_root, body_only=True)
    if not figs:
        warnings.append("原稿に図参照がありません (figures/ は空)")
        return 0, warnings, []
    if fallback:
        # TIFF ネイティブ経路は「実装しない」と決めた (見送りの根拠と再検討条件は
        # docs/profile-schema.md / docs/journal-bhi.md §5.2)。代替であることを黙らせず毎回明示する。
        extra = ""
        if fmt in ("tiff", "tif"):
            extra = ("。TIFF ネイティブ経路は**意図的に用意していない** — コンテナに画像"
                     "ライブラリが無く (Pillow/ImageMagick/exiftool いずれも不在)、追加すると"
                     "全ビルドが重くなる一方、BHI は PNG も受け付けるため。TIFF しか受け付けない"
                     "誌に投稿するときに再検討する (docs/journal-bhi.md §5.2)")
        warnings.append(
            f"図形式 '{fmt}' は未対応の生成経路です。代替として '{export}' で出力します "
            f"(docs/profile-schema.md の figures.formats。EPS 経路は将来追加){extra}"
        )
    if export == "png":
        # dpi は物理単位の無い SVG にも効く (svg_raster が物理サイズから画素数を計算し、
        # 届かなければエラー停止する)。残る注意は
        # 「無単位 SVG の物理サイズをどう決めたか」という前提の明示だけ。
        warnings.append(
            f"png 図は {dpi}dpi を保証して生成しました (実画素数を検算済)。ただし物理単位 "
            "(mm/pt/in) を持たない SVG は width/height (無ければ viewBox) を CSS px = 96dpi と"
            "みなして物理サイズを決めています。**図を意図した印刷幅より小さい公称サイズで作っている場合、"
            "その印刷幅での実効解像度は 300dpi を下回りえます** — 各図のログ行 (元サイズ→inch→画素数) を"
            "確認し、必要なら SVG ルートに物理単位の width/height を持たせてください。"
            "ベクター図を png にラスタ化している点にも注意 (線画はベクター提出が望ましい場合あり)。"
        )
    if export == "pptx":
        # ベクター提出。dpi は「pptx に同梱する PNG フォールバック」の解像度として効く。
        # 「pptx 図は SVG をベクターのまま埋め込み…同梱しました」と
        # 全 pptx 図について断言しない。案 A (一次 pptx の無変換コピー) の図はテンプレートが
        # 中身に触っていないので、埋込も 300dpi の代替表示 PNG も**保証していない**。
        # 主語を「SVG から生成した図」に限り、案 A の図は個別の注意で扱う旨を書く。
        warnings.append(
            f"**SVG から生成した** pptx 図は SVG をベクターのまま埋め込み、"
            f"{pptx_cfg['png_fallback_dpi']}dpi の PNG "
            "フォールバックを同梱しました (**一次 pptx を無変換コピーした図 = 案 A は"
            "この保証の対象外で、個別に注意を出しています**)。**PNG フォールバックは保険ではなく多数の"
            "受け手が実際に見る本体です** — SVG のネイティブ表示に対応するのは Microsoft 365 / "
            "Office 2019 以降で、買い切り版 Office 2016 では PNG 側が描画され、投稿系の査読用 PDF 変換でも"
            "描画されえます (どちらが描かれるかは確かめていない。docs/journal-bhi.md §5.1.3 リスク 1)。"
            "なお **スライド寸法を図に合わせても『余白の最小化 (closely cropped)』要件は満たせません** "
            "— SVG の viewBox が描画内容より広ければ白余白はそのままスライドに載るため、"
            "余白のトリミングは執筆者が SVG 側で行ってください。"
        )
    out_fig_dir = Path(out_fig_dir)
    out_fig_dir.mkdir(parents=True, exist_ok=True)
    ext = {"pdf": "pdf", "pptx": "pptx"}.get(export, "png")

    count = 0
    written = []            # 書き出した順 (= 本文の初出順) を保つ
    for i, rel in enumerate(figs, start=1):
        src = _resolve_fig_sources(rel, input_root)
        if not rel.endswith(".svg"):
            # 非 svg 図 (png/jpg 等): 原寸のまま複製 (svg 経路のみ形式変換に対応)。番号は必ず進める。
            orig_ext = Path(rel).suffix.lstrip(".") or "img"
            dest = out_fig_dir / f"{figure_basename(profile, i)}.{orig_ext}"
            cand = FIG_ROOT / rel
            if not cand.is_file():
                cand = Path(input_root) / rel
            if cand.is_file():
                shutil.copyfile(cand, dest)
                count += 1
                written.append((dest.name, dest))
                # 実画素数と pHYs をその場で読み、解像度の状態を必ず出す。
                # 300dpi 保証 (svg_raster) はこの経路に届かないので、そのことを利用者に必ず伝える
                # (実投稿で dpi 要件に引っかかりやすいのは線画ではなく写真であり、それがこの経路を通る)。
                res_note = _raster_resolution_note(dest, dpi)
                print(f"  figures: Figure {i} ({rel}) -> {dest}  [非svg 原寸複製。{res_note}]")
                if export == "pptx":
                    # 元がラスタの図は **意図的に** pptx へ包まない (規定は PowerPoint を受け付ける形式に挙げるだけで、
                    # 画像を包むことは求めていない)。ラスタを pptx に包んでも拡大耐性は上がらないため。
                    warnings.append(
                        f"Figure {i}: 元がラスタの図 ({rel}) は **pptx に包まず画像ファイルのまま**"
                        "出しました (画像の図は画像ファイルのまま提出する。"
                        "ラスタを pptx に包んでも拡大耐性は"
                        f"上がりません)。{res_note} "
                        f"**この図は {dpi}dpi 保証 (SVG からの生成経路) の対象外です** — 雑誌が dpi 要件を課す"
                        "場合は、元画像を要求解像度で書き出し直してください (ツール側では作り直せません)。"
                    )
                else:
                    warnings.append(
                        f"Figure {i}: 非 svg 図 ({rel}) は形式 '{fmt}' へ変換せず原寸複製しました "
                        f"(svg 経路のみ形式変換に対応)。{res_note} "
                        f"**この図は {dpi}dpi 保証 (SVG からの生成経路) の対象外です** — 雑誌が dpi 要件を課す場合は、"
                        "元画像を要求解像度で書き出し直してください (ツール側では作り直せません)。"
                    )
                # 原寸複製は形式変換を経ないため check_export_allowed の検査を
                # 通らない。元の拡張子を誌の受入形式と照合し、外れていれば注意を出す。
                allowed_ff = (profile.get("submission") or {}).get("figure_formats")
                if allowed_ff:
                    norm_ff = {_FMT_ALIASES.get(str(a).lower(), str(a).lower()) for a in allowed_ff}
                    oe = orig_ext.lower()
                    if _FMT_ALIASES.get(oe, oe) not in norm_ff:
                        warnings.append(
                            f"Figure {i}: 原寸複製した '{orig_ext}' はこの誌の受入形式 {allowed_ff} に"
                            "含まれません。受入形式内に変換してから提出してください。"
                        )
            else:
                warnings.append(f"Figure {i}: 非 svg 図 {rel} の実体が見つからずスキップ (番号は保持)")
            continue
        dest = out_fig_dir / f"{figure_basename(profile, i)}.{ext}"
        # pptx 以外の形式で出すときは、執筆者が置いた一次 pptx が
        # **使われない**。これを黙って行わない。原稿が参照する `.svg` は執筆規約上
        # 「pptx のプレビュー」でしかないので (CLAUDE.md)、下書きの図がそのまま提出物になりうる。
        if export != "pptx" and (src["src_pptx"].is_file() or src.get("src_macro")):
            found = src["src_pptx"] if src["src_pptx"].is_file() else src["src_macro"]
            warnings.append(
                f"Figure {i}: 図の隣に PowerPoint ファイル ({found}) が置かれていますが、"
                f"形式 '{export}' で出すため**使っていません**。"
                f"提出物になるのは同名の SVG ({src['svg']}) から作った画像です。"
                "その SVG が PowerPoint 側の内容と合っているかを確認してください "
                "(執筆規約では .svg は .pptx のプレビュー扱いです)。"
                "PowerPoint の中身をそのまま出すには --format pptx で実行してください。"
            )
        if export == "pdf":
            master = src["pdf"]
            if not master.is_file():
                warnings.append(
                    f"Figure {i}: pdf 図 {master} が未生成です "
                    f"(package.sh が svg-conversion で生成します。mermaid は step01 で生成済)。スキップ"
                )
                continue
            shutil.copyfile(master, dest)
            count += 1
            written.append((dest.name, dest))
            print(f"  figures: Figure {i} ({rel}) -> {dest}  [pdf。ベクターは dpi 非依存]")
        elif export == "pptx":
            if _export_one_pptx(src, dest, pptx_cfg, i, rel, warnings, profile):
                count += 1
                written.append((dest.name, dest))
        else:  # png
            if not src["svg"].is_file():
                warnings.append(f"Figure {i}: svg {src['svg']} 不在のためスキップ")
                continue
            r = _png_at_dpi(src["svg"], dest, dpi, label=f"Figure {i} ({rel})")
            count += 1
            written.append((dest.name, dest))
            print(f"  figures: Figure {i} ({rel}) -> {dest}  "
                  f"[png {r['width_px']}x{r['height_px']} px @ {dpi}dpi 検算済]")
    return count, warnings, written


# =====================================================================
# assemble: 提出一式を data/output/<journal>/ に集約
# =====================================================================

def _copy_if_exists(src, dst, label, collected, missing):
    src = Path(src)
    if src.is_file():
        Path(dst).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dst)
        collected.append((label, str(dst)))
        return True
    missing.append((label, str(src)))
    return False


def _safe_journal_out_dir(journal):
    """data/output/<journal> を返す。journal id を検証し OUTPUT_ROOT の外を指さないことを保証する。

    shutil.rmtree(out_dir) が data/output や data/ 全体を消さないよう、空・'.'・'..'・
    パス区切り (/・\\) を拒否し、解決後パスが OUTPUT_ROOT の真の子孫であることを確認する。直接 package.py を
    呼ぶ運用でも効く load-bearing なガード。
    """
    if not journal or journal in (".", "..") or "/" in journal or "\\" in journal:
        sys.exit(f"エラー: 不正な --journal '{journal}' (空・'.'・'..'・パス区切りは使えません)")
    out = (OUTPUT_ROOT / journal).resolve()
    root = OUTPUT_ROOT.resolve()
    if out == root or root not in out.parents:
        sys.exit(f"エラー: --journal '{journal}' が {OUTPUT_ROOT}/ の外を指します (削除を中止します)")
    return OUTPUT_ROOT / journal


# =====================================================================
# supplementary / video のパススルー
# =====================================================================

SUPP_DIRNAME = "supplementary"
# 動画かどうかは拡張子で決める。profile.submission.video_formats は「投稿系が受け付ける形式」の
# 記録なので、これで判定すると **受け付けられない形式の動画** (mov 等) が動画として扱われず、
# サイズ上限の検査からも漏れる。分類は拡張子、可否は profile、という切り分けにする。
VIDEO_SUFFIXES = (".mp4", ".mov", ".avi", ".wmv", ".mkv", ".m4v", ".webm", ".mpg", ".mpeg")

# OS が勝手に作る管理用ファイル。BHI の補足資料は「受け取ったまま、一切変換せず
# 公開され、受理後は変更できない」ため、これらが混ざるとそのまま誌面に載る (実測: `.DS_Store` が
# 複製され、SUBMISSION.md に「形式: (拡張子なし) / 1 B」として提出物の行が立った)。
# **雑誌に依存しない規則なので profile のキーにはせずコード側の定数に置く**。
# ドット始まりのファイルも同じ理由で落とす (`.gitkeep` 等)。除外したことは黙らせない。
JUNK_NAMES = {"thumbs.db", "desktop.ini", ".ds_store"}
JUNK_DIRS = {"__macosx"}


def _is_junk(rel):
    """補足資料として複製しない管理用ファイルか。"""
    if rel.name.lower() in JUNK_NAMES or rel.name.startswith("."):
        return True
    return any(part.lower() in JUNK_DIRS for part in rel.parts[:-1])


def copy_supplementary(input_root, profile, out_dir, warnings, flags=None):
    """`<INPUT_ROOT>/supplementary/` を**無変換で**複製する。

    BHI の規定は "published as received ... without any conversion" (査読対象・受理後は変更不可)
    なので、テンプレート側は**ファイルの中身に**一切手を加えず複製する。動画は
    `profile.limits.video_mb` 超過と受入形式外を警告する。

    入力ルートを `src/` 直書きにしないのは、`.development` の有無で `data/dummy` / `src` に
    切り替わる規約 (docs/architecture.md §4) があり、`src/` 固定では検証データで確認できないため。

    あわせて次の 3 点を守る:
      - OS が作る管理用ファイル (`.DS_Store` 等) は複製しない (`_is_junk`)。除外は報告する。
      - 動画のサイズ判定は **10 進 (1MB = 1,000,000 バイト)** のバイト比較にする。
        1024 進で割った値を「MB」と比較すると上限が実質 52.4MB になり
        (規定より 4.9% 甘い)、境界では「50.0 MB で … 上限 50 MB を超えています」という
        自己矛盾した文面が出る。実バイト数を併記して丸めの誤解も断つ。
      - 複製が 0 件のときに、作られてもいない複製先を名指しする行を出さない。

    引数 `flags` に dict を渡すと、SUBMISSION.md の表へ出す印 (表示名 → 注意文) を書き込む。

    返り値: (supplementary エントリ, video エントリ)。各エントリは (表示名, 実パス)。
    """
    src_root = Path(input_root) / SUPP_DIRNAME
    if not src_root.is_dir():
        return [], []
    dest_root = Path(out_dir) / SUPP_DIRNAME
    limits = profile.get("limits") if isinstance(profile.get("limits"), dict) else {}
    video_mb = limits.get("video_mb")
    allowed_video = (profile.get("submission") or {}).get("video_formats")
    norm_video = ({_FMT_ALIASES.get(str(a).lower(), str(a).lower()) for a in allowed_video}
                  if allowed_video else None)
    if flags is None:
        flags = {}

    supp, video, skipped = [], [], []
    for src in sorted(p for p in src_root.rglob("*") if p.is_file()):
        rel = src.relative_to(src_root)
        if _is_junk(rel):
            skipped.append(rel.as_posix())
            continue
        dst = dest_root / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dst)                 # 無変換 (中身に手を加えない)
        name = f"{SUPP_DIRNAME}/{rel.as_posix()}"
        entry = (name, dst)
        if src.suffix.lower() in VIDEO_SUFFIXES:
            video.append(entry)
            n_bytes = dst.stat().st_size
            # 10 進 (1MB = 1,000,000 バイト) のバイト比較。
            if video_mb is not None and n_bytes > float(video_mb) * 1000 * 1000:
                warnings.append(
                    f"動画 '{rel.as_posix()}' は {n_bytes:,} バイト ({_human_size(n_bytes)}) で、"
                    f"この誌の上限 {video_mb} MB (= {int(float(video_mb) * 1000 * 1000):,} バイト) を"
                    "超えています。分割するか再エンコードしてください。")
                flags[name] = "⚠ 上限超過"
            ext = src.suffix.lstrip(".").lower()
            if norm_video is not None and _FMT_ALIASES.get(ext, ext) not in norm_video:
                warnings.append(
                    f"動画 '{rel.as_posix()}' の形式 '{ext}' はこの誌の受入形式 "
                    f"{allowed_video} に含まれません。")
                flags[name] = (flags.get(name, "") + " ⚠ 受入形式外").strip()
        else:
            supp.append(entry)
    n_copied = len(supp) + len(video)
    if n_copied:
        print(f"  supplementary: {n_copied} 件を {dest_root}/ に無変換で複製 "
              f"(うち動画 {len(video)} 件)")
    else:
        # 0 件のときは複製先が作られないので、その場所を名指ししない。
        print(f"  supplementary: {src_root}/ に複製する対象がありませんでした")
    if skipped:
        # 除外は黙らせない (執筆者が意図して置いたものかもしれない)。
        print(f"  supplementary: 管理用ファイル {len(skipped)} 件を除外しました "
              f"({', '.join(skipped)})")
    if n_copied and (profile.get("submission") or {}).get("supplementary") == "as-is":
        warnings.append(
            "補足資料は**無変換で公開され、査読対象で、受理後は変更できません**。"
            "投稿時点で最終形になっているか確認してください "
            "(本文中では図表と同様に引用のかたちで言及すること)。")
    return supp, video


# =====================================================================
# 提出マニフェスト SUBMISSION.md
# =====================================================================

def _human_size(n_bytes):
    """人が読むサイズ表記。**10 進 (1KB = 1,000 バイト)** で数える。

    1024 進で割った値に「KB」「MB」の単位を付けると、動画の上限判定を同じ流儀で行ったときに
    規定の「1 ファイル 50MB 以内」が実質 52.4MB になり (4.9% 甘い)、
    境界では「50.0 MB で … 上限 50 MB を超えています」という自己矛盾した文面が出る。
    投稿系の表示に合わせるなら 10 進のほうが素直なので、判定と表示の両方を 10 進に揃える。
    """
    if n_bytes < 1000:
        return f"{n_bytes} B"
    if n_bytes < 1000 * 1000:
        return f"{n_bytes / 1000:.1f} KB"
    return f"{n_bytes / (1000 * 1000):.2f} MB"


def _fmt_of(path):
    return Path(path).suffix.lstrip(".").lower() or "(拡張子なし)"


def _file_table(entries, flags=None, notes=None):
    """[(表示名, パス)] を Markdown 表にする。返り値: (行リスト, 合計バイト)。

    任意の `flags` (表示名 → 注意文) と `notes` (表示名 → 用途) を
    受ける。**該当が 1 つでもあるときだけ列を増やす**ので、印も用途も無い表は 4 列のままになる。
    上限超過や受入形式外はここで `⚠ 上限超過` として行に出す — 画面のログは流れるが
    マニフェストは残るため、規定に反するファイルを一覧に無印で載せてはならない。
    """
    flags = flags or {}
    notes = notes or {}
    has_flag = any(flags.get(name) for name, _ in entries)
    has_note = any(notes.get(name) for name, _ in entries)
    head = "| # | ファイル | 形式 | サイズ |"
    sep = "|---|----------|------|--------|"
    if has_flag:
        head += " 注意 |"
        sep += "------|"
    if has_note:
        head += " 用途 |"
        sep += "------|"
    rows = [head, sep]
    total = 0
    for i, (name, path) in enumerate(entries, start=1):
        size = Path(path).stat().st_size if Path(path).is_file() else 0
        total += size
        row = f"| {i} | `{name}` | {_fmt_of(path)} | {_human_size(size)} |"
        if has_flag:
            row += f" {flags.get(name, '')} |"
        if has_note:
            row += f" {notes.get(name, '')} |"
        rows.append(row)
    return rows, total


def _submission_cfg(profile):
    cfg = profile.get("submission")
    return cfg if isinstance(cfg, dict) else {}


def has_submission_spec(profile):
    """profile が提出マニフェストを出すに足る情報を持つか。

    `submission` の**いずれか 1 つ**が非 null なら真、とはしない。
    `submission.figure_formats` は図の生成でも読む `submission` キーで
    (受入形式外の図への代替を止める検査に使う)、新しい誌を足すとき**最初に
    書きたくなる**キーである。それだけを書いた段階でマニフェストを出すと、他の項目が未調査のまま
    「この誌はフォームの提出を求めていない」のような**未調査を断定に化けさせる**文面が並ぶ。
    原稿本体の受入形式 (`text_formats`) が分からない誌ではマニフェストの第 1 節が成立しないので、
    これを必須にする。`submission` ブロックを持たない誌ではマニフェストを出力しない。
    """
    return _submission_cfg(profile).get("text_formats") is not None


# =====================================================================
# Caption / Legend の貼り付け用ファイル CAPTIONS.md
# =====================================================================
# ScholarOne の投稿画面の「File Upload」の段は、上げたファイルごとに **Caption / Legend:** 欄
# (書式なしの textarea。文字数の上限なし) を持つ。図表の題と凡例を手で写すと本文と食い違うので、**提出するファイルそのもの**
# (manuscript.docx の Figure Legends 節と tables/*.docx) から抜き出して、貼るだけの形で出す。
# 欄は書式を持てないので、上付き・下付きは Unicode の文字に置き換え、斜体・太字は注記する。

_SUPERSCRIPT = str.maketrans({
    **dict(zip("0123456789", "⁰¹²³⁴⁵⁶⁷⁸⁹")),
    "+": "⁺", "-": "⁻", "−": "⁻", "=": "⁼", "(": "⁽", ")": "⁾",
    **dict(zip("abcdefghijklmnoprstuvwxyz", "ᵃᵇᶜᵈᵉᶠᵍʰⁱʲᵏˡᵐⁿᵒᵖʳˢᵗᵘᵛʷˣʸᶻ")),
})
_SUBSCRIPT = str.maketrans({
    **dict(zip("0123456789", "₀₁₂₃₄₅₆₇₈₉")),
    "+": "₊", "-": "₋", "−": "₋", "=": "₌", "(": "₍", ")": "₎",
    **dict(zip("aehijklmnoprstuvx", "ₐₑₕᵢⱼₖₗₘₙₒₚᵣₛₜᵤᵥₓ")),
})


def _toggle_on(rpr, tag):
    """rPr の太字・斜体などのトグルが**明示的に**オンか (w:val が 0 / false でない)。"""
    el = rpr.find(W(tag)) if rpr is not None else None
    return el is not None and (el.get(W("val")) or "true").lower() not in ("0", "false", "off")


def caption_plain_text(paragraph):
    """段落を書式なしのテキスト欄へ貼れる文字列にする。返り値: (文字列, 注記のリスト)。

    - 上付き・下付きは Unicode の上付き・下付き文字に置き換える (10⁴ / log₂)。置き換えられない
      文字を含むときは ^(…) / _(…) と書き、注記に出す (人が投稿画面の Special Characters で直す)。
    - 斜体・太字は貼ると消えるので、該当する文字列を注記に出す (段落スタイル由来の斜体 =
      TableCaption の全体斜体などは書式であって中身ではないので数えない)。
    - タブは空白、改行 (w:br) は改行にする。フィールドの命令文 (w:instrText) は拾わない。
    """
    out, notes = [], []
    for r in paragraph.iter(W("r")):
        if any(a.tag == W("del") for a in r.iterancestors()):
            continue                      # 変更履歴の削除側は本文ではない
        buf = []
        for child in r:
            if child.tag == W("t"):
                buf.append(child.text or "")
            elif child.tag == W("tab"):
                buf.append(" ")
            elif child.tag in (W("br"), W("cr")):
                buf.append("\n")
            elif child.tag == W("noBreakHyphen"):
                buf.append("-")
        s = "".join(buf)
        if not s:
            continue
        rpr = r.find(W("rPr"))
        va = rpr.find(W("vertAlign")) if rpr is not None else None
        va = va.get(W("val")) if va is not None else None
        if va in ("superscript", "subscript"):
            table, mark, word = ((_SUPERSCRIPT, "^", "上付き") if va == "superscript"
                                 else (_SUBSCRIPT, "_", "下付き"))
            conv = s.translate(table)
            if all(c != o or c.isspace() for c, o in zip(conv, s)):
                notes.append(f"{word} `{s}` を Unicode の `{conv}` にした")
                s = conv
            else:
                notes.append(f"⚠ {word} `{s}` は Unicode にできないので `{mark}({s})` と書いた"
                             " — 投稿画面の Special Characters で直すこと")
                s = f"{mark}({s})"
        if _toggle_on(rpr, "i"):
            notes.append(f"斜体 `{s.strip()}` (貼ると斜体は消える)")
        if _toggle_on(rpr, "b"):
            notes.append(f"太字 `{s.strip()}` (貼ると太字は消える)")
        out.append(s)
    text = re.sub(r"[ \t]+", " ", "".join(out)).strip()
    return text, notes


def collect_caption_entries(manuscript_docx, tables_files, figures_written):
    """提出するファイルから図表の題と凡例を集める。投稿画面の順 (Table → Figure) で返す。

    返り値: [{"kind": "Table"|"Figure", "number": int|None, "file": 表示名|None,
              "text": 貼る文字列, "notes": [...]}]
    - 表: tables.placement: separate なら各 tables/TableN.docx、そうでなければ本文 (末尾) から。
    - 図: 本文の Figure Legends 節 (relocate が集約した ImageCaption + Legend)。図ファイル名は
      題の番号で figures_written (書き出した順 = 本文の初出順) と対応づける。
    """
    from lxml import etree

    def body_of(path):
        with zipfile.ZipFile(path) as z:
            return etree.fromstring(z.read("word/document.xml")).find(W("body"))

    def entry(kind, number, file_name, paragraphs):
        texts, notes = [], []
        for p in paragraphs:
            t, n = caption_plain_text(p)
            if t:
                texts.append(t)
            notes.extend(n)
        return {"kind": kind, "number": number, "file": file_name,
                "text": "\n".join(texts), "notes": notes}

    entries = []
    if tables_files:
        for name, path in tables_files:
            for g in relocate_mod.collect_table_groups(body_of(path)):
                paras = ([g["caption"]] if g["caption"] is not None else []) + g["legends"]
                entries.append(entry("Table", g["number"], name, paras))
    else:
        for g in relocate_mod.collect_table_groups(body_of(manuscript_docx)):
            paras = ([g["caption"]] if g["caption"] is not None else []) + g["legends"]
            entries.append(entry("Table", g["number"], None, paras))
    fig_names = [name for name, _ in (figures_written or [])]
    for g in relocate_mod.collect_figure_groups(body_of(manuscript_docx)):
        n = g["number"]
        name = fig_names[n - 1] if n is not None and 0 < n <= len(fig_names) else None
        entries.append(entry("Figure", n, name, [g["caption"]] + g["legends"]))
    return entries


def write_captions_manifest(out_dir, profile, journal_id, entries):
    """data/output/<journal>/CAPTIONS.md を書く (Caption / Legend 欄に貼る文面)。"""
    name = profile.get("name", journal_id)
    lines = [
        f"# Caption / Legend (貼り付け用) — {name}",
        "",
        "投稿系 (ScholarOne) のファイルを上げる画面 (**File Upload**) で、上げたファイルごとの "
        "**「Caption / Legend:」欄**に、下の枠の中身をそのまま貼る。**このファイル自体はアップロードしない。**",
        "",
        f"- 生成元: `data/output/{journal_id}/` の `manuscript.docx` (図の題と凡例の節) と表ファイル。"
        "**提出するファイルそのものから抜き出した**ので本文と食い違わない。"
        "原稿を直したら `package.sh --mode final` で作り直すこと (このファイルも作り直される)。",
        "- 並びは投稿画面のファイルの順 (Manuscript > **Table** > **Figure** > …)。",
        "- 各枠の 1 行目が題 (`Table 1: …` / `Figure 1: …`)、2 行目以降が凡例。",
        "- 欄は書式なしのテキストなので、**上付き・下付きは Unicode の文字に置き換えてある** (例: 10⁴)。"
        "斜体・太字は貼ると消える — 該当があれば各項の下に書いてある。",
        "- Manuscript・カバーレター・フォームの欄に入れる文面は、ここには無い。",
        "",
    ]
    if not entries:
        lines += ["図表の題と凡例は見つからなかった (本文に図表が無い)。", ""]
    for e in entries:
        label = f"{e['kind']} {e['number']}" if e["number"] is not None else f"{e['kind']} (番号なし)"
        file_note = f" — `{e['file']}`" if e["file"] else (
            " — (本文の末尾にある表)" if e["kind"] == "Table" else " — (図ファイルと対応づけられない)")
        fence = "~~~~" if "```" in e["text"] else "```"
        lines += [f"## {label}{file_note}", "", f"{fence}text", e["text"] or "(題も凡例も無い)", fence, ""]
        for n in e["notes"]:
            lines.append(f"- {n}")
        if e["notes"]:
            lines.append("")
    path = Path(out_dir) / "CAPTIONS.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def write_submission_manifest(out_dir, profile, journal_id, mode, ctx):
    """data/output/<journal>/SUBMISSION.md を書く。

    ScholarOne は原稿を**アップロード種別ごとに分けて**登録させるため、どのファイルをどの種別で
    出すのかを機械生成のチェックリストにしておく。形式・サイズ・順序と、COI Disclosure Form /
    License to Publish の提出要否まで 1 枚に収める (案 B の pptx は SVG と
    300dpi PNG を両方同梱するため肥大するが、profile がサイズ予算を持っているのは動画だけなので、
    サイズは「上限判定」ではなく「一覧」として出す)。

    **実行時の状態と検出結果を受け取る。** profile と出力
    ディレクトリの中身だけからマニフェストを組み立てると、その実行が実際に何をしたか、
    何を検出したかが分からない。そのため (a) 草稿モード / `--keep-figures` でも出力され、
    図が本文に埋め込まれたままなのに「生成モード: final (図: 分離)」と書き、
    (b) 表があるのに「本文に表が無いため移設していない」と断定し、
    (c) 上限超過の動画・受入形式外のファイル・表の色・図と凡例の食い違いといった
    **検出済みの問題を 1 つも載せない** (すべて実測)。
    マニフェストは画面のログが流れたあとに残る唯一のチェックリストであり、投稿は生成の当日に
    行うとは限らない。**信じるほど誤りやすい**状態は機能の目的と正反対である。

    ctx が受け取る鍵:
      relocated     : 提出構成の組み替えを行ったか (= 提出用のパッケージか)
      keep_figures  : --keep-figures 指定だったか (表示の出し分けに使う)
      warnings      : この実行で出た注意の全文 (末尾の節に転記する)
      flags         : 表の行に出す印 (表示名 → "⚠ 上限超過" 等)
      findings      : 規定チェック (validate) の指摘 list[Finding]。**None は「省略した」**
                      (--no-validate)。空リスト = 検査したが指摘なし

    **規定チェックの指摘も載せる。** validate の「規定違反の可能性 (要修正)」を載せず、
    冒頭の断定文が注意の件数だけを数えると、画面に要修正が何件出ていても「この実行で 1 件の注意が
    出ている」と書くことになる。投稿は生成の当日に行うとは限らず、後日このファイルだけを見て
    投稿する運用では上限超過や必須節の欠落が完全に見えなくなる。
    """
    sub = _submission_cfg(profile)
    tables_cfg = profile.get("tables") if isinstance(profile.get("tables"), dict) else {}
    limits = profile.get("limits") if isinstance(profile.get("limits"), dict) else {}
    at = profile.get("article_type")
    at_name = ((profile.get("article_types") or {}).get(at) or {}).get("name", "") if at else ""
    relocated = bool(ctx.get("relocated"))
    warn_list = list(ctx.get("warnings") or [])
    flags = ctx.get("flags") or {}
    # 規定チェックの指摘 (None = --no-validate で省略した)
    findings = ctx.get("findings")
    must_list = [f for f in (findings or []) if f.level == validate_mod.LEVEL_MUST]
    info_list = [f for f in (findings or []) if f.level == validate_mod.LEVEL_INFO]

    # 値が無いのは「規定に無い」ではなく「プロファイルに記録が無い」である。
    # 断定に化けさせると、出し忘れると受理が止まる書類 (利益相反の申告書等) について
    # 「求められていない」と読める文面が機械生成されてしまう。
    def fmt_list(key, fallback="(プロファイルに記録なし。規定を確認すること)"):
        v = sub.get(key)
        return " / ".join(str(x).upper() for x in v) if v else fallback

    lines = [
        f"# 提出物マニフェスト — {profile.get('name', journal_id)}",
        "",
    ]
    # --- 提出用でないパッケージはいちばん先に宣言する ---
    if not relocated:
        why = "--keep-figures (図を本文に残す指定)" if ctx.get("keep_figures") else "草稿モード"
        lines += [
            f"> ⛔ **このパッケージは提出用ではない** ({why} で生成した)。",
            "> **図が本文に埋め込まれたまま**であり、提出構成の組み替え (表の末尾移設 / "
            "図の題と凡例の集約) も行っていない。",
            "> 提出物を作るには `--mode final` を `--keep-figures` なしで実行すること。",
            "> 以下の一覧はこの状態のまま機械生成したものである。",
            "",
        ]
    # 注意と規定チェックの要修正を合算して断定する。注意だけを
    # 数えると、要修正が何件出ていても「1 件の注意が出ている」のように書けてしまう。
    if warn_list or must_list:
        parts = []
        if must_list:
            parts.append(f"規定チェックの要修正 {len(must_list)} 件")
        if warn_list:
            parts.append(f"注意 {len(warn_list)} 件")
        lines += [
            f"> ⚠ **この実行で {' / '.join(parts)} が出ている。"
            "末尾の該当する節を必ず読むこと。**",
            "",
        ]
    if findings is None:
        # 沈黙を「問題なし」と読ませない (未調査を断定に化けさせないのと同じ考え方)
        lines += [
            "> ℹ **規定チェック (語数・上限・執筆 lint) は `--no-validate` で省略した。**"
            "本ファイルに規定チェックの節は無い。",
            "",
        ]
    lines.append(f"- 雑誌プロファイル: `{journal_id}`"
                 + (f" ({profile['name']})" if profile.get("name") else ""))
    if at:
        lines.append(f"- 記事種別: `{at}`" + (f" ({at_name})" if at_name else ""))
    if profile.get("submission_system"):
        lines.append(f"- 投稿系: <{profile['submission_system']}>")
    # 図の扱いは mode ではなく**実際に分離したか**で書く。
    # `mode == 'draft'` だけを見ると、`--mode final --keep-figures` で
    # 図が埋め込まれたままなのに「図: 分離」と書いてしまう。
    fig_state = "分離" if relocated else (
        "埋込 (--keep-figures)" if ctx.get("keep_figures") else "埋込")
    lines += [
        f"- 生成モード: `{mode}` (図: {fig_state})",
        f"- 生成元: `data/output/{journal_id}/`",
    ]
    # どの原稿から作ったパッケージかを残す。roundtrip.sh が提出パッケージを
    # Drive の submission-<journal>/ へ届ける前に、今の入力ルートと一致するかを照合する
    # (動作例 data/dummy/bhi で作ったパッケージが data/output/bhi/ に残っていても、日付だけでは
    #  見分けられない。**この行の書式は roundtrip.sh が読むので変えるときは両方を直すこと**)。
    if ctx.get("input_root"):
        lines.append(f"- 原稿の入力ルート: `{ctx['input_root']}`")
    lines += [
        "",
        "> `profile.yaml` の `submission` ブロックから機械生成したチェックリストである。",
        "> **投稿系の画面表示が優先する** — 規定が改訂されたらプロファイル側を直すこと。",
        "",
    ]

    total_bytes = 0
    n_section = 0

    def section(title, note_lines, entries, empty_note, notes=None):
        nonlocal total_bytes, n_section
        n_section += 1
        lines.append(f"## {n_section}. {title}")
        lines.append("")
        lines.extend(note_lines)
        lines.append("")
        if entries:
            rows, size = _file_table(entries, flags=flags, notes=notes)
            total_bytes += size
            lines.extend(rows)
        elif empty_note:
            lines.append(empty_note)
        lines.append("")

    # --- 1. Text ---
    text_notes = [f"受入形式: {fmt_list('text_formats')}"]
    if ctx.get("structure"):
        text_notes.append("")
        text_notes.append(f"構成: {ctx['structure']}")
    section("Text (原稿本体)", text_notes, ctx["text"],
            "**原稿本体がありません** (先に `bash scripts/build.sh` を実行してください)。")

    # --- 2. Tables ---
    tbl_notes = [f"受入形式: {fmt_list('table_formats')}"
                 + ("。**画像化は不可** (Word の表オブジェクトのまま出す)"
                    if str(tables_cfg.get("object") or "").lower() == "word" else "")]
    if ctx.get("tables_moved"):
        tbl_notes.append("")
        tbl_notes.append(
            f"本文ファイルの末尾へ **{ctx['tables_moved']} 件**を移設済み "
            f"(題は表の上・凡例は表の下。元位置には `[Table N about here]` を残した)。"
            + ("別ファイルでの提出も認められている。"
               if tables_cfg.get("separate_file_allowed") else ""))
    elif ctx.get("tables_files"):
        # tables.placement: separate (1 表 1 ファイル)
        tbl_notes.append("")
        tbl_notes.append(
            f"**1 表 1 ファイル**で `tables/` に出した ({len(ctx['tables_files'])} 件。"
            "各ファイルは題 (表の上)・表・凡例 (表の下))。"
            "本文の元位置には `[Table N about here]` を残し、**本文ファイルには表を入れていない**。")
        tbl_notes.append("")
        tbl_notes.append("**表番号の順にアップロードする** (下表の順。表の # が本文の表番号と一致する)。"
                         "投稿画面の Caption / Legend 欄には `CAPTIONS.md` の文面を貼る。")
    elif relocate_mod.table_placement(profile) in ("end", "separate"):
        tbl_notes.append("")
        # 条件を `tables.placement == "end"` だけにしてモードを見ないと、
        # **表がある原稿を草稿モードで回したときに「本文に表が無い」と断定**してしまう
        # (実測)。移設したかどうかは relocated でしか分からない。
        if relocated:
            tbl_notes.append("本文に表が無いため移設していない。"
                             if relocate_mod.table_placement(profile) == "end"
                             else "本文に表が無いため表ファイルは無い。")
        else:
            tbl_notes.append(
                "**このモードでは表を移設していない** (本文に表があるかどうかは判定していない)。"
                "提出物を作るときは `--mode final` を `--keep-figures` なしで実行すること。")
    # 末尾移設をした場合は上の注記で説明が済んでいるので、空表の注記は出さない (重複を避ける)
    section("Tables (表)", tbl_notes, ctx.get("tables_files") or [],
            "" if ctx.get("tables_moved") else "別ファイルとしての表はない。")

    # --- 3. Figures ---
    fig_notes = [f"受入形式: {fmt_list('figure_formats')}"]
    dpi = (_figures_cfg(profile) or {}).get("dpi")
    if dpi:
        fig_notes[0] += f"、最低 {dpi} dpi"
    fig_notes.append("")
    # 下表は export_figures が書き出した順 (= 本文の初出順) をそのまま並べる。
    # 投稿系は**上げた順に図番号を割り当てる**ので、この順序が狂うと全図が凡例と食い違う。
    fig_notes.append("**本文の初出順にアップロードする** (下表の順。表の # が本文の図番号と一致する)。")
    if ctx.get("legends_section"):
        fig_notes.append(
            "投稿画面の Caption / Legend 欄には `CAPTIONS.md` の文面を貼る。"
            f"図の題と凡例は原稿本体の `{ctx['legends_section']}` 節にまとめてあり、"
            "画像ファイル側には書かない。")
    section("Figures (図)", fig_notes, ctx.get("figures") or [],
            "分離出力した図はない "
            + ("(`--mode final` を `--keep-figures` なしで実行すると生成される)。"
               if not relocated else "(原稿に図参照がない)。"))

    # --- 4. Video ---
    video_notes = [f"受入形式: {fmt_list('video_formats', '(動画の規定なし)')}"
                   + (f"、1 ファイル {limits['video_mb']} MB 以内"
                      if limits.get("video_mb") else "")]
    section("Video (動画)", video_notes, ctx.get("video") or [],
            f"動画なし (`<INPUT_ROOT>/{SUPP_DIRNAME}/` に置けば複製される)。")

    # --- 5. Supplementary ---
    supp_notes = []
    if sub.get("supplementary") == "as-is":
        supp_notes.append("**無変換で公開される**。査読対象であり、受理後は変更できないので"
                          "投稿時に最終形で出すこと。本文中では図表と同様に引用のかたちで言及する。")
    else:
        supp_notes.append("補足資料。")
    section("Supplementary (補足資料)", supp_notes, ctx.get("supplementary") or [],
            f"補足資料なし (`<INPUT_ROOT>/{SUPP_DIRNAME}/` に置けば無変換で複製される)。")

    # --- 6. 提出フォーム ---
    n_section += 1
    lines.append(f"## {n_section}. 提出フォーム (アップロード種別ではない)")
    lines.append("")
    forms = sub.get("forms")
    if forms:
        # 通数と記入者は誌によって違う (著者ごとに 1 通の誌も、連絡著者が全著者を代表して
        # 1 通の誌もある) ので、ここでは断定せず profile の各項目の注記に任せる。
        lines.append("**誰が何通出すかは各項目の注記と誌の規定に従う。**")
        lines.append("")
        for f in forms:
            lines.append(f"- [ ] {f}")
    else:
        # 未調査を「求められていない」と断定しない。
        lines.append("**フォームの記録がプロファイルに無い** (規定を確認すること)。"
                     "出し忘れると受理が止まる書類 (利益相反の申告書など) が"
                     "この誌にも要る可能性がある。")
    lines.append("")

    # --- 7. アップロード種別ではないもの (用途を注記する) ---
    if ctx.get("other"):
        n_section += 1
        lines.append(f"## {n_section}. 同じパッケージに入っているが、アップロード種別ではないもの")
        lines.append("")
        lines.append("**投稿画面のどの欄に出すか (あるいは出さないか) はファイルごとに違う。**")
        lines.append("")
        # 用途は名前で引く (差分 docx は初回投稿では上げない)。
        other_notes = {
            "cover-letter.docx": "投稿画面のテキスト欄または添付",
            "revise-report.docx": "**査読対応の再投稿でのみ使う**",
            "manuscript-diff.docx": "**査読対応の再投稿でのみ使う。初回投稿では上げない**",
            "CAPTIONS.md": "**アップロードしない**。投稿画面の各ファイルの Caption / Legend 欄に貼る文面",
        }
        rows, size = _file_table(ctx["other"], flags=flags, notes=other_notes)
        total_bytes += size
        lines.extend(rows)
        lines.append("")
        if any(Path(p).name == "manuscript-diff.docx" for _, p in ctx["other"]):
            lines.append("> 差分版 (マークアップ原稿) を出すかどうかは規定に記述が無く、"
                         "**未確定**である (求められたら出す)。")
            lines.append("")

    # --- 合計 ---
    n_files = sum(len(ctx.get(k) or []) for k in
                  ("text", "tables_files", "figures", "video", "supplementary", "other"))
    lines.append("---")
    lines.append("")
    lines.append(f"**合計: {n_files} ファイル / {_human_size(total_bytes)}**")
    lines.append("")
    lines.append("(サイズは 10 進 (1MB = 1,000,000 バイト) で数えている。"
                 "**動画以外は投稿系の上限判定ではなく一覧である** — "
                 "profile がサイズ予算を持つのは動画だけなので、"
                 "他は投稿系の画面表示で確認すること。)")
    lines.append("")

    # --- 規定チェック (validate の指摘をマニフェストに残す) ---
    # 注意の節より前に置く — 上限超過や必須節の欠落は、図変換の注意より投稿に直結する。
    if findings is not None:
        lines.append("---")
        lines.append("")
        lines.append(f"## 規定チェック (要修正 {len(must_list)} 件 / 参考 {len(info_list)} 件)")
        lines.append("")
        if not findings:
            lines.append("限度内 (または `limits` 未設定)。")
            lines.append("")
        else:
            lines.append("**要修正は投稿前に直すこと。** Markdown 段階の機械判定なので"
                         "最終判断は実物で行う (検査はエラーにしない)。"
                         "単独で回し直すには "
                         "`python3 main/step05_package/validate.py --input-root <原稿> "
                         "--journal <id> --article-type <種別>`。")
            lines.append("")
            for title, rows in (("規定違反の可能性 (要修正)", must_list),
                                ("参考情報", info_list)):
                if not rows:
                    continue
                lines.append(f"### {title} — {len(rows)} 件")
                lines.append("")
                for f in rows:
                    lines.append(f"- {validate_mod.finding_text(f)}")
                lines.append("")

    # --- 注意 (この実行で検出したものをマニフェストに残す) ---
    # 画面のログは流れるがマニフェストは残る。投稿は生成の当日に行うとは限らず、
    # 共著者の確認を待って別の人が上げることもある。その人が読むのはこのファイルだけである。
    if warn_list:
        lines.append("---")
        lines.append("")
        lines.append(f"## 注意 (この実行で検出したもの — {len(warn_list)} 件)")
        lines.append("")
        lines.append("**投稿する前にすべて目を通すこと。**"
                     "パッケージを作り直しても、原稿を直さない限り同じ注意が出る。")
        lines.append("")
        for w in warn_list:
            lines.append(f"- {w}")
        lines.append("")

    path = Path(out_dir) / "SUBMISSION.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def cmd_assemble(args):
    input_root = args.input_root
    # rmtree の前に journal id を検証する (不正値での破壊的削除を防ぐ)。
    out_dir = _safe_journal_out_dir(args.journal)
    profile = load_profile(args.journal, args.article_type)
    mode = resolve_mode(profile, args.mode)
    fmt = resolve_format(profile, args.format)
    export, fallback = resolved_export(fmt)
    export_warning = None
    if mode == "final" and not args.keep_figures:
        # --keep-figures は図を分離出力しない (禁止形式の図が生成されない) ため対象外。
        # 生成経路が無い形式はここで停止する (pdf などへの既定代替はしない)
        require_export_route(fmt, export)
        # 代替なら停止。明示指定は明示同意 (--allow-disallowed-format) を要求する
        export_warning = check_export_allowed(profile, fmt, export, fallback,
                                              args.allow_disallowed_format)
    dpi = resolve_dpi(profile, args.dpi)
    # pptx 経路の設定は「実際に pptx を出すとき」だけ解決する (綴り違いの検証を含むため、
    # pptx を使わない誌に無関係なエラーを出さない)。
    pptx_cfg = (resolve_pptx_cfg(profile, dpi, args.slide_fit)
                if export == "pptx" and mode == "final" and not args.keep_figures else None)

    # 提出パッケージは生成物なので毎回作り直す (data/output/<journal>/ 全体を再生成)。
    # flat な data/output/*.docx (roundtrip 集約) は別物なので触らない。
    if out_dir.exists():
        print(f"  注意: 既存の {out_dir}/ を再生成します (手置きファイルがあれば事前に退避してください)")
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"== Step 05 投稿パッケージ組立 ==")
    print(f"  INPUT_ROOT = {input_root}")
    print(f"  JOURNAL    = {args.journal}  ({profile.get('name', '(名称未設定)')})")
    if profile.get("article_types") and profile.get("article_type"):
        at = profile["article_type"]
        at_name = (profile["article_types"].get(at) or {}).get("name", "")
        print(f"  TYPE       = {at}  ({at_name})")
    print(f"  MODE       = {mode}  (図: {'埋込' if mode == 'draft' else '分離'})")
    if mode == "final":
        # export is None = 生成経路なし。--keep-figures のときだけここに来る (分離しないので害はない)
        if export is None:
            note = " [生成経路なし。--keep-figures のため図は分離しません]"
        else:
            note = f" [{fmt}→{export} 代替]" if fallback else ""
        print(f"  FIGURES    = 形式={fmt}{note} / dpi={dpi}")
        if pptx_cfg:
            print(f"  PPTX       = mode={pptx_cfg['mode']} / slide_fit={pptx_cfg['slide_fit']} / "
                  f"png_fallback_dpi={pptx_cfg['png_fallback_dpi']} / "
                  f"text_to_path={str(pptx_cfg['text_to_path']).lower()}")
        if export_warning:   # 受入形式外の図を作ろうとしている
            print(f"  {export_warning}")
    print(f"  OUT_DIR    = {out_dir}/")

    collected = []
    missing = []

    main_build = BUILD_DIR / "main.docx"
    if not main_build.is_file():
        sys.exit(f"エラー: {main_build} がありません。先に 'bash scripts/build.sh' を実行してください。")

    # main.docx がどの雑誌で build されたかを照合し、--journal と異なれば警告
    # (package は事前 build の docx をそのまま使うため、雑誌固有体裁の取り違えを検知する)。
    prov = BUILD_DIR / ".journal"
    if prov.is_file():
        # 1 行目 = journal id (2 行目は記事種別の provenance。ここでの照合は
        # journal のみ — 記事種別は build の出力を変えないため不一致でも docx は正しい)
        prov_lines = prov.read_text(encoding="utf-8").splitlines()
        built_for = prov_lines[0].strip() if prov_lines else ""
        if built_for and built_for != args.journal:
            print(f"  [注意] data/step02_build/main.docx は journal={built_for} で build されています "
                  f"(今回の --journal {args.journal} と不一致)。雑誌固有の体裁を反映するには "
                  f"'bash scripts/build.sh --journal {args.journal}' か 'package.sh --build' を使ってください。")
        # 2 行目 (記事種別) も照合する。
        # build を letter、package を既定 (original) で回すと 1200 語ではなく 4000 語で検証されるのに、
        # 照合しなければ何の注意も出ない。build の出力は種別で
        # 変わらないので docx 自体は正しく、警告に留める。
        built_type = prov_lines[1].strip() if len(prov_lines) > 1 else ""
        this_type = profile.get("article_type") or ""
        if built_type and this_type and built_type != this_type:
            print(f"  [注意] data/step02_build/main.docx は article_type={built_type} で "
                  f"build されています (今回の検証は {this_type})。語数・抄録の上限は {this_type} の値で照合します。"
                  f"意図が違う場合は '--article-type {built_type}' を付け直してください。")

    # --- manuscript ---
    manuscript_out = out_dir / "manuscript.docx"
    # 受入形式外の警告は末尾の「図変換の注意」にも残す (冒頭表示だけだと流れる)
    fig_warnings = [export_warning] if export_warning else []
    struct_warnings = []                 # 提出構成の組み替え・表 lint の注意
    # 組み替えの結果 (SUBMISSION.md が読む)。草稿 / --keep-figures では何もしないので 0 のまま。
    r = {"stripped": 0, "figures": 0, "tables": 0, "legends_section": None, "tables_files": []}
    # 実行が実際に何をしたかを SUBMISSION.md へ渡す。
    #   relocated  = 提出構成の組み替えを行ったか (= 提出用のパッケージか)
    #   fig_written = 分離出力した図を **書き出した順** で保つ (ディレクトリは読み直さない)
    relocated = (mode == "final" and not args.keep_figures)
    fig_written = []
    manifest_flags = {}     # SUBMISSION.md の表に出す印 (表示名 → "⚠ 上限超過" 等)
    if mode == "final" and not args.keep_figures:
        # 図のプレースホルダ化 → 提出構成の組み替え (表末尾移設 / Figure Legends 集約)
        # → 表の体裁 lint を 1 回の書庫の開閉で行う。
        r.update(strip_inline_figures(main_build, manuscript_out, profile=profile,
                                      tables_dir=out_dir / "tables"))
        n = r["stripped"]
        struct_warnings.extend(r["warnings"])
        struct_warnings.extend(r["lint"])
        label_extra = ""
        if r["figures"]:
            label_extra += f" / 図の題+凡例 {r['figures']} 組を '{r['legends_section']}' へ集約"
        if r["tables"]:
            label_extra += f" / 表 {r['tables']} 組を末尾へ移設"
        if r["tables_files"]:
            label_extra += f" / 表 {len(r['tables_files'])} 組を tables/ へ分離"
        collected.append((f"manuscript (図 {n} 件をプレースホルダ化{label_extra})",
                          str(manuscript_out)))
        for name, path in r["tables_files"]:
            collected.append((f"table (別ファイル) {name}", str(path)))
        # 除去した本文図数と原稿の図参照数を照合し、ずれれば警告 (番号ずれを黙認しない)。
        # 照合相手を body_only (テキストボックス内図を除く) にする。
        # (manifest 全件と比べると、textbox 内図があるだけで必ず不一致警告が出る)。
        n_refs = len(manuscript_figures(input_root, body_only=True))
        if n != n_refs:
            fig_warnings.append(
                f"本文から除去した図 {n} 件と原稿の本文図参照 {n_refs} 件が一致しません。"
                "本文中の非図 inline 画像がある場合、'[Figure N about here]' の番号と "
                "figures/ の番号がずれる可能性があります (要確認)。"
            )
        # 図を分離出力。書き出した順 (= 本文の初出順) をそのまま受け取り、
        # SUBMISSION.md へ渡す (ディレクトリを読み直すと文字列順になり初出順でなくなる)。
        n_fig, fw, fig_written = export_figures(
            input_root, profile, out_dir / "figures", fmt, export, fallback, dpi,
            pptx_cfg=pptx_cfg
        )
        fig_warnings.extend(fw)
        print(f"  figures: {n_fig} 件を {out_dir}/figures/ に分離出力")
        # figures/ の件数と Figure Legends の項目数が食い違うなら、
        # 図番号の 3 系統 (プレースホルダ / 集約した題 / 分離出力ファイル) が割れている。
        if r["legends_section"] and n_fig != r["figures"]:
            struct_warnings.append(
                f"★要注意: 分離出力した図 {n_fig} 件と '{r['legends_section']}' に集約した"
                f"題 {r['figures']} 件が一致しません。題の無い図があるか、図以外の inline 画像が"
                "本文に混ざっています (提出物で図と凡例の対応が崩れます)。")
    else:
        shutil.copyfile(main_build, manuscript_out)
        label = "manuscript (図埋込)" if mode == "draft" else "manuscript (図埋込・--keep-figures)"
        collected.append((label, str(manuscript_out)))
        # この経路では構成の組み替えをしない。profile が要求しているなら黙らせない。
        skipped = []
        if (_figures_cfg(profile).get("legends_section")):
            skipped.append(f"図凡例の '{_figures_cfg(profile)['legends_section']}' への集約")
        placement = relocate_mod.table_placement(profile)
        if placement == "end":
            skipped.append("表の末尾移設")
        elif placement == "separate":
            skipped.append("表の別ファイル化")
        if skipped:
            why = ("草稿モード" if mode == "draft" else "--keep-figures (図を本文に残す指定)")
            struct_warnings.append(
                f"{' と '.join(skipped)} は {why} のため行いませんでした。"
                "提出物を作るときは '--mode final' を --keep-figures なしで実行してください。")
        struct_warnings.extend(lint_manuscript_tables(manuscript_out, profile))

    # --- 差分 docx (任意。査読対応の提出に有用) ---
    # main.docx より古い差分なら陳腐化警告 (初回投稿への古い差分混入を防ぐ。
    # roundtrip.sh の phase_collect と同方式。同梱自体は維持し非破壊)。
    diff_src = DIFF_DIR / "main_diff.docx"
    if diff_src.is_file():
        # 別の原稿・別の誌から作った差分や古い差分が、提出物に黙って混ざらないようにする。
        # diff.sh は誌と新版の原稿のパスを .main_diff.source に記録する。食い違えば SUBMISSION.md の注意にも載せる
        # (画面の 1 行だけだと、SUBMISSION.md を投稿前の確認の一覧として読む人が見落とす)。
        diff_notes = []
        if main_build.is_file() and diff_src.stat().st_mtime < main_build.stat().st_mtime:
            diff_notes.append("data/step02_build/main.docx より古い")
        rec = DIFF_DIR / ".main_diff.source"
        if rec.is_file():
            rec_lines = rec.read_text(encoding="utf-8").splitlines()
            d_journal = rec_lines[0].strip() if rec_lines else ""
            d_new = rec_lines[1].strip() if len(rec_lines) > 1 else ""
            if d_journal and d_journal != args.journal:
                diff_notes.append(f"journal={d_journal} で作られている (今回は {args.journal})")
            if d_new and Path(d_new).resolve() != (Path(input_root) / "main.md").resolve():
                diff_notes.append(f"新版が {d_new} である (今回の原稿は {input_root}/main.md)")
        else:
            diff_notes.append("どの原稿から作ったかの記録が無い")
        if diff_notes:
            msg = ("manuscript-diff.docx (元は data/step03_diff/main_diff.docx) は "
                   + " / ".join(diff_notes) + "。別の原稿や古い版の差分かもしれないので、"
                   "再投稿で使うなら 'bash scripts/diff.sh' で作り直し、使わないなら "
                   "data/step03_diff/main_diff.docx を消してから package し直してください")
            print(f"  [注意] {msg}")
            struct_warnings.append(msg)
    _copy_if_exists(diff_src, out_dir / "manuscript-diff.docx",
                    "manuscript-diff (任意)", collected, missing)

    # --- revise-report / cover-letter (任意) ---
    # 前段 (build) の出力は入力ルートを切り替えても残るため、別原稿の
    # revise-report.docx が [OK] で提出物に並ぶことがある。build.sh 側でも掃除するが、
    # 「package だけ回した」「INPUT_ROOT を変えて package だけ回した」経路も残るので、
    # 一次ソース (<INPUT_ROOT>/<name>.md) の有無を照合して黙らせない。
    for opt in ("revise-report", "cover-letter"):
        docx = BUILD_DIR / f"{opt}.docx"
        if docx.is_file() and not (Path(input_root) / f"{opt}.md").is_file():
            print(f"  [注意] {docx} を集めましたが、今回の入力ルートに {input_root}/{opt}.md が"
                  f"ありません。**別の原稿でビルドした古い docx が混ざっている可能性**があります "
                  f"(不要なら {docx} を消してから再実行してください)。")
    _copy_if_exists(BUILD_DIR / "revise-report.docx", out_dir / "revise-report.docx",
                    "revise-report (任意)", collected, missing)
    _copy_if_exists(BUILD_DIR / "cover-letter.docx", out_dir / "cover-letter.docx",
                    "cover-letter (任意)", collected, missing)

    # --- supplementary / video の無変換パススルー ---
    supp_entries, video_entries = copy_supplementary(
        input_root, profile, out_dir, struct_warnings, flags=manifest_flags)
    for label, entries in (("supplementary (無変換)", supp_entries),
                           ("supplementary (動画)", video_entries)):
        for name, path in entries:
            collected.append((f"{label} {name}", str(path)))

    # --- 検証 (語数・上限・執筆 lint) ---
    # **マニフェストを書く前に走らせる**。マニフェストを書いた
    # あとで validate を回すと、「規定違反の可能性 (要修正)」が
    # SUBMISSION.md に 1 件も載らない。しかもマニフェストは検出件数を断定的に書くので、
    # 画面に要修正が何件出ていても「この実行で 1 件の注意が出ている」と書いてしまう
    # (マニフェストは画面のログが流れたあとに残る唯一のチェックリストである)。
    # **validate はファイルに一切触れない**
    # (原稿と profile を読んで指摘を返すだけ。check_reference_layout も読み取りのみ) ため、
    # 先に回しても成果物は変わらない。指摘の一覧は下 (集約結果の後) で印字する。
    #
    # profile は解決済み (load_profile が article_type まで解決)。validate 側の再解決は
    # journal_profile.resolve の冪等ガード (_resolved) で素通りする。
    # journal_id を渡すと reference.docx の実体裁との突合も掛かる
    v_findings = None            # None = --no-validate で省略した (空リスト = 指摘なし と区別する)
    if not args.no_validate:
        v_findings = validate_mod.validate(input_root, profile, args.article_type,
                                           journal_id=args.journal)

    # --- Caption / Legend の貼り付け用 CAPTIONS.md (提出用パッケージで、
    #     提出マニフェストを書く誌のみ = 既存 4 誌には出ない)。マニフェストより前に書き、
    #     マニフェストの「アップロード種別ではないもの」に載せる ---
    if relocated and has_submission_spec(profile):
        cap_entries = collect_caption_entries(manuscript_out, r["tables_files"], fig_written)
        captions = write_captions_manifest(out_dir, profile, args.journal, cap_entries)
        collected.append((f"CAPTIONS (Caption / Legend の貼り付け用。{len(cap_entries)} 件)",
                          str(captions)))
        for e in cap_entries:
            for n in e["notes"]:
                if n.startswith("⚠"):
                    struct_warnings.append(f"CAPTIONS.md の {e['kind']} {e['number']}: {n}")

    # --- 提出マニフェスト SUBMISSION.md (submission.text_formats を持つ誌のみ) ---
    if has_submission_spec(profile):
        structure = None
        if relocated:
            parts_desc = ["Title page → Abstract → 本文 → Declarations → References"]
            if r["figures"]:
                parts_desc.append(f"**{r['legends_section']}** ({r['figures']} 組)")
            if r["tables"]:
                parts_desc.append(f"**表** ({r['tables']} 組)")
            structure = " → ".join(parts_desc) + \
                "。図は本文から分離し `[Figure N about here]` を残した。"
            if r["tables_files"]:
                structure += ("表も本文から分離し `[Table N about here]` を残した "
                              "(表は `tables/` の 1 表 1 ファイル。本文の末尾には置いていない)。")
        manifest = write_submission_manifest(
            out_dir, profile, args.journal, mode,
            {
                "text": [(manuscript_out.name, manuscript_out)],
                # tables.placement: separate のときだけ非空 (end では本文末尾に含める)
                "tables_files": [(nm, p) for nm, p in r["tables_files"]] if relocated else [],
                # export_figures が書き出した順 (= 本文の初出順) をそのまま使う
                "figures": list(fig_written),
                "video": [(n, p) for n, p in video_entries],
                "supplementary": [(n, p) for n, p in supp_entries],
                "other": [(Path(p).name, p) for label, p in collected
                          if Path(p).name in ("cover-letter.docx", "revise-report.docx",
                                              "manuscript-diff.docx", "CAPTIONS.md")],
                "structure": structure,
                "tables_moved": r["tables"] if relocated else 0,
                "legends_section": r["legends_section"] if relocated else None,
                # 実行時の状態と検出結果を渡す (profile と出力ディレクトリの中身だけでは
                # 「この実行が何をしたか / 何を見つけたか」が分からない)。
                "relocated": relocated,
                # roundtrip.sh の配送前の照合に使う
                "input_root": str(input_root),
                "keep_figures": bool(args.keep_figures),
                "warnings": list(struct_warnings) + list(fig_warnings),
                "flags": manifest_flags,
                # 規定チェックの指摘 (None = --no-validate で省略)
                "findings": v_findings,
            })
        collected.append(("SUBMISSION (提出マニフェスト)", str(manifest)))

    # --- 集約結果 ---
    print("\n-- 集約した提出物 --")
    for label, path in collected:
        print(f"  [OK]   {label}: {path}")
    for label, path in missing:
        print(f"  [skip] {label}: {path} は無し")

    # --- 検証結果の表示 (実行そのものはマニフェストより前で済ませてある) ---
    # 戻り値は Finding の list (level = 要修正 / 参考)。表示は validate 側に任せ、
    # 「規定違反の可能性 (要修正)」と「参考情報」に区分して出す。
    # 印字は集約結果の後に置く (実行そのものはマニフェストより前)。
    if v_findings is not None:
        print("\n-- 規定チェック (validate) --")
        validate_mod.print_findings(v_findings)

    # --- 匿名版の要求を黙殺しない (blinded はスキーマ拡張。自動伏字は未実装。docs/profile-schema.md) ---
    if profile.get("blinded"):
        print("\n  [注意] この雑誌は匿名版 (blinded: true / double-anonymous) を要求します。"
              "著者・所属の伏字は未自動化です — 提出前に手動で匿名化してください。")

    # --- 図変換の警告 ---
    if fig_warnings:
        print("\n-- 図変換の注意 --")
        for w in fig_warnings:
            print(f"  [注意] {w}")

    # --- 提出構成 (移設・集約・表の体裁・補足資料) の警告 ---
    if struct_warnings:
        print("\n-- 提出構成の注意 --")
        for w in struct_warnings:
            print(f"  [注意] {w}")

    print(f"\n== 完了: {out_dir}/ ==")
    return 0


# =====================================================================
# エントリ
# =====================================================================

def main(argv=None):
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--input-root", required=True, help="原稿ルート (data/dummy または src)")
    common.add_argument("--journal", default=DEFAULT_ID, help="雑誌プロファイル id (既定 _default)")
    common.add_argument("--article-type", default=None,
                        help="記事種別 (article_types を持つ誌のみ。limits/abstract を種別値で解決)")
    common.add_argument("--mode", choices=["draft", "final"], default=None,
                        help="図の扱い (既定: profile.figures.embed)")
    # 綴り違いが黙って別の形式に化けないよう受入値を明示する (検証は resolve_format)。
    # pptx はベクター提出。jpeg は生成非対応。
    common.add_argument("--format", default=None,
                        help="図形式の上書き (pdf/png/pptx/tiff/eps。jpeg は生成非対応)")
    # スライド寸法が規格 (1〜56 インチ) を外れる図の退避経路を CLI からも選べるようにする
    # (profile を書き換えずに済ませるため)。
    common.add_argument("--slide-fit", choices=list(PPTX_SLIDE_FITS), default=None,
                        help="pptx のスライド寸法 (figure=図の実寸 / fixed=既定サイズに中央配置)。"
                             "既定: profile.figures.pptx.slide_fit")
    common.add_argument("--font-handling", choices=["outline", "embed"], default=None,
                        help="最終図 svg→pdf のフォント処理上書き")
    # figure-plan も --keep-figures を解する。assemble 専用にすると、
    # 「図を分離しないので形式検査は対象外」という assemble 側の判断が figure-plan に伝わらず、
    # --keep-figures 付きでも figure-plan が受入形式照合で停止する (BHI の pptx 主形式で実測)。
    common.add_argument("--keep-figures", action="store_true",
                        help="最終モードでも図を manuscript に残す (分離しない)")
    # 受入形式外の形式を明示指定したときの明示同意。警告どまりで生成すると、
    # BHI で --format png と --format pdf を打ち間違えたときに規定違反の図一式が終了コード 0 で揃う。
    common.add_argument("--allow-disallowed-format", action="store_true",
                        help="誌の受入形式 (submission.figure_formats) 外の図を承知のうえで生成する")

    pp = sub.add_parser("figure-plan", parents=[common],
                        help="最終モードで pdf 化が要る非 mermaid svg を TSV 列挙")
    pp.set_defaults(func=cmd_figure_plan)

    pa = sub.add_parser("assemble", parents=[common], help="提出一式を集約")
    pa.add_argument("--dpi", default=None, help="ラスタ図の dpi 上書き")
    pa.add_argument("--no-validate", action="store_true", help="語数等の検証をしない")
    pa.set_defaults(func=cmd_assemble)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
