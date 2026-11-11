# profile.yaml のキー (profile-schema.md)

雑誌プロファイル `data/journals/<id>/profile.yaml` のキーの一覧。省略したときの動きと、どのモジュールが読むかを書く。
雑誌を足す手順は [`docs/usage-guide.md`](usage-guide.md) の §4、プロファイルが処理のどこで効くかは
[`docs/architecture.md`](architecture.md) にある。例は同梱の 2 誌 (`data/journals/_default/profile.yaml` と
`data/journals/bhi/profile.yaml`) から採った。

---

## 1. 読み方の約束

- **プロファイルは基底の既定値の上に重ねて読む**。既定値は `main/00_setup/lib/journal_profile.py` の `DEFAULTS` の 1 か所にあり、
  `load_resolved()` が「既定値 → `profile.yaml` → 記事種別」の順に重ねる (辞書は再帰的に重ね、リストはまるごと置き換える。
  例外は §5 の lint の禁止集合)。build (`build_docx.py`)・差分 (`diff_docx.py`)・パッケージ (`package.py`)・規定チェック
  (`validate.py`) はすべてこの解決済みのプロファイルを使う。
- **キーはすべて省略できる**。省略したときは「何もしない」側か、汎用の投稿フォーマットの値になる。新しいキーを足すときも
  この約束を守る (既存の誌の出力を変えないため)。
- **★ 印** — 同梱の `bhi/profile.yaml` と `journal_profile.py` のコメントにある ★ は、**誌固有の要件のために足した拡張キー**の
  目印である。汎用の投稿フォーマット (`_default`) は使わず、既定値はどれも「何もしない」側 (検査しない・組み替えない・制限しない)
  になっている。つまり ★ のキーを書かない誌の出力は、そのキーが無かったときと変わらない。下の表では「拡張」の列に ★ を付けた。
- `bhi/profile.yaml` のコメントの「確度高 / 確度中」は、その値の根拠の確かさ (規定の文面どおりか、設計上の判断か) の覚え書きで、
  プログラムは読まない。
- **体裁キー** (`line_spacing` など §3.2) は `reference.docx` に焼き込む値で、読むのは `data/journals/make-reference.sh` だけ
  (build の実行時には読まない)。体裁を変えたら `bash data/journals/make-reference.sh <id>` を回し直す。忘れると build と
  規定チェックが、焼き込み済みの体裁と `profile.yaml` の食い違いを警告する。体裁キーの既定値は `make-reference.sh` の側にあり、
  `DEFAULTS` には置かない (同じ既定を 2 か所に書かないため)。
- 診断はすべて標準エラーに出る (`package.py figure-plan` の標準出力は機械が読む TSV のため)。

---

## 2. ファイルの構成

```
data/journals/<id>/
├── profile.yaml       # このファイル
├── <id>.csl           # 引用様式 (csl: で指す。無ければ _default.csl を継承)
├── reference.docx     # 体裁を焼き込んだ Word のテンプレート (reference_doc: で指す。生成物)
└── skeleton/          # (任意) 原稿骨格。ビルドの対象ではなく、写して書き始める雛形
```

---

## 3. キー一覧

「読み手」はそのキーを読むモジュール (`main/` の下のファイル名)。`make-reference.sh` は `data/journals/make-reference.sh`。

### 3.1 基本

