from __future__ import annotations

import json
import unittest

from _support import PLUGIN_ROOT, STRUCTURE_PLAN, diagram, load_template, mermaid_fit, validate_lesson


class DiagramTests(unittest.TestCase):
    def test_diagrams_use_public_fields_only_and_the_outline_must_carry_the_chain(self):
        plan = load_template()
        plan["sections"] = [dict(plan["sections"][0], id="s01"), dict(plan["sections"][0], id="s02", title="第二节", depends_on=["s01"]),
                            dict(plan["sections"][0], id="s03", title="第三节", depends_on=["s01"])]
        plan["deferred"] = [{"type": "section", "id": "s03", "reason": "略过"}]
        chain = diagram.chain(plan)
        self.assertTrue(chain.startswith("```mermaid\nflowchart TD") and chain.endswith("```"))
        self.assertIn('S_s01["1 从线性材料到总体结构"]', chain)
        self.assertIn("S_s01 --> S_s02", chain)
        self.assertNotIn("S_s03[", chain)                       # deferred sections are not drawn
        self.assertIn("本次略过：s03", chain)
        for hidden in (plan["sections"][0]["meaning"], plan["sections"][0]["checkpoint"]["criteria"][0]["text"]):
            self.assertNotIn(hidden, chain)
        system = diagram.system(plan)
        self.assertIn('M1["输入范围"]', system)
        self.assertIn("M4 --> M5", system)
        graph = diagram.section_graph(plan, "s01")
        self.assertIn('-- "依赖" -->', graph)     # the relation type in words, not the field value
        self.assertNotIn("depends_on", graph)
        self.assertIn("问题链（supporting）", graph)
        plan["relations"][0]["layer"] = "rationale"
        self.assertIn("没有公开层的关系边", diagram.section_graph(plan, "s01"))   # rationale-layer edges are never drawn
        with self.assertRaises(ValueError):
            diagram.section_graph(plan, "s99")
        with self.assertRaises(ValueError):
            diagram.system(dict(plan, big_picture={"system_map": []}))

        outline = (PLUGIN_ROOT / "skills" / "learn" / "assets" / "outline-template.md").read_text(encoding="utf-8")
        base = load_template()
        self.assertEqual(validate_lesson.validate_outline(outline, base), [])
        stripped = validate_lesson.MERMAID_BLOCK.sub("", outline)
        errors = validate_lesson.validate_outline(stripped, base)
        self.assertTrue(any("mermaid diagram of the problem chain" in e for e in errors), errors)
        old = dict(base, schema_version="1.2")
        old["sections"][0]["concepts"][0] = {k: v for k, v in old["sections"][0]["concepts"][0].items() if k not in ("contrast", "cases", "ontology")}
        self.assertEqual(validate_lesson.validate_outline(stripped, old), [])   # older courses are not asked for a diagram
        two = load_template()
        two["sections"].append(dict(two["sections"][0], id="s02", title="没画进图的节", depends_on=["s01"]))
        two["sections"][0]["new_problem"] = "下一节"
        errors = validate_lesson.validate_outline(outline + "\n第二节标题：没画进图的节\n", two)
        self.assertTrue(any("does not show section 's02'" in e for e in errors), errors)


