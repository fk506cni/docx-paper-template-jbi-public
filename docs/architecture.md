# 設計 (architecture.md)

処理の流れと、なぜそういう作りにしたかをまとめる。使い方は [`docs/usage-guide.md`](usage-guide.md)、
`profile.yaml` のキーは [`docs/profile-schema.md`](profile-schema.md)、差分の詳しい仕組みは
[`docs/design-fullarea-diff.md`](design-fullarea-diff.md) にある。

節の番号は段の番号に合わせてある (§2.1 = step01 の図の前処理 … §2.5 = step05 の投稿パッケージ)。コードのコメントも
この番号で参照する。

---

## 0. 設計上の確定事項

| 論点 | 採用 | 採らなかった案と理由 |
|------|------|-------------------|
| docx → PDF | **Windows の Word (COM) で変換する roundtrip だけ** (任意の機能) | LibreOffice は Word 固有の体裁 (テキストボックス・行番号・フィールド) の再現が劣るため、PDF 化には使わない |
| 図の埋め込み | **ネイティブ SVG + PNG フォールバック** | EMF への変換は品質の検証の手間が大きい。閲覧環境ごとに出し分ける方式は複雑になる |
| 差分 | **構造保持 AST 差分 → 色ハイライト** (全領域) | Word の変更履歴は表・テキストボックス・図に弱い。pandiff は内部で HTML の語単位の差分を取り、`custom-style` Div・表・生 OOXML を壊す |
| 既定の書式 | **汎用の投稿フォーマット** (ダブルスペース・連続行番号・Times 相当 12 pt・余白 25 mm) | 多くの英文誌の初回投稿の要件に合う |
| 雑誌ごとの違い | **`data/journals/<id>/` のプロファイルに閉じ込める** | 原稿 (`src/main.md`) は雑誌に依存させない。誌の要求 (表を末尾へ・別ファイルへ・凡例を集める) は提出物を作る段で満たす |
| 実行環境 | **変換はすべてコンテナの中** | ホストに何も入れない。版を固定して出力を再現できるようにする |

---

## 1. システム構成

### 1.1 データフロー

```
              src/main.md   src/ref.bib   src/figs/*.{svg,pdf,png}  src/figs/mermaid/*.mmd
                   │             │               │                         │
                   │             │               ▼                         ▼
                   │             │        [step01_figures]  ◄──── (mermaid: .mmd → svg/pdf)
                   │             │   SVG 補正 / PDF → SVG (+pt) / SVG → PNG (要求 dpi + pHYs)
                   │             │               │
                   │             │               ▼  data/step01_figures/figs/
                   ▼             ▼               ▼
  雑誌プロファイル ──► [step02_build] ◄───────────┘
  (CSL / reference.docx)  pandoc: crossref → generic-style.lua → citeproc
                          後処理: 表の罫線 / SVG のネイティブ埋め込み / テキストボックス / 行番号の範囲
                   │
                   ▼  data/step02_build/{main,revise-report,cover-letter}.docx
                   │
     旧版 main.md ─► [step03_diff]  pandoc -t json (旧 / 新) → 構造保持 AST 差分 → 色 span → docx
                   │
                   ▼  data/step03_diff/main_diff.docx
                   │
                   ├──────────────► [step05_package]  プロファイルに従って提出物を組み立てる
                   │                  草稿 / 最終 (図の分離・表の移設 / 別ファイル化・凡例の集約)・規定チェック
                   │                  → data/output/<id>/ (manuscript / tables / figures / SUBMISSION.md / CAPTIONS.md …)
                   │
                   ▼  [step04_pdf]  roundtrip.sh (任意)
         data/output/*.docx → rclone → Google Drive → Windows の Word → PDF → data/products/
         (提出パッケージの本文と表も PDF にし、パッケージ一式を Drive の submission-<id>/ に置く)
```

### 1.2 コンテナ

変換専用のコンテナを 3 つ使う。どれも常駐しないので、**ポートは公開しない**。イメージ名にはプロジェクト名を前に付け、
ベースイメージのタグと、出力に直結するパッケージ (pandoc / pandoc-crossref / panflute / lxml / mermaid-cli / Inkscape など) の
版を固定する。apt / apk のパッケージは、ビルドした時点の配布物の版になる (部分的な再現性)。

| イメージ | ベース | 役割 | 起動のしかた |
|---------|--------|------|-------------|
| `docx-paper-template-pandoc` | ubuntu:24.04 | md → docx・差分・後処理・図の pptx 化・検査 | `docker compose -f docker/docker-compose.yml run --rm` (ビルドは利用者が 1 回行う) |
| `docx-paper-template-mermaid` | node (タグ固定) | `.mmd` → svg / pdf | `docker/mermaid/convert.sh` が未ビルドなら自動でビルドする |
| `docx-paper-template-svg-converter` | alpine (タグ固定) | svg → pdf / svg → 文字をアウトライン化した svg (最終図) | `docker/svg-conversion/convert.sh` が未ビルドなら自動でビルドする |

#### 1.2.1 pandoc コンテナ

| 区分 | 中身 | 用途 |
|------|------|------|
| ARG | pandoc `3.6.4` / pandoc-crossref `0.3.19` | 変換エンジンと相互参照番号 (この 2 つは組で更新する。片方だけ上げると crossref が動かない) |
| pip | panflute / lxml / PyYAML | 構造保持 AST 差分 / OOXML の直接操作 / プロファイルの読み込み |
| apt | librsvg (`rsvg-convert`) / pdf2svg | SVG → PNG / PDF → SVG |
| apt | Noto CJK / IPA フォント | 和文の描画 |
| apt | git | `diff.sh HEAD~1` の旧版の取り出し |
| apt | LibreOffice Writer + Impress | 生成した docx / pptx の**読み込み検査**だけに使う (Word / PowerPoint とは独立した OOXML の実装で開けるか)。PDF 化には使わない |

