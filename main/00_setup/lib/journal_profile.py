#!/usr/bin/env python3
"""journal_profile.py — 雑誌プロファイルの読み込み・スキーマ既定値・記事種別解決 (共通モジュール)。

docs/profile-schema.md。profile.yaml の読み込み (load)・スキーマ既定値 (DEFAULTS)・記事種別の解決 (resolve) を
本モジュールに集約する。build_docx.py / package.py / validate.py がそれぞれ profile.yaml を読み、
既定値を各呼び出し側の `.get()` に書くと、30 個を超えるキーの既定値が呼び出し側ごとに
食い違いうるため。

【読み込み経路】`main/00_setup/lib/` は先頭が数字のディレクトリ名でパッケージ import
できず `__init__.py` も無いため、呼び出し側 (main/stepNN_*/xxx.py) は次の 1 行で
本ディレクトリを sys.path に足してから import する (docs/profile-schema.md に記録):

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "00_setup" / "lib"))
    import journal_profile

基準パスは呼び出し側スクリプトの実体位置 (`__file__`) から辿る (parents[1] = main/)。
CWD 非依存で、コンテナ内 (/workspace) とホストのどちらでも同じ式で解決できる。
一方 profile.yaml 自体の探索 (JOURNALS_DIR) は CWD 相対 (リポジトリルートで
実行する規約。build.sh / package.sh が cd で保証する)。

【記事種別の解決規則】(docs/profile-schema.md):
  優先順: article_type 引数 (--article-type) > profile.article_type > 指定なし。
  (a) 上書きは深さ 1 の部分マージ (全置換にしない)。ただし種別の
      abstract_structured が false のときは abstract.labels を明示的に空 [] にする
      (部分マージだと前種別の構造化ラベルが残るため)。
  (b) キー写像: word_count→limits.word_count / abstract_words→limits.abstract_words /
      figures_tables→limits.figures_tables / abstract_structured→abstract.structured /
      abstract_labels→abstract.labels。name / note / sections は解決対象外 (参照用)。
  (c) article_types はあるが種別未指定 → limits/abstract をそのまま使い警告。
  (d) 存在しない種別 → 即エラーで停止 (綴り違いで上限検証が無効化されるのを防ぐ)。
  (e) article_types を持たない誌に種別指定 → 警告して無視。
  (f) limits.keywords はスカラとリストの両形式を受理する。
      スカラ N は「上限のみ指定」として [1, N] に正規化する (`keywords: 5` とだけ書いた
      プロファイルを、リストの形に書き直さずに使えるようにするため)。

【png_fallback_dpi の一本化】figures.pptx.png_fallback_dpi が null / 未指定なら
figures.dpi の値を写す (同じ値を 2 か所に書かないため。bhi は null 指定で
figures.dpi=300 に一本化)。

診断メッセージはすべて stderr に出す (package.py figure-plan の stdout は機械読取の
TSV であるため。stdout を汚すと package.sh の変換計画が壊れる)。
"""

import copy
import re
import sys
from pathlib import Path

import yaml

JOURNALS_DIR = Path("data/journals")

