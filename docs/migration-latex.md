# LaTeX の原稿を本テンプレートへ書き起こす (migration-latex.md)

LaTeX (IEEEtran などの 2 段組のクラス) で書いた原稿を、本テンプレートの Markdown に書き起こすときの対応表である。
執筆の規約は [`CLAUDE.md`](../CLAUDE.md)、BHI の規定は [`docs/journal-bhi.md`](journal-bhi.md)、
投稿までの手順は [`docs/usage-guide.md`](usage-guide.md) §8 にある。

> **これは「機械変換の後始末」ではなく「書き起こし」の手引きである。** 元の原稿の内容を写して、同等の
> (同一ではない) 投稿原稿を新しく作る。**レイアウトの同等性は求めない** — 2 段組・`.textbox` の絶対配置・
> 元のクラスの体裁は引き継がず、**最初から本文の流れに図表を置き、本テンプレートの規約で書く**。
> 変換の補助スクリプトは用意していない。下の (a)〜(e) はどれも書き起こしの一部で、機械化しても目で見る作業が残る
> (とくに表は列の意味を見ないと直せない)。

下の例はすべて**架空の最小原稿** (IEEEtran の 2 段組。題・著者・抄録・キーワード・図 2 つ・表 2 つ・`\thanks{}` 2 つ) を
pandoc 3.6.4 (`docx-paper-template-pandoc` コンテナ) の `pandoc -f latex -t markdown` に通した、そのままの出力である。

---

## 0. 全体の流れ

```bash
# 0. 骨格を写す (必須節の抜けが起きない)
cp data/journals/bhi/skeleton/main.md         src/main.md
cp data/journals/bhi/skeleton/cover-letter.md src/cover-letter.md
# 文例集: data/journals/bhi/skeleton/declarations.md (ビルドの対象外。Declarations を書くときに見る)
rm -f .development

# 1. 下書きを得る (参考。そのままは使わない)。元の原稿はリポジトリの中 (コンテナから見える場所) に置く
docker compose -f docker/docker-compose.yml run --rm -u "$(id -u):$(id -g)" pandoc \
    pandoc -s -f latex -t markdown --wrap=none jank/orig/main.tex -o jank/draft.md

# 2. jank/draft.md を見ながら src/main.md の骨格を埋める (本文書 §1〜§5)

# 3. 図を置く (PDF はそのまま置いてよい。原稿からは .svg で参照する)
cp jank/orig/figs/*.pdf src/figs/

# 4. 回して直す
bash scripts/build.sh   --journal bhi --article-type original
bash scripts/package.sh --journal bhi --mode final           # 最後に「規定チェック」が出る
bash scripts/check-figures.sh --journal bhi
```

- コンテナはリポジトリのルートを `/workspace` として見るので、**元の原稿と下書きはリポジトリの中に置く**
  (`jank/` は git 管理の外で、コンテナからも見える)。
- **`-s` を付ける。** 付けないと、題・著者・抄録が下書きから**消える** (メタデータに入り、本文としては書き出されない)。
  `-s` を付けると YAML の前置きに出てくるので、それを骨格の `custom-style` の Div (Title / Author / Affiliation /
  Abstract) へ移す。**YAML のまま残さない** — YAML のメタデータは全領域差分の対象にならない (`CLAUDE.md` の
  「原稿執筆の規約」)。

```markdown
<!-- -s を付けたときの下書きの先頭 (抜粋) -->
---
abstract: |
  Ward messages were triaged by a rule-based classifier. We evaluated it on 356 messages from a fictional hospital [@doe2020].
author:
- Alex Example, Robin Sample, and Kim Placeholder [^1] [^2]
bibliography:
- ref.bib
title: Automated Triage of Ward Messages with a Rule-Based Classifier
---
```

`pandoc -f latex -t markdown` を通すと、**引用 (`\cite{key}` → `[@key]`、複数は `[@a; @b]`)・見出し・箇条書き・
イタリック・数式はそのまま使える**。使えないのは下の 5 種である。

---

## 1. pandoc の変換で使えない 5 種

### (a) 図の拡張子 — `.pdf` のままでは埋め込みが壊れる

