# CLAUDE.md — AI アシスタント向けの要約

本ファイルは、このリポジトリで作業する人と AI のコーディング支援のための**規約の短い版**である。
使い方の詳細は `docs/usage-guide.md`、設計は `docs/architecture.md`、`profile.yaml` のキーは
`docs/profile-schema.md` にある。

## 概要

Markdown で論文を書き、投稿用の docx を生成する**テンプレートリポジトリ**。査読対応の全領域の差分ハイライト、
ベクター図 (SVG/PDF) の劣化のない docx 埋め込み、雑誌ごとの投稿規定への切り替えに対応する。
投稿先が変わっても雑誌プロファイル (`data/journals/<id>/`) を差し替えるだけで使い回せることを目指す。

同梱の雑誌プロファイルは `_default` (汎用の投稿フォーマット) と `bhi` (*BioHealth Informatics*) の 2 つ。
**テンプレートを特定の誌の専用にしない** — 誌固有の要件は `profile.yaml` のキーで吸収し、新しいキーは
すべて省略可能 (未指定なら従来どおりの動作) にする。

## 設計上の確定事項

| 項目 | 採用方式 | 理由 |
|------|---------|------|
| docx → PDF | **roundtrip のみ** (Google Drive → Windows の Word COM 変換。任意の機能) | 最終体裁の再現性を最優先する。LibreOffice での PDF 化は採用しない |
| ベクター図の挿入 | **ネイティブ SVG 埋め込み + PNG フォールバック** | PDF 図は SVG に変換して同じ経路に載せる。ベクター表示は Microsoft 365 / Office 2019 以降 (Office 2016 は PNG を表示する) |
| 全領域差分 | **構造保持 AST 差分 → 色ハイライト** | タイトル / 著者 / 抄録 / キーワード / 本文 / 表 / テキストボックスをすべて差分の対象にする。pandiff は使わない (Div・表・生 OOXML を壊すため) |
| 既定書式 (雑誌テンプレートが無いとき) | **汎用投稿フォーマット** | ダブルスペース・連続行番号・標準余白・Times 相当 12pt |

## 構成

```
.
├── src/                 # 原稿 (人が編集する一次ソース): main.md / ref.bib / figs/ (+ mermaid/)
│                        #   revise-report.md / cover-letter.md (任意)
├── main/                # パイプラインの段ごとの処理コード
│   ├── 00_setup/        #   共通設定 (defaults.yaml)・Lua フィルタ・lib/ (OOXML 操作・SVG 埋め込み・
│   │                    #     ラスタ化・pptx 生成・雑誌プロファイルの解決)
│   ├── step01_figures/  #   図の前処理 (SVG 修正 / PDF→SVG / SVG→PNG) + 解像度の検査
│   ├── step02_build/    #   main.md → docx (pandoc + 後処理) + 引用様式の検査
│   ├── step03_diff/     #   全領域差分 docx
│   ├── step04_pdf/      #   docx → PDF (roundtrip)。windows/ = Windows 側の watcher
│   └── step05_package/  #   投稿パッケージ (package.py)・提出構成の組み替え (relocate.py)・規定チェック (validate.py)
├── data/
│   ├── journals/        #   雑誌プロファイル: _default/ と bhi/ (bhi/skeleton/ = 原稿骨格)
│   ├── dummy/           #   動作例とフィクスチャ (git 管理)
│   ├── source/          #   本番の素材 (git 管理外)
│   ├── step01_figures/ step02_build/ step03_diff/   # 各段の中間・成果物 (git 管理外)
│   ├── output/          #   提出物の集約 (git 管理外)
│   └── products/        #   Word で変換した PDF (git 管理外)
├── docker/              # pandoc / mermaid / svg-conversion のコンテナ (ポートは公開しない)
├── scripts/             # 入口のスクリプト (build / diff / package / 検査 / roundtrip / 回帰スナップショット)
├── fonts/               # svg-conversion 用の専有フォント (git 管理外。利用者が置く)
└── docs/                # 詳しいガイド
```

## Step-by-Step Pipeline

- 各ステップの**コード**は `main/stepNN_name/` に置く。
- 各ステップの**中間・成果データ**は `data/stepNN_name/` に出す (コードとデータを分ける)。
- 提出物は `data/output/`、Windows で変換した PDF は `data/products/` に集める。
- 各ステップは単独で再実行できること。連番を保つ。

## 主なコマンド

