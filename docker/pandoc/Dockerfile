# docx-paper-template — pandoc 主変換コンテナ
# 役割: md→docx / 全領域 AST 差分 / OOXML 後処理 (SVG 埋込・textbox)
# 設計: docs/architecture.md §1.2.1。pandiff は採用しない (§2.3)。作図は mermaid コンテナが担うため nodejs は入れない。
FROM ubuntu:24.04

# --- 再現性のためのバージョン固定 (ARG) ---
# 注意: PANDOC_VERSION と CROSSREF_VERSION は結合している。
#   pandoc-crossref は pandoc 本体と同じ pandoc-types でビルドされた版でないと実行時に
#   弾かれるため、片方だけ更新してはならない。両者は対応する組で同時に更新すること
#   (現行の組: pandoc 3.6.4 ↔ pandoc-crossref 0.3.19 = pandoc-types 1.23.1)。
ARG PANDOC_VERSION=3.6.4
ARG CROSSREF_VERSION=0.3.19
# pip パッケージも版固定 (panflute=構造保持 AST 差分用 / lxml=OOXML 直接操作用)
ARG PANFLUTE_VERSION=2.3.1
ARG LXML_VERSION=5.3.0

# パッケージインストール中の対話プロンプトを抑止
ENV DEBIAN_FRONTEND=noninteractive

# --- システムパッケージ (apt は distro 固定 / 部分的再現性) ---
RUN apt-get update && apt-get install -y --no-install-recommends \
    wget \
    ca-certificates \
    xz-utils \
    # 和文フォント
    fonts-noto-cjk \
    fonts-ipafont-mincho \
    fonts-ipafont-gothic \
    fontconfig \
    # SVG → PNG フォールバック (rsvg-convert)
    librsvg2-bin \
    # PDF 図 → SVG 変換
    pdf2svg \
    # git revision の取り出し (diff.sh HEAD~1) / safe.directory
    git \
    # Python (OOXML 後処理・構造保持 AST 差分)
    python3 \
    python3-pip \
    # LibreOffice。用途は 2 つ:
    #   (1) 生成 docx の読み込み検査 — Word と独立した OOXML 実装なので、パッケージ構造・
    #       関係定義・種類宣言が壊れていれば読み込みに失敗する (関係定義の壊れた docx は
    #       実際に拒否された)。Word 実機が無い環境での代替検査に使う
    #   (2) 雑誌提供 .doc テンプレ → .docx 変換
    # PDF 化には使わない (roundtrip のみ。docs/architecture.md §0 / §2.4)。本パッケージでイメージが約 2 倍になる
    libreoffice-writer \
    # Impress は **生成 pptx の読み込み検査**のためだけに入れる。writer だけの状態では
    # pptx フィルタ (simpress) が無く、**pandoc 純正の reference.pptx すら
    # "source file could not be loaded" で拒否される** = 我々の生成物が壊れているのか
    # フィルタが無いだけなのか区別できない (実測)。libreoffice-core が既に入っているため
    # 追加は 28.4MB と小さい (実測)。**pptx→pdf の変換品質には依存しない** — 見るのは
    # 「独立した OOXML 実装が読み込めるか」だけで、体裁の再現には使わない (roundtrip 方針は不変)。
    libreoffice-impress \
    && rm -rf /var/lib/apt/lists/*

# フォントキャッシュ更新
RUN fc-cache -fv

# --- Pandoc を GitHub release の .deb で導入 (版固定) ---
RUN wget -q "https://github.com/jgm/pandoc/releases/download/${PANDOC_VERSION}/pandoc-${PANDOC_VERSION}-1-amd64.deb" \
    -O /tmp/pandoc.deb \
    && dpkg -i /tmp/pandoc.deb \
    && rm /tmp/pandoc.deb

# --- pandoc-crossref を GitHub release で導入 (pandoc 3.6.4 互換版に固定) ---
# tar には man ページ等も含まれるため、バイナリ pandoc-crossref のみを取り出す。
RUN wget -q "https://github.com/lierdakil/pandoc-crossref/releases/download/v${CROSSREF_VERSION}/pandoc-crossref-Linux-X64.tar.xz" \
    -O /tmp/pandoc-crossref.tar.xz \
    && tar -xf /tmp/pandoc-crossref.tar.xz -C /usr/local/bin/ pandoc-crossref \
    && chmod +x /usr/local/bin/pandoc-crossref \
    && rm /tmp/pandoc-crossref.tar.xz

# --- Python パッケージを版固定で導入 ---
# Ubuntu 24.04 は PEP 668 (externally-managed) のため --break-system-packages を付ける
# (コンテナ専用環境なので system へ直接入れてよい)。
RUN python3 -m pip install --no-cache-dir --break-system-packages \
    "panflute==${PANFLUTE_VERSION}" \
    "lxml==${LXML_VERSION}"

# /workspace を git の safe.directory に登録 (diff.sh の git 操作用)
RUN git config --system --add safe.directory /workspace

WORKDIR /workspace

CMD ["pandoc", "--version"]
