<!--
data/dummy/bhi-csl/main.md — bhi.csl 受入フィクスチャ

目的: BioHealth Informatics の引用様式 (docs/journal-bhi.md §3) を実機で検証する。
  - 文献リストの文字列が規定の公式例 5 件 (expected.txt) と一致するか
  - 本文中の引用が `1)` ごと上付きになるか (docx の w:vertAlign を実測)
  - 表の中・図凡例の中の引用も同じ書式で出るか
  - 著者 4 名以上で et al が発火するか / 3 名までは全員列挙されるか
  - 複数引用・連続引用の実出力 (規定に記述が無いため「記録」が達成条件)

【重要】文献番号は初出順に振られる。expected.txt と番号を合わせるため、
以下の "文献の初出" 6 箇所の順序 (mulford → nakajima → mitchell → watanabe → doe → yokanEtAl)
を変えないこと。複数引用の検証はすべてその後ろに置く。

使い方:
  bash scripts/check-csl.sh                                     # 文献リストの文字列突合
  bash scripts/build.sh --input data/dummy/bhi-csl --journal bhi --article-type original

注記: 原稿側の字面は TJD/THS のパロディだが、**公式例 5 件 (expected.txt の
  1〜5 行目) は規定からの逐語転記で、架空の字面にはしていない**。パロディは (f)〜(i) の 4 件だけで、
  構造 (著者 4 名 / 巻・号・ページ / DOI) は検証に必要な形にしてある。

注記: figs/fig-overview.svg は data/dummy/figs/fig-overview.svg の複製である
  (図凡例内の引用を検証するためだけの図で、図の中身に意味は無い)。実体が 2 か所に重複するので、
  元図を更新してもこちらへは波及しない点に注意する。
-->

::: {custom-style="Title"}
Citation Style Fixture for BioHealth Informatics
:::

::: {custom-style="Author"}
Test Fixture^1^

Correspondence: fixture@example.org
:::

::: {custom-style="Affiliation"}
^1^Graduate School of Hunch Engineering, University of the Tremendous, Tremendo, Hunchshire, Fictionia
:::

::: {custom-style="Abstract"}
**Objective:** This fixture exercises the BHI reference style; it is not a manuscript.

**Methods:** Each of the five official reference examples is cited once, in the order the
examples appear in the instructions to authors.

**Results:** The rendered reference list is compared character by character with the
official examples.

**Conclusion:** Deviations, if any, are recorded in `docs/journal-bhi.md`.
:::

::: {custom-style="Keywords"}
**Keywords:** citation style; Vancouver; reference management
:::

# Introduction

Each reference is cited once here, in the order of the official examples, so that the
citation numbers match `expected.txt`.

A journal article with two authors is the first example [@mulford1994]. A paper written in
Japanese is the second [@nakajima1994]. A paper cited only by its DOI is the third
[@mitchell2009]. A book with an edition statement is the fourth [@watanabe1990]. An online
material with a URL and an access date is the fifth [@doe1999]. A paper with four authors
triggers the "et al" rule [@yokanEtAl2099].

Three reference types that are absent from the official examples are cited last so their
numbers stay after the first six (regression guard): a book chapter with page
numbers [@chapter2099], a conference paper with page numbers [@conf2100], and a dataset cited
by DOI [@dataset2101]. The rendered list must keep their inclusive page numbers and DOI.

# Methods

Multiple citations in one bracket are rendered here so that the actual output string can be
recorded: two non-adjacent references [@mulford1994; @watanabe1990], and three adjacent
references that a numeric style may collapse into a range [@mulford1994; @nakajima1994;
@mitchell2009].

A citation carrying a locator is also rendered [@watanabe1990, p. 23].

# Results

A citation inside a table cell must use the same superscript format as the body text
(Table 1). A citation inside a figure legend must do the same ([@fig:fixture]).

: Citations rendered inside a table.

| Item                   | Reference       |
|------------------------|-----------------|
| Journal article        | [@mulford1994]  |
| Paper in Japanese      | [@nakajima1994] |
| Book                   | [@watanabe1990] |

![Fixture figure; the legend cites a reference [@mitchell2009] to confirm that legends use
the same citation format.](figs/fig-overview.svg){#fig:fixture}

# Discussion

The reference list below is the artifact under test. Its expected content is
`data/dummy/bhi-csl/expected.txt`.

# References
