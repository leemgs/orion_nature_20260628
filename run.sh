#!/bin/bash
set -e

# Usage:
#   ./run.sh           → build main.pdf      (IEEEtran template)
#   ./run.sh nature    → build main_nature.pdf (sn-jnl / Springer Nature template)

if [ "${1}" = "nature" ]; then
    MAIN="main_nature"
else
    MAIN="main"
fi

echo "[1/4] pdflatex (first pass) — ${MAIN}..."
pdflatex -interaction=nonstopmode "${MAIN}.tex"

echo "[2/4] bibtex..."
bibtex "${MAIN}"

echo "[3/4] pdflatex (second pass)..."
pdflatex -interaction=nonstopmode "${MAIN}.tex"

echo "[4/4] pdflatex (final pass)..."
pdflatex -interaction=nonstopmode "${MAIN}.tex"

echo "Done: ${MAIN}.pdf"
