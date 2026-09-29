# 命令行坏输入契约

26 个脚本在坏输入下的现行行为：消息的首行前缀、消息所在的流、退出码。给调用这些脚本的模型与维护者对照。本文记录的是代码现在的行为，不表示它是对的；要改其中任何一条，先改 `plugin/tests/test_cli.py` 里对应的行，再改脚本。

脚本位置：`plugin/skills/learn/scripts/` 下 21 个；`scan_wikilinks.py` 在 `plugin/skills/clarify/scripts/`；`score_pack.py`、`score_all.py`、`difficulty_digest.py`、`gap_ledger.py` 在 `plugin/evals/`。

## 1. 共同约定

- 坏输入时不打印 `Traceback`。脚本的 `main()` 捕获读文件与解析的异常，打印一行 `ERROR: <原因>`，返回下表的退出码。
- 消息只走一个流，另一个流为空。`test_cli.py` 对第 3 节的每一行都检查这三件事：没有 `Traceback`、退出码相符、另一个流为空，并检查首行前缀。
- 原因部分是异常原文，不是固定措辞：文件不存在是 `[Errno 2] No such file or directory: …`，非 JSON 是 `json` 模块的解析错误，JSON 根为数组时是 `… root must be an object`。调用方只应依赖前缀、流与退出码。
- 参数错误由 `argparse` 处理：用法说明与 `error:` 行打到 `stderr`，首行前缀是 `usage:`，退出 2。所有脚本相同，第 3 节不再逐个列出。

## 2. 每个脚本

"读坏文件"指给的文件或目录不存在、不是合法 JSON、或 JSON 根不是对象。

| 脚本 | `ERROR:` 所在流 | 读坏文件 | 其他退出码 |
|---|---|---|---|
| `validate_lesson` | `stdout` | 2；根为数组时 1 | 1 校验不通过；0 通过 |
| `validate_prerequisites` | `stdout` | 2 | 1 校验不通过 |
| `mrg_export` | `stdout` | 2 | 1 校验不通过，或输出文件已存在而没给 `--force` |
| `scan_wikilinks` | `stdout` | 2：不是目录，或目录下没有课程 | — |
| `learning_state` | `stdout` | 1 | — |
| `store_init` | `stdout` | 1：不是知识库，或 `store.json` 读坏 | — |
| `prerequisite_state` | `stdout` | 1 | — |
| `lesson_section` | `stderr` | 1 | — |
| `diagram` | `stderr` | 1 | — |
| `comparator` | `stderr` | 1：没有这门课的 MRG 导出，或抽取文件读坏 | — |
| `review_outline` | `stderr` | 1：`learner-state.json` 未建或读坏 | — |
| `review_pool` | `stderr` | 1 | — |
| `cards` | `stderr` | 1：不是知识库，或没有这门课的 MRG 导出 | — |
| `learner_state_build` | `stderr` | 1 | — |
| `index_match` | `stderr` | 1 | — |
| `outline_status` | `stderr` | 1 | 0 且 `stdout` 打 `skipped: `：课程目录缺三个文件之一，含目录不存在 |
| `mermaid_fit` | `stderr` | 1 | — |
| `lrg_record` | `stderr` | 1 | `show` 的知识库或课程不存在时 0，见第 5 节，待定 |
| `store_sync` | `stderr` | 1 | — |
| `source_manifest` | `stderr` | 1 | 1 且无前缀：两处参数检查；2：清单生成了但有 `problems` |
| `next_step` | `stderr` | 1 | — |
| `survey_materials` | `stderr` | 2：不是目录 | `--max-files` 小于 1 时走 `argparse`，退出 2 |
| `score_pack` | `stderr` | 1 | 2：`--material-id` 在 `materials.json` 里没有 |
| `score_all` | `stderr` | 2：不是目录 | 2：见第 4 节；1：有课程目录的状态是 `fail` 或 `skipped`，或基线文件读坏 |
| `difficulty_digest` | `stderr` | 2 | 1：`--against` 列出了减少 |
| `gap_ledger` | `stderr` | 2 | 1：`--check` 不通过，每条一行 `FAIL: ` |