画像処理ライブラリ (Pillow / ImageMagick など) は入れていない。PNG の pHYs の書き込みは標準ライブラリ (`struct` + `zlib`) で
チャンクを組み立てている (`main/00_setup/lib/svg_raster.py`)。

```bash
# 生成物の読み込み検査の例 (Word / PowerPoint の実機の代わりにはならない)
docker compose -f docker/docker-compose.yml run --rm -u "$(id -u):$(id -g)" pandoc \
    soffice --headless --convert-to pdf --outdir jank/ data/output/bhi/figures/Figure1.pptx
```

#### 1.2.2 mermaid コンテナ

- `node` + `@mermaid-js/mermaid-cli` (`mmdc`。版を固定) + headless Chromium + 和文フォント。Puppeteer は
  `--no-sandbox` で動かす。
- `docker/mermaid/config.json` (テーマ) と `docker/mermaid/postprocess-svg.js` (後処理) は**実行時に読み取り専用で被せる**。
  イメージに焼いた写しだけだと、設定を直しても再ビルドするまで古い設定で動くため。
- **ラベルは SVG の `<text>` で出す** (`config.json` の最上位の `"htmlLabels": false`)。HTML のラベル (`foreignObject`) は
  Word と librsvg (PNG フォールバック) で消える。
- 後処理は (1) **`hsl()` などの色を 16 進に直す** (Word / PowerPoint は `hsl()` の色の図形を黒く塗る) と
  (2) **`<text>` に `xml:space="preserve"` を付ける** (語の間の空白を librsvg が落とすため) の 2 つ。生成した SVG に
  `foreignObject` が残っていれば警告する。

#### 1.2.3 svg-conversion コンテナ

- Inkscape + Ghostscript + fontconfig。**MS Core Fonts** はビルド時に取得し、SHA256 (`docker/svg-conversion/mscorefonts.sha256`)
  で検証する。取得・検証に失敗したらビルドを止める (フォントを黙って欠かさない)。オフラインで作るときは取得済みのフォントを
  `fonts/` に置き、`FETCH_MSCOREFONTS=false` で取得を省く。
- **専有フォント** (Calibri / Yu Gothic など) は同梱しない。必要なら利用者が `fonts/` (git 管理外) に置く。無ければ代わりの
  フォントになる (ビルドは続く)。イメージは無いときにだけビルドするので、後からフォントを足したら
  `docker image rm docx-paper-template-svg-converter` で消す (次に使うときに作り直す。`convert.sh --rebuild` でもよい)。
  フォントを含むので、ビルドしたイメージは公開のレジストリに上げないこと。
- svg → pdf は既定で**文字をアウトライン化する** (`--export-text-to-path`)。フォントの無い環境でも字形が保たれるが、文字の
  選択・検索はできなくなり、雑誌の「フォントの埋め込み」の要求とは意味が違う。埋め込みは `figures.font_handling: embed`
  (`convert.sh --embed-fonts`)。`--outline-svg` は pptx に入れる SVG のアウトライン化 (`figures.pptx.text_to_path: true`) に使う。

---

## 2. 段ごとの処理

### 2.0 共通設定 (main/00_setup/)

- `defaults.yaml` — pandoc の共通引数と、pandoc-crossref の設定 (`figureTitle` / `tableTitle` / `figPrefix` / `tblPrefix` など)。
- `filters/generic-style.lua` — (1) 図のパス `*.svg` を `*.svg.png` に書き換える (pandoc の段では PNG を置き、SVG は
  後処理で足す) (2) `custom-style` の適用 (3) テキストボックスの目印を出す (4) 画像の出現順の一覧 (マニフェスト) を書く。
- `filters/color-diff.lua` — 差分の span (`.diff-add` / `.diff-del`) を文字スタイル `DiffAdd` / `DiffDel` に写す。
  生の OOXML の run は書かない。
- `lib/` — OOXML の後処理と共通部品:
  `journal_profile.py` (プロファイルの読み込み・既定値・記事種別の解決) /
  `patch_reference_docx.py` (reference.docx への体裁の焼き込み) /
  `svg_raster.py` (要求 dpi を満たす SVG → PNG) /
  `ooxml_svg.py` (docx と pptx に共通の SVG ネイティブ埋め込み) /
  `svg_pptx.py` (1 図 = 1 pptx の生成)。
- `main/00_setup/lib/` はディレクトリ名が数字で始まりパッケージとして import できないので、呼び出し側が
  `sys.path` に足してから `import journal_profile` する。

### 2.1 図の前処理 (main/step01_figures/)

- **入力**: `<入力ルート>/figs/` の `*.svg` / `*.pdf` / ラスタ図、`figs/mermaid/*.mmd`
- **出力**: `data/step01_figures/figs/` (補正した SVG / PDF 由来の SVG / `*.svg.png`)。**原稿の相対パス
  (`figs/…`・`figs/mermaid/…`) をそのまま再現する**。pandoc には `--resource-path=data/step01_figures:<入力ルート>/figs:.` を
  渡し、相対パス全体を連結して解決させる (ファイル名だけで突き合わせると、図が見つからずに黙って本文から落ちる)。
- **処理**:
  0. **Mermaid**: `.mmd` を mermaid コンテナで svg / pdf にし、以降の図に合流させる。入力の `figs/mermaid/` に同じ名前の
     `.svg` / `.pdf` (単独で描いた残骸) があれば読み飛ばして警告する (作り直した図を古い図で上書きしないため)。
  1. **SVG の文字の切り取りの補正**: R / svglite 由来の `textLength` / `clip-path` を librsvg が誤って描く問題を補正する (冪等)。
  2. **PDF → SVG** (`pdf2svg`)。**変換の直後に SVG ルートの `width` / `height` に `pt` を付ける**。pdf2svg は MediaBox (pt) を
     単位なしの数値で書くため、SVG の規約どおり CSS px と読むと図の公称サイズが 75% になり、300 dpi の保証が PDF 由来の図で
     崩れる。`viewBox` は変えない (縦横比は同じなので描画は変わらない)。書き換えられなかったときは警告する。手書きの SVG の
     単位なしは規約どおり CSS px のまま扱う。
  3. **SVG → PNG フォールバック** (`svg_raster.py`)。
