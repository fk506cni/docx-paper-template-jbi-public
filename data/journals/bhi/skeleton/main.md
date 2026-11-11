<!--
data/journals/bhi/skeleton/main.md — BioHealth Informatics (BHI) 原稿骨格

用途: BHI へ投稿する原稿の【雛形】。実際に書き始めるときは本ファイルを原稿の入力ルートへ写す。

    cp data/journals/bhi/skeleton/main.md src/main.md      # 本番 (.development 無し)
    cp data/journals/bhi/skeleton/cover-letter.md src/cover-letter.md

  ※ 記入済みの動作例は data/dummy/bhi/ にある (ビルドが通る完結サンプル)。
    書き方に迷ったらそちらを見る。

【この雛形の約束ごと】
  - `<<...>>` は記入欄。提出前にすべて置き換える (残っていれば書き忘れ)。
    ※ 置換漏れは `package.sh` の末尾の「規定チェック」で
      要修正として出る (本ファイルと cover-letter.md の両方を読む)。
      ※ 記入欄の【総数は validate.py が報告する残数を正とする】— 雛形を編集するたびに変わる
        (Acknowledgments 節を含めて、本ファイル単体で 50 箇所)。
      ※ pandoc の扱いは記入欄の中身によって【3 通りに分かれる】(実測)。そのまま残る /
        中身が消えて `<>` だけ残る (実測時点の 34 種のうち 15 種がこれ。`<<Given-name Family-name>>`
        `<<Department>>` など、中身が HTML タグとして読める場合) / メールリンクになる。
        危ないのは 2 つめで、docx を通し読みしても組版のごみに見えるため書き忘れに気づけない
        (docs/journal-bhi.md §7.7 に実測表)。
  - タイトル / 著者 / 所属 / 連絡著者 / 抄録 / キーワードは【YAML メタではなく custom-style Div】
    で書く。全領域差分 (step03) がこれらを温存し内部を語単位で差分化するための必須事項
    (CLAUDE.md 「原稿執筆の規約」/ docs/architecture.md §2.3)。
  - 節の順は Original Article の規定順 (docs/journal-bhi.md §1 / §7)。
    Title page → Abstract → **Abbreviations** → Introduction → Methods → Results → Discussion
    → Conclusion → (Acknowledgments) → **Declarations** → References。
    ※ Acknowledgments は規定の必須節ではないが、【AI ツールを使ったなら開示が必須】なので
      受け皿として置いてある (docs/journal-bhi.md §14.3)。該当が無ければ節ごと削る。
    ※ 他の記事種別 (review / short / technical / data / perspective / tutorial / letter) は
      本文構成が異なる。data/journals/bhi/profile.yaml の article_types.<種別>.sections を見て
      Introduction〜Conclusion の並びを差し替える。Title page / Abstract / Abbreviations /
      Declarations / References の枠組みは共通。
  - 図と表は【本文中の自然な位置】に書く。末尾への移設と Figure Legends への集約は
    package の仕事なので、原稿側で末尾へ動かさない (雑誌非依存を保ち、
    pandoc-crossref の初出順採番を壊さないため)。
    ※ `package.sh --mode final` が自動で組み替えるので、
      原稿側で手を加える必要はない。
  - 図表の【題】と【凡例】は別物として書く。題はキャプション、凡例は直後の
    `custom-style="Legend"` Div (CLAUDE.md 「図表の題と凡例の書き分け」)。
    凡例は【段落だけ】で書き、多パネル図でも `(A) …` / `a. …` で始めない (番号つきリストに
    なって集約から外れる)。パネルは `Panel A shows … Panel B shows …` のように文で説明する。
  - **Results 節の図・表の記入欄は HTML コメントで囲んである**。図表を入れるときは
    コメントを外して記入する。囲んだままにしてあるのは、記入欄の画像が
    実在しないファイルを指すと `build.sh` が画像数の照合で【中止する】ため — 本ファイルを写した
    直後でもビルドが通る状態にしてある。
  - 本文語数の上限 (Original Article 4000 語) から除外されるのは 表・図 / 文献 /
    図キャプション (規定本文) と、本テンプレートの扱いとして抄録 / Abbreviations。**Declarations は算入する**。
    ※ `package.sh` が出す概算語数では、
      図表の凡例 (Legend Div) は本文語数から除外され、除外した語数が図/表に分けて
      内訳表示される (表の凡例も除外する判断。docs/journal-bhi.md §7.7)。
