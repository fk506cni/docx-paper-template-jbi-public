# src/ — 原稿の正本 (一次ソース)

このディレクトリに**あなたの論文**を置く。`.development` マーカーが**無い**とき、`build.sh` / `diff.sh` /
`package.sh` はこの `src/` を入力ルート (`INPUT_ROOT`) にする。

**clone した直後の `src/` には、BHI の Original Article の体裁のサンプル論文が入っている** (TJD/THS のパロディで、
著者・所属・データはすべて架空)。BHI の原稿骨格の記入欄を埋めた完結した論文なので、そのまま試せる:

```bash
bash scripts/build.sh   --journal bhi --article-type original   # → data/step02_build/main.docx (+ cover-letter.docx)
bash scripts/package.sh --journal bhi --mode final              # → data/output/bhi/ (manuscript.docx・図・表・補足資料・
                                                                #    SUBMISSION.md・CAPTIONS.md)
```

雑誌を指定しなければ既定の `_default` (汎用の投稿フォーマット) で組まれる。

## 構成

```
src/
├── main.md            # 本文 (必須。サンプル入り)。タイトル/著者/抄録/キーワードは custom-style Div で書く
├── ref.bib            # 文献データベース (BibTeX。サンプル入り)
├── cover-letter.md    # カバーレター (任意。サンプル入り)
├── revise-report.md   # リバイスレポート (査読対応。任意。サンプルには無い)
├── supplementary/     # 補足資料 (任意。サンプル入り)。--mode final が無変換で提出物に複製する
└── figs/              # 図ソース (*.svg / *.pdf を手で配置。サンプルは fig-apparatus.svg / fig-ths.svg)
    └── mermaid/       #   Mermaid 図ソース (*.mmd)
```

同じ内容の写しが `data/dummy/bhi/` にある (検証用。`--input data/dummy/bhi` で使う)。雑誌によらない全機能
(SVG / PDF / Mermaid の図・数式・罫線の表・テキストボックス・査読対応の差分) の見本は `data/dummy/` にある。

## 自分の論文に置き換える

サンプル一式を消してから書き始める (`src/README.md` と `src/figs/mermaid/` は残る):

```bash
bash scripts/remove-sample.sh                         # 中身がサンプルのままのファイルだけを消す (自分のファイルは消さない)
cp data/journals/bhi/skeleton/main.md src/main.md     # BHI に出すなら骨格から (記入欄は <<...>>)
$EDITOR src/main.md
```

自分の `main.md` の隣にサンプルのファイルが残っていると、最終モードの package は止まる (サンプルのカバーレターと補足資料が
提出物に入らないように)。手順の正本は `docs/usage-guide.md` §1。

雑誌によらない全機能の見本から始めるなら、骨格の代わりに次を写す:

```bash
cp data/dummy/main.md data/dummy/ref.bib data/dummy/cover-letter.md data/dummy/revise-report.md src/
cp -r data/dummy/figs/. src/figs/
```

ゼロから書く場合は `src/main.md` と `src/ref.bib` を新規作成する。**タイトル・著者・抄録・キーワードは
YAML メタではなく `custom-style` Div** で書くこと (構造保持 AST 差分で温存・差分化するため。CLAUDE.md の「原稿執筆の規約」)。

## 執筆 → 投稿の流れ

`docs/usage-guide.md` (操作ガイド: 図の追加 / 雑誌の追加 / 差分の出し方。§8 = BHI 投稿の通し手順) と、
リポジトリルートの `README.md` (クイックスタート) を参照。

> 注: `src/` 配下の原稿・図はあなたの著作物であり git 追跡される (`.gitignore` は中間/成果物のみ除外)。
> テンプレートを別リポジトリとして複製して使う想定。
