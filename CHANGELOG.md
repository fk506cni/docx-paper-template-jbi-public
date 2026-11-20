# Changelog

All notable changes to this project are recorded in this file.
Versions follow [Semantic Versioning](https://semver.org/).

## 0.1.3 — sample handling, diff provenance and figure fixes

### Added

- **`scripts/remove-sample.sh`**: removes the sample paper from `src/`, but only the files whose contents
  still match the sample (`scripts/lib/sample-files.sha256`); edited files and your own files with the same
  names are kept, so it is safe to run more than once (`--dry-run` lists what would be removed and kept).
  The README, `src/README.md` and the guides use it instead of `rm -rf`.
- **Leftover sample files stop a final package**: when `main.md` is not the sample but other sample files
  (cover letter, supplementary file, references, figures) remain unchanged, `package.sh --mode final`
  stops and lists them (a draft package notes them). Building the sample itself still works.

### Fixed

- **Documentation**: the `roundtrip.sh` hint for the state right after the quick start (use `--skip-build`;
  `INPUT_ROOT=data/dummy/bhi` only for a package built with `--input data/dummy/bhi`). The diff command
  of the quick start passes `--input data/dummy`, so it works without `.development`. If you update from
  0.1.0 or 0.1.1 with your own manuscript in `src/`, the sample files are added next to yours: keep your
  own versions and run `bash scripts/remove-sample.sh`.
- **Diff provenance**: `diff.sh` records a hash of the other manuscript inputs (`ref.bib`, `cover-letter.md`,
  `revise-report.md`, `figs/`) in `data/step03_diff/.main_diff.source`, and `SUBMISSION.md` notes when they
  changed after the diff or when the record lacks the hash. `diff.sh` checks the figure provenance after the
  diff and stops, deleting the diff it made, if the inputs or figures changed during the diff. A failed diff
  leaves neither a broken `main_diff.docx` nor intermediate files (it is written under a temporary name).
  `diff.sh` stops with a message when a manuscript is outside the repository or given as an absolute path.
- **Mermaid figures**: only figures made from a `.mmd` directly in `figs/mermaid/` are kept as the Mermaid
  PDF. Other figures in `figs/mermaid/` or in folders named `mermaid` (hand-made SVG, raster, PDF without a
  `.mmd`, subfolders) are preprocessed and converted like any other figure, so a PDF-format final package
  works with them. A `.mmd` that is not directly in `figs/mermaid/` is not drawn, and the preprocessing says so.
- **Supplementary files**: packaging also stops on links to a folder that contains the input root, on folders
  reached through a link that hold an item named `supplementary`, when `supplementary/` itself is such a
  link, and on file links to the manuscript's `main.md` / `ref.bib` / `cover-letter.md` / `revise-report.md`.
  A folder that can be listed but not entered gives a message instead of a traceback. Packaging that stops
  part-way removes the half-built package and restores the previous one.
- **PowerPoint figures (`figures.pptx.inline_css`)**: a `<use>` with both `href` and `xlink:href` is checked
  against both targets; ids containing `:` or `=`, or percent-encoded, are recognised as references; the
  `var()` check covers every SVG 1.1 and SVG 2 presentation attribute (such as `transform-origin`,
  `mask-type` and `d`); `var()` in element `style` attributes is resolved also in an SVG without `<style>`;
  a `var()` that resolves to an empty value stops the conversion; a `<style>` in a namespace other than
  SVG or XHTML is not read as CSS.
- **Figure numbers**: untitled images at the end of the manuscript are not listed as a cause of mismatched
  figure numbers; `SUBMISSION.md` notes that they do not shift the numbering.
- **Messages**: the Docker start-up message also appears on a fresh clone (before `reference.docx` is
  generated); a figure provenance record with a repeated key is treated as broken; the rule-check notes on
  text boxes name the restructuring the journal uses.

## 0.1.2 — sample manuscript in src/

### Added

- **Sample manuscript in `src/`**: a fresh clone has a complete sample paper in `src/` (`main.md`,
  `ref.bib`, `cover-letter.md`, two figures and a supplementary file), so `bash scripts/build.sh
  --journal bhi --article-type original` and `bash scripts/package.sh --journal bhi --mode final` run
  without `.development`. It is the clearly fictional "TJD / THS" parody written to the BHI Original
  Article format, the same paper as `data/dummy/bhi/`. The README, `src/README.md` and the usage guide
  describe how to remove it and start from the BHI skeleton or the generic sample.

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