```bash
docker compose -f docker/docker-compose.yml build    # pandoc イメージのビルド (mermaid / svg-conversion は初回に自動ビルド)

bash scripts/build.sh                                # 図の前処理 → docx (data/step02_build/main.docx)
bash scripts/diff.sh HEAD~1                          # 直前のコミットとの全領域差分 (data/step03_diff/main_diff.docx)
bash scripts/diff.sh old.md new.md                   # 任意の 2 版の差分
bash scripts/package.sh --journal _default --mode final   # 投稿パッケージ (data/output/<id>/)
bash data/journals/make-reference.sh <id>            # profile.yaml から reference.docx を作り直す

# BHI
bash scripts/build.sh   --journal bhi --article-type original
bash scripts/package.sh --journal bhi --mode final   # 図は 1 図 1 pptx、表は 1 表 1 docx (tables/)。凡例の集約・SUBMISSION.md・
                                                     #   CAPTIONS.md (Caption / Legend 欄に貼る文面)・規定チェック
bash scripts/package.sh --journal bhi --mode final --format png   # 図を 300 dpi PNG で出す
bash scripts/check-figures.sh --journal bhi                                        # 図ツリー (実画素数まで検算)
bash scripts/check-figures.sh --journal bhi --figures-dir data/output/bhi/figures  # 分離出力した図
bash scripts/build.sh --input data/dummy/bhi-csl --journal bhi                    # 引用様式の照合: フィクスチャをビルドして
bash scripts/check-csl.sh --docx data/step02_build/main.docx                       #   規定の出力例と docx の上付きを照合する

# 規定チェックだけを回す (ビルド不要)
docker compose -f docker/docker-compose.yml run --rm -u "$(id -u):$(id -g)" pandoc \
    python3 main/step05_package/validate.py --input-root data/dummy/bhi --journal bhi --article-type original

# PDF (任意。Windows 側の watcher が要る)
bash scripts/push-win-tools.sh     # Windows 側の 3 ファイルを Drive の送出先へ送る
bash scripts/check-pdf-path.sh     # 経路の診断 (読み取りのみ。--full で docx を 1 本往復)
bash scripts/roundtrip.sh          # data/output/*.docx → PDF (data/products/)。SUBMISSION.md を持つ提出パッケージは
                                   #   本文と表も PDF にし、パッケージ一式を Drive の submission-<journal>/ に置く
                                   #   (--no-package で使わない。動作例のパッケージは INPUT_ROOT=data/dummy/bhi を付ける)
```

## 原稿執筆の規約 (src/main.md)

- **Markdown 拡張構文** (Pandoc)。`--from markdown+east_asian_line_breaks`。
- **タイトル / 著者 / 所属 / 抄録 / キーワードは YAML メタではなく本文中の `custom-style` Div** で書く。
  構造保持 AST 差分がこれらを温存して中身を差分にするため (YAML メタは差分の対象にならない)。
  ```markdown
  ::: {custom-style="Title"}
  論文タイトル
  :::
  ```
