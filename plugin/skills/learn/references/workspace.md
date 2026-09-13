# 学习工作区布局

系统写出的**一切**都放在学习工作区里，材料本身永远不被写入。两种布局，一套规则：

```text
独立布局：一批材料、就地学                 统一布局：一个总目录管所有材料和课程
<材料根>/                                  <总目录>/                  ← 宿主打开的目录
├── （仓库、文档…）                          ├── material/<材料集>/     只读
└── whetstone/          ← 工作区             ├── learner-profile.md     跨目标的档案（背景、偏好、知识库开关）
    ├── learner-profile.md                    ├── courses/<目标>/        ← 计划目录：一个学习目标一个
    ├── learning-plan.md                      │   ├── learning-plan.md   （开头写这个目标的情境与终点能力）
    ├── survey/                               │   ├── survey/
    ├── courses/<id>/                         │   └── <course-id>/
    ├── external/<集名>_<日期>/                ├── external/<集名>_<日期>/   检索来的外部资料存档
    ├── store/                                └── store/
    └── scripts/（仅 Cowork）
```

- **工作区**：宿主打开的目录里已有 `courses/`、`store/` 或 `learner-profile.md` 之一 → 就是它（统一布局）；否则是材料根下的 `whetstone/`（独立布局，不存在就创建）；学习者在调用语句里另指路径时用那个。
- **计划目录**：`learning-plan.md`、`survey/` 和各课程目录所在的目录。独立布局里就是工作区；统一布局里是 `courses/<目标>/`（目标名由学习者给，或按材料集取）。档案只放工作区根；计划目录里可以再放一份 `learner-profile.md` 只写这个目标的情境与终点能力，字段覆盖根档案。
- **课程包自包含**：`coverage[].path`、`source_refs.path`、`anchor.path` 都相对**材料根**；`sources.json` 的 `base_path` 记录材料根相对课程目录的位置（`source_manifest.py … --output <课程目录>/sources.json` 自动写好，如 `../../..` 或 `../../../material/tee_dsh`）。校验器和评分器不给 `--sources-root` 时从它推出材料根，所以课程目录搬到哪种布局都能校验。
- 旧布局（档案、`courses/`、`materials-survey.*` 直接放在材料根）仍被识别，不强制迁移。

