# 阶段一、二：最小前置地图与无提示诊断

## 阶段一：建立最小前置地图

1. 先读取足以识别主题、边界和关键推理的原材料，不先用外部资料替代原文分析。
2. 对每个候选前置项记录：名称、为何是前置、它支撑哪一段主线、材料位置、当前确定性。
3. 按相互依赖的概念簇组织，不用大量孤立术语考察。
4. 用 `assets/prerequisite-plan-template.json` 写 `prerequisite-plan.json`，运行 `scripts/validate_prerequisites.py`。

前置地图是组织诊断的机器参考，不是对学习者的判决，也不是标准答案。

## 开启知识库时：先查掌握状态

提出任何诊断问题之前运行：

```bash
python3 scripts/index_match.py prerequisites --store <工作区>/store --lesson-id <本课 lesson_id> --prerequisite-plan path/to/prerequisite-plan.json
```

按每项返回的 `action` 处理：

| `action` | 学习者状态 | 处理 |
|---|---|---|
| `variant` | `fresh`；或 `via_prerequisite_course` 非空——这个概念是在本课的前置课里学的 | **一道变式题代替诊断**：换情境或角度考同一机制，不复用原 `diagnostic.prompt`。答对即 `ready`，答错进正常诊断 |
| `variant_then_diagnose` | `stale` | 先变式题，答错走正常诊断 |
| `diagnose` | `unknown` | 正常诊断 |

`ambiguous = true` 的项先向学习者确认是不是同一概念。变式题作答记 `lrg_record.py append --kind variant`，同时 `prerequisite_state.py record` 记 verdict。替代不是跳过：`fresh` 也要答一题。

## 阶段二：无提示、自适应诊断

1. 简短说明将评估哪些"针对当前材料的准备能力"，允许学习者回答"不知道"或跳过。
2. 一次只问一个主问题。提问后交还对话，不同时给参考答案或检索补充。
3. 问题优先暴露：能否用自己的话生成概念而不只是识别名称；能否说明边界、反例或失效条件；能否说明概念之间的关系、方向和理由；能否应用到一个简单的新情境。
4. 不用文本相似度判分。对每个簇记 `ready | fragile | gap | misconception | skipped`，单独记判断置信度；非 `ready` 的簇再记依赖类型 `dependency_kind`：`def` 缺的是定义或约定，`mech` 缺的是机制，`tool` 缺的是表征或操作。
5. 证据够就停，不为凑题数继续。
6. `scripts/prerequisite_state.py` 追加原始回答与修订，生成 `prerequisite-progress.json`；不用后续回答覆盖首次证据。开启知识库时每次诊断作答同时 `lrg_record.py append --kind diagnostic --concept <id>`（即时证据，不加 `--progress`）。

只说"这个簇对本材料尚未就绪"，不说"学习者基础差"之类的概括。

诊断结束：全部 `ready | skipped` → 直接进正课；有任何 `fragile | gap | misconception` → [course.md](course.md)。学习者在大纲确认时自述不懂的概念，视为已诊断为 `gap`，不必再问。
