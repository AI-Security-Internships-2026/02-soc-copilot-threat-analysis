# Reproduction runner logs (issue #45, M6.2)

## `reproduce_all_dryrun_bash.log`

Real output of `bash scripts/reproduce_all.sh --dry-run`, ANSI codes stripped.
28 steps planned, nothing executed. Every script path it names was checked to
exist on this branch.

## PowerShell dry-run — **not produced, and why**

The issue asks for a committed dry-run log for *both* scripts. The bash log is
real. **There is no PowerShell log**, because PowerShell is not installed on the
development machine (macOS) and could not be installed: Homebrew refused to
resolve any formula while an unrelated third-party tap (`mongodb/brew`) sits
untrusted in the environment, and trusting an unrelated third-party tap to
satisfy a logging requirement is not a trade worth making.

Rather than fabricate the log, here is exactly what *was* verified about
`reproduce_all.ps1`:

- **Identical script set.** Both runners name the same 27 script paths
  (`experiments/*.py`, `scripts/*.py`, `tests/*.py`), compared as sorted sets.
- **Identical step sequence.** Both define the same 32 step labels, in the same
  order, with the same run-vs-skip disposition under each flag. Verified by
  diffing the extracted label lists after normalising the helper-function names
  (`run`/`skip` against `Invoke-Step`/`Skip-Step`) — the diff is empty.
- **Structural check.** Balanced braces, parentheses, brackets and quotes; every
  helper called is also defined. This is a structural check, **not a parse** —
  `pwsh` never ran, so a genuine PowerShell syntax error remains possible.
- **Windows venv layout** is handled: the script prefers
  `venv\Scripts\python.exe` and falls back to `venv/bin/python`.

**What a Windows reviewer should do first:** run
`.\scripts\reproduce_all.ps1 -DryRun` and confirm it prints 28 steps. That is
the one thing this environment could not check, and it takes seconds.

This follows the precedent set for issue #29's WSL2 requirement: do the
substantive equivalent on the available platform and label the deviation,
rather than report the step as done as specified.
