# Evals

任何提示词、协议切分或管线改动，都要能在同一组材料上看到指标变化；看不到就不改（`docs/specs/protocol.md` §5）。这里不追求绝对值，追求**改动前后可比**。

## 材料

`materials.json` 列出三份来自本仓库的小材料（教材式文档、小代码库、评审式长文），各带学习目标与结构期望（节数范围、每节概念上限、最少关系数）。用被测技能把每份材料 build 成课程目录，放到 `results/<run-id>/<material-id>/`。

## 打分

```bash
# build 指标（结构、支持类型、层分布、引文定位命中率、泄漏检查）
python3 evals/score_pack.py results/<run>/doc-learning-layers \
  --sources-root .. --material-id doc-learning-layers \
  --output results/<run>/doc-learning-layers.json

# 加上 teach 指标（需要用知识库模式教过这个课程目录）
python3 evals/score_pack.py results/<run>/doc-learning-layers \
  --sources-root .. --store <知识库目录> \
  --baseline results/<prev>/doc-learning-layers.json
```

`--baseline` 逐项打印数值差异。

结果里另有六项形态信号，只记录、不设阈值、不进错误与警告：`prompt_questions_per_section`（主问题题面的问号数）与 `checklist_prompt_sections`（问号不少于判定标准条数的节，题面把判定标准逐条问了出来）；`criteria_incl_checks_per_section`（主问题加本节各概念 `check` 的判定标准条数）；`intra_section_relation_depth`（两端都在本节的 `relations` 最长链，≥ 2 是一节装了两个中心机制、可拆节的信号）；`final_core_coverage`（`final_challenge` 文字里出现核心概念名或别名的节数 / 有核心概念的节数，逐字匹配，换说法就漏计）；`units_turn_block_close`（`units/` 下「轮到你」一节写了「合上」的文件数，没有 `units/` 时为 `null`）。来由是 2026-10-01 对第一门由 DeepSeek 建的课的复核。`validator_warnings` 与 `validate_lesson.py` 命令行的计数一致，含 schema 1.6 的警告。

一条命令给 `evals/` 与 `examples/` 下全部课程目录（含 `lesson-plan.json` 的目录）打分，一目录一行：

```bash
python3 evals/score_all.py                      # 默认根目录：evals/ 与 examples/
python3 evals/score_all.py skills/learn/assets --output-dir /tmp/scores
python3 evals/score_all.py --baseline-dir /tmp/scores --output-dir /tmp/scores   # 与上次比较后覆盖
```

状态三种：`ok`（无校验错误，期望满足）、`fail`（有校验错误或 `materials.json` 的期望未满足，目录名等于材料 id 时才核对期望）、`skipped`（不能打分，备注写原因：没有 `lesson-plan.json`、JSON 坏了等）。全部 `ok` 退出 0，有 `fail` 或 `skipped` 退出 1，根目录不存在或一个课程目录都没找到退出 2。`--output-dir` 每个目录写一份与 `score_pack.py --output` 同格式的结果，可作下次的 `--baseline`；`--sources-root`、`--store` 与 `score_pack.py` 同义。

`--baseline-dir` 在表后逐目录与上次 `--output-dir` 写出的同名文件比较，差异按 `score_pack.py --baseline` 的格式列出，末行汇总 `no change / changed / no baseline / bad` 各几个。没有同名文件记 `no baseline`，不算失败；文件读不了、不是 JSON 或根不是对象时在 stderr 打 `ERROR: bad baseline …`，退出 1；目录本身不存在退出 2。数值有差异不影响退出码。先读完比较用的文件再写结果，所以两个选项可以指向同一目录。还没建成课程目录的材料列在表后。`results/example-baseline.json` 是对 `examples/project-consensus` 的一次打分，作为输出格式样例；来源是冻结在 `examples/project-consensus/source/` 里的 v1 共识文本，所以定位可以被脚本核对。

## 重建难度

给课程补前置内容（或重新生成大纲）之后，每节主问题要求学习者重建的内容不能变少。`difficulty_digest.py` 记下每节主问题的判定标准条数、各层条数、`core` 概念、题面与每条判定标准的摘要，骨架课的 `probe`、`supporting` 概念的 `check` 与 `final_challenge` 同样处理：

```bash
python3 evals/difficulty_digest.py <课程目录>/lesson-plan.json --output before.json
python3 evals/difficulty_digest.py <课程目录>/lesson-plan.json --against before.json
```

`--against` 逐条列出变少的项（`REDUCED`：节或检查被删、判定标准变少、某一层变少、`core` 概念被移走、题面或某条判定标准的文字变了）与新增的项（`ADDED`，允许）；有变少退出 1，没有退出 0，文件读不了退出 2。`score_pack.py` 的结果里有对应的四项，`--baseline` 能直接比较：`criteria_layers_per_section`、`checkpoint_digest`（每节一个数，题面或判定标准文字一变就变）、`bridge_items_per_section`、`bridge_share`（后两项计 `role: bridge` 概念与带 `bridge_for` 的节，现行 schema 没有这两个字段，所以都是 0；没有 `units/` 时 `bridge_share` 是 `null`）。

## 用托管模型建课

`deepseek_build.py` 扮演宿主，让一个经 HTTP 调用的模型运行 `learn` 技能，建到大纲呈现处停下，不进入教学：