| キー | 拡張 | 既定 | 例 | 説明 | 読み手 |
|------|------|------|-----|------|--------|
| `name` | | — | `"BioHealth Informatics"` | 表示名。`SUBMISSION.md` の見出しに出る | `package.py` |
| `publisher` | ★ | — | `"Japan Association for Medical Informatics"` | 発行者 (記録用) | (なし) |
| `submission_system` | ★ | — | `"https://mc.manuscriptcentral.com/bhi"` | 投稿系の URL。`SUBMISSION.md` に出る | `package.py` |
| `csl` | | `null` | `bhi.csl` | 引用様式 (このディレクトリからの相対パス)。`null` か、指すファイルが無ければ `_default.csl` (AMA 11th) を継承し、**build / diff が毎回その旨を警告する** (規定と違う引用様式のまま提出しないため) | `build_docx.py` / `diff_docx.py` |
| `reference_doc` | | `null` | `reference.docx` | Word のテンプレート。`null` か、指すファイルが無ければ `_default` のものを継承し、継承した体裁と `profile.yaml` の体裁キーの食い違いを警告する。`reference.docx` を指していてファイルが無ければ、build / diff が `make-reference.sh` で作る。別の名前 (雑誌が配るテンプレート) は作らない | `build_docx.py` / `diff_docx.py` / `validate.py` / `scripts/lib/ensure-reference.sh` |

### 3.2 体裁 (reference.docx に焼き込む)

| キー | 拡張 | 既定 (`make-reference.sh`) | 例 | 説明 | 読み手 |
|------|------|------|-----|------|--------|
| `line_spacing` | | `double` | `double` | 行間 (`single` / `1.5` / `double`) | `make-reference.sh` |
| `line_numbers` | | `continuous` | `continuous` | 行番号 (`none` / `continuous` / `per-page`)。1 行目を 1 から数える | `make-reference.sh` |
| `page_numbers` | ★ | `false` | `true` | フッタの中央にページ番号 (`PAGE` フィールド)。`false` ならフッタの部品を作らない | `make-reference.sh` |
| `font` | | `"Times New Roman"` | `"Times New Roman"` | 本文のフォント | `make-reference.sh` |
| `font_size` | | `12` | `12pt` | 本文の文字の大きさ | `make-reference.sh` |
| `margins` | | `25` | `25mm` | 余白 (四辺一律の代表値として焼き込む) | `make-reference.sh` |
| `paper_size` | | `a4` | `a4` | 用紙 (`a4` / `letter`) | `make-reference.sh` |
| `text_styles.uniform_size` | ★ | `false` | `true` | `true` なら級数を持つ段落・文字スタイル (題・副題・著者・日付・抄録・見出し 1〜3 など) をすべて本文の級数 (`font_size`) にそろえ、見出しの階層を強調で付ける (題・見出し 1 = 太字 / 見出し 2 = 太字斜体 / 見出し 3 = 斜体)。題を継ぐ著者・日付・副題には、継いだ強調を打ち消す | `make-reference.sh` |
| `text_styles.heading_color` | ★ | `keep` | `black` | `black` なら題・見出しのテーマ色 (pandoc の既定は青) を外して自動色にする | `make-reference.sh` |
| `text_styles.uniform_line_spacing` | ★ | `false` | `true` | `true` なら段落スタイルが個別に持つ行送りを外し、文書全体の行送り (`line_spacing`) にそろえる (段落の前後の空きは残す)。題 (`Title`) の行送りは、このキーが無くても本文の行送りに直す | `make-reference.sh` |
| `line_numbers_scope` | ★ | `all` | `manuscript` | 行番号を付ける文書。`all` = すべて / `manuscript` = `main.md` だけ (cover-letter / revise-report の docx から行番号を外す)。**体裁キーで唯一 build が読む** (焼き込んだ節設定から外す形で効かせるので、`make-reference.sh` の再実行は要らない) | `build_docx.py` |

食い違いの検算 (build と規定チェック) は `line_spacing` / `line_numbers` / `page_numbers` / `font` / `font_size` /
`margins` / `paper_size` を焼き込み済みの `reference.docx` と比べる (`text_styles.*` は比べないので、変えたら
`make-reference.sh` を回し直すのを忘れないこと)。

### 3.3 図 (`figures`)

