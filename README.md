# docx-paper-template-jbi

**Write your manuscript in Markdown and get a submission-ready Word (.docx) file.**
This is a template repository: copy it, write `src/main.md`, choose a journal profile, and build.
It covers the parts of journal submission that are usually done by hand in Word:
change-highlighted diffs for peer review, vector figures without quality loss,
journal-specific formatting, and the final submission package.

日本語版: [README.ja.md](README.ja.md)

> **Not affiliated with any journal or society.** This project is an independent tool. It is not
> provided, reviewed, or endorsed by *BioHealth Informatics* or the Japan Association for Medical
> Informatics. The `bhi` profile is our reading of the journal's public author guidelines, and
> those guidelines can change at any time. **Always check the official
> [For Authors](https://biohealth-informatics.com/for-authors/) page before you submit.**

---

## Features

- **Markdown → .docx** with pandoc. Title, authors, affiliations, abstract and keywords are written
  as styled blocks in the body, so they are formatted by the journal's reference document and take
  part in the diff.
- **Full-manuscript diff for peer review.** Compares two versions of `main.md` on the pandoc AST
  and marks added words in blue and deleted words in red strikethrough — in the title, authors,
  abstract, keywords, body text, tables, and tables inside text boxes. The document structure is
  kept intact.
- **Vector figures.** SVG figures are embedded natively in the .docx, with a PNG fallback
  rendered at the profile's resolution (300 dpi by default). PDF figures are converted to SVG
  first. Mermaid diagrams (`.mmd`) are rendered in a container and handled the same way.
- **Journal profiles** (`data/journals/<id>/`): one directory per journal holds the formatting
  (`profile.yaml`), the citation style (CSL), and the Word reference document (`reference.docx`,
  generated from `profile.yaml` the first time it is needed). The manuscript itself stays
  journal-independent.
  - `_default` — a generic submission format: double spacing, continuous line numbers,
    Times New Roman 12 pt, A4 with 25 mm margins, AMA-style numbered citations.
  - `bhi` — *BioHealth Informatics*.
- **BHI support:**
  - 8 article types with their own word, abstract and figure/table limits (`--article-type`)
  - a citation style that reproduces the guideline's examples (superscript `1)` markers),
    with an acceptance test against those examples
  - figures delivered as PowerPoint files (one figure per file, vector SVG plus a 300 dpi PNG
    fallback), since PowerPoint is the only accepted format that keeps vector graphics
  - a reference document that follows the guideline's "12-point type face" and "double-spaced
    throughout": the title, headings and abstract use the body size (12 pt), heading levels are
    marked by bold and italics, and no paragraph style keeps its own line spacing
  - final-submission restructuring: tables taken out of the manuscript into one file per table
    (`tables/Table1.docx`, …), figure titles and legends collected after the references,
    placeholders left in the text, so the manuscript file holds text only
  - `SUBMISSION.md`: a per-upload-type file list with formats, sizes, and the forms to attach
  - `CAPTIONS.md`: the title and legend of each table and figure, extracted from the files to be
    uploaded, ready to paste into the submission system's Caption / Legend field
  - rule checks: word counts per article type, required sections, abstract structure, and
    writing checks such as thousands separators, composed characters (`℃`), and legend placement
  - a manuscript skeleton with all required sections (`data/journals/bhi/skeleton/`)
- **Optional PDF output through Microsoft Word.** The .docx is sent to Google Drive with rclone,
  a watcher on a Windows PC converts it with Word, and the PDF comes back. This shows the layout
  as Word renders it (the PDF that the submission system builds for editors and reviewers can still
  differ). LibreOffice is deliberately not used for PDF output. The final submission package is
  converted as well, and then placed in its own Drive folder (`submission-<journal>/`) so that
  the files to upload can be picked from one place.

## Requirements

- **Docker** (Engine with Compose v2), **bash**, and **git**. All conversion runs in containers;
  nothing is installed on the host.
- An **x86-64 (amd64)** host. The pandoc image installs amd64 release binaries. The tooling is
  developed on Linux; other environments have not been tested.
- **Network access on the first build.** The images download pandoc and pandoc-crossref, the
  Mermaid CLI with headless Chromium, and (for the optional `svg-conversion` image) the
  Microsoft Core Fonts.
- To view the native SVG figures as vectors: **Microsoft 365 or Office 2019 and later**.
  Office 2016 and other viewers show the PNG fallback.

Optional:

- **PDF output:** rclone configured with a Google Drive remote (default name `gdrive:`), and a
  Windows PC with Microsoft Word that syncs the same Drive folder. See
  [docs/roundtrip-windows-watcher.md](docs/roundtrip-windows-watcher.md).
- **`svg-conversion` image** (used only to export figures as PDF with outlined text, e.g. the
  `_default` profile in final mode): proprietary fonts such as Calibri or Yu Gothic are **not
  included**. Put the font files you are licensed to use in `fonts/` before the image is built.
  Without them the image still builds and substitutes other fonts. The image is built only when it
  is missing, so if you add fonts after it has been built, remove it
  (`docker image rm docx-paper-template-svg-converter`) and it is rebuilt the next time it is needed.
  Building this image downloads the Microsoft Core Fonts from the `corefonts` project; **by building it
  you accept Microsoft's End-User License Agreement for these fonts** (<https://corefonts.sourceforge.net/eula.htm>).
  The image is built automatically the first time it is needed (for example by `_default` in final mode).

## Quick start

These commands build the bundled sample manuscripts. Run them from the repository root.

```bash
git clone https://github.com/fk506cni/docx-paper-template-jbi-public.git
cd docx-paper-template-jbi-public

# 1. Build the main conversion image (pandoc, pandoc-crossref, Python, librsvg, LibreOffice)
docker compose -f docker/docker-compose.yml build

# 2. Use the bundled sample (data/dummy/) as the input instead of src/
echo dev > .development

# 3. Markdown -> .docx (the first run also builds the Mermaid image and generates reference.docx)
bash scripts/build.sh
#    -> data/step02_build/main.docx

# 4. Change-highlighted diff between two versions of the manuscript
mkdir -p jank
sed 's/Twenty trials/Twenty-four trials/' data/dummy/main.md > jank/main-new.md
bash scripts/diff.sh data/dummy/main.md jank/main-new.md
#    -> data/step03_diff/main_diff.docx

# 5. Draft package with the generic profile (figures stay embedded)
bash scripts/package.sh --journal _default --mode draft
#    -> data/output/_default/

# 6. BHI sample: build, then assemble the final submission package
bash scripts/build.sh   --journal bhi --article-type original --input data/dummy/bhi
bash scripts/package.sh --journal bhi --mode final --input data/dummy/bhi
#    -> data/output/bhi/ (manuscript.docx, tables/*.docx, figures/*.pptx, SUBMISSION.md, CAPTIONS.md, ...)
```

Open the resulting files in Word. In `data/step03_diff/main_diff.docx` the changed number in the
abstract is highlighted. `data/output/bhi/manuscript.docx` holds text only: each table is in its
own file in `data/output/bhi/tables/`, the figure legends follow the references, and the figures
themselves are in `data/output/bhi/figures/`. `data/output/bhi/SUBMISSION.md` lists the files to
upload, the rule-check results, and the points to review before submitting;
`data/output/bhi/CAPTIONS.md` holds the text for the Caption / Legend fields.

### Start your own manuscript

```bash
rm .development                 # the input root switches from data/dummy/ to src/
cp -r data/dummy/. src/         # start from the generic sample, then edit src/main.md
```

For BHI, start from the skeleton instead (`cp data/journals/bhi/skeleton/main.md src/main.md`)
and follow the BHI walkthrough in [docs/usage-guide.md](docs/usage-guide.md).
Keep your manuscript under `src/` and commit it as usual; generated files go to `data/` and are
ignored by git.

## Main commands

| Command | What it does |
|---|---|
| `bash scripts/build.sh [--journal <id>] [--article-type <type>]` | Figures → `data/step02_build/main.docx` |
| `bash scripts/diff.sh [REVISION \| old.md new.md]` | Diff against a git revision (default `HEAD~1`) or between two files → `data/step03_diff/main_diff.docx` |
| `bash scripts/package.sh --journal <id> --mode draft\|final` | Submission package → `data/output/<id>/` (final mode separates the figures, and for BHI the tables, and runs the rule checks) |
| `bash scripts/check-figures.sh [--journal <id>] [--figures-dir <dir>]` | Checks figure resolution; with `--figures-dir`, also the structure of PowerPoint figures |
| `bash scripts/check-csl.sh [--docx <file>]` | Compares formatted references with a fixture of expected output |
| `bash data/journals/make-reference.sh <id>` | Generates a journal's `reference.docx` from its `profile.yaml`. `build.sh` and `diff.sh` run it when the file is missing; run it yourself after you change the page setup in `profile.yaml` |
| `bash docker/mermaid/convert.sh <file.mmd> both` | Renders a Mermaid diagram to SVG and PDF on its own (not needed for builds, which render `figs/mermaid/*.mmd` themselves; render a copy outside `figs/` when you only want to look at it) |
| `bash scripts/push-win-tools.sh` / `check-pdf-path.sh` / `roundtrip.sh` | Optional PDF output through Word (setup / diagnosis / conversion; `roundtrip.sh` also places a final submission package in the Drive folder `submission-<journal>/`) |
| `bash scripts/baseline.sh <suffix>` / `baseline-bhi.sh <suffix>` / `scripts/compare-snapshots.py` | Regression snapshots of the build outputs and their comparison |

`build.sh`, `diff.sh`, `package.sh`, `check-figures.sh`, `check-csl.sh`, `baseline.sh`, `baseline-bhi.sh`
and the three PDF scripts print their usage with `--help`. Script messages and the detailed guides are in Japanese.

## Repository layout

```
.
├── src/              # your manuscript: main.md, ref.bib, figs/ (+ cover-letter.md, revise-report.md)
├── data/
│   ├── journals/     # journal profiles: _default/ and bhi/ (bhi/skeleton/ = manuscript skeleton)
│   ├── dummy/        # sample manuscripts and test fixtures (used while .development exists)
│   └── step*/ output/ products/   # generated files (ignored by git)
├── main/             # processing code, one directory per pipeline stage
│   ├── 00_setup/     #   shared settings, Lua filters, OOXML helpers
│   ├── step01_figures/  step02_build/  step03_diff/  step04_pdf/  step05_package/
├── scripts/          # entry points (build / diff / package / checks / PDF round trip)
├── docker/           # pandoc, Mermaid and svg-conversion images (no ports are exposed)
├── fonts/            # optional proprietary fonts for svg-conversion (ignored by git)
└── docs/             # detailed guides (Japanese)
```

## Documentation

The detailed guides are written in Japanese.

| Document | Contents |
|---|---|
| [docs/usage-guide.md](docs/usage-guide.md) | Step-by-step usage: figures, journals, diffs, packages, PDF, and the BHI walkthrough |
| [docs/architecture.md](docs/architecture.md) | Processing flow and design decisions |
| [docs/profile-schema.md](docs/profile-schema.md) | Every `profile.yaml` key, its default, and what reads it |
| [docs/design-fullarea-diff.md](docs/design-fullarea-diff.md) | How the structure-preserving diff works |
| [docs/journal-bhi.md](docs/journal-bhi.md) | BHI requirements mapped to the implementation |
| [docs/bhi-submission-checklist.md](docs/bhi-submission-checklist.md) | One-page checklist for submission day |
| [docs/migration-latex.md](docs/migration-latex.md) | Moving an existing LaTeX manuscript to this template |
| [docs/roundtrip-windows-watcher.md](docs/roundtrip-windows-watcher.md) | Setting up and diagnosing the Word PDF conversion |
| [CLAUDE.md](CLAUDE.md) | Conventions in short form (also read by AI coding assistants) |

## Sample manuscripts

The manuscripts in `data/dummy/` are obvious fiction: a parody of the "tremendous hunch"
(TJD/THS) story from <https://github.com/fk506cni/jami-pandoc-public>. The authors, institutions,
and results are invented. They exist so that every feature can be built and checked without a
real manuscript.

## Limitations

- **PDF output needs Windows and Microsoft Word.** Without them you still get every .docx, but no PDF.
- **Diff:** a moved paragraph is shown as a deletion plus an addition. Tables with merged cells
  can be aligned imperfectly. The reference list and equation contents are regenerated rather
  than diffed. Text without spaces between words (such as Japanese) is compared phrase by phrase
  rather than word by word.
- **Figures:** resolution is guaranteed only for images generated from SVG or PDF. Raster images
  you place yourself are copied as they are. Some valid SVG files render incorrectly in Word or
  PowerPoint (several SVG files concatenated into one, or colors written as `hsl()`);
  `scripts/check-figures.sh` lists them as warnings.
- **Rule checks are aids, not guarantees.** Typeset page counts, English quality, MeSH keywords,
  and permissions cannot be checked automatically; see the checklist.
- **Two journal profiles are included.** Other journals are added by copying `_default`
  (see the usage guide).

## License

The code in this repository is released under the [MIT License](LICENSE).
The two bundled CSL citation styles are under CC BY-SA 3.0. The Word reference documents are not
bundled; they are generated on your machine from pandoc's default data.
See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

Documents you write and build with this template are your own work.
