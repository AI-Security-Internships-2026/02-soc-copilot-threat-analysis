# Week 1 Tasks — SOC Co-pilot: LLM-Assisted Threat Analysis and Alert Triage

**Target branch:** `your-name-week-01`
**PR target:** `dev`
**Due:** End of Week 1

---

## Checklist

### a) Orientation
- [ ] Read `README.md` in full
- [ ] Read `docs/proposal.md` in full
- [ ] Accept the GitHub repository invitation

### b) Environment setup
- [ ] Clone the repository:
  ```bash
  git clone https://github.com/AI-Security-Internships-2026/02-soc-copilot-threat-analysis.git
  cd 02-soc-copilot-threat-analysis
  ```
- [ ] Create a virtual environment:
  ```bash
  python -m venv .venv
  source .venv/bin/activate
  pip install -r requirements.txt
  ```
- [ ] Run the starter script successfully:
  ```bash
  python src/main.py
  ```
- [ ] Create your weekly branch:
  ```bash
  git checkout dev
  git pull origin dev
  git checkout -b your-name-week-01
  ```

### c) Documentation
- [ ] Add your personal introduction in `docs/weekly-progress.md` (Week 1 section)
- [ ] Fill in your name and GitHub username at the top of `docs/weekly-progress.md`

### d) Literature search
Identify **5 related papers, tools, or datasets** and add them to `docs/literature-review.md`.
Suggested search terms:
- Google Scholar / IEEE Xplore / arXiv
- Use the project title as your initial query
- Refine with terms from the technology stack

### e) First Pull Request
- [ ] Commit your Week 1 changes:
  ```bash
  git add docs/weekly-progress.md docs/literature-review.md
  git commit -m "[Week 01] Add intro and initial literature notes"
  git push origin your-name-week-01
  ```
- [ ] Open a Pull Request on GitHub:
  - Base branch: `dev`
  - PR title: `[Week 01] Introduction and literature search`
  - Describe what you did and any questions you have for your supervisor

---

## Resources

- Project proposal: `docs/proposal.md`
- Literature review template: `docs/literature-review.md`
- Weekly log: `docs/weekly-progress.md`
- GitHub guide for students: see supervisor's `SUPERVISOR-README.md`
