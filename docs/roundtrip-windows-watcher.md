# PDF 変換経路 (roundtrip-windows-watcher.md)

docx → PDF を **Windows の Microsoft Word (COM)** で行う経路 (step04 = `scripts/roundtrip.sh`) の、Windows 側の
watcher の配置・経路の診断・動作の要点・既知の制限をまとめる。**任意の機能**で、使わなければ docx までは Linux だけで完結する。

なぜ LibreOffice で PDF にしないかは [`docs/architecture.md`](architecture.md) §0 (設計上の確定事項。最終体裁の再現性を
最優先する)、Linux 側の段の流れは同 §2.4、日々の使い方は [`docs/usage-guide.md`](usage-guide.md) §6 にある。

> 一言で言うと: Linux が Google Drive の送出先フォルダに docx を置き、Windows の watcher が Word で PDF にして
> **同じフォルダ (docx の隣)** に書き、Linux がそれを取りに行く。

---

## 1. 全体像

```
[Linux]  scripts/roundtrip.sh
   data/step02_build/*.docx                    段 1-2: ビルドと集約
   data/step03_diff/*.docx   ──▶ data/output/  ─────────────────────────┐
   data/output/<id>/ (提出パッケージ) の本文と表 ──▶ <id>-manuscript.docx 等 │
                                                                         │ 段 3: rclone で送る
                                                                         ▼
[Google Drive]  送出先 = gdrive:tmp/<リポジトリ名>/   (scripts/lib/gdrive-dest.sh が算出)
   ├── main.docx, main_diff.docx, ...          ◀── Linux が送る
   ├── main.pdf,  main_diff.pdf,  ...          ◀── watcher が docx の隣に書く ──┐
   ├── watch-and-convert.ps1 / .bat            ◀── push-win-tools.sh が置く     │
   ├── word-to-pdf.bat                         ◀── 同上 (単発変換用)           │
   ├── .watcher-alive                          ◀── watcher が 60 秒ごとに更新   │
   │                                               (時刻 + 版と設定)             │
   ├── watch-and-convert.log                   ◀── watcher のログ               │
   ├── processed/ ── 変換した docx の移動先                                     │
   ├── submission-<id>/ ── 提出パッケージ (段 5。watcher は触らない)             │
   ├── error/     ── 変換できなかった docx の移動先 (失敗したときだけ作られる)  │
   └── __archives ── 前回の PDF (Linux が送る直前に退避する)                    │
                                                                                │ 段 4: rclone で取り込む
[Windows]  watch-and-convert.ps1 (常駐)                                         ▼
   docx を見つける → %TEMP% へコピー → 子プロセスで Word COM 変換   [Linux] data/products/*.pdf
   (1 本 120 秒で打ち切り) → PDF だけを同じフォルダへ
```

| 道具 | 動く場所 | 役割 |
|------|---------|------|
| `scripts/roundtrip.sh` | Linux | ビルド → 集約 → 送る → PDF を待つ → 取り込む → 提出パッケージを届ける (段 5) |
| `scripts/push-win-tools.sh` | Linux | Windows 側の 3 ファイルを送出先へ送り、内容がローカルと一致するかまで照合する |
| `scripts/check-pdf-path.sh` | Linux | 経路の診断 (既定は読み取りだけ・数秒)。`--full` で docx を 1 本往復させる |
| `scripts/lib/gdrive-dest.sh` | Linux | 送出先の算出の**唯一の定義** (上の 3 本が source する) |
| `scripts/lib/watcher-alive.sh` | Linux | 生存記録の 2 行目以降 (実行中の watcher の版と設定) の読み方 (`check-pdf-path.sh` と `roundtrip.sh` が source する) |
| `main/step04_pdf/windows/watch-and-convert.ps1` | Windows | 自分が置かれたフォルダを監視し、docx を PDF にする |
| `main/step04_pdf/windows/watch-and-convert.bat` | Windows | 上の起動用 (ダブルクリック) |
| `main/step04_pdf/windows/word-to-pdf.bat` | Windows | 単発変換 (docx をドラッグ&ドロップ)。watcher とは独立に使える |
| `main/step04_pdf/inspect_pdf_figures.py` | Linux | 返ってきた PDF の図がベクターで載っているかの判定 (§6) |

---

## 2. 前提条件

| 場所 | 必要なもの |
|------|-----------|
| Linux | `rclone` が入っていて、Google Drive のリモート (既定名 `gdrive:`) が設定済み |
| Windows | **Microsoft Word** (COM 変換に必須)。Windows PowerShell 5.1 以上 |
| Windows | **Google Drive for Desktop** が動いていて、送出先フォルダをローカルに同期している |
| 共通 | Linux の rclone と Windows の Google Drive が**同じ Google アカウント**を指す |