- **公称サイズと解像度** (`svg_raster.py`。step05 の分離出力図も同じモジュールを通る):
  - SVG ルートの `width` / `height` を公称サイズとする。物理単位 (pt / mm / cm / in) はそのまま、単位なしと px は
    **CSS px = 1/96 inch**、`width` / `height` が無ければ `viewBox` を CSS px として読む。
  - 公称サイズ × 要求 dpi から画素数を計算して `rsvg-convert -w/-h` に渡す (`-d/-p` の dpi は物理単位の SVG にしか効かない)。
    換算の根拠 (元の寸法・単位・inch・画素数) をログに出す。
  - 生成後に PNG の IHDR から実画素数を読み直し、**目標に届かなければエラーで止める**。PNG の構造 (IEND まで) を確かめてから
    読み書きし、書き戻しは一時ファイル → `os.replace` で行う (中断しても元の PNG は壊れない)。
  - **pHYs (物理解像度) を書く**。pHYs は px/m の整数なので 300 dpi をちょうどには表せず、四捨五入すると pandoc が 299 dpi と
    読むため、切り上げる。
  - SVG はルート要素の開始タグまでしか読まない (必要なのは `width` / `height` / `viewBox` だけ。巨大な SVG でも解析器の
    安全装置を外さずに済む)。
  - 画素数の上限 (`MAX_PIXELS` = 2 億画素) は暴走を止めるためのもので、メモリの実効上限ではない。`rsvg-convert` が途中で
    落ちたときは、エラー文に目標の画素数・基準の寸法・dpi を書く。
  - **寸法の決まらない SVG** (`width` / `height` も `viewBox` も無い) は、step01 (草稿のフォールバック) では警告にとどめて
    `rsvg-convert` の既定の描画に任せ、pHYs は書かない (300 dpi の画像だと偽らない)。step05 (提出図) では止める。
  - **自分で置いたラスタ図はこの経路を通らない** (そのまま複製する)。解像度の保証の対象外で、`check-figures.sh` が「注意」に出す。
- **docx 上の表示寸法**: pandoc は pHYs の無い PNG を 72 dpi とみなすが、pHYs を書いた PNG は SVG の公称サイズどおりに置かれる。
  物理単位で書いた図はその実寸になるので、見た目を変えたいときは原稿で `{width=...}` を付ける。本文幅を超える図は pandoc が
  本文幅に縮める (本文幅を 96 dpi の整数画素に切り捨てて扱うので、A4・余白 25 mm では 159.81 mm)。
- **冪等性**: `figures.sh` を回し直しても SVG / PNG は同じものになる (Mermaid 由来の PDF だけは毎回変わる)。
- **Word / PowerPoint で崩れる SVG の検出** (`check_dpi.py`。`check-figures.sh` の図ツリーのモード): svglite の出力の連結
  (`<g class='svglite'>` が 2 個以上)・`id` の重複・`hsl()` の色を「注意」として出す。確かめていない条件は検出しない。

### 2.2 原稿のビルド (main/step02_build/)

- **入力**: `<入力ルート>/main.md` / `ref.bib` / `data/step01_figures/` / 雑誌プロファイル。`revise-report.md` と
  `cover-letter.md` があれば同じ仕組みで docx にする。
- **pandoc の呼び出し** (考え方):
  ```
  pandoc <入力ルート>/main.md \
    --from markdown+east_asian_line_breaks --to docx \
    --reference-doc=<誌の reference.docx> \
    --resource-path=data/step01_figures:<入力ルート>/figs:. \
    --filter pandoc-crossref \
    --lua-filter main/00_setup/filters/generic-style.lua \
    --citeproc --bibliography=<入力ルート>/ref.bib --csl=<誌の CSL> \
    --output=data/step02_build/main.docx
  ```
- **reference.docx と CSL の解決** (`build_docx.py`): `profile.yaml` の `reference_doc` / `csl` が指すファイルがあればそれを、
  無ければ `_default` のものを使う。継承したときは必ず警告する (CSL は「AMA 11th を継承します」、reference.docx は継承した
  体裁と、`profile.yaml` の体裁キーで食い違うもの)。自前の reference.docx があるときは、焼き込まれた体裁が `profile.yaml` と
  一致するかを検算し、食い違えば `make-reference.sh` の再実行を促す。
- **reference.docx の自動生成** (`scripts/lib/ensure-reference.sh`。`build.sh` / `diff.sh` が使う): `_default` の
  reference.docx と、`reference_doc: reference.docx` の誌の reference.docx が無ければ、`make-reference.sh` で作ってから
  ビルドする。`reference_doc` が別の名前 (雑誌が配るテンプレート) を指していて無いときは作らない (人が置くファイルを
  作り物で置き換えない)。
- **後処理** (Python + lxml。`postprocess.py`):
  - 表に三本線 (booktabs) の罫線を付ける (`.grid` Div の中は全罫線)。
  - **SVG のネイティブ埋め込み** (`ooxml_svg.py`): `a:blip > a:extLst > a:ext uri="{96DAC541-…}" > asvg:svgBlip r:embed` を
    入れ、`word/media/*.svg` を同梱し、`[Content_Types].xml` に `image/svg+xml` を登録する。図の対応は画像のマニフェスト
    (出現順・キャプション・テキストボックス内かどうか) で取り、件数と順序を検算する (位置の一致だけに頼らない)。
  - `.textbox` Div を `wp:anchor` のテキストボックスにし、`page` 属性の位置へ置く。
  - `line_numbers_scope: manuscript` の誌では、`main.md` 以外の docx の節設定から行番号 (`w:lnNumType`) を外す。
- **出力**: `data/step02_build/*.docx` と、どの誌でビルドしたかの記録 `data/step02_build/.journal`
  (package が `--journal` と照合する)。入力に無い任意の文書 (revise-report / cover-letter) の前回の docx は消す
  (入力ルートを切り替えたときに別の原稿の docx が残らないように)。