`stdout` 一组 7 个，`stderr` 一组 19 个。`stdout` 一组里的前四个是校验、导出与扫描类，输出本来就给模型读；`learning_state`、`store_init`、`prerequisite_state` 与同类的 `stderr` 脚本不一致，原因没有记录，是否统一未定。

## 3. `test_cli.py` 逐行

四张表与 `test_cli.py` 的四组行一一对应，顺序相同。前缀一列除注明外都是 `ERROR: `。

临时目录里有：`bad.json`（不是 JSON）、`resp.txt`、`badstore/store.json`（不是 JSON）、`badcourse/`（`outline.md` 加两个读坏的 JSON）。`missing.*`、`nostore/`、`nocourse/` 不存在。

`WITHOUT_STORE`，41 行：

| 脚本 | 参数 | 退出码 | 流 |
|---|---|---|---|
| `validate_lesson` | `missing.json` | 2 | `stdout` |
| `validate_lesson` | `bad.json` | 2 | `stdout` |
| `learning_state` | `show --state missing.json` | 1 | `stdout` |
| `learning_state` | `init --lesson-plan bad.json --output out.json` | 1 | `stdout` |
| `mrg_export` | `missing.json --output-dir out` | 2 | `stdout` |
| `mrg_export` | `bad.json --output-dir out` | 2 | `stdout` |
| `store_init` | `show --store nostore` | 1 | `stdout` |
| `store_init` | `show --store badstore` | 1 | `stdout` |
| `lesson_section` | `missing.json --list` | 1 | `stderr` |
| `lesson_section` | `bad.json --list` | 1 | `stderr` |
| `diagram` | `missing.json --chain` | 1 | `stderr` |
| `diagram` | `bad.json --chain` | 1 | `stderr` |
| `comparator` | `--store nostore --lesson-id x --section-id s --extraction missing.json` | 1 | `stderr` |
| `review_outline` | `--store nostore --lesson-id x` | 1 | `stderr` |
| `review_pool` | `--store nostore` | 1 | `stderr` |
| `review_pool` | `--store badstore` | 1 | `stderr` |
| `cards` | `due --store nostore` | 1 | `stderr` |
| `cards` | `build --store badstore --lesson-id x` | 1 | `stderr` |
| `learner_state_build` | `build --store nostore` | 1 | `stderr` |
| `learner_state_build` | `build --store badstore` | 1 | `stderr` |
| `index_match` | `show --store nostore` | 1 | `stderr` |
| `outline_status` | `--course badcourse` | 1 | `stderr` |
| `outline_status` | `--course nocourse` | 0 | `stdout`，前缀 `skipped: ` |
| `mermaid_fit` | `missing.md` | 1 | `stderr` |
| `mermaid_fit` | `badcourse` | 1 | `stderr` |
| `lrg_record` | `append --store nostore --lesson-id x --section-id s --response-file resp.txt --verdict mastered` | 1 | `stderr` |
| `scan_wikilinks` | `missing.md` | 2 | `stdout` |
| `score_pack` | `nocourse` | 1 | `stderr` |
| `score_pack` | `badcourse` | 1 | `stderr` |
| `score_all` | `nocourse` | 2 | `stderr` |
| `difficulty_digest` | `missing.json` | 2 | `stderr` |
| `difficulty_digest` | `bad.json` | 2 | `stderr` |
| `gap_ledger` | `missing.json missing.json` | 2 | `stderr` |
| `gap_ledger` | `bad.json bad.json` | 2 | `stderr` |
| `prerequisite_state` | `show --state missing.json` | 1 | `stdout` |
| `prerequisite_state` | `show --state bad.json` | 1 | `stdout` |
| `validate_prerequisites` | `missing.json` | 2 | `stdout` |
| `validate_prerequisites` | `bad.json` | 2 | `stdout` |
| `survey_materials` | `nocourse` | 2 | `stderr` |
| `store_sync` | `push --store nostore` | 1 | `stderr` |
| `store_sync` | `push --store badstore` | 1 | `stderr` |
| `source_manifest` | `--rebase missing.json` | 1 | `stderr` |
| `source_manifest` | `--rebase bad.json` | 1 | `stderr` |
| `next_step` | `--progress missing.json` | 1 | `stderr` |
| `next_step` | `--progress bad.json` | 1 | `stderr` |

