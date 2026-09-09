# 学习科学依据与开放问题

系统的每个机制押在哪条证据上，这些证据有多强，以及哪些假设还没有数据。效应量与文献来自 2026-08 与 2026-09 的两次联网核对，引用前建议抽查原文，尤其是效应量在不同二手来源间可能有出入。

## 1. 机制与证据

| 系统里的机制 | 依据 | 判定 |
|---|---|---|
| 隐藏参考、合上材料用自己的话重建；resume 先出变式题 | 检索练习优于重读：Adesope, Trevisan & Sundararajan 2017 元分析（272 个效应量），g = 0.51 对比重学、0.61 对比全部对照；保持间隔 1–6 天时更大（g = 0.82 对比不到 1 天的 0.56） | 强支持 |
| 主问题要求"是什么、为什么需要、如何工作" | 自我解释：Bisra et al. 2018 元分析（69 个效应量），g = 0.55；"解释你对 X 的理解程度"这类元认知提示效果差，所以追问用推理型（"为什么 A 导致 B""去掉 X 会怎样"） | 强支持 |
| 学习者作答被抽成概念和有类型的关系 | 构建概念图优于研读：Schroeder, Nesbit, Anguiano & Adesope 2018 元分析（142 个效应量），构建 g = 0.72、研读 0.43 | 强支持 |
| 严守"不看材料重建" | Karpicke & Blunt 2011（Science）：检索练习优于照书画概念图；O'Day & Karpicke 2021：概念图加检索不比纯检索好但更费时。从记忆中重建本身就是检索练习，一旦允许翻书就退化为被证伪的形态 | 设计站在正确一侧，红线 |
| 信心只作诊断信号；反馈先处理高信心错误；旧错误以匿名命题回来 | 延迟 JOL（Nelson & Dunlosky 1991；Weaver & Kelemen 1997）：即时判断被流畅性错觉污染；hypercorrection（Butterfield & Metcalfe 2001）：高信心错误被纠正后记得更牢；Kornell, Hays & Bjork 2009、Metcalfe 2017：主动犯错并得到纠正优于避免犯错。条件：纠正必须紧跟暴露，所以复习题同轮闭环 | 强支持；匿名化本身无直接证据（§4 问题 11） |
| `core ≤ 4 / 节` | Cowan 2001/2010：工作记忆约 4±1 个组块 | 强支持 |
| 提示逐步减少：全概念名 → 锚点 → 无提示 → 迁移 | expertise reversal（Kalyuga）：对新手有效的脚手架对熟练者有害 | 方向有强支持；档位划分是自创，切换时机是开放问题 |
| 先预测再揭示；rationale 与 principle 不作讲解出现 | Schwartz & Bransford 1998 "A Time for Telling"：先对比案例、自己挣扎，之后的讲解被理解为洞见；顺序反过来只被当作事实记住。四层对应 SOLO taxonomy（Biggs & Collis 1982）的 unistructural → multistructural → relational → extended abstract；后两层是 Polanyi 1966 意义上的默会知识 | 方向强支持；四层的具体切分是自创 |
| 时效窗口；"已掌握"必须带时效；着色不按错误次数 | 间隔效应（Cepeda et al. 2008，N > 1350）：最优间隔约为保持目标的 10–20%；FSRS 在约 7 亿条复习记录上对 99.5% 以上用户优于 SM-2。只有即时证据不算掌握与延迟 JOL 一致；按错误次数着色会与 hypercorrection 矛盾 | 支持；时效窗口是占位，将来接 FSRS |
| 学习者状态放在派生的结构化文件里，不靠模型"记住" | LLM 无法跨时间一致地追踪学习者知识状态（arXiv:2512.23036） | 一致 |
| 协议按状态拆文件，每时刻 ≤ 60 行；校验器代替规则 | 多约束指令遵循基准（IFEval，arXiv:2311.07911）：遵循率随约束数下降；"Lost in the Middle"（arXiv:2307.03172）：长上下文中段被忽略 | 支持；拆分对连贯性的代价未测 |
| 受信领域内 MRG 是尺子；`pedagogical_inference` 降权 | 这是范围决策，无学习科学证据直接支持或反对。风险来自抽取而非材料：先修边的抽取精度低于概念（arXiv:2507.18479），课程知识点抽取 F1 约 0.77 | 可接受；支持类型分级与 `weak_reference` 是必要的保险 |
| 跨课概念索引；已学概念出变式题代替诊断 | 把复用变成延迟检索符合间隔效应；概念对齐是实体消解问题，一般情形无解，个人规模加人工确认可行 | 机制有支持，精度未验证 |

## 2. 同类产品

| 产品 | 做法 | 实证 |
|---|---|---|
| Khanmigo | GPT 辅导 + 练习体系 | NBER Working Paper 35620，两年 RCT（田纳西 18 所中学）：数学提升 0.06–0.08 SD / 年，与无 AI 的普通练习相当；中位学生只在 1/3 的练习日使用，出错后仅 17% 的场次求助 |
| LearnLM、Study Mode、Claude Learning Mode | 提示工程实现"教学模式" | TeachLM（arXiv:2510.05087）：三家行为高度趋同，常见缺陷是给答案、默认选择题、忽略学习者上下文；答案准确率 97.3%，教学合理性 56.6% |
| Anki、RemNote | FSRS 间隔算法 | srs-benchmark：等留存下省 20–30% 复习量 |
| Kit-Build（广岛大学） | 专家图拆成部件让学习者重组，命题级自动比对 | RCT 显示显著提升阅读理解；但是封闭式重组，不是自由重建 |