# ---------------------------------------------------------------------
# スキーマ既定値 (docs/profile-schema.md)。「未指定ならどう動くか」を 1 箇所で定義する。
# 値は呼び出し側 (package.py の resolve_* / figure_label) が前提にしている既定と
# 一致させてある。★ 印のキーの既定はすべて「何もしない」側。
# 体裁キー (line_spacing 等) は python 側の消費者がいないため本辞書に含めない
# (それらの既定は data/journals/make-reference.sh 内の焼き込み時既定が正)。
# ---------------------------------------------------------------------
DEFAULTS = {
    "csl": None,                     # null = _default の CSL を継承
    "reference_doc": None,           # null = _default の reference.docx を継承
    # page_numbers はここに置かない。本辞書の方針は上記コメントどおり
    # 「体裁キーは python 側の消費者がいないため含めない (既定は make-reference.sh 側が正)」
    # であり、page_numbers も体裁キーで python 側に消費者がいない (docs/profile-schema.md の「読み手は
    # make-reference.sh であり build / package の実行時ではない」)。ここにも書くと
    # make-reference.sh の flag() 既定との二重定義になる。
    # ★ 行番号の適用範囲。体裁キーだが**唯一 python 側に消費者がある**
    # (build_docx.py が読む) ので DEFAULTS に置く。reference.docx へ焼き込むのではなく、
    # 焼き込み済みの sectPr から `w:lnNumType` を外す形で効かせるため make-reference.sh は読まない。
    #   all        = 全文書に行番号 (既定。_default はこれ)
    #   manuscript = 本文 (main.md) だけに行番号。cover-letter.md / revise-report.md からは外す
    "line_numbers_scope": "all",
    "article_type": None,            # ★ 既定の記事種別 (無指定なら limits をそのまま使用)
    "article_types": None,           # ★ 記事種別ごとの上限・構成の辞書
    "figures": {
        "embed": True,               # 草稿は docx 埋込 (package.resolve_mode の既定)
        "formats": ["pdf"],          # 最終図の形式 (package.resolve_format の既定)
        "dpi": 300,                  # ラスタ図解像度 (package.resolve_dpi の既定)
        "font_handling": "outline",  # svg→pdf のフォント処理 (package.resolve_font_handling の既定)
        "placement": "inline",       # 注: 現状どのコードも読まない
        # ★ ベクターを載せる容器 (pptx / null)。**どのコードも読まない予約キー**
        # (主形式は figures.formats の先頭が決めるため役目が重複する。formats: [png,...] と
        #  vector_container: pptx を同時に書いても pptx は出ない)。将来「ラスタ主形式だが一部の図
        #  だけベクターで出す」を入れるときのために残す。placement と同じ扱い
        "vector_container": None,
        "pptx": {                    # ★ pptx 経路の設定 (package.resolve_pptx_cfg が読む)
            "mode": "svg-blob",
            "slide_fit": "figure",
            "png_fallback_dpi": None,   # null = figures.dpi を継承 (resolve() が写す)
            "text_to_path": False,      # 既定 false
        },
        "legends_section": None,     # ★ null = 図凡例の集約をしない (値があれば relocate.py が集約する)
        "title_words": None,         # ★ 図の題の語数上限 (検証用)
        "legend_words": None,        # ★ 図凡例の語数上限 (検証用)
        "keys_in_graphic": False,    # ★ 凡例キーを画像内に入れる要件 (注意喚起用)
        "multipanel_single_file": False,  # ★ 多パネル図 1 ファイル合成の要件 (注意喚起用)
    },
    "tables": {                      # ★ ブロックごと新規
        "placement": "inline",       # inline = 末尾移設しない (既定。end なら relocate.py が末尾へ移す)
                                     # end = 本文末尾へ移す / separate = 本文から外し
                                     # 1 表 1 ファイルで出す。解釈は
                                     # relocate.table_placement() (未知の綴りはエラーで停止)
        # ★ 末尾へ移した表の前に置く見出し。null = 見出しを置かず改ページのみ。
        # BHI の規定は原稿本体の構成として "Tables" を列挙するだけで見出しの文言を定めていないため
        # 既定は null にした (規定に無い文字列を提出物へ勝手に足さない)。見出しを要求する誌のための
        # 逃げ道として profile 側で指定できるようにしてある (figures.legends_section と対の関係)。
        "section_title": None,
        "object": None,
        "allow_color": True,         # true = 制限なし
        "thousands_separator": True, # true = 制限なし
        "title_words": None,
        "legend_words": None,
        "separate_file_allowed": True,
    },
    "limits": {
        "word_count": None,
        "abstract_words": None,
        "references": None,
        "figures_tables": None,      # ★
        "title_words": None,         # ★
        "keywords": None,            # スカラ N も可。resolve() が [下限, 上限] に正規化
        "video_mb": None,            # ★
    },
    "blinded": False,
    "abstract": {
        "structured": False,
        "labels": None,              # ★ 構造化抄録の見出しラベル
        "citations_allowed": True,   # ★ true = 制限なし
        "keyword_source": None,      # ★
    },
    "declarations": {                # ★ ブロックごと新規
        "required": None,
        "credit": False,
        "abbreviations_section": False,
    },
    "submission": {                  # ★ ブロックごと新規
        "text_formats": None,
        "table_formats": None,
        "figure_formats": None,      # 定義された場合、代替図形式がここに無ければエラー停止
        "video_formats": None,
        "forms": None,
        "supplementary": None,
    },
    # ★ 執筆 lint (ブロックごと新規)。
    #
    # 【2 層構成】
    # `forbid_chars` の合成文字回避・`units: SI`・記入欄 `<<...>>` の残存・凡例 Div の配置規則は
    # **BHI 固有ではない** — 前 2 つは欧文組版と医学系誌の一般則、後ろ 2 つは本テンプレの記法の
    # 規約である。BHI プロファイルにだけ置くと、同じ原稿を別の誌でパッケージした瞬間に
    # 検査が消え、「本文は雑誌非依存に保つ」原則と矛盾する。そこで**基底 (ここ) に既定値を置き、
    # 雑誌側は上書き・追加のみ**とする。lint ブロックを持たない誌 (_default など) にも
    # 基底の値がそのまま効くが、いずれの検査も**該当する記述が原稿に無ければ沈黙する**ので
    # ダミー原稿の出力は変わらない。
    # 逆に `device_notation` と `corresponding_author` は誌ごとに温度差があるため既定は無効に
    # しておき、要求する誌 (BHI) がプロファイルで有効にする。
    "lint": {
        # 合成 1 文字は「度記号 + C」等に分解して書く (BHI Units 節 4。他誌でも組版事故のもと)
        "forbid_chars": ["℃", "℉", "㎎", "㎏", "㎜", "㎝", "㎡", "㎥", "㎕", "㎖", "㎗"],
        "units": "SI",               # 非 SI 単位らしき語の狭い検出 (参考情報)
        "device_notation": False,    # 統計ソフトのバージョン・製造元の記載 (誌ごと)
        "placeholder_markers": True, # 骨格の記入欄 `<<...>>` の残存 (テンプレ共通の規約)
        "legend_placement": True,    # 凡例 Div の配置規則と中身 (テンプレ共通の記法)
        "corresponding_author": False,  # 連絡著者ブロックの検査 (誌ごと)
        # ref.bib の langid が japanese 以外なら要修正 (誌ごと)。langid があるだけで
        # "(in Japanese)" を付ける引用様式 (bhi.csl) を使う誌で true にする
        "langid_japanese_only": False,
    },
    "numbering": {
        "figure": "Figure %d.",      # package.figure_label の既定
        "table": "Table %d.",
    },
}

