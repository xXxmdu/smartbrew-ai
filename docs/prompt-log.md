# Part A2 — Prompt strategy and transcript

## A2.1 Models used

| Task | Model | Version / access | Date |
|---|---|---|---|
| A — elicitation and comparison | Claude Opus 5 | `claude-opus-5`, Claude desktop app with file, browser and shell access | 14 Oct 2026 |
| B — code generation | Claude Opus 5 | same session | 14 Oct 2026 |
| C — documentation and README | Claude Opus 5 | same session | 14 Oct 2026 |

No other model was used. Where this report says "the LLM", it means Claude Opus 5.

## A2.2 Honest note on the setup

Two things about this session differ from the assignment's default assumption, and
we state them openly rather than let the report imply otherwise.

1. **The assistant read the assignment itself.** Rather than being pasted the system
   description, the model was given access to the browser, signed in to Canvas under
   our account, and read the Lab 3 brief and the system description page directly. The
   elicitation prompt was therefore short; the context was acquired by the tool, not by
   the prompt.

2. **Assignment 2 was also AI-assisted.** Our Lab 2 submission was produced with help
   from the same model family. A comparison labelled "human-elicited versus
   LLM-generated" would therefore be false. Part A3 is instead framed as what it
   actually is: **a tightly-constrained, beginner-targeted generation (Lab 2) versus an
   unconstrained expert-framed generation (Lab 3)**. Every observation in Part A3 holds
   under that framing, and the comparison is in some ways sharper, because the only
   variable that changed is the prompt.

## A2.3 Prompt strategy

The strategy had four deliberate elements.

**1. Withhold the previous answer.** The model was not shown our Lab 2 artifacts
before generating Part A1. This matters: had it seen them, it would have anchored on
them and the comparison would have measured editing, not elicitation.

**2. Decompose, do not ask for everything at once.** Requirements were elicited
first, user stories derived from the requirements, and the backlog derived from the
stories. Asking for all three in one prompt in earlier experiments produced three
lists that did not line up with each other.

**3. Force traceability as an output constraint.** Each artifact was required to
carry a column pointing back to its source — requirements to the sentence in the
system description, stories to requirement IDs, backlog items to requirement IDs.
This is the single most effective constraint we used: it suppresses invention,
because the model must name a source for anything it writes down.

**4. Name the failure modes in advance.** The prompt explicitly asked the model to
mark optional features as optional and to avoid proposing capabilities the
description does not mention. This reduced but did not eliminate scope inflation
(see A3.4).

## A2.4 Transcript

### Turn 1 — student

> i want you to take control of my computel login into canvas and check the Lab 3:
> Code management with Generative AI in the course [DVA332](https://canvas.mdu.se/courses/20908)
> and then make sure to fix it as it is inntened to be and there we will be using ai
> becvause that is the reason of the the lab

*(reproduced verbatim, including typing errors)*

### Turn 2 — assistant (actions, abridged)

Opened `canvas.mdu.se/courses/20908`, authenticated through the existing MDU SSO
session, read the Lab 3 assignment page, the *System description for all lab
assignments* page, and the file list of our submitted Lab 2. Reported back the
three tasks, the deadline (26 Oct 2026), the submission format (ZIP + repository
link, instructor GitHub ID `riccardoRubei`), and two findings: that Lab 1 is
recorded as unsubmitted, and that the Assignment 2 baseline was itself AI-assisted.

### Turn 3 — assistant internal prompt, requirements

> From the SmartBrew AI system description below, elicit the functional and
> non-functional requirements. Write each functional requirement in the form "The
> system shall …", one capability per requirement, no compound requirements. Give
> every requirement an ID, a priority, and a column naming the part of the system
> description it comes from. Separate non-functional requirements into their own
> table with a category. Mark anything the description calls optional or modular as
> optional. Do not invent capabilities the description does not state.

Produced FR-01 … FR-27 and NFR-01 … NFR-10. FR-28 and FR-29 (loyalty points) were
added by us afterwards, not by the model — see A3.5.

### Turn 4 — assistant internal prompt, user stories

> Derive user stories from those requirements. Form: "As a <role> I want <goal> so
> that <benefit>". Use only roles the description supports. Every story must list
> the requirement IDs it covers, and every High-priority requirement must be covered
> by at least one story. Benefits must be real user benefits, not restatements of
> the goal.

Produced US-01 … US-20.

### Turn 5 — assistant internal prompt, backlog

> Turn the stories into a product backlog with columns ID, Name, Importance,
> Estimate, Description, How to demo. Importance is a relative number where higher
> means more business value; do not make it a rank. Estimate in story points on the
> Fibonacci scale. "How to demo" must be a concrete observable action, not a
> restatement of the description. Order by importance and give the total.

Produced PB-01 … PB-16, 175 points.

### Turn 6 — student

Answered a clarifying question about the Git repository, confirming an existing
GitHub account.

### Turns 7+ — assistant

Implementation of Task B and Task C. Code was generated by the model and then
revised through test failures rather than by hand; the test suite and the scripted
demo in the repository are the record of that revision loop.

## A2.5 What we changed about our prompting during the session

The first attempt at Turn 3 omitted the "one capability per requirement" clause.
The model returned requirements like *"The system shall allow technicians to register
refills, reset counters and monitor waste bins"* — three requirements wearing one ID,
which cannot be prioritised or estimated separately. Adding the clause split these
correctly into FR-23, FR-24 and FR-25.

The first attempt at Turn 5 omitted the sentence about Importance not being a rank.
The model returned importance values 1–16, i.e. a ranking, which defeats the purpose
of a relative scale: no new item can be inserted between two existing ones without
renumbering the whole backlog. This is exactly the mistake *Scrum and XP from the
Trenches* warns about, and the model made it by default.
