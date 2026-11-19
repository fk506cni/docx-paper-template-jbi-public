#!/usr/bin/env python3
"""test_caption_matches.py — postprocess._caption_matches の単体テスト。

図キャプション照合 (postprocess._caption_matches) は、原稿と docx の図の取り違えを止める
安全網である。判定は「引用・相互参照を境に分割し、残った断片が順に現れるか」で、
キャプション中の引用が docx 側で番号に置換されていても一致する。この判定が意図どおり働くこと、
および安全網として機能する (取り違えを False にする) ことを固定するための最小テスト。

pytest は導入していないので素の assert で書く。コンテナ内で実行する:
  docker compose -f docker/docker-compose.yml run --rm -u "$(id -u):$(id -g)" pandoc \
      python3 main/step02_build/test_caption_matches.py
全件通れば exit 0、1 件でも外れれば exit 1。
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from postprocess import _caption_matches  # noqa: E402

# (説明, caption, descr, 期待値)
CASES = [
    # 引用がキャプションにあり、docx 側では番号に置換されていても一致する (この判定の核心)
    ("引用付きキャプションが番号置換後の descr と一致",
     "Overview of the pipeline [@fig:x]",
     "Figure 1: Overview of the pipeline 3)",
     True),
    # 引用を除いた断片が順に現れれば一致
    ("複数断片が順に現れれば一致",
     "Study flow [@a] and outcomes [@b]",
     "Figure 2: Study flow 1) and outcomes 2)",
     True),
    # 断片が 1 つも残らない (引用だけのキャプション) は True (位置合わせに委ねる。文書化済みの挙動)
    ("引用だけのキャプションは True",
     "[@mitchell2009]",
     "Figure 3: 4)",
     True),
    # 全く違う本文は False = 安全網が生きている
    ("無関係な descr は False",
     "Overview of the analysis pipeline",
     "Figure 4: A completely unrelated caption",
     False),
    # 断片の出現順が違えば False (順序一致を要求している)
    ("断片が逆順なら False",
     "alpha [@x] beta",
     "Figure 5: beta then alpha",
     False),
    # 空キャプションは True (照合材料なし)
    ("空キャプションは True",
     "",
     "Figure 6: anything",
     True),
]


def main():
    ng = 0
    for desc, caption, descr, want in CASES:
        got = _caption_matches(caption, descr)
        mark = "OK" if got == want else "NG"
        if got != want:
            ng += 1
        print(f"  {mark}: {desc} (期待={want} 実際={got})")
    print("")
    if ng:
        print(f"== NG {ng} 件 / 全 {len(CASES)} 件 ==")
        return 1
    print(f"== 全 {len(CASES)} 件が期待どおり ==")
    return 0


if __name__ == "__main__":
    sys.exit(main())