| キー | 拡張 | 既定 | 例 | 説明 | 読み手 |
|------|------|------|-----|------|--------|
| `figures.embed` | | `true` | `true` | `package.sh` の既定のモード。`true` → 草稿 (図を埋め込む) / `false` → 最終 (図を分離)。`--mode` で上書き | `package.py` |
| `figures.formats` | | `[pdf]` | `[pptx, png, tif]` | 最終提出の図の形式。**先頭が主形式**。作れるのは `pdf` / `png` / `pptx`。`eps` → pdf / `tiff` (`tif`) → png は警告つきで代わりに作り、作れない形式は止まる。`--format` で上書き | `package.py` |
| `figures.dpi` | | `300` | `300` | ラスタ図と PNG フォールバックの解像度。`--dpi` で上書き | `package.py` / `check_dpi.py` |
| `figures.font_handling` | | `outline` | `embed` | PDF 図の文字 (`outline` = アウトライン化 / `embed` = 埋め込み)。pptx の経路では PNG フォールバックの生成にだけ効く | `package.py` |
| `figures.pptx.mode` | ★ | `svg-blob` | `svg-blob` | pptx の作り方。`svg-blob` = 案 B (SVG を埋め込んで生成。図の隣に同名の `.pptx` があれば案 A) / `passthrough` = 案 A (執筆者の pptx を無変換でコピー) / `native-shapes` = 案 B′ (作っていない。指定すると止まる)。呼び名は `docs/architecture.md` §2.5。綴りの誤りも止まる | `package.py` |
| `figures.pptx.slide_fit` | ★ | `figure` | `figure` | スライドの寸法。`figure` = 図の公称サイズ (1 inch 未満の軸は広げて中央に置き、56 inch 超は止まる) / `fixed` = 既定の寸法に縮めて置く。`--slide-fit` で上書き | `package.py` |
| `figures.pptx.png_fallback_dpi` | ★ | `null` | `null` | pptx に同梱する PNG の解像度。`null` なら `figures.dpi` を写す (同じ値を 2 か所に書かないため) | `package.py` / `journal_profile.py` |
| `figures.pptx.text_to_path` | ★ | `false` | `false` | 埋め込む SVG の文字をアウトライン化するか (`true` なら svg-conversion を使う)。既定は `false` — 組版で組み直す誌では文字を図形にすると直せなくなるため | `package.py` |
| `figures.legends_section` | ★ | `null` | `"Figure Legends"` | 最終モードで図の題 + 凡例を References の後へ集めるときの見出し。`null` なら集めない | `relocate.py` / `package.py` / `validate.py` |
| `figures.title_words` | ★ | `null` | `15` | 図の題の語数の上限 (キャプションだけを数え、`Figure 1: ` は含めない) | `validate.py` |
| `figures.legend_words` | ★ | `null` | `300` | 図の凡例 (直後の `Legend` Div) の語数の上限 | `validate.py` |
| `figures.keys_in_graphic` | ★ | `false` | `true` | 凡例のキーを画像の中に入れる要件 (記録用。画像の中身は判定できないので検査しない) | (なし) |
| `figures.multipanel_single_file` | ★ | `false` | `true` | 多パネル図を 1 ファイルに合成する要件 (記録用。同上) | (なし) |
| `figures.vector_container` | ★ | `null` | `pptx` | ベクターを載せる容器 (予約キー。主形式は `figures.formats` の先頭が決めるので、今は読まない) | (なし) |
| `figures.placement` | | `inline` | `end` | 図表の置き場所 (予約キー。**読まない**。組み替えの発火には `figures.legends_section` と `tables.placement` を使う) | (なし) |

### 3.4 表 (`tables`)