SVG をベクターのまま PDF に載せるには、Word が **Microsoft 365 / Office 2019 以降**であること (買い切り版 Office 2016 は
SVG を解釈できず、PNG フォールバックで描く。§6 の 1.)。

### 2.1 送出先の決まり方

送出先は `scripts/lib/gdrive-dest.sh` が次のように決める (3 本のスクリプトが同じ値を使う)。

```
GDRIVE_DEST = ${RCLONE_REMOTE}${GDRIVE_BASE_PATH}/<リポジトリ名>[/${GDRIVE_SUBDIR}]
既定:          gdrive:         tmp             /<作業ツリーのディレクトリ名>
```

| 環境変数 | 既定 | 意味 |
|---------|------|------|
| `RCLONE_REMOTE` | `gdrive:` | rclone のリモート名 |
| `GDRIVE_BASE_PATH` | `tmp` | マイドライブ直下のベースフォルダ |
| `GDRIVE_SUBDIR` | (なし) | さらに下に切りたいときだけ指定する (例 `roundtrip`) |

- **`<リポジトリ名>` は作業ツリーのディレクトリ名**である。このテンプレートを別名で clone した原稿リポジトリは、自分の名前の
  フォルダを使う。論文ごとに送出先が分かれるので、watcher も論文ごとに置く。
- 環境変数を変えたときは、**Windows 側の watcher も同じフォルダに置く**こと。両者が食い違うと、送るのは成功するのに PDF が
  返らない。食い違いはビルドの成否には現れないので、`bash scripts/check-pdf-path.sh` で確かめる (送出先の算出を 1 か所に
  まとめてあるのも同じ理由)。

---

## 3. 配置

### 3.1 Windows 側のファイルを送る (Linux)

```bash
bash scripts/push-win-tools.sh --dry-run   # 何を送るかの確認 (rclone を呼ばない)
bash scripts/push-win-tools.sh             # 3 ファイルを送出先へ送り、rclone check で内容まで照合する
```

送出先フォルダが無ければ作られる。送り終えると、Windows 側の操作手順が表示される。

> **`.ps1` の UTF-8 BOM を落とさないこと。** Windows PowerShell 5.1 は **BOM の無いファイルを UTF-8 ではなく ANSI
> (日本語環境では Shift-JIS) として読む**ので、BOM が落ちた `.ps1` は非 ASCII 文字の前後で解析が崩れて起動できなく
> なることがある。エディタで保存し直したときは確かめる:
> ```bash
> head -c 3 main/step04_pdf/windows/watch-and-convert.ps1 | xxd   # -> "efbb bf" が出れば OK
> ```
> BOM が無ければ付け直してから送り直す:
> ```bash
> python3 -c "p='main/step04_pdf/windows/watch-and-convert.ps1'; \
>   d=open(p,'rb').read(); \
>   open(p,'wb').write(d if d[:3]==b'\xef\xbb\xbf' else b'\xef\xbb\xbf'+d)"
> ```
> 同じく `word-to-pdf.bat` は **CRLF** で保存してある (cmd.exe 向け)。`file` で確かめられる。

### 3.2 watcher を起動する (Windows)

