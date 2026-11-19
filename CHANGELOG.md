# Changelog

All notable changes to this project are recorded in this file.
Versions follow [Semantic Versioning](https://semver.org/).

## 0.1.1 — fixes

### Fixed

- **PowerPoint figures (`figures.pptx.inline_css`)**: opacity is no longer folded into `fill-opacity`
  for shapes with a `filter`, for elements reused through `<use>`, `<pattern>` or `<feImage>`, or for
  content inside `<defs>` / `<symbol>`; an `rgba()` / `hsl()` colour that cannot be written as a single
  value in such places stops the conversion. CSS variables are taken only from rules that match the
  root element; a definition under `#<root id> :root` (as Mermaid writes it) counts as undefined, and a
  presentation attribute that uses `var()` stops the conversion.
- **Figure provenance**: the record of the figure preprocessing also covers Mermaid PDFs and carries
  a format version, so a build made with an earlier version must be rebuilt before a final package or
  `--skip-figures`. A PDF in a subfolder of `figs/mermaid/` counts as a manuscript input. `build.sh`
  checks the figure provenance again before writing its record, and `diff.sh` stops if the manuscript
  changes while the diff is made.
- **Supplementary files**: unreadable folders or files, and links to a folder that contains
  `supplementary/` (such as the input root), stop packaging with a message.
- **Messages**: `build.sh` reports a Docker start-up failure separately from inputs that the container
  cannot see, and `SUBMISSION.md` lists every cause when figure numbers and figure files do not match.

## 0.1.0 — first public release

### Added

- **Build**: Markdown → .docx with pandoc 3.6.4, pandoc-crossref and citeproc. Title, authors,
  affiliations, abstract and keywords are written as `custom-style` blocks in the body.
  Each journal profile supplies its reference document and CSL style.
- **Diff**: a structure-preserving diff of two manuscript versions on the pandoc AST. Changes are
  highlighted word by word in the title, authors, abstract, keywords, body, tables, and tables
  inside text boxes. Works with a git revision or with two files.
- **Figures**: SVG clip fixes, PDF → SVG conversion, Mermaid rendering, native SVG embedding with
  a PNG fallback whose resolution is computed from the figure's nominal size and verified, and
  `scripts/check-figures.sh` for resolution and for SVG constructs that Word or PowerPoint render
  incorrectly.
- **Journal profiles**: `_default` (generic submission format) and `bhi` (*BioHealth Informatics*:
  eight article types, citation style with an acceptance test against the guideline's examples,
  reference document with line and page numbers and with the title, headings and abstract at the
  body size and line spacing, manuscript skeleton). Optional `text_styles` keys make the reference
  document use the body size for every paragraph style (heading levels 1–3 shown by bold and italics),
  remove the theme color from titles and headings, and drop per-style line spacing.
- **Submission package** (`scripts/package.sh`): figures exported as PowerPoint (vector SVG with a
  PNG fallback), PNG, or PDF; tables moved to the end or written as one file per table
  (`tables.placement: end | separate`; `bhi` uses `separate`, so no table stays in the main text
  flow); figure legends collected after the references; `SUBMISSION.md` with the upload list;
  `CAPTIONS.md` with the title and legend of each table and figure for the submission system's
  Caption / Legend field; supplementary files copied unchanged; rule checks for word limits,
  required sections and common writing issues.
- **PowerPoint figures for converters that ignore CSS**: `figures.pptx.inline_css` writes the
  stylesheet of an embedded SVG (for example the one R's svglite emits) into each element's `style`
  and removes it, so that a converter that ignores CSS does not paint unfilled shapes black.
  `figures.pptx.text_to_path` outlines the figure text after that step. `bhi` turns both on.
- **PDF (optional)**: conversion with Microsoft Word on Windows through Google Drive and rclone,
  with a watcher that converts each file in a separate process under a time limit, plus setup
  and diagnosis scripts. The manuscript and table files of the final submission package are converted
  as well, and the package is placed in its own Drive folder (`submission-<journal>/`), after checking that it is up to date and was built from
  the current manuscript.
- **Regression snapshots**: `scripts/baseline.sh`, `scripts/baseline-bhi.sh` and
  `scripts/compare-snapshots.py`.