### 2.3 全領域差分 (main/step03_diff/)

詳しい設計は [`docs/design-fullarea-diff.md`](design-fullarea-diff.md)。

- **入力**: 2 つの版の `main.md` (git の revision か、明示した 2 ファイル)。図は新版の図ツリー、文献は新版の `ref.bib` で解決する。
- **方式**: 構造保持 AST 差分 (latexdiff の発想を pandoc の AST の上で行う)。
  1. 旧版・新版をそれぞれ `pandoc -t json` で AST にする。
  2. **二層の差分** (Python + panflute): ブロック列を LCS で整列し (`Div` / 表 / リストには再帰する)、残った削除と追加を
     類似度で突き合わせて「変更」の組にし、組になった段落の中を語単位で差分にする。変わった語を `Span`
     (`.diff-add` / `.diff-del`) で包み、引用・相互参照・数式は要素のまま温存する。表は行を整列し、セルの位置で
     突き合わせてセルの中に再帰する。
  3. マージした AST を build と同じ引数 (reference.docx / CSL / defaults.yaml / フィルタ) で docx にし、最後に
     `color-diff.lua` で span を文字スタイルに写す。
  4. 後処理は build と同じ。加えて `word/styles.xml` に `DiffAdd` (青 `#2E74B5`) / `DiffDel` (赤 `#C00000` + 取り消し線) を
     **毎回入れる** (雑誌が配るテンプレートがこの 2 スタイルを持たなくても色が出るように。定義が無いと黙って無着色になる)。
- **全領域**: `custom-style` Div で書いたタイトル・著者・所属・抄録・キーワードも温存され、中身が差分になる。表とテキストボックスの
  中の表のセルも差分になり、色は run のプロパティなのでテキストボックスの中にも運ばれる。
- **既知の制限**: 段落・文の移動は削除 + 追加になる。結合セルを含む表の整列は曖昧になりうる。削除した引用も温存されるので、
  番号順の引用様式では差分版の引用番号が旧版とも新版とも一致しないことがある。文献リストと相互参照番号は再生成される。
  数式は式ごとの削除 + 追加になり、ラベルつきの式を編集するとその式への参照が壊れる。コードブロック・生 OOXML・水平線の変更は
  着色せず新旧を併記する。見出しレベルだけの変更は全削除 + 全追加になる。表の列の増減では後ろの列がずれうる。削除した図は
  画像を描かず、キャプション (赤) だけを残す。語の間に空白の無い言語の本文は、句ごとの削除 + 追加になりうる。

### 2.4 PDF の生成 (main/step04_pdf/ — roundtrip)

配置・診断・既知の制限は [`docs/roundtrip-windows-watcher.md`](roundtrip-windows-watcher.md)。

1. ビルドの成果 (`data/step02_build/*.docx` / `data/step03_diff/*.docx`) を `data/output/` に集める。古い docx を消すのは
   `data/output/*.docx` (直下) だけで、step05 が書く `data/output/<id>/` には触れない。
2. 送出先の `.watcher-alive` で watcher の生存を確かめ (止まっていれば警告。中止はしない)、前回の PDF を送出先の
   `__archives/` へ退避する (**退避できなければ中止** — 待つ段は名前の一致だけで「届いた」と判断するので、古い PDF を
   今回の成果として持ち帰らないため)。続いて docx を rclone で送る。
3. Windows の watcher (`main/step04_pdf/windows/watch-and-convert.ps1`) が Word COM で PDF にし、**送出先の直下
   (docx の隣)** に書く (docx は `processed/`、失敗は `error/` へ移す)。
4. 待つ PDF (`data/output/*.docx` の名前から決まる) が**全部揃うまで**待ち (既定 10 分・10 秒間隔)、`data/products/` へ取り込む。
5. **提出パッケージの配送**: `SUBMISSION.md` を持つ `data/output/<id>/` (既定は全部。`--package <id>` で絞り、`--no-package` で
   使わない) を、送出先の `submission-<id>/` に置く。表と図は 1 階層に並べ、`rclone sync` で中身を一致させ、消えた・置き換わった
   ファイルは `__archives/submission-<id>_<時刻>/` へ退避し、手元の写し `data/products/submission-<id>/` と `rclone check` で
   照合する。手順 1 ではパッケージの本文と表も `<id>-manuscript.docx` / `<id>-Table1.docx` … の名前で集めて PDF 化に回す
   (集めるのは写しで、パッケージは動かさない)。パッケージが草稿モードで作られている・パッケージより新しい原稿 / ビルド /
   誌のプロファイルがある・`SUBMISSION.md` に書いた入力ルートが今の入力ルートと違う (または書かれていない) ときは、
   **何も送らずに止める**。watcher は送出先の直下の docx しか見ないので、サブフォルダは変換されない。

- **送出先** `gdrive:tmp/<リポジトリのディレクトリ名>` の算出は `scripts/lib/gdrive-dest.sh` だけが持ち、`roundtrip.sh` /
  `push-win-tools.sh` / `check-pdf-path.sh` が共有する (送出先のずれはビルドの成否に現れず、「PDF が返らない」という形でしか
  分からないため)。
- **watcher の作り**: docx を `%TEMP%` の作業フォルダにコピーして変換し (Google Drive の同期のロックから切り離す)、変換は
  **子プロセス**に出して **1 ファイル 120 秒で打ち切る**。打ち切るときに止めるのは**その変換が起動した WINWORD だけ**
  (起動の前後の WINWORD の一覧の差から PID と起動時刻を記録し、特定できなければ止めない)。待つ間も `.watcher-alive` を
  更新し、2 行目以降に実行中の watcher の版 (MD5) と設定を書く (`check-pdf-path.sh` と `roundtrip.sh` が読み、再起動忘れと
  試験用の起動のままの放置を知らせる)。docx は普通に開き、開けなかったときだけ修復して開く (修復したら `REPAIRED:` で知らせる)。
  1 ファイルで何が起きても watcher は止まらない。