| キー | 拡張 | 既定 | 例 | 説明 | 読み手 |
|------|------|------|-----|------|--------|
| `tables.placement` | ★ | `inline` | `separate` | 最終モードでの表 (題 + 表 + 直後の `Legend` 段落) の置き場所。`end` なら文書の末尾へ移し、`separate` なら本文から外して `tables/TableN.docx` に 1 表 1 ファイルで出す (本文はテキストだけになる)。どちらも元の位置に `[Table N about here]` を残す。`inline` / `end` / `separate` 以外の綴りは止める | `relocate.py` / `package.py` / `validate.py` |
| `tables.section_title` | ★ | `null` | `null` | `end` で末尾へ移した表の前に置く見出し。`null` なら見出しを置かず改ページだけ (規定に無い文字列を提出物に足さない) | `relocate.py` |
| `tables.allow_color` | ★ | `true` | `false` | `false` なら表の網掛け・文字色・蛍光ペン・罫線の色を警告する (草稿モードでも) | `relocate.py` |
| `tables.thousands_separator` | ★ | `true` | `false` | `false` なら `1,234` の形の数値を指摘する (本文と表の両方。URL・References・コードは除く) | `validate.py` |
| `tables.title_words` | ★ | `null` | `15` | 表の題 (キャプション) の語数の上限 | `validate.py` |
| `tables.legend_words` | ★ | `null` | `300` | 表の凡例の語数の上限 | `validate.py` |
| `tables.object` | ★ | `null` | `word` | 表の作り方の要件 (`word` = Word の表で作る)。`SUBMISSION.md` の注記に出る | `package.py` |
| `tables.separate_file_allowed` | ★ | `true` | `true` | 表を別ファイルで出してよいか。`SUBMISSION.md` の注記に出る | `package.py` |

### 3.5 上限 (`limits`)

| キー | 拡張 | 既定 | 例 | 説明 | 読み手 |
|------|------|------|-----|------|--------|
| `limits.word_count` | | `null` | `4000` | 本文語数の上限 (数え方は `docs/architecture.md` §2.5 の「規定チェック」) | `validate.py` |
| `limits.abstract_words` | | `null` | `250` / `300` | 抄録の語数の上限 | `validate.py` |
| `limits.references` | | `null` | `null` | 文献数の上限 | `validate.py` |
| `limits.figures_tables` | ★ | `null` | `8` | 図表の合計点数の上限。本文の流れの上にある図と表を数える (番号の無い装飾画像も数える。`.grid` の中は数え、`.textbox` の中は数えない)。値があると、数えなかった `.textbox` の中の図表を要修正にする | `validate.py` |
| `limits.title_words` | ★ | `null` | `30` | タイトルの語数の上限。あわせてタイトルの全大文字の語 (略語らしい語) を参考情報に挙げる | `validate.py` |
| `limits.keywords` | | `null` | `[3, 5]` | キーワードの数。`[下限, 上限]`、またはスカラ `N` (= 上限だけ。`[1, N]` と読む) | `validate.py` |
| `limits.video_mb` | ★ | `null` | `50` | 補足資料の動画 1 ファイルの上限 (MB。10 進) | `package.py` |

### 3.6 抄録・匿名化・番号 (`abstract` / `blinded` / `numbering`)

| キー | 拡張 | 既定 | 例 | 説明 | 読み手 |
|------|------|------|-----|------|--------|
| `abstract.structured` | | `false` | `false` | 構造化抄録か | `validate.py` |
| `abstract.labels` | ★ | `null` | `[Objective, Methods, Results, Conclusion]` | 構造化抄録の見出し。書いた誌では全ラベルの有無を 1 つずつ確かめ、欠けたものを名指しする。書かない誌は既定の 4 ラベル (Background / Methods / Results / Conclusions) のどれか 1 つで合格 | `validate.py` |
| `abstract.citations_allowed` | ★ | `true` | `false` | `false` なら抄録の中の文献引用 (`@key`) を指摘する | `validate.py` |
| `abstract.keyword_source` | ★ | `null` | `MeSH` | キーワードの語彙 (記録用。シソーラスを同梱しないので検査しない。数は `limits.keywords` が見る) | (なし) |
| `blinded` | | `false` | `false` | 匿名版を求める誌か。`true` なら `package.sh` が「伏せる作業は手で」と注意を出す (自動の匿名化は無い) | `package.py` |
| `numbering.figure` | | `"Figure %d."` | `"Figure %d."` | 図の番号の書式。分離した図のファイル名に使う (`"Figure %d."` → `Figure1.pptx` / `"Fig. %d"` → `Fig1.pdf`) | `package.py` |
| `numbering.table` | | `"Table %d."` | `"Table %d."` | 表の番号の書式 (記録用。本文の表の番号は pandoc-crossref の設定 `main/00_setup/defaults.yaml` が決める) | (なし) |

