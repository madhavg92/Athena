# Athena demo script

Goal: show a DM/AM, a hub leader and a CSM (and a BA for a minute) what Athena would do on a normal day, then get from them the values and questions Athena needs (gates G8 and G9).

Everything in the demo is synthetic: three made-up clients (Northwind Orthopedics, Bluefield Imaging, Cedar Family Clinic), made-up people (DM One, Hub Leader Key, ...), made-up numbers. Say so at the start.

## Before the session (10 minutes)

1. Open the demo page: https://claude.ai/artifact/1XT2xqcbKbQMmG4NTZ8SRy (it is private: share it from its Share menu if someone else will present).
2. Optional, for live questions: a laptop with the repo and `pip install -e ".[dev]"`. Check `athena ask "What is the backlog for Northwind Orthopedics?" --as dm.one@fixture.local` works.
3. Print or open `docs/DEMO_FEEDBACK.md`. One copy per person.

## Let people ask their own questions

Each tab on the page has an **Ask Athena** box. People type any question as that person (DM One, Hub Leader Key, CSM One, BA One), or tap a suggested one.

- **Live answers** (the page opened in Claude): Claude reads the synthetic data through Athena's six tools, as that person. The page's own code enforces what Athena's code enforces: only that person's clients and data sources, a Sources footer made by code, "I do not know" when no tool returned data, and "Data is not current" for old data. Each answer shows a "Checked:" line listing the tools used. The first question asks the viewer to allow the page to use their Claude account (it uses their usage).
- **Scripted answers** (Claude not available, e.g. a public link): the suggested questions still answer with Athena's scripted stand-in.

Good live questions to show the guard rails: one for a client outside the person's scope, one for data Athena does not have (NPS, collections, FTEs), and a pre-call brief.

Write down every question people type. Those are the real G9 questions.

## What to say first (1 minute)

> Athena is an assistant for managers. It reads Smartsheet, Supaboard, CS Hub and SharePoint, tells the right person in Teams when something needs action, and answers questions with the source of every number. It only reads; it never changes a system and never sends anything to a client. Today everything is made-up data. In the Ask box a real AI model answers, but only from Athena's tools and only for the person you picked. Judge what it does and when, and ask the questions you really ask.

## Session 1: DM/AM (20 minutes)

Page tab: **DM/AM**. Terminal user: `dm.one@fixture.local`.

| Time | Show | Point to make |
|---|---|---|
| 11:30 | Three alerts: two late tasks, one at risk | Code decides what is late, not the AI. Each alert has the task, due time, status and owner. |
| 11:40 | "Which tasks are late for Northwind?" | Every answer ends with its sources and how fresh the data is. |
| 11:42 | "What is the backlog for Northwind Orthopedics?" | Numbers come with the target. |
| 11:44 | "Show late tasks for Cedar Family Clinic" | DM One does not own Cedar, so Athena refuses. |
| 13:31 | Reminders, one per open alert | At most two messages per alert: the first, and one reminder after 2 hours. |

Live questions (terminal): let them ask in their own words.
```
athena ask "<their question>" --as dm.one@fixture.local
```
If the answer is "I do not know", say: that is the right answer when Athena has no data; the real model will also handle more ways of asking. Write the exact question on the feedback sheet either way.

Then the feedback questions (on the page under the timeline, and in `DEMO_FEEDBACK.md`).

## Session 2: Hub leader (20 minutes)

Page tab: **Hub leader**. Terminal user: `hl.key@fixture.local`.

| Time | Show | Point to make |
|---|---|---|
| 09:00 | The daily exception digest | One message a day, before the shift. If the data is old it says "Data is not current", never "all on target". |
| 09:05–09:09 | Two answers and one refusal | The hub leader sees only their hub. |
| 15:31 | Escalations | An alert still open after 4 hours goes to the hub leader. |

Show the stale-data case live (Cedar is in the other hub):
```
athena ask "What is the health score for Cedar Family Clinic?" --as hl.small@fixture.local
```
Then the feedback questions.

## Session 3: CSM (20 minutes)

Page tab: **CSM**. Terminal user: `csm.one@fixture.local`.

| Time | Show | Point to make |
|---|---|---|
| 17:30 | "Brief me on Northwind Orthopedics" | A pre-call brief in one message: health, tickets, metrics, tasks, documents, profile. |
| 17:35 | Escalation SOP search | Document search only covers approved SharePoint sites. |
| 17:37 | "What is the NPS?" | No NPS data, so it says "I do not know". It does not guess. |
| 18:30 | Tickets with no reply for 24 hours | A new alert added last week with configuration only (no code). Goes to the CS lead after 8 more hours. |

Then the feedback questions.

## Bonus: BA (5 minutes)

Page tab: **BA**. Show the 08:00 draft notice. Open a draft deck from a laptop:
```
athena tick --rule R5      # writes drafts/<client>-wbr-<week>.pptx
```
Point: every number is calculated in code with a query ID in the slide notes; the AI only writes the comments, and a comment with a number that is not in the table is thrown away. The BA reviews and sends; Athena never sends to clients. Ask for the real report template.

## Re-run the whole day

```
athena demo                       # all personas, in the terminal
athena demo --persona csm         # one persona
athena demo --json docs/demo/demo.json --html docs/demo/athena-demo.html   # rebuild the page data
```

## Questions people will ask

- **Is this live data?** No. Synthetic. Live needs the gates in `docs/BLOCKERS.md`.
- **Will it flood me?** Each alert sends at most 2 messages to a person. New alerts run in shadow for a week first; owners mark each one correct or wrong, and a rule with too many wrong alerts is turned down automatically.
- **Does the AI decide who gets an alert?** No. Rules in code decide; the AI only writes the wording, and a plain template is used if it fails.
- **Does it see patient data?** Connectors pass only approved fields and mask patient details before the model reads anything. No live data goes to a model until a model host is under a contract that covers it.
- **Can it update Smartsheet / reply to the client?** No. Read only, and nothing goes to clients.
