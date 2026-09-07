---
lesson_id: sample-guided-lesson
title: 示例：从总体问题理解系统设计
mode: full
---

# 示例：从总体问题理解系统设计

## 学习目标与模式

- 目标：能解释每个方案为何出现，以及它如何引出下一步
- 模式：**完整（full）**——每个 unit 都预测、重建、追问；core 概念全部进入检查点
- 材料范围：`examples/source.md`（总体设计与核心流程）；未覆盖：部署和性能调优

## 总体问题

材料试图解决：如何把分散输入转成可以理解和验证的结果。

## 系统地图

```text
输入范围 → 结构分析 → 教学路径 → 学习者解释 → 反馈与迁移
```

## 问题链（学习路线）

| # | Unit | 当前问题 → 方案 | 状态 |
|---|---|---|---|
| 1 | [[s01\|从线性材料到总体结构]] | 逐页阅读让局部遮住整体 → 先建立输入、过程、输出的宏观地图 | 待学 |

## 本课程涉及的全部概念

### Unit 1：从线性材料到总体结构

- **core**（进入检查点）：系统边界、宏观地图
- **supporting**（会讲，可要求验收）：问题链——把材料重组为“问题 → 方案 → 新问题”的序列
- **listed**（只列出，需要时用 `[[附录]]` 展开）：附录——不进入主线、可按需展开的次要细节（来源 `## Appendix`）

## 覆盖账本

| 材料位置 | 去处 |
|---|---|
| `examples/source.md` · Architecture | Unit 1（core） |
| `examples/source.md` · Course ordering | Unit 1（supporting） |
| `examples/source.md` · Appendix | Unit 1（listed） |
| `examples/source.md` · Deployment notes | 不讲：与学习目标无关的运维细节 |

## 怎么用

- 每个 unit 的正文在 `units/<id>.md`；学习时一次一个 unit，先预测再阅读方案。
- 想验收某个 supporting 概念，说“验收 问题链”。
- 想展开某个 listed 概念，在任何文档里写 `[[概念名]]` 后调用 clarify。
- 本次略过的内容（如有）列在上表“不讲 / 略过”，以后可以补。