### 3.7 記事種別 (`article_type` / `article_types`)

| キー | 拡張 | 既定 | 例 | 説明 | 読み手 |
|------|------|------|-----|------|--------|
| `article_type` | ★ | `null` | `original` | 既定の記事種別。`--article-type` で上書き | `journal_profile.py` |
| `article_types.<id>` | ★ | `null` | (下) | 種別ごとの上限と構成。解決のときに `limits` / `abstract` に重ねる (§4) | `journal_profile.py` |

`article_types.<id>` の中のキー:

| キー | 重ねる先 | 例 (`bhi` の `original`) |
|------|---------|------------------------|
| `word_count` | `limits.word_count` | `4000` |
| `abstract_words` | `limits.abstract_words` | `300` |
| `figures_tables` | `limits.figures_tables` | `8` |
| `abstract_structured` | `abstract.structured` | `true` |
| `abstract_labels` | `abstract.labels` | `[Objective, Methods, Results, Conclusion]` |
| `name` | (参照用) | `"Original Article"` (`SUBMISSION.md` に出る) |
| `sections` | (参照用) | 規定の本文の構成の写し。節の順の検査には使わない |
| `note` | (参照用) | 種別ごとの補足 |

### 3.8 Declarations (`declarations`)

| キー | 拡張 | 既定 | 例 | 説明 | 読み手 |
|------|------|------|-----|------|--------|
| `declarations.required` | ★ | `null` | `["Funding", "Authors' contributions", …]` | 必須の Declarations の項目名。`# Declarations` から次の同じレベル以上の見出しまでを範囲にし、項目名と見出しを正規化 (小文字化・空白の畳み込み・アポストロフィの統一) して突き合わせる | `validate.py` |
| `declarations.abbreviations_section` | ★ | `false` | `true` | Abstract と Introduction の間に略語の一覧を置く誌か。`true` なら `# Abbreviations` 節を本文語数から除き、位置を確かめる (節が無いことは参考情報にとどめる) | `validate.py` |
| `declarations.credit` | ★ | `false` | `true` | 著者の貢献を CRediT で書く誌か (記録用) | (なし) |

### 3.9 提出物 (`submission`)

| キー | 拡張 | 既定 | 例 | 説明 | 読み手 |
|------|------|------|-----|------|--------|
| `submission.text_formats` | ★ | `null` | `[docx]` | 本文の受入形式。**これがある誌にだけ `SUBMISSION.md` を出す** | `package.py` |
| `submission.table_formats` | ★ | `null` | `[docx, xlsx, pptx]` | 表の受入形式 (`SUBMISSION.md` の注記) | `package.py` |
| `submission.figure_formats` | ★ | `null` | `[jpeg, tif, png, pptx]` | 図の受入形式。書いた誌では、実際に作る形式をこれと照合し、外れたら止める (代わりの形式なら止め、明示した形式なら `--allow-disallowed-format` を求める)。受入形式の記録なので、ここにあっても作れるとは限らない (`jpeg` は作らない) | `package.py` |
| `submission.video_formats` | ★ | `null` | `[mp4]` | 動画の受入形式 (動画の分類は拡張子で行い、これは照合にだけ使う) | `package.py` |
| `submission.forms` | ★ | `null` | `["COI Disclosure Form (1 通。…)", "License to Publish (1 通。…)"]` | 別に出すフォーム。文字列のまま `SUBMISSION.md` のチェック欄になるので、通数と記入者は注記として書く | `package.py` |
| `submission.supplementary` | ★ | `null` | `as-is` | 補足資料の扱い。`as-is` なら「受理後は変更できない」旨を注意に出す (複製はどの誌でも無変換) | `package.py` |