- **引用**: `[@bibkey]`。文献は `src/ref.bib` (BibTeX) に集める。様式は雑誌プロファイルの CSL。
- **図**: `![キャプション](figs/foo.svg){#fig:foo}`、参照は `[@fig:foo]` (CJK の文中でも角括弧の形で書く)。
  題つきの図は **1 段落に 1 図**。
  - 草稿の段階では**図を docx に埋め込む** (共著者が見られるように)。
  - **PDF 図も原稿では `.svg` で参照する** (`figs/foo.pdf` を置き、本文は `figs/foo.svg`)。前処理が SVG に変換する。
    `.pdf` で参照すると埋め込みが壊れるので、ビルドがエラーで止める。
  - **SVG ルートの `width` / `height` は図の公称サイズ**で、docx 上の表示寸法と、ラスタ化するときの画素数
    (公称サイズ × 要求 dpi) の両方を決める。物理単位 (`160mm` / `144pt` / `2in`) ならそれが実寸、単位なしと
    `px` は **CSS px = 1/96 inch** とみなす。印刷したい幅より小さい公称サイズで作ると、その幅での実効解像度が
    要求 dpi を下回るので、**300 dpi を求める誌に出す図は物理単位で幅を書く**。見た目の大きさを変えたいときは
    原稿側で `{width=...}` を付ける。本文幅を超える図は pandoc が本文幅 (A4・余白 25 mm で約 159.8 mm) に縮める。
  - **自分で置いたラスタ図 (PNG / JPEG / TIFF) は解像度の保証の対象外**。そのまま複製されるので、解像度は
    執筆者が担保する (本文幅いっぱいで 300 dpi なら幅 1890 画素以上)。検査は不合格ではなく「注意」として出す。
  - **寸法を持たない SVG** は、草稿のビルドは警告つきで通るが、提出図の生成 (`--mode final`) はエラーで止まる。
  - **複数の SVG を 1 ファイルに連結しない**。多パネル図は作図側で 1 枚として出力する。svglite の出力を 2 つ入れた
    SVG は Word が文字だけを片方のパネルへ寄せ、連結で `id` が重複すると切り取り範囲を取り違える。ブラウザでも
    PNG でも正常に見えるので、`bash scripts/check-figures.sh` の「注意」と、roundtrip の PDF の拡大での目視で見つける。
    塗り・線の色を `hsl()` で書いた SVG も Word / PowerPoint が黒く塗るので同じ「注意」に出る。
  - **Mermaid 図**: `src/figs/mermaid/*.mmd` を置けば前処理が SVG / PDF にする (`.mmd` が一次ソース)。
    ラベルは SVG の `<text>` で出し、`hsl()` の色は生成時に 16 進へ直す。**別の道具で作った SVG を `figs/` に
    直接置くとこの後処理を通らない**ので、`.mmd` を置いてこの経路で作ること。
  - **最終提出図**: `docker/svg-conversion/convert.sh` の svg→pdf は文字をアウトライン化する (選択・検索はできなくなる)。
    埋め込みとアウトラインは `profile.yaml` の `figures.font_handling` で切り替える。
  - **図を PowerPoint で仕上げたいときは、図の隣に同名の `.pptx` を置く** (`figs/fig1.svg` + `figs/fig1.pptx`)。
    最終提出ではそれが無変換でコピーされる。1 ファイル 1 スライドで、マクロを含むものは拒否する。
- **テキストボックス (フロート図表)**: `.textbox` Div に `width/height/pos-x/pos-y/page/valign` 属性。
  中身は提出構成の組み替え (表の移設・凡例の集約) の対象外で、図表点数の上限検査からも外れる
  (外れた点数は規定チェックの概算行に必ず出る)。
