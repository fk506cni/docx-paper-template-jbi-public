# Changelog

All notable changes to this project are recorded in this file.
Versions follow [Semantic Versioning](https://semver.org/).

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
  document use the body size for every paragraph style (heading levels shown by bold and italics),
  remove the theme color from titles and headings, and drop per-style line spacing.
- **Submission package** (`scripts/package.sh`): figures exported as PowerPoint (vector SVG with a
  PNG fallback), PNG, or PDF; tables moved to the end or written as one file per table
  (`tables.placement: end | separate`; `bhi` uses `separate`, so the manuscript file holds text
  only); figure legends collected after the references; `SUBMISSION.md` with the upload list;
  `CAPTIONS.md` with the title and legend of each table and figure for the submission system's
  Caption / Legend field; supplementary files copied unchanged; rule checks for word limits,
  required sections and common writing issues.
- **PDF (optional)**: conversion with Microsoft Word on Windows through Google Drive and rclone,
  with a watcher that converts each file in a separate process under a time limit, plus setup
  and diagnosis scripts. The final submission package is converted as well and placed in its own
  Drive folder (`submission-<journal>/`), after checking that it is up to date and was built from
  the current manuscript.
- **Regression snapshots**: `scripts/baseline.sh`, `scripts/baseline-bhi.sh` and
  `scripts/compare-snapshots.py`.
