# BioHealth Informatics (BHI) の投稿規定と実装の対応 (journal-bhi.md)

*BioHealth Informatics* (発行: 日本医療情報学会 / Japan Association for Medical Informatics) へ投稿するときに、
規定のどの要求を本テンプレートのどこが受け持つかをまとめる。投稿の当日に上から順に確かめる表は
[`docs/bhi-submission-checklist.md`](bhi-submission-checklist.md)、執筆の開始から投稿までの手順は
[`docs/usage-guide.md`](usage-guide.md) §8、`profile.yaml` のキーは [`docs/profile-schema.md`](profile-schema.md) にある。

> 本テンプレートは雑誌・学会とは関係のない独立したツールである。本文書の規定の読み取りは
> 2026-11 時点の公開ページに基づく。**規定は変わりうるので、投稿の前に必ず公式の
> [For Authors](https://biohealth-informatics.com/for-authors/) で確かめること。**
> 本文書の引用は要点を示すための短い抜き書きで、正本は公式ページである。

- **投稿規定 (For Authors)**: <https://biohealth-informatics.com/for-authors/> — 原稿の形 (体裁・構成・図表・文献)
- **Editorial Policies**: <https://biohealth-informatics.com/editorial-policies/> — 投稿してよい原稿か
  (剽窃スクリーニング・オーサーシップ・AI 使用の開示・転載許諾・プレプリント)。§14
- **About**: <https://biohealth-informatics.com/about-biohealth-informatics/> — 刷り上がりページの上限 (Table 1) と
  超過ページ料金・ライセンス。§1 の末尾
- **投稿系**: ScholarOne Manuscripts <https://mc.manuscriptcentral.com/bhi>
- **本テンプレートでの id**: `data/journals/bhi/` (`--journal bhi`)。既定の記事種別は Original Article
  (`--article-type original`)

規定の文面だけでは一意に決まらない点は、本テンプレートの扱いとして §11 にまとめた。規定は変わりうるので、
公式ページと合わせて確かめ、気になる点は投稿前に編集事務局に確かめること。

---

## 0. 一行まとめ

`_default` (汎用の投稿フォーマット) と BHI の**体裁**はほぼ同じである (ダブルスペース / 12pt / A4 /
行番号。余白は `_default` が 25 mm、BHI が 25.4 mm)。違いの本体は体裁ではなく、**(a) 引用様式、(b) 提出物の分け方 (表を 1 表 1 ファイルに分ける・図の題と凡例の集約・
図を原稿に埋め込まない)、(c) 記事種別ごとの上限**の 3 点にある。体裁で違うのは、BHI が題・見出し・抄録まで本文と同じ 12pt に
そろえる点 (§2) と余白だけである。

図については、**BHI の受入形式のうちベクターを保てるのは PowerPoint だけ**である (JPEG / TIF / PNG はラスタで、
PDF / EPS は受け付けない)。本テンプレートは SVG を正本にしたまま、1 図 1 スライドの pptx に SVG をベクターのまま
埋め込んで出す (§5.1)。

---

## 1. 記事種別 (Manuscript Types)

本文語数は**表・図、文献、図のキャプションを除いた**語数 (抄録と Abbreviations の扱いは下の表)。

| profile の id | 種別 | 本文語数 | 抄録 | 図表の合計 | 本文の構成 |
|-----------|------|---------|------|---------|---------|
| `original` | Original Article | 4,000 | **構造化** (Objective / Methods / Results / Conclusion) 300 語 | 8 | Abstract, Introduction, Methods, Results, Discussion, Conclusion, Declarations, References, Figure Legends |
| `review` | Review Article | 4,800 | 非構造化 300 語 | 10 | Abstract, 本文 (内容に応じた構成), Declarations, References, Figure Legends |
| `short` | Short Communication | 2,400 | 非構造化 200 語 | 4 | Abstract, Introduction, Methods, Results, Discussion, Conclusion, Declarations, References, Figure Legends |
| `technical` | Technical Note | 3,600 | 非構造化 200 語 | 5 | Abstract, Introduction, **Technical Description**, Discussion, Conclusion, Declarations, References, Figure Legends |
| `data` | Data Report | 3,600 | 非構造化 200 語 | 5 | Abstract, Introduction, **Data Description**, **Usage Notes**, Conclusion, Declarations, References, Figure Legends |
| `perspective` | Perspective | 2,400 | 非構造化 200 語 | 4 | Abstract, 本文, Declarations, References, Figure Legends |
| `tutorial` | Tutorial | 2,400 | 非構造化 200 語 | 4 | Abstract, 本文, Declarations, References, Figure Legends |
| `letter` | Letter to the Editor | 1,200 | **なし** | 1 | 本文 (**見出しを立てない連続した文章**), Declarations, References, Figure Legends |

種別ごとの付帯条件:

- `review` — 系統的レビューは **PRISMA チェックリスト**を supplementary で出すことが推奨されている。
- `data` — データセットの**オープンデータとしての公開と公共リポジトリへの登録が必須**。永続的識別子つきの
  Data Availability Statement が要る。
- `perspective` — トピックについての**著者の専門性の簡潔な陳述**が推奨されている。
- `technical` — ソフトウェアやプロトコルを**公開リポジトリで提供する**ことが強く推奨されている。

値は `data/journals/bhi/profile.yaml` の `article_types` にあり、`--article-type` で切り替える。build・package・規定チェックは
解決した値を使う (存在しない種別は一覧を出して止まる)。

**本文語数の数え方** (規定が除くと書いているのは表・図 / 文献 / 図のキャプションだけで、ほかは規定の文面だけでは
決まらない。下の「本テンプレートの扱い」は気になれば投稿前に編集事務局に確かめる):

| 節 | 本文語数 | 根拠 |
|---|---|---|
| 表・図 / 文献 / 図のキャプション | 除外 | 規定本文 ("The word limit ... excludes tables/figures, references and figure captions.") |
| Abstract | 除外 (本テンプレートの扱い) | 抄録には別に語数の上限がある |
| Abbreviations | 除外 (本テンプレートの扱い) | 略語の一覧で、本文の文章ではない |
| **Declarations** | **算入** (本テンプレートの扱い) | 除外の対象に挙がっておらず、Main Text の節に含まれる |
| Acknowledgments | 算入 (本テンプレートの扱い) | 除外の対象のどれにも当たらない |
| 図表の凡例 (Legend Div) | 除外 (本テンプレートの判断) | §7.7 |

Declarations は算入されるので、CRediT の 14 ロールに沿って書くと数百語になり、4,000 語に対して無視できない。

**刷り上がりページの上限と超過ページ料金** (出典は For Authors ではなく About ページの Table 1):

| 種別 | 刷り上がりページの上限 (typeset pages) |
|------|------|
| Original Article | **9** |
| Review Article | 11 |
| Technical Note / Data Report | 7 |
| Short Communication / Perspective / Tutorial | 5 |
| Letter to the Editor | 3 |

- 上限を超えると **1 ページあたり 20,000 円 (税別)** の超過ページ料金が掛かる。投稿料・掲載料は無い。
- 同じ段落に "Invited manuscripts are exempt from excess page fees." とあるが、何が招待原稿に当たるかは定義されていない (§11)。
- 刷り上がりのページ数は**組版の後にしか分からない**ので、本テンプレートは検査しない (`profile.yaml` にもキーを置いていない)。
  語数と図表点数の上限を守ったうえで、図表が多い原稿や Declarations が長い原稿は超えうると見込むこと。

---

## 2. 体裁 (Style)

| 規定 | 値 | 本テンプレート |
|------|-----|-----------|
| 行間 | double-spaced throughout | `line_spacing: double`。段落スタイルが個別に持つ行送りも外して全体をそろえる (`text_styles.uniform_line_spacing: true`) |
| 文字の大きさ | 12-point | `font_size: 12pt`。**題・見出し・抄録も 12pt にそろえる** (`text_styles.uniform_size: true`。§2.1) |
| 用紙 | A4 | `paper_size: a4` |
| 余白 | at least 2.5 cm (1 inch) | `margins: 25.4mm` (= 1 inch。2.5 cm と 1 inch のどちらの読み方でも「以上」を満たす) |
| **行番号** | 必須 | `line_numbers: continuous` (本文だけ。`line_numbers_scope: manuscript`) |
| **ページ番号** | 必須 | `page_numbers: true` (フッタの `PAGE` フィールド。§2.1) |

書体の指定は規定に無いので、`_default` の Times New Roman 12pt を継承する。題・見出しの色の定めも規定に無い。本テンプレートは
級数をそろえた原稿で見出しだけが青く残らないよう、題・見出しのテーマ色を外して黒 (自動色) にする (`text_styles.heading_color: black`)。

### 2.1 reference.docx の実装 (行番号とページ番号)

体裁は `data/journals/bhi/reference.docx` に焼き込む。この reference.docx は pandoc の既定データから作る生成物なので
リポジトリには入っておらず、`bash data/journals/make-reference.sh bhi` で作る (`build.sh` / `diff.sh` は無ければ自動で作る)。
`profile.yaml` の体裁の値 (ダブルスペース / 12pt / Times New Roman / A4 / 四辺 25.4 mm / 連続行番号 / ページ番号) を
`main/00_setup/lib/patch_reference_docx.py` がそのまま書き込む。

- **行間**: 本文の既定 (`docDefaults`) に加えて、**題の段落スタイル (`Title`) の行間も本文と同じにする**。pandoc の既定の
  `Title` は行間を single で上書きしており、題が 2 行以上になると規定の "double-spaced throughout" から外れるため。
  さらに `uniform_line_spacing` で、段落スタイルが個別に持つ行送りをすべて外す (どのスタイルも文書全体のダブルを継ぐ)。
- **級数と色**: pandoc の既定の reference.docx は題 28pt / 見出し 1〜3 = 20・16・14pt (テーマ色の青) / 抄録 10pt を持ち、
  `docDefaults` を 12pt にしてもこれらは各スタイルの値で上書きされたまま残る。規定は "12-point type face" なので、
  `uniform_size` で級数を持つスタイルをすべて本文の 12pt にそろえ、見出しの階層は強調で付ける (題・見出し 1 = 太字 /
  見出し 2 = 太字斜体 / 見出し 3 = 斜体)。題を継ぐ著者・日付の行には、継いだ太字を打ち消す。`heading_color: black` で
  題・見出しの青を外す。Word で測る行送りは本文の最頻値なので、題や見出しの級数が外れていても数字には出ない点に注意する。
- **行番号**: 本文の `sectPr` に `w:lnNumType` を入れる。`w:start="0"` にしてあるのは、Word が「start + 1」から
  数え始めるためで、こうすると 1 行目が 1 になる (Word で確かめてある)。
- **ページ番号**: `sectPr` の設定だけでは足りず、**フッタのパートそのもの**が要る。`--page-numbers` で次の 4 点を冪等に入れる。

  | 追加するもの | 中身 |
  |--------|------|
  | `word/footer1.xml` | 中央揃え・本文の書体と大きさ・行間 single の 1 段落に `PAGE` フィールド。**`w:suppressLineNumbers` つき** (付けないとフッタの行にも行番号が振られ、ページ番号の隣に行番号が並ぶ) |
  | `[Content_Types].xml` | `/word/footer1.xml` の Override |
  | `word/_rels/document.xml.rels` | footer の Relationship (未使用の最大 rId + 1) |
  | `word/document.xml` | 本文の `sectPr` の先頭に `<w:footerReference w:type="default" …/>` |

  pandoc は reference.docx の `sectPr` の子要素を**そのまま写す**ので、子要素の順序 (`footerReference → … → pgSz → pgMar →
  lnNumType`) が規格どおりでないと、生成するすべての docx に黙って伝わる。書き込みは規格の順序の位置へ挿し込み、
  最後に順序を検算する。

**雑誌が配る reference.docx を入力にするときの扱い** (テンプレートを別の誌に使い回すための作り):

- `--page-numbers` を指定したときだけ既存のフッタを外して 1 枚入れ直す。**指定しなければ既存のフッタに触らない**
  (誌のテンプレートが自前のフッタを持つ場合に壊さないため)。外したフッタが本スクリプトの生成物と違うときだけ警告する。
- フッタを外すときは、文書の**すべての `sectPr`** (段落の中にある節の設定も含む) から `footerReference` を外し、パート・
  Override・Relationship を一緒に消す。書き出す前に、どこからも参照されない・存在しない rId を指す関係が無いことを確かめる
  (壊れた docx を黙って出さないため)。
- `pgMar` のヘッダ・フッタの位置は `min(708 twips, 本文の余白の半分)` にする (余白の狭い誌でページ番号が本文に食い込まないため)。
- 出力は**バイト単位で再現できる** (zip の項目の時刻を 1980-01-01 に固定)。作り直すたびに中身が揺れないので、
  手元で作り直した reference.docx を比べれば「意図した変更」と「作り直しただけ」を見分けられる。

**確かめ方と限界**: Word の実機での確かめ方は §12。コンテナの LibreOffice でも読み込み検査はできる。

```bash
docker compose -f docker/docker-compose.yml run --rm -u "$(id -u):$(id -g)" pandoc \
    soffice --headless --convert-to pdf --outdir jank/ data/journals/bhi/reference.docx
```

この検査で分かるのは、パッケージの構造・関係・種類の宣言が壊れていないこと (LibreOffice は Word と独立した実装なので、
壊れていれば読み込みに失敗する) だけである。フィールドの再計算・行番号の範囲・フッタ余白といった Word 固有の挙動は分からない。
**ページ数もこの検査では決まらない** — コンテナには Times New Roman も字幅の互換な Liberation Serif も無く、字幅の広い
DejaVu Serif で組まれるため、同じ docx が Word より 1 ページほど長くなる。**ページ数は roundtrip (Word の COM 変換) の PDF で見ること。**

---

## 3. 引用・文献 (References)

BHI は Vancouver 系だが、細部が `_default` の AMA の CSL と合わないので、専用の `data/journals/bhi/bhi.csl` を持つ
(本テンプレートが書いたもので、誌の公式の様式ではない)。

| 項目 | 規定 | `bhi.csl` の実装 |
|------|-----------|------|
| 本文中の指示 | 上付きの数字と閉じ括弧 ("superscript Arabic numerals in closing parenthesis")。閉じ括弧まで上付きかは文面からは決まらないので、本テンプレートは `1)` を丸ごと上付きにする | `cs:citation/cs:layout` に `vertical-align="sup"` と `suffix=")"` (§3.2 の技術メモ) |
| 番号 | 引用順 | `citation-number` で並べる |
| 著者 | 先頭 3 名まで。4 名以上は `et al` | `et-al-min="4"` / `et-al-use-first="3"`。`et al` はピリオドなし |
| 誌名 | Index Medicus の略誌名 | `ref.bib` の `journal` に略記で持つ (CSL では正式誌名から略せない) |
| 誌名の書体 | 立体 (規定の出力例がすべて立体) | イタリックにしない |
| ページ | 終了ページは短縮形 (出力例 2 の `1813–97`) | `page-range-format="minimal-two"` (`1813–1897` → `1813–97`) |
| 収載の範囲 | 本文で引用し、出版済みか受理済みのものだけ | 著者の責任 (検査しない) |

### 3.1 規定に載っている出力例 (CSL の受入テストに使う)

For Authors の References の節に、書式の例が 5 件載っている (正本は公式ページ)。本テンプレートはこの 5 件を
受入テストの期待値にしている (`data/dummy/bhi-csl/expected.txt`)。例から読み取れる書式の規則:

- 著者は `姓 イニシャル` (イニシャルはピリオドなしで続ける)、`, ` で区切り、末尾にピリオド。
- 論題はセンテンスケース + ピリオド。
- 誌名の後にピリオドを打たず、` 年; 巻:ページ.` と続ける (`Acta Cytol 1994; 38:9–17.`)。
- 和文の論文は末尾に `(in Japanese)`。
- DOI だけで引く文献は巻とページを置かず `誌名 年; doi: 10.xxxx/yyyy.`。
- 書籍は `版. 発行地: 出版社; 年. p. ページ.`。
- オンライン資料は `作成者. ページの題. In: 収録先. 発行主体. 年. URL. Accessed 日付.`。

### 3.2 実装の判断と執筆側の注意

**受入テスト**: `bash scripts/check-csl.sh [--docx <docx>]` (フィクスチャ `data/dummy/bhi-csl/`・本体
`main/step02_build/check_csl.py`)。規定の出力例 5 件と、et al を確かめる 1 件などを citeproc に通し、`expected.txt` と
**1 文字ずつ**照合する。`--docx` を付けると docx の `w:vertAlign` を直接読み、`1)` が丸ごと上付きかも確かめる。
`--docx` に渡すのは**フィクスチャからビルドした docx** である (原稿の docx を渡すと引用の件数が合わずに NG になる)。

```bash
bash scripts/build.sh --input data/dummy/bhi-csl --journal bhi --article-type original
bash scripts/check-csl.sh --docx data/step02_build/main.docx
```

#### 規定に記述が無く、実装で決めた点

| 論点 | 採った実装 | 根拠 |
|------|-----------|------|
| **複数引用・範囲引用** | `[@a; @d]` → `1,4)` / `[@a; @b; @c]` → `1–3)` (連続する番号は範囲にまとめる) | 規定に記述が無い。citeproc の `collapse="citation-number"` の結果を記録している |
| **locator つきの引用** | `[@d, p. 23]` → `4, p. 23)` | 規定に記述が無い。閉じ括弧の内側に入れた |
| **DOI の併記** | 巻・号・ページがあれば DOI は出さない。無いときだけ `誌名 年; doi: …` | 規定は「DOI だけで引く文献は例 3 のとおり」とし、例 1・2・4 に DOI が出ていない |
| **号 (issue)** | `巻(号):ページ` (`41(2):105–12`) | 規定にも出力例にも号を持つ文献が無い。Vancouver の既定に倣った |
| **ページの短縮の端** | `100–105` → `100–05` (最低 2 桁を残す) | `minimal-two` の素直な結果 |

#### 執筆側で守ること (自動化できない)

pandoc 3.6.4 の BibTeX の読み方に由来する。知らないと出力が規定と食い違う。

| 事象 | 対処 |
|------|------|
| BibTeX の `language = {Japanese}` は pandoc に捨てられる | 和文の論文には **`langid = {japanese}`** を書く。CSL の `language` に写り `(in Japanese)` が出る |
| 和文以外の非英語の文献 | CSL は変数の値を比べられないので、`language` があると言語によらず `(in Japanese)` になる。**`note = {in German}` のように書く** (`note` が最優先で括弧に入る)。逆に、書誌管理ソフトの控えを `note` に残すと文献リストに出てしまう |
| 書誌管理ソフト (Zotero / Better BibTeX など) が英語の文献にも `langid = {english}` を付けて書き出す | **英語の文献には `langid` を書かない (付いていたら消す)**。`langid = {english}` も `language` に写るので、英語の文献に `(in Japanese)` が付く |
| pandoc が英語と判定した題をセンテンスケースに直す | 固有名詞やコロンの直後の語は**波括弧で保護する** (`{Cancer Institute Hospital}` / `: {a} meta-analysis`)。`langid` を付けた和文の論文には掛からない |

#### 規定に定めが無く、執筆側で判断する点

| 事象 | 本テンプレートの判断 |
|------|-----------------|
| **MEDLINE に収載されていない誌の略誌名** — 規定は「Index Medicus の略誌名」を求めるが、字義どおりなら収載誌にしか略誌名が無い | **NLM Catalog** (<https://www.ncbi.nlm.nih.gov/nlmcatalog/>) で誌を引き、MEDLINE に収載されていなくても登録されている略誌名 (NLM Title Abbreviation) を使う。登録が無ければ正式誌名。引き方は [`docs/migration-latex.md`](migration-latex.md) §4 |
| **和文の法令・行政資料** — 規定の出力例に法令は無い (近いのは例 5 のオンライン資料)。和文の正式名称を `note` に入れると英文の文献リストに和文がそのまま出る | **題を英訳名**にして全体を波括弧で保護し、`url` と `urldate` を持たせ、`langid = {japanese}` で `(in Japanese)` を出す。英訳名は日本法令外国語訳データベース (<https://www.japaneselawtranslation.go.jp/>) に訳があればそれに合わせる。`@misc` でも `@online` でも同じ出力になる |

```bibtex
@misc{appi,
  author  = {{Government of Japan}},
  title   = {{Act on the Protection of Personal Information (Act No. 57 of 2003)}},
  year    = {2003},
  url     = {https://laws.e-gov.go.jp/law/415AC0000000057},
  urldate = {2026-11-09},
  langid  = {japanese}
}
```

```
1. Government of Japan. Act on the Protection of Personal Information (Act No. 57 of 2003). 2003. https://laws.e-gov.go.jp/law/415AC0000000057. Accessed 9 Nov 2026. (in Japanese)
```

`note = {個人情報の保護に関する法律}` を足すと、末尾の `(in Japanese)` が和文の名称に置き換わる。

#### 技術メモ (citeproc の書式の掛かり方)

pandoc 3.6.4 の citeproc では、書式の掛かり方が要素によって違う。

- `cs:text` の `prefix` / `suffix` には、その要素の `vertical-align` が**乗らない** —
  `<text variable="citation-number" vertical-align="sup" suffix=")"/>` は数字だけが上付きになり、閉じ括弧はベースラインに残る。
- `cs:citation/cs:layout` の `suffix` には layout の `vertical-align` が**乗る** — 引用のまとまり全体が 1 つの上付きの run になる。
  suffix はまとまりの末尾に 1 回だけ付くので `collapse` とも両立する (閉じ括弧を各引用に付けると collapse が効かず `1),2),3)` になる)。
- CSL 1.0.2 の「locale ごとの `cs:layout`」は使えない (`Multiple layout elements present in bibliography` で拒否される)。

この違いは目で見ても気づきにくいので、`check-csl.sh --docx` が OOXML で確かめる (閉じ括弧をベースラインに落とした CSL で
意図どおり失敗することも確かめてある)。

---

## 4. 提出物の構成 (Manuscript Submission)

ScholarOne には**種類ごとに分けてアップロード**する。原稿の本体に図を埋め込んではならない。

| 提出物 | 受け付ける形式 | 中身 | 本テンプレート (`package.sh --journal bhi --mode final`) |
|--------|---------|------|-----------|
| Text | MS Word | Title page / Abstract / 本文 / Declarations / References / **Figure legends** / **Tables (題つき)** | `manuscript.docx`。表を外し、図の題・凡例を集約して出す。本文はテキストだけになる (§6.1) |
| Tables | MS Word / Excel / PowerPoint (画像にしない) | 本文の末尾に置くか別のファイル | `tables/TableN.docx` に 1 表 1 ファイル (題 + 表 + 凡例) で出す (§6) |
| Figures | **JPEG / TIF / PNG / PowerPoint** (300 dpi 以上) | 図ごとに 1 ファイル | `figures/FigureN.pptx` (既定) か `--format png` で `FigureN.png` (§5) |
| Video | MP4 (1 ファイル 50 MB 以内) | — | `supplementary/` に無変換で複製し、形式と大きさを検査する |
| 各種フォーム | COI Disclosure Form / License to Publish | **各 1 通**。連絡著者が全著者を代表して記入し、PDF で出す (§4.1) | `SUBMISSION.md` にチェック項目として出す (中身は見ない) |
| Supplementary | 任意 (**無変換で公開**) | 査読の対象。受理後は変えられない | `<入力ルート>/supplementary/` を無変換で複製する |

**PDF と EPS は図の形式に含まれない** (`_default` の最終図は PDF なので、BHI ではそのまま使えない)。BHI では PowerPoint
(ベクター) を主形式、300 dpi の PNG を退避先にする (§5 / §5.1)。

### 4.1 LTP / COI フォーム

入手先は For Authors の「LTP/COI Forms」の節 (<https://biohealth-informatics.com/for-authors/>)。どちらも `.docx` の様式である。

| フォーム | URL |
|---------|-----|
| COI Disclosure Form | <https://biohealth-informatics.com/wp/wp-content/uploads/2026/06/BHI_COI_disclosure.docx> |
| License to Publish | <https://biohealth-informatics.com/wp/wp-content/uploads/2026/06/BHI_LtoP_v2-1.docx> |

**どちらも 1 通で、連絡著者が全著者を代表して出す** (COI は For Authors の Competing interests に全共著者の申告を
1 通にまとめるとあり、LTP は様式に連絡著者が全共著者を代表して結ぶとある)。

| | 通数 | 誰が書くか |
|---|------|----------|
| COI Disclosure Form | 1 通 | 連絡著者が**全共著者の申告を集め**、1 通にまとめて出す |
| License to Publish | 1 通 | 連絡著者が全共著者を代理して締結する (全著者名を書く) |

- 様式のヘッダに、**記入したうえで PDF に変換してアップロードする**よう指示がある (本文ではなくヘッダにあるので見落としやすい)。
  署名欄は無い。
- **COI の申告の要点** (共著者に頼むときの説明用。正本は様式そのもの): 対象は**投稿前 24 か月**で、本人だけでなく
  **配偶者その他の近親者**の関係も含む。雇用・株式・特許・講演料・原稿料・研究費・寄附金・寄附講座・旅費などの分類ごとに
  金額の閾値がある。該当が無ければ「No」に印を付けるだけでよい。
- **License to Publish の要点**: 出版者 (日本医療情報学会) に非独占のライセンスを与え、**著作権は著者に残る**。
  公開ライセンスは **CC BY 4.0**。著者は、未発表で他誌の審査中でないこと、第三者の素材について書面の許諾を得ていること
  (§14.4)、全共著者から代理の権限を得ていることを保証する。

フォームの記入と回収は**ツールの外**の作業である。`SUBMISSION.md` は `profile.yaml` の `submission.forms` を
チェック項目として出すだけで、中身は見ない (通数と記入者は `submission.forms` の各項目に書いてある)。
COI は共著者への聞き取りが要るので、投稿の 2〜4 週間前に始めること ([`docs/bhi-submission-checklist.md`](bhi-submission-checklist.md))。

---

## 5. 図 (Figures)

| 規定 | 本テンプレート |
|------|-----------|
| 原稿ファイルに**埋め込まない** | `--mode final` が図を外し、元の位置に `[Figure N about here]` を残す |
| 図の題 (**15 語以内**) と凡例 (**300 語以内**) を **References の後の新しいページ**にまとめる (画像の側に書かない) | 題 = キャプション / 凡例 = `custom-style="Legend"` Div と書き分け (§7.6)、`figures.legends_section` が集約する (§6.1)。語数は規定チェックが数える (§7.7) |
| 形式は JPEG / TIF / PNG / PowerPoint、**300 dpi 以上** | 既定は pptx (SVG をベクターのまま + 300 dpi の PNG。§5.1 / §5.3)。`--format png` で 300 dpi を保証した PNG (§5.2) |
| 番号は本文の初出順で、その順でアップロードする | pandoc-crossref が初出順に番号を振る。`SUBMISSION.md` の図の一覧も書き出した順 (= 番号順) に並ぶ |
| **多パネル図は 1 ファイルに合成する** | 執筆者が作図の側で行う (検査しない) |
| 図の凡例キー (key) は**画像の中**に入れる (凡例の文章に書かない) | 執筆者が作図の側で行う (検査しない) |
| 余白を最小限に切り詰める (closely cropped) | 執筆者が SVG の側で行う。`slide_fit: figure` はスライドを図の公称サイズに合わせるだけで、SVG の中の余白は削らない |
| 正しい向きでアップロードする | 執筆者が確かめる |
| 既出の図の再録は権利者の許諾を取り、凡例に明記し、出典を文献に載せる | 執筆者が行う (§14.4) |

**300 dpi の落とし穴**: `rsvg-convert` の dpi の指定は、SVG が物理単位 (pt / mm / in) を持つときにしか画素数に効かない。
px 単位や単位なしの SVG では指定した dpi が反映されず、300 dpi を満たせない。本テンプレートは SVG の公称サイズから
必要な画素数を計算して `-w` / `-h` で渡し、生成した後に実際の画素数を検算する (§5.2)。

### 5.1 図をベクターのまま提出する — PPTX 経路

#### 5.1.1 なぜ PPTX なのか

BHI の受入形式は JPEG / TIF / PNG / PowerPoint の 4 つで、**JPEG・TIF・PNG はすべてラスタ** (拡大すると必ず劣化する)。
**PowerPoint (pptx) だけがベクターを保てる受入形式**である。規定の 300 dpi も原文は "image files should have a minimum of
300 dpi" で、ラスタ画像への要求と読める。SVG / PDF / EPS は受け付ける形式に挙がっていないので、直接出す道は無い。
規定は PowerPoint の図が編集できる図形であることまでは求めていない (本テンプレートは、ベクターの図を pptx で、
画像の図は画像のファイルのまま出す。§11)。

pptx (OOXML) はスライドの中身を DrawingML というベクターの記述で持ち、さらに **SVG をネイティブに埋め込む拡張**を持つ。
この拡張は、本テンプレートが docx に図を埋め込むときに使っているものと同じである (§5.1.3)。

pptx の作り方には 3 案ある。呼び名 (案 A / 案 B / 案 B′) は `profile.yaml`・ログ・`SUBMISSION.md` でも使う
([`docs/architecture.md`](architecture.md) §2.5 の「pptx の経路と案 A / 案 B / 案 B′」)。

#### 5.1.2 案 A — 執筆者が PowerPoint で作った pptx をそのまま出す

図の隣に同名の `.pptx` を置くと、最終提出ではそれを**無変換でコピー**する (`figs/fig1.svg` + `figs/fig1.pptx`。原稿は
`.svg` のプレビューを参照したままにする)。

- **利点**: 変換が無いので劣化しない。DrawingML のシェイプのままなので、組版の側が扱いやすい。解析の結果を PowerPoint で
  仕上げる作業の流れをそのまま使える。
- **守ること** (`CLAUDE.md` の執筆規約): **1 ファイル 1 スライド** (2 枚以上はエラーで止まる。分割はしない)。
  **マクロを含むもの** (`.pptm` / `.ppsm` / `.potm`、`ppt/vbaProject*` を含むもの) は拒否する (投稿系がマクロを含む文書の
  変換に失敗すると明記しているため)。
- **限界**: pptx はバイナリなので git の差分が効かない。PowerPoint は既定でフォントを埋め込まないので、受け側に同じ
  フォントが無いと字送りが変わる。**中身はテンプレートの検査の対象外**になるので、フォント・余白・凡例キーは PowerPoint で
  自分で確かめる (`check-figures.sh` は不合格ではなく「注意」に出す)。

#### 5.1.3 案 B — SVG を pptx に埋め込む (既定)

`figs/*.svg` を正本にしたまま、**1 図 = 1 pptx = 1 スライド**を生成する。スライドには SVG をネイティブに埋め込み、
PNG を代替表示として同梱する (`main/00_setup/lib/svg_pptx.py`)。埋め込みの仕組みは docx と同じで、共通部は
`main/00_setup/lib/ooxml_svg.py` にある。

```
a:blip @r:embed="rIdM"                                      ← PNG (代替表示) への参照
 └ a:extLst
    └ a:ext uri="{96DAC541-7B7A-43D3-8B79-37D633B846F1}"    ← Office の SVG 拡張
       └ asvg:svgBlip r:embed="rIdN"                        ← SVG 本体への参照
+ [Content_Types].xml に Extension="svg" の Default
+ media/ に SVG と PNG の実体
```

pptx では同じ構造を `p:pic/p:blipFill/a:blip` の下に置き、実体を `ppt/media/` に入れる。ただし共通なのは `a:blip` の下の拡張の
注入と Content_Types への登録だけで、pptx にはそれを載せる骨格を作る処理が別に要る (骨格の選び方は §5.3)。

- **利点**: 正本が SVG (テキスト) のままなので git の差分が効く。Mermaid (`.mmd` → SVG) や PDF 図 (→ SVG) の経路がそのまま
  最終提出までつながり、図の足し方・直し方が草稿と変わらない。スライドの寸法を図の公称サイズに合わせるので、スライドの側に
  余白を足さない。代替表示の PNG を同梱するので、SVG に対応しない環境でも図は消えない。
- **closely cropped は自動では満たさない**: 規定の要求は「描いた内容の周りの白を削れ」で、SVG の `viewBox` が描いた内容より
  広ければ (作図ライブラリの既定の余白や台紙など)、その白はそのままスライドに載る。余白を詰めるのは執筆者の仕事である。

**リスク** (コードのコメントとログはこの番号で参照する):

1. **受け側の Office の世代で、ベクターになるかが変わる。** SVG のネイティブ表示に対応するのは
   **Microsoft 365 / Office 2019 以降**で、**買い切り版の Office 2016 は代替表示の PNG を描く**。投稿系の査読用の PDF 変換が
   この拡張を解釈する保証も無い。したがって **代替表示の PNG は保険ではなく、多数の受け手が実際に見る本体**であり、
   300 dpi で持つ (§5.2)。Microsoft 365 の PowerPoint と Word では SVG の側が描かれることを確かめてある (§5.3 / §12)。
2. **スライドに載るのは SVG の画像 1 枚で、DrawingML のシェイプの集まりではない。** ただし Microsoft 365 の PowerPoint では、
   **グループ化を解除すると文字の選択・編集ができる** (§5.3)。編集できるシェイプが求められても、受け手の操作 1 つで応えられる。
3. **SVG の中の文字は受け側のフォントで描かれる。** 文字をアウトライン化すれば字送りは崩れなくなるが、既定ではしない
   (`figures.pptx.text_to_path: false`)。理由は (a) BHI は受理後に組版の側で組み直すので、文字を図形にすると組版の側で直せず、
   査読者も検索できない、(b) リスク 1 のとおり多数の受け手には PNG が表示され、PNG はコンテナのフォントで描き終えているので
   フォントの差の実害が小さい、(c) アウトライン化すると、リスク 2 の「グループ化の解除で文字を編集できる」が使えなくなる。
   特定のフォントの崩れが実際に見つかったときのために `true` を残してある (§5.3)。案 A も同じフォントの問題を持つ。

#### 5.1.4 案 B′ — SVG を PowerPoint のネイティブのシェイプに変換する (初期の範囲外・未実装)

LibreOffice の svg→pptx 変換で、パスと文字を DrawingML のシェイプに落とす案。本当に編集できるベクターになるが、
文字の位置ずれ・パスの近似・グラデーションの劣化が起きやすく、変換の結果を毎回目で確かめる手間がかかる。
**初期の範囲から外し、実装していない**。`figures.pptx.mode: native-shapes` を指定するとエラーで止まる
(黙って案 B に落とすと「編集できるシェイプ」という要求に応えたことにならないため)。ベクターは必須ではなく (§5.1.1)、
案 B でもグループ化の解除で文字を編集できる (§5.1.3 リスク 2) ので、当面は要らない見込みである。

#### 5.1.5 選び方と差し戻されたときの退避

**案 B を主経路にし、案 A を「正本が pptx のときの受け口」として用意する。** SVG を正本にする本テンプレートで、SVG の
ベクターの情報を届けられる受入形式は pptx しか無い。

- **元がラスタの図 (`.png` など) は pptx に包まない。** 画像の図は画像ファイルのまま出す (§5.1.1)。ラスタを pptx に包んでも
  拡大には強くならない。案 B の対象は SVG から作る図だけである。
- **退避先を残す**: ベクターは必須ではないので、`figures.formats: [pptx, png, tif]` の順にしてあり、pptx に問題があれば
  300 dpi の PNG にすぐ切り替えられる。

| 差し戻しの理由 | 対応 |
|---|---|
| 形式が不可 (pptx を受け付けない) | `bash scripts/package.sh --journal bhi --mode final --format png` (300 dpi の PNG。必須要件は満たす) |
| ベクターのシェイプとして認められない | 案 A (PowerPoint で仕上げた図を図の隣に置く。変換しない)。案 B′ は未実装 |

#### 5.1.6 profile.yaml の設定

```yaml
figures:
  formats: [pptx, png, tif]   # 先頭が主形式。pptx = ベクター。不可なら png (300 dpi) へ退避
  dpi: 300                    # png 図と、pptx に同梱する PNG の解像度
  vector_container: pptx      # 予約キー (いまはどのコードも読まない)
  pptx:
    mode: svg-blob            # svg-blob (案 B) / passthrough (案 A を必須にする) / native-shapes (案 B′ = 未実装・停止)
    slide_fit: figure         # スライドを図の公称サイズに合わせる (fixed = 既定サイズに縮めて中央に置く)
    png_fallback_dpi: null    # null = figures.dpi を継承
    text_to_path: false       # 文字をアウトライン化しない (§5.1.3 リスク 3)
```

- `slide_fit` は `--slide-fit` で実行ごとに上書きできる (規格外の寸法の図を退避するのに、`profile.yaml` を書き換えずに済むように)。
- `mode` と `slide_fit` の綴りの誤りは、黙って既定に倒さずエラーで止める。
- `vector_container` は `figures.placement` と同じく読み手の無い予約キーである。`formats` の先頭が主形式を決めるので、
  `formats: [png, ...]` と `vector_container: pptx` を同時に書いても pptx は出ない。キーの一覧は
  [`docs/profile-schema.md`](profile-schema.md)。

### 5.2 ラスタの 300 dpi の保証

| ファイル | 役割 |
|---------|------|
| `main/00_setup/lib/svg_raster.py` | SVG の公称サイズの解析 / 必要な画素数の計算 / `rsvg-convert -w/-h` / 実際の画素数の検算 / pHYs の書き込み |
| `main/step01_figures/process_figures.py` | docx に埋め込む代替表示の PNG (`*.svg.png`) を上の経路で作る |
| `main/step05_package/package.py` | 分けて出す図 (`figures/FigureN.png`) と pptx に同梱する PNG を上の経路で作る |
| `main/step01_figures/check_dpi.py` / `scripts/check-figures.sh` | 受入テスト |

**公称サイズの決め方**:

1. SVG のルートの `width` / `height` が**物理単位** (pt / pc / mm / cm / in / Q) → その値をインチに換算する。
2. `px` / 単位なし → **CSS px = 1/96 インチ**とみなす。
3. `width` / `height` が無い・`%` → `viewBox` を CSS px とみなす。
4. 片方だけある → `viewBox` の縦横比でもう片方を補う。
5. どれも無い → 草稿のビルドは警告つきで通すが、提出図を作る `--mode final` は**エラーで止まる** (解像度を保証できない図を黙って出さない)。

**PDF 図の寸法**: pdf2svg は MediaBox (pt) を単位なしで `width` / `height` に書くので、SVG の約束どおり CSS px と読むと
75% の大きさになり、300 dpi のつもりで作った PNG がその実寸では 225 dpi になる。前処理は pdf2svg の直後に
`width` / `height` へ `pt` を付ける (`viewBox` はそのまま)。手で書いた SVG の単位なしは CSS px のままである。

必要な画素数は**切り上げる** (実効の解像度が目標を下回らないように)。作った後に PNG の IHDR から実際の画素数を読み直し、
足りなければ**警告ではなくエラー**にする。

**pHYs (物理解像度)**: コンテナに画像ライブラリ (Pillow / ImageMagick / exiftool) が無いので、標準ライブラリ
(`struct` + `zlib.crc32`) でチャンクを組んで IHDR の直後に入れる (既存の pHYs は置き換える)。値は**切り上げる** —
pHYs は px/m の整数なので 300 dpi を厳密に表せず (11811.02)、四捨五入した 11811 を書くと pandoc は 299 dpi と読む。
投稿系が「300 dpi 以上」を機械で判定するなら 299 は違反になりうるので、11812 を書いて必ず目標以上にする。

**docx 上の図の大きさ**: pandoc は pHYs の無い PNG を 72 dpi と読むが、pHYs を入れるので docx の図は SVG の公称サイズで
置かれる。物理単位で幅を書いた図は、その実寸のとおりに (思ったより小さく) 見えることがある。見た目の大きさは原稿の側の
`{width=...}` で決める。本文幅を超える図は pandoc が本文幅に縮める。

**執筆者が知っておくこと**:

- **SVG の公称サイズが「印刷したい幅」より小さいと、その幅での実効の解像度は 300 dpi を下回る。** 保証しているのは
  「公称サイズで置いたときに 300 dpi」で、誌が図をどの幅で組むかは分からない。300 dpi を求める誌に出す図は、SVG のルートに
  **物理単位で幅を書く** (`width="160mm"` など) のが安全である (本文幅いっぱいなら幅 1890 画素以上が要る)。
- **自分で置いたラスタ図 (写真など) は保証の対象外**で、そのまま複製される。解像度は執筆者が担保する
  (受入テストは不合格ではなく「注意」に出す)。
- 検算は `bash scripts/check-figures.sh --journal bhi` (図のツリー。SVG の公称サイズから期待する画素数を出し、実際の画素数まで
  確かめる) と `bash scripts/check-figures.sh --journal bhi --figures-dir data/output/bhi/figures` (分けて出した図。元の SVG が
  無いので pHYs だけを見る)。両方を回すこと。

**用意していない経路** (判断の記録):

- **TIFF をそのまま作る経路 (G6)**: 用意していない。画像ライブラリを足すか画像の符号化を自前で書くことになり、すべてのビルドが
  使う pandoc コンテナが重くなる一方、BHI は PNG を受け付け、第一希望は pptx である。`--format tiff` は PNG で代わりに出し、
  代わりであることを毎回警告する。**TIFF しか受け付けない誌に出すときに考え直す。**
- **`figures.dpi` を図の種類 (線画・写真・複合) ごとに分けること**: 用意していない。足りないのはキーではなく、どの図が
  どの種類かを知る手段である。実行ごとに `--dpi <n>` で上書きできる。

**図の形式の扱いを厳しくしてある点**:

- 生成の経路が無い形式 (未知の綴りなど) は、図を出す直前に**エラーで止まる** (草稿と `--keep-figures` では図を作らないので、
  判定は図を出す直前に置く)。
- `--format` の値を検査する (綴りの誤りが別の形式に化けない)。
- **受入形式の外の形式を明示したときは、明示の同意 `--allow-disallowed-format` を求める** — `png` と `pdf` の打ち間違いで
  規定違反の図が一式そろうのを防ぐため。

| 操作 | 終了コード | `figures/` |
|---|---|---|
| `--mode final` (既定 = pptx) | 0 | `Figure1.pptx` / `Figure2.pptx` |
| `--mode final --format png` | 0 | `Figure1.png` / `Figure2.png` (300 dpi を検算済み) |
| `--mode final --format pdf` | **1** | 出ない (受入形式の外) |
| `--mode final --format pdf --allow-disallowed-format` | 0 | `Figure1.pdf` / `Figure2.pdf` (警告つき) |
| `--mode final --format eps` / `--format pnj` (綴りの誤り) | 1 | 出ない |

### 5.3 ベクター提出 (PPTX) の実装

| ファイル | 役割 |
|---------|------|
| `main/00_setup/lib/ooxml_svg.py` | **docx と pptx で共通**の SVG のネイティブ埋め込み (拡張の注入 / Content_Types への svg の登録 / rId の採番) |
| `main/00_setup/lib/svg_pptx.py` | 1 図 = 1 pptx = 1 スライドの生成 (案 B) と、図の隣の pptx の無変換コピー (案 A) |
| `main/step05_package/package.py` | pptx を主形式にする配線 / `figures.pptx` の解決と検査 / `--slide-fit` |
| `docker/svg-conversion/convert.sh` | `--outline-svg` (文字をアウトライン化した SVG。`text_to_path: true` のときだけ使う) |
| `main/step01_figures/check_dpi.py` | 受入テストの pptx の検査 (SVG 拡張の位置 / SVG と PNG の同梱 / 同梱した PNG の pHYs) |

#### 骨格の pptx の選び方

**`pandoc --print-default-data-file reference.pptx` を骨格にする。**

| 案 | 判断 | 理由 |
|---|---|---|
| pandoc の既定の reference.pptx を加工する | **採用** | 依存を足さずに済む。reference.docx を作るのと同じ流儀になる |
| python-pptx をコンテナに足す | 採らない | すべてのビルドが使う pandoc コンテナを重くする |
| 最小のひな形 pptx をリポジトリに置く | 採らない | バイナリを置くことになり、「正本はテキスト」の原則に反する |

骨格 (4 スライド + ノート) からスライド 2〜4・ノート・使わないテーマを落として 1 スライドにする。`docProps/core.xml` /
`docProps/app.xml` は**中立な内容で書き直す** (骨格には pandoc の開発者の氏名・作成日時・アプリケーション名が入っており、
そのまま投稿物に載せないため)。スライドマスター・レイアウト・テーマはそのまま使い、スライドは白紙のレイアウト ("Blank") を指す
(タイトルの枠があるレイアウトだと、空のプレースホルダが PowerPoint に見えるため)。

#### SVG 拡張を一次資料と突き合わせる

拡張の綴りを「自分が書いた綴りを自分で探す」形で検査しても誤りは見つからないので、Microsoft の一次資料と突き合わせた。

| 確かめたこと | 結果 | 出典 |
|---|---|---|
| 名前空間 | `http://schemas.microsoft.com/office/drawing/2016/SVG/main` | [MS-ODRAWXML] のスキーマ |
| 要素 | `svgBlip` (型 `CT_SVGBlip`。`r:embed` / `r:link` を持つ) | 同上 |
| 修飾名 | `asvg:svgBlip` | Open XML SDK の `SVGBlip` クラス |
| 対応する版 | Office 2019 以降 | 同上 (§5.1.3 リスク 1 の裏づけ) |

- <https://learn.microsoft.com/en-us/openspecs/office_standards/ms-odrawxml/cc083f6d-bc38-4ff4-b32a-5bc97df8addc>
- <https://learn.microsoft.com/en-us/openspecs/office_standards/ms-odrawxml/2451f45e-5d77-4661-86d1-0a017fced779>
- <https://learn.microsoft.com/en-us/dotnet/api/documentformat.openxml.office2019.drawing.svg.svgblip>

拡張の識別子 `{96DAC541-7B7A-43D3-8B79-37D633B846F1}` (`a:ext` の `uri`) は上のスキーマには載っていない (スキーマは要素だけを
定め、どの `a:ext` に載せるかは定めていない)。この値の裏づけは Office が作った実ファイルと、独立した複数の実装にとどまる。
この値を含む docx と pptx が Microsoft 365 の Word と PowerPoint でベクターとして描かれることは確かめてある (§12)。

#### スライドの寸法

ECMA-376 のスライドの寸法 (`ST_SlideSizeCoordinate`) は 1〜56 インチ。下限と上限で扱いを分ける。

| 状況 | 挙動 | 理由 |
|---|---|---|
| 1〜56 インチに収まる | スライド = 図の公称サイズ (余白を足さない) | `slide_fit: figure` の動作 |
| 1 インチを割る軸がある | その軸だけスライドを 1 インチに広げ、図を中央に置く。**足した余白を警告に出す** | 1 インチ未満の図は珍しくない。止めると普通の図で提出が止まり、`fixed` に逃がすと余白がもっと増える |
| 56 インチを超える軸がある | **エラーで止まる**。`--slide-fit fixed` / SVG の寸法の修正 / `--format png` を案内する | 上限の側は広げても縮めても意味が変わる (図ははみ出すか、公称サイズを伝えなくなる) |
| `slide_fit: fixed` | スライド = 骨格の既定の大きさ (10 × 5.625 インチ)。図は縦横比を保って収め、中央に置く。**拡大はしない** | 拡大すると PNG の実効の解像度が目標を下回る |

#### 代替表示の PNG の解像度

PNG は `svg_raster.py` (§5.2) を通すので 300 dpi を保証する。ラスタ化の基準は**実際にスライドに置く寸法**で、`fixed` で縮めて
置くときは縮めた寸法で作る (公称サイズで作ると PNG が過大になり、大きな図では画素数の上限に当たって退避の経路が止まるため)。
図は公称サイズ以下にしか置かれない (広げても拡大しない) ので、置いた寸法での実効の解像度は必ず目標以上になる。

#### `text_to_path` (文字のアウトライン化)

既定は `false` (理由は §5.1.3 リスク 3)。`true` にすると `docker/svg-conversion/convert.sh --outline-svg`
(`inkscape --export-type=svg --export-plain-svg --export-text-to-path`) が `<stem>.outline.svg` を作り、pptx にはそれを埋め込む。
アウトライン化した SVG が無いのに `true` のときは**エラーで止まる** (フォントへの依存を消したつもりで消えていない状態を見逃さないため)。

#### 案 A (図の隣の pptx の無変換コピー)

- 発火の条件: 原稿が参照する図と同じ場所・同じ名前 (拡張子を除く) の `.pptx` があること。図のツリー
  (`data/step01_figures/figs/`) → 入力ルート (`src/figs/` など) の順に探す。`figures.pptx.mode: passthrough` にすると**必須**になり、
  無ければ止まる。
- 機械で検査すること: スライドが 2 枚以上ならエラー / `.pptm` などマクロ有効の拡張子・`ppt/vbaProject*` を含むものは拒否。
  スライドの分割はしない (1 ファイル 1 スライドにしてから置く)。
- 中身はテンプレートの検査の対象外なので、受入テストは不合格ではなく「注意」に出す。
- 案 A のために LibreOffice で pptx を変換することはしない (草稿の docx には同名の SVG のプレビューを使う)。
  「PDF 化に LibreOffice を使わない」という設計 ([`docs/architecture.md`](architecture.md) §0) とも衝突しない。

#### 受入テスト自身の識別力

`bash scripts/check-figures.sh --self-test` が、その場で pptx を 1 つ作り、わざと 2 通りに壊して (`asvg:svgBlip` の参照先を同梱の
PNG に差し替える / スライドへの関係を消す)、検査がそれを落とせることを確かめる。壊した固定のファイルはリポジトリに置かない
(生成器を変えたときに古くなり、検査が形だけになるため)。

#### 再現性

zip の各項目の時刻を 1980-01-01 に固定し、書き出す順と `docProps` の日時も固定してある。同じ入力から 2 回作った pptx は
バイト単位で一致する。

#### 独立した OOXML の実装での読み込み検査

コンテナの LibreOffice Impress は、生成した pptx を**独立した実装が読み込めるか**の検査にだけ使う (体裁の再現には使わない)。

```bash
docker compose -f docker/docker-compose.yml run --rm -u "$(id -u):$(id -g)" pandoc \
    soffice --headless --convert-to pdf --outdir jank/ data/output/bhi/figures/Figure1.pptx
```

pandoc の既定の reference.pptx が読める (フィルタが効いている) こと、`ppt/presentation.xml` を抜いた壊れた pptx は拒否される
(検査に識別力がある) ことを対照にしている。生成した pptx は読み込まれ、出力 PDF の MediaBox がスライドの寸法と一致し、
画像オブジェクトは 0 個 (= PNG ではなく SVG の側がベクターで描かれ、文字も文字のまま) になる。

#### PowerPoint での確認

`Microsoft PowerPoint for Microsoft 365` (16.0 系) で、SVG の側と PNG の側に別々の文字を焼き込んだ診断用の pptx を開くと、
**SVG の側が描かれた**。0.08 / 0.15 / 0.3 mm の細線の描き分け、2.4 pt 相当の小さな文字、和文も問題なかった。提出物の
`Figure1.pptx` / `Figure2.pptx` も正しく描かれ、**グループ化を解除すると文字の選択・編集ができた**。

- **PowerPoint から PDF を作るときは、印刷ではなく「エクスポート → PDF/XPS の作成」を使う。** 印刷ドライバ
  (`Microsoft Print to PDF`) はベクターも文字もビットマップに潰し、PDF の作成者の欄に Windows のアカウント名を書く。

**確かめていないこと**: 代替表示の PNG が描かれる環境 (買い切り版の Office 2016 / 投稿系の査読用の PDF 変換) での見え方 (§13)。

---

## 6. 表 (Tables)

| 規定 | 本テンプレート |
|------|-----------|
| **本文ファイルの末尾**に置く (別のファイルでもよい) | `tables.placement: separate` で、題 + `w:tbl` + 直後に続く `Legend` 段落を 1 組にして本文から外し、`tables/TableN.docx` に 1 表 1 ファイルで出す (§6.1)。規定は本文の末尾 ("placed at the end of the main manuscript file") と別のファイル ("or can be submitted as a separate file") のどちらも認めている。本テンプレートは**別のファイルを既定にする** — 本文の docx がテキストだけになり、どちらの読み方にも合うため。末尾に移すときは `end` |
| Word の**表オブジェクト**で作る (画像やスプレッドシートの埋め込みは不可) | pandoc が `w:tbl` を作る |
| 題は**表の上** (15 語以内)、凡例は**表の下** (300 語以内) | 題 = キャプション / 凡例 = 直後の Legend Div (§7.6)。pandoc は表のキャプションを表の上に出すので、題が上・凡例が下になる |
| **色・網掛けは使わない**。強調は上付き・番号・記号・太字で行い、意味は凡例で説明する | 三本線 (booktabs) も `.grid` も無彩色。docx の表に `w:shd` / `w:color` / `w:highlight` (罫線の色・テーマ色を含む) があれば警告する (生 OOXML や手で貼った表に効く) |
| **数値の桁区切りにカンマを使わない** (`10 000` のように空白) | 規定チェックが `1,234` の形の数値を拾う (URL と References の節は除く。§7.7) |
| 番号は本文の出現順 (Table 1, Table 2 …) | pandoc-crossref が振る |

### 6.1 提出構成の組み替えと SUBMISSION.md

`--mode final` で `main/step05_package/relocate.py` が `manuscript.docx` を組み替える (図のプレースホルダ化と同じ 1 回の書庫の開閉で行う)。

**組み替えの結果** (`data/dummy/bhi` を `--journal bhi --mode final` でパッケージした docx):

- 本文: 図の位置に `[Figure N about here]`、表の位置に `[Table N about here]` が残る。図の題と凡例、表は本文から消える。
- 末尾: References → **改ページ** → `Figure Legends` の見出し → 図の題 (`ImageCaption`) と凡例 (`Legend`) の組 → `w:sectPr`
  (`tables.placement: end` の誌では、このあとに **改ページ** → 表の題 (`TableCaption`) → 表 → 凡例 が続く)。
- 表のファイル `tables/TableN.docx`: 題 (表の上) → 表 → 凡例 (表の下)。組み替えた本文の書庫を複製して `w:body` をその組と元の
  `w:sectPr` だけにしたものなので、スタイル・フッタが本文と同じになる (別の reference.docx から組み立て直すと、本文と表で体裁が
  ずれうる)。行番号は `line_numbers_scope: manuscript` なので外れ、ページ番号は残る。表の体裁の検査は表のファイルにも掛ける。
- `.textbox` の中の図・題・凡例・表は**動かない** (本文の流れの外にあるため)。
- `tables.placement` の綴りを誤るとエラーで止まる (表が本文に残ったまま、警告なしに提出物ができるのを防ぐ)。

**設計の判断** (規定に書かれていないこと):

1. **(`end` のとき) 表の前に見出しを置かない** (`tables.section_title: null`)。規定は原稿の構成として "Tables" を挙げるだけで見出しの文言を
   定めていないので、規定に無い文字列を足さない。各表の題 ("Table 1: …") が目印になる。見出しが要る誌のためにキーはある。
2. **ブックマークは動かさない**。pandoc-crossref は `fig:x` / `tbl:x` のブックマークを図表の前後に置き、本文の "Fig. 1" /
   "Table 1" はそこへのリンクになっている。移すのは段落と表だけにして、ブックマークは元の位置に残す。相互参照のリンクは
   `[Figure N about here]` / `[Table N about here]` の位置に着地する (本文のどこに図表が入るかを指す動線としてはこれが自然である)。
3. **`Legend` 段落の見分けは「直前が何か」だけに頼る**。図と表の凡例は同じ `Legend` スタイルなので、docx の側の手がかりは
   配置しか無い。「`ImageCaption` の直後に続く `Legend`」「`w:tbl` の直後に続く `Legend`」として拾う。配置の規則が守られて
   いることは、Markdown の層で規定チェックが確かめる (§7.7)。

**実装の注意** (どちらも実際に起きる):

- 添字で `body.insert()` すると `w:sectPr` が最後の子でなくなる (前から抜いて後ろへ入れるので添字が 1 ずれる)。要素を基準に
  (`sectPr.addprevious()`) 入れ、`body` の最後の子が `sectPr` であることを検算する。
- **続けて置いた `w:tbl` は Word が 1 つの表に結合する** (`end` で末尾に並べるとき)。表と表の間に空段落を挟み、末尾が表で
  終わるときは空段落を 1 つ足す (Word 自身も表の後に必ず空段落を書く)。

**番号の検算**: 題の無い画像があると「本文の図 N 件のうち M 件に題がありません」と警告し、`figures/FigureN` 以降が凡例と
ずれる範囲を示す (プレースホルダの数と集約した題の数を、番号ではなく配置で照らし合わせる)。

**提出マニフェスト `data/output/bhi/SUBMISSION.md`** — 画面のログが流れた後に残る、投稿のためのチェックリストである。

- ScholarOne のアップロード種別ごとのファイルの一覧・形式・大きさ。図は**書き出した順 (= 本文の初出順)** に並ぶ
  (図が 10 枚を超えても `Figure1 → Figure10 → Figure2` のような文字列順にならない。投稿系は上げた順に図番号を振るため)。
- COI / LTP のフォームのチェック項目 (§4.1)。
- **規定チェック** (要修正 / 参考) と、この実行で出た注意を全文転記する。`--no-validate` のときは省いたことを書く
  (節が無いことを「問題なし」と読ませないため)。
- 草稿や `--keep-figures` で作ったときは、冒頭に「このパッケージは提出用ではない」と出す。
- 動画の大きさは **10 進 (1 MB = 1,000,000 バイト)** で比べ、実際のバイト数を添える。上限を超えたものに印を付ける。
- 補足資料は `.DS_Store` などの管理用ファイルを除いて複製し、除いたことを報告する (補足資料は無変換で公開され、受理後に変えられないため)。
- 差分の docx は初回投稿では上げないと明記する。
- どの原稿 (入力ルート) から作ったかを 1 行書く。roundtrip が Drive の `submission-bhi/` へ届ける前に、今の入力ルートと照合する
  ([`docs/usage-guide.md`](usage-guide.md) §8.4)。

**Caption / Legend の貼り付け用 `data/output/bhi/CAPTIONS.md`** — 投稿系のファイルを上げる画面 (File Upload) は、上げたファイル
ごとに書式なしの Caption / Legend 欄を持つ。図表の題と凡例を手で写すと本文と食い違うので、**提出するファイルそのもの**
(`manuscript.docx` の Figure Legends 節と `tables/*.docx`) から抜き出し、表 → 図の順に 1 ファイル 1 項目で並べる。上付き・下付きは
Unicode の文字に置き換え、置き換えられない文字と斜体・太字は項目の下に注記する。`CAPTIONS.md` 自体はアップロードしない。

---

## 7. 原稿の骨格 (Title page 〜 Declarations)

BHI 用の原稿骨格は `data/journals/bhi/skeleton/` にある (§7.6)。下は骨格に組み込んだ規定の内訳である。節の順
(Original Article) は Title page → Abstract → **Abbreviations** → Introduction → Methods → Results → Discussion → Conclusion →
(Acknowledgments) → **Declarations** → References で、Figure Legends は `--mode final` が末尾へ移し、表は 1 表 1 ファイルに分ける。

### 7.1 Title page

- 題 — 簡潔で内容を表す。**30 語以内**。分野で一般的なもの以外の略語・数式・商品名を避ける。各語の頭文字だけを大文字にし、
  接続詞・冠詞・前置詞は先頭の語を除いて小文字。
- 著者 — フルネーム + **ORCID iD (あれば)**。学位・肩書は書かない。
- 所属 — 部門 + 機関 + 所在地 (市・州・国)。複数の機関は上付きの数字で対応づける。
- **連絡著者 (corresponding author) は 1 名だけ**で、氏名・住所の全文・電話・E-mail を書く。原稿では
  `custom-style="Corresponding"` の Div に 1 名分を書く (段落スタイルは reference.docx に入れてある)。規定チェックの連絡著者の
  検査はこの Div を見る (`lint.corresponding_author: true` の誌だけ)。

### 7.2 Keywords

3〜5 語。**MeSH** (MEDLINE のシソーラス) から採る。

### 7.3 Abbreviations

**Abstract と Introduction の間**に略語の一覧を置く。一覧で定義した略語は本文で使えるが、**図・表の凡例では改めて定義する**。

### 7.4 Declarations (全 6 項目)

| 項目 | 要点 |
|------|------|
| Funding | すべての資金源。資金提供者が研究デザイン・データ収集・解析・執筆に関わったかも書く。無ければ "The authors received no specific funding for this work." |
| Authors' contributions | **CRediT (14 ロール)** で著者ごとに書く。全著者が最終原稿を確認・承認し説明責任を負う旨も書く |
| Data availability statement | データのありかと入手の方法。公開できない場合の文例も規定にある |
| Ethics approval and consent to participate | 倫理委員会の名前と承認番号、同意の取得 (免除でも書く)。動物実験も同様。該当しなければ "Not applicable" |
| Consent for publication | 個人を特定しうるデータ・画像があるときの公表の同意。該当しなければ "Not applicable" |
| Competing interests | 金銭的・非金銭的なものすべて。無ければ "The authors declare that they have no competing interests." |

6 項目の中身は For Authors だけでは決まらない — Ethics approval / Data availability statement / Competing interests と Funding の
書き方は Editorial Policies も定めている (§14.5)。文例は `data/journals/bhi/skeleton/declarations.md`。

#### 7.4.1 Acknowledgments (任意。AI 使用の開示の置き場所)

規定の必須の節ではないが、骨格は Conclusion と Declarations の間に `# Acknowledgments` を置く。

- オーサーシップの 4 基準を満たさない貢献者は、Acknowledgments に書いてよい (Editorial Policies "Authorship"。§14.2)。
- **生成 AI ツールを使ったら開示が要る** (Editorial Policies "Use of AI tools"。§14.3)。規定は場所を指定していないので、本テンプレートは
  この節に置く (Declarations の 6 項目の構成を崩さないため)。文例と 5 要素は `skeleton/declarations.md` の AI 使用の節。
- **資金は書かない** (Funding に書く)。
- **本文語数に算入される** (除外の対象のどれにも当たらない)。規定チェックも本文語数に数える。
- 該当が無ければ節ごと消してよい (規定チェックは節の有無を見ない)。

### 7.5 その他の執筆規約

- **単位**: SI か SI 派生単位。臨床で慣用の単位 (mmHg など) は使ってよい。温度は**度記号 `°` + 大文字の `C`** で書き、合成済みの
  1 文字 `℃` を使わない (規定チェックが指摘する)。
- **機器・製品**: 型番 + 製造元 + 所在地 (市・州・国) を本文の括弧内に。統計ソフトは版も書く。
- **抄録**: 略語は最小限。**文献を引用しない** (規定チェックが指摘する)。
- **報告ガイドライン**: 研究デザインに応じたものに準拠する。基底は EQUATOR Network で、Editorial Policies の "Reporting guidelines" が
  名指ししているのは PRISMA / CONSORT-EHEALTH / CONSORT-AI・SPIRIT AI / STARE-HI / TRIPOD+AI (または TRIPOD) / SQUIRE / STROBE。
  チェックリストの提出が推奨と明記されているのは、系統的レビューの PRISMA (supplementary) だけである。
- **英語**: 米式か英式のどちらかに統一する。英語を母語としない著者は、投稿の前にネイティブチェックか英文校正を受ける
  (英語の不備は査読の前にリジェクトされうる)。**本誌の規定文書の綴りも一定しない**ので、誌に合わせても統一にはならない
  (§14.3 の綴りの注)。

### 7.6 図表の題と凡例の記法と骨格

| パス | 中身 |
|------|------|
| `data/journals/bhi/skeleton/main.md` | Original Article の記入式の雛形。`<<...>>` が記入欄。Title page (Title / Author / Affiliation / **Corresponding**) → Abstract (4 ラベル) → **Abbreviations** → … → Conclusion → Acknowledgments → **Declarations** (6 項目) → References |
| `data/journals/bhi/skeleton/cover-letter.md` | 規定の 4 点 (§8) を節ごとに置いた雛形 |
| `data/journals/bhi/skeleton/declarations.md` | Declarations 6 項目と AI 使用の開示の**文例集**。ビルドの対象ではない |
| `data/dummy/bhi/` | 骨格を埋めた**完結したサンプル** (`main.md` + `ref.bib` + `figs/` + `cover-letter.md` + `supplementary/`)。`--input data/dummy/bhi` でビルドする |

**図表の「題」と「凡例」を書き分ける記法**: **題 = キャプション / 凡例 = 直後の `custom-style="Legend"` Div**。
`for="fig:x"` で対応先を明示する (docx には出ない。規定チェックと読みやすさのため)。書き方の規約は `CLAUDE.md` の
「図表の題と凡例の書き分け」にある。

```markdown
![Processing pipeline from the record to the reviewed event list.](figs/fig-flow.svg){#fig:flow}

::: {custom-style="Legend" for="fig:flow"}
Rectangles denote processing stages. EHR, electronic health record.
:::
```

**なぜこの形か**:

- BHI は題 (15 語) と凡例 (300 語) に別々の上限を置くが、pandoc のキャプションは図にも表にも 1 本しか付けられない。
- **キャプションの先頭の 1 文を題とみなす方式は採らない** — pandoc-crossref が付ける `Figure 1: ` と切れ目が干渉し、`et al.` や
  `e.g.` のピリオドで題が切れる。
- **図と表で同じ方式にする** — 境界が明示的で、docx でも段落スタイルとして残るので、提出構成の組み替え (§6.1) と 4 つの語数検査
  (§7.7) を図と表で同じ仕組みに載せられる。
- **クラス (`.legend`) ではなく `custom-style` にする** — クラスだけの Div は pandoc の docx 出力で段落スタイルにならず、
  docx から凡例を特定できない。
- キャプションの中に区切り記号を置いて題と凡例を分ける方式は、区切り記号を忘れたときに黙って壊れるので採らない。

**語数の数え方**: 題は執筆者が書いたキャプションだけ (`Figure 1: ` は含めない)。凡例は Div の中身。

**docx の側の受け皿**: `patch_reference_docx.py` がすべての reference.docx に段落スタイル `Legend` を入れる (`basedOn=Normal`)。
誌に依らない構造の要素なので `_default` にも入れる (`Corresponding` も同じ)。docx では、表は「題 (`TableCaption`) → 表 → 凡例
(`Legend`)」、図は「画像 (`CaptionedFigure`) → 題 (`ImageCaption`) → 凡例 (`Legend`)」の順になる。

**全領域差分も通る**: 凡例の 1 語だけを変えた 2 版を比べると、その `Legend` 段落が語単位で色分けされる (custom-style の Div は
差分の経路で温存され、中身が差分の対象になる。[`docs/design-fullarea-diff.md`](design-fullarea-diff.md))。

**凡例の段落と移設の単位**: 凡例の Div の中で段落を分けると `Legend` 段落が複数になる (凡例は 300 語まで認められるので段落を
分けたくなる長さである)。提出構成の組み替えは「直後に**続く** `Legend` 段落すべて」を 1 組で動かす。1 段落だけを動かすと
2 段落目が本文に取り残され、本文と見た目が変わらないので校正刷りまで気づけない。

### 7.7 記事種別ごとの上限と BHI の lint (規定チェック)

`main/step05_package/validate.py` が、Markdown の原稿と解決した `profile.yaml` から語数・点数を数え、規定に外れていそうな点を
**「規定違反の可能性 (要修正)」と「参考情報」**に分けて出す。**エラーにはしない** (終了コード 0)。`package.sh` の最後に自動で
走り、単独でも回せる。

```bash
docker compose -f docker/docker-compose.yml run --rm -u "$(id -u):$(id -g)" pandoc \
    python3 main/step05_package/validate.py --input-root data/dummy/bhi --journal bhi --article-type original
```

**判断 1 — 表の凡例も本文語数から除外する**

規定が本文語数から除くのは「表・図 / 文献 / 図のキャプション」+ 抄録 + Abbreviations で、**表の凡例は明示されていない**。
次の 3 点から、図と同じく除くことにした。

1. 規定は表の題を「表の上」・凡例を「表の下」と定めており、題も凡例も表という提出物の一部として書かれている。除外の対象の
   「表」に題と凡例が含まれると読むのが素直である。
2. 図のキャプションが明示的に除かれている以上、図と表で扱いを変える根拠が規定に無い。
3. 図と表の凡例は同じ `Legend` 段落スタイルなので、算入と除外を分けると、語数の計算そのものが「直前が図か表か」の判定に頼る
   ことになる。その判定は配置の規則が守られている前提に立つので、規則に外れた原稿で語数が黙ってずれる。

除外は費用の見積もりを**甘くする側**に効く (超過ページは 1 ページ 20,000 円 + 税)。そこで**除いた語数を図と表に分けて
概算の行に必ず出す** — 編集室の数え方が違ったときに足し戻せるようにするためである。

```
  概算: 本文 1147 語 / 抄録 263 語 / 文献 3 件 / 図 2 点・表 1 点
        本文語数から除外した凡例: 図の凡例 163 / 表の凡例 41 語 (合計 204 語)
```

**配置の規則に外れた凡例 (直前に図表が無いもの) は算入する**。この凡例は集約から漏れて提出物の本文に残るので、語数も実態に
合わせる (算入したことは概算の行に 1 行出し、配置の規則の違反として要修正にも出す)。連絡著者のブロック (`Corresponding` Div) は
Title page の一部なので本文語数から除く。

**判断 2 — 一般的な作法の lint は雑誌プロファイルではなく基底に置く**

合成文字の禁止と SI 単位は欧文組版と医学系の誌の一般則で、記入欄 `<<...>>` の残りと凡例の配置の検査は本テンプレートの記法の
規約である。BHI のプロファイルにだけ置くと、同じ原稿を別の誌でパッケージしたときに検査が消える。そこで
`journal_profile.DEFAULTS` に既定値を置き、誌の側は上書きと追加だけにした。

| キー | 置いた層 | 既定 | 理由 |
|------|---------|------|------|
| `lint.forbid_chars` | 基底 | 合成文字 11 種 | 欧文組版の一般則 |
| `lint.units` | 基底 | `SI` | 医学系の誌の一般則 |
| `lint.placeholder_markers` | 基底 | `true` | 骨格の規約 |
| `lint.legend_placement` | 基底 | `true` | 題と凡例の記法の規約 |
| `lint.device_notation` | 誌ごと | `false` | 記載の様式は誌による差が大きい |
| `lint.corresponding_author` | 誌ごと | `false` | `Corresponding` Div を持たない誌で誤って出るため |
| `lint.langid_japanese_only` | 誌ごと | `false` | `langid` の扱いは引用様式による (`bhi.csl` は `langid` があるだけで `(in Japanese)` を付ける) |

禁止する文字の集合は「基底 ∪ 誌」で解決する (誌が一覧を書いても基底の検査を弱められない)。キーの一覧は
[`docs/profile-schema.md`](profile-schema.md) §5。

**判断 3 — 機械で判定できないものは、狭い検査にするか実装しない**

- `lint.units: SI` は英米の慣用単位 (`°F` / `inch` / `lb` / `oz` / `mile` / `gallon`) の綴りを拾うだけの狭い検出器にした。SI に準拠して
  いる証明にはならないので参考情報で出す。固有名詞を拾わないよう大文字小文字を区別する。
- `lint.device_notation` は機器一般を文面から判定できないので、規定が特に「版も」と書いている**統計ソフト**に絞った (綴りが一意な
  ソフトについて、版と括弧の中の製造元があるか)。
- `figures.keys_in_graphic` / `figures.multipanel_single_file` は**実装しない**。画像ファイルの中身への要求で、Markdown にも docx にも
  判定の材料が無い。`profile.yaml` と執筆規約に書くだけにしてある。

**検査の一覧** (BHI でのもの。要修正 / 参考の区分つき):

- タイトルの語数と略語 / キーワードの数 / 抄録の語数・構造 (4 ラベル)・抄録の中の引用 / 本文語数 / 図表の合計点数 /
  図表の題 (15 語)・凡例 (300 語) の語数
- Declarations の 6 項目 / Abbreviations の節の位置 / References が本文の最後の節か / 連絡著者のブロック
- 合成文字 (`℃` など) / 数値の桁区切りのカンマ / 記入欄 `<<...>>` の残り / 英米の慣用単位 / 統計ソフトの版の書き方
- **凡例の Div**: `for` が実在する図表を指すか・直前の図表と一致するか (欠落は参考) / 直前に図表があるか / **中身が段落だけか**

**Markdown の層に「ブロックの走査」を置いた理由**: 多くの検査は「凡例の Div の直前が図か表か」「Abbreviations が Abstract と
Introduction の間にあるか」のような**文書順の位置関係**を見る。行ごとの正規表現では位置関係を持てないので、原稿を文書順の
ブロックの列にならす `scan_blocks()` を置いた。

- **構造の Div (`.textbox` / `.grid` / `#refs`) の中には入り、custom-style の Div の中には入らない**。テキストボックスの中のブロックには
  印を付け、**図表の点数に数えない** (本文の流れの外にあり、表の移設・凡例の集約の対象からも外れるため)。外れた点数は概算の行に必ず出し、
  `limits.figures_tables` を持つ誌では要修正として指摘する。`.grid` の中の表は数える。
- **表のキャプションの行は、隣の表に畳む** (pandoc は `: 題 {#tbl:x}` を表の前にも後にも書けるので、畳まないと判定がキャプションの
  位置で変わる)。
- **テキストボックスの内と外をまたいで凡例を結びつけない** (箱を閉じた直後の凡例を箱の中の図に結びつけると、集約されずに本文に
  残るのに指摘が出なくなる)。

**凡例の中身の検査** — 箇条書き / 番号つきリスト / 表 (pipe table・simple table・grid table) / 画像の段落 / 見出し / 引用ブロック /
入れ子の Div / コードブロック (` ``` ` / `~~~` / 空行の後の 4 個以上の空白の字下げ) / 定義リスト / 水平線、の 11 種を見る。
どれも docx で `Legend` の外の段落・表・図になるので、そこで集約が止まり、以降が本文に取り残される (表は題の無い表として末尾へ
移される)。先頭が `|` の 1 行 (行ブロック) と脚注の定義は docx でも `Legend` 段落のまま並ぶので指摘しない。判定は pandoc の読み方に合わせてあり、**pandoc が新しいブロックを
始める位置** (凡例の 1 行目と空行の直後) だけを見る。そのつもりがなくても書けてしまうのは次の 3 つである。

- **凡例を `(A)` や `a.` で始める** — pandoc は段落の先頭の `(A)` / `A)` / `a.` / `(i)` / `IV.` なども番号つきリストとして読む。
  パネルの説明は `Panel A shows … Panel B shows …` のように文で書く (大文字 1 字 + ピリオド + 空白 1 個の `A. Smith` は、頭文字と
  区別するためリストにならない)。
- **空行の後を 4 個以上の空白で字下げする** — コードブロックになる (折り返した続きの行の字下げは段落に吸収されるので問題ない)。
- **定義リスト** — 「凡例で略語を改めて定義する」という規定の要求を素直に書くと出てくる形である。略語の再定義は普通の文で書く
  (`EHR, electronic health record; ICU, intensive care unit.`)。

**記入欄 `<<...>>` は Markdown の層で捕まえるしかない**: pandoc は記入欄を中身によって 3 通りに扱う。

| pandoc の扱い | 条件 | 例 |
|------|------|-----|
| そのまま残る | 中身にカンマ・日本語がある、先頭が数字 | `<<Title of the Manuscript in Title Case, Not Exceeding 30 Words>>` |
| **中身が消えて `<>` だけが残る** | 中身が HTML のタグとして読める | `<<Given-name Family-name>>` → `<>` |
| メールのリンクになる | 中身がメールアドレスの形 | `<<` + アドレス + `>>` → `<` + アドレス + `>` |

2 つ目は著者名・所属・連絡著者の欄が当たり、docx を通して読んでも組版のごみに見えるので書き忘れに気づけない。そこで記入欄は
改行をまたぐものも含めて全文で探し、`main.md` に加えて `cover-letter.md` / `revise-report.md` も見る (カバーレターも編集部に届く
提出物であるため)。

**受入フィクスチャ**:

| フィクスチャ | 中身 | 期待する結果 |
|---|---|---|
| `data/dummy/bhi/` | 適合する原稿 | 要修正 0 件・参考 0 件 |
| `data/dummy/bhi-lint/` | **不適合の原稿** (違反を 26 種仕込んである。対応表は main.md の冒頭のコメント) | 要修正 23 件 + 参考 4 件 |

本文語数の超過だけは仕込んでいない (4,000 語の散文を置いて保つ手間に見合わないため)。記事種別による上限の切り替えは、適合の原稿に
`--article-type letter` を当てて「図表 3 点 > 上限 1 点」が出ることで確かめる。

---

## 8. カバーレター

次の 4 点を含めることが推奨されている (`data/journals/bhi/skeleton/cover-letter.md` に雛形がある)。

1. なぜ本稿が BHI に掲載されるべきか
2. 雑誌のポリシーに関わる論点があればその説明
3. 潜在的な競合利益の申告
4. 未発表で、他誌へ同時に投稿していないことの確認

**関連する原稿の開示もここに書く**。Editorial Policies "Originality" は、関連する原稿が他所で審査中・印刷中・公開済みなら編集者に
知らせることを義務にしている (§14.1)。学会の抄録やプレプリントとの関係は、剽窃のスクリーニングが人の判断より前に走ることを
見込んで、**重複の範囲まで**書いておくのが安全である。招待や推薦を受けて投稿するなら、その旨と元の発表との関係も書く。

---

## 9. profile.yaml

実物は `data/journals/bhi/profile.yaml` で、各キーの横に規定の該当箇所と確度 (確度高 = 規定の文面どおり / 確度中 = 設計判断 /
確度低 = 規定に無く既定を継承) を書いてある。キーの意味・既定値・読み手のモジュールは [`docs/profile-schema.md`](profile-schema.md)。

| 群 | BHI での主な値 |
|---|---|
| 体裁 | `line_spacing: double` / `font_size: 12pt` / `margins: 25.4mm` / `paper_size: a4` / `line_numbers: continuous` / `line_numbers_scope: manuscript` / `page_numbers: true` / `text_styles: {uniform_size: true, heading_color: black, uniform_line_spacing: true}` |
| 引用 | `csl: bhi.csl` |
| 記事種別 | `article_type: original` + `article_types` の 8 種 (§1) |
| 図 | `formats: [pptx, png, tif]` / `dpi: 300` / `pptx.*` (§5.1.6) / `legends_section: "Figure Legends"` / `title_words: 15` / `legend_words: 300` |
| 表 | `placement: separate` / `section_title: null` / `allow_color: false` / `thousands_separator: false` / `title_words: 15` / `legend_words: 300` |
| 上限 | `title_words: 30` / `keywords: [3, 5]` / `video_mb: 50` |
| 抄録・Declarations | `abstract.citations_allowed: false` / `declarations.required` (6 項目) / `declarations.abbreviations_section: true` |
| 提出物 | `submission.text_formats` / `table_formats` / `figure_formats: [jpeg, tif, png, pptx]` / `video_formats` / `forms` / `supplementary: as-is` |
| lint | `forbid_chars` / `units: SI` / `device_notation: true` / `corresponding_author: true` / `langid_japanese_only: true` |

記事種別に由来する値 (語数・抄録・図表点数) は `article_types` にだけ持ち、`limits` に写さない (同じ値を 2 か所に書かない)。
解決は `main/00_setup/lib/journal_profile.py` の `resolve()` が行う。

---

## 10. 規定と実装の対応一覧

規定の要求のうち、実装が要ったものの一覧である (番号はコードのコメントからも参照される)。

| # | 要求 | 実装 | 確かめ方 | 節 |
|---|---------|------|------|-----|
| G1 | 専用の引用様式 (上付きの `1)` / 先頭 3 名 + et al / 誌名は立体 / 終了ページの短縮) | `data/journals/bhi/bhi.csl` | `bash scripts/check-csl.sh [--docx]` | §3 |
| G2 | ページ番号 | `page_numbers: true` → フッタの `PAGE` フィールド (`patch_reference_docx.py --page-numbers`) | Word の PDF のフッタ (§12) | §2.1 |
| G3 | 表を本文の末尾か別のファイルに置く | `tables.placement: separate` (`end` も選べる) → `relocate.py` + `package.py` の `write_table_files()` | `manuscript.docx` に表が無いこと・`tables/TableN.docx` / Word の PDF | §6.1 |
| G4 | 図の題と凡例を References の後の新しいページにまとめる | `figures.legends_section` → `relocate.py` | 同上 | §6.1 |
| G5 | 300 dpi 以上 | `svg_raster.py` (公称サイズ → 画素数 → 検算 → pHYs) | `bash scripts/check-figures.sh` | §5.2 |
| G6 | TIFF | **用意していない** (`--format tiff` は PNG で代わりに出し、毎回警告する) | — | §5.2 |
| G7 | 記事種別ごとの上限 | `article_types` + `--article-type` → 規定チェック | `--article-type letter` で上限が切り替わる | §1 / §7.7 |
| G8 | Title page / Abbreviations / Declarations の骨格 | `data/journals/bhi/skeleton/` | `data/dummy/bhi/` がビルドでき、規定チェックが 0 件 | §7.6 |
| G9 | BHI 固有の lint (題の語数 / キーワード / `℃` / 桁区切り / 抄録の引用 など) | `validate.py` | 不適合フィクスチャ `data/dummy/bhi-lint/` | §7.7 |
| G10 | アップロード種別ごとの提出物の一覧 | `SUBMISSION.md` | — | §6.1 |
| G11 | 補足資料と動画 | `<入力ルート>/supplementary/` の無変換の複製 + `limits.video_mb` | `SUBMISSION.md` | §4 / §6.1 |
| G12 | ベクターの図 (受入形式では PowerPoint だけ) | 案 B (`svg_pptx.py`) + 案 A (図の隣の pptx) | `bash scripts/check-figures.sh --figures-dir <dir>` | §5.1 / §5.3 |
| G13 | 図表の題と凡例の語数の別々の上限 | 題 = キャプション / 凡例 = Legend Div + `Legend` 段落スタイル | 規定チェック | §7.6 |

G6 を除くすべての要求に実装がある。G6 は意図して用意していない (§5.2。TIFF しか受け付けない誌に出すときに考え直す)。

---

## 11. 規定に明記が無い点と、本テンプレートの扱い

公開されている規定の文面だけでは一意に決まらない点の扱いである。**規定は変わりうるので、気になる点は投稿前に
編集事務局に確かめること**。

**公開資料で裏付けられること**

| 論点 | 公開資料 | 本テンプレートへの反映 |
|---|---|---|
| ページの範囲の書式 | 終了ページは短縮形 (For Authors の References の出力例 2 の `1813–97`) | `minimal-two` (§3) |
| 受け付ける図の形式 | JPEG / TIF / PNG / PowerPoint (For Authors の Manuscript Submission)。SVG / PDF / EPS は挙がっていない | pptx を主経路にし、PNG への退避を残す (§5.1) |
| 刷り上がりページの上限 | About ページの Table 1。Original Article は 9 typeset pages | 検査しない (組版の後にしか分からない)。§1 の末尾 |
| COI / LTP のフォームの通数 | COI は連絡著者が全共著者の申告を 1 通にまとめる (For Authors の Competing interests)。LTP は連絡著者が全共著者を代表して結ぶ (License to Publish の様式) | `submission.forms` の注記 (§4.1) |

**公開資料で分かること**: 投稿料・掲載料は無く、刷り上がりが上限を超えたら 1 ページ 20,000 円 (税別)、ライセンスは CC BY 4.0
(About ページ)。報告ガイドラインの実体は Editorial Policies の "Reporting guidelines" (§7.5)。

**規定に定めが無く、本テンプレートが決めたこと**

- 本文語数から、規定が挙げる表・図 / 文献 / 図のキャプションに加えて抄録と Abbreviations を除き、Declarations は数える (§1)。
  表の凡例も除く (§7.7 判断 1)。Acknowledgments は本文語数に数える (§7.4.1)。
- 引用番号は `1)` を丸ごと上付きにする。規定は "superscript Arabic numerals in closing parenthesis" で、閉じ括弧まで
  上付きかは文面からは決まらない (§3)。
- PowerPoint の図は編集できる図形でなくてよいとみなし、ベクターの図を pptx (SVG と 300 dpi の PNG を同梱) で出す。
  画像の図は pptx に包まず、画像のファイルのまま出す (§5.1)。
- 複数引用・locator・DOI・号の書式 (§3.2)。MEDLINE に収載されていない誌の略誌名と、和文の法令の書き方 (§3.2)。
- 表は本文の末尾ではなく別のファイルにする (規定はどちらも認める。§6)。末尾に移す (`end`) ときも表の前に見出しを置かない (§6.1)。
- 題・見出しの色を黒 (自動色) にする (規定に色の定めは無い。§2)。
- 生成 AI の使用の開示を Acknowledgments に置き、版も書く (§14.3。版は規定の要求ではなく本テンプレートの上乗せ)。

**規定に定めが無く、投稿者が判断すること**

- **招待原稿の超過ページ料金の免除の範囲** — About ページに "Invited manuscripts are exempt from excess page fees." とあるが、何が
  招待原稿に当たるか (編集委員会からの依頼だけか、学会などの推薦や案内を受けた原稿も含むか) の定義が無い。費用だけの問題で、
  体裁には影響しない。招待・推薦を受けて投稿し、刷り上がりが上限を超えそうなら編集事務局に確かめる価値がある。
- **査読対応のときに差分の原稿 (マークアップ版) を出すか** — For Authors は初回投稿の規定だけを扱い、リバイスの手順に触れていない。
  `scripts/diff.sh` で全領域の差分 docx をいつでも作れるので、求められたら出せばよい。ただし BHI は表の色・網掛けを禁じているので、
  **色で差分を示した版を本体として出してはならない** (本体はクリーンな版)。
- **招待・推薦による投稿の案内に条件があるとき** — 案内の文面に規定と違う条件 (締切・記事種別の指定・語数の緩和) が書かれていれば、
  どちらに従うかを編集事務局に確かめる (規定に案内による投稿の記述が無く、どちらが優先するかは決まっていない)。無ければ規定どおりに作る。カバーレターに招待・推薦である旨と元の発表との関係を書く (§8)。

---

## 12. 通し検証で確かめていること

BHI のプロファイルで build → diff → package (final) → roundtrip (Windows の Word の COM 変換) を通し、Word が返した PDF を機械で
測ると、動作例 `data/dummy/bhi/` では次の値になる (手順は [`docs/usage-guide.md`](usage-guide.md) §8.4。PDF の測り方は
[`docs/roundtrip-windows-watcher.md`](roundtrip-windows-watcher.md) の「PDF の確かめ方」)。体裁を変えたときや、Word の版が
変わったときの「こう出れば正常」の基準に使う。

**Word が返した PDF** (`bhi-manuscript.pdf`。`Microsoft Word for Microsoft 365` (16.0 系) で変換):

| 項目 | 値 |
|------|------|
| ページ数 | 10 |
| 用紙 | 210.0 × 297.0 mm (A4) |
| 左余白 (本文の最小の x) | 25.4 mm (= 72.0 pt) |
| 本文の書体 / 大きさ | Times New Roman / 12.0 pt (題・見出し・抄録も 12.0 pt。12 pt でない字は上付きの引用の 8 pt だけ) |
| 行送り (最頻値) | 27.6 pt (= ダブルスペース) |
| 題と著者の行送り | 題 (12 pt・太字。2 行) 27.7 pt・著者 27.6 pt (本文と同じダブルスペース) |
| 行番号 | 1〜172 が連続 (欠番なし・重なりなし)。字は本文の左の x = 36.0〜48.0 pt |
| フッタのページ番号 | 1〜10 (中央) |
| 節の並び | p1 Title page → p2 Abstract → p3 Abbreviations・Introduction → p4 Methods → p5 Results → p6 Discussion → p7 Conclusion・Acknowledgements・Declarations → p8〜p9 References → **p10 Figure Legends** (表は本文に無い) |
| 表ファイル (`bhi-Table1.pdf`) | 1 ページ・題が上・表・凡例が下・**行番号 0 個**・フッタ 1 (`line_numbers_scope: manuscript`) |
| 上付きの引用 | `1)` `2)` `3)` (p3) / `2)` `3)` (p6) の 5 件。閉じ括弧も同じ上付きの run |
| 画像オブジェクト | 0 個 (図を含む草稿の `main.pdf` でも 0 個 = SVG の側がベクターで描かれている) |
| `cover-letter.pdf` | 2 ページ・**行番号 0 個**・フッタ 1〜2 (`line_numbers_scope: manuscript`) |
| 草稿 `main.pdf` | 10 ページ・行番号 1〜174・図 2 枚はベクター (画像オブジェクト 0 個) |
| 相互参照 | 本文の "Fig. 1" / "Table 1" などのリンクが `[Figure N about here]` / `[Table N about here]` の位置に着地する |

これは**原稿の PDF のページ数であって、刷り上がり (組版の後) のページ数ではない**。§1 の末尾の上限 (9 typeset pages) とは比べられない。

**動作例とは別の入力で確かめたこと**: `tables.placement: end` で末尾に移した表が 2 つ続く原稿 (題の無い表と題つきの表) では、Word で 2 つの表が
結合せず、別々の列のグリッドで描かれた (移設の際に表と表の間へ空段落を挟むため)。動作例 `data/dummy/bhi/` の表は 1 つだけなので、
この点は動作例の PDF では確かめられない。確かめるときは、`tables.placement: end` にして表を 2 つ以上持つ原稿で `--mode final` を回し、Word で開く。

**Markdown の層** (規定チェックの概算の行):

| フィクスチャ | 本文 | 抄録 | 文献 | 図表 | 除いた凡例 | 指摘 |
|------------|-----|-----|-----|-----|------------|-----|
| `data/dummy/bhi/` (適合) | 1147 語 | 263 語 | 3 件 | 図 2・表 1 | 図 163 / 表 41 = 204 語 | 要修正 0 / 参考 0 |
| `data/dummy/bhi-lint/` (不適合) | 260 語 | 53 語 | 3 件 | 図 8・表 1 | 図 370 / 表 304 = 674 語 (+ 対応の取れない 24 語は算入) | 要修正 23 / 参考 4 |
| `data/dummy/bhi-csl/` | — | — | 9 件 | — | — | 全件が期待値と一致 / docx の上付き 16 件 |

**通しの実行では触れない系統**は個別に確かめる — 記事種別の切り替え (`--article-type`)・引用様式 (`check-csl.sh`)・不適合フィクスチャ・
解像度の停止の条件・`--format tiff` の代替・`text_to_path: true`・案 A の pptx・受入形式の外の形式の停止 (§5.2 の表)。

---

## 13. 既知の制限と確かめていないこと

- **代替表示の PNG が描かれる環境での見え方を確かめていない。** 買い切り版の Office 2016 では PNG の側が描かれ、投稿系の
  査読用の PDF 変換でも、SVG の拡張を解釈する保証が無いので PNG の側が描かれうる (§5.1.3 リスク 1。投稿系がどちらを描くかは
  確かめていない)。確かめた LibreOffice・Microsoft 365 の PowerPoint・Word はどれも SVG の側を描いた。同梱した PNG が
  300 dpi であることは受入テストが保証しているが、それが表示されたときの見え方は投稿後の校正刷りで見ることになる。
- **ScholarOne の実際の画面のアップロード種別と照らし合わせていない。** `SUBMISSION.md` の種別は For Authors の記述から作っている。
  投稿のアカウントを作ったら画面を見て、食い違えば `profile.yaml` の `submission` を直す。転載許諾の写しをどの種別で出すかも画面で確かめる (§14.4)。
- **刷り上がりのページ数は検査しない** (組版の後にしか分からない。§1)。
- **画像ファイルの中身への要求は検査しない** — 多パネル図の合成・凡例キーを画像の中に入れること・余白の切り詰め・向き (§5)。
- **案 A の pptx の中身は検査しない** (スライドの数とマクロだけを見る。§5.1.2)。
- **TIFF をそのまま作る経路と、案 B′ (ネイティブのシェイプへの変換) は無い** (§5.2 / §5.1.4)。
- **コンテナの LibreOffice で数えたページ数は Word と違う** (フォントの差。§2.1)。ページ数は Word の PDF で見る。
- **規定は変わりうる**。本文書の読み取りは 2026-11 時点の公開ページに基づく。

---

## 14. Editorial Policies (投稿規定とは別の文書)

**一次資料**: <https://biohealth-informatics.com/editorial-policies/>

For Authors が「原稿の形」を定めるのに対し、Editorial Policies は**「投稿してよい原稿か」**を定める。体裁を自動化しても担保できないので、
この節の内容はほとんどが [`docs/bhi-submission-checklist.md`](bhi-submission-checklist.md) の 👁 (人が目で見る) の側に落ちる (§14.7)。

### 14.0 節の番号

ページの見出しには番号が印字されていない。本文書の `#NN` は**ページ内のアンカー (`#01`〜`#15`) の番号**で、冒頭の導入部が `#01` なので
見出しを目で数えた番号より 1 つ大きい (Reporting guidelines は 4 つ目の節だが `#05`)。

