# docx-paper-template — Mermaid 作図コンテナ
# 役割: src/figs/mermaid/*.mmd → svg/pdf (headless Chromium 経由)
# 設計: docs/architecture.md §1.2.2。
FROM node:20.18-slim

# mermaid-cli は版固定する (docs/architecture.md §1.2.2)
ARG MERMAID_CLI_VERSION=11.4.2

# Puppeteer (headless Chromium) と和文フォント
# 注意: chromium は base (debian) の配布版を使うため版は浮動する
#   (= 部分的再現性)。chromium 同梱により本イメージは約 1.5GB と大きい。版更新時は
#   mermaid-cli (puppeteer) と chromium の整合をダミー .mmd 変換で確認すること。
RUN apt-get update && apt-get install -y --no-install-recommends \
    chromium \
    fonts-ipafont-gothic \
    fonts-ipafont-mincho \
    fonts-noto-cjk \
    fonts-freefont-ttf \
    fontconfig \
    && rm -rf /var/lib/apt/lists/*

# フォントキャッシュ更新 (CJK ラベルを正しく描画するため)
RUN fc-cache -fv

# Puppeteer は同梱 Chromium を落とさず、システムの chromium を使う
ENV PUPPETEER_SKIP_CHROMIUM_DOWNLOAD=true
ENV PUPPETEER_EXECUTABLE_PATH=/usr/bin/chromium

# mermaid-cli (mmdc) を版固定で導入
RUN npm install -g "@mermaid-js/mermaid-cli@${MERMAID_CLI_VERSION}"

# mermaid テーマ設定 (fontSize / fontFamily / flowchart) をイメージに同梱し、
# convert.sh から -c で参照する (config.json を実際に効かせる)
# convert.sh はリポジトリの config.json を実行時に同じパスへ被せる (再ビルドなしで設定が効く)。
# ここでの複製は、convert.sh を経ずにイメージを直接使う場合の既定値として残している。
COPY config.json /etc/mermaid/config.json

WORKDIR /workspace

CMD ["mmdc", "--version"]