```markdown
<!-- pandoc の出力 (使えない) -->
![Overview of the proposed system (TriageBot). Each incoming ward message is …](figs/fig_overview.pdf){#fig:overview width="\\columnwidth"}

<!-- 本テンプレートの書き方 -->
![Overview of the message triage system.](figs/fig_overview.svg){#fig:overview}
```

**PDF の図もファイルは `figs/*.pdf` のまま置き、原稿からは `.svg` で参照する。** 図の前処理 (step01) が pdf2svg で
SVG に変換し、SVG のネイティブ埋め込みと PNG フォールバックの経路に載せるためである。`.pdf` で参照すると埋め込みが
壊れるので、ビルドがエラーで止める。

### (b) 無効な属性 — `width="\columnwidth"` / `width="86%"`

pandoc は LaTeX の長さをそのまま属性に残す (`\includegraphics[width=0.86\linewidth]` は `width="86%"` になる)。
**消す**か、見た目を保ちたいときだけ `{width=120mm}` のように**実寸で置き換える**。`\columnwidth` は 2 段組の段の幅なので、
1 段組の誌 (BHI など) では意味を持たない。`width="\\columnwidth"` は docx にするときに**黙って無視され** (警告は出ない)、
図は公称サイズで置かれる。害は無いが、原稿に意味の無い指定が残るので消しておく。

### (c) 相互参照 — 番号が固定される

```markdown
<!-- pandoc の出力 (使えない。番号 1 が本文に焼き付いている) -->
Fig. [1](#fig:overview){reference-type="ref" reference="fig:overview"}

<!-- 本テンプレートの書き方 -->
[@fig:overview]
```

そのままだと **pandoc-crossref の初出順の採番が効かない**。提出構成の組み替え (本文に残す `[Figure N about here]` と、
図の題と凡例の集約) も crossref が振った番号を見るので、どちらも正しく動かない。

### (d) 表 — 名前の付いた Div + simple table + `tab:` 接頭辞

```markdown
<!-- pandoc の出力 (使えない。\begin{center} で囲んだ表) -->
:::: center
::: {#tab:demographics}
  **Characteristic**           **Value**
  ------------------------ -------------
  Age (years), mean (SD)     56.2 (17.8)
  Sex, n (%)
  Male                       172 (48.3%)
  Female                     184 (51.7%)

  : Patient Characteristics (N = 356)
:::
::::

<!-- 本テンプレートの書き方 (pipe table + 題はキャプションの記法、凡例は直後の Legend Div) -->
: Characteristics of the 356 patients whose messages were triaged. {#tbl:demographics}

| Characteristic         | Value       |
|:-----------------------|------------:|
| Age (years), mean (SD) | 56.2 (17.8) |
| Sex: male, n (%)       | 172 (48.3%) |
| Sex: female, n (%)     | 184 (51.7%) |

::: {custom-style="Legend" for="tbl:demographics"}
Percentages are column proportions of the 356 patients. SD, standard deviation.
:::
```

- **識別子の接頭辞を `tab:` から `tbl:` に変える。** `tab:` では pandoc-crossref が解決しない。
- 題と凡例は `CLAUDE.md` の「図表の題と凡例の書き分け」に従って分ける (題 = キャプション / 凡例 = 直後の
  `custom-style="Legend"` の Div)。**1 本のキャプションに両方を詰め込まない** — BHI は題 15 語・凡例 300 語と別々に
  上限を定めていて、キャプション 1 本では 2 つの上限を判定できない。
- `\begin{center}` は `:::: center`、2 段抜きの `\begin{table*}` は `::: table*`、IEEEtran のキーワードは
  `::: IEEEkeywords` のように、**名前の付いた Div** に包まれて出てくる。どれも **Div を外して、中身を本テンプレートの
  記法に書き直す** (キーワードは `custom-style="Keywords"` の Div へ)。
- **`\begin{table*}` / `\begin{figure*}` (2 段抜き) も、1 段組の誌ではそのまま本文の流れの図表にする**
  (`.textbox` は使わない。§3)。
