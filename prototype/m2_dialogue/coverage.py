"""objectives 覆盖情况的启发式判断。离线可测；LLM 判定留到事后批处理链路。"""

import re

REASON = re.compile(
    r"\b(because|since|due to|delay|delayed|problem|issue|sick|busy|stuck|waiting|blocked)\b", re.I)
DATE = re.compile(
    r"\b(monday|tuesday|wednesday|thursday|friday|saturday|sunday|tomorrow|tonight|"
    r"next week|next month|today|\d{1,2}(st|nd|rd|th)?|"
    r"january|february|march|april|may|june|july|august|september|october|november|december|"
    r"\d{1,2}/\d{1,2})\b", re.I)


def coverage(learner_texts, event_fired, replies_after_event):
    """返回与 SCENARIO.objectives 对齐的三个布尔值。

    前两条看学习者全部发言里的关键词；第三条要求意外问题确实触发过、
    且之后学习者有过回应。只是「说没说到」，不是「说得好不好」。
    """
    text = " ".join(learner_texts)
    return [bool(REASON.search(text)), bool(DATE.search(text)),
            bool(event_fired and replies_after_event > 0)]
