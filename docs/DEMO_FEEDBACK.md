# Athena demo feedback

One sheet per person. Each answer maps to a file, so it can go straight into Athena (shown in brackets). Do not write real patient data here. Client names are fine in your own notes, but keep real names out of the Git repo: send the filled sheet to Madhav, not as a commit.

Name / persona: ______________________   Date: ____________

## 1. When is a task late or at risk? (rules/R2.yaml, gate G8)

| Question | Today (provisional) | Their answer |
|---|---|---|
| A task is **late** when… | due time has passed and status is not Complete | |
| Grace period before "late"? | none | |
| A task is **at risk** when… | due within 4 hours and no update for 2 hours | |
| Which status values mean done? | Complete | |
| Reminder after… | 2 hours | |
| Escalate to the hub leader after… | 4 hours | |
| Most alerts a day before it is noise | at most 2 messages per alert | |

## 2. Hours and digest (personas/*.yaml, gate G8)

| Question | Today (provisional) | Their answer |
|---|---|---|
| Work days | Monday to Friday | |
| Work hours (IST) | 10:00–19:00 (CSM: 17:00–02:00) | |
| Digest time | 09:00 IST | |
| What the digest must show | off-target metrics, open alerts | |
| What the digest should leave out | — | |

## 3. Metrics (context/metrics.yaml)

For each metric: one-sentence meaning, which way is good, target, owner.

| Metric | Meaning | Better (higher / lower) | Target | Owner |
|---|---|---|---|---|
| Backlog | | lower | | |
| First pass rate | | higher | | |
| AR days | | lower | | |
| Denial rate | | lower | | |
| (new) | | | | |

## 4. Tickets (rules/R6.yaml, CSM and CS lead)

| Question | Today (provisional) | Their answer |
|---|---|---|
| Alert when a ticket has no reply for… | 24 hours | |
| Different by priority? | no | |
| Escalate to | CS lead, after 8 more hours | |
| Who is the CS lead? | — | |

## 5. Their real questions (tests/golden, gate G9)

Write each question exactly as they said it, and the right answer if they know it. Aim for 20 per persona over the next week.

| # | Question (exact words) | Right answer / where it comes from | Did Athena answer? |
|---|---|---|---|
| 1 | | | |
| 2 | | | |
| 3 | | | |
| 4 | | | |
| 5 | | | |
| 6 | | | |
| 7 | | | |
| 8 | | | |
| 9 | | | |
| 10 | | | |

## 6. Anything else

- What would make them use it every day?
- What would make them turn it off?
- Which documents (SharePoint sites) should it search? (G4: IT must confirm the sites have no patient data.)
- BA only: the standard weekly report template (.pptx) and how each number is calculated (G7).