| アンカー | 節 | 投稿への効き方 |
|---------|----|--------------|
| `#01` | (導入部) | 投稿は、全著者が承認し、事実であることを保証し、公表する権利を持つことを意味する |
| **`#02`** | **Originality** | 剽窃のスクリーニング / **関連する原稿の開示の義務** → §14.1 |
| `#03` | Research ethics | ヘルシンキ宣言 / 委員会の名前と番号 / 同意の免除の説明 → §14.5 |
| `#04` | Clinical trial registration | 臨床試験は登録が投稿の条件 → §14.5 |
| `#05` | Reporting guidelines | EQUATOR Network と 7 つのガイドライン → §7.5 |
| `#06` | Data Availability | Data Availability Statement は全実証研究で必須 → §14.5 |
| **`#07`** | **Authorship** | ICMJE の 4 基準 / 共同筆頭は 2 名まで / **受理後は変えられない** → §14.2 |
| `#08` | Data falsification, data fabrication and image integrity | 画像の加工は最小限に。編集者は未加工の原画像を求めることができる → §14.5 |
| **`#09`** | **Use of AI tools** | **生成 AI の使用の開示の義務** → §14.3 |
| **`#10`** | **Reproducing copyrighted material** | **転載許諾の写しを初回投稿のときに添える** → §14.4 |
| `#11` | Author conflicts of interest | ICMJE に準拠 / 資金は Funding に → §14.5 |
| `#12` | Confidentiality | 編集室・編集者・査読者とのやりとりを秘匿する義務 → §14.5 |
| **`#13`** | **Preprints** | プレプリントは先行公開に当たらない → §14.6 |
| `#14` | Self-archiving (Green Open Access) policy | 掲載後の機関リポジトリへの登録を推奨 |
| `#15` | Long-term digital archiving | J-STAGE + Portico による長期保存 |

