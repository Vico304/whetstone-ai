# Whetstone

> **Learning tools promise frictionless. Friction is the point.**

Whetstone is an LLM-powered learning system built on *desirable difficulties* — the well-replicated finding that strategies which make learning feel harder (retrieval practice, self-explanation, delayed reconstruction) are precisely the ones that produce durable, transferable understanding. Where most learning software optimizes for smoothness, Whetstone deliberately makes you reconstruct the knowledge structure yourself: explain concepts from memory, rebuild relations between them, and defend your reconstruction against the source material.

A whetstone sharpens a blade through friction. Nothing about the process is smooth — that is what makes it work.

**为什么叫 Whetstone（磨刀石）**：市面上的学习软件都在承诺"轻松学会"，但学习科学的结论恰恰相反——那些让学习过程变得费力的策略（主动回忆、自我解释、延迟重建），才是形成长期、可迁移理解的策略。刀不是靠泡在油里变锋利的，而是靠磨刀石的摩擦。这个项目的核心体验——读完材料后合上它，用自己的话重建整个知识框架——是艰难的，而这份艰难正是它有效的原因。

**[中文完整说明 →](README.zh-CN.md)**

## Status

**Research prototype.** The core teaching loop (source-grounded course generation → section-by-section active reconstruction → evidence-constrained feedback) is implemented and in daily personal use as a Codex plugin. The project's most original mechanism — dual-track comparison between a machine reference graph and the learner's reconstruction — is designed but **not yet validated**. The [consensus document](docs/consensus.md) lists twelve open research questions that must not be treated as settled.

## What's here

| Path | What it is |
|---|---|
| [`docs/`](docs/) | The design framework: project consensus, [a one-page synthesis of the core idea](docs/design.md), and an evidence review with effect sizes from the learning-science literature |
| [`plugin/`](plugin/) | A working skills plugin implementing the minimal teaching loop — one shared skill directory for Codex, Claude Code, and DeepSeek Harness |

The documentation is a first-class citizen of this repository, not an appendix. If you are building AI learning tools, the [consensus constraints](docs/consensus.md) and the [evidence review](docs/reviews/evidence-review.md) may be more useful to you than the code.

## Core design commitments

1. **Not a summarizer.** PDF → summary → flashcards is the failure mode this project exists to avoid. LLM output is a component, constrained by a knowledge model, a learner model, and a learning policy.
2. **Reconstruction from memory is the core learning act.** The learner explains concepts in their own words and rebuilds typed, directed relations between them — with the reference hidden. This is retrieval practice (g ≈ 0.5–0.6) combined with self-explanation (g ≈ 0.55), and it deliberately avoids the "copy-the-book concept mapping" that Karpicke & Blunt (2011) showed to be inferior.
3. **The machine reference is not the truth.** AI-generated structure is an auditable reference, not an answer key. Conflicts between the machine's reading and the learner's reconstruction are adjudicated against source evidence — either side can be wrong.
4. **Every important claim is traceable.** Five support types (`explicit / entailed / pedagogical_inference / external / unsupported`) are distinguished throughout; pedagogical inference is never dressed up as the author's claim.
5. **Uncertainty is a legal state.** "The source is ambiguous," "no evidence found," and "not yet decidable" are valid outputs. The system does not fabricate confidence to keep a graph tidy.

## Quick start

The same skill directory works in three hosts:

| Host | Install | Invoke |
|---|---|---|
| Codex | plugin via `.codex-plugin/` | `$guided-learning-tutor` |
| Claude Code | `claude --plugin-dir ./plugin` | `/guided-learning-tutor:guided-learning-tutor` or natural language |
| DeepSeek Harness | `cp -r plugin/skills/guided-learning-tutor ~/.agents/skills/` | `/guided-learning-tutor` |

```text
Use the guided-learning-tutor skill to learn these materials:
- /path/to/document.md
- /path/to/repository

I want to be able to explain the core design and apply it to new problems.
```

The plugin builds a problem-driven course (`problem → solution → new problem → next solution`), checks prerequisite gaps one question at a time, then teaches section by section: you predict before reading, explain from memory, rate your confidence, and get feedback that targets your weakest claim instead of showing the answer. See [`plugin/README.md`](plugin/README.md) for details.

Verify locally:

```bash
cd plugin && python3 -m unittest discover -s tests
```

No third-party dependencies — standard-library Python only.

## Roadmap

See [`docs/roadmap.md`](docs/roadmap.md). The next milestone is the first real run of the dual-track mechanism: structured capture of the learner's reconstruction, a comparator that classifies differences instead of scoring similarity, and a cross-course learner state keyed by concept.

## License

[Apache-2.0](LICENSE)
