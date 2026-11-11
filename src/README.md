# src/ — 原稿の正本 (一次ソース)

このディレクトリに**あなたの論文**を置く。`.development` マーカーが**無い**とき、`build.sh` / `diff.sh` /
`package.sh` はこの `src/` を入力ルート (`INPUT_ROOT`) にする。clone 直後は雛形ディレクトリだけで
原稿 (`main.md`) はまだ無い。

## 構成 (執筆時にここへ作る)

```
src/
├── main.md            # 本文 (必須)。タイトル/著者/抄録/キーワードは custom-style Div で書く
├── ref.bib            # 文献データベース (BibTeX)
├── revise-report.md   # リバイスレポート (査読対応。任意)
├── cover-letter.md    # カバーレター (任意)
└── figs/              # 図ソース (*.svg / *.pdf を手で配置)
    └── mermaid/       #   Mermaid 図ソース (*.mmd)
```

## 新規論文の始め方 (ブートストラップ)

`data/dummy/` がタイトル/著者/抄録/本文/図(SVG+PDF+mermaid)/引用/表/textbox を網羅した**完結する作例**なので、
これを `src/` にコピーして雛形にするのが速い:

```bash
cp -r data/dummy/. src/        # ダミー一式を src/ へ複製 (.gitkeep は上書きされない)
rm .development                # 本番モードへ (入力ルートを data/dummy → src に切替)
$EDITOR src/main.md            # 自分の原稿に書き換える
```

ゼロから書く場合は `src/main.md` と `src/ref.bib` を新規作成する。**タイトル・著者・抄録・キーワードは
YAML メタではなく `custom-style` Div** で書くこと (構造保持 AST 差分で温存・差分化するため。CLAUDE.md の「原稿執筆の規約」)。

## 執筆 → 投稿の流れ

`docs/usage-guide.md` (操作ガイド: 図の追加 / 雑誌の追加 / 差分の出し方) と、リポジトリルートの
`README.md` (Getting Started) を参照。

> 注: `src/` 配下の原稿・図はあなたの著作物であり git 追跡される (`.gitignore` は中間/成果物のみ除外)。
> テンプレートを別リポジトリとして複製して使う想定。
