<!--
data/journals/bhi/skeleton/declarations.md — BHI Declarations 6 項目の定型文集
(§7 は Acknowledgments 節に書く AI 使用開示の文例)

用途: 参照専用の【文例集】。ビルド対象ではない (build.sh が読むのは main.md /
      revise-report.md / cover-letter.md の 3 つだけ)。
      main.md の `# Declarations` 節に、下の文例から該当するものを写して使う。

出典: docs/journal-bhi.md §7.4 (規定 "Declarations" 節の要約)。
      規定に例文が示されているものは「規定の例文」と注記した。それ以外は本テンプレの文案なので、
      自研究の事実に合わせて必ず書き換えること。

【注意】Declarations は本文語数に【算入される】として本テンプレートは数える (規定の文面だけでは決まらない)。CRediT 14 ロールを
        著者ごとに書き下すと数百語になりうる。Original Article の 4000 語に対して無視できず、
        刷り上がりが記事種別ごとの上限 (Original Article は 9 ページ) を超えると
        1 ページ 2 万円 (+税) の著者負担になるため、費用にも直結する (docs/journal-bhi.md §11)。
        ロールは「実際に担当したものだけ」を挙げ、全ロールを網羅しようとしないこと。
-->

# Declarations 文例集 (BHI)

6 項目はすべて必須。該当しない項目も**節ごと削らず** "Not applicable." と書く。

> **§7 だけは Declarations の外にある**。`main.md` の
> **`# Acknowledgments`** 節に書く **AI 使用開示**の文例で、Declarations 6 項目には数えない。
> 資金は §1 Funding に書き、謝辞に重複させないこと。

## 1. Funding

**資金がある場合**

> This work was supported by <<Funder name>> (grant number <<XXXXXXXX>>) to <<A.B.>>.
> The funder had no role in the study design, data collection and analysis, decision to
> publish, or preparation of the manuscript.

- 資金提供者が研究デザイン / データ収集 / 解析 / 執筆に関与した場合は、その関与を具体的に書く
  (上の 2 文目を事実に合わせて書き換える)。

**資金が無い場合** (規定の例文)

> The authors received no specific funding for this work.

## 2. Authors' contributions

**CRediT (14 contributor roles) で著者ごとに記述する。**

> <<A.B.>>: Conceptualization, Methodology, Formal analysis, Writing – original draft.
> <<C.D.>>: Data curation, Investigation, Writing – review & editing.
> <<E.F.>>: Supervision, Funding acquisition, Writing – review & editing.
>
> All authors read and approved the final manuscript, and agree to be accountable for all
> aspects of the work.

CRediT 14 ロール (順序は CRediT の定義順):

| # | Role | # | Role |
|---|------|---|------|
| 1 | Conceptualization | 8 | Resources |
| 2 | Data curation | 9 | Software |
| 3 | Formal analysis | 10 | Supervision |
| 4 | Funding acquisition | 11 | Validation |
| 5 | Investigation | 12 | Visualization |
| 6 | Methodology | 13 | Writing – original draft |
| 7 | Project administration | 14 | Writing – review & editing |

- **全著者が最終原稿を確認・承認し、説明責任を負う旨の文**を必ず添える (上の最終段落)。
- ダッシュは en dash (`–`)。CRediT の正式表記に合わせる。

## 3. Data availability statement

**公開する場合**

> The dataset generated and analysed during the current study is available in the
> <<repository name>> repository, <<persistent identifier / URL>>.

**要請に応じて提供する場合**

> The datasets generated and analysed during the current study are available from the
> corresponding author on reasonable request.

**公開できない場合** (理由を必ず書く)

> The datasets generated and analysed during the current study are not publicly available
> because <<they contain information that could compromise the privacy of research
> participants>>, but are available from the corresponding author on reasonable request
> <<with the approval of the ethics committee>>.

**規定の例文** (For Authors "Data availability statement"。上の 3 つとは別に、規定はこの 4 文を例示している)

> The datasets supporting the conclusions of this article are available in the
> <<repository name, unique persistent identifier, hyperlink to datasets>>.

> The datasets supporting the conclusions of this article are included within the article
> <<as additional files>>.

> Data are available from the corresponding author upon reasonable request.

> Data cannot be shared due to patient privacy concerns.

- 記事種別が `data` (Data Report) のときは、**オープンデータ公開と公共リポジトリ登録が必須**で、
  **永続的識別子つき**の Data Availability Statement が要る (profile.yaml の
  `article_types.data.note`)。
- 法的・倫理的・契約上の制約でデータを出せないときは、**その制約を Statement に書く**。
  査読中は編集者・査読者の求めに応じてデータを提供する義務がある (Editorial Policies
  "Data Availability"。`docs/journal-bhi.md` §14.5)。
- ⚠ **上の 3 つの文例 (規定の例文ではなく本テンプレの文案) は英式綴りの `analysed` を使っている。**
  原稿を米式で書くなら **`analyzed` に直す** (§7 の文例にある `analyse` も同じ)。
  規定が求めるのは「米式/英式のどちらかに統一」だけで、どちらを採るかは投稿ごとに決める。
  **本誌の規定文書の綴りも一定しない** (Editorial Policies は節名に米式の `Acknowledgments`、
  本文に英式の `analyse` を使う) ので、雑誌側に合わせようとしても決まらない — 決め手は原稿側の統一である。
  骨格 `main.md` の節名は本誌の用例に合わせて `Acknowledgments` にしてあるので、英式で書く原稿は
  `Acknowledgements` に直す。