### 2.5 投稿パッケージ (main/step05_package/)

- **入力**: ビルド済みの docx (`data/step02_build/`)、差分 docx (`data/step03_diff/`。任意)、図 (`data/step01_figures/`)、
  雑誌プロファイル。
- **処理**: `scripts/package.sh` (ホスト) → `package.py` (コンテナ)。Inkscape が要る変換 (pdf 化・アウトライン化) は
  `package.py figure-plan` が必要な変換を TSV で列挙し、`package.sh` が svg-conversion コンテナで回す。
- **モード**: `profile.figures.embed` で決まる (`true` → 草稿 / `false` → 最終)。`--mode` で上書きできる。
  - **草稿 (draft)**: 図を埋め込んだ `main.docx` をそのまま `manuscript.docx` にする。
  - **最終 (final)**: 本文の inline の図 (`wp:inline`) を除いて `[Figure N about here]` に置き換え、図を `figures/` に
    分離して出す。テキストボックス (`wp:anchor`) の中は図として扱わず残す。
- **出力**: `data/output/<id>/` に `manuscript.docx` / `figures/` / `revise-report.docx` / `cover-letter.docx`
  (+ 差分があれば `manuscript-diff.docx`、`supplementary/`、`SUBMISSION.md`)。`tables.placement: separate` の誌は
  `tables/TableN.docx`、`SUBMISSION.md` を書く誌は `CAPTIONS.md` も出る (下の「提出構成の組み替え」「提出マニフェスト」)。毎回作り直す。

#### 図の生成経路

主形式は `figures.formats` の先頭 (`--format` で上書き)。

| 形式 | 作り方 |
|------|-------|
| `pdf` | Mermaid 以外の SVG を svg-conversion で PDF にする (`font_handling: outline` で文字をアウトライン化 / `embed` で埋め込み)。Mermaid 図は mermaid コンテナが作った PDF を使う |
| `png` | `svg_raster.py` が `figures.dpi` (または `--dpi`) を満たす画素数で作り、pHYs を書く (§2.1 と同じ換算) |
| `pptx` | 1 図 = 1 pptx = 1 スライド (下の「pptx の経路」) |

- `eps` → pdf / `tiff` → png は警告つきで代わりに作る。TIFF をそのまま作る経路は持たない (pandoc コンテナに画像ライブラリが
  無く、足すと全ビルドが使うイメージが重くなるため。PNG を受け付ける誌では PNG で要件を満たせる)。`jpeg` は作らない
  (線画を非可逆圧縮で劣化させるため。指定すると止まる)。
- 作れない形式 (綴りの誤りを含む) は**ほかの形式に代えずに止める**。代わりの形式が `submission.figure_formats` に無い誌でも止める。
  受入形式外の形式を明示したときは `--allow-disallowed-format` を要求する。判定は図を実際に出す直前 (最終モードで
  `--keep-figures` でないとき) に行う。
- 自分で置いたラスタ図は原寸で複製し、その解像度 (実画素数と pHYs) を毎回表示する。

#### pptx の経路と案 A / 案 B / 案 B′

*BioHealth Informatics* の受入形式 (JPEG / TIF / PNG / PowerPoint) でベクターを保てるのは PowerPoint だけなので、SVG を
一次ソースに保ったまま pptx を作る経路を持つ。本テンプレートは pptx の作り方を 3 つの名前で呼び分ける
(`figures.pptx.mode` の値・ログ・`SUBMISSION.md` の注意にこの名前で出る):

| 呼び名 | `figures.pptx.mode` | 中身 | 状態 |
|-------|---------------------|------|------|
| **案 A** | `passthrough` (`svg-blob` でも図の隣に同名の `.pptx` があればこちらになる) | 執筆者が PowerPoint で仕上げた `.pptx` を**無変換でコピー**する。劣化が無い。1 スライドであることとマクロが無いことを機械で確かめる。中身はテンプレートの検査の対象外 | 実装済み |
| **案 B** | `svg-blob` (既定) | SVG から 1 スライドの pptx を生成し、**SVG をネイティブで埋め込み + PNG フォールバック**を同梱する | 実装済み |
| **案 B′** | `native-shapes` | SVG を PowerPoint のネイティブの図形 (編集できるシェイプ) に変換する | **作っていない**。変換の品質が安定しないため。指定すると止まる (黙って案 B にすると「編集できるシェイプ」の要求に応えたことにならないため) |

- **SVG のネイティブ埋め込みは docx と pptx で同じ仕組み**なので、`ooxml_svg.py` を両方が使う (`p:pic/p:blipFill/a:blip` の下に
  同じ拡張を入れる)。
- 骨格は `pandoc --print-default-data-file reference.pptx` をコンテナの中で取り出して加工する (追加の依存なし。同梱もしない)。
  1 スライドに間引き、レイアウトは Blank を指す。`docProps/core.xml` / `app.xml` は中立な内容で書き直し、zip の項目の時刻と
  書き出し順を固定するので、同じ入力なら同じバイト列になる。
- **スライドの寸法は図の公称サイズに合わせる** (`slide_fit: figure`)。PowerPoint の規格 (1〜56 inch) の下限を割る軸は
  スライドを 1 inch に広げて図を中央に置き (足した余白は警告)、上限を超えると止めて `--slide-fit fixed` (既定の寸法に
  縮めて置く) を案内する。スライドを図に合わせても、SVG の `viewBox` の中の余白は残る (余白の切り詰めは作図の側で行う)。
- PNG フォールバックは**実際に置く寸法**でラスタ化する (`fixed` で縮めて置くときは、その寸法の画素数になる)。
  Office 2016 以前と多くのビューアではこの PNG が表示されるので、保険ではなく受け手が実際に見る品質として要求 dpi を満たす。