### 14.1 `#02` Originality — 剽窃のスクリーニングと関連する原稿の開示

- 既発表 (**言語を問わず、一部でも全部でも**)・印刷中・他誌で審査中の原稿は投稿できない。
- **Crossref Similarity Check で剽窃をスクリーニングする**。投稿はスクリーニングへの同意とみなされ、許容できない水準なら編集長の裁量で
  リジェクトまたは撤回される。
- **関連する原稿が他所で審査中・印刷中・公開済みなら、編集者に知らせなければならない** ("Authors must inform the editors if any related
  manuscripts are under consideration, in press or published elsewhere.")。
- プレプリントサーバでの公開は先行公開に当たらない。
- 決定の前に他誌へ出すなら、先に本誌から取り下げる。

**自分の先行公開と重なる原稿は類似度が高く出る**。学会の抄録・詳細な抄録・プレプリントを元にした原稿は、剽窃ではなく自分の先行公開との
一致だが、機械のスクリーニングは人の判断より前に走る。カバーレターで関連する原稿を開示するときは**重複の範囲まで**書く (§8)。
学会の抄録や発表の扱いは、この節に明記が無い。

### 14.2 `#07` Authorship — 受理後は連絡著者を変えられない

- 投稿は、**全著者が著者のリストを見て承認した**ことを意味する。
- **ICMJE の 4 基準** (構想・設計またはデータの取得・解析・解釈への実質的な貢献 / 起草または重要な知的内容の批判的な改訂 / 最終版の承認 /
  説明責任) に基づく。
- 共同筆頭著者は原則 2 名まで (対等な貢献を原稿の中に明示する)。
- 投稿の後の著者のリストの変更 (追加・削除・順序) は、全著者と編集者の承認が要る。
- **受理の後は、著者の追加・削除・連絡著者の変更・著者の順序の変更のいずれも認められない** ("…are not permitted after acceptance of a
  manuscript.")。**連絡著者は投稿の前に確定させる。**
- 4 基準を満たさない貢献者は著者にすべきではないが、**代わりに Acknowledgments に書いてもよい** ("may be included in the Acknowledgments
  section instead" = 任意)。骨格の Acknowledgments の節の根拠である (§7.4.1)。
- **AI ツールは著者になれない** (4 基準を満たせないため。この一文は AI の節ではなく、この節の最後にある)。

### 14.3 `#09` Use of Artificial Intelligence (AI) tools — 開示の義務

要点 (正本は公式ページ):

1. 生成 AI の使用は**原稿の適切な箇所で開示しなければならない** (COPE の指針に準拠。"in a suitable part of the manuscript")。対象はデータの
   収集・解析、画像の生成・改変、**原稿の全部または一部の執筆**。
2. **どのツールを使い、どう使ったかを書かなければならない** ("Authors must describe which tools they used and how the tools were used.")。
3. 許されるのは原則として**研究デザイン・方法に不可欠な場合**で、それ以外は個別に審査される (case-by-case)。
4. **いかなる場合も、著者は提出した原稿の全内容に責任を負い続ける** ("In all cases, authors remain responsible for all the content of
   their submitted manuscript.")。
5. AI が生成した内容の著作権には懸念が続いていることを認識し、"Reproducing copyrighted material" (§14.4) に従う。
6. スペルや文法の確認のような可読性の改善は許される。ただし **AI で整えた後も、最終原稿をネイティブスピーカーが確認することが求められる**。
7. 査読者・編集者は未公開の原稿を AI ツールにアップロードしてはならない (著者の側の義務ではない)。

**開示の置き場所は規定が指定していない**。本テンプレートは独立した `# Acknowledgments` の節 (Conclusion と Declarations の間) に置く
(§14.2 で Acknowledgments の節に言及があり、Declarations の 6 項目の構成を崩さずに済むため)。文例は
`data/journals/bhi/skeleton/declarations.md` の AI 使用の節。

**開示の 5 要素** (骨格と文例集が使う番号):

| # | 要素 | 規定の要求か |
|---|------|------------|
| 1 | ツールの名前 | 要求 (上の 2) |
| 2 | **版** | **規定の要求ではない (本テンプレートの上乗せ)**。同じ名前の道具でも版で挙動が変わるので、版まで書いて特定する。他誌に出し直すときに、何が規定に由来し何が上乗せかを見分けられるよう区別してある |
| 3 | 使途 (何にどう使ったか) | 要求 (上の 2) |
| 4 | 著者が提出原稿の全内容に責任を負う旨 | 要求 (上の 4) |
| 5 | AI で整えた後もネイティブスピーカーが最終原稿を確認した旨 | 要求 (上の 6) |

- 「原稿の構成の補助」のような使い方は文法の確認の範囲を超えるので、規定の上では個別の審査の側に落ちる。規定が求めるとおりに書いた結果で
  あって避けるべきものではないが、投稿の後に説明を求められる可能性は見込んでおく。英文校正を受けたなら、その事実を同じ段落に書くと
  要素 5 に答えた形になる。
- **版は実際に使ったものを書く**。執筆が長くなると途中で道具や版が変わるので、作業中は使った道具と版を **git で追跡している作業記録の
  ファイル**に書き足し、投稿の直前に開示の文と突き合わせる (commit のたびに消える一時ファイルには書かない)。

**綴りの注 — 米式か英式のどちらかに統一する。誌に合わせても決まらない**: 規定 (For Authors の English standards) が求めるのは「どちらかに統一」
だけで、どちらを採るかは投稿ごとに決める。本誌の規定文書の綴りも一定しない (Editorial Policies は `analyse` (英式) と `Acknowledgments`
(米式)、For Authors は `analysed` (英式))。

- 骨格の節の名前は本誌の用例に合わせて `Acknowledgments` (米式)。英式で書く原稿は `Acknowledgements` に直す。
- `skeleton/declarations.md` の文例は英式の `analysed` / `analyse` を使う。米式で書く原稿は `analyzed` / `analyze` に直す。
- 動作例 `data/dummy/bhi/` は英式で書いてある (`randomised` / `labelled` など) ので、節の名前も `Acknowledgements` にしてある。
  英文校正に出すときは、どちらで統一するかを頼むときに指示する。

### 14.4 `#10` Reproducing copyrighted material — 転載許諾の写しを初回投稿のときに添える

- 著者自身の著作権の下にない素材を含むなら、**権利者から転載の許諾を得なければならない**。
- 既発表の素材なら、**権利者と原著の出版社の両方**から許諾を得る。原著を本文で引用する。
- **すべての転載許諾の写しを、初回投稿のときに原稿に添えなければならない** ("Copies of all reproduction permissions must be included with
  the manuscript when it is first submitted.")。投稿の後に集めればよいものではない。許諾には日数がかかるので、投稿の 2〜4 週間前の作業になる。
- License to Publish の保証の条項にも同じ要求がある (§4.1)。
- ScholarOne のどのアップロード種別で写しを出すかは、実際の画面で確かめる (§13)。

### 14.5 Declarations と図に効くその他の節

| 節 | 要求 | 効く先 |
|----|----------|-------|
| `#03` Research ethics | ヘルシンキ宣言と所属機関の指針に従ったことを示し、**倫理委員会の名前と (該当すれば) 承認番号を書く**。同意の取得の手続きを述べるか、**免除ならその説明を書く** (匿名化したデータを使う研究が例に挙がっている) | Declarations > Ethics approval and consent to participate。**同意を免除された研究も免除の説明が要る** |
| `#04` Clinical trial registration | 臨床試験は最初の患者を登録する時点までに公的な登録が要る (投稿の条件)。**登録番号と登録先の名前を原稿に書く** | 臨床試験の原稿だけ |
| `#06` Data Availability | **全実証研究で Data Availability Statement が必須**。公開ならアクセッション番号か DOI。査読中は編集者・査読者の求めに応じてデータを出す義務があり、法的・倫理的・契約上の制約で出せないなら**その制約を書く** | Declarations > Data availability statement |
| `#08` Data falsification, data fabrication and image integrity | 画像の加工は最小限にし、画像全体に一様に掛け、分野の標準に沿い、本文に書く。部分の移動・削除・追加・強調は不可。**編集者は未加工の原画像を求めることができ、応じられなければリジェクト・撤回されうる** | 図。**多パネル図を合成したなら、合成の前の素材を捨てない** |
| `#11` Author conflicts of interest | 全著者が競合利益を申告する (ICMJE に準拠)。**資金源は Funding に列挙する** | Declarations > Competing interests / Funding。Acknowledgments に資金を重ねない |
| `#12` Confidentiality | 著者は、原稿についての編集室・編集者・査読者とのやりとりをすべて秘匿する | **査読のコメントや編集室とのやりとりを公開のリポジトリに入れない** (原稿のリポジトリを公開するときに注意) |

### 14.6 `#13` Preprints

- プレプリントの公開は**推奨されている** (投稿の前でも同時でもよい)。対象は一次研究の原版だけ。
- **査読に応じて直した版・受理された版・掲載された版は、プレプリントサーバに載せてはならない**。代わりに掲載版へのリンクを置く。
- プレプリントを公開するときも著者が著作権を保つ。
- 掲載後の機関リポジトリへの登録は `#14` Self-archiving が別に推奨している。

### 14.7 この節が投稿チェックリストへ落ちる先

Editorial Policies の要求はほとんどが 👁 (人が目で見る) である — 規定チェックが見るのは Markdown の構造で、「関連する原稿があるか」
「許諾を取ったか」「実際に使った AI ツールは何か」は原稿の外の事実だからである。
[`docs/bhi-submission-checklist.md`](bhi-submission-checklist.md) では次の行になる。

| 行 | 節 |
|-----------|----|
| (投稿の 2〜4 週間前) 転載する素材の許諾 / 使った AI ツールと版の記録 | §14.4 / §14.3 |
| (投稿の 2〜4 週間前) COI / LTP のフォームの回収 (各 1 通) / 超過ページ料金の見込み | §4.1 / §1 の末尾 |
| (原稿) `# Acknowledgments` の節と AI 使用の開示の 5 要素 (実際に使ったものと合っているか) | §14.2 / §14.3 |
| (原稿) 受理の後は連絡著者を変えられないので、投稿の前に確定している | §14.2 |
| (原稿) 関連する原稿を編集者に開示した | §14.1 |
| (原稿) 転載する素材があれば、許諾の写しを初回投稿のときに添えた | §14.4 |