### 3.10 執筆の検査 (`lint`)

既定値は基底 (`DEFAULTS`) に置いてあり、`lint` を書かない誌にも効く (§5)。

| キー | 拡張 | 既定 (基底) | 例 (`bhi`) | 説明 | 読み手 |
|------|------|------------|-----------|------|--------|
| `lint.forbid_chars` | ★ | `["℃", "℉", "㎎", "㎏", "㎜", "㎝", "㎡", "㎥", "㎕", "㎖", "㎗"]` | 同じ | 使ってはいけない合成済みの 1 文字。行番号つきで指摘し、`°C` などの書き方を案内する。**誌の値は基底に足される** (§5) | `validate.py` |
| `lint.units` | ★ | `SI` | `SI` | 英米の慣用単位 (`°F` / Fahrenheit / inch / lb / pound / ounce / mile / gallon。大文字と小文字を区別する) を拾って参考情報に出す (SI に従っていることの証明ではない) | `validate.py` |
| `lint.placeholder_markers` | ★ | `true` | (基底のまま) | 骨格の記入欄 `<<...>>` の残り (`main.md` / `cover-letter.md` / `revise-report.md`) | `validate.py` |
| `lint.legend_placement` | ★ | `true` | (基底のまま) | 凡例 Div の配置 (直前が図表か・`for` が実在し直前の図表と一致するか・`for` の欠落) と、中身が段落だけか | `validate.py` |
| `lint.device_notation` | ★ | `false` | `true` | 統計ソフト (綴りの決まった 11 種) に版と括弧内の製造元があるか (機器一般は文面から判定できないので見ない) | `validate.py` |
| `lint.corresponding_author` | ★ | `false` | `true` | `custom-style="Corresponding"` Div が 1 つで、住所・電話・E-mail を備えているか | `validate.py` |
| `lint.langid_japanese_only` | ★ | `false` | `true` | `ref.bib` に `langid` が japanese 以外の文献が無いか (`langid` があるだけで言語によらず `(in Japanese)` を付ける引用様式 = `bhi.csl` を使う誌で有効にする) | `validate.py` |

---

## 4. 記事種別の解決

- **優先順**: `--article-type` > `profile.article_type` > (どちらも無い) `limits` / `abstract` をそのまま使う。
- **(a) 重ね方は深さ 1 の部分的な上書き** (まるごと置き換えない)。まるごと置き換えると、誌全体の規定
  (`abstract.citations_allowed` など) まで消えるため。ただし `abstract_structured: false` の種別では `abstract.labels` を空にする
  (前の種別のラベルが残らないように)。
- **(b) 重ねる先**は §3.7 の表のとおり。`name` / `note` / `sections` は解決に使わない。
- **(c)** `article_types` はあるが種別の指定が無い → `limits` / `abstract` をそのまま使い、警告する。
- **(d)** 存在しない種別を指定 → **有効な一覧を出して止まる** (綴りの誤りで上限の検査が黙って外れないように)。
- **(e)** `article_types` を持たない誌に `--article-type` を渡す → 警告して無視する。
- **(f)** `limits.keywords` はスカラ `N` を `[1, N]` に直す。
- 解決は冪等 (解決済みのプロファイルを渡しても二重に重ねない)。build と差分は種別で出力を変えないが、未知の種別を早く止めるために
  `--article-type` を受け付ける。

---

## 5. lint の 2 層構成