-->

::: {custom-style="Title"}
<<Title of the Manuscript in Title Case, Not Exceeding 30 Words>>
:::

<!-- 題名: 30 語以内。略語は分野で一般的なもの以外不可。数式・商品名は避ける。
     大文字化は「各語の頭文字のみ大文字。ただし接続詞・冠詞・前置詞は先頭語を除き小文字」。 -->

::: {custom-style="Author"}
<<Given-name Family-name>>^1^ (ORCID: <<0000-0000-0000-0000>>), <<Given-name Family-name>>^1,2^ (ORCID: <<0000-0000-0000-0000>>), <<Given-name Family-name>>^2^
:::

<!-- 著者: フルネーム。学位・肩書 (MD, PhD, Professor 等) は書かない。
     ORCID iD があれば併記する。所属は上付き数字で対応づける。 -->

::: {custom-style="Affiliation"}
^1^<<Department>>, <<Institution>>, <<City>>, <<State/Prefecture>>, <<Country>>

^2^<<Department>>, <<Institution>>, <<City>>, <<State/Prefecture>>, <<Country>>
:::

::: {custom-style="Corresponding"}
**Corresponding author:** <<Given-name Family-name>>

<<Department>>, <<Institution>>

<<Street address>>, <<City>>, <<State/Prefecture>> <<Postal code>>, <<Country>>

Tel: <<+81-00-0000-0000>>

E-mail: <<name@example.org>>
:::

<!-- 連絡著者は 1 名のみ。氏名・住所全文・電話・E-mail をすべて書く (規定 "Title page")。
     validate.py の検査はこの Div を検出対象にするので、Div ごと消さないこと
     — 連絡著者が 1 名か、住所・電話・E-mail が揃っているかを見る。 -->

::: {custom-style="Abstract"}
**Objective:** <<研究の目的を 1〜2 文で。>>

**Methods:** <<デザイン・対象・データ・解析手法。>>

**Results:** <<主要な結果を数値で。>>

**Conclusion:** <<結論と含意。>>
:::

<!-- 抄録: Original Article は Objective / Methods / Results / Conclusion の 4 ラベル、300 語以内。
     【文献引用は不可】。略語は最小限。
     他の記事種別は非構造化 (200〜300 語) — profile.yaml の article_types.<種別> を見る。 -->

::: {custom-style="Keywords"}
**Keywords:** <<keyword one>>; <<keyword two>>; <<keyword three>>
:::

<!-- キーワード: 3〜5 語。MeSH (MEDLINE シソーラス) から採る。区切りは `;`。 -->

# Abbreviations

<<EHR>>, <<electronic health record>>; <<ICU>>, <<intensive care unit>>

<!-- Abbreviations: 【Abstract と Introduction の間】に置く (規定 "Declarations" 節)。
     ここで定義した略語は本文中でそのまま使えるが、【図・表の凡例では改めて定義する】。
     本文語数には算入しない (本テンプレートの扱い)。 -->

# Introduction

<<背景・先行研究・空白・本研究の目的。引用は `[@bibkey]` 形式で書く。>>

# Methods

<<デザイン / 対象 / データ源 / 変数 / 解析。>>

<!-- 単位は SI または SI 派生単位 (mmHg 等の臨床慣用単位は可)。
     温度は `°C` (度記号 + 大文字 C の 2 文字) と書く。合成済み 1 文字の度セルシウス記号
     (および mg / kg などの合成 1 文字) は使わない — 禁止文字そのものはここには書かない
     (この雛形を写した原稿が validate.py の lint に引っかかるため)。
     一覧は CLAUDE.md の執筆規約に。
     機器・製品は 型番 + 製造元 + 所在地 (市・州・国) を括弧内に。統計ソフトはバージョンも。
     研究デザインに応じた報告ガイドライン (STROBE / PRISMA / STARE-HI / TRIPOD+AI 等) に準拠する。 -->

