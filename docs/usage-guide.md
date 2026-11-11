# 操作ガイド (usage-guide.md)

clone してから投稿パッケージを作るまでの手順をまとめる。設計と理由は [`docs/architecture.md`](architecture.md)、
`profile.yaml` のキーは [`docs/profile-schema.md`](profile-schema.md)、原稿の書き方の規約は [`CLAUDE.md`](../CLAUDE.md)、
差分の仕組みは [`docs/design-fullarea-diff.md`](design-fullarea-diff.md)、PDF 変換の Windows 側の配置は
[`docs/roundtrip-windows-watcher.md`](roundtrip-windows-watcher.md) にある。

> **BioHealth Informatics (BHI) に投稿するなら → [§8 BHI へ投稿する (通し手順)](#8-bhi-へ投稿する-通し手順)。**
> 執筆の開始から投稿までを 1 本につないである。投稿当日に 1 枚で確認する表は
> [`docs/bhi-submission-checklist.md`](bhi-submission-checklist.md)。
>
> **既存の LaTeX 原稿を書き起こすなら → [`docs/migration-latex.md`](migration-latex.md)。**

各スクリプトの入力ルート (`INPUT_ROOT`) は `.development` マーカーの有無で切り替わる:

| `.development` | 入力ルート | 用途 |
|---------------|-----------|------|
| 有り (`echo dev > .development`) | `data/dummy/` | 同梱のサンプル原稿で動作を確かめる |
| 無し (`rm .development`) | `src/` | 自分の原稿 |

環境変数 `INPUT_ROOT=...` か `--input <dir>` でも上書きできる (優先順は 環境変数 > `--input` > `.development`)。

---

## 0. 初回セットアップ

```bash
git clone <このリポジトリの URL> my-paper && cd my-paper
docker compose -f docker/docker-compose.yml build    # pandoc イメージをビルド
                                                     # mermaid / svg-conversion は初めて使うときに自動でビルドされる
echo dev > .development                              # まず同梱のサンプルで確かめる (入力ルート = data/dummy)
```

動作確認 (サンプルで通す):

```bash
bash scripts/build.sh                                # → data/step02_build/main.docx
bash scripts/package.sh --journal _default --mode draft   # → data/output/_default/
```

**雑誌の Word テンプレート `reference.docx` は同梱していない**。初めて `build.sh` / `diff.sh` を回したときに、
`_default` と、使う誌のものが pandoc の既定データと `profile.yaml` から自動で生成される
(`-- data/journals/<id>/reference.docx が無いので生成します` と表示される)。手で作り直すときは
`bash data/journals/make-reference.sh <id>`。生成物は何度作っても同じものになる。

---

## 1. 新しい論文を始める

```bash
cp -r data/dummy/. src/        # サンプル一式を src/ へ複製して雛形にする
rm .development                # 入力ルートを data/dummy → src に切り替える
$EDITOR src/main.md            # 自分の原稿に書き換える
```

**投稿先が BHI と決まっているなら、汎用サンプルではなく原稿骨格から始める** (§8.1)。骨格は必須節
(Title page / Abbreviations / Declarations 6 項目) を記入式で持つので、書き漏らしが起きない。

```bash
cp data/journals/bhi/skeleton/main.md         src/main.md
cp data/journals/bhi/skeleton/cover-letter.md src/cover-letter.md
#  Declarations 6 項目の文例は data/journals/bhi/skeleton/declarations.md (参照用。ビルドの対象外)
#  記入済みの動作例:  bash scripts/build.sh --journal bhi --article-type original --input data/dummy/bhi
```

> `cp -r data/dummy/. src/` は `data/dummy/` の下のサブディレクトリ (`bhi/` `bhi-csl/` `bhi-lint/` `regression/`) も
> 一緒に複製する。ビルドが読むのは `src/main.md` とそこから参照するファイルだけなので害は無いが、要らなければ消してよい。

`src/main.md` の要点 (詳しくは `CLAUDE.md` の「原稿執筆の規約」):

- **タイトル / 著者 / 所属 / 抄録 / キーワードは YAML メタではなく `custom-style` Div** で書く
  (構造保持 AST 差分がこれらを温存し、中身を差分にするため):
  ```markdown
  ::: {custom-style="Title"}
  論文タイトル
  :::
  ```
- 引用は `[@bibkey]`、文献は `src/ref.bib` に集める。
- 図の参照は `[@fig:foo]`、表の参照は `[@tbl:bar]` (日本語の文中でも角括弧の形で書く)。

---

## 2. 図を追加する

図のソースは `src/figs/` に置く。**本文からは常に `.svg` で参照する** (PDF 図も。前処理が SVG に変換するため)。

### 2.1 SVG 図 / PDF 図

```bash
cp my-figure.svg src/figs/fig-foo.svg     # PDF なら src/figs/fig-foo.pdf を置く
```

本文 (`.pdf` を置いた場合も `.svg` で参照する):

```markdown
![図のキャプション](figs/fig-foo.svg){#fig:foo}
```

- 前処理 (step01) が SVG の文字の切り取りを補正し、PDF を SVG に変換し、PNG フォールバックを作る。
  `.pdf` のまま参照すると埋め込みが壊れるので、ビルドがエラーで止める。
- ビルドは docx に **SVG をネイティブで埋め込む**。**Microsoft 365 / Office 2019 以降**はベクターで表示し、
  Office 2016 以前とその他のビューアは PNG フォールバックを表示する。
- **PNG フォールバックは要求 dpi (既定 300) を満たすように作られる**。SVG の公称サイズから必要な画素数を計算して
  ラスタ化し、実画素数を検算する (足りなければエラーで停止)。PNG には物理解像度 (pHYs) も書く。
  確かめるときは `bash scripts/check-figures.sh`。
- **SVG ルートの `width` / `height` は「図の公称サイズ」として 2 つのことを決める**: docx 上の表示寸法と、
  ラスタ化するときの画素数 (公称サイズ × 要求 dpi)。
  - 物理単位 (`160mm` / `144pt` / `2in`) で書けば、それがそのまま図の実寸になる。
  - 単位なしと `px` は **CSS px = 1/96 inch** とみなす (`320` → 3.33 inch)。
  - PDF 図は MediaBox の寸法 (pt) をそのまま公称サイズにする。
  - **印刷したい幅より小さい公称サイズで作ると、その幅で刷ったときの実効解像度が要求 dpi を下回る**。
    300 dpi を求める誌に出す図は、`width="160mm"` のように物理単位で幅を書くのが安全。
  - 物理単位で書くと docx 上の図はその実寸になる。見た目の大きさを変えたいときは原稿側で `{width=...}` を付ける
    (`![..](figs/fig-foo.svg){#fig:foo width=100%}`)。
  - 本文幅を超える図は pandoc が本文幅に縮める (A4・左右の余白 25 mm なら約 159.8 mm)。同じ画素数を狭い幅に
    置くので、実効解像度は上がる側に動く。
- **寸法を持たない SVG** (`width` / `height` も `viewBox` も無い) は、草稿のビルドは警告つきで通るが、
  提出図の生成 (`package.sh --mode final`) はエラーで止まる。SVG のルートに寸法を書けば直る。
- **ラスタ図 (PNG / JPEG / TIFF) を直接参照してもよい**: `src/figs/` に置き `![..](figs/photo.png){#fig:photo}` と書く。
  前処理は変換せずにそのまま使う。
  - **自分で置いたラスタ図は解像度の保証の対象外**である。そのまま複製されるので、解像度は執筆者が担保する。
  - `check-figures.sh` はこれらを**不合格ではなく「注意」として一覧に出す** (ツールでは作り直せないため)。
    PNG なら実画素数と pHYs を表示するので、`実画素数 ÷ 印刷したい幅 (inch)` が要求 dpi 以上かを確かめる。
    JPEG / TIFF は pHYs を持たないので機械では判定できない。
  - 目安: 本文幅いっぱい (約 6.3 inch) に置く図を 300 dpi にするには、幅 **1890 画素以上**が要る。
- **複数の SVG を 1 ファイルに連結しない**。多パネル図は作図側で 1 枚として出力する (R なら cowplot / patchwork などで
  まとめてから 1 回だけ書き出す)。次の 2 つは SVG としては正しく、ブラウザでも PNG でも正常に見えるのに、
  Word / PowerPoint では崩れる:
  - **svglite の出力を 2 つ入れた SVG** (`<g class='svglite'>` が 2 個以上) — Word が文字だけを片方のパネルの位置に
    寄せて描く (図形は正しい位置のまま)。包み方を変えても直らない。
  - **SVG の中で `id` が重複している** — svglite の `clipPath` の `id` は座標から作られるので、寸法を揃えた 2 つの出力を
    連結すると一致し、片方のパネルが誤った範囲で切り取られる。

  `check-figures.sh` (図ツリー) はこの 2 条件を「注意」として出す。**それ以外の崩れ方は検出できないので、
  roundtrip の PDF (§6) や PowerPoint で図を拡大して目で見ること**。
- **塗り・線の色を `hsl()` で書いた図形は Word / PowerPoint で黒くなる**。CSS のクラスで塗っても `fill` 属性に
  書いても同じで、色の書き方が原因である (16 進 `#rrggbb` なら正常)。本テンプレートの Mermaid の経路 (§2.2) は
  16 進に直してから出す。別の道具で作った SVG を置いた場合は `check-figures.sh` が「注意」に出すので、色を 16 進で
  書き直す。
- **番号つきの図 (`{#fig:..}`) は 1 段落に 1 図**で書く。1 段落に番号つきの図を複数置くと、pandoc-crossref が
  図として扱わず、参照が `Undefined cross-reference` になる (番号の要らない装飾画像は同じ段落に複数置いてよい)。
- **題と凡例を分けたいとき**は、キャプションを題 (短い一文) に留め、凡例を直後の Div に書く
  (`CLAUDE.md` の「図表の題と凡例の書き分け」)。題と凡例に別々の語数上限がある誌 (BHI は題 15 語・凡例 300 語) では
  必須。表も同じ書き方で、docx では題が表の上・凡例が表の下に出る。
  ```markdown
  ![Processing pipeline from the record to the reviewed event list.](figs/fig-foo.svg){#fig:foo}

  ::: {custom-style="Legend" for="fig:foo"}
  Rectangles denote processing stages. EHR, electronic health record.
  :::
  ```
  - **凡例は段落だけで書く**。とくに**多パネル図の凡例を `(A) …` で始めない** — pandoc は段落の先頭の
    `(A)` / `A)` / `a.` / `(i)` などを番号つきリストとして読むので、凡例が `Legend` 段落にならず、
    最終パッケージで Figure Legends へ集められずに本文に取り残される。パネルの説明は
    `Panel A shows … Panel B shows …` のように文で書く。`package.sh` の規定チェックが要修正として出す。

### 2.2 Mermaid 図 (フロー図・構成図)

```bash
$EDITOR src/figs/mermaid/flow.mmd          # .mmd が一次ソース
```

本文からは生成される `.svg` を参照する (前処理が `.mmd` から SVG と PDF を作る):

```markdown
![システム構成図](figs/mermaid/flow.svg){#fig:arch}
```

`.mmd` から作った SVG / PDF は作り直せるので git では追跡しない (`.gitignore`)。ビルドの前処理が毎回 `.mmd` から作るので、
**ふだんは単独で描かなくてよい**。見た目だけを確かめたいときは、`.mmd` を `jank/` などへ写してそこで描く
(`bash docker/mermaid/convert.sh jank/flow.mmd both`。同じ名前の出力が既にあると止まるので、描き直すときは `--force`)。
`figs/mermaid/` の中で単独に描いた `.svg` / `.pdf` が残っていても、前処理は同じ名前の `.mmd` から作り直した図を使い、
残骸を読み飛ばして「単独描画の残骸を無視しました」と警告する (残骸は消してよい)。

- **ラベルは SVG の文字 (`<text>`) で出す**。HTML のラベル (`foreignObject`) は Word と PNG フォールバックで消える
  (ブラウザでは正常に見える) ため、`docker/mermaid/config.json` の最上位に `"htmlLabels": false` を置いてある。
  `config.json` を書き換えるときもこの行は消さないこと (`convert.sh` は生成した SVG に `foreignObject` が残っていると
  警告する)。
- `config.json` は `convert.sh` が実行時に読み込むので、書き換えてもイメージの再ビルドは要らない。
- **テーマの色は変えてよい**。Mermaid は色を変えるとサブグラフの枠などの色を `hsl()` で出すが、`convert.sh` の後処理
  (`docker/mermaid/postprocess-svg.js`) が 16 進に直す。**Mermaid Live などで作った SVG を `figs/` に直接置くと
  この後処理を通らない**ので、`.mmd` を `figs/mermaid/` に置いてこの経路で作ること。
- ラベルが箱の中心より少し下に見えることがある。Mermaid のラベル配置そのもので、ブラウザでも Word でも同じに見える。

### 2.3 確認

```bash
bash scripts/build.sh
# ログに「SVG ネイティブ埋込: ... -> word/media/svgN.svg」が図の数だけ出れば埋め込めている
bash scripts/check-figures.sh                    # PNG フォールバックの画素数を SVG の公称サイズから検算する
```

---

## 3. 差分を出す (査読対応)

`scripts/diff.sh` は**論文の全領域** (タイトル / 著者 / 抄録 / キーワード / 本文 / 表 / テキストボックスの中の表) を
構造保持 AST 差分で突き合わせ、追加 = 青・削除 = 赤の取り消し線の docx を作る。

```bash
# 直前のコミットとの差分 (旧版 = HEAD~1 の main.md、新版 = 作業ツリー)
bash scripts/diff.sh HEAD~1

# 任意の revision との差分 (初回投稿時のタグなど)
bash scripts/diff.sh v1-submitted

# 明示した 2 ファイルの差分 (どちらも実在するファイル)
bash scripts/diff.sh old.md src/main.md
#  → data/step03_diff/main_diff.docx
```

- revision の形で使うには、`<入力ルート>/main.md` がその revision に存在している必要がある (新しく作ったファイルは
  2 ファイルの形を使う)。初回投稿の版にタグを付けておくと、改訂のたびに同じ旧版と比べられる。
- 図は新版の図ツリー、文献は新版の `ref.bib` で解決する。
- 既知の制限 (詳しくは `docs/design-fullarea-diff.md`): 段落の「移動」は削除 + 追加として出る。コードブロック・
  水平線・生 OOXML・見出しレベルだけの変更は着色せず新旧を併記する。数式は式ごとの削除 + 追加になる (ラベルつきの
  式への参照が壊れうる)。表の列の増減では後ろの列がずれうる。引用番号・相互参照番号・文献リストは再生成され、
  差分にはならない。**語の間に空白の無い言語 (日本語など) の本文は、変更が語単位ではなく句ごとの削除 + 追加になりうる**
  (英語の本文は語単位)。
- リバイスレポートは `src/revise-report.md` に書けば、`build.sh` が同じ仕組みで docx にする。

---

## 4. 新しい投稿先 (雑誌) を追加する

投稿規定はプロファイルに閉じ込め、本文 (`src/main.md`) は雑誌に依存させない。例として架空の誌
`example-journal` を足す:

```bash
mkdir data/journals/example-journal
cp data/journals/_default/profile.yaml data/journals/example-journal/   # 1. 雛形の profile.yaml を写す
$EDITOR data/journals/example-journal/profile.yaml                      # 2. 投稿規定に合わせて書き換える
bash data/journals/make-reference.sh example-journal                    # 3. 体裁を焼き込んだ reference.docx を作る
bash scripts/build.sh --journal example-journal                         # 4. その誌の体裁でビルドする
```

- 2 では `name` と、体裁 (`line_spacing` / `line_numbers` / `page_numbers` / `font` / `font_size` / `margins` /
  `paper_size` / `text_styles.*`)・図 (`figures.*`)・表 (`tables.*`)・上限 (`limits.*`) を規定に合わせる。キーの一覧と省略したときの動きは
  [`docs/profile-schema.md`](profile-schema.md)。
- `csl:` は、誌の引用様式の CSL を `data/journals/example-journal/` に置いたらそのファイル名、無ければ `null` にする。
  `null` だと `_default` の AMA 系を継承し、build / diff が毎回「csl 未指定。_default (AMA 11th) を継承します」と知らせる
  (規定と違う引用様式のまま提出しないため)。CSL の照合は §4.1。
- 3 は省いてもよい。`reference_doc: reference.docx` (雛形のまま) なら、ファイルが無いときに build / diff が自動で作る。
- **体裁は `reference.docx` に焼き込まれる**。`profile.yaml` の体裁を後から変えたら、**3 を回し直す**。回し直さないと
  build と規定チェックが「`reference.docx` の体裁が `profile.yaml` と食い違っています (line_spacing: profile=1.5 !=
  reference.docx='double')」のように警告する。
- 雑誌が Word のテンプレートを配っているなら、それを置いて `reference_doc:` にそのファイル名を書く
  (`reference_doc: publisher-template.docx`)。この場合は自動生成されない。差分の色のスタイルは差分の後処理が
  毎回足すので、配られたテンプレートが持っていなくてよい。

`profile.yaml` の主なキー (全項目は `docs/profile-schema.md`):

| キー | 例 | 説明 |
|------|-----|------|
| `line_spacing` / `line_numbers` | `double` / `continuous` | 行間 / 行番号 (`reference.docx` に焼き込む) |
| `page_numbers` | `true` | フッタの中央にページ番号を入れる (既定 `false`。`reference.docx` に焼き込む) |
| `font` / `font_size` / `margins` / `paper_size` | `"Times New Roman"` / `12pt` / `25mm` / `a4` | 体裁 (`reference.docx` に焼き込む) |
| `text_styles.uniform_size` / `heading_color` / `uniform_line_spacing` | `true` / `black` / `true` | 題・見出し・抄録も本文の級数にそろえる / 題・見出しのテーマ色を外す / 段落スタイルごとの行送りを外す (省略すると pandoc の既定のまま。`reference.docx` に焼き込む) |
| `figures.embed` | `true` / `false` | `package.sh` の既定のモード。`true` → 草稿 (図を埋め込む) / `false` → 最終 (図を分離) |
| `figures.formats` | `[pdf]` / `[pptx, png, tif]` | 最終提出の図の形式。先頭が主形式。作れるのは `pdf` / `png` / `pptx` |
| `figures.dpi` / `figures.font_handling` | `300` / `outline` | ラスタ図の解像度 / PDF 図の文字の扱い (`outline` = アウトライン化 / `embed` = 埋め込み) |
| `tables.placement` | `inline` / `end` / `separate` | 最終モードで表を本文に残す / 本文の末尾へ移す / 1 表 1 ファイルで出す (§5.3) |
| `limits.word_count` / `abstract_words` / `references` | `4000` / `250` / `null` | 規定チェックの上限 |
| `abstract.structured` | `true` / `false` | 構造化抄録か |
| `numbering.figure` | `"Figure %d."` | 図の番号の書式。分離した図のファイル名にも使う (`Figure1.pdf`) |

**必須節の多い誌には原稿骨格 `skeleton/` を添えられる** (任意)。ビルドの対象ではなく、執筆の出発点として写して使う
雛形である (`cp data/journals/<id>/skeleton/main.md src/main.md`)。同梱の例は `bhi/skeleton/`
(`main.md` / `cover-letter.md` / 文例集 `declarations.md`)。

### 4.1 引用様式 (CSL) を自前で用意したときの確認

引用様式の食い違いは目で見ても気づきにくく (閉じ括弧の上付きの落ち・ページ範囲の桁・`et al` の閾値など)、
規定と違うと全文献の書き直しになる。規定に**出力例が載っているなら機械で照合する**。

```bash
# フィクスチャ: <dir>/{main.md, ref.bib, expected.txt} の 3 点
#   expected.txt = 規定の出力例を 1 行 1 文献で写したもの (# で始まる行はコメント)
bash scripts/check-csl.sh --journal <id> --fixture data/dummy/<id>-csl

# docx の OOXML まで見る (上付きなど、文字列の比較では分からない体裁)
bash scripts/build.sh --input data/dummy/<id>-csl --journal <id>
bash scripts/check-csl.sh --journal <id> --fixture data/dummy/<id>-csl --docx data/step02_build/main.docx
```

BHI の実例が `data/journals/bhi/bhi.csl` + `data/dummy/bhi-csl/` にある (`--journal` と `--fixture` の既定はこの 2 つ)。
食い違ったときは、文字列の差を行内の差分とコードポイントで表示する。`--docx` には**フィクスチャからビルドした docx** を渡す
(原稿の docx を渡すと、引用の件数がフィクスチャと合わずに NG になる)。

**`ref.bib` の側で気をつけること** (pandoc の BibTeX の読み方による。自動化できない):

- 誌名は雑誌が指定する形 (BHI なら Index Medicus の略誌名) で `journal` に**直接**書く。CSL には正式誌名から
  略誌名への変換が無い。
- 題の固有名詞は**波括弧で保護**する (`{Cancer Institute Hospital}`)。保護しないと、pandoc が英語の題を
  センテンスケースに直して規定の例と食い違う。
- 和文の文献には **`langid = {japanese}`** を書く (BibTeX の `language` は pandoc に捨てられる)。
  `langid` はセンテンスケースへの正規化も止める。
- **英語の文献には `langid` を書かない**。`bhi.csl` は `langid` (pandoc が CSL の `language` に写す) が**あるだけで**、
  言語によらず `(in Japanese)` を付ける。書誌管理ソフト (Zotero / Better BibTeX など) は英語の文献にも
  `langid = {english}` を付けて書き出すことが多いので、和文以外の文献からは消しておく。和文以外の非英語の文献は
  `langid` ではなく `note = {in German}` のように書く (`docs/journal-bhi.md` §3.2)。

---

## 5. 投稿パッケージを作る

雑誌プロファイルに従って提出物を整形・命名し、`data/output/<id>/` に集める。

```bash
# 雑誌の体裁を本文に反映するため、先にその誌でビルドする
bash scripts/build.sh --journal <id>

# 草稿パッケージ (図を docx に埋め込んだまま)
bash scripts/package.sh --journal <id> --mode draft

# 最終提出パッケージ (図を分離: 本文には [Figure N about here] を残し、図は figures/ に出す)
bash scripts/package.sh --journal <id> --mode final
#  → data/output/<id>/ に manuscript.docx / figures/ / revise-report.docx / cover-letter.docx
#     (+ 差分があれば manuscript-diff.docx。誌によっては SUBMISSION.md と supplementary/)
```

- `--build` を付けると前段のビルドも一緒に回す: `package.sh --journal <id> --mode final --build`。
- `--mode` を省くと `profile.figures.embed` で決まる (`true` → draft / `false` → final)。
- `package.sh` は**ビルドしたときの誌**を覚えていて、`--journal` と違えば警告する (別の誌の体裁の docx を提出しないため)。
- `.textbox` の中の図は分離せず、本文に残す (テキストボックスは本文の流れの外に置くフロート図表のため)。

### 5.1 図の形式

- 主形式は `figures.formats` の先頭 (`--format` で上書きできる)。**作れるのは `pdf` / `png` / `pptx` の 3 つ**で、
  `eps` → pdf / `tiff` → png は**警告つきで代わりに作る**。それ以外 (綴りの誤りを含む) は**エラーで止まる**
  (作れない形式を黙って別の形式にしない)。代わりの形式が誌の受入形式 (`submission.figure_formats`) に無ければ、それも止まる。
- 受入形式外の形式を `--format` で明示したときも止まる (`png` と `pdf` の打ち間違いで規定違反の図一式が揃うのを防ぐため)。
  承知のうえで出すには `--allow-disallowed-format` を付ける。
- **`pdf`**: SVG を `svg-conversion` コンテナで PDF にする (`figures.font_handling: outline` なら文字をアウトライン化。
  初回は `svg-conversion` イメージのビルドが走る)。Mermaid 図は Mermaid の経路で作った PDF をそのまま使う。
- **`png`**: SVG の公称サイズから `figures.dpi` (または `--dpi`) を満たす画素数で作り、pHYs を書く。
- **`pptx`**: **1 図 = 1 pptx = 1 スライド**で、SVG をベクターのまま埋め込み、PNG フォールバックを同梱する
  (この経路を本テンプレートでは**案 B** と呼ぶ。ログにもこの名前で出る)。BHI の既定の主形式。
  - Microsoft 365 / Office 2019 以降の PowerPoint では SVG 側が描画され、グループ化を解除すると文字の選択・編集もできる。
    Office 2016 以前では PNG フォールバックが表示される (同梱する PNG は要求 dpi を満たす)。
  - **図の隣に同名の `.pptx` を置くと、それを無変換でコピーする** (**案 A**。PowerPoint で仕上げた図を劣化なしに出す)。
    原稿はそのまま同名の `.svg` をプレビューとして参照する (`figs/fig1.svg` + `figs/fig1.pptx`)。
    **1 ファイル 1 スライド**にすること (2 枚以上は止まる)。マクロを含むファイル (`.pptm` / `vbaProject` 入り) は拒否する。
    中身はテンプレートの検査の対象外になるので、フォント・余白・凡例のキーは PowerPoint で自分で確かめる。
  - **元がラスタの図 (`.png` など) は pptx に包まず、画像ファイルのまま出す**。
  - 図の公称サイズが **1 inch 未満**の軸は、PowerPoint の規格の下限までスライドを広げて図を中央に置く
    (足した余白は警告に出る)。**56 inch を超えるとエラーで止まる**ので、SVG の寸法を直すか `--slide-fit fixed`
    (既定のスライドの大きさに縮めて置く) を使う。
  - `--format png` への切り替えはいつでも効く。
  - PowerPoint から PDF を作るときは「印刷」ではなく「エクスポート → PDF/XPS の作成」を使う。`Microsoft Print to PDF`
    を通すと、ベクターも文字もビットマップになる。

### 5.2 図の解像度を確かめる

`check-figures.sh` には守備範囲の違う 2 つのモードがある。**提出前は両方を回す**。

```bash
bash scripts/check-figures.sh --journal <id>                                    # 図ツリー
bash scripts/check-figures.sh --journal <id> --figures-dir data/output/<id>/figures   # 分離出力した図
```

- **図ツリー** (`data/step01_figures/figs`。`--tree` で変えられる) — SVG の公称サイズから期待する画素数を出し、
  **実画素数まで検算**する。解像度の確認はこちらが本体。
- **分離出力した図** (`--figures-dir`) — ここには元の SVG が無いので期待する画素数を出せず、**pHYs (PNG に書かれた
  申告解像度) の確認だけ**になる。pptx 図は書庫を開き、SVG 拡張の位置・SVG 本体と PNG フォールバックの同梱・
  同梱 PNG の pHYs を検査する。
- 目標 dpi の優先順は `--dpi` > `--journal` の `figures.dpi` > 300。実行時にどこから採ったかを表示する。
- 自分で置いたラスタ図は「注意」として一覧に出る。終了コードには影響しないが、合格の件数にも入らないので、内容を読むこと。
- `bash scripts/check-figures.sh --self-test` は、この検査自体に識別力があるか (わざと壊した pptx を落とせるか) を確かめる。

### 5.3 提出構成の組み替え (最終モード)

原稿 (`src/main.md`) は図表を本文中の自然な位置に書いたまま雑誌に依存させず、「表は末尾 (または別ファイル)」「図の題と凡例は
References の後」という誌の要求は、提出物を作るときに満たす。`--mode final` かつ `--keep-figures` なしのときだけ動き、
何をするかは `profile.yaml` で決まる (BHI は両方とも有効)。

- `tables.placement: end` → 本文中の表を「題 + 表 + **直後に連続する `Legend` 段落すべて**」の 1 組として
  **文書の末尾へ**移し、元の位置に `[Table N about here]` を残す。
- `tables.placement: separate` → 同じ 1 組を**本文から外し**、`data/output/<id>/tables/TableN.docx` に **1 表 1 ファイル**で
  出す (題が上・凡例が下)。元の位置には `[Table N about here]` を残し、本文の docx はテキストだけになる。表のファイルは
  組み替えた本文と同じ書庫から作るので、スタイル・フッタが本文と同じになる。行番号は `line_numbers_scope: manuscript` なら
  外す。BHI はこちらが既定 (規定は本文末尾と別ファイルのどちらも認める。別ファイルなら本文がテキストだけになり、
  どちらの読み方にも合う)。`tables.placement` の値の綴りを誤るとエラーで止まる。
- `figures.legends_section: "Figure Legends"` → 「図の題 + **直後に連続する `Legend` 段落すべて**」を References の後の
  **新しいページ**の見出しの下へ集める。画像の段落は `[Figure N about here]` として本文に残る。
- **`.textbox` の中身は動かさない** (本文の流れの外にあるため)。
- 並びは **References → Figure Legends → 表** (`separate` では表が本文に無いので References → Figure Legends で終わる)。
  図表番号が本文の初出順と一致するか、題の無い画像が混ざっていないかを検算し、ずれがあれば注意を出す。
- 本文の相互参照 (`Fig. 1` / `Table 1`) は、移した後もプレースホルダの位置へ飛ぶ。`end` で末尾に並べた表どうしは、Word が
  1 つの表に結合しないよう間に空の段落を挟む。
- 草稿モードや `--keep-figures` では組み替えない。profile が要求しているのに組み替えなかったときは注意に出すので、
  提出物を作るときは `--mode final` をそのまま回す。
- **`tables.allow_color: false` の誌では、表の網掛け・文字色・蛍光ペン・罫線の色を検出して警告する** (草稿モードでも)。
  数値の桁区切りカンマは Markdown の層の規定チェック (§5.6) が見る。
- **カバーレターから行番号を外せる** (`line_numbers_scope: manuscript`)。行番号は査読者が本文の位置を指すためのものなので、
  BHI では `main.md` だけに付く。ページ番号は残る。
- 提出物は roundtrip がそのまま Word に回す (§8.4)。`SUBMISSION.md` を持つ提出パッケージの本文と表は、`roundtrip.sh` が
  `<id>-manuscript.docx` / `<id>-Table1.docx` … の名前で集めて PDF にし、パッケージ一式を Drive の `submission-<id>/` に置く。

### 5.4 提出マニフェスト `SUBMISSION.md`

`submission.text_formats` を持つ誌 (同梱では BHI) には `data/output/<id>/SUBMISSION.md` が出る。投稿系のアップロードの
種類 (Text / Tables / Figures / Video / Supplementary) ごとに、**ファイルの一覧・順序・形式・サイズ**と、別途提出する
フォーム (`submission.forms`) のチェック欄を並べる。**投稿画面を開く前にこれを 1 枚見れば、何をどの欄に上げるかが決まる**。

- **図は「Figures」の表の順に、表は「Tables」の表の順にアップロードする** (`tables.placement: separate` のとき)。この順は
  本文の初出順で、表の `#` 列が本文の図番号・表番号と一致する。投稿系は上げた順に番号を割り当てるので、並べ替えない。
- **投稿画面の Caption / Legend 欄に貼る文面は `CAPTIONS.md` に出る** (`SUBMISSION.md` を書く誌だけ)。ファイルを上げる画面
  (File Upload) は、上げたファイルごとに書式なしの Caption / Legend 欄を持つ。`CAPTIONS.md` は**提出するファイルそのもの**
  (`manuscript.docx` の Figure Legends 節と `tables/*.docx`) から題と凡例を抜き出し、表 → 図の順に 1 ファイル 1 項目で並べる。
  欄は書式を持てないので、上付き・下付きは Unicode の文字 (例: 10⁴) に置き換え、置き換えられない文字と斜体・太字は項目の下に
  注記する。`CAPTIONS.md` 自体はアップロードしない。
- `SUBMISSION.md` には、どの原稿 (入力ルート) から作ったパッケージかを書いた 1 行が入る。roundtrip が Drive へ届ける前に、
  今の入力ルートと照合する (§8.4)。
- **冒頭に ⛔ が出ていたら提出しない**。草稿モードや `--keep-figures` で作ったパッケージは、図が本文に埋め込まれたままで、
  構成も組み替えていない。
- **「規定チェック」節の要修正と、末尾の「注意 (この実行で検出したもの)」を必ず読む**。上限を超えた動画・受入形式外の
  ファイル・表の色・図と凡例の食い違いなど、この実行で見つかった問題がすべて転記される。規定に反するファイルは表の行にも
  `⚠ 上限超過` のような印が付く。画面のログは流れて消えるが、このファイルは残る。`--no-validate` で作ったときは
  節を出さず、冒頭に「省略した」と書く。
- アップロードの種類は投稿規定の記述から作ったもので、投稿系の実際の画面とは照合していない。食い違ったら画面が優先で、
  その誌の `profile.yaml` の `submission` ブロックを直す。

### 5.5 補足資料と動画

- **`<入力ルート>/supplementary/` は無変換で `data/output/<id>/supplementary/` に複製される**。中身には一切手を加えない。
- 動画 (拡張子で判定) は `limits.video_mb` の超過と受入形式外を警告する (サイズは 10 進。1 MB = 1 000 000 バイト)。
- **OS が作る管理用のファイル (`.DS_Store` / `Thumbs.db` / ドットで始まる名前) は複製しない**。除いたときは
  「管理用ファイル N 件を除外しました」と表示するので、意図して置いたものが落ちていないか確かめる。

### 5.6 規定チェック (validate)

`package.sh` の最後に、記事種別ごとの上限 (`--article-type`) と執筆の検査 (lint) を掛け、**「規定違反の可能性 (要修正)」と
「参考情報」に分けて**出す。**エラーにはしない** (終了コードは 0。判断は執筆者に残す)。

- 概算: 本文語数 / 抄録語数 / 文献数 / 図表の点数。本文語数からは、メタの Div (タイトル・著者・所属・連絡著者・
  キーワード・抄録)・References・表・キャプション・**図表の凡例 (`Legend` Div)** を除く。除いた凡例の語数は図 / 表に
  分けて内訳を出す (編集部の数え方が違えば足し戻せるように)。`.textbox` の中の図表は点数に数えず、数えなかった点数を
  概算行に必ず出す。
- 主な検査: タイトルの語数 / キーワードの数 / 抄録の構造と抄録内の文献引用 / Declarations の必須項目 / Abbreviations 節の
  位置 / 合成文字 (`℃`) / 数値の桁区切りカンマ / 骨格の記入欄 `<<...>>` の残り / 図表の合計点数 / 図表の題と凡例の語数 /
  凡例 Div の `for` 属性と配置 / 凡例 Div の中身が段落だけか / References が本文の最後の節か / 連絡著者のブロック /
  英米の慣用単位 / 統計ソフトの版の書き方。
- **一般的な作法 (合成文字・単位系・記入欄・凡例の配置) は雑誌プロファイルではなく基底に置いてある**ので、どの誌で
  パッケージしても掛かる。その誌の規定を調べたものではないので、指摘の文末に **`(本テンプレ共通の作法)`** が付く
  (付いていない要修正は、その誌の `profile.yaml` に根拠がある)。仕組みは `docs/profile-schema.md` の「lint の 2 層構成」。
- 指摘には原稿の行番号が付く。指摘は `SUBMISSION.md` の「規定チェック」節にも残る。
- ビルドせずに単独でも回せる:
  ```bash
  docker compose -f docker/docker-compose.yml run --rm -u "$(id -u):$(id -g)" pandoc \
      python3 main/step05_package/validate.py \
          --input-root data/dummy/bhi --journal bhi --article-type original
  ```
- 指摘の出方を見たいときは、違反を仕込んだフィクスチャ `data/dummy/bhi-lint/` を同じコマンドに渡す
  (要修正 23 件 + 参考 4 件が出る)。

### 5.7 入力ルートを切り替えるとき

`build.sh` は、`<入力ルート>/revise-report.md` / `cover-letter.md` が無ければ前回の docx を消す。`package.sh` も一次ソースの
有無と照合し、別の原稿でビルドした古い docx が混ざっていそうなら注意を出す。それでも、**入力ルートを大きく切り替えるときは
掃除してから回すのが確実**である:

```bash
rm -f data/step02_build/*.docx data/step02_build/*.tsv
rm -rf data/step05_package        # 提出用の派生物 (*.outline.svg) の置き場所
bash scripts/build.sh --journal <id> --input <入力ルート>
```

`data/step05_package/` は `figures.pptx.text_to_path: true` のときに作る `<stem>.outline.svg` の置き場所で、毎回作り直すので
古いものが使われることは無いが、掃除しておくと分かりやすい。

- `blinded: true` の誌では、著者・所属を伏せる作業を**手で**行う (自動の匿名化は無い。`package.sh` が注意を出す)。

---

## 6. 最終 PDF を作る (roundtrip)

docx → PDF は **Windows の Word (COM) で変換する**経路だけを用意している (任意の機能)。rclone の Google Drive の
リモートと、Windows 側で動く watcher が要る (配置・診断・トラブルシュート: `docs/roundtrip-windows-watcher.md`)。

送出先は Google Drive の **`gdrive:tmp/<リポジトリのディレクトリ名>/`** (算出は `scripts/lib/gdrive-dest.sh`。
環境変数 `RCLONE_REMOTE` / `GDRIVE_BASE_PATH` / `GDRIVE_SUBDIR` で変えられる)。watcher は PDF を**送出先の直下
(docx の隣)** に書く。

```bash
# 初回 (と watcher を更新したとき): Windows 側の 3 ファイルを送る → Windows で watch-and-convert.bat を起動
bash scripts/push-win-tools.sh

# 経路の診断 (読み取りだけ・数秒)。--full を付けると docx を 1 本往復させる
bash scripts/check-pdf-path.sh

bash scripts/roundtrip.sh                 # build → data/output に集約 → Drive へ送る → PDF を待つ → data/products へ取り込む
bash scripts/roundtrip.sh --skip-build    # 既存の docx を集約して変換 (別の誌でビルドした docx を見るときは必ずこちら)
bash scripts/roundtrip.sh --skip-push     # タイムアウトの後の再開 (送り直さず、待ちと取り込みだけ)
bash scripts/roundtrip.sh --dry-run       # rclone を呼ばずに流れだけ表示 (ビルドもしない。watcher は要らない)
```

- 引数なしのときの最初の段は `build.sh` を引数なしで回す (= `_default`)。BHI の体裁などで見たいときは、先にその誌で
  ビルドして `--skip-build` で回す。
- PDF を待つ時間の既定は 10 分 (`--timeout MIN`)。送る前に watcher の生存記録 (`.watcher-alive`) を見て、止まっている・
  ローカルと別の版が動いている・試験用の起動引数のまま、のときは警告する。前回の PDF を退避できなければ中止する
  (古い PDF を今回の結果として持ち帰らないため)。
- Windows 側の watcher は **1 ファイルあたり 120 秒で変換を打ち切り** (Word が固まったとき)、その docx を `error/` へ移して
  次へ進む。止めるのはその変換が起動した Word だけで、開いている Word の文書は巻き込まない。docx は 1 本ずつ順に変換するので、
  固まる docx が続くと合計が上の 10 分を超えうる。
- rclone や watcher が無い環境では docx までで止まる。`--dry-run` は rclone を呼ばないので、リモートが未設定でも流れを表示して
  正常終了する。
- 返ってきた PDF は**図を拡大して目で見る**こと。体裁の計測では図の中身の崩れに気づけない。PDF の図がベクターで載っているかは
  `main/step04_pdf/inspect_pdf_figures.py` で判定できる (`docs/roundtrip-windows-watcher.md` の「PDF の確かめ方」)。

---

## 7. パイプライン早見表

| 段 | コード | 入力 | 出力 | スクリプト |
|----|--------|------|------|-----------|
| step01 | `main/step01_figures/` | `<入力ルート>/figs/` | `data/step01_figures/figs/` | (build.sh / diff.sh が回す) |
| step02 | `main/step02_build/` | `<入力ルート>/main.md` + step01 | `data/step02_build/*.docx` | `scripts/build.sh` |
| step03 | `main/step03_diff/` | 旧版 / 新版の main.md | `data/step03_diff/main_diff.docx` | `scripts/diff.sh` |
| step04 | `main/step04_pdf/` (Windows 側は `windows/`) | `data/output/*.docx` | `data/products/*.pdf` | `scripts/roundtrip.sh` (準備 `push-win-tools.sh` / 診断 `check-pdf-path.sh`) |
| step05 | `main/step05_package/` | step02 / step03 の成果 + プロファイル | `data/output/<id>/` | `scripts/package.sh` |
| (検査) | `main/step02_build/check_csl.py` | `data/dummy/<id>-csl/` + `<id>.csl` (+ 任意で docx) | 照合結果 | `scripts/check-csl.sh` |
| (検査) | `main/step01_figures/check_dpi.py` | `data/step01_figures/figs/` または `data/output/<id>/figures/` | 実画素数・pHYs と目標 dpi の照合結果 | `scripts/check-figures.sh` |

各段は単独で再実行できる。コード (`main/`) とデータ (`data/stepNN_name/`) は分けてある。

テンプレート自体を直したときの回帰の確かめ方は `CLAUDE.md` の「変更するときの確認」
(`scripts/baseline.sh` / `baseline-bhi.sh` / `compare-snapshots.py`)。

---

## 8. BHI へ投稿する (通し手順)

*BioHealth Informatics* への投稿を、執筆の開始から投稿まで 1 本につないだもの。個々の機能の説明は §1〜§6 にあるので、
ここでは**順番と、どの段で何が担保されるか**だけを書く。投稿当日に 1 枚で確認する表は
[`docs/bhi-submission-checklist.md`](bhi-submission-checklist.md) (自動で担保される項目と、人が目で見るしかない項目を
分けてある)。規定の読み解きと実装の対応は [`docs/journal-bhi.md`](journal-bhi.md)。

> 本テンプレートは雑誌・学会とは関係のない独立したツールである。**規定は変わりうるので、公式の
> [For Authors](https://biohealth-informatics.com/for-authors/) で確かめること。**

### 8.1 執筆を始める

```bash
cp data/journals/bhi/skeleton/main.md         src/main.md
cp data/journals/bhi/skeleton/cover-letter.md src/cover-letter.md
rm -f .development
```

骨格は必須節を記入式で持ち、記入欄は `<<...>>` で書いてある。**埋め忘れは §8.3 の規定チェックが `main.md` /
`cover-letter.md` の両方について件数と行番号つきで指摘する**。Declarations 6 項目の文例は
`data/journals/bhi/skeleton/declarations.md` (参照用)。記入済みの動作例は `data/dummy/bhi/` で、`--input data/dummy/bhi` を
付ければそのままビルドできる。

**生成 AI ツールを使うなら、書き始めた時点から道具と版を記録する**。本誌は Editorial Policies で **AI の使用を原稿の中で
開示する**ことを求めており、骨格は Conclusion と Declarations の間の `# Acknowledgments` 節をその受け皿にしている
(文例は `declarations.md` の AI 使用の節。ツール名 / 版 / 使途 / 著者が全内容に責任を負う旨 / ネイティブによる最終確認の
5 要素)。開示は**実際に使ったもの**でなければならず、執筆が長引くと途中で版が変わるので、**git で追跡している作業記録の
ファイル**に書き足していく。Acknowledgments は本文語数に算入される。AI ツールを使わず、謝辞の相手もいなければ節ごと消してよい。

### 8.2 図を用意する

- 本文からは常に `.svg` で参照する (§2)。
- **SVG ルートの `width` / `height` には「印刷したい幅」を物理単位 (mm / pt / in) で書く**。px や単位なしで書くと
  CSS px (96 dpi) とみなされ、誌が公称サイズより大きく組んだときに 300 dpi を割る。動作例 `data/dummy/bhi/figs/` は
  `width="160mm"` のように書いてある (BHI の本文幅 159.2 mm = A4 から左右の余白 25.4 mm を引いた幅より 0.8 mm 広い。
  docx 上では pandoc の本文幅の扱いで 159.1 mm に縮むが、実効解像度が上がる側なので害は無い)。
- 多パネル図は 1 ファイルに合成し、余白は SVG の側で切り詰め、凡例のキーは画像の中に入れる (自動化されない)。
- PowerPoint で仕上げたい図は、図の隣に**同名の `.pptx`** を置く (無変換でコピーされる。§5.1)。

### 8.3 ビルドして中身を確かめる

```bash
bash scripts/build.sh   --journal bhi --article-type original
bash scripts/package.sh --journal bhi --article-type original --mode final
bash scripts/check-figures.sh --journal bhi                                       # 図ツリー
bash scripts/check-figures.sh --journal bhi --figures-dir data/output/bhi/figures # 提出する図
```

引用様式 (`data/journals/bhi/bhi.csl`) を変えたときは、§4.1 の照合も回す。`check-csl.sh --docx` に渡すのは
**フィクスチャ `data/dummy/bhi-csl/` からビルドした docx** で、原稿の docx を渡すと引用の件数が合わずに NG になる。
フィクスチャのビルドは `data/step02_build/main.docx` を上書きするので、照合のあとで原稿をビルドし直す。

`package.sh` は最終モードで **(a) 表を本文から外して `tables/` に 1 表 1 ファイルで出し (b) 図の題と凡例を References の後の
`Figure Legends` 節へ集め (c) 図を `figures/` に 1 図 1 pptx で分離し (d) 投稿画面の Caption / Legend 欄に貼る文面を
`CAPTIONS.md` に出した**うえで、**規定チェック**を回す。指摘は画面と
**`data/output/bhi/SUBMISSION.md` の「規定チェック」節**の両方に出る — 画面のログは流れて消えるので、
**最終確認は `SUBMISSION.md` で行う**。

規定チェックの出力は 2 段に分かれる。

- **規定違反の可能性 (要修正)** — 直す。語数・キーワードの数・Declarations の欠け・凡例の配置の誤りなど
- **参考情報** — 判断が要るもの。タイトルの略語・英米の慣用単位らしい表記・統計ソフトの版の書き方など

**どちらもエラーにはしない** (終了コードは 0)。CI で落としたい場合は出力を自分で判定する。

### 8.4 体裁を Word で確かめる (任意だが推奨)

Windows 側で watcher が動いていることが前提 (§6。止まっていると 10 分待ってタイムアウトするので、先に
`bash scripts/check-pdf-path.sh` で [4/5] が「稼働中」になることを見ておく)。

```bash
bash scripts/roundtrip.sh --skip-build   # → data/products/bhi-manuscript.pdf / bhi-Table1.pdf … + Drive の submission-bhi/
```

`roundtrip.sh` は、`SUBMISSION.md` を持つ提出パッケージ `data/output/bhi/` の本文と表を `bhi-manuscript.docx` /
`bhi-Table1.docx` … の名前で集めて PDF 化に回す (手でコピーしなくてよい)。PDF はほかの docx (main / main_diff /
cover-letter) の分と一緒に `data/products/` に届く。PDF がそろうと、**最後の段がパッケージ一式を Drive の `submission-bhi/` に
置く** (表と図は 1 階層に並べる。中身はパッケージと一致させ、消えた・置き換わったファイルは送出先の `__archives` フォルダへ退避し、手元の写し
`data/products/submission-bhi/` と照合する。watcher は送出先の直下の docx しか見ないので、このフォルダは変換されない)。
**`bhi-manuscript.pdf` には図も表も入らない** — 最終モードは図を `data/output/bhi/figures/`、表を `data/output/bhi/tables/` へ
分離するので、本文には `[Figure N about here]` / `[Table N about here]` だけが残り、図の題と凡例は References の後の
Figure Legends に集まる。表は `bhi-Table1.pdf` … で見る。**図の描画は草稿の `main.pdf` で拡大して目で見る** (§6 の最後の項目)。

**送る前に止まる条件** (何も送らない): パッケージが草稿モード (`--keep-figures` を含む) で作られている / パッケージより新しい
原稿・ビルド・誌のプロファイルがある / `SUBMISSION.md` に書いた入力ルートが今の入力ルートと違う・書かれていない。動作例
(`--input data/dummy/bhi`) で作ったパッケージを確かめるときは `INPUT_ROOT=data/dummy/bhi bash scripts/roundtrip.sh --skip-build`
とする。提出パッケージを使わないときは `--no-package`、1 誌に絞るときは `--package <id>`。

**`--skip-build` を必ず付ける** — 付けないと最初の段が `build.sh` を引数なしで回し直し、BHI の体裁の docx を `_default` の
体裁で上書きする (そのうえパッケージより新しいビルドができるので、Drive へ届ける前に止まる)。

Word で見るときの確認点: A4 / 余白 25.4 mm / Times New Roman 12 pt / ダブルスペース / 左余白の連続行番号 / フッタのページ番号 /
References → (改ページ) Figure Legends の並び (表は本文に無く、`bhi-Table1.pdf` … に題が上・凡例が下で載る) /
題・見出し・抄録も本文と同じ 12 pt で、見出しは黒の太字・斜体 / 引用番号 `1)` が丸ごと上付き / カバーレターに行番号が無い。

### 8.5 投稿する

`data/output/bhi/` に揃ったものを投稿系 (ScholarOne) へ上げる。**種類ごとの対応と、上げてはいけないファイル (初回投稿で
`manuscript-diff.docx` を上げない など) は `SUBMISSION.md` に書いてある**。投稿当日の確認は
`docs/bhi-submission-checklist.md` を上から順に。
**Google Drive からファイルを選ぶときは `submission-bhi/` から取る** (§8.4 の roundtrip が置く。表と図は 1 階層に並ぶ)。
送出先の直下や `processed/` には、草稿の `main_…` と提出用の `bhi-manuscript_…` が時刻付きの名前で並ぶので、そこから選ぶと
取り違えやすい。上げたファイルごとの **Caption / Legend 欄には `CAPTIONS.md` の枠の中身を貼る** (`CAPTIONS.md` 自体は上げない)。

投稿の 2〜4 週間前から要る作業 (どれもツールの外にある):

- **COI Disclosure Form と License to Publish は各 1 通** — 連絡著者が全著者を代表して記入し、PDF で上げる。COI は
  **全共著者の申告を集めて 1 通にまとめる**ので、共著者への聞き取りに日数がかかる。
- **転載する素材があれば、許諾の写しを初回投稿時に添える** (後から集めればよいものではない)。
- **連絡著者は受理後に変更できない** — 著者の追加・削除・著者順の変更も同じ。
- **関連する原稿 (学会の詳細な抄録・プレプリントなど) があれば、カバーレターで開示する**。
- **刷り上がりが Original Article で 9 ページを超えると、1 ページごとに著者の負担がある**。ページ数は組版の後にしか
  分からないので、超えたときにどうするかを投稿前に決めておく。

いずれも本誌の Editorial Policies と For Authors による。詳細は `docs/journal-bhi.md`。

### 8.6 記事種別を変える

`--article-type` を差し替えるだけで、本文語数・抄録語数・抄録の構造 (ラベル)・図表点数の上限が切り替わる。定義は
`data/journals/bhi/profile.yaml` の `article_types`。

| 種別 | 本文 | 抄録 | 図表 |
|------|------|------|------|
| `original` (既定) | 4,000 | **構造化** (Objective / Methods / Results / Conclusion) 300 | 8 |
| `review` | 4,800 | 非構造化 300 | 10 |
| `short` | 2,400 | 非構造化 200 | 4 |
| `technical` | 3,600 | 非構造化 200 | 5 |
| `data` | 3,600 | 非構造化 200 | 5 |
| `perspective` | 2,400 | 非構造化 200 | 4 |
| `tutorial` | 2,400 | 非構造化 200 | 4 |
| `letter` | 1,200 | (抄録なし) | 1 |

存在しない種別を渡すと、**有効な種別の一覧を出してエラーで止まる** (綴りの誤りで上限の検査が黙って外れないように)。

---

## 9. 動作例とフィクスチャ (data/dummy/)

`data/dummy/` の原稿はすべて**明らかなフィクション**で、<https://github.com/fk506cni/jami-pandoc-public> の
「tremendous hunch」(TJD/THS) の物語のパロディである。著者・機関・結果は架空で、実在の原稿が無くても全機能を
ビルドして確かめられるように置いてある。

| ディレクトリ | 中身 | 使い方 |
|-------------|------|--------|
| `data/dummy/` (直下) | 汎用の完結した原稿 (タイトル・著者・抄録・SVG / PDF / Mermaid の図・引用・表・テキストボックス) + リバイスレポート + カバーレター | `.development` を置いて `build.sh` / `diff.sh` / `package.sh` |
| `data/dummy/bhi/` | BHI の骨格を埋めた完結原稿 (+ 物理単位の図・補足資料) | `--input data/dummy/bhi --journal bhi --article-type original`。規定チェックは要修正 0 件 |
| `data/dummy/bhi-lint/` | 規定に**合わない**原稿 (違反を仕込んである) | validate に渡すと要修正 23 件 + 参考 4 件 |
| `data/dummy/bhi-csl/` | 規定の文献の出力例 5 件 + `expected.txt` | `bash scripts/check-csl.sh` (既定のフィクスチャ) |
| `data/dummy/regression/` | 回帰用の図 (PNG 図・段落内の複数図・テキストボックス内の図表・物理単位 / px 単位の SVG・Word で崩れる SVG の例) | `--input data/dummy/regression` を明示したときだけ回る |