- 合成済みの文字を避けること (`forbid_chars`) と SI 単位 (`units`) は欧文の組版と医学系の誌の一般則で、記入欄
  (`placeholder_markers`) と凡例の配置 (`legend_placement`) は本テンプレートの記法の規約である。特定の誌のプロファイルにだけ
  置くと、同じ原稿を別の誌でパッケージしたとたんに検査が消え、「原稿は雑誌に依存させない」という原則と食い違う。
  そこで**既定値を基底 (`DEFAULTS`) に置き、誌の側は上書きと追加だけ**にした。誌ごとに要否が分かれる `device_notation` と
  `corresponding_author` は基底で無効にしてある。
- **基底から来た指摘には出所を添える**。その誌の `profile.yaml` が自分で書いていない `lint` のキーから出た指摘には、文末に
  **`(本テンプレ共通の作法)`** が付く (その誌の規定を調べた結果ではないため)。
- **禁止集合 (`forbid_` で始まるリストのキー) は「基底 ∪ 誌」で解決する**。リストをまるごと置き換えると、誌が基底より少ない
  文字を書いたときに、規定を持つその誌でだけ残りの文字が素通りするため。一覧を狭めたい誌は `forbid_chars: null` と書いて
  **検査そのものを無効にする** (意思表示をはっきりさせる)。`null` を見ると警告を 1 行出す (YAML では値を書き忘れても `null` に
  なり、区別できないため)。基底に無い `lint` のキー (`lint.forbid_char` のような綴りの誤り) にも警告を出す。
- **この規則を lint の外へ広げない**。`figures.formats` / `abstract.labels` / `submission.*_formats` は「誌の値で置き換える」が
  正しい意味である。将来 lint に許可リスト (`allow_*`) を足すときも、和集合にすると誌が範囲を狭められなくなるので入れない。

---

## 6. 読み手の無いキー

次のキーは値を書いてもプログラムは読まない。「値があるから検査が効いている」と読み替えないこと。

| キー | 理由 |
|------|------|
| `figures.placement` | 予約キー。組み替えの発火は `figures.legends_section` と `tables.placement` が担う (このキーで発火させると、値を書いてある誌が意図せず組み替わる) |
| `figures.vector_container` | 予約キー。主形式は `figures.formats` の先頭が決めるので、役目が重なる。「ラスタが主形式だが一部の図だけベクターで出す」を作るときのために残す |
| `figures.keys_in_graphic` / `figures.multipanel_single_file` | 画像ファイルの中身への要求で、判定の材料が無い。執筆の規約 (`CLAUDE.md`) で扱う |
| `abstract.keyword_source` | 語が MeSH 由来かはシソーラスを引かないと決まらない。キーワードの数は `limits.keywords` が見る |
| `declarations.credit` / `publisher` / `numbering.table` | 記録用 |

---

## 7. 新しい誌のプロファイルを書くときの注意

- `_default/profile.yaml` を写して始める (手順は `docs/usage-guide.md` §4)。書かなかったキーは基底の既定値になる。
- ブロック名だけを書いて中身を空にしない (`tables:` だけの行など)。空のブロックは `null` と読まれてそのブロックの既定値を
  まるごと消すので、使わないブロックは名前ごと消す。
- 体裁キーを変えたら `make-reference.sh` を回し直す (§1)。
- 誌の受入形式を `submission.figure_formats` に書いておくと、受入形式外の図を出す前に止まる。書かなければ照合しない。
- `submission.text_formats` を書くと `SUBMISSION.md` が出る。ほかの `submission` のキーを調べていないうちは書かない
  (値の無い項目は「プロファイルに記録なし (規定を確認すること)」と出る)。
- 図の種類ごとの解像度 (線画 1200 dpi / 写真 300 dpi など) は表せない。`figures.dpi` には代表値を書き、必要なら
  `--dpi` で全図を高くする。`margins` も四辺一律の代表値になる。
