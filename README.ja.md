# docx-paper-template-jbi

**論文を Markdown で書き、投稿用の Word ファイル (.docx) を生成するテンプレートリポジトリです。**
複製して `src/main.md` を書き、雑誌プロファイルを選んでビルドします。
投稿の作業のうち、ふだん Word で手作業になる部分 — 査読対応の差分の色付け、ベクター図の劣化のない貼り込み、
雑誌ごとの体裁、最終提出物の組み立て — を受け持ちます。

English: [README.md](README.md)

> **雑誌・学会とは無関係です。** 本プロジェクトは独立した道具で、*BioHealth Informatics* および
> 日本医療情報学会が提供・確認・推奨したものではありません。`bhi` プロファイルは同誌の公開されている
> 投稿規定を私たちが読み解いたもので、規定はいつでも変わりえます。**投稿の前に必ず公式の
> [For Authors](https://biohealth-informatics.com/for-authors/) で確かめてください。**

---

## できること

- **Markdown → .docx** (pandoc)。タイトル・著者・所属・抄録・キーワードは本文中のスタイル付きブロックとして書くので、
  雑誌の reference document で整形され、差分の対象にもなります。
- **原稿全体の差分 (査読対応)**。2 版の `main.md` を pandoc の AST で突き合わせ、追加した語を青、削除した語を赤の
  取り消し線で示します。タイトル・著者・抄録・キーワード・本文・表・テキストボックス内の表まで対象で、
  文書の構造は壊しません。
- **ベクター図**。SVG 図を .docx にネイティブで埋め込み、プロファイルの解像度 (既定 300 dpi) の PNG を
  フォールバックとして添えます。PDF 図はまず SVG に変換します。Mermaid 図 (`.mmd`) はコンテナで描画して同じ経路に載せます。
- **雑誌プロファイル** (`data/journals/<id>/`)。体裁 (`profile.yaml`)・引用様式 (CSL)・Word の reference document
  (`reference.docx`。初めて要るときに `profile.yaml` から生成します) を雑誌ごとに 1 ディレクトリで持ちます。原稿そのものは雑誌に依存させません。
  - `_default` — 汎用の投稿フォーマット。ダブルスペース・連続行番号・Times New Roman 12 pt・A4 余白 25 mm・AMA 系の番号引用
  - `bhi` — *BioHealth Informatics*
- **BHI 対応**:
  - 記事種別 8 種。種別ごとに語数・抄録・図表点数の上限が変わる (`--article-type`)
  - 規定の出力例を再現する引用様式 (`1)` を丸ごと上付き) と、その出力例との照合テスト
  - 図を PowerPoint 形式で出す (1 図 1 ファイル。ベクターの SVG と 300 dpi の PNG フォールバックを同梱)。
    受入形式のうちベクターを保てるのが PowerPoint だけなので
  - 規定の "12-point type face" と "double-spaced throughout" に合わせた体裁: 題・見出し・抄録も本文と同じ 12 pt にそろえ、
    見出しの階層は太字と斜体で付け、段落スタイルごとの行送りは持たせない
  - 最終提出用の組み替え: 表を本文から外して 1 表 1 ファイル (`tables/Table1.docx` …) で出し、図の題と凡例を
    References の後へ集め、本文にはプレースホルダを残す (本文ファイルはテキストだけになる)
  - `SUBMISSION.md`: アップロード種別ごとのファイル一覧・形式・サイズと、添付するフォーム
  - `CAPTIONS.md`: 投稿系の Caption / Legend 欄に貼る図表の題と凡例。アップロードするファイルそのものから抜き出す
  - 規定チェック: 記事種別ごとの語数、必須節、抄録の構造、桁区切りのカンマ・合成文字 (`℃`)・凡例の配置などの執筆チェック
  - 必須節をすべて含む原稿の骨格 (`data/journals/bhi/skeleton/`)
- **Microsoft Word による PDF 化 (任意)**。.docx を rclone で Google Drive に送り、Windows の PC で動く watcher が
  Word で変換し、PDF が戻ってきます。Word で開いたときの体裁で確かめるためで (投稿系が編集者・査読者向けに作る PDF とは違いうる)、PDF 化に LibreOffice は意図して使いません。
  最終提出用のパッケージも PDF にしたうえで、Drive の専用のフォルダ (`submission-<journal>/`) に置くので、
  アップロードするファイルを 1 か所から選べます。

## 必要なもの

- **Docker** (Compose v2 つき)、**bash**、**git**。変換はすべてコンテナの中で行い、ホストには何も入れません。
- **x86-64 (amd64)** のホスト。pandoc のイメージは amd64 版のバイナリを入れます。開発は Linux で行っており、
  ほかの環境では試していません。
- **初回ビルド時のネットワーク接続**。pandoc と pandoc-crossref、Mermaid CLI と headless Chromium、
  (任意の `svg-conversion` イメージでは) Microsoft Core Fonts を取得します。
- 埋め込んだ SVG をベクターで表示するには **Microsoft 365 または Office 2019 以降**。
  Office 2016 などでは PNG のフォールバックが表示されます。

任意:

- **PDF 化**: Google Drive のリモート (既定名 `gdrive:`) を設定した rclone と、同じ Drive フォルダを同期する
  Microsoft Word 入りの Windows PC。[docs/roundtrip-windows-watcher.md](docs/roundtrip-windows-watcher.md) を参照。
- **`svg-conversion` イメージ** (図を文字のアウトライン化つきの PDF で出すときだけ使う。例: `_default` の最終モード):
  Calibri や Yu Gothic などの専有フォントは**同梱していません**。使用許諾のあるフォントファイルを、イメージを
  ビルドする前に `fonts/` に置いてください。置かなくてもイメージはビルドでき、別のフォントで代替されます。
  イメージは無いときにだけビルドされるので、ビルドした後でフォントを足したときは
  `docker image rm docx-paper-template-svg-converter` で消してください (次に使うときに作り直されます)。
  このイメージはビルドの際に `corefonts` プロジェクトから Microsoft Core Fonts を取得します。**ビルドすると、
  これらのフォントの Microsoft の使用許諾契約 (EULA) に同意したことになります**
  (<https://corefonts.sourceforge.net/eula.htm>)。初めて必要になったとき (例: `_default` の最終モード) に自動でビルドされます。

## クイックスタート

同梱のサンプル原稿をビルドします。リポジトリのルートで実行してください。

```bash
git clone https://github.com/fk506cni/docx-paper-template-jbi-public.git
cd docx-paper-template-jbi-public

# 1. 主変換イメージをビルドする (pandoc・pandoc-crossref・Python・librsvg・LibreOffice)
docker compose -f docker/docker-compose.yml build

# 2. 入力を src/ ではなく同梱のサンプル (data/dummy/) にする
echo dev > .development

# 3. Markdown → .docx (初回は Mermaid のイメージのビルドと reference.docx の生成も行われる)
bash scripts/build.sh
#    -> data/step02_build/main.docx

# 4. 原稿の 2 版の差分 (色付き)
mkdir -p jank
sed 's/Twenty trials/Twenty-four trials/' data/dummy/main.md > jank/main-new.md
bash scripts/diff.sh data/dummy/main.md jank/main-new.md
#    -> data/step03_diff/main_diff.docx

# 5. 汎用プロファイルで草稿パッケージ (図は埋め込んだまま)
bash scripts/package.sh --journal _default --mode draft
#    -> data/output/_default/

# 6. BHI のサンプル: ビルドしてから最終提出パッケージを組み立てる
bash scripts/build.sh   --journal bhi --article-type original --input data/dummy/bhi
bash scripts/package.sh --journal bhi --mode final --input data/dummy/bhi
#    -> data/output/bhi/ (manuscript.docx, tables/*.docx, figures/*.pptx, SUBMISSION.md, CAPTIONS.md, ...)
```

できたファイルを Word で開いてください。`data/step03_diff/main_diff.docx` では抄録の数字の変更に色が付いています。
`data/output/bhi/manuscript.docx` はテキストだけで、表は 1 表ずつ `data/output/bhi/tables/` に、図の凡例は References の後に、
図そのものは `data/output/bhi/figures/` にあります。`data/output/bhi/SUBMISSION.md` には、アップロードするファイルの一覧・
規定チェックの結果・投稿前に目を通す注意がまとまっています。`data/output/bhi/CAPTIONS.md` は Caption / Legend 欄に貼る文面です。

### 自分の原稿を始める

```bash
rm .development                 # 入力ルートが data/dummy/ から src/ に切り替わる
cp -r data/dummy/. src/         # 汎用のサンプルを写してから src/main.md を書き換える
```

BHI に出すなら骨格から始め (`cp data/journals/bhi/skeleton/main.md src/main.md`)、
[docs/usage-guide.md](docs/usage-guide.md) の BHI の通し手順に沿ってください。
原稿は `src/` に置いてふつうに commit します。生成物は `data/` に出て、git の対象外です。

## 主なコマンド

| コマンド | すること |
|---|---|
| `bash scripts/build.sh [--journal <id>] [--article-type <種別>]` | 図の前処理 → `data/step02_build/main.docx` |
| `bash scripts/diff.sh [REVISION \| old.md new.md]` | git の版 (既定 `HEAD~1`) または 2 ファイルの差分 → `data/step03_diff/main_diff.docx` |
| `bash scripts/package.sh --journal <id> --mode draft\|final` | 投稿パッケージ → `data/output/<id>/` (最終モードは図を分離し (BHI は表も)、規定チェックを走らせる) |
| `bash scripts/check-figures.sh [--journal <id>] [--figures-dir <dir>]` | 図の解像度の検査。`--figures-dir` では PowerPoint 図の構造も検査する |
| `bash scripts/check-csl.sh [--docx <file>]` | 整形した文献リストを期待値のフィクスチャと照合する |
| `bash data/journals/make-reference.sh <id>` | 雑誌の `reference.docx` を `profile.yaml` から生成する。ファイルが無ければ `build.sh` と `diff.sh` が自動で回す。`profile.yaml` の体裁を変えたら自分で回す |
| `bash docker/mermaid/convert.sh <file.mmd> both` | Mermaid 図を単独で SVG と PDF に描画する (ビルドは `figs/mermaid/*.mmd` を自分で描くので要らない。見た目を確かめるだけなら `figs/` の外に写して描く) |
| `bash scripts/push-win-tools.sh` / `check-pdf-path.sh` / `roundtrip.sh` | Word による PDF 化 (準備 / 診断 / 変換。任意。`roundtrip.sh` は最終提出用のパッケージを Drive の `submission-<journal>/` にも置く) |
| `bash scripts/baseline.sh <接尾辞>` / `baseline-bhi.sh <接尾辞>` / `scripts/compare-snapshots.py` | ビルド成果物の回帰スナップショットと、その比較 |

`build.sh`・`diff.sh`・`package.sh`・`check-figures.sh`・`check-csl.sh`・`baseline.sh`・`baseline-bhi.sh` と PDF 化の 3 本は `--help` で使い方を表示します。
スクリプトのメッセージと詳しいガイドは日本語です。

## ディレクトリ構成

```
.
├── src/              # あなたの原稿: main.md, ref.bib, figs/ (+ cover-letter.md, revise-report.md)
├── data/
│   ├── journals/     # 雑誌プロファイル: _default/ と bhi/ (bhi/skeleton/ = 原稿の骨格)
│   ├── dummy/        # サンプル原稿と検査用フィクスチャ (.development があるときの入力)
│   └── step*/ output/ products/   # 生成物 (git の対象外)
├── main/             # 処理コード (パイプラインの段ごとに 1 ディレクトリ)
│   ├── 00_setup/     #   共通設定・Lua フィルタ・OOXML の補助
│   ├── step01_figures/  step02_build/  step03_diff/  step04_pdf/  step05_package/
├── scripts/          # 入口 (build / diff / package / 検査 / PDF 化)
├── docker/           # pandoc・Mermaid・svg-conversion のイメージ (ポートは公開しない)
├── fonts/            # svg-conversion 用の専有フォント (任意。git の対象外)
└── docs/             # 詳しいガイド
```

## 文書

| 文書 | 内容 |
|---|---|
| [docs/usage-guide.md](docs/usage-guide.md) | 操作手順: 図・雑誌・差分・パッケージ・PDF と、BHI の通し手順 |
| [docs/architecture.md](docs/architecture.md) | 処理の流れと設計の判断 |
| [docs/profile-schema.md](docs/profile-schema.md) | `profile.yaml` の全キー・既定値・読み手 |
| [docs/design-fullarea-diff.md](docs/design-fullarea-diff.md) | 構造を保つ差分の仕組み |
| [docs/journal-bhi.md](docs/journal-bhi.md) | BHI の規定と実装の対応表 |
| [docs/bhi-submission-checklist.md](docs/bhi-submission-checklist.md) | 投稿当日に確かめる 1 枚の表 |
| [docs/migration-latex.md](docs/migration-latex.md) | LaTeX の原稿を本テンプレートへ書き起こす |
| [docs/roundtrip-windows-watcher.md](docs/roundtrip-windows-watcher.md) | Word による PDF 化の準備と診断 |
| [CLAUDE.md](CLAUDE.md) | 規約の短い版 (AI のコーディング支援も読む) |

## サンプル原稿

`data/dummy/` の原稿は明らかなフィクションで、<https://github.com/fk506cni/jami-pandoc-public> の
「とてつもない予感」(TJD/THS) の物語のパロディです。著者・機関・結果はすべて架空です。
実際の原稿が無くても、すべての機能をビルドして確かめられるように置いています。

## 制限

- **PDF 化には Windows と Microsoft Word が要ります。** 無くても .docx はすべて作れますが、PDF はできません。
- **差分**: 段落の移動は削除と追加として表示されます。結合セルを含む表は整列が不正確になることがあります。
  文献リストと数式の中身は差分ではなく作り直しになります。語の間に空白の無い文 (日本語など) は、語ではなく句の単位で比べます。
- **図**: 解像度を保証するのは SVG や PDF から作る画像だけです。自分で置いたラスタ画像はそのまま複製されます。
  SVG としては正しいのに Word や PowerPoint で崩れるものがあり (複数の SVG を 1 ファイルに連結したもの、色を
  `hsl()` で書いたもの)、`scripts/check-figures.sh` が注意として一覧に出します。
- **規定チェックは補助で、保証ではありません。** 刷り上がりのページ数・英語の質・MeSH のキーワード・転載許諾は
  自動では確かめられません。チェックリストを見てください。
- **同梱の雑誌プロファイルは 2 つです。** ほかの雑誌は `_default` を複製して足します (操作ガイドを参照)。

## ライセンス

本リポジトリのコードは [MIT License](LICENSE) で公開しています。
同梱している引用様式の CSL 2 本は CC BY-SA 3.0 です。Word の reference document は同梱せず、pandoc の既定データから
あなたの手元で生成します。[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) を参照してください。

本テンプレートで書いてビルドした文書は、あなたの著作物です。