- 題 (`\caption{}`) を持たない表への参照は、番号ではなく**識別子そのもの**に化ける。
  見た目がかなり違うので見落としやすい。(c) と同じく `[@tbl:rules]` に書き直す (表には題を付ける)。

  ```markdown
  The rules are listed in Table [\[tab:rules\]](#tab:rules){reference-type="ref" reference="tab:rules"}.
  ```

### (e) 脚注 — `\thanks{}` が本文の脚注になる

IEEEtran の `\thanks{}` は Markdown の脚注定義になり、下書きの末尾に並ぶ (`-s` を付けたときは著者の行に
`[^1] [^2]` の参照が付く)。

```markdown
<!-- pandoc の出力 (使えない) -->
[^1]: (Corresponding author: Alex Example; e-mail: (address)).

[^2]: R. Sample is also with the Department of Nursing, Example University Hospital.
```

**本文に脚注として残さない。** 中身に応じて Title page の Div へ移す。

- **連絡著者の情報** → `custom-style="Corresponding"` の Div (BHI は氏名・住所の全文・電話・E-mail をまとめて書くよう
  求めている)
- **所属の補足** (「〜にも所属する」) → `custom-style="Affiliation"` の Div に上付きの数字で足す

放っておくと docx に本物の脚注として出て、Title page に求められる書き方から外れる。
**規定チェックは本文中の脚注を指摘しない**ので、機械では拾えない (凡例の Div の中の脚注だけは検出する)。

---

## 2. 図表の題を 15 語に収める

LaTeX の `\caption{}` は説明文を丸ごと抱えていることが多く、**そのままでは 15 語を超える**。題 (短い一文) と
凡例 (説明) に割り直す。

```markdown
<!-- 元のキャプション (41 語) -->
\caption{Overview of the proposed system (TriageBot). Each incoming ward message is normalized by the
parser into a structured record, scored by the rule engine, and routed to the queue whose threshold it
exceeds; low-confidence messages are sent to a human reviewer.}

<!-- 書き起こし後: 題 6 語 + 凡例 -->
![Overview of the message triage system.](figs/fig_overview.svg){#fig:overview}

::: {custom-style="Legend" for="fig:overview"}
Each incoming ward message is normalised by the parser into a structured record, scored by the rule
engine and routed to the queue whose threshold it exceeds. Low-confidence messages are sent to a human
reviewer.
:::
```

**凡例は段落だけで書く。** 箇条書き・表・定義リスト・空白 4 個以上の字下げ (コードブロック) などを入れると、pandoc が
`Legend` 以外の段落スタイルを付け、凡例の集約がそこで止まる (検出する構造と注意点は `CLAUDE.md` の
「図表の題と凡例の書き分け」)。とくに **「凡例では略語を改めて定義する」という BHI の要求を定義リスト
(`用語` の次の行に `:   説明`) で書くと事故になる** — 普通の文で `EHR, electronic health record;` のように並べる。
元のキャプションがパネルを `(a) … (b) …` と説明しているときも、凡例を `(A)` で始めると番号つきリストになるので、
`Panel A shows … Panel B shows …` のように文で書き直す。

---

## 3. `.textbox` は使わない

2 段組の詳細抄録などのテンプレートに合わせた原稿は、図表を `.textbox` の絶対配置で置いていることがある
(Markdown で書いた原稿を別の誌へ移すときにも起きる)。1 段組の誌へ書き起こすときはこれを引き継がず、
**本文の流れの図表にする**。

理由は 2 つある。

1. **BHI は図を原稿の本体に埋め込むことを禁じている** ("Figures must NOT be embedded within the manuscript file.")。
   `.textbox` の中身は提出構成の組み替え (表の移設・図の題と凡例の集約) の対象外なので、最終提出の docx に
   **本文へ埋め込まれたまま残る**。
2. **図表の点数・題の語数・凡例の語数の検査から外れる。** 点数は「本文の流れの上にある図表」だけを数えるので、
   全図表を箱に置いた原稿は「図 0 点・表 0 点」になる。

箱の中に図表があること自体を、規定チェックが要修正として指摘する (図表点数の上限を持つ誌のとき。
「.textbox の中に図 N 点・表 M 点があります」)。概算の行にも「うち .textbox 内 図 N 点・表 M 点は上限の対象外」が
必ず出るので、移し忘れは `package.sh` の「規定チェック」で気づける。

