#!/bin/bash
# make-reference.sh — _default の reference.docx 生成 (汎用版への薄いラッパー)。
#
# 体裁値 (double / continuous / Times New Roman / 12 / 25mm / a4) はここに持たない。
# 汎用版 data/journals/make-reference.sh が _default/profile.yaml から体裁値を読んで生成するので、
# ここにも値を書いて二重管理すると、将来 _default/profile.yaml だけを変えたときに生成物が食い違う
# (値ドリフト)。そのため本スクリプトは体裁値の重複を持たず、汎用版へ委譲する薄いラッパーである。
# 出力は data/journals/_default/reference.docx (汎用版が id 既定 _default で同じ場所へ書く)。
#
# 使い方:  bash data/journals/_default/make-reference.sh
#          (= bash data/journals/make-reference.sh _default と等価)
# 出力:    data/journals/_default/reference.docx
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec bash "$SCRIPT_DIR/../make-reference.sh" _default
