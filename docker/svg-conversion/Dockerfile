# docx-paper-template — 最終提出図 svg → pdf 変換コンテナ
# 役割: Inkscape + Ghostscript で text-to-path (フォントをアウトライン化) した PDF を作る。
#       アウトライン化は字形を図形に変換するため、フォント不在環境でも崩れない (選択・検索は不可)。
# 設計: docs/architecture.md §1.2.3。
# build context はリポジトリルート (fonts/ を同梱するため。convert.sh が -f で本ファイルを指定)。
FROM alpine:3.21

# inkscape は 1.x 系 CLI (--export-type / --export-text-to-path) を前提とする
RUN apk add --no-cache \
    inkscape \
    ghostscript \
    fontconfig \
    cabextract \
    bash \
    wget \
    font-noto-cjk \
    font-ipa

# --- Microsoft Core Fonts (Arial / Times New Roman 等) ---
# 方針: 取得物の再現性を保ち、フォントの無言の欠落を許さない。
#   取得元: SourceForge corefonts プロジェクト (sourceforge.net/projects/corefonts/)。
#   版: corefonts 最終リリース (2002 年公開以降凍結)。取得日 2026-06-08 の SHA256 を
#       docker/svg-conversion/mscorefonts.sha256 に固定し、ビルド時に `sha256sum -c` で検証する。
#       (注: alpine の busybox sha256sum は # コメント行を解釈できないため、当該ファイルは
#        チェックサム行のみとし、来歴コメントはこの Dockerfile 側に置く)
#   既定 (FETCH_MSCOREFONTS=true): ビルド時取得 + チェックサム検証 + 必須フォント欠落時はビルド失敗。
#   オフライン/完全再現重視時: 取得済み .ttf を fonts/ へ vendoring し、
#       `--build-arg FETCH_MSCOREFONTS=false` で取得をスキップする (convert.sh は環境変数で渡せる)。
ARG FETCH_MSCOREFONTS=true
COPY docker/svg-conversion/mscorefonts.sha256 /tmp/mscorefonts.sha256
RUN set -e; \
    if [ "$FETCH_MSCOREFONTS" = "true" ]; then \
        mkdir -p /usr/share/fonts/truetype/msttcorefonts; \
        cd /tmp; \
        for f in andale32 arial32 arialb32 comic32 courie32 georgi32 \
                 impact32 times32 trebuc32 verdan32 webdin32; do \
            wget -q --tries=3 --timeout=30 \
                "https://downloads.sourceforge.net/corefonts/${f}.exe" -O "${f}.exe"; \
        done; \
        sha256sum -c /tmp/mscorefonts.sha256; \
        for f in *.exe; do cabextract -q "$f"; done; \
        cp /tmp/*.ttf /tmp/*.TTF /usr/share/fonts/truetype/msttcorefonts/ 2>/dev/null || true; \
        fc-cache -f; \
        rm -f /tmp/*.exe /tmp/*.ttf /tmp/*.TTF /tmp/*.inf /tmp/*.cat; \
    else \
        echo "FETCH_MSCOREFONTS=false: MS Core Fonts のネットワーク取得をスキップ (fonts/ の vendoring に委ねる)"; \
    fi

# --- 専有フォント (Calibri / Yu Gothic 等) ---
# プロジェクトルート直下の fonts/ (gitignored) に置かれたユーザー所有フォントを同梱する。
# 未配置 (fonts/.gitkeep のみ) でもビルドは成功し、専有フォントは代替フォントに化ける (docs/architecture.md §5)。
COPY fonts/ /usr/share/fonts/truetype/proprietary/
RUN fc-cache -fv

# --- フォント導入状況の確認 ---
# MS Core Fonts は「無言で欠落」させない。
#   FETCH_MSCOREFONTS=true なのに Arial/Times が検出できなければビルドを失敗させる
#   (取得・展開の失敗を握り潰さない)。専有フォント (Calibri 等) の不在は警告のみ。
RUN echo "=== Microsoft Core Fonts ===" && \
    if fc-list | grep -iqE "arial|times new roman"; then \
        fc-list | grep -iE "arial|times|courier|verdana|georgia"; \
    elif [ "$FETCH_MSCOREFONTS" = "true" ]; then \
        echo "  ERROR: MS Core Fonts (Arial/Times) が未検出。取得・展開に失敗した可能性がある。ビルドを中止する。" >&2; \
        exit 1; \
    else \
        echo "  WARNING: FETCH_MSCOREFONTS=false かつ Arial/Times 未検出。fonts/ への vendoring が必要 (最終図のフォントが代替に化ける)。"; \
    fi && \
    echo "=== Japanese Fonts ===" && \
    (fc-list | grep -iE "noto|ipa" || echo "  (和文フォント未検出)") && \
    echo "=== Proprietary Fonts (fonts/) ===" && \
    if fc-list | grep -iqE "calibri|yu ?gothic"; then \
        fc-list | grep -iE "calibri|yu ?gothic"; \
    else \
        echo "  WARNING: 専有フォント (Calibri/Yu Gothic 等) 未検出。"; \
        echo "  fonts/ に配置すると原典フォントを保持できます (未配置時は代替フォントで描画)。"; \
    fi

WORKDIR /workspace

CMD ["bash"]