对本项目的含义：AI 能力不是瓶颈，参与度是；纯对话式教学模式的平庸正是本项目用状态机和校验器约束模型的理由；Kit-Build 是"对照参考图找差异"最近的先例，但本项目要求的自由重建难度显著更高，没有先例在这个难度上验证过可持续性。

## 3. LLM 的能力边界

- 作为评判者的已知偏差：位置偏差、冗长偏差、偏好自己生成的文本（arXiv:2410.21819、arXiv:2410.02736）。教育评分的可靠性区间极宽：约束性短答题 QWK 可达 0.95 以上，开放性作答低至 r = 0.38。规律是人类评分者本身分歧大的维度，模型也不可靠；模糊的标准会被传导而不是被解决。系统的对策：`criteria` 带 `layer`、按条目判定；`verdict` 与 `depth_reached` 分开；比较器只落类别不打分。
- 知识图谱抽取：概念节点中等可靠，先修边明显更难（arXiv:2507.18479；综述 arXiv:2509.14554）。系统的对策：`prerequisite_for` 默认教学推断、诊断时降权；来源定位与支持类型不省。
- 本项目做的"模型对学习者自由重建的作答做结构化读取与反馈"，在 2025 年的系统综述里是研究空白：没有现成结论保证可行。

## 4. 风险与开放问题

四个风险，按严重程度：

1. **参与度是第一死因。** 系统的全部篇幅在讲学习正确性，而单次活动的摩擦决定能不能持续用下去；参与一旦中断，学习记录和掌握状态都失去数据来源。
2. **结构化记录的交互成本没有先例。** 指标是每节用时（`elapsed_seconds`），阈值是引入结构化记录前后不超过 +30%。
3. **模型评分有硬上限。** 到达层的判定尤其如此。
4. **先修边抽取精度不足。** 系统假设"使用中修正"，修正量可能被低估。

以下问题没有数据，不得当作已证明的结论：

1. 给出全部概念名会在多大程度上降低主动回忆的难度？
2. 一次活动包含多少概念和关系时，能兼顾结构整合与认知负担？
3. 学习者作答应拆到什么样的最小命题粒度？
4. 哪些关系能由原文验证，哪些本质上只是教学推断？
5. 哪些差异应立即反馈，哪些应留到延迟重建后再判断？
6. 如何用少量人工标注建立概念、关系、层与差异分类的质量基准？
7. 如何校准语义判定和支持类型判断？
8. **结构化 LRG 记录的交互成本是否可承受？** 这是生死问题，以每节用时回答。
9. 不同领域是否需要不同的概念粒度和关系集？
10. 模型对 `depth_reached` 的判定与人工判定的一致率有多高，在哪一层最不可靠？
11. 匿名化的错误复习是否保留了 hypercorrection 效应，还是所有权感的消失削弱了它？
12. 简单的时效窗口与 FSRS 类模型在个人规模数据上的差距有多大？
13. 跨课别名召回的精确率与召回率，以及学习者确认歧义的实际负担？
14. 协议按状态拆分后，讲义与评估的连贯性是否受损，如何测？

## 5. 来源

Adesope, Trevisan & Sundararajan 2017, *Review of Educational Research* 87:659–701；Bisra et al. 2018, *Educational Psychology Review* 30:703–725；Schroeder, Nesbit, Anguiano & Adesope 2018, *Educational Psychology Review*；Karpicke & Blunt 2011, *Science* 331:772–775；O'Day & Karpicke 2021；Cepeda et al. 2008, *Psychological Science* 19:1095–1102；Cowan 2001/2010；Kalyuga, expertise reversal effect；Nelson & Dunlosky 1991；Weaver & Kelemen 1997；Butterfield & Metcalfe 2001, *JEP: LMC* 27:1491–1494；Kornell, Hays & Bjork 2009, *JEP: LMC* 35:989–998；Metcalfe 2017, *Annual Review of Psychology* 68:465–489；Schwartz & Bransford 1998, *Cognition and Instruction* 16:475–522；Biggs & Collis 1982, *Evaluating the Quality of Learning: The SOLO Taxonomy*；Polanyi 1966, *The Tacit Dimension*。

NBER Working Paper 35620（Khanmigo RCT）；TeachLM, arXiv:2510.05087；srs-benchmark, github.com/open-spaced-repetition；Kit-Build, RPTEL 2026；arXiv:2512.23036（学习者建模的时间一致性）；arXiv:2410.21819、arXiv:2410.02736（LLM-as-judge 偏差）；arXiv:2504.03877（概念级 rubric）；arXiv:2509.14554（LLM 概念图综述）；arXiv:2507.18479（先修预测）；Liu et al. 2023, arXiv:2307.03172；Zhou et al. 2023, IFEval, arXiv:2311.07911。
