# Weekly Progress Log: SOC Co-pilot: LLM-Assisted Threat Analysis and Alert Triage

**Student:** _[Fill in your name]_
**GitHub username:** _[Fill in]_

---

## How to Use This File

Add a new section every Friday before opening your weekly Pull Request.
Be honest — problems and blockers are normal and help your supervisor support you.

---

## Week 1

**Branch:** `your-name-week-01`
**PR link:** _[Add link after opening PR]_

### Completed this week
- [ ] Read README and proposal
- [ ] Set up local environment (Python venv, dependencies)
- [ ] Ran `src/main.py` successfully
- [ ] Wrote personal introduction (below)
- [ ] Identified 5 related papers / tools / datasets

### Personal Introduction
_Write 3–5 sentences about your background, skills, and what you hope to learn._

### Problems / Blockers
_Describe any issues you faced. Did you solve them? How?_

### Next week plan
- Read the 5 papers identified this week
- Complete `docs/proposal.md` draft
- Set up dataset download / preprocessing pipeline

---

## Week 2

**Branch:** `asma-week-02`
**PR link:** _[Add link after opening PR]_

### Completed this week
- [x] Created `asma-week-02` branch from `dev`
- [x] Drafted `docs/proposal.md` (problem statement, research questions, methodology)
- [x] Built GUIDE dataset schema reference + synthetic sample generator (for local dev without the full Kaggle download)
- [x] Built data loader + preprocessing pipeline (feature engineering, encoding)
- [x] Built baseline Random Forest triage classifier (TP/BP/FP) with eval metrics
- [x] Wired `src/main.py` to run the full pipeline end to end — confirmed working
- [ ] Expand literature review to 10 papers/tools (in progress)
- [ ] Real GUIDE dataset download/preprocessing pipeline (currently running on synthetic sample)

### Problems / Blockers
Hit a merge conflict in `docs/weekly-progress.md` after stashing local changes across a branch switch — resolved by manually merging the conflicting "Next week plan" section.

### Next week plan
- Continue triage agent implementation (LangGraph)
- Architecture design doc (due Week 3)
- Expand literature review toward 10 papers/tools (carried over)

---

_(Add a new section each week)_