# (b) 記事種別 → profile 本体へのキー写像 (深さ 1 の部分マージ)
_TYPE_KEYMAP = {
    "word_count": ("limits", "word_count"),
    "abstract_words": ("limits", "abstract_words"),
    "figures_tables": ("limits", "figures_tables"),
    "abstract_structured": ("abstract", "structured"),
    "abstract_labels": ("abstract", "labels"),
}
# name / note / sections は解決対象外 (参照用。sections は一次資料 "Main Text" 欄の転記で
# あり実節順の検査に使わない)


def _warn(msg):
    print(f"  [journal_profile] {msg}", file=sys.stderr)


def _section(prof, name):
    """prof[name] を必ず dict として返す (無い / null なら空 dict を入れてから返す)。

    profile.yaml で `limits:` のようにブロック名だけ書いて中身を
    省くと値が None になり、_deep_merge は None で既定の dict を上書きする。そのとき
    `prof.setdefault(sect, {})[dst_key] = ...` と書くと、キーが存在して値が None なので
    setdefault が None を返し `TypeError: 'NoneType' object does not support item
    assignment` で異常終了する (新規誌を起こすときの落とし穴)。
    """
    if not isinstance(prof.get(name), dict):
        prof[name] = {}
    return prof[name]


_MISSING = object()


