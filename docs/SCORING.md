# Scoring and assessment methodology

All numbers come from deterministic, versioned code. Versions are stored with every result
(`scoring-v1`, `adaptive-v1`, `proficiency-v1`, `planner-v1`, `ranking-v1`, `interview-rubric-v1`).

## Separate indicators (never merged into each other)

| Indicator | Measures | Inputs |
|---|---|---|
| Resume quality (0-100) | How well the document is written | Sections 25, contact 10, quantified bullets 20, action verbs 15, length 15, dated roles 15 |
| Role fit (0-100) | Resume **evidence** for each job requirement | Weighted share of skill requirements with evidence |
| Experience alignment | Dated years vs stated requirement | `min(1, resume years / required years)` |
| Assessed proficiency | Quiz and practical results only | Adaptive assessment |
| Project evidence | Rubric self-assessment of portfolio projects | Project rubric (1-4 per criterion) |
| Interview performance | Mock-interview rubric | Last 3 completed interviews |
| Overall readiness | Weighted mean of the **available** indicators above | Weights below |

**Role fit**: importance weight mandatory 3 / preferred 1; evidence strength demonstrated in work history 1.0,
listed only 0.6, related skill 0.3, none 0. A keyword match is a *claim with a supporting line*, not proof of
competence. Role fit is not a hiring probability, and there is no "ATS pass score".

**Readiness weights**: resume quality 0.10, role fit 0.10, assessed proficiency 0.30, experience 0.15, projects
0.20, interviews 0.15. Missing components are listed and the remaining weights are renormalised. Readiness is
marked provisional until an assessment exists.

## Proficiency scale (0-100, `proficiency-v1`)

Bands (configurable in `services/evidence.py`): novice 0, beginner 25, developing 50, proficient 70, advanced 85.
Targets: mandatory skills 70, preferred 60.

Evidence types: self-reported, resume, quiz, practical, project, course completion. Only quiz/practical change
**assessed** proficiency. Course completion is recorded but never raises it; finishing a course prompts a checkpoint
quiz instead. Before assessment, a *provisional* estimate is used for planning (resume context: work history 55,
skills list 40; self-rating 1-5 → 5/25/45/60/75), always labelled provisional.

## Adaptive assessment (`adaptive-v1`)

A bounded heuristic, not a calibrated statistical model:

1. **Blueprint** from the job's skill requirements. Mandatory skills need 2+ questions, preferred 1+. Budget is
   about one extra question per mandatory skill, between 8 and 30. Professional skills (communication, etc.) are
   assessed through interviews and projects, and listed as "not covered by quiz".
2. **Selection**: cover every mandatory skill first (prerequisites first, then importance), then spend the
   remaining budget where importance × uncertainty is highest. Stops early when every skill has medium+ confidence.
3. **Difficulty staircase**: starts from the provisional level (easy/medium/hard); correct → harder, wrong → easier;
   a weak prerequisite resets dependants to easy.
4. **Rotation**: unseen questions preferred; repeated exposures count at half weight.
5. **Scoring**: weighted accuracy (easy 1, medium 1.5, hard 2) × cap by the hardest difficulty attempted
   (easy 60, medium 85, hard 100). Multi-select gives partial credit (correct − incorrect picks).
6. **Confidence** by number of scored answers: <2 insufficient (no score shown), 2-3 low, 4-5 medium, 6+ high.

A short quiz is not a scientifically validated measure of professional competence, and the UI says so.

## Planner (`planner-v1`)

Hours per skill = taxonomy effort × gap / 70, minus 80% of already-completed lesson/exercise time. Split into
lessons 60%, exercises 30%, checkpoint quiz and milestone. Tasks are chunked to fit a study day and scheduled
greedily; **each week's total never exceeds weekly hours** (asserted in code and tested). Weekly revision is 10%
from week 2. If the work runs past the deadline, alternatives are offered: later deadline, more hours (if ≤ 40/week),
or mandatory-only scope.
