# Whetstone
> A whetstone sharpens a blade. Blades don't get sharp by soaking in oil.

> *"I just love the feeling of knowledge flowing naturally into my brain."*　　　　　　　— said every clueless waste of a learner

Why does everyone now believe they can actually learn from a short video? Lectures at 2x speed, papers "read" via a 100-word AI summary, agents driven with nothing but "continue", "it errored", "just give me something that runs". Somewhere along the way we forgot that learning is supposed to be a scourging of the soul, a grinding of the mind, a mortification of the flesh. If you want effortless, why not sleep on the textbook and absorb it by osmosis? :)

This is the most user-hostile learning tool there is. Unless you also want to be Sisyphus pushing the boulder with me, I don't recommend it to anyone.

---

Decades of learning science converge on the same finding: techniques that make learning *feel* easier mostly damage long-term retention, and techniques that make retrieval *harder* mostly strengthen it. These are called desirable difficulties. Retrieval practice: meta-analytic g ≈ 0.5–0.6. Self-explanation: g ≈ 0.55. Rereading hovers near zero.

## What it is

An LLM-powered learning system. Give it books, documents, or a codebase; it converts the material into a `problem → solution → new problem → next solution` path, then makes you actively reconstruct, section by section:

- Predict before reading: "how would you solve this?"
- Close the material and explain concepts in your own words
- Rate your confidence before answering; feedback prioritizes exposing "confident but wrong"
- Follow-ups target the weakest claim in your actual answer, not a question bank
- On resume, a transfer-variant question checks whether last session's understanding survived

Feedback is evidence-constrained: every claim in the machine reference carries a source locator and a support type (`explicit / entailed / external / pedagogical_inference / unsupported`). Within trusted domains (vetted textbooks, web-verified CS material) the reference is treated as the ruler; you can challenge any of it and the system shows its evidence.

Two things the system deliberately withholds:

- **The higher layers of the reference.** Knowledge is modelled in four layers — `fact`, `mechanism`, `rationale`, `principle`. You can read and query the first two. The "why was it designed this way" and "what is the transferable idea" layers are never shown; they exist only to generate questions and to judge how deep your own answer went. A summary of the essence, once shown, is just another thing to memorise.
- **Your own reconstruction log.** Every attempt is appended, never edited, never displayed. Your past wrong claims come back later as anonymous propositions to critique — the error is yours, the embarrassment isn't.

**Status: research prototype.** The core teaching loop is implemented and in daily personal use. The v2 design — a persistent knowledge store with a layered machine reference graph, an append-only learner log, a cross-course concept registry with freshness-aware mastery, and a discipline-tree visualisation — is **implemented as an opt-in store (P0 complete, 2026-09-05) but not yet validated on a real course**. See [`docs/specs/`](docs/specs/) for the specs and [`docs/roadmap.md`](docs/roadmap.md) for what remains (visualisation export, challenge log, staged build pipeline). The [consensus document](docs/consensus.md) lists eighteen open research questions that must not be treated as settled.

**[中文说明 →](README.zh-CN.md)**

## Repository layout

| Path | What it is |
|---|---|
| [`docs/user-guide.md`](docs/user-guide.md) | **User manual** (Chinese): install, directory layout, a full course walkthrough with example dialogues, knowledge store, troubleshooting |
| [`docs/design.md`](docs/design.md) | One-page synthesis of the core idea |
| [`docs/consensus.md`](docs/consensus.md) | Normative baseline (v2); the authority when rules conflict |
| [`docs/learning-layers.md`](docs/learning-layers.md) | The four layers of understanding and why the system withholds the top two |
| [`docs/specs/knowledge-store.md`](docs/specs/knowledge-store.md) | Persistent store spec: MRG / LRG / concept index / learner state / exports (schema 1.1) |
| [`docs/specs/protocol-architecture.md`](docs/specs/protocol-architecture.md) | Staged protocol loading, build pipeline, model tiering, eval set |
| [`docs/specs/course-planning.md`](docs/specs/course-planning.md) | Outline-first build, per-unit documents, full/fast mode, concept roles, coverage ledger (schema 1.2) |
| [`docs/specs/domain-skeleton.md`](docs/specs/domain-skeleton.md) | Learning orientation (material / domain), skeleton courses grounded in an evidence pool, principle probes, learner-chosen branches (schema 1.3) |
| [`docs/roadmap.md`](docs/roadmap.md) | Current coverage and next milestone |
| [`docs/reviews/`](docs/reviews/) | Learning-science evidence review, with effect sizes and sources |
| [`plugin/`](plugin/) | Working skills plugin; one skill directory, three hosts |

Documentation is a first-class citizen here. If you build AI learning tools, the [consensus constraints](docs/consensus.md) and the [evidence review](docs/reviews/evidence-review.md) may be worth more to you than the code.

## Install

Full manual with examples: [`docs/user-guide.md`](docs/user-guide.md) (Chinese). One skill directory, four hosts:

| Host | Install | Invoke |
|---|---|---|
| Claude Code (CLI) | `claude plugin marketplace add /path/to/whetstone-ai && claude plugin install whetstone@whetstone-ai` (or ad hoc: `claude --plugin-dir ./plugin`) | `/whetstone:learn` … |
| Claude Desktop | build `../dist/whetstone.plugin` with `python3 package_plugin.py` and upload it in the plugin manager; or `./install_skills.sh ~/.claude/skills` | `/learn` … |
| DeepSeek Harness | `./install_skills.sh ~/.agents/skills` (global) or `./install_skills.sh <project>/.agents/skills`; restart `npx @deepseek-ai/dsh web` | `/learn` … |
| Codex | install `plugin/` as a plugin (ships `.codex-plugin/`) | `$learn` … |

Type `/` in a session and you should see `guide / outline / learn / clarify` (descriptions are in Chinese — the skills teach in Chinese). Everything the system writes goes under `whetstone/` inside your materials directory (profile, plan, survey, `courses/`, optional store); the materials themselves are never written to.

## The four skills

| Skill | What it does | When |
|---|---|---|
| **learn** | Main entry. Fills in whatever is missing (profile → material triage → course-by-course confirmed plan → this course's outline), then builds one document per unit, diagnoses prerequisites (skeleton courses run a principle probe instead) and tutors section by section | Start or resume a course |
| **guide** | Wizard. Always asks first: tour or plan? Planning = learner profile + material triage (A primary / B authored-and-verified / C generated intermediate / D noise) + a plan confirmed course by course. Plans only; never builds | First time; a messy directory; changing goals or the plan |
| **outline** | Generate, discuss or revise one course's outline (problem chain, every concept with its role, coverage ledger, mode); writes back after confirmation. No units, no teaching | "Show me the outline", "split section 3", "promote this concept to core", "switch to fast mode" |
| **clarify** | Turns `[[wikilinks]]` you leave in the pack into source-grounded, example-rich concept notes (Obsidian-compatible) | You hit a concept you don't understand |

Two orthogonal choices are made while planning: **mode** `full` (every unit: predict → reconstruct → follow-up) / `fast` (narrower scope, tolerated vagueness, discounted evidence); **orientation** `material` (learn these materials, coverage ledger heading by heading) / `domain` (first a *skeleton course* of basic principles with the materials as an evidence pool, then learner-chosen branches from a candidate table, each becoming an ordinary course).

### Case 1: one spec, start directly (material orientation)

```text
/whetstone:learn learn src/threatmodel.adoc, course directory whetstone/courses/c2-threatmodel/.
Afterwards I want to state the adversary model by category and map each threat to an architectural mechanism.
```

It reads the material → produces the outline and **stops** for your confirmation (mode; units to skip or deepen) → generates `units/s01.md …` one at a time → diagnoses prerequisites one question at a time → tutors. The coverage ledger is checked against every heading of the real source, so omissions fail validation — which is why details like page faults and timer interrupts in the CoVE spec no longer get squeezed into one line. To resume, open a new session and say "resume my course".

### Case 2: a directory with 3 repositories and a dozen AI-generated documents (domain orientation)

```text
/whetstone:guide
→ Plan. Directory ~/Project/tee; I want to rebuild my understanding of confidential computing, not just learn Occlum.
```

The wizard records the profile (orientation = domain), surveys and grades the directory: upstream repos and official docs are the A-level evidence pool, your own verified design docs are B-level and reserved for branch courses, session summaries and handoffs are C-level and **never sources**, logs are D-level and excluded. The plan is one skeleton course plus a branch-candidate table. In the skeleton outline every concept carries its **anchor** in your materials (e.g. `occlum/docs/fs_overview.md · ## SEFS`); the validator prints the grounding ratio but sets no threshold — you judge whether it drifted. After confirmation a **probe round** runs (one no-hint principle question per unit; you decide whether passed units are skipped), and at the end you pick branches.

### Case 3: just revise the outline

```text
/whetstone:outline whetstone/courses/c3-refarch/ split section 5 in two and promote "interrupt and exception delegation" to core
```

It re-validates, asks for confirmation again, and marks affected unit documents for regeneration on the next `learn`.

### Case 4: an unfamiliar concept mid-course

Write `[[G-stage page table]]` in any unit document, or drop it into `whetstone/courses/<id>/concepts/_inbox.md`, then `/whetstone:clarify`. Each concept gets a note: the problem it solves, mechanism, two examples, boundaries and misconceptions, links to related concepts and back to its unit. Open `whetstone/` in Obsidian and the wikilinks and graph just work.

Section too shallow? Before answering its main question say "deepen this section" — it writes a `zoom/` document and returns you to the question. Deepening prepares for the check; it never replaces it.

### Optional: the knowledge store

Name a persistent directory in the profile and courses accumulate across time: a layered machine reference graph (MRG; upper layers never shown) and your append-only, invisible learner log (LRG). The next course replaces diagnosis with variant questions for concepts you already hold, fast-mode evidence is discounted, and past errors come back de-personalised as anonymous propositions for review. See [`docs/specs/knowledge-store.md`](docs/specs/knowledge-store.md).

Verify locally:

```bash
cd plugin && python3 -m unittest discover -s tests
```

Standard-library Python only, no third-party dependencies.

## License

[Apache-2.0](LICENSE)