后三组先用课程模板建好知识库 `store/`：`store_init init`、`store_init register`、`mrg_export --store`。`{lesson}`、`{section}` 是模板的课程 id 与第一节 id；`append …` 省略的是 `--store store --lesson-id {lesson} --section-id {section}`。

`WITH_STORE`，8 行，全部退出 1、走 `stderr`：

| 脚本 | 参数 |
|---|---|
| `comparator` | `--store store --lesson-id {lesson} --section-id {section} --extraction bad.json` |
| `index_match` | `recall --store store --candidates missing.json` |
| `index_match` | `recall --store store --candidates bad.json` |
| `lrg_record` | `append … --response-file missing.txt --verdict mastered` |
| `lrg_record` | `append … --response-file resp.txt --verdict mastered --extraction bad.json` |
| `cards` | `build --store store --lesson-id nosuch` |
| `review_outline` | `--store store --lesson-id {lesson}`，尚无 `learner-state.json` |
| `learner_state_build` | `show --store store`，尚无 `learner-state.json` |

`ARRAY_ROOT`，6 行：`list.json` 与 `pack/lesson-plan.json` 的内容是 `[]`。每条打一行 `ERROR: … root must be an object`，退出 1：

| 脚本 | 参数 | 流 |
|---|---|---|
| `validate_lesson` | `list.json` | `stdout` |
| `learning_state` | `show --state list.json` | `stdout` |
| `learning_state` | `mark --state list.json --type probe_completed` | `stdout` |
| `prerequisite_state` | `show --state list.json` | `stdout` |
| `lrg_record` | `append … --response-file resp.txt --verdict mastered --progress list.json` | `stderr` |
| `score_pack` | `pack` | `stderr` |

`validate_lesson` 对数组根退出 1，与读不到文件时的 2 不同：它按校验不通过处理，消息与 `validate_plan` 报的相同。

把 `store/learner-state.json` 改成非 JSON 之后，3 行，全部退出 1、走 `stderr`：

| 脚本 | 参数 |
|---|---|
| `learner_state_build` | `show --store store` |
| `review_outline` | `--store store --lesson-id {lesson}` |
| `review_pool` | `--store store` |

## 4. 退出码

- 0：成功。另有两处坏输入也是 0：`outline_status` 打 `skipped: `；`lrg_record show` 见第 5 节。
- 1：多数脚本读坏文件或执行失败时的退出码。`validate_lesson`、`validate_prerequisites`、`mrg_export` 的 1 专指校验不通过；`mrg_export` 的输出文件已存在而没给 `--force` 也是 1。`score_all` 的 1 是有课程目录的状态是 `fail` 或 `skipped`，或基线文件读坏。
- 2 有五种含义：
  1. `argparse` 参数错误，包括 `survey_materials` 的 `--max-files` 小于 1。前缀 `usage:`，走 `stderr`。
  2. 校验与导出脚本读不到或读不懂输入：`validate_lesson`、`validate_prerequisites`、`mrg_export`。用来与它们的"校验不通过 = 1"区分。
  3. 给的路径不是目录，或目录下找不到要处理的东西：`scan_wikilinks` 不是目录或没有课程；`survey_materials` 不是目录；`score_all` 任一根不是目录、`--baseline-dir` 不是目录、`materials.json` 读坏、找不到任何课程目录。
  4. `source_manifest` 生成了清单，但清单的 `problems` 非空，例如源路径不存在。清单照常写出，`stdout` 或 `--output`，没有 `ERROR:` 行。
  5. `score_pack` 的 `--material-id` 在 `plugin/evals/materials.json` 里找不到。

## 5. 已知例外

- `lrg_record show` 遇到不存在的知识库目录，或知识库里没有这门课的学习记录（LRG，`lrg/<lesson-id>.jsonl`），退出 0，`stdout` 打 `lesson: <id>  attempts: 0`，`stderr` 为空，不创建目录。待定：这是否应当报错尚未决定，`test_cli.py` 不收这一条，本文不把它当作规范。
- `source_manifest` 的两处参数检查用 `raise SystemExit("…")`：没给源路径也没给 `--rebase`，`--max-text-bytes` 或 `--max-hash-bytes` 小于 1。退出 1，消息走 `stderr`，没有 `ERROR:` 前缀。