class MermaidFitTests(unittest.TestCase):
    """Width is what the layout engine does to a topology, so it is decided in code, not by prompt."""

    def test_the_direction_follows_the_shape_of_the_graph(self):
        chain = "\n".join(f"    N{i}[节点{i}] --> N{i + 1}[节点{i + 1}]" for i in range(1, 7))
        self.assertEqual(mermaid_fit.fit_direction(chain), "TD")          #深链横着排，宽度随链长增长
        fan = "\n".join(f"    R[根] --> L{i}[叶{i}]" for i in range(1, 7))
        self.assertEqual(mermaid_fit.fit_direction(fan), "LR")            # 宽扇出竖着排，宽度随扇出增长
        self.assertLess(mermaid_fit.estimate_width(f"flowchart TD\n{chain}"),
                        mermaid_fit.estimate_width(f"flowchart LR\n{chain}"))

    def test_a_note_beside_the_last_actor_is_moved_over_it(self):
        text = "sequenceDiagram\n    participant A as 甲\n    participant B as 乙\n    A->>B: 提交\n    Note right of B: 这一步之后乙的状态变了"
        fitted, report = mermaid_fit.fit(text)
        self.assertIn("Note over B:", fitted)
        self.assertNotIn("Note right of", fitted)
        self.assertLess(report["after"], report["before"])

    def test_a_subgraph_with_a_crossing_edge_becomes_a_box_and_keeps_its_name(self):
        text = ("flowchart TD\n"
                "    subgraph G[\"外框\"]\n"
                "        A[\"里面的甲\"]\n"
                "        B[\"里面的乙\"]\n"
                "    end\n"
                "    G --> A\n"
                "    C[\"外面的丙\"] --> B\n")
        fitted = mermaid_fit.fit(text, budget=1)[0]
        self.assertNotIn("subgraph", fitted)      # mermaid 会忽略跨界子图内部的 direction，留着只多占一个 rank
        self.assertIn('G["外框"]', fitted)         # 框变成盒子，名字不丢
        self.assertIn("G -.- B", fitted)          # 原本没有连线的子部件补一条虚线，包含关系不丢
        self.assertNotIn("G -.- A", fitted)       # 已经有连线的不重复画
        self.assertEqual(mermaid_fit.fit(text, budget=999)[1]["actions"], [])   # 不超预算就不动它

    def test_folding_breaks_at_a_space_and_never_inside_a_word(self):
        self.assertEqual(mermaid_fit.wrap("流式返回 token", 12), "流式返回<br/>token")
        self.assertEqual(mermaid_fit.wrap("CUDA graph 运行器", 12), "CUDA graph<br/>运行器")
        self.assertEqual(mermaid_fit.wrap("短名", 12), "短名")
        self.assertEqual(mermaid_fit.text_width("甲<br/>乙丙"), 4)   # 折过行的标签按最宽的一行算

    def test_an_edge_label_that_only_repeats_an_endpoint_is_dropped(self):
        text = 'flowchart LR\n    A["内存池"] -- "内存池" --> B["调度器"]\n    B -- "分配 KV" --> A\n'
        fitted = mermaid_fit.fit(text, budget=1)[0]
        self.assertNotIn('-- "内存池" -->', fitted)
        self.assertIn("分配 KV", fitted)          # 携带信息的标签留着

    def test_a_line_it_does_not_understand_is_passed_through_and_reported(self):
        text = 'flowchart TD\n    A["甲"] --> B["乙"]\n    classDef hot fill:#f00\n    class A hot\n'
        fitted, report = mermaid_fit.fit(text)
        self.assertIn("classDef hot fill:#f00", fitted)
        self.assertIn("class A hot", fitted)
        self.assertEqual(sorted(report["unhandled"]), ["class A hot", "classDef hot fill:#f00"])

    def test_every_block_in_a_note_is_fitted_and_the_prose_is_left_alone(self):
        note = ("# 一篇笔记\n\n正文一段。\n\n```mermaid\nflowchart LR\n" +
                "\n".join(f"    N{i}[节点{i}] --> N{i + 1}[节点{i + 1}]" for i in range(1, 7)) +
                "\n```\n\n正文二段。\n\n```mermaid\nsequenceDiagram\n    participant A as 甲\n    Note left of A: 旁注\n```\n")
        fitted, reports = mermaid_fit.fit_document(note)
        self.assertEqual(len(reports), 2)
        self.assertIn("正文一段。", fitted)
        self.assertIn("flowchart TD", fitted)
        self.assertIn("Note over A: 旁注", fitted)
        self.assertEqual(fitted.count("```"), 4)

    def test_a_diagram_already_within_budget_comes_back_unchanged(self):
        for kind in ("--chain", "--system", "--section"):
            plan = json.loads(STRUCTURE_PLAN.read_text(encoding="utf-8"))
            drawn = diagram.chain(plan) if kind == "--chain" else (
                diagram.system(plan) if kind == "--system" else diagram.section_graph(plan, "s01"))
            self.assertEqual(mermaid_fit.fit(drawn)[0], drawn, kind)
            self.assertLessEqual(mermaid_fit.estimate_width(drawn), mermaid_fit.DEFAULT_BUDGET, kind)