- **表**: 既定は三本線 (booktabs)。全罫線が要るときは `.grid` Div。
- **数式**: LaTeX 構文 (`$...$` / `$$...$$`)。
- **生 OOXML**: 段組みの変更など細かい体裁は ```` ```{=openxml} ```` ブロックで入れる。

### 図表の題と凡例の書き分け

**題 = キャプション / 凡例 = 直後の `custom-style="Legend"` Div** と書き分ける。誌によって題と凡例の語数上限が
別々に決まっているが、pandoc のキャプションは 1 本しか付けられないため。

```markdown
![Processing pipeline from the record to the reviewed event list.](figs/fig-flow.svg){#fig:flow}

::: {custom-style="Legend" for="fig:flow"}
Rectangles denote processing stages. EHR, electronic health record.
:::
```

- 表も同じで、キャプション (`: 題 {#tbl:x}`) が題、直後の Legend Div が凡例。
- **Legend Div は対象の図 (画像段落) / 表の直後に置く**。`for` は対応先の明示で docx には出ない。Div の中で段落を
  分けてもよいが、対象の直後に連続して置く (提出構成の組み替えは「直後に連続する `Legend` 段落」を 1 組で動かす)。
- **凡例は段落だけで書く**。箇条書き・表・見出し・コードブロックなどを入れると pandoc が `Legend` 以外の段落スタイルを
  付け、そこで集約が止まって以降が本文に取り残される。規定チェックが要修正として指摘する。とくに次の 3 つは
  そのつもりがなくても書けてしまう:
  - **凡例を `(A)` や `a.` で始めない** — pandoc は番号つきリストとして読む。パネルの説明は
    `Panel A shows … Panel B shows …` のように文で書く。
  - **空行のあとを空白 4 個以上で字下げしない** — コードブロックになる。
  - **定義リストを使わない** — 略語の再定義は `EHR, electronic health record; ICU, intensive care unit.` のように文で書く。
- 凡例が要らない図表では Legend Div を省いてよい。
- 題の語数は執筆者が書いたキャプションだけを数え、pandoc-crossref が付ける `Figure 1: ` は含めない。

## BHI 投稿時の執筆規約

詳細と出典は `docs/journal-bhi.md`、投稿当日の確認は `docs/bhi-submission-checklist.md`。
**規定は変わりうるので、公式の [For Authors](https://biohealth-informatics.com/for-authors/) で確かめる。**
ここに挙げるのは、体裁ではなく**原稿の書き方に踏み込むもの**だけ。

- **骨格から書き始める**: `cp data/journals/bhi/skeleton/main.md src/main.md`。記入欄は `<<...>>`。
  記入済みの動作例は `data/dummy/bhi/` (`--input data/dummy/bhi` でビルドできる)。
- **節の順** (Original Article): Title page → Abstract → Abbreviations → Introduction → Methods → Results →
  Discussion → Conclusion → (Acknowledgments) → Declarations → References。図表は本文中の自然な位置に書く
  (`--mode final` が表を本文から外して 1 表 1 ファイルにし、図の題と凡例を References の後へ移す)。
- **抄録**: Original Article は Objective / Methods / Results / Conclusion の 4 ラベル・300 語以内・文献引用不可。
  ほかの種別の抄録は見出しの無い非構造化 (Letter は抄録なし)。本文の構成も、Review / Perspective / Tutorial は
  内容に合わせた自由な構成、Letter は見出しを立てない連続した文章になる (種別ごとの値は `profile.yaml` の `article_types`)。
- **本文語数**: 規定が上限から除くと書いているのは表・図 / 文献 / 図のキャプション。規定の文面だけでは決まらない部分は、
  本テンプレートは抄録と Abbreviations を除き、Declarations と Acknowledgments は数える (気になれば投稿前に編集事務局に確かめる)。
  図表の凡例 (Legend Div) は除外し、除外した語数は図 / 表に分けて内訳を出す。
- **Declarations** は 6 項目必須 (Funding / Authors' contributions (CRediT) / Data availability statement /
  Ethics approval and consent to participate / Consent for publication / Competing interests)。文例は
  `data/journals/bhi/skeleton/declarations.md`。
- **生成 AI ツールを使ったら原稿の中で開示する**。本テンプレートは `# Acknowledgments` 節に置き、ツール名・版・使途・
  著者が全内容に責任を負う旨・ネイティブによる最終確認を書く (文例は `declarations.md` の AI 使用の節)。
- **単位**: SI または SI 派生単位 (mmHg などの臨床で慣用の単位は可)。温度は `°C` (度記号 + 大文字 C の 2 文字) と書き、
  合成済み 1 文字の `℃` を使わない (`㎎` `㎏` などの合成 1 文字も同様。規定チェックが指摘する)。
- **機器・製品**: 型番 + 製造元 + 所在地 (市・州・国) を括弧内に書く。統計ソフトはバージョンも書く。
- **報告ガイドライン**: 研究デザインに応じたもの (STROBE / PRISMA / CONSORT-AI / STARE-HI / TRIPOD+AI など。
  基底は EQUATOR Network) に準拠する。
- **表**: 色・網掛け禁止、数値の桁区切りカンマ禁止 (`10 000` のように空白)。提出物では表は
  `tables/TableN.docx` に 1 表 1 ファイル (題 + 表 + 凡例) で出て、本文 `manuscript.docx` はテキストだけになる
  (規定は本文末尾・別ファイルのどちらも認めており、本テンプレートは別ファイルを既定にする)。
  投稿画面で上げたファイルごとの Caption / Legend 欄には、`data/output/bhi/CAPTIONS.md` の文面を貼る。
- **図**: 提出形式は JPEG / TIF / PNG / PowerPoint、300 dpi 以上 (PDF・EPS は不可)。本テンプレートは既定で
  1 図 1 pptx (ベクター) を出し、`--format png` で 300 dpi PNG に退避できる。多パネル図は 1 ファイルに合成し、
  凡例のキーは画像の中に入れる。
- **文献** (`src/ref.bib`): 誌名は Index Medicus の略誌名を `journal` に略記で持つ (CSL では正式誌名から略せない)。
  和文論文は `langid = {japanese}` を付ける (`(in Japanese)` が付く)。**英語の文献には `langid` を書かない** —
  `langid` があるだけで言語によらず `(in Japanese)` が付くので、書誌管理ソフトが付けた `langid = {english}` も消す
  (和文以外の非英語は `note = {in German}`)。題の固有名詞は波括弧で保護する
  (pandoc がセンテンスケースに直すため)。引用番号は `1)` を丸ごと上付きにする (規定は "superscript Arabic numerals in closing parenthesis" で、
  閉じ括弧まで上付きかは文面からは決まらない。本テンプレートは丸ごと上付きにする)。
  引用様式を変えたら、フィクスチャ `data/dummy/bhi-csl/` をビルドして `bash scripts/check-csl.sh --docx <その docx>` で
  規定の出力例と照合する (`docs/usage-guide.md` §4.1。原稿の docx を渡すと引用の件数が合わずに NG になる)。
- **補足資料**は `<入力ルート>/supplementary/` に置く。`--mode final` が無変換で複製し、`SUBMISSION.md` に一覧を出す。

## 雑誌プロファイル (data/journals/<id>/)

投稿先ごとに次を 1 セットで持つ。テンプレートを提供しない誌は `_default/` を複製して作る。

- `profile.yaml` — 図の要件 (形式・解像度)、行番号、行間、余白、題・見出しの級数と色 (`text_styles`)、
  表の置き場所 (`tables.placement`)、語数の上限、図表番号の書式など。キーの一覧と省略時の挙動は `docs/profile-schema.md`
- `<id>.csl` — 引用様式 (無ければ `_default` の AMA 系を継承)
- `reference.docx` — 体裁を焼き込んだ Word のテンプレート (`bash data/journals/make-reference.sh <id>` で生成)。
  pandoc の既定データから作る生成物なので同梱しない。`build.sh` / `diff.sh` が、`_default` のものと、`reference_doc` が
  `reference.docx` を指す対象誌のものを、無ければ自動で生成する。**`profile.yaml` の体裁を変えたら自分で作り直す**
  (古いままだと build と規定チェックが食い違いを警告する)
- `skeleton/` (任意) — 誌固有の原稿骨格 (ビルドの対象ではなく、写して書き始める雛形)

**記事種別** (`article_types`): 種別ごとに語数・抄録の要件が違う誌のために `article_types.<id>` を持てる。
優先順は `--article-type` > `profile.article_type` > (種別なし) `limits` そのまま。存在しない種別は一覧を出して止まる。

## データの置き場所

- 原稿の正本は常に `src/`。`data/source/` は本番の素材を置く git 管理外の補助領域、`data/dummy/` は自己検証用の
  完結したサンプル (`src/` と同じ構成)。
- **`.development` マーカーで入力ルートを切り替える**: 有り → `data/dummy/`、無し → `src/`。存在だけで判定する
  (`echo dev > .development` / `rm .development`)。環境変数 `INPUT_ROOT` か `--input <dir>` でも上書きできる。
- **開発時はまずダミーで動作を確かめる**。
- 一時ファイルは `jank/` に置く (git 管理外。`diff.sh` と回帰スナップショットもここを使う)。

## コンテナ運用の原則

- **テキストファイルの確認以外はコンテナの中で実行する**。ホストの Python は汚さない。
- ホストで Python を使ってファイルを見る必要があるときは **uv** で隔離する (`uv run --with <pkg> python ...`)。
- 変換処理は必ずコンテナ経由。コンテナはすべて変換専用 (常駐しない) なので、ポートは公開しない。
- イメージ名はプロジェクト名を前に付ける (`docx-paper-template-pandoc` など)。版を固定するのは pandoc / pandoc-crossref /
  panflute / lxml / mermaid-cli と、ベースイメージのタグ (ダイジェストではない) である。apt / apk のパッケージ
  (librsvg・LibreOffice・Inkscape など) は固定しておらず、イメージを作った時点の版になるので、作り直すと PNG の描画や
  読み込み検査の結果が変わりうる。pandoc と pandoc-crossref は組で更新する (片方だけ上げると crossref が動かない)。

## 変更するときの確認

- 回帰の確認: 変更の前後で `bash scripts/baseline.sh <接尾辞>` と `bash scripts/baseline-bhi.sh <接尾辞>` を撮り、
  `docker compose -f docker/docker-compose.yml run --rm -u "$(id -u):$(id -g)" pandoc python3 scripts/compare-snapshots.py <前> <後>`
  で比べる (docx は zip の部品ごとに内容で比べる)。diff の旧版は環境変数 `DIFF_REV` (既定 `HEAD~1`) で、
  比べる 2 つは同じ値で撮る。**clone した直後は `HEAD~1` に原稿が無い**ので `DIFF_REV=HEAD` を付ける
  (`DIFF_REV=HEAD bash scripts/baseline.sh <接尾辞>`)。
- `profile.yaml` に足すキーは省略可能にし、未指定なら従来どおりに動くようにする (既存の誌に回帰を起こさない)。