---

## 4. 文献の誌名を Index Medicus の略誌名に直す

LaTeX の原稿の bib は誌名を正式名で持っていることが多い。CSL では正式誌名から略誌名へ変換できないので、
**入力の側 (bib の `journal`) で直すしかない** (`CLAUDE.md` の「BHI 投稿時の執筆規約」の文献の項)。

**略誌名は記憶で書かず、NLM Catalog で 1 件ずつ確かめる。** 確かめ方 (NCBI の E-utilities):

```bash
# 正式誌名 → NLM Catalog の uid
curl -s 'https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?db=nlmcatalog&retmode=json&term=%22Scientific+Reports%22[Title]+AND+ncbijournals[filter]'
# uid → MedlineTA (= Index Medicus の略誌名)
curl -s 'https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?db=nlmcatalog&id=101563288&retmode=xml' | grep MedlineTA
#   → <MedlineTA>Sci Rep</MedlineTA>
```

> **題での検索は紛らわしい別の誌を返す。** たとえば `Scientific Reports` は `Sci Rep Ist Super Sanita` などの近縁の
> 誌と並んで返り、誌によっては**目当ての誌が 1 件も出ない**こともある。
> **候補が 2 件以上出たら ISSN で引き直す** (`term=<ISSN>[ISSN]`)。
>
> **MEDLINE に収載されていない誌**も、NLM Catalog に登録があればその略誌名を使う (登録が無ければ正式誌名)。

あわせて bib の側で行うこと:

- **和文の文献には `langid = {japanese}` を付ける** (出力に `(in Japanese)` が付く)。`language` フィールドは
  pandoc に捨てられて効かない。和文以外の非英語の文献は `note = {in German}` のように書く (`docs/journal-bhi.md` §3.2)。
- **英語の文献の `langid` は消す**。LaTeX の原稿の bib は Zotero / Better BibTeX などの書き出しであることが多く、
  英語の文献にも `langid = {english}` が付いている。`langid` があると言語によらず `(in Japanese)` が付く。
- **題の固有名詞は波括弧で保護する** (`{Japan}` / `{TriageBot}`)。保護しないと pandoc がセンテンスケースに直して、
  規定の出力例と食い違う。
- **引用されない文献は落とす** (bib に残っていても出力には出ないが、入力を提出に要るものだけにしておくほうが
  後の照合が楽になる)。

誌名の略記は**目で見て**確かめる。`bash scripts/check-csl.sh` は引用様式 (CSL) が規定の出力例どおりかを照合する道具で、
自分の bib の中身は見ない (`docs/usage-guide.md` §4.1)。

---

## 5. 内容の側で必ず当たる 5 点

どれもテンプレートの不足ではなく**執筆の作業**である。書き起こしの時点で片付けるのがいちばん安い。

### 5.1 抄録を 4 ラベルに組み直す

BHI の Original Article は **Objective / Methods / Results / Conclusion** の 4 ラベル・300 語以内で、
**文献の引用は不可**。IEEE 系の抄録は見出しの無い 1 段落が多いので組み直す。ラベルは `**Objective:**` のように
太字で書く — 規定チェックは `**` + ラベル名の形でしか検出しない (単複を取り違えた `Conclusions` も弾く)。
元の抄録が文献を引いていれば外す (§0 の下書きの抄録にも `[@doe2020]` が残っている)。

### 5.2 表の階層行 — pipe table では行頭の空白が落ちる

`Sex, n (%)` の下に `\quad Male` / `\quad Female` を字下げして並べる形は、(d) の出力のとおり **pandoc の時点で
行頭の空白が落ちて階層が消える**。対処は 2 つ:

- 行のラベルを `Sex: male, n (%)` のように書き換える (**推奨**。docx でも PDF でも崩れない)
- `&nbsp;` を使う (見た目は保てるが、語数の数え方と検索のしやすさが落ちる)

### 5.3 Declarations の 6 項目と CRediT は本文語数に算入される

