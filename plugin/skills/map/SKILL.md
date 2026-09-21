---
name: map
description: 为一门 Whetstone 课程建立或修订系统结构图（部件、包含关系、带文字说明的连线），把某一节改成结构讲解节或过程讲解节，或指定某一节展开的是图上的哪个部件。确认后写回 lesson-plan.json 与 outline.md。用于"这些名词我不知道在哪""先给我看看这套系统由什么组成""把第 2 节改成跟着一次运行走一遍""这一节到底在讲图上的哪块"。不生成 unit 文档、不教学。
---

# Map：系统结构图与两种讲解节

对**一门已有大纲的课**做三件事之一，确认后写回；不生成 `units/`，不教学。schema 低于 1.6 的计划先升到 `1.6`（新字段都可选，其余内容不动）。

## 三件事

1. **建立或修订系统结构图**：把这门课里表示"东西、通道、管理机制"的概念挑出来做部件，写进 `big_picture.system_map` 的 `{components: [{id, parent?}], links: [{from, to, label}]}`。`parent` 表示包含，渲染成框里套框；`links` 是有向线，`label` 写成几个字的短语说明这条线上走的是什么（图示原样渲染，不截断）。端点用本课概念 id；开启知识库时也可以用库里登记过的他课概念 id（校验时带 `--store`）。
2. **把某一节改成结构讲解节或过程讲解节**：改 `kind`，按新类型调整字段与检查点（见下）。原有的 `solution` 与 `new_problem` 要删掉，内容并进 `mechanism` 或移到别的节，不要静默丢弃。
3. **指定返回位置**：给某一节填 `position: <部件 id>`，表示这一节展开的是图上的哪个部件。任何节类型都可以填。

## 怎么判断该用哪种节

方法与判据在 `learn` 技能的 `references/build.md`「三种节：先安放，再追踪，再追因果」一节，照它执行。要点：说不出名词在系统里的位置 → 结构讲解节；名词认识而说不出一次运行怎么走 → 过程讲解节；有真实的机制、限制或取舍 → 保持问题链节。不为一个名词虚构设计理由。

结构讲解节的部件只能是 `supporting` 或 `listed`，每个必填 `ontology`（`entity / process / constraint / relation`）——编程平台、内存管理机制、通信方式不是三块并列的硬件，类型不同，图上的画法也不同。过程讲解节追踪**一种明确的运行方式**，`steps[]` 至少两条 `{actor, target?, action, changes}`，`actor` 与 `target` 用概念 id；本次不追踪的可选运行方式写成本节 `listed` 概念并填 `contrast.with` 指向被追踪的那个过程，不要串进步骤。

## 检查点

两种新节的检查点都是**合上文档走一条链路**，不是指认：结构讲解节给一个起点和一个终点，请学习者说出中间经过哪些部件、谁装在谁里面、每条连线上走的是什么，只判这一条路径；过程讲解节请学习者按顺序说出步骤、参与者与变化。`criteria` 三条，分别落在 `fact` 层与 `mechanism` 层。

## 呈现与确认

改动前把结构图画出来给学习者看（`diagram.py --system`），连同改了哪几节、哪些概念的角色或 `ontology` 变了。**只问一句**："这张图对不对？有没有画错位置的、该合并或拆开的？"确认后才写回，再跑校验。

## 写回与校验

```bash
python3 <learn>/scripts/validate_lesson.py <lesson-plan.json> --outline outline.md [--store <工作区>/store]
python3 <learn>/scripts/diagram.py <lesson-plan.json> --system      # 贴进 outline.md 的系统地图
python3 <learn>/scripts/diagram.py <lesson-plan.json> --section <id> # 结构节的部件图 / 过程节的时序图
```

`outline.md` 的系统地图换成新图；改过的节在问题链表里标出组织方式。`units/` 已存在且受影响的节，报告哪几份需要重生成，交给 `learn`；本技能不重生成。

## 脚本与契约的位置

- Claude Code 插件安装：`${CLAUDE_PLUGIN_ROOT}/skills/learn/scripts/`，契约 `${CLAUDE_PLUGIN_ROOT}/skills/learn/references/lesson-contract.md`，建课方法 `${CLAUDE_PLUGIN_ROOT}/skills/learn/references/build.md`；
- 个人技能目录安装：`${CLAUDE_SKILL_DIR}/../learn/...`；
- 其他宿主：与本技能同级的 `learn` 技能目录。

## 边界

- 只动 `big_picture.system_map`、节的 `kind / steps / position / checkpoint` 与相关概念的 `role / ontology`；不改学习记录、不改进度文件；
- 不把全部底层细节设成必学前置：结构讲解是为了给后面的内容一个坐标系，不是先学完一层基础；
- 部件的 `explanation` 只写职责、输入输出、连接，内部机制写一句"本节不展开"；真要展开另起一节，用 `position` 指回这个部件。
