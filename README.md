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
| [`docs/design.md`](docs/design.md) | One-page synthesis of the core idea |
| [`docs/consensus.md`](docs/consensus.md) | Normative baseline (v2); the authority when rules conflict |
| [`docs/learning-layers.md`](docs/learning-layers.md) | The four layers of understanding and why the system withholds the top two |
| [`docs/specs/knowledge-store.md`](docs/specs/knowledge-store.md) | Persistent store spec: MRG / LRG / concept index / learner state / exports (schema 1.1) |
| [`docs/specs/protocol-architecture.md`](docs/specs/protocol-architecture.md) | Staged protocol loading, build pipeline, model tiering, eval set |
| [`docs/roadmap.md`](docs/roadmap.md) | Current coverage and next milestone |
| [`docs/reviews/`](docs/reviews/) | Learning-science evidence review, with effect sizes and sources |
| [`plugin/`](plugin/) | Working skills plugin; one skill directory, three hosts |

Documentation is a first-class citizen here. If you build AI learning tools, the [consensus constraints](docs/consensus.md) and the [evidence review](docs/reviews/evidence-review.md) may be worth more to you than the code.

## Install

One skill directory, three hosts:

| Host | Install | Invoke |
|---|---|---|
| Codex | install `plugin/` as a plugin (ships `.codex-plugin/`) | `$guided-learning-tutor` |
| Claude Code (CLI) | `claude --plugin-dir ./plugin`, or `claude plugin marketplace add . && claude plugin install guided-learning-tutor@whetstone` | `/guided-learning-tutor:guided-learning-tutor` |
| Claude Desktop (Code tab) | install via the CLI above (shared config), or copy `plugin/skills/*` into `~/.claude/skills/` | `/guided-learning-tutor` |
| DeepSeek Harness | `cp -r plugin/skills/* ~/.agents/skills/` | `/guided-learning-tutor` |

## Use

Start a course:

```text
Use the guided-learning-tutor skill to learn these materials:
- /path/to/document.md
- /path/to/repository

I want to be able to explain the core design and apply it to new problems.
```

It analyzes the material, diagnoses prerequisite gaps (one question at a time), researches cited supplements where needed, then generates and teaches the course section by section. To resume after a break, open a new session and say "resume my course" — progress lives in the lesson pack's JSON files.

Hit an unfamiliar concept? Write `[[concept-name]]` anywhere in the lesson pack, or drop it into `concepts/_inbox.md`, then invoke `clarify` (`$clarify` in Codex). It scans unresolved links and writes one source-grounded note per concept — what problem it solves, mechanism, two examples, boundaries and common misconceptions, cross-links to related concepts and back to the teaching guide. Open the lesson pack in Obsidian and the wikilinks and graph just work.

Section too shallow? Before answering its main question, say "deepen this section" — it generates a `zoom/` document covering the section's internal concepts in more detail, then returns you to the main question. Deepening prepares for the check; it never replaces it.

Verify locally:

```bash
cd plugin && python3 -m unittest discover -s tests
```

Standard-library Python only, no third-party dependencies.

## License

[Apache-2.0](LICENSE)
