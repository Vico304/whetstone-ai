# Whetstone
> A whetstone sharpens a blade. Blades don't get sharp by soaking in oil.

> *"I just love the feeling of knowledge flowing naturally into my brain."*　　　　　　　— said every clueless waste of a learner

Why does everyone now believe they can actually learn from a short video? Lectures at 2x speed, papers "read" via a 100-word AI summary, agents driven with nothing but "continue", "it errored", "just give me something that runs". Somewhere along the way we forgot that learning is supposed to be a scourging of the soul, a grinding of the mind, a mortification of the flesh. If you want effortless, why not sleep on the textbook and absorb it by osmosis? :)

This is the most user-hostile learning tool there is. Unless you also want to be Sisyphus pushing the boulder with me, I don't recommend it to anyone.

---

This is the short English version. The full documentation is in Chinese: **[中文说明 →](README.zh-CN.md)**. The skills teach in Chinese.

## What it is

A learning tool that runs inside Claude Code, Claude Desktop, Codex, DeepSeek Harness or pi. Give it a book, a document or a codebase; it rearranges the material into a `problem → solution → new problem` path and then, section by section, makes you:

- predict the solution before reading it;
- close the material and explain the section in your own words;
- rate your confidence before answering, so feedback can start with "confident but wrong";
- answer a follow-up aimed at the weakest point of your actual answer;
- on your next session, answer a variant question first to check what survived.

Decades of learning science point the same way: methods that make learning *feel* easy mostly hurt long-term retention; methods that make recall *harder* mostly strengthen it. Retrieval practice g ≈ 0.5–0.6, self-explanation g ≈ 0.55, rereading near zero (sources in [`docs/evidence.md`](docs/evidence.md)). This tool sits on the effortful side.

Two things it deliberately withholds:

- **The top two of the four layers.** Fact and mechanism go into the lesson text. Rationale and principle — why it was designed this way, what the transferable idea is — are never shown; they only generate questions and judge how deep your answer went. An essence, once summarised for you, is just another thing to memorise.
- **Your own learning log.** Every attempt is appended, never edited, never shown. With the optional store, your past wrong claims come back anonymised for you to critique.

## Install

One skill directory, five hosts:

| Host | Install | Invoke |
|---|---|---|
| Claude Code | `claude plugin marketplace add /path/to/whetstone-ai && claude plugin install whetstone@whetstone-ai`, or ad hoc `claude --plugin-dir ./plugin` | `/whetstone:learn` … |
| Claude Desktop | `python3 package_plugin.py` builds `../dist/whetstone.plugin`; upload it in the plugin manager. Or `./install_skills.sh ~/.claude/skills` | `/learn` … |
| DeepSeek Harness | `./install_skills.sh ~/.agents/skills`, then restart `npx @deepseek-ai/dsh web` | `/learn` … |
| pi | `pi install git:github.com/Vico304/whetstone-ai` (or a local checkout: `pi install /path/to/whetstone-ai`, or `./install_skills.sh ~/.pi/agent/skills`) | `/skill:learn` … |
| Codex | install `plugin/` as a plugin | `$learn` … |

Type `/` and you should see `guide / outline / learn / clarify`. Everything the tool writes goes under `whetstone/` inside your materials directory; the materials themselves are never modified.

## The four skills

| Skill | What it does |
|---|---|
| **learn** | Main entry. Fills in whatever is missing (your profile, a survey of the materials, a course-by-course plan, this course's outline), then generates one lesson document per section, checks prerequisites and tutors section by section |
| **guide** | Wizard. Asks whether you want a tour or a plan; planning records your background and goals, surveys a directory of materials, and confirms the course sequence one course at a time. Plans only |
| **outline** | Generate, discuss or revise one course's outline; writes it back after you confirm |
| **clarify** | Turns `[[wikilinks]]` you leave in the lesson documents into source-grounded, example-rich concept notes (Obsidian-compatible) |

Two choices are made while planning: **full** or **fast** (fast narrows the scope and relaxes judging, but still predicts before revealing); **by material** or **by domain** (by domain starts with a skeleton course of basic principles, with your materials as examples, and you pick branches to go deeper afterwards).

## Status

1.0, in daily use. The knowledge store is optional and has no long-term usage data yet.

```bash
cd plugin && python3 -m unittest discover -s tests
```

Standard-library Python only, no third-party dependencies.

## License

[Apache-2.0](LICENSE)