- `figures.pptx.text_to_path: true` のときだけ、埋め込む SVG の文字をアウトライン化する (svg-conversion の `--outline-svg`)。
  既定は `false` — 組版で組み直す誌では文字を図形にすると直せなくなり、PNG フォールバックはコンテナの中のフォントで描いて
  あるのでフォントの環境の差の影響が小さいため。
- **元がラスタの図は pptx に包まず、画像ファイルのまま出す** (包んでも拡大に強くはならない)。
- Microsoft 365 の PowerPoint で SVG 側が描画され、グループ化を解除すると文字を編集できることを確かめている。PNG 側が描画される
  環境 (投稿系の査読用 PDF の変換など) での見え方は確かめていない。

#### 提出構成の組み替え (`relocate.py`)

原稿は図表を本文中の自然な位置に書いたまま雑誌に依存させず、「表は末尾 (または別ファイル)」「図の題と凡例は References の後」
という誌の要求は**提出物を作る段**で満たす。最終モード (`--mode final` かつ `--keep-figures` なし) でだけ動き、何をするかは
次の 2 キーで決まる。

- `tables.placement: end` — 本文の `w:tbl` を「題 (`TableCaption`) + 表 + **直後に連続する `Legend` 段落すべて**」の 1 組として
  文書の末尾へ移し、元の位置に `[Table N about here]` を入れる。題の無い表は `[Untitled table about here]` にして警告する。
  前に置く見出しは `tables.section_title` で選ぶ (既定は見出しなし・改ページだけ)。
- `tables.placement: separate` — 同じ 1 組を本文から外し (元の位置のプレースホルダは `end` と同じ)、`package.py` の
  `write_table_files()` が `tables/TableN.docx` に **1 表 1 ファイル**で書く。表のファイルは、組み替えた本文の書庫を複製して
  `w:body` をその組と元の `w:sectPr` だけにしたものなので、スタイル・番号・フッタを本文と共有する (別の reference.docx から
  組み立て直すと、本文と表で体裁がずれうる)。題は表の上、凡例は表の下。行番号は `line_numbers_scope: manuscript` なら外す。
  表の体裁の検査は表のファイルにも掛ける。本文の docx はテキストだけになる。
  `tables.placement` の値は `inline` / `end` / `separate` のどれかで、それ以外の綴りは**止める**
  (`relocate.table_placement()`。綴りの誤りで表が本文に残ったまま、警告なしに提出物ができるのを防ぐ)。
- `figures.legends_section: <見出し>` — 「`ImageCaption` (題) + **直後に連続する `Legend` 段落すべて**」を本文から抜き、
  改ページつきの見出し (`Heading1`) の下へ集める。画像の段落は動かさない (`[Figure N about here]` が本文の元の位置に残る)。
- **挿入は常に `w:sectPr` の直前**。`w:sectPr` は `w:body` の最後の子でなければならず、後ろに要素があると Word が修復を
  促す。抜いては入れる操作なので、位置は添字ではなく要素を基準にし、最後に「body の最後の子が sectPr か」を検算する。
- 順序は Figure Legends → 表 (規定の References → Figure legends → Tables。`separate` では表が本文に来ない)。References が本文の最後の節なら、sectPr の直前に
  入れれば「References の後」になる (規定チェックが「References が最後の節か」を見る)。
- **`w:body` の直接の子だけ**を見るので、テキストボックスの中身 (`w:txbxContent` の下) は構造的に対象外になる。
- **ブックマークは動かさない**。pandoc-crossref は図表の前後にブックマークを置き、本文の "Fig. 1" / "Table 1" はそこへの
  ハイパーリンクなので、段落と表だけを抜けば相互参照はプレースホルダの位置に着地する。
- **`end` で連続する `w:tbl` の間には段落を挟む** (Word は続いた 2 表を 1 つに結合する)。
- **番号の検算**: キャプションの番号が 1..n の連番か、題の無い画像が途中に紛れていないか (紛れていると、その後ろの図ファイルが
  すべて凡例とずれる) を確かめ、`figures/` の件数と集めた題の件数の食い違いも警告する。
- **表の体裁の検査** (`tables.allow_color: false` の誌): 網掛け (`w:shd`。テーマ色だけの網掛けも)・文字色・蛍光ペン・罫線の色を
  検出して警告する。草稿モードでも読み取りだけで掛ける。走査は最も外側の表から行う。

#### 規定チェック (`validate.py`)

Markdown の層で原稿を読み、上限と執筆の検査を掛ける。結果は「規定違反の可能性 (要修正)」と「参考情報」に分け、
**エラーにはしない** (終了コードは常に 0)。`validate()` はファイルに触れないので、成果物は変わらない。

- **本文語数の数え方**: メタの Div (Title / Author / Affiliation / Corresponding / Keywords / Abstract / Legend)・References 節・
  `#refs` Div・表の行・キャプションの行を除く。`declarations.abbreviations_section: true` の誌では `# Abbreviations` 節も除く。
  図表の凡例 (`Legend`) は除き、除いた語数を図 / 表に分けて出す。ただし直前に図表が無い凡例 (配置の誤り) は、提出物でも本文に
  残るので算入する。
- **ブロック走査層**: 位置関係を見る検査が多いので、原稿を文書順のブロック列にならす層を置いた。`.textbox` / `.grid` / `#refs` の
  中には入り、`custom-style` Div の中には入らない。テキストボックスの中のブロックには印を付けて図表の点数に数えない
  (数えなかった点数は概算行に必ず出し、`limits.figures_tables` を持つ誌では要修正にする)。表のキャプション行は隣の表に畳む
  (pandoc はキャプションを表の前にも後にも書けるため)。