```bash
python3 evals/deepseek_build.py --case <用例>.json --out-dir <仓库外目录> --dry-run   # 只估算用量，不发请求
python3 evals/deepseek_build.py --case <用例>.json --out-dir <仓库外目录> --max-total-tokens 630000
python3 evals/deepseek_build.py --material-id doc-learning-layers --out-dir <仓库外目录>
```

用例文件给 `id`、`materials_root`、`materials[]`（相对路径）、`request`（第一句话），可选 `profile`（复制成工作区的 `learner-profile.md`）、`auto_reply`（模型问学习者时的固定回答，默认"你定，按默认值继续。"）、`max_auto_replies`（默认 3）、`stop_after`（`outline` 默认；`prerequisites` 时大纲处回一次 `outline_reply`，之后照常回固定回答，一直跑到有能解析的 `prerequisite-plan.json`）。脚本把技能与材料复制进 `<out-dir>/ws/w<用例 id 的 sha256 前 8 位>/`（目录名中性，模型看到的路径里没有用例 id；`ledger.json` 的 `sandbox` 记它在哪；材料去掉各路径共有的前导目录再放进 `materials/`），模型只有五个工具：列目录、读文件、写文件、按原文替换一处（技能与材料只读）、运行技能的 `scripts/*.py` 与 `date`，路径不能出沙盒，子进程不继承环境变量。同一文件被之后的整份重写取代后，旧的写文件内容在后续请求里换成一行省略说明，`ledger.json` 的 `superseded_chars_dropped` 记省掉的字符数。停止条件：沙盒里有能解析的 `lesson-plan.json`、同目录有 `outline.md`（`stop_after: prerequisites` 时改为有能解析的 `prerequisite-plan.json`），且模型把回合交还学习者（退出 0）；下一次请求可能超过 `--max-total-tokens`（输入加输出）、请求数到 `--max-requests`、固定回答用完或模型调用失败（退出 1）。账目与对话写在 `<out-dir>/<id>/`，同一 id 再跑不覆盖（退出 2）。`ledger.json` 逐次记输入、输出、缓存命中、缓存未命中 token 与按 `--price` 折算的金额，`transcript.jsonl`、`messages.json` 是原始对话。

系统提示里的宿主说明写明两件事：技能脚本按协议写法运行、用法不清看 `--help`，不必读 `scripts/` 的源码；`lesson-plan.json` 这类大文件一开始就分块写（每次不超过约 12000 字符，之后 `append=true`）。起因是 2026-09 的第一次校准：模型读了 `validate_lesson.py` 源码，约 1.5 万 token 此后每次请求都带着；又想一次写完 `lesson-plan.json`，被输出上限截断作废一次。

`--max-output-tokens` 默认 16384（思考加正文）：2026-09-30 的重跑里两次截断都是思考吃满 8192。被截断的回复如果既没有正文也没有工具调用，就不放进后续请求的上下文（`transcript.jsonl` 照记），改发一句提示：先把节骨架写进文件，再逐节补细节；`ledger.json` 每次请求另记 `reasoning_chars`（思考字符数）、`reasoning_tokens`（接口回报的思考 token）与 `in_context`。

密钥只从环境变量 `DEEPSEEK_API_KEY` 读，不打印、不写盘。模型调用在 `ModelClient.complete` 之后：`DeepSeekClient` 连 `api.deepseek.com`，`--replies` 用 `ScriptedClient` 回放写好的回复；换成别的服务只需另写一个实现。

## 前置检查样例

`prerequisites/` 放着 `examples/project-consensus` 的一份前置计划与一份前置作答记录，让前置检查的两个脚本也在同一份材料上可复核：

```bash
python3 skills/learn/scripts/validate_prerequisites.py evals/prerequisites/prerequisite-plan.json \
  --manifest examples/project-consensus/sources.json
python3 skills/learn/scripts/prerequisite_state.py show --state evals/prerequisites/prerequisite-progress.json
```

作答记录由 `prerequisite_state.py` 按计划逐条写出（一簇 `ready`；一簇 `gap` 后回程复测 `ready`），测试会按事件顺序重放并比对。

## 指标含义

| 指标 | 关注什么 |
|---|---|
| `validator_errors / warnings` | 结构契约是否被遵守；warnings 含认知负担与 rationale 层泄漏提示 |
| `sections`、`max_concepts_per_section` | 课程规模是否落在期望区间（新概念 ≤ 4） |
| `support`、`unsupported_ratio`、`pedagogical_inference_ratio` | 证据质量；教学推断占比过高说明抽取在编关系 |
| `relations`、`layers` | 1.1 的图是否真的被填了；层标注分布是否合理（全是 mechanism 说明没标） |
| `locator_hit_rate` | 引文定位是否真的能在来源文件里找到——最便宜的"MRG 抽取忠实度"代理 |
| `median_checkpoint_elapsed_s` | **交互成本**。结构化记录前后对比，阈值 +30% |
| `depths`、`conflicts_per_attempt`、`high_confidence_conflict_share` | 教学是否把学习者推到了更高层；高信心冲突是否被识别 |

## 尚未自动化

teach 侧的"一次回复只推进一个状态""首次重建前不出现 criteria 文本""追问是否引用了回答内容"需要对话回放，目前靠人工抽查；`depth_reached` 与人工判定的一致率也是人工。宿主提供 eval 框架（如 skill-creator）时优先接入。
