# IJIS LaTeX build (issue #16, PROGRESS.md item T1)

`svjour3.cls` + `svglov3.clo` — the actual LaTeX macro package Springer's own
current submission-guidelines page for this journal (10207) links under
"LaTeX Package (Download zip, 279 kB)". Confirmed 2026-08-06 by fetching that
page directly (no longer gated once accessed with an authenticated session)
and cross-checking the linked zip's filename
(`1633537_svjour3-Latex-package.zip`) and contents against `template.tex`'s
own `\documentclass[twocolumn]{svjour3}` invocation, which matches the
guidelines' text instruction verbatim ("choose the formatting option
'twocolumn'").

This replaces an earlier `sn-jnl.cls`-based port (Springer Nature's newer
unified template) that was a third-party-corroborated guess, not a
first-party confirmation — see git history for that version if needed.

## Files

- `ijis-draft.tex` — the manuscript. Section-by-section port of `../draft.md`,
  content otherwise unchanged (see the header comment in the file for the
  few structural adaptations LaTeX forced) plus one addition: an
  AI-assistance disclosure subsection in Section 3, per the guidelines'
  Title Page instructions on documenting non-copy-editing LLM use.
- `references.bib` — BibTeX-format source of truth for the paper's 22
  references (content only; not used directly by the build, see below).
- `svjour3.cls`, `svglov3.clo` — the class file and the generic "global"
  class-option file from the official zip. **Not** `svepjc3.clo` — that
  option file is specific to *European Physical Journal C*, a different
  journal bundled in the same generic Springer zip, and does not apply to
  IJIS.
- Bibliography: hand-written `\thebibliography` inside `ijis-draft.tex`
  rather than BibTeX-driven, since the only `.bst` in the official zip
  (`spphys.bst`) is styled for physics journals and `bibtex` isn't available
  in this environment (tectonic only, no bibtex/biber binary). Each entry is
  manually formatted to match the guidelines' own reference examples
  (journal article / article-by-DOI / online-document forms). Content
  (authors/titles/years/DOIs) matches `references.bib` — keep both in sync
  if a reference changes; `references.bib` is not otherwise built from.
- Citation style: default `svjour3` `\cite` (no `natbib` option loaded)
  produces numbered, compressible bracket citations (`[3]`, `[1-3,7]`)
  directly from `\@lbibitem`/`\@citex` in `svjour3.cls` — confirmed by
  reading the class source, and matches the guidelines' own citation
  examples exactly.

## Building

Requires a LaTeX toolchain. This was verified locally with
[tectonic](https://tectonic-typesetting.github.io/) (`brew install
tectonic`), which self-fetches missing packages — no system TeX
distribution needed:

```
tectonic ijis-draft.tex
```

Compiles cleanly to a 10-page, two-column PDF with all citations and
cross-references resolved (verified 2026-08-06; zero `undefined` warnings in
the log after a full build).

`ijis-draft.pdf` is committed as a build check, not a submission-ready
PDF — see `../PROGRESS.md` for what's still open.