## 4. Ethics approval and consent to participate

**ヒト対象研究**

> This study was approved by the <<Ethics Committee of Institution>> (approval number
> <<XXXX>>). <<Written informed consent was obtained from all participants.>> /
> <<The requirement for informed consent was waived by the committee because of the
> retrospective nature of the study, and an opt-out opportunity was provided.>>

**動物実験**

> All animal experiments were approved by the <<Animal Care and Use Committee of
> Institution>> (approval number <<XXXX>>) and were performed in accordance with
> <<relevant guidelines>>.

**該当しない場合** (規定の例文)

> Not applicable.

## 5. Consent for publication

**個人が特定されうるデータ・画像を含む場合**

> Written informed consent for publication of the <<clinical details and/or images>> was
> obtained from the <<patient / participant>>.

**該当しない場合** (規定の例文)

> Not applicable.

## 6. Competing interests

**ある場合** (金銭的・非金銭的の両方を申告する)

> <<A.B.>> has received <<lecture fees>> from <<Company>>. The other authors declare that
> they have no competing interests.

**無い場合** (規定の例文)

> The authors declare that they have no competing interests.

---

## 7. (Declarations の外) Acknowledgments — AI 使用の開示

**⚠ 本節は Declarations 6 項目ではない。** `main.md` の **`# Acknowledgments`**
(Conclusion と Declarations の間) に書く。

**根拠**: Editorial Policies "Use of Artificial Intelligence (AI) tools"
(<https://biohealth-informatics.com/editorial-policies/> のアンカー `#09`。全文と読み解きは
`docs/journal-bhi.md` §14.3)。規定は開示の**場所を指定していない** ("in a suitable part of the
manuscript") ので、本テンプレは独立した Acknowledgments 節に置く (Declarations 6 項目の構成を
崩さずに済むため。Editorial Policies "Authorship" も "the Acknowledgments section" に言及している)。

**入れる 5 要素** (1・3・4・5 のどれかが欠けると規定の要求を満たさない):

| # | 要素 | 規定の根拠 |
|---|------|-----------|
| 1 | **ツール名** | "Authors must describe **which tools** they used" |
| 2 | **バージョン** | ⚠ **規定の要求ではない (本テンプレの上乗せ)**。原文に版への言及は無い。同名の道具でも版で挙動が変わるため、版まで書いて初めて特定できる。**他誌へ出すときは、ここが規定由来ではないことを取捨の目印にする** |
| 3 | **使途** (何にどう使ったか) | "…and **how the tools were used**" |
| 4 | **著者が提出原稿の全内容に責任を負う旨** | "In all cases, **authors remain responsible for all the content** of their submitted manuscript." |
| 5 | **ネイティブスピーカーによる最終確認を受けた旨** | "authors are still required have **the final manuscript reviewed by a native English speaker** even after AI-assisted refinement" (原文ママ) |

**文例** (5 要素をこの順で並べたもの)

> The authors used <<ツール名>> (version <<X.Y>>, <<提供元>>) to <<使途を具体的に。
> 例: assist with organizing the structure of the manuscript and to check spelling and grammar>>.
> The tool was not used to <<生成 AI に任せなかったことを書く。例: collect or analyse data,
> or to generate any figures>>. The authors reviewed and edited all output and take full
> responsibility for the entire content of the submitted manuscript. The final manuscript was
> also reviewed by <<a native English speaker / 英文校正業者名>>.

**AI ツールを使っていない場合**

> 本節に AI の記述は要らない (使っていない旨を書く義務は規定に無い)。
> 4 基準を満たさない貢献者への謝辞だけを書くか、貢献者もいなければ節ごと削る。

**書くときの注意**

- **版は「実際に使ったもの」を書く。** 執筆が複数セッションに分かれると途中で版が変わりうるので、
  **投稿の直前に、実際に使った道具と版を確定させる**。作業中は、使った道具と版を
  **git で追跡している作業記録ファイル**に書き足していくこと — **コミットメッセージの下書きのように
  commit のたびに退避される一時ファイルには書かない** (git 管理外へ退避されたファイルは、
  セッションをまたぐと手元から消えて記録が途切れる)。
- **資金は書かない。** 資金源は上の §1 Funding に書く (Editorial Policies
  "Author conflicts of interest" が Funding 節を指定している)。
- **文法・スペルチェックの範囲を超える使い方は個別審査 (case-by-case) の側に落ちる。**
  それでも規定は開示を求めているので、**書かないという選択肢は無い**。
  ネイティブ確認 (要素 5) を同じ段落に書くと、規定の最後の要求に答えた形になる。
- **AI はオーサーになれない** (Editorial Policies "Authorship" の最終文)。著者一覧に入れないこと。
- 文例の `analyse` は英式綴り (§3 の注意を参照)。原稿の綴りに合わせて直す。
