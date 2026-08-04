# IJIS LaTeX build (issue #16, PROGRESS.md item T1)

Springer Nature's official unified journal LaTeX template (`sn-jnl.cls`,
`.bst` styles, and the `sn-article.tex` sample), pulled from
[godkingjay/springer-nature-latex-template](https://github.com/godkingjay/springer-nature-latex-template),
a mirror of Springer Nature's public LaTeX author package (also distributed
via the [Overleaf gallery](https://www.overleaf.com/latex/templates/springer-nature-latex-template/myxmhdsbzkyd)).
Version 2.1 (April 2023), per the header comment in `sn-jnl.cls`.

## Files

- `ijis-draft.tex` — the manuscript. Section-by-section port of `../draft.md`,
  content otherwise unchanged (see the header comment in the file for the
  few structural adaptations LaTeX forced, e.g. Introduction subheadings
  become bold run-in paragraphs per the template's own guidance not to use
  `\subsection` there).
- `references.bib` — BibTeX entries for the paper's 17 references. Several
  carry `{AUTHORS TO VERIFY}` placeholders, ported as-is from `draft.md`'s
  `[AUTHORS TO VERIFY]` flags — see `../PROGRESS.md` item R2. Do not
  replace these with guessed names; pull real author lists from
  arXiv/publisher metadata.
- `sn-jnl.cls`, `sn-*.bst` — the class file and reference-style files from
  the upstream template. `sn-mathphys` (numbered) is the one actually used
  (matches `draft.md`'s existing `[1]`...`[17]` numbered citation scheme);
  the others are kept only because they shipped in the same template
  package.
- `sn-article.tex` — the upstream sample/documentation article, kept as a
  syntax reference for tables, equations, appendices, theorem environments,
  etc. Not part of the submission.

## Building

Requires a LaTeX toolchain. This was verified locally with
[tectonic](https://tectonic-typesetting.github.io/) (`brew install
tectonic`), which self-fetches missing packages — no system TeX
distribution needed:

```
tectonic ijis-draft.tex
```

With a standard TeX Live/MacTeX install instead:

```
pdflatex ijis-draft && bibtex ijis-draft && pdflatex ijis-draft && pdflatex ijis-draft
```

`ijis-draft.pdf` is committed as a build check, not a submission-ready
PDF — see `../PROGRESS.md` for what's still open (E2, E3, R1, R2, T2, T3).
Rebuild it after any further edits rather than trusting the committed copy
is current.