BHI が本文語数から**除外**するのは表・図 / 文献 / 図のキャプション / 抄録 / Abbreviations で、**Declarations は算入
される** (本テンプレートは図表の凡例も除外して数え、内訳を出す。`docs/journal-bhi.md` §7.7)。CRediT の 14 分類を書き下すと
数百語になりうる。刷り上がりが上限を超えると**1 ページあたり 2 万円 +税の著者負担**になるので、書き起こしの途中で
規定チェックの概算の行を見ながら進める。

```bash
docker compose -f docker/docker-compose.yml run --rm -u "$(id -u):$(id -g)" pandoc \
    python3 main/step05_package/validate.py --input-root src --journal bhi --article-type original
```

### 5.4 図表の点数が上限を超える

BHI の Original Article は図表あわせて **8 点**まで。会議録や技術報告をもとにした原稿は超えやすい。規定チェックが
要修正として出すので、**多パネル図への統合**か **supplementary への移動**を決める。統合するときは**1 ファイルに合成**し
(自動化されない。作図の側で 1 枚として出力する。複数の SVG を後から連結すると Word で崩れる — `CLAUDE.md`)、
**凡例のキーは画像の中**に入れる。

### 5.5 図の公称サイズ — px 単位の大きな SVG と、MediaBox の大きな PDF

- **px 単位の大きな SVG は巨大な PNG を生む。** px と単位なしは CSS px (1/96 inch) とみなすので、たとえば
  1600×1200 px の SVG は公称 16.67×12.5 インチで、300 dpi では 5000×3750 px (18.75 MP) になる。書き起こしのときに
  **SVG ルートの `width` / `height` を物理単位 (mm) に直す** (`CLAUDE.md` の規約)。pptx のスライドの寸法にも
  公称サイズがそのまま出る。
- **PDF の図は MediaBox の実寸がそのまま公称サイズになる** (pdf2svg が書き出す寸法を pt として読む)。元の図が大きく
  作ってあると提出図も大きくなる — たとえば MediaBox が 2000×1700 pt なら 27.78×23.61 インチで、pptx のスライドも
  27.78 インチ、PNG フォールバックは 8333×7083 px (約 59 MP) になる。**規定違反ではない**が、刷り面に対して極端に大きい
  図は元のデータの側で作り直すのが筋である (**56 インチを超えるとエラーで止まる**。`--slide-fit fixed` で既定の寸法へ
  縮めて置くこともできる。`docs/architecture.md` §2.5)。

---

## 6. 受入 — 書き起こせたかの判定

```bash
bash scripts/build.sh   --journal bhi --article-type original                          # 警告なしで終わる
bash scripts/package.sh --journal bhi --mode final                                     # 最後に「規定チェック」
bash scripts/check-figures.sh --journal bhi                                            # 図ツリー (実画素数まで検算)
bash scripts/check-figures.sh --journal bhi --figures-dir data/output/bhi/figures      # 提出する図
```

次が揃えば、記法の書き起こしは終わっている。

- [ ] ビルドがエラーも警告も出さずに終わる (`.pdf` で参照した図はエラー、寸法の無い SVG は警告になる)
- [ ] 相互参照がすべて解決している — docx の本文に `Fig. 1` / `Table 1` が初出順に並び、**`¿tbl:rules?` のような
      `¿…?` が 1 つも無い**。pandoc-crossref は解決できなかった参照をこの形で出すが、**ビルドは警告を出さずに通る**ので、
      docx の中を `¿` で検索して確かめる。(c)・(d) の書き直し漏れ (とくに `tab:` のまま残った接頭辞) はここで見つかる
- [ ] 規定チェックに**記法に由来する指摘が無い** (凡例の配置と中身・記入欄 `<<...>>` の残り・`.textbox` の中の図表・
      抄録のラベル)。残る指摘が**内容の判断が要るもの** (図表の合計点数・タイトルの略語が分野で一般的か・語数) だけに
      なっていればよい
- [ ] `check-figures.sh` の 2 つのモードが合格し、「注意」(自分で置いたラスタ図・連結した SVG・`hsl()` の色) を
      読んで片付けた
- [ ] 脚注 (§1 (e)) が本文に残っていない (機械では拾えないので目で見る)

最後の確認は `docs/bhi-submission-checklist.md` を上から順に。
