# ORION — Regime-dependent limits of hierarchical memory orchestration in large-scale AI inference

LaTeX manuscript targeting **Nature Computational Science** (or Nature Machine Intelligence).

---

## Repository structure

```
.
├── main.tex                  # IEEEtran template (draft / internal review)
├── main_nature.tex           # Springer Nature sn-jnl template (submission)
├── sn-jnl.cls                # Springer Nature journal class (required)
├── IEEEtran.cls              # IEEE class (for main.tex)
├── IEEEtranDOI.bst           # IEEE BibTeX style
├── reference-data.bib        # Bibliography database
├── latexmkrc                 # latexmk configuration (timezone)
├── run.sh                    # Build script
├── figures/                  # All figures (PNG)
└── section/                  # Per-section .tex files
    ├── 001_title.tex
    ├── 005_author.tex        # IEEEtran author block
    ├── 005_author_nature.tex # sn-jnl author block
    ├── 006_abstract.tex
    ├── 006_abstract_nature.tex
    ├── 010_introduction.tex
    ├── 020_regime_principle.tex
    ├── 030_transfer_model.tex
    ├── 040_experimental_validation.tex
    ├── 050_implications.tex
    ├── 060_discussion.tex
    ├── 070_methods.tex
    ├── 080_conclusion.tex
    ├── 090_ack.tex
    ├── 095_reference.tex
    ├── 095_reference_nature.tex
    └── 900_appendix.tex
```

---

## 1. Install dependencies (Ubuntu 24.04)

```bash
# Core TeX Live packages
sudo apt-get update
sudo apt-get install -y \
    texlive-base \
    texlive-latex-base \
    texlive-latex-recommended \
    texlive-latex-extra \
    texlive-fonts-recommended \
    texlive-fonts-extra \
    texlive-science \
    texlive-pictures \
    texlive-bibtex-extra \
    bibtex

# PDF viewer
sudo apt-get install -y evince
```

> **Note:** `texlive-science` provides `algorithm.sty` and `algorithmicx.sty`
> required by this manuscript.

---

## 2. Build

### Nature template (for submission)

```bash
./run.sh nature
```

Produces `main_nature.pdf`.

### IEEEtran template (internal draft)

```bash
./run.sh
```

Produces `main.pdf`.

### What `run.sh` does internally

```
pdflatex  →  bibtex  →  pdflatex  →  pdflatex
```

---

## 3. View the PDF

```bash
# Nature submission PDF
evince main_nature.pdf

# IEEEtran draft PDF
evince main.pdf
```

Other viewers:

```bash
xdg-open main_nature.pdf     # system default viewer
okular main_nature.pdf        # KDE viewer
zathura main_nature.pdf       # lightweight viewer
```

---

## 4. Anonymity switch

The `\anonymous` flag in `main.tex` / `main_nature.tex` controls author visibility:

| Value | Effect |
|-------|--------|
| `1`   | Real author name and affiliation shown |
| `0`   | "Anonymous Author(s)" for blind review |

---

## 5. Target journals

| Journal | Scope fit |
|---------|-----------|
| **Nature Computational Science** | Theory (regime boundaries) + computational experiments |
| **Nature Machine Intelligence** | AI system principles + broad ML impact |
| Communications Engineering | Systems engineering, higher acceptance rate |