- **凡例 Div の検査**: 対応関係は「対象の直後に置く」という位置だけで表し、`for` 属性は docx に出ない。そこで Markdown の層で
  位置と `for` を突き合わせる (直前が図表でない / `for` が実在しない識別子を指す / `for` が直前の図表と食い違う / `for` が無い)。
  **中身が段落だけか**も見る — 箇条書き・番号つきリスト (`(A)` / `a.` / `IV.` などの形も)・表 (pipe / simple / grid)・画像の段落・
  見出し・引用・入れ子の Div・コードブロック (フェンス / 空白 4 個以上の字下げ)・定義リスト・水平線を入れると、docx で `Legend` の外の
  段落・表・図になって集約がそこで止まるため (行ブロックと脚注の定義は `Legend` 段落のまま並ぶので指摘しない)。判定は pandoc の読み方に合わせ、新しいブロックが始まりうる位置 (凡例の 1 行目と空行の直後) だけを見る。
- **記入欄 `<<...>>` の残り**: pandoc は `<Given-name Family-name>` のような中身を HTML のタグとみなして捨て、docx には `<>` だけが
  残るので、Markdown の層で捕まえるしかない。`main.md` / `cover-letter.md` / `revise-report.md` を読み、改行をまたぐ記入欄も拾う。
- **数値の桁区切りカンマ**: コメント・コード・URL・References を除き、`1,234` の形の数値を本文と表の両方で拾う
  (表の体裁は docx の層、数値の書き方は Markdown の層、と分けている)。
- **指摘の行番号**: 複数行の構文を同じ行数の空行に潰してから検査するので、指摘の行番号は原稿と一致する。
- **走査層の前提**: Div の開始は `::: {…}` (波括弧つき) と書く。「References が最後の節か」は第 1 レベルの見出しだけを見る。
- lint の既定値の置き方 (基底と誌の 2 層) は [`docs/profile-schema.md`](profile-schema.md) の「lint の 2 層構成」。

#### 提出マニフェスト `SUBMISSION.md` と補足資料

- `submission.text_formats` を持つ誌にだけ出す (`submission` のほかのキーだけでは出さない。中途半端なマニフェストで
  「この誌はフォームを求めていない」のように、調べていないことが断定に化けないように)。値の無い項目は「プロファイルに記録なし
  (規定を確認すること)」と書く。
- 投稿系のアップロードの種類ごとにファイルの一覧・順序・形式・サイズを並べ、`submission.forms` のチェック欄を付ける。
  サイズは一覧であって上限の判定ではない (上限を持つのは動画の `limits.video_mb` だけ)。図の一覧は書き出した順 (= 本文の初出順)
  をそのまま使う (ディレクトリを読み直すと `Figure10` が `Figure2` より前に来る)。
- **実行時の状態と検出した問題を反映する**: 組み替えをしなかった実行では冒頭に「提出用ではない」を出し、規定チェックの指摘と、
  この実行で出た注意をすべて転記し、規定に反するファイルの行に印を付ける。画面のログが流れた後に残る唯一のチェックリストだから。
- **入力ルートの記録**: どの原稿 (入力ルート) から作ったパッケージかを 1 行書く。roundtrip が Drive へ届ける前に、今の入力ルートと
  照合する (§2.4 の手順 5。動作例で作ったパッケージが残っていても、日付だけでは見分けられないため)。
- **`CAPTIONS.md`**: 投稿系のファイルを上げる画面 (File Upload) は、上げたファイルごとに書式なしの Caption / Legend 欄を持つ。
  図表の題と凡例を手で写すと本文と食い違うので、**提出するファイルそのもの** (`manuscript.docx` の Figure Legends 節と
  `tables/*.docx`。`end` なら本文の末尾) から抜き出し、表 → 図の順に 1 ファイル 1 項目で並べる。欄は書式を持てないので、
  上付き・下付きは Unicode の文字に置き換え、置き換えられない文字 (`^(…)` / `_(…)` と書く) と斜体・太字は項目の下に注記する。
  `SUBMISSION.md` を書く誌だけに出し、`SUBMISSION.md` の「アップロード種別ではないもの」の節に載せる。
- **補足資料**: `<入力ルート>/supplementary/` を `data/output/<id>/supplementary/` へ無変換で複製する (受け取ったまま公開する誌の
  ため)。動画は拡張子で分類し (受入形式で分類すると受入外の形式が検査から漏れる)、`limits.video_mb` (10 進) の超過と受入形式外を
  警告する。OS の管理用ファイルは複製せず、除いた件数を報告する。

---

## 3. 雑誌プロファイル (data/journals/<id>/)

投稿規定の違いをプロファイルに閉じ込め、`main.md` は雑誌に依存させない。

```
data/journals/<id>/
├── profile.yaml       # 規定のパラメータ (docs/profile-schema.md)
├── <id>.csl           # 引用様式 (無ければ _default の CSL を継承)
├── reference.docx     # 体裁を焼き込んだ Word のテンプレート (生成物。雑誌が配るものを置いてもよい)
└── skeleton/          # (任意) 誌固有の原稿骨格
```

- 同梱は `_default` (汎用の投稿フォーマット) と `bhi` (*BioHealth Informatics*)。テンプレートを特定の誌の専用にしない —
  誌固有の要件は `profile.yaml` のキーの拡張で吸収し、新しいキーはすべて省略できて、未指定なら何もしない側に倒す。
- **reference.docx は生成物**: `data/journals/make-reference.sh <id>` が pandoc の既定の reference.docx をコンテナの中で
  取り出し、`profile.yaml` の体裁 (`line_spacing` / `line_numbers` / `page_numbers` / `font` / `font_size` / `margins` /
  `paper_size` / `text_styles.*`) を `patch_reference_docx.py` で焼き込む。あわせて差分の文字スタイル (`DiffAdd` / `DiffDel`) と、
  `custom-style` Div の受け皿になる段落スタイル (`Affiliation` / `Keywords` / `Corresponding` / `Legend`) を入れる。
  zip の項目の時刻を固定しているので、何度作っても同じバイト列になる。pandoc の既定データを加工したものなので
  リポジトリには同梱せず、`build.sh` / `diff.sh` が無ければ作る (§2.2)。
