"""单场景定义，字段对齐 M0 §2.8 Scenario。

scripted_events 的 unexpected_question 用来制造 SI 类互动机会；
切片只记录它有没有触发，不写 CanDoEvidence。
"""

SCENARIO = dict(
    id="m2-project-delay",
    title="向同事解释项目延期",
    target_cefr="A2-B1",
    agent_role="同事 Alex，周五等你的周报",
    learner_role="项目负责人，要解释延期并给出新日期",
    objectives=["说明延期原因", "提出新的完成日期", "回应同事临时加的要求"],
    scripted_events=[
        dict(kind="unexpected_question", at_turn=2,
             payload="客户想今天要一页摘要，问你能不能给"),
    ],
)

OPENING = ("Hey, it's Alex. Are we still on track to send the report on Friday? "
           "How is it going on your side?")

UNEXPECTED_QUESTION = ("I see. One more thing — the client just asked for a one-page "
                       "summary today. Can you send it to them?")

PRODUCT_RULE_M2 = (
    "本切片不写学习者模型：没有 confirmed ErrorInstance、没有 FSRS、没有 CanDoEvidence。"
    "recast 只是 status=provisional 的待核对提示（detected_by=rule，实时链路的占位），"
    "不计入错误统计。浏览器语音识别会归一化文本，只用于驱动对话，不是权威转写。"
    "音素边界同 M1：实验 D 未通过，不产生 P 类错误。"
)