def _merge_forbid_lists(prof, raw_profile):
    """lint の **禁止集合** (`forbid_*` の list) を「基底 ∪ 誌」で解決する。

    `_deep_merge` は list をまるごと置換するので、誌のプロファイルが `lint.forbid_chars` を
    書くと**基底の検査を弱められる** (誌が基底より少ない文字を書くと、規定を持つその誌でだけ
    残りの文字が素通りする。値をそろえても、同じ形の事故はキーが増えるたびに再発しうる)。
    lint の 2 層構成は「基底に既定・誌は**上書きと追加**」(DEFAULTS["lint"] の説明) なので、
    禁止集合については加算で解決するのが趣旨に合う。

    **`forbid_` で始まる list のキーだけ**を対象にする。lint 以外のブロック
    (`figures.formats` / `abstract.labels` / `submission.*_formats` 等) は「誌の値で
    置き換える」が正しい意味なので触らない。同じ理由で、将来 lint に許可リスト
    (`allow_*`) を足すときもここへ入れてはならない — 和集合は許可を広げる側に効き、
    誌が範囲を狭められなくなる。

    **無効化したい誌は `null` を書く** (`forbid_chars: null` → 検査そのものが沈黙する)。
    空リストではなく null を要求するのは、意思表示を明示させるためである。

    **`null` を受け取ったら警告を 1 行出す**。YAML では
    `forbid_chars:` と書いて値を省略した場合も `null` になるため、**書き忘れと明示的な無効化を
    区別できない**。値を書きかけて保存した・一覧を別の場所へ移そうとして中身だけ切り取った、
    といった編集の途中状態が、黙っていればそのまま**検査の無効化**として通る (上で塞いだ
    「誌が基底の検査を弱められる」経路が、置き換えから書き忘れに移るだけになる)。
    明示的な無効化なら警告は正しい情報であり、書き忘れなら気づける。

    **基底に存在しない `lint` キーにも警告を出す**。`lint.forbid_char`
    のように綴りを間違えると、基底に同名キーが無いので本関数は触らず、意図した文字が
    黙って効かない (検査は基底のまま残るので弱まりはしないが、書いた側は気づけない)。
    """
    raw_lint = raw_profile.get("lint") if isinstance(raw_profile.get("lint"), dict) else {}
    out = _section(prof, "lint")
    for key, base_val in DEFAULTS["lint"].items():
        if not (key.startswith("forbid_") and isinstance(base_val, list)):
            continue
        own = raw_lint.get(key, _MISSING)
        if own is _MISSING:
            continue                       # 未指定 = 基底のまま
        if own is None:
            # null は「明示的な無効化」だが YAML の値書き忘れと同じ形になる
            _warn(f"lint.{key} が null のため、この検査を行いません "
                  f"(無効化の意思表示なら正しい動作です。値の書き忘れなら基底の "
                  f"{len(base_val)} 件が効かなくなっています)")
            continue
        if isinstance(own, list):
            merged = list(base_val)
            merged += [v for v in own if v not in merged]
            out[key] = merged
    # 綴り違いのキーは黙って無視されるので名指しで知らせる
    for key in raw_lint:
        if key not in DEFAULTS["lint"]:
            _warn(f"lint.{key} は既知の検査ではありません (綴り違いの可能性)。"
                  f"この指定は無視されます")