1. Google Drive for Desktop の同期が終わるのを待ち、送出先フォルダを開く
   (例: `G:\マイドライブ\tmp\<リポジトリ名>\`)。3 ファイルが見えることを確かめる。
2. **`watch-and-convert.bat` をダブルクリック**する。PowerShell の窓が開いて監視が始まる (窓は閉じない)。bat は実行ポリシーを
   回避する指定 (`-ExecutionPolicy Bypass`) つきで起動するので、通常はそのまま動く。PowerShell から直接起動したいときは、
   一度だけ `Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser` を実行してから `.\watch-and-convert.ps1`。
3. 起動するとバナーと設定値 (監視フォルダ・ポーリング間隔・**1 ファイルあたりの変換タイムアウト**・作業フォルダ・生存記録・
   ログファイル・**スクリプトの MD5**) が出て、`.watcher-alive` がすぐに書かれる。
   止めるのは **Ctrl+C** (変換の途中で止めても、その変換のために起動した Word は止めてから終わる)。

> **watcher は監視フォルダごとに 1 つ**。スクリプトは「自分が置かれたフォルダ」を監視するので、必ず**この論文の送出先
> フォルダの中**で起動する。別の論文のフォルダの watcher は流用できない。

> **`.ps1` を更新したら起動し直す。** 実行中の watcher はスクリプトをメモリに持ち続けるので、Drive 上の `.ps1` を
> 差し替えても古い版が動き続ける。`push-win-tools.sh` の後は、watcher の窓で Ctrl+C → `watch-and-convert.bat` を
> 起動し直す。起動し直したかは Linux 側から確かめられる — watcher は起動時に読んだ `.ps1` の MD5 を生存記録に書き、
> `check-pdf-path.sh` の [4/5] がローカルの `.ps1` と照合する。

### 3.3 経路を診断する (Linux)

```bash
bash scripts/check-pdf-path.sh          # 読み取りだけ・数秒
bash scripts/check-pdf-path.sh --full   # docx を 1 本送って PDF が返るまで確かめる (Drive に書き込む)
```

| 段 | 見るもの | 失敗・警告のときの対処 |
|----|---------|----------------------|
| [1/5] | rclone があるか | rclone を入れる |
| [2/5] | 送出先に到達できるか | `rclone config reconnect gdrive:`。送出先の名前 (§2.1) を確かめる |
| [3/5] | Windows 側の 3 ファイルが揃い、内容がローカルと一致するか | `bash scripts/push-win-tools.sh` で送り直す |
| [4/5] | `.watcher-alive` が新しいか (既定 300 秒以内。`--stale SEC`)。**実行中の watcher がローカルの `.ps1` と同じ版か** (MD5)・**既定と違う起動引数で動いていないか**・変換タイムアウトの値 | watcher を起動 (し直) す。生存記録が**無い**ときは watcher が起動していない (生存記録を書かない別の版の watcher が動いている場合とは区別できないので、`--full` で確かめる)。時刻だけで**版と設定が無い**ときは、変換タイムアウトを持たない別の版の watcher が動いている |
| [5/5] | (`--full` のときだけ) docx → PDF が返るか | watcher の窓とログ (`watch-and-convert.log`) を見る |

`--full` で送る docx の既定は `data/step02_build/main.docx` (`--docx PATH` で変えられる。待ち時間は `--wait SEC`、既定 300 秒)。
同名の古い PDF が送出先にあれば先に `__archives` フォルダへ退避し、返ってきた PDF も終わった後に `__archives` フォルダへ片付ける。

---

## 4. 使い方 (Linux 側)

watcher を起動した状態で:

```bash
bash scripts/roundtrip.sh                 # ビルド → 集約 → 送る → PDF を待つ → 取り込む
bash scripts/roundtrip.sh --skip-build    # 既存の docx を集約して変換 (別の誌でビルドした docx を見るときは必ずこちら)
bash scripts/roundtrip.sh --skip-push     # PDF を待って取り込むだけ (タイムアウトの後の再開。送り直さない)
bash scripts/roundtrip.sh --dry-run       # rclone を呼ばず流れだけ表示 (ビルドもしない。watcher は要らない)
bash scripts/roundtrip.sh --timeout 15 --poll 15   # 待ち時間 (分。既定 10) とポーリング間隔 (秒。既定 10)
bash scripts/roundtrip.sh --skip-build --no-package   # 提出パッケージを使わない (PDF 化にも回さず、Drive にも置かない)
bash scripts/roundtrip.sh --skip-build --package bhi  # 提出パッケージを 1 誌に絞る
```

- 集約元は `data/step02_build/` と `data/step03_diff/` の docx で、`data/output/` (直下) に集めてから送る。
- **提出パッケージ**: `SUBMISSION.md` を持つ `data/output/<id>/` (既定は全部) の本文と表も、`<id>-manuscript.docx` /
  `<id>-Table1.docx` … の名前で集めて PDF 化に回す (パッケージ自体は動かさない)。PDF が揃ったあとの**段 5** が、パッケージ一式を
  送出先の `submission-<id>/` に置く (表と図は 1 階層に並べる。`rclone sync` で中身を一致させ、消えた・置き換わったファイルは
  `__archives/submission-<id>_<時刻>/` へ退避し、手元の写し `data/products/submission-<id>/` と `rclone check` で照合する)。
  投稿系へ上げるファイルは、このフォルダから選ぶ (送出先の直下や `processed/` には草稿と提出用の docx が時刻付きで並ぶので、
  取り違えやすい)。watcher は送出先の**直下**の docx しか見ないので、サブフォルダは変換されない。
- **提出パッケージを送る前に止める** (何も送らない): パッケージが草稿モード (`--keep-figures` を含む) で作られている /
  パッケージより新しい原稿・ビルド・誌のプロファイルがある / `SUBMISSION.md` に書いた原稿の入力ルートが今の入力ルートと違う・
  書かれていない。動作例 (`--input data/dummy/bhi`) で作ったパッケージは `INPUT_ROOT=data/dummy/bhi bash scripts/roundtrip.sh --skip-build` で送る。
- **引数なしの最初の段は `build.sh` を引数なしで回す** (= `_default` プロファイル)。BHI など別の誌でビルドした docx を見たい
  ときは `--skip-build` を付ける。付けないと `_default` の体裁の docx で上書きされる。
- 集めた docx は**何本でもまとめて送り、全部の PDF が揃うまで待つ**。待つ PDF の名前は `data/output/*.docx` から決まる
  (`main.docx` → `main.pdf`)。
- PDF は `data/products/` に届く。Drive 側の PDF は Windows で見られるよう残し、**次に送る直前に
  `__archives` フォルダ (`<名前>_<時刻>.pdf`) へ退避**する。
- 差分版 (`main_diff.docx`) を PDF にしたいときは、先に `bash scripts/diff.sh` を回してから `--skip-build`。

### 4.1 単発変換 (word-to-pdf.bat)

watcher を使わずに 1 本だけ変換したいときは、Windows で docx を `word-to-pdf.bat` にドラッグ&ドロップする (引数なしで
ダブルクリックすると、同じフォルダで最も新しい docx を変換する)。PDF は docx の隣にできる。途中経過を確かめやすいよう、
実行内容をすべて画面に出す。watcher と違い、**最初から修復つき (OpenAndRepair) で開き、時間での打ち切りは無い**
(固まったら窓を閉じ、タスクマネージャで `WINWORD.EXE` を終了する)。書き出しは watcher と同じ `ExportAsFixedFormat`
(OptimizeFor = Print) で、失敗したときだけ `SaveAs2` に退避する。

---

## 5. 動作の要点

### 5.1 watcher (Windows)

- **状態を持たないポーリング** (既定 5 秒): 毎回、監視フォルダ直下の `*.docx` をすべて見る。Word の一時ファイル
  (`~$*.docx`) は飛ばす。**排他で開けないファイル (Google Drive の同期中など) は飛ばして次の周回でもう一度試す**。
- **`%TEMP%` で変換する**: docx を `%TEMP%\docx2pdf_<一意の名前>\` にコピーして変換し、できた PDF だけを**送出先の直下
  (docx の隣)** へコピーする。Google Drive の同期クライアントが変換中のファイルを掴んで失敗するのを避けるためで、Word が
  Drive のフォルダへ PDF を直接書くより書き込みも短く済む。作業フォルダは成功・失敗・打ち切りのどれでも消す。watcher ごと
  落ちたときの残りは、次の起動時に **1 時間より古いもの**を掃除する。
- **変換は子プロセスで行い、時間で打ち切る**: 固まった Word への COM 呼び出しは戻ってこず、同じ PowerShell のプロセスの中
  からは止められない。そこで watcher は変換用のスクリプト (watcher の中に埋め込んであり、変換のたびに作業フォルダへ書き出す)
  を別の PowerShell として起動し、**1 ファイルあたり既定 120 秒** (`-ConvertTimeoutSec`) で待つ。超えたら、その子プロセスと、
  **その変換のために起動した WINWORD だけ**を止め、docx を `error/` へ移して次のファイルに進む。打ち切ったときは、子が
  どこまで進んだか (`Opening:` で止まった / `Exporting as PDF...` で止まった) がログに出る。変換用のスクリプトを毎回書き出す
  のは、Drive 上のファイルが差し替えられても、子が実行中の watcher と必ず同じ版になるようにするため。
  - **止める WINWORD の特定**: COM が起動する WINWORD は watcher の子プロセスにならないので、親子関係では辿れない。子が
    Word を起動する**直前と直後**に WINWORD の一覧を取り、増えたものがちょうど 1 つで**窓が無い**ときだけ、その PID と起動時刻を
    記録する (同じ瞬間に利用者が起動した Word には窓があるので、取り違えない)。
    打ち切るときは、その PID が今も WINWORD で起動時刻も一致するときだけ止める (PID の再利用で別のプロセスを止めないため)。
    記録が無い (Word の起動中に固まった) ときは、子の起動後に現れた WINWORD がちょうど 1 つで**窓が無い**ときだけ止める。
    **どちらにも当たらなければ止めない** (ログに WARN を出す)。利用者が開いている Word は窓があり、変換より前から
    動いているので対象にならない。「窓の無い WINWORD をすべて止める」方式は、別のアプリが COM で使っている Word まで
    巻き込むので採らない。
  - 正常に終わったのに、記録した Word が 15 秒たっても残っている (`Quit` が効かなかった) ときも、同じ条件で止める。
  - 子が Word を起動したときに新しい WINWORD が現れなかった (既に動いていた Word に繋がった) ときは、**その Word に何もせずに
    止まる** — 窓を隠す・警告を切る・文書を開く・`Quit` する、のどれもしない (利用者が作業中の文書を持っているかもしれないため)。
    ログに `ATTACHED:` を WARN で出し、docx は `error/` へ移さずに監視フォルダへ残して、次の周回でもう一度試す。
    繰り返し起きるなら、その PC で開いている Word を閉じる。
- **2 段階で開く**: まず普通に開き、**失敗したときだけ OpenAndRepair** で開き直す。修復が要った docx は、PDF を作った
  うえで `REPAIRED:` を WARN でログに出す — 「生成した docx が Word の修復なしで開けるか」は、手で組んだ OOXML
  (テキストボックス・SVG の埋め込み・差分ハイライト) が健全かを知る手がかりになるので、無条件に修復して隠さない。
- **書き出し**: `ExportAsFixedFormat` (**OptimizeFor = Print** = 「標準 (オンライン発行および印刷)」) で PDF を書く。失敗した
  ときだけ `SaveAs2(…, 17)` (Word の既定の画質) に退避する — PDF が出ないよりはよいため。`BitmapMissingFonts` は既定の
  True のまま (False にすると書体が置き換わりうる)。
- **変換している間に docx が差し替わったら、その PDF は返さない**: 作業フォルダへ写した時点と、PDF ができた時点で元の docx の
  大きさと更新時刻を比べ、違っていれば (同じ名前の新しい版が届いた) 古い版の PDF を捨てて `CHANGED:` を WARN で出し、
  docx は動かさずに次の周回で変換し直す。古い版の PDF を新しい版のものとして返さないため。**ただし Google Drive では、
  同じ名前の上書きが Windows に届くのは変換の後になりやすく、この判定には掛からない** (実機で、変換中を狙った上書きが
  2 回とも docx を `processed/` へ移した後に届いた。上書きの到着は push から 16 秒以上遅れ、新しく作った docx の到着より遅い)。
  そのため `roundtrip.sh` が、同じ名前の docx が送出先に残っている間は push しない (§5.3・§7)。
- 変換できた docx は `processed/` へ、できなかった docx は `error/` へ移す (同名があれば時刻を付ける)。**1 ファイルの処理で
  何が起きても watcher は止まらない** — 変換の失敗も、docx を移す処理の失敗も、想定外の例外も、そのファイルについて
  ログに出して次へ進む。watcher が止まるのは Ctrl+C か窓を閉じたときだけ。
- **所要時間**: 1 本あたり 13〜28 秒 (Word 16.0 Build 16.0.20527 で BHI の動作例の docx を変換したときの値)。毎回
  PowerShell と Word を起動し、Word の終了を待ってから PDF を置くためで、時間で打ち切れることの代償である。
- **生存記録** `.watcher-alive`: 起動直後と、以後は **60 秒に 1 回まで**書く (毎周回書くと Drive の同期が忙しくなるため)。
  **変換を待っている間も書く**ので、長い変換で「停止」と誤って判定されない。1 行目が時刻、2 行目以降が次の 3 つ:

  | キー | 中身 |
  |------|------|
  | `script_md5=` | 起動時に読んだ `.ps1` の MD5 (Linux 側がローカルの `.ps1` と照合し、起動し直し忘れを見つける) |
  | `convert_timeout_sec=` | 1 ファイルあたりの変換タイムアウト (秒) |
  | `nondefault=` | 既定と違う起動引数 (通常は `none`。§5.2) |

  Linux 側の `check-pdf-path.sh` と `roundtrip.sh` がこれを読んで、稼働・版・設定を判断する (読み方は
  `scripts/lib/watcher-alive.sh`)。
- **ログ** `watch-and-convert.log`: 窓に出す行と同じものを監視フォルダに追記する。Drive で同期されるので、Linux 側から
  watcher の診断を読める。書き込みに失敗しても変換は止めない。
- **画像の圧縮の診断**: 変換のたびに Word の版と、画像・圧縮に関係しそうな `Options.*` の値を**読んで**ログに出す
  (書き換えはしない)。docx の中の PNG より低い解像度で PDF に載ることがある (600 dpi の PNG が 200 ppi で載った例がある)
  ため、効きそうな設定を Linux 側から確かめられるようにしている。docx に `<w:doNotAutoCompressPictures/>` を入れても
  この圧縮は止まらない。

### 5.2 試験用の起動引数 (watcher)

打ち切りの動作を確かめるときは、**Drive 上のファイルを書き換えずに**起動引数で設定を変える。`.bat` は引数を渡さないので、
窓を閉じて `.bat` で起動し直せば既定に戻る (書き換えた版を Drive に戻し忘れる余地が無い)。**先に通常の watcher の窓を必ず
閉じること** — 閉じ忘れると 2 つの watcher が同じ docx を拾い、通常の側が先に変換を終えて試験にならないことがある (§7)。

```powershell
# 送出先フォルダで PowerShell を開いて
powershell -NoProfile -ExecutionPolicy Bypass -File .\watch-and-convert.ps1 -ConvertTimeoutSec 30 -SimulateHang
```

| 引数 | 既定 | 意味 |
|------|------|------|
| `-ConvertTimeoutSec <秒>` | 120 | 1 ファイルあたりの変換タイムアウト (Word の起動・docx を開く・PDF の書き出しの合計)。1〜86400 |
| `-SimulateHang` | 無し | **試験用**。子が docx を開いたあと眠り、**必ず**打ち切りに至る (Word がダイアログ待ちで固まった状態の再現) |

起動引数を渡したときは (既定と同じ値でも) 起動バナーに WARN が出て、生存記録の `nondefault=` に残る。`check-pdf-path.sh` と
`roundtrip.sh` は、これが `none` でなければ警告する (試験用の起動のまま放置すると、以後の変換がすべて打ち切られて `error/`
へ行くため)。`-ConvertTimeoutSec` を数秒にするだけだと Word の起動中に打ち切られることが多く、「記録が無いときの特定」
(§5.1 の「止める WINWORD の特定」の後半) しか通らない。記録した PID で止める本来の経路は `-SimulateHang` で確かめる。

### 5.3 roundtrip.sh (Linux)

- **多重に起動しない**: `data/products/.roundtrip.lock` を flock で取る (`--dry-run` を除く)。flock が無い環境では警告して続ける。
- **待つ前に watcher の生存を確かめる**: 送出先に `watch-and-convert.ps1` が無い、`.watcher-alive` が無い、または 300 秒
  (環境変数 `STALE_SEC`) より古いときは警告する。生存記録の版がローカルの `.ps1` と違う・既定と違う起動引数で動いている・
  版と設定が書かれていない、のときも警告する。どれも中止はしない (止まったまま待つと、タイムアウトまで何も出ないため)。
- `--timeout` / `--poll` は正の整数だけを受け付ける (0・負数・小数・値の欠落は使い方の誤りとして止める)。
- **前回の PDF を退避できなければ中止する**: 前回の PDF が残っていると、それを今回の成果物として持ち帰ってしまう。送出先の一覧が取れない・`__archives` フォルダへ移せない・移した後も残っている、
  のどれでも中止する。
- **送出先に同じ名前の docx が残っていれば push しない**: 前回の分が変換を待っているか変換中なので、中止して、前回の PDF が
  返ってから再実行するよう案内する (一覧が取れないときも中止する)。同じ名前で上書きすると、新しい版が変換されないまま
  `processed/` に入り、古い版の PDF を今回の成果物として持ち帰りうるため (§5.1)。打ち切りや Ctrl+C の後にすぐ再実行したときに当たる。
- **push より前に書かれた PDF は取り込まない**: 待つ段は、ファイル名が一致し、更新時刻が push を始めた時刻より後のもの
  (時計のずれを 120 秒まで許す。環境変数 `PDF_MTIME_SLACK_SEC`) だけを今回の成果物とする。古いものは警告を 1 回出して待ち続ける。
  `--skip-push` で再開したときは push の時刻が無いので、名前の一致だけで判断する。
- rclone の呼び出しはすべて**タイムアウト + 再試行** (既定 3 回・5 秒間隔。環境変数 `RCLONE_MAX_RETRIES` /
  `RCLONE_RETRY_SLEEP`)。
- **提出パッケージの段 5** (§4): 送る前に止める条件を、集約と push より前に確かめる (送ってから止まると、送出先に中途半端な
  docx が残るため)。`submission-<id>/` は `rclone sync` で中身を手元の写しと一致させ、消える・置き換わるファイルは削除せずに
  `__archives/submission-<id>_<時刻>/` へ退避する。置いたあとで `rclone check` で手元の写しと照合する。
- 進捗ログは標準エラーに出す (標準出力は最後の `docx:` / `PDF :` の 2 行と、提出パッケージを届けたときの `提出:` の行だけ)。

---

## 6. PDF の確かめ方

roundtrip で得た PDF は、体裁の計測 (用紙・余白・行番号) だけでは**図の中身の崩れ**に気づけない。次の 3 つを見る。図を
見るのは**図を埋め込んだ草稿の PDF** (`main.pdf` など) である。`package.sh --mode final` で組み替えた提出 docx は図を別の
ファイルへ分けるので、その PDF には図が無い (画像オブジェクトが 0 個でも「図が無いから 0」であって、判定にならない)。

1. **図がベクターで載っているか** — Word は SVG を解釈できないと、警告なしに PNG フォールバックで描く。docx を目で見ても
   区別できないが、PDF にすると差が構造として残る (ベクターで描いた図はパスの描画命令になり、PNG は画像オブジェクトになる)。
   PDF の画像オブジェクトを数えて判定する:
   ```bash
   uv run --with pypdf python main/step04_pdf/inspect_pdf_figures.py \
       data/products/main.pdf --expected-raster 0
   ```
   `--expected-raster` は原稿の図のうち**元からラスタ (PNG / JPEG など) の枚数**。動作例 `data/dummy/` は図がすべて SVG なので
   `0`、`data/dummy/regression/` は `2`。画像の数がこれを超えたら PNG フォールバックの疑いがある (雑誌のテンプレートによっては
   ヘッダのロゴなども画像として数えられるので、内訳も見る)。`[NG]` のときは (a) docx に `asvg:svgBlip` があるか
   (`unzip -p <docx> word/document.xml | grep -c asvg:svgBlip`) と、(b) 変換した Word の世代 (ベクター表示は **Microsoft 365 /
   Office 2019 以降**。買い切り版 Office 2016 は必ず PNG になる) を確かめる。
2. **図を拡大して目で見る** — 400% 程度まで拡大し、文字が図形と重なっていないか、パネルが誤った範囲で切り取られていないかを
   見る。1 つの SVG に複数のグラフの出力を連結した図で、Word が文字を誤った座標に描くことがある (ブラウザでも PNG でも正常に
   見えるので、ここでしか見つからない。書き方の注意は [`CLAUDE.md`](../CLAUDE.md) の「原稿執筆の規約」の図の項)。
3. **体裁** — 用紙・余白・行送り・行番号・ページ番号・節の順。BHI の提出 docx で見る点は
   [`docs/usage-guide.md`](usage-guide.md) §8.4 の最後、こう出れば正常という値は [`docs/journal-bhi.md`](journal-bhi.md) §12 と
   [`docs/bhi-submission-checklist.md`](bhi-submission-checklist.md)。

確かめた結果は、変換に使った **Word のバージョン** (「ファイル → アカウント」) とともに記録すること。とくに 1. は Word の
世代で結果が変わる。

---

## 7. 既知の制限

- **普通に開いた時点で Word がダイアログを出して固まる docx は、修復を試す前に打ち切られて `error/` へ行く** (2 段階の
  2 段目に進めないため)。`DisplayAlerts = 0` の下では、開けない docx は通常は例外になって 2 段目に進むが、そうならない
  壊れ方がありうる。`error/` に入った docx は Word で直接開いて確かめる。
- **止める WINWORD を特定できないときは止めない。** Word の起動中に固まり、しかも同じ時間に別の Word も起動した、といった
  場合に起きる。ログに `Cannot tell which WINWORD …` が出たら、タスクマネージャで**ウィンドウの無い** `WINWORD.EXE` を終了する
  (残っていても次の変換は新しい Word で行われる)。
- **複数の docx は 1 本ずつ順に変換する。** 1 本あたり最大 120 秒 (+ 後片付け) かかりうるので、固まる docx が続くと合計が
  `roundtrip.sh` の `--timeout` (既定 10 分) を超えうる。**1 ファイルの打ち切り (120 秒) は全体の打ち切り (10 分) より短い**
  ので、通常は 1 本が固まっても残りは間に合う。超えたら `--skip-push` で待ちを再開するか、`--timeout` を延ばす。
- **同じフォルダを 2 つの watcher が監視すると、同じ docx を二重に変換する**。遅れた側は docx を移す時点で
  `Source already gone` を出して続けるので害は無いが、変換は無駄になり、ログも 2 つの watcher の行が交互に並んで読みにくくなる。
  watcher はフォルダごとに 1 つだけ動かす (別の PC で動かしたままのものにも注意)。2 つ目の起動を拒む仕組みは無い。
- docx を `processed/` へ移せなかったとき (変換の直後に同期クライアントが掴んでいたなど) は、docx が直下に残るので次の周回で
  もう一度変換される (PDF が上書きされるだけで害は無い)。
- **変換の後に届いた同じ名前の上書きは変換されない。** Google Drive は同じ名前の上書きを同じファイルの更新として扱うので、
  watcher が docx を `processed/` へ移した後に更新が届くと、新しい版は `processed/` の中のファイルに付き、送出先には古い版の
  PDF だけが残る (変換中に届けば `CHANGED:` で捨てて変換し直す)。`roundtrip.sh` は同じ名前の docx が送出先に残っている間は
  push しないが、**Drive に手で docx を置くときはこの確かめが無い**ので、前回の PDF が返ってから置く。また、docx が送出先から
  消えてから前回の PDF が届くまでの間 (同期の順序によってはありうる) に再実行すると、その PDF を今回の成果物として取り込みうる
  (更新時刻の確かめは時計のずれを 120 秒まで許すため)。PDF が返ったのを確かめてから再実行する。
- Word の COM 自動化で**アプリのオプションを設定する・修復した docx を docx として保存し直す**と、Word が再現性をもって
  固まる。watcher はオプションを読むだけで、`SaveAs2` は PDF への書き出しの退避経路としてだけ使う。この 2 つを足さないこと
  (固まっても打ち切られるが、毎回打ち切られるなら変換できない)。
- Windows が無い環境では PDF を作れない (docx までは Linux で完結する)。その場合は docx を共有し、Word を使える端末で変換する。

---

## 8. トラブルシュート

| 症状 | 原因と対処 |
|------|-----------|
| Linux: `rclone リモート '...' に接続できません` | `rclone config reconnect gdrive:` を実行する。送出先の環境変数 (`RCLONE_REMOTE` / `GDRIVE_BASE_PATH` / `GDRIVE_SUBDIR`) も確かめる |
| Linux: `生存記録 .watcher-alive がありません` | watcher が起動していない (メッセージは、生存記録を書かない別の版の watcher が動いている場合も挙げる)。`push-win-tools.sh` → watcher を起動する |
| Linux: `watcher の生存記録が N 秒前で止まっています` | watcher の窓が閉じられたか、PC がスリープした。変換を待つ間も生存記録は書かれるので、変換が長いだけでは古くならない。Drive の同期の遅れでも古く見えることがある |
| Linux: `生存記録に watcher の版と設定がありません` | 版と設定を書かない (変換タイムアウトを持たない) 別の版の watcher が動いている。`push-win-tools.sh` → watcher の窓を閉じて `.bat` で起動し直す |
| Linux: `実行中の watcher はローカルの watch-and-convert.ps1 と別の版です` | `push-win-tools.sh` の後に watcher を起動し直していない (実行中の watcher はスクリプトをメモリに持つ)。ローカルを編集して送っていないときも出る |
| Linux: `watcher が既定と違う起動引数で動いています` | 試験用の起動 (`-SimulateHang` など) のまま。窓を閉じて `.bat` で起動し直す (`-SimulateHang` のままだと全件が打ち切られる) |
| Windows: 窓に `Watcher stopped.` が出て止まっている | Ctrl+C で止めたか、PowerShell そのものが終了した。`watch-and-convert.bat` を起動し直す (1 ファイルの処理の失敗では止まらない) |
| Windows: `TIMEOUT: not finished within 120s` → docx が `error/` へ | Word が固まった (ダイアログ待ちなど)。直後の行に子がどこまで進んだかが出る。docx を Word で直接開いて状態を確かめる。単に大きい docx なら `-ConvertTimeoutSec` を延ばして起動する |
| Windows: `Cannot tell which WINWORD this conversion started` | 止める Word を特定できなかったので止めていない (§7)。ウィンドウの無い `WINWORD.EXE` が残っていればタスクマネージャで終了する |
| Windows: `REPAIRED: plain open failed and OpenAndRepair was needed` | PDF はできている。生成した docx に、Word が修復を要する綻びがある。手で組む OOXML (テキストボックス・SVG の埋め込み・差分ハイライト) に関わる変更をした直後なら、そこを疑う |
| Windows: `Could not write X.pdf to the watch folder (open in a PDF viewer?)` | 前回の同名の PDF を Windows のビューアで開いたまま。閉じてから docx を送出先の直下へ戻す (または roundtrip を回し直す) |
| Windows: `Could not remove the work folder` | 作業フォルダ (`%TEMP%\docx2pdf_*`) を消せなかった。次の起動時に 1 時間より古いものは自動で掃除される |
| Linux: `タイムアウト: PDF が N 件そろいませんでした` | `bash scripts/check-pdf-path.sh` で切り分ける。watcher の窓・`watch-and-convert.log`・`error/` を見る。変換が遅いだけなら `bash scripts/roundtrip.sh --skip-push` で待ちを再開する |
| Linux: `旧 PDF の退避に失敗しました` / `退避後も X.pdf が送出先に残っています` | 前回の PDF を今回の成果物として持ち帰らないための中止。Drive 上でその PDF を `__archives` フォルダへ移すか消してから、もう一度回す |
| Linux: `別の roundtrip が実行中です` | 多重起動の防止 (flock)。`pgrep -af roundtrip` で確かめ、要らないプロセスを終了する |
| Linux: `送出先のツールがローカルと一致しません` (`check-pdf-path.sh` の [3/5]) | Drive 上の watcher が古い。`bash scripts/push-win-tools.sh` で送り直し、**watcher を起動し直す** |
| Windows: `Locked (sync in progress?)` が続く | Google Drive の同期が終わっていない。次の周回で自動的にもう一度試すので待つ |
| Windows: `OPEN_ERROR` / `EXPORT_ERROR` / `WORD_ERROR` → docx が `error/` へ | 直前の行 (子のログ) の例外メッセージを見る。`WORD_ERROR` は Word の起動そのものの失敗が多い。Word を手で起動して状態 (ライセンス・更新・ダイアログ) を確かめる。直したら docx を送出先の直下へ戻す |
| Windows: `ExportAsFixedFormat failed` → `Falling back to SaveAs2` | PDF は Word の既定の画質で出ている。図の解像度が下がっていないか、§6 で確かめる |
| Windows: 起動直後に `式またはステートメントのトークン '...' を使用できません` などの解析エラー | **`.ps1` の UTF-8 BOM が落ちている**可能性が高い。§3.1 で BOM を確かめて付け直し、送り直す |
| PDF の図が粗い・拡大するとぼやける | SVG が PNG フォールバックに落ちたか、Word が画像を圧縮した。§6 の 1. で切り分ける |
