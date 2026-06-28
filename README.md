# Nature Communications TOC-based LaTeX Manuscript

This folder contains a LaTeX manuscript restructured to match the requested Nature Communications-style Table of Contents.

## Files
- `main.tex`: main entry
- `sections/`: section `.tex` files aligned with the requested TOC
- `figures/`: figures copied from the attached manuscript materials
- `references.bib`: bibliography copied from the attached manuscript materials

## Build
This project uses BibTeX (`plainnat`). Compile with a standard LaTeX toolchain, e.g.:

```bash
pdflatex main.tex
bibtex main
pdflatex main.tex
pdflatex main.tex
```

(If your environment does not include `bibtex`, install a full TeX distribution.)