# Results

<<結果。図表は本文中の自然な位置に置く (末尾移設は package の仕事)。>>

<!-- 【図・表を入れるときは、この行と下の閉じ行を消してコメントを外す】

     コメントで囲んであるのは、記入欄の画像 figs/<<fig-name>>.svg が実在しないファイルを指すため、
     このまま build.sh を掛けると「原稿の画像数 (1) と docx の図数 (0) が一致しません」で
     【中止する】から。骨格を写した直後にビルドが通るようにしてある。
     図を入れるときは、コメントを外して <<...>> を埋め、実ファイルを <入力ルート>/figs/ に置く。

![<<Figure title, 15 words or fewer.>>](figs/<<fig-name>>.svg){#fig:<<label>>}

::: {custom-style="Legend" for="fig:<<label>>"}
<<Figure legend, 300 words or fewer. 図中で使う略語はここで改めて定義する。>>
:::

: <<Table title, 15 words or fewer.>> {#tbl:<<label>>}

| <<Variable>> | <<Group A>> | <<Group B>> |
|:-------------|------------:|------------:|
| <<name>>     | <<10 000>>  | <<9 500>>   |

::: {custom-style="Legend" for="tbl:<<label>>"}
<<Table legend, 300 words or fewer. 表中で使う略語・記号の意味はここで説明する。>>
:::

     ここまで -->

<!-- 記入済みの図表の書き方は data/dummy/bhi/main.md を見る (そのままビルドできる完結サンプル)。 -->

<!-- 表: 色・網掛け禁止 (強調は上付き・番号・記号・太字で行い、意味は凡例で説明)。
     数値の桁区切りにカンマを使わない (`10 000` のように空白)。 -->

# Discussion

<<主要な知見 / 先行研究との比較 / 限界。>>

# Conclusion

<<結論。>>

# Acknowledgments

<<オーサーシップの 4 基準を満たさない貢献者への謝辞。該当が無ければこの段落は削る。>>

<<AI ツールを使ったなら開示する (下のコメントの 5 要素)。文例は
data/journals/bhi/skeleton/declarations.md の §7 にある。>>

<!-- Acknowledgments 節 (位置は Conclusion と Declarations の間。規定の必須節ではない)

     【綴り】本誌の用例は Acknowledgments (米式) である (Editorial Policies "Authorship" の
     "the Acknowledgments section"。投稿規定 For Authors にはこの語が現れない)。
     規定が求めるのは「米式/英式のどちらかに統一する」ことだけなので、英式で書く原稿なら
     Acknowledgements に直す。本誌の規定文書自体が analyse/analysed (英式) と
     Acknowledgments (米式) を混在させているので、「雑誌に合わせる」では決まらない —
     決め手は原稿側の統一である (docs/journal-bhi.md §14.3)。

     【何を書くか】
     (a) オーサーシップの 4 基準を満たさない貢献者 (Editorial Policies "Authorship" =
         docs/journal-bhi.md §14.2)。規定の原文は "may be included" なので【任意】である。
     (b) 生成 AI ツールを使った場合の開示 (Editorial Policies "Use of AI tools" = 同 §14.3)。
         規定は「原稿の適切な箇所で開示せよ」と言うだけで【場所を指定していない】。
         本テンプレは独立した本節に置く (規定が定める Declarations 6 項目の構成を崩さずに済むため)。
         文例の 5 要素:
           1. ツール名  2. バージョン  3. 使途 (何にどう使ったか)
           4. 著者が提出原稿の全内容に責任を負う旨
           5. AI で整えた後もネイティブスピーカーが最終原稿を確認した旨
         1・3・4・5 は規定の原文が求めている (4 は "authors remain responsible for all the
         content of their submitted manuscript"、5 は "the final manuscript reviewed by a native
         English speaker even after AI-assisted refinement" が根拠で、自主的な追加ではない)。
         【2 だけは規定の要求ではなく本テンプレの上乗せ】である (原文に版への言及は無い。
         同名の道具でも版で挙動が変わるので、版まで書いて特定する)。他誌へ出すときの取捨の目印にする。
         ※ 文法・スペルチェックの範囲を超える使い方 (構成の補助など) は、規定上
           【個別審査 (case-by-case)】の側に落ちる。編集室から説明を求められる可能性は
           見込んでおくこと (規定どおりに書いた結果であり、書かずに済ませるという選択肢は無い)。

     【資金は書かない】資金源は Declarations > Funding に書く (Editorial Policies
     "Author conflicts of interest" が "Authors should list all funding sources for their work
     in the Funding section" と場所を指定している)。謝辞に重複させないこと。

     【本文語数に算入される】除外対象は「表・図 / 文献 / 図キャプション」(規定本文に明示) と
     「抄録 / Abbreviations」(本テンプレートの扱い) で、本節はどれにも当たらない。
     Declarations と同じく【算入される前提】で書く (validate.py も本文語数に数える)。

     【該当が無ければ】節ごと削ってよい。規定が必須としている 6 項目は Declarations 側であって
     本節ではない (validate.py も本節の有無は見ない)。ただし AI ツールを使ったなら開示は必須。 -->

# Declarations

<!-- 6 項目すべて必須。該当しない項目も削らず "Not applicable" と書く。
     定型文は data/journals/bhi/skeleton/declarations.md にある。
     【Declarations は本文語数に算入される】ので、CRediT を書き下すと上限を圧迫する点に注意。 -->

## Funding

<<資金源をすべて。資金提供者が研究デザイン・データ収集・解析・執筆に関与したかも記す。
無い場合: The authors received no specific funding for this work.>>

## Authors' contributions

<<CRediT 14 ロールで著者ごとに記述する。例:
A.B.: Conceptualization, Methodology, Formal analysis, Writing – original draft.
C.D.: Data curation, Investigation, Writing – review & editing.
E.F.: Supervision, Funding acquisition, Writing – review & editing.>>

All authors read and approved the final manuscript, and agree to be accountable for all
aspects of the work.

<!-- CRediT 14 ロール: Conceptualization / Data curation / Formal analysis /
     Funding acquisition / Investigation / Methodology / Project administration / Resources /
     Software / Supervision / Validation / Visualization / Writing – original draft /
     Writing – review & editing -->

## Data availability statement

<<データの所在と入手方法。公開不可の場合はその理由と条件を書く。>>

## Ethics approval and consent to participate

<<倫理委員会名と承認番号、同意取得の方法 (免除の場合も記載)。該当なしは Not applicable.>>

## Consent for publication

<<個人が特定されうるデータ・画像を含む場合の公表同意。該当なしは Not applicable.>>

## Competing interests

<<金銭的・非金銭的な競合利益をすべて。
無い場合: The authors declare that they have no competing interests.>>

# References

::: {#refs}
:::

<!-- 文献は src/ref.bib に BibTeX で持つ。BHI 固有の注意 (CLAUDE.md / docs/journal-bhi.md §3.2):
       - 誌名は Index Medicus の略誌名を `journal` に【略記で】持つ (CSL では変換できない)
       - 和文論文は `langid = {japanese}` を付ける (出力に "(in Japanese)" が付く)。
         `language` フィールドは pandoc に捨てられて効かない
       - 英語文献には `langid` を書かない (あるだけで言語によらず "(in Japanese)" が付く。
         書誌管理ソフトが付けた langid = {english} も消す)
       - 題の固有名詞は BibTeX の波括弧で保護する ({Cancer Institute Hospital})
     引用書式を変えたら bash scripts/check-csl.sh --docx <docx> で公式例と機械照合する。 -->
