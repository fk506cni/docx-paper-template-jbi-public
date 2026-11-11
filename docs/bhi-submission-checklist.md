# BHI 投稿前チェックリスト (bhi-submission-checklist.md)

*BioHealth Informatics* (BHI) へ Original Article を投稿する直前に、**人が 1 枚で確認するための表**である。
投稿系は ScholarOne (<https://mc.manuscriptcentral.com/bhi>)。規定の読み解きと実装の対応は
[`docs/journal-bhi.md`](journal-bhi.md)、執筆の開始から投稿までの手順は [`docs/usage-guide.md`](usage-guide.md) §8 にある。
本ファイルはそれらの要約ではなく、**投稿の当日に手を動かす順番**で並べ直したものである。

> 本テンプレートは雑誌・学会とは関係のない独立したツールである。**規定は変わりうるので、公式の
> [For Authors](https://biohealth-informatics.com/for-authors/) と
> [Editorial Policies](https://biohealth-informatics.com/editorial-policies/) で確かめること。**

## この表の読み方

各項目に次の印を付けてある。**印の意味を取り違えると、機械が見ていないものを見たつもりになる。**

| 印 | 意味 |
|----|------|
| 🤖 | **ツールが機械的に担保する。** 指定のコマンドを回して指摘が出なければよい。人が読み直す必要はない |
| 👁 | **人が目で見るしかない。** ツールは検出できない (判断が要る / 外部の情報が要る / 対象がファイルの外にある) |
| 📮 | **規定から決まらず、必要なら編集事務局に確かめる** (§9) |

> **🤖 が「規定に適合している」ことの証明ではない**項目がある。たとえば lint の `units: SI` は
> 「英米の慣用単位の綴りを拾う狭い検出器」であって、SI に準拠していることの証明ではない。
> 各項目の「限界」の欄にそれを書いてある。

---

## 0. 投稿の 2〜4 週間前にやること

**ここは全部 👁 である。** ツールを回しても催促されず、投稿日に気づくと間に合わないものばかりなので先頭に置く。

| | 項目 | 中身 | 出典 |
|---|------|------|------|
| 👁 | **ScholarOne のアカウント準備** | 連絡著者が <https://mc.manuscriptcentral.com/bhi> にアカウントを作り、投稿画面の**アップロード種別の実物**を確かめる。`SUBMISSION.md` の分類は**投稿規定に書かれた分類**から作っており、本テンプレートは実画面と照合していない (§8) | For Authors / Manuscript Submission |
| 👁 | **英文校正** | 規定は**英語の不備を査読前のリジェクトの対象と明記**している。英語を母語としない著者は、投稿前にネイティブチェックか英文校正を受ける。発注から納品まで 1〜2 週間を見込む | For Authors / English standards |
| 👁 | **ORCID iD の収集** | **持っている著者の分を集める。** 規定の原文は "Authors' full names and ORCID ID (if they have)" で、**取得は投稿の条件ではない**。持っている人の分を書き漏らさないよう先に集めておく | For Authors / Title page |
| 👁 | **APC と超過ページ料金の見込み** | **APC は無料**。ただし**刷り上がりが記事種別ごとの上限を超えると 1 ページあたり 2 万円 (+税)** の著者負担になる。上限は **Original Article で 9 typeset pages** (About ページの Table 1。ほかの種別は `docs/journal-bhi.md` §1)。刷り上がりのページ数は組版の後にしか分からないので**ツールは検査しない**。図表が多い原稿・Declarations が長い原稿は超えうると見込み、**超えたときにどうするかを投稿前に決めておく**。ライセンスは **CC BY 4.0** | [About](https://biohealth-informatics.com/about-biohealth-informatics/) |
| 👁 | **査読者推薦の要否** | 規定に記載が無い。ScholarOne の画面に欄があれば、当日に氏名・所属・E-mail が要る。上のアカウント準備のときに一緒に見ておく | — |
| 👁 | **報告ガイドラインのチェックリスト** | 研究デザインに応じたものに準拠する (基底は EQUATOR Network)。本誌が名指しするのは **PRISMA / CONSORT-EHEALTH / CONSORT-AI / SPIRIT AI / STARE-HI / TRIPOD+AI / SQUIRE / STROBE**。**系統的レビューの PRISMA だけは supplementary での提出が推奨と明示**されている | Editorial Policies "Reporting guidelines" |
| 👁 | **COI / License to Publish の回収を始める** | **共著者が多いほど日数がかかり、この節で最も長い作業になる。** **COI Disclosure Form も License to Publish も 1 通**で、**連絡著者が全著者を代表して記入する**。ただし COI は**全共著者の申告を集めて 1 通にまとめる**ので、共著者への聞き取りが要る。どちらも記入後に **PDF にして**アップロードする (様式の指示。署名欄は無い)。入手先と中身は §6、`docs/journal-bhi.md` §4.1 | For Authors / LTP・COI Forms |
| 👁 | **転載素材の許諾** | 著者自身の著作権下にない図表・素材を含むなら、**権利者 (既発表なら出版社も) の許諾を取る**。**許諾の写しは初回投稿時に原稿と一緒に出す**ので、投稿当日には間に合わない。該当が無いなら「無い」と確かめておく | Editorial Policies "Reproducing copyrighted material" (`docs/journal-bhi.md` §14.4) |
| 👁 | **使った AI ツールと版の記録** | 開示は**実際に使ったもの**でなければならない。執筆が長引くと途中で版が変わるので、**git で追跡している作業記録のファイル**に、使うたびに道具と版を書き足す (commit のたびに消える一時ファイルには書かない)。投稿の直前に §2 の開示文と突き合わせる | Editorial Policies "Use of AI tools" (`docs/journal-bhi.md` §14.3) |
| 👁 | **リバイス時のマークアップ原稿** | 初回投稿では**上げない**。要求されたら `bash scripts/diff.sh` で作れる (📮 §9) | — |

---

## 1. パッケージを作る (この 5 行で提出物が揃う)

```bash
bash scripts/build.sh     --journal bhi --article-type original     # 原稿 docx
bash scripts/diff.sh      --journal bhi <旧版の revision>            # 再投稿のときだけ (旧版をファイルで渡すなら
                                                                     #   <旧版.md> src/main.md の 2 つを並べる)
bash scripts/package.sh   --journal bhi --mode final                 # 提出物一式 + SUBMISSION.md + CAPTIONS.md
bash scripts/check-figures.sh --journal bhi                          # 図ツリー (実画素数まで検算)
bash scripts/check-figures.sh --journal bhi --figures-dir data/output/bhi/figures  # 提出する図
```

- `--input` は**原稿が `src/` に無いときだけ**足す (動作例を回すなら `--input data/dummy/bhi`)。
- `package.sh` の最後に**規定チェック (validate)** が自動で走り、結果は `data/output/bhi/SUBMISSION.md` の
  「規定チェック」節にも転記される。**画面のログは流れて消えるので、最終的な確認は `SUBMISSION.md` で行う。**
- Windows の Word で PDF にして体裁を見るときは `bash scripts/roundtrip.sh --skip-build` (`docs/usage-guide.md` §8.4)。
  提出パッケージ `data/output/bhi/` の本文と表も `bhi-manuscript.docx` / `bhi-Table1.docx` … の名前で PDF にし、
  PDF がそろうとパッケージ一式を Google Drive の `submission-bhi/` に置く。**`--skip-build` を必ず付ける** — 付けないと
  最初の段が `build.sh` を引数なしで回し直し、BHI の体裁の docx を `_default` の体裁で上書きする。パッケージが草稿モードで
  作られている・古い・今と別の入力ルートから作られている、のどれかなら何も送らずに止まる。

---

## 2. 原稿 (manuscript.docx)

### 🤖 ツールが担保する

| | 項目 | 担保するもの | 限界 |
|---|------|------------|------|
| 🤖 | 用紙 A4 / 余白 25.4 mm / Times 12 pt (題・見出し・抄録も 12 pt、見出しは黒) / ダブルスペース (題と著者の行も) / 連続行番号 / ページ番号 | `data/journals/bhi/reference.docx` (`profile.yaml` から生成。無ければ `build.sh` が作る。体裁を変えたら `bash data/journals/make-reference.sh bhi` で作り直す)。Word で開いたときの値は付録 | 投稿系が再変換したときの見え方までは保証しない。行番号は 1 から始まる |
| 🤖 | 本文語数・抄録語数・図表点数が記事種別の上限の内 | `validate.py` (`package.sh` が自動で回す)。8 種別で上限が切り替わる | **概算**である。編集室の数え方と一致する保証は無い。**文献数は BHI に上限の規定が無いので件数を出すだけで判定しない** (`limits.references: null`) |
| 🤖 | 本文語数から図表の凡例を除外し、内訳を出す | 同上 | **表の凡例も除外するのは本テンプレートの判断**で、規定に明示は無い (`docs/journal-bhi.md` §7.7)。編集室の数え方が違ったら内訳を足し戻す |
| 🤖 | 抄録が Objective / Methods / Results / Conclusion の 4 ラベルを**すべて**持つ | `validate.py` (誌が指定したラベルは全件必須) | ラベルの有無だけ。中身が対応しているかは見ない |
| 🤖 | 抄録に文献の引用が無い | `validate.py` (`abstract.citations_allowed: false`) | — |
| 🤖 | キーワードが 3〜5 語 | `validate.py` (`;` を優先して分割) | **MeSH から採ったか**は見ない → 👁 |
| 🤖 | タイトルが 30 語以内 | `validate.py` | 略語は「分野で一般的か」の判断が要るので**参考情報**どまり |
| 🤖 | Abbreviations 節が Abstract と Introduction の間にある | `validate.py` | — |
| 🤖 | Declarations の 6 項目が揃っている | `validate.py` (Funding / Authors' contributions / Data availability statement / Ethics approval and consent to participate / Consent for publication / Competing interests) | **見出しの有無**だけ。中身が規定を満たすかは見ない → 👁 |
| 🤖 | 連絡著者のブロックが 1 名分で、E-mail と Tel を持つ | `validate.py` (`lint.corresponding_author`) | **住所の全文**は国ごとに形式が違うので機械では判定しない → 👁 |
| 🤖 | 合成済みの 1 文字 (`℃` `㎎` など 11 種) を使っていない | `validate.py` (`lint.forbid_chars`) | — |
| 🤖 | 数値の桁区切りにカンマを使っていない | `validate.py` (`tables.thousands_separator: false`) | — |
| 🤖 | 骨格の記入欄 `<<...>>` が残っていない | `validate.py` (`main.md` / `cover-letter.md` の両方を見る) | — |
| 🤖 | References が本文の最終節である | `validate.py` | — |
| 🤖 | 末尾の並びが References → Figure Legends で、本文に図も表も入っていない | `relocate.py` が `--mode final` で組み替える (Figure Legends の前で改ページする。表は 1 表 1 ファイルに分ける) | `.textbox` の中身は動かない。References より前の節の並びは見ない (下の 👁) |

### 👁 人が目で見る

- [ ] **英語が米式・英式のどちらかに統一されている** (英文校正の納品物をそのまま入れたか)。
      **本誌の規定文書の綴りも一定しない**ので、雑誌に合わせても統一にはならない (`docs/journal-bhi.md` §14.3)。
      骨格の節名は `Acknowledgments` (米式)、`skeleton/declarations.md` の文例は `analysed` (英式) なので、
      **写すときに原稿の綴りに直したか**を見る
- [ ] **キーワード 3〜5 語が MeSH の統制語である** (MeSH ブラウザで実在を確かめる。語数だけは 🤖)
- [ ] **節の並びが Title page → Abstract → Abbreviations → 本文 → (Acknowledgments) → Declarations → References** である
      (ツールが見るのは Abbreviations の位置と References が本文の最終節であることだけ。Title page と Abstract の順・
      Declarations の位置は見ない)
- [ ] **タイトルの略語が「分野で一般的なもの」に限られている** (validate は参考情報として一覧を出すだけ)
- [ ] **タイトルの大文字の規則** — 各語の頭文字だけを大文字にし、接続詞・冠詞・前置詞は (先頭の語を除き) 小文字にしている
- [ ] **タイトルに数式と商品名が無い**
- [ ] **所属が「部門 + 機関 + 所在地 (市・州・国)」の形で、著者と上付きの番号で対応づけてある**
- [ ] **著者名に学位・肩書を書いていない** (フルネームと、持っていれば ORCID iD だけ)
- [ ] **臨床試験なら、登録番号と登録先の名前を原稿に書いている** (Editorial Policies `#04`。最初の患者を登録する時点までの
      公的な登録が投稿の条件。`docs/journal-bhi.md` §14.5)
- [ ] **連絡著者の住所が全文で書かれている** (機関名だけになっていないか)
- [ ] **Declarations の中身が規定を満たす** — とくに **Authors' contributions が CRediT の 14 分類**で書かれ、
      **全著者の承認と説明責任の文**を含むか。文例は `data/journals/bhi/skeleton/declarations.md`
- [ ] **CRediT を書き下すと数百語になる。** Declarations は**本文語数に算入される**ので、4,000 語の上限との
      兼ね合いを見る (刷り上がりの超過は 1 ページあたり 2 万円 +税で、費用に直結する)
- [ ] **Abbreviations の一覧で定義した略語を、図・表の凡例では改めて定義している**
      (凡例は本文から切り離されて末尾に並ぶので、一覧の定義が届かない)
- [ ] **未発表であり、他誌へ同時に投稿していない**

#### 👁 Acknowledgments と AI 使用の開示・Editorial Policies

> **ここに並ぶ 5 行はどれも `validate.py` が見ていない。** Editorial Policies (投稿規定とは**別の文書**) の
> 要求で、しかも「実際に何を使ったか」「誰が連絡著者か」「関連原稿があるか」という**原稿の外にある事実**と
> 照らし合わせるので、機械では判定できない。読み解きは `docs/journal-bhi.md` §14。

- [ ] **AI ツールを使ったなら `# Acknowledgments` 節がある** (Conclusion と Declarations の間)。
      規定は置き場所を指定していない ("in a suitable part of the manuscript") ので、本テンプレートは独立の節に
      置く。骨格 `data/journals/bhi/skeleton/main.md` に受け皿がある。
      **AI ツールを使っておらず、謝辞の相手もいないなら節ごと無くてよい** (必須の節ではない)
- [ ] **AI 使用の開示に 5 要素が揃い、実際に使ったものと一致している** —
      **① 道具名 ② 版 ③ 使途 ④ 著者が全内容に責任を負う旨 ⑤ ネイティブによる最終確認**。
      ① ③ ④ ⑤ は**規定の原文が求めている**もので、② だけは本テンプレートの上乗せ。
      **投稿の直前に作業記録 (§0) と突き合わせて、実際に使ったものに直す**。文例は
      `data/journals/bhi/skeleton/declarations.md` の §7。
      文法・スペルの確認を超える使い方 (構成の補助など) は、規定上**個別に審査される (case-by-case)** 側に入る。
      説明を求められる可能性を見込んでおく
- [ ] **連絡著者が確定している** — **受理後は連絡著者を変更できない**
      ("Changes of authorship … and/or changes in corresponding author … are not permitted after acceptance")。
      著者の追加・削除・著者順も同じ。**投稿後・受理前**の変更には全著者と編集者の承認が要る。
      共同筆頭著者は**原則 2 名まで**で、対等な貢献を原稿の中で明示する
- [ ] **関連原稿を開示した** — 他所で**審査中・印刷中・公開済み**の関連原稿 (学会の詳細な抄録・プレプリントを含む) が
      あれば編集者に知らせる (Originality の節の義務) → カバーレターに書く。
      **剽窃の検出 (Crossref Similarity Check) は人の判断より前に走る**ので、自分の先行公開と重なる範囲まで書いておく
- [ ] **転載素材があれば許諾の写しを添えた** — 著者自身の著作権下にない素材を含むなら、権利者 (既発表なら
      **出版社も**) の許諾を取り、原著を本文で引用し、**すべての許諾の写しを初回投稿時に原稿と一緒に出す**
      (後から集めればよいものではない)

---

## 3. 図 (figures/)

### 🤖 ツールが担保する

| | 項目 | 担保するもの | 限界 |
|---|------|------------|------|
| 🤖 | 図が本文から分離され、`[Figure N about here]` が残る | `package.sh --mode final` (`manuscript.docx` に画像は入らない) | — |
| 🤖 | 提出の形式が受入形式 (JPEG / TIF / PNG / PPTX) の中にある | `package.py`。**`--format pdf` は明示の同意 (`--allow-disallowed-format`) が無いと止まる** | — |
| 🤖 | ラスタ図が 300 dpi | `svg_raster.py` が公称サイズ × dpi で画素数を計算し、**実画素数を検算**して pHYs を書く。`bash scripts/check-figures.sh` で確かめ直せる | **「公称サイズで置いたときに 300 dpi」まで** → 下の 👁 を必ず読む |
| 🤖 | pptx にベクターの SVG と 300 dpi の PNG が同梱されている | `bash scripts/check-figures.sh --figures-dir …` が SVG 拡張の位置と同梱 PNG の pHYs を検査する | 分離出力した図には元の SVG が無いので**画素数の期待値は出せない** (実画素数の検算は図ツリーの検査が行う。**両方回すこと**) |
| 🤖 | 1 ファイル 1 スライド / マクロ無し (自分で pptx を置いた場合) | `svg_pptx.py` が枚数と `vbaProject` を検査して止める | 中身 (フォント・余白・凡例キー) は**検査の対象外** → 👁 |
| 🤖 | 寸法を書いていない SVG が提出図に混じらない | `--mode final` はエラーで止まる (草稿のビルドは警告どまり) | — |

### 👁 人が目で見る

- [ ] **各図の SVG が「印刷したい幅」を物理単位で持っている** — **図で最も見落としやすい項目である。**
      解像度の保証は「**公称サイズで置いたときに** 300 dpi」までで、雑誌が公称サイズより大きく組めば、実効解像度は
      その比で下がる。受入テストの「合格」はここを見ていない。
      **確かめ方**: `build.sh` / `package.sh` のログの `png:` の行を読む。
      - 良い例 (動作例 `data/dummy/bhi/`): `160mmx50mm [物理単位 mm] = 6.299x1.969 in @ 300dpi -> 1890x591 px`
        (BHI の本文幅 159.2 mm (A4 から左右の余白 25.4 mm を引いた幅) より 0.8 mm 広い。docx 上では pandoc の本文幅の扱いで 159.1 mm に縮むが、
        同じ画素数を狭い幅に置くので実効解像度は上がる側に働き、害は無い。縮めずに置きたいなら 159 mm 程度にする)
      - 危ない例: `460x140 [px/単位なし → CSS px (96dpi) とみなす] = 4.792x1.458 in` …
        公称 4.79 in の図を誌が 180 mm (7.09 in) で組むと、実効 **203 dpi** になる
      - **直し方**: SVG ルートの `width` / `height` を `width="180mm"` のように書く。`viewBox` はそのままでよい
        (比が合っていれば描画も縦横比も変わらない)
      - **注意**: 物理単位にすると docx 上の図がその実寸で置かれ、小さく見えることがある。見た目を保ちたいときは
        原稿側で `{width=...}` を付ける (この 2 つは対で使う)
- [ ] **自分で置いたラスタ図 (写真の PNG / JPEG / TIFF) の解像度** — **300 dpi の保証の対象外**。受入テストは
      不合格ではなく「注意」として一覧に出すだけである。本文幅いっぱい (約 6.3 in) に置くなら**幅 1890 画素以上**が要る。
      JPEG / TIFF は pHYs を持たないので、機械では判定もできない
- [ ] **多パネル図が 1 ファイルに合成され、余白が最小限に切り詰めてある** — **自動化されない**。スライドの寸法を
      図に合わせても、SVG の `viewBox` が描画内容より広ければ白い余白はそのままスライドに載る。
      **合成は作図側で 1 枚として出力して行う**。複数の SVG を後から 1 ファイルに連結すると、Word / PowerPoint で
      **文字だけが片方のパネルへ寄る** (svglite の出力 2 つ) / **切り取りの範囲を取り違える** (`id` の重複) ことがある。
      `bash scripts/check-figures.sh` (図ツリー) の「注意」に出たら作り直す
- [ ] **図の中の文字を Word / PowerPoint で拡大して確かめた** — Word / PowerPoint でだけ崩れる図は、体裁の計測でも
      解像度の検査でも見つからず、ブラウザでは正常に見える。Mermaid 図は本テンプレートの経路
      (`figs/mermaid/*.mmd`) で作ればラベルを SVG の文字で出し、`hsl()` の色を 16 進に直すが、**別の道具で作った SVG は
      この後処理を通らない**ので、`check-figures.sh` の「注意」を読む。roundtrip の草稿 PDF と pptx の両方で見る
- [ ] **凡例のキーが画像の中に入っている** (凡例の文章の側に書かない)
- [ ] **図が正しい向きでアップロードされている**
- [ ] **pptx の図を PowerPoint で開いて拡大し、ベクターとして耐えることを確かめた** — Microsoft 365 の PowerPoint では
      **SVG 側が描画され**、グループ化を解除すると文字の選択・編集もできる。**買い切り版の Office 2016 では
      PNG フォールバック側が表示される**。PNG 側が表示される環境での見え方は本テンプレートでは確かめていない (§9)
- [ ] **PowerPoint から PDF を作るときは「印刷」を使わない** — `Microsoft: Print To PDF` を通すと、ベクターも文字も
      すべてビットマップに潰れる (約 220 dpi)。「エクスポート → PDF/XPS の作成」を使う
- [ ] **既出の図を再録する場合、権利者の許諾を取り、凡例に明記し、出典を文献リストに載せた**
- [ ] **TIFF を求められた場合** — `--format tif` は **PNG で代わりに作る** (`FIGURES = 形式=tif [tif→png 代替]` と
      ログに出る)。TIFF をそのまま作る経路は持たないので、TIFF しか受け付けない状況では別の手段が要る
      (理由は `docs/architecture.md` §2.5)

---

## 4. 表 (`tables/TableN.docx`。1 表 1 ファイル)

### 🤖 ツールが担保する

| | 項目 | 担保するもの |
|---|------|------------|
| 🤖 | 表が本文から外れて `tables/TableN.docx` に 1 表 1 ファイルで出て (題が上・凡例が下)、本文の元の位置に `[Table N about here]` が残る。本文 `manuscript.docx` に表が入っていない | `relocate.py` + `package.py` (`tables.placement: separate`) |
| 🤖 | 表に網掛け・文字色・蛍光ペンが無い | `relocate.py` の体裁の lint (`tables.allow_color: false`。`w:shd` / `w:color` / `w:highlight` を検出する。表のファイルにも掛ける) |
| 🤖 | 数値に桁区切りのカンマが無い | `validate.py` |
| 🤖 | 題 15 語以内 / 凡例 300 語以内 | `validate.py` (題 = キャプション / 凡例 = 直後の `Legend` Div) |

### 👁 人が目で見る

- [ ] **表が画像になっていない** (Word の表のまま出す。規定は表の画像化を認めていない)
- [ ] **強調を色ではなく上付き・番号・記号・太字で行い、意味を凡例で説明している**
- [ ] **題が表の上・凡例が表の下**に来ている (pandoc の既定でそうなるが、最終の docx で目で見る)

---

## 5. 引用・文献 (References)

### 🤖 ツールが担保する

| | 項目 | 担保するもの | 限界 |
|---|------|------------|------|
| 🤖 | 文献リストの書式が規定の出力例と一致する | `bash scripts/check-csl.sh` が**規定に載っている出力例 5 件と 1 文字ずつ照合**する (残りの 4 件は本テンプレートが足した検証用。`docs/journal-bhi.md` §3.1) | 規定の例に無い型 (号つき / DOI の抑制など) の期待値は**実装の出力に合わせたもの**なので、独立した検証にはならない |
| 🤖 | 本文の引用番号が `1)` ごと上付きになっている | `bash scripts/check-csl.sh --docx <docx>` が docx の run を調べる。`--docx` に渡すのは**フィクスチャ `data/dummy/bhi-csl/` からビルドした docx** (`bash scripts/build.sh --input data/dummy/bhi-csl --journal bhi`) | 原稿の docx を渡すと引用の件数が合わずに NG になる。照合のあとで原稿をビルドし直す |

### 👁 人が目で見る

- [ ] **誌名が Index Medicus の略誌名で `src/ref.bib` の `journal` に入っている** — **CSL では正式誌名から略誌名へ
      変換できない。入力の側で略記にするしかない。** ここを間違えると全文献の書き直しになる
      (引き方は `docs/migration-latex.md` §4)
- [ ] **和文論文に `langid = {japanese}` が付いている** (出力に `(in Japanese)` が付く)。`language` フィールドは
      **pandoc に捨てられて効かない**。和文以外の非英語文献は `note = {in German}` のように書く
- [ ] **英語の文献に `langid` が付いていない** (`grep -n langid src/ref.bib` で和文の文献だけが出る)。`langid` があると
      言語によらず `(in Japanese)` が付く。書誌管理ソフトは英語の文献にも `langid = {english}` を付けて書き出すことが多い
- [ ] **題の固有名詞を BibTeX の波括弧で保護している** (`{Cancer Institute Hospital}`)。保護しないと pandoc が
      センテンスケースに直して、規定の出力例と食い違う
- [ ] **研究デザインに応じた報告ガイドラインに準拠している** (§0 の一覧)

---

## 6. 提出フォーム (アップロード種別ではない)

**入手先**: [For Authors](https://biohealth-informatics.com/for-authors/) の **「LTP/COI Forms」** の節
(中身の読み解きは `docs/journal-bhi.md` §4.1)。

- [ ] 👁 **COI Disclosure Form** — **1 通**。**連絡著者が全共著者の申告を集め、1 通にまとめて**記入し、
      **PDF に変換して**アップロードする。様式は全著者について正確であることを証明させるので、
      **記入の前に共著者全員の該当の有無を聞き取る**こと。申告の対象は**投稿前 24 か月**・**本人と配偶者その他の近親者**・
      **金額の閾値つきの 9 分類**。該当が無ければ「No」に印を付けるだけでよい
- [ ] 👁 **License to Publish** — **1 通**。**連絡著者が全共著者を代理して締結する**
      (様式の本文が *the Corresponding Author (acting on behalf of all co-authors)* と定めている)。
      **日付・全著者名・題を記入して PDF で**アップロードする (署名欄は無い)。ライセンスは **CC BY 4.0** で、
      **著作権は著者に残る**。締結は「未発表で他誌で審査中でない」「第三者の素材の書面の許諾を得ている」
      「共著者から代理の権限を得ている」の 3 点を保証する行為である

> 🤖 `SUBMISSION.md` の「6. 提出フォーム」にチェックボックスとして出る (通数と記入者は `profile.yaml` の
> `submission.forms` の注記がそのまま出る) が、**中身の回収はツールの外**である。共著者が多いほど時間が
> かかるので、§0 の段階で声を掛けておく。

---

## 7. 補足資料 (Supplementary)

- [ ] 🤖 `<入力ルート>/supplementary/` に置けば `data/output/bhi/supplementary/` へ**無変換で複製**され、
      `SUBMISSION.md` に一覧が出る。動画は **1 ファイル 50 MB** と受入形式 (MP4) を検査する
      (50 MB を超える mp4 や `.avi` は警告になる)
- [ ] 👁 **本文の中で、図表と同じく引用のかたちで言及している**
- [ ] 👁 **動画にも題を付けた** — 規定は *A title for each Table, Figure or Video must be included.* と、
      **表・図・動画のそれぞれに題**を求めている (Manuscript Submission の節)。表と図の題は語数まで機械で検査するが、
      **動画の題は本文か投稿画面に人が書くしかない** (本テンプレートはファイルを無変換で複製するだけなので、
      ファイルの側には現れない)
- [ ] 👁 **投稿の時点で最終形になっている** — 補足資料は**無変換で公開され、査読の対象で、受理後は変更できない**

---

## 8. ScholarOne での操作

> ⚠ **本節の対応づけは投稿規定に書かれた分類に基づくもので、ScholarOne の実画面とは照合していない。
> 実画面の表示が優先する。** 画面と食い違ったら `data/journals/bhi/profile.yaml` の `submission` ブロックを直す。

| アップロード種別 (規定の分類) | 出すファイル | 形式 |
|-----------------------------|------------|------|
| Text (原稿本体) | `manuscript.docx` | DOCX |
| Tables | `tables/Table1.docx`, `Table2.docx`, … (1 表 1 ファイル) | DOCX / XLSX / PPTX。**画像化は不可** |
| Figures | `figures/Figure1.pptx`, `Figure2.pptx`, … | JPEG / TIF / PNG / PPTX、300 dpi 以上 |
| Video | `supplementary/` の動画 | MP4、1 ファイル 50 MB 以内 |
| Supplementary | `supplementary/` のその他 | 無変換 |
| (フォーム) | COI Disclosure Form / License to Publish | 投稿系の指示に従う |

- [ ] 👁 **ファイルは Google Drive の `submission-bhi/` から選ぶ** (`roundtrip.sh` が置く。表と図は 1 階層に並ぶ)。
      送出先の直下や `processed/` には草稿の `main_…` と提出用の `bhi-manuscript_…` が時刻付きの名前で並ぶので、そこからは選ばない
- [ ] 👁 **表と図は番号の順にアップロードする** (`SUBMISSION.md` の「2. Tables」「3. Figures」の表の順)
- [ ] 👁 **上げたファイルごとの Caption / Legend 欄に `CAPTIONS.md` の枠の中身を貼る** (提出するファイルから抜き出した題と凡例。
      上付き・下付きは Unicode の文字に置き換えてあり、斜体・太字は貼ると消えるので項目の下の注記を見る。`CAPTIONS.md` 自体は上げない)
- [ ] 👁 **`cover-letter.docx`** は投稿画面のテキスト欄か添付で出す。カバーレターは
      (1) なぜ本稿が BHI に掲載されるべきか (2) 雑誌のポリシーに関わる論点 (3) 潜在的な競合利益の申告
      (4) 未発表で他誌へ同時に投稿していないことの確認、の 4 点を含めることが推奨されている (規定は "encouraged"。
      `docs/journal-bhi.md` §8)
- [ ] 👁 **`manuscript-diff.docx` は初回投稿では上げない** (査読対応の再投稿でだけ使う)
- [ ] 👁 **投稿系が作った校正刷り (PDF) を最後に必ず開く** — とくに次の 2 点は本テンプレートの管理の外なので、
      ここでしか見つからない:
      - **ページ番号が 1, 2, 3… と正しく振られているか。** docx のページ番号は `PAGE` フィールドで、
        **フィールドを計算し直さない変換器では全ページが `1` に見えうる** (Windows の Word では正しく振られる)
      - **pptx の図がベクターで出ているか、PNG フォールバック側になっているか** (§9)

---

## 9. 📮 規定から決まらないこと・確かめていないこと

規定の文面だけでは決まらない点を本テンプレートがどう扱うかは `docs/journal-bhi.md` §11 にまとめてある
(本文語数から除く範囲・引用番号の上付きなど。気になるものは投稿前に編集事務局に確かめる)。
**投稿前に決まっていないのは次の 2 件**である。

| 何が決まらないか | 影響 | どうするか |
|----------------|------|----------|
| **"Invited manuscripts are exempt from excess page fees." の「招待原稿」に何が当たるか** (About ページ。定義が無い) | 当たれば**超過ページ料金が掛からない** | 規定に定めが無い。**招待・推薦を受けて投稿し、上限を超えそうなときだけ**、必要なら編集事務局に確かめる |
| 査読対応の再投稿でマークアップ原稿 (差分版) を出すか | リバイスのときだけ | 規定に定めが無い。要求されたら `bash scripts/diff.sh` で作る |

加えて、**規定の問題ではないが、本テンプレートでは確かめられない**ものが 3 件ある。

| | 何が未確認か | どうするか |
|---|------------|----------|
| 👁 | **招待・推薦による投稿の案内の条件** (該当する場合だけ) | 学会・編集委員会などから投稿の案内や推薦を受けて投稿する場合、**規定には案内による投稿の記述が無い**。**案内の文面に条件 (締切 / 記事種別の指定 / 元の発表の扱い / 語数の緩和の有無) があり規定と食い違うなら、どちらに従うかを編集事務局に確かめる** (規定に案内による投稿の記述が無いので、どちらが優先するかは決まっていない)。案内を持っているのは投稿者なので、投稿者が読み合わせる。条件が書かれていなければ規定どおりに作る。カバーレターには**招待・推薦による投稿である旨と、元の発表との関係**を書く |
| 👁 | **ScholarOne の実画面のアップロード種別** (§8) | 投稿アカウントを作った時点で画面を見て、食い違えば `profile.yaml` を直す |
| 👁 | **PNG フォールバックが表示される環境での図の見え方** | LibreOffice も Microsoft 365 の PowerPoint・Word も **SVG 側**を表示するので、本テンプレートではこの経路の見え方を確かめていない。同梱の PNG が 300 dpi であることは機械で保証しているが、実際に表示されたときの見え方は**投稿後の校正刷りで確かめる**しかない |

---

## 付録: こう出れば正常 (動作例 `data/dummy/bhi/` での値)

動作例 `data/dummy/bhi/` を `--journal bhi --article-type original --input data/dummy/bhi` で通したときの値。
自分の原稿で桁が違ったら、どこかで入力が入れ替わっている。動作例は明らかなフィクションである
(出典は `docs/usage-guide.md` §9)。Word の値は、`docs/usage-guide.md` §8.4 の手順で組み替え済みの
`manuscript.docx` を Microsoft 365 の Word (16.0) で PDF にして測ったもの。

| 項目 | 値 |
|------|----|
| 最終提出 docx のページ数 (Word) | **10 ページ** (組版前の原稿のページ数。刷り上がりのページ数とは比べられない) |
| 用紙 / 左余白 / 本文 / 行送り (Word) | 210.0 × 297.0 mm / 25.4 mm / Times New Roman 12.0 pt (題・見出し・抄録も 12 pt) / 27.6 pt (題と著者の行も同じダブルスペース) |
| 行番号 / ページ番号 (Word) | **1〜172** (連続・欠番なし) / フッタに 1〜10 |
| 節の並び (Word) | p1 Title page → p2 Abstract → p3 Abbreviations・Introduction → p4 Methods → p5 Results → p6 Discussion → p7 Conclusion・Acknowledgements・Declarations → p8〜p9 References → **p10 Figure Legends** (表は本文に無い) |
| 上付き引用 | 本文に `1)` 形式で 5 件。CSL のフィクスチャ (`data/dummy/bhi-csl/`) では 16 件すべてが上付きで、9 件が期待値と一致 |
| 語数 (規定チェックの概算) | 本文 1 147 語 (凡例 204 語 = 図 163 / 表 41 を除外) / 抄録 263 語 / 文献 3 件 / 図 2 点・表 1 点 |
| 図 | `Figure1.pptx` (6.30 × 1.97 in / PNG 1890 × 591 px @ 300 dpi) / `Figure2.pptx` (5.98 × 3.15 in / PNG 1796 × 945 px @ 300 dpi) |
| 規定チェック | 要修正 0 件 / 参考 0 件 |
| 規定に合わないフィクスチャ `data/dummy/bhi-lint/` | 要修正 **23 件** / 参考 **4 件** (検査が発火することの確認用) |
| 表 | `tables/Table1.docx` (1 件。題が上・凡例が下。Word では 1 ページ・行番号なし・フッタ 1) |
| `CAPTIONS.md` | 3 項目 (Table 1 / Figure 1 / Figure 2) |
