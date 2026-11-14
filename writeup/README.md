# Write-up (2 pages, LaTeX)

- `main.tex`: the document. Replace the grey `\todo{...}` placeholders with your text.
- `generated/`: plot data and table rows, built from the committed stats files. Do not edit;
  regenerate with `.venv/bin/python writeup/make_figures.py` (from `stage1/`).

## Compile (works offline)

```bash
cd writeup && ./tectonic --only-cached main.tex
```

`--only-cached` never touches the network. The packages this document uses are cached in
`~/Library/Caches/TectonicProject.Tectonic` (about 50 MB); don't clear that folder. Adding a
`\usepackage` that isn't cached yet needs one online compile without `--only-cached`.

`tectonic` (the binary in this folder, v0.17.0) is git-ignored. Reinstall with:

```bash
curl --proto '=https' --tlsv1.2 -fsSL https://drop-sh.fullyjustified.net | sh
```