def _deep_merge(base, override):
    """dict を再帰マージした新しい dict を返す (override 優先。list はまるごと置換)。

    例外は lint の禁止集合 (`forbid_*`) で、resolve() が `_merge_forbid_lists` で
    「基底 ∪ 誌」に解き直す。理由は同関数の説明を参照。
    """
    out = copy.deepcopy(base)
    for k, v in (override or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


def load(journal_id, journals_dir=None):
    """data/journals/<id>/profile.yaml を読んで生 dict を返す。無ければ空 dict (警告)。"""
    path = (journals_dir or JOURNALS_DIR) / journal_id / "profile.yaml"
    if not path.is_file():
        _warn(f"{path} が無いため _default 既定を使います")
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def resolve(profile, article_type=None):
    """スキーマ既定値を敷き、記事種別で limits / abstract を解決した profile を返す。

    冪等: 解決済み profile (_resolved マーカー付き) を同じ種別 (または種別無指定) で
    再度渡された場合はそのまま返す (package.py → validate.py の受け渡しで二重解決と
    警告の重複を防ぐ)。

    判定は `article_type in (None, profile["article_type"])` だけでは足りない。
    article_types を持たない誌では解決後も article_type が None のままなので、
    同じ種別を渡し直した package.py → validate.py の 2 回目で素通りせず再解決し、規則 (e) の
    警告が二重に出る (実測)。そこで要求された種別そのものを `_resolved_for` に控えて判定に
    加える。別の種別を渡し直したときは解き直す。
    """
    profile = profile or {}
    if profile.get("_resolved") and article_type in (
            None, profile.get("_resolved_for"), profile.get("article_type")):
        return profile

    prof = _deep_merge(DEFAULTS, profile)
    # 禁止集合だけは list 置換ではなく「基底 ∪ 誌」にする
    _merge_forbid_lists(prof, profile)

    # **その誌が自分で宣言した lint キー**を控える。lint の 2 層構成
    # (基底に既定・誌は上書き) では、解決後の profile を見ても値の出所が分からない。
    # 出所が分からないと、規定を調べていない誌の指摘まで「規定違反の可能性」として出すことに
    # なる (合成文字・記入欄・凡例の配置は基底では欧文組版とテンプレの記法の規約に過ぎない)。
    # validate.py が指摘の文末に出所を添えるために使う。
    # 既に控えられていれば上書きしない — 解決済み profile を別の記事種別で渡し直したとき、
    # 解決後の全キー (= 基底由来を含む) で塗り潰さないため。
    if "_lint_declared" not in prof:
        raw_lint = profile.get("lint")
        prof["_lint_declared"] = sorted(raw_lint) if isinstance(raw_lint, dict) else []

    types = prof.get("article_types")

    if types:
        atype = article_type or prof.get("article_type")
        if atype is None:
            # (c) 種別未指定: limits / abstract をそのまま使う
            _warn("既定の記事種別が未指定です (article_type / --article-type)。"
                  "limits / abstract をそのまま使います")
        elif atype not in types:
            # (d) 未知の種別は即エラー (黙って素通しすると上限検証が無効化されたまま投稿されうる)
            sys.exit(f"エラー: 記事種別 '{atype}' は article_types に存在しません "
                     f"(有効: {', '.join(sorted(types))})")
        else:
            spec = types[atype] or {}
            for src_key, (sect, dst_key) in _TYPE_KEYMAP.items():
                if src_key in spec:  # (a) 深さ 1 の部分マージ (null も明示値として写す)
                    _section(prof, sect)[dst_key] = copy.deepcopy(spec[src_key])
            if spec.get("abstract_structured") is False:
                # (a) 非構造化の種別ではラベルを明示的に空にする (前種別のラベル残留を防ぐ)
                _section(prof, "abstract")["labels"] = []
            prof["article_type"] = atype
    elif article_type:
        # (e) article_types を持たない誌への種別指定は警告して無視
        _warn(f"この雑誌プロファイルは article_types を持たないため "
              f"--article-type '{article_type}' を無視します")

    # (f) limits.keywords の正規化: スカラ N → [1, N]
    kw = (prof.get("limits") or {}).get("keywords")
    if isinstance(kw, (int, float)) and not isinstance(kw, bool):
        _section(prof, "limits")["keywords"] = [1, int(kw)]

    # png_fallback_dpi の一本化: null なら figures.dpi を写す。
    # figures が null でも _section() で prof に dict を入れてから書く (局所変数に書くと捨てられる)
    figures = _section(prof, "figures")
    if not isinstance(figures.get("pptx"), dict):
        figures["pptx"] = {}
    pptx = figures["pptx"]
    if pptx.get("png_fallback_dpi") is None:
        pptx["png_fallback_dpi"] = figures.get("dpi", DEFAULTS["figures"]["dpi"])

    prof["_resolved"] = True
    prof["_resolved_for"] = article_type   # 冪等ガードの判定に使う
    return prof


def load_resolved(journal_id, article_type=None, journals_dir=None):
    """load() → resolve() の一括呼び出し (build_docx.py / package.py / validate.py が使う)。"""
    return resolve(load(journal_id, journals_dir=journals_dir), article_type)


# ---------------------------------------------------------------------
# 体裁キーの値の解釈と、reference.docx との突合
#
# 体裁は profile.yaml (意図) と reference.docx (実体) の二重管理になる。値の解釈を
# data/journals/make-reference.sh (焼き込み側) と build / validate (検査側) が別々に持つと、
# それ自体が「既定値の二重定義」を作ることになるため、
# 解釈は本モジュールに 1 つだけ置き、make-reference.sh からも import して使う。
# ---------------------------------------------------------------------

LAYOUT_KEYS = ("line_spacing", "line_numbers", "page_numbers", "font", "font_size",
               "margins", "paper_size")
TRUE_WORDS = {"true", "yes", "on", "y", "1"}
FALSE_WORDS = {"false", "no", "off", "n", "0"}


def as_flag(v, key="(キー名不明)", default=False):
    """真偽値キーを解釈する。認識できない値は default に落としたうえで警告する。

    落ち先が「機能を無効にする」なので、page_numbers: enabled のような
    1 語の誤記でページ番号が静かに落ち、BHI では規定違反の docx がそのまま提出物になる。
    y / n も真偽語として受ける (YAML 1.1 は y 単独を真偽値に解決しないため文字列で届く)。
    """
    if v is None:
        return default
    if isinstance(v, bool):
        return v
    word = str(v).strip().lower()
    if word in TRUE_WORDS:
        return True
    if word in FALSE_WORDS:
        return False
    _warn(f"{key}: {v!r} は真偽値として解釈できないため {default} として扱います "
          f"(真: {'/'.join(sorted(TRUE_WORDS))} / 偽: {'/'.join(sorted(FALSE_WORDS))})")
    return default


def as_choice(v, allowed, default):
    """列挙キーを解釈する (候補外・未指定は default)。make-reference.sh の choice() と同一。"""
    word = (str(v).strip().lower() if v is not None else "")
    return word if word in allowed else default


def as_number(v, default):
    """`12pt` / `25mm` のような単位つきの値から数値部分を取り出す (未指定は default)。"""
    if v is None:
        return default
    m = re.search(r"[-+]?[0-9]*\.?[0-9]+", str(v))
    return m.group(0) if m else default


def layout_mismatches(profile, reference_docx):
    """profile.yaml の体裁と reference.docx に焼き込まれた実体裁の食い違いを返す。

    戻り値は [(キー, profile の値, reference.docx の実値)]。体裁は
    reference.docx 側に焼き込む設計なので、profile.yaml を編集して make-reference.sh の
    再実行を忘れると古い体裁のまま投稿まで進む (BHI は行間・行番号・ページ番号がいずれも
    規定必須なので規定違反に直結する)。実体側を読んで機械的に突き合わせる。

    数値は丸め差を許容する (font_size は 0.1pt、margins は 0.05mm。0.5mm だと 25mm と 25.4mm を見分けられない)。reference.docx から
    読み取れなかったキーは判定しない (欠落を不一致と報告しない)。
    """
    import patch_reference_docx  # 遅延 import (lxml を要するのはこの経路だけ)

    try:
        actual = patch_reference_docx.read_layout(reference_docx)
    except Exception as exc:                                    # noqa: BLE001
        _warn(f"{reference_docx} の体裁を読めませんでした ({exc})。突合を省略します")
        return []

    tol = {"font_size": 0.1, "margins": 0.05}   # 余白は twip の丸め (0.02mm 未満) だけを許す
    out = []
    for key in LAYOUT_KEYS:
        want, got = profile.get(key), actual.get(key)
        if got is None:
            continue
        if key == "page_numbers":
            if as_flag(want, key) != bool(got):
                out.append((key, as_flag(want, key), bool(got)))
        elif key in tol:
            w_num = as_number(want, None)
            if w_num is not None and abs(float(w_num) - float(got)) > tol[key]:
                out.append((key, want, round(float(got), 2)))
        else:
            if want is not None and str(want).strip().lower() != str(got).strip().lower():
                out.append((key, want, got))
    return out