- **体裁キーの読み手は `make-reference.sh` だけ**で、build / package の実行時には読まない (体裁は reference.docx に焼き込む)。
  したがって体裁を変えたら `make-reference.sh` を回し直す。忘れたときは build と規定チェックが食い違いを警告する。
  例外は `line_numbers_scope` で、焼き込んだ節設定から行番号を外す形で build が効かせる。
- `page_numbers: true` のときだけフッタ (`PAGE` フィールド) を作る。未指定の誌にはフッタの部品も関係も入らない。
- 題 (`Title`) の行送りは、pandoc の既定 (シングル) から本文の行送りに直す。`text_styles` を持つ誌はさらに、
  `uniform_size` で級数を持つスタイル (題・副題・著者・日付・抄録・見出し 1〜3 など) をすべて本文の級数にそろえ、見出しの階層を
  強調で付け (題・見出し 1 = 太字 / 見出し 2 = 太字斜体 / 見出し 3 = 斜体。題を継ぐ著者・日付・副題には継いだ強調を打ち消す)、
  `heading_color: black` で題・見出しのテーマ色を外し、`uniform_line_spacing` で段落スタイルが個別に持つ行送りを外して文書全体の
  行送りにそろえる。どれも省略時は何もしない (既存の誌の出力は変わらない)。
- 行番号は 1 行目を 1 から数える (`w:lnNumType` の `w:start="0"`。Word はこの値に 1 を足した番号から始める)。

---

## 4. 入出力とデータ管理

| 種類 | 置き場所 | git |
|------|---------|-----|
| 原稿 (一次ソース) | `src/` (main.md / ref.bib / revise-report.md / cover-letter.md / figs/ / supplementary/) | 追跡する |
| サンプル原稿とフィクスチャ | `data/dummy/` (`src/` と同じ構成) | 追跡する |
| 雑誌プロファイル | `data/journals/` (同梱 2 誌の `reference.docx` は生成物なので追跡しない) | 追跡する |
| 本番の図・素材 (補助) | `data/source/` | 追跡しない |
| 図の中間生成物 | `data/step01_figures/` | 追跡しない |
| ビルドした docx | `data/step02_build/` | 追跡しない |
| 差分 docx | `data/step03_diff/` | 追跡しない |
| 提出物の集約 | `data/output/` (`<id>/` = 投稿パッケージ) | 追跡しない |
| Word で変換した PDF | `data/products/` | 追跡しない |
| 一時ファイル | `jank/` (`diff.sh` の旧版・回帰スナップショット) | 追跡しない |

- **入力ルート**: `.development` が有れば `data/dummy/`、無ければ `src/` (存在だけで判定し、中身は見ない)。環境変数 `INPUT_ROOT` と
  `--input` で上書きできる。原稿の正本は常に `src/` で、`data/source/` は git に入れたくない素材の置き場に限る。
- clone した直後の `src/` は雛形 (`src/README.md` と空の `figs/`) だけで、`main.md` はまだ無い。まず `.development` でサンプルを
  通し、`cp -r data/dummy/. src/` などで原稿を起こす。
- **コードとデータを分ける**: `main/` にはデータの生成物を置かない。段のコードは `main/stepNN_name/`、段の出力は `data/stepNN_name/`。
- **冪等性**: 同じ入力なら図の前処理・pptx・reference.docx は同じバイト列になる。docx は `docProps/core.xml` の作成時刻だけが変わる
  (回帰の比較は docx を zip の部品ごとに内容で比べる。`scripts/compare-snapshots.py`)。

---

## 5. 制約と既知の制限

- **PDF は roundtrip に依存する**: rclone のリモートと、送出先のフォルダで動く Windows の watcher が要る。無ければ docx までは
  作れるが PDF は作れない。watcher が無いまま送ると、変換されずにタイムアウトする (`roundtrip.sh` は送る前に生存記録を見て
  警告する。事前の確認は `check-pdf-path.sh`)。
- **ネイティブ SVG の閲覧環境**: ベクターで表示するのは Microsoft 365 / Office 2019 以降。Office 2016 以前と一部のビューアは
  PNG フォールバックを表示する (ファイルは壊れない)。そのため PNG フォールバックの解像度は、多くの受け手が実際に見る品質として
  要求 dpi を満たすように作る。代わりに docx は大きくなる。
- **PDF → SVG の品質**: 複雑な PDF (透明・特殊なフォント) は pdf2svg で崩れることがある。崩れる図は元のデータから SVG で出し直す。
  PDF しか無いときは、PDF を直接ラスタ化して PNG で置く。
- **和文フォント**: pandoc / mermaid コンテナに Noto CJK と IPA を入れてある。Windows で変換したときのフォントの違いに注意する。
- **語数・ページ数**: `profile.yaml` の上限は検査の補助で、最終の判断は実物で行う。刷り上がりのページ数は組版の後にしか
  分からず、検査しない。
- **Mermaid**: headless Chromium を `--no-sandbox` で動かす。権限の厳しい環境では調整が要ることがある。
- **svg-conversion のフォント**: 専有フォントが無ければ代わりのフォントになる (警告のみ)。MS Core Fonts の取得に失敗したら
  ビルドを止める。
- **段組・和文フォント・非対称の余白・日本語のスタイル名は扱わない**。同梱の 2 誌 (英文・1 段組・四辺一律の余白) に要らないため。
  2 段組は原稿に生 OOXML (`sectPr` + `<w:cols>`) を書けば作れる。`margins` は四辺一律の代表値として焼き込む。
  `custom-style` に日本語のスタイル名を書くと pandoc は通すが、差分の温存と語数の除外の対象にならない。これらが要る誌では、
  個別に足すより、雑誌が配る reference.docx をそのまま使う経路を作るほうが安い見込みである。
- **図の種類ごとの解像度** (線画 1200 dpi / 写真 300 dpi など) は表せない。線画かどうかを知る手段がパイプラインに無いため。
  `--dpi <n>` で全図を高い解像度にすれば規定は満たせる。
- **匿名化は自動では行わない**。`blinded: true` の誌では `package.sh` が注意を出す。
