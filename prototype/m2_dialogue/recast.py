"""recast 候选的规则扫描：实时纠错链路的离线占位。

只扫少数高确定性的中文母语者迁移错误（代码见 docs/design/l1-zh-error-taxonomy.md）。
产出是 provisional 提示，不是 confirmed ErrorInstance；复盘里必须如实标注。
"""

import re

# (错误代码, 匹配, 期望说法)。observed 取实际匹配到的原文。
RULES = [
    ("G13", re.compile(r"\bmore better\b", re.I), "better"),
    ("G08", re.compile(r"\bdiscuss(?:ed)? about\b", re.I), "discuss / discussed（去掉 about）"),
    ("G09", re.compile(r"\bvery like\b", re.I), "really like"),
    ("G03", re.compile(r"\b(he|she) go\b", re.I), "he/she goes"),
    ("G08", re.compile(r"\bin (monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b", re.I),
     "on + 星期几"),
]


def scan_recasts(text):
    """返回 [{code, observed, expected, status, detected_by}]，全部 provisional。"""
    out = []
    for code, pattern, expected in RULES:
        m = pattern.search(text)
        if m:
            out.append(dict(code=code, observed=m.group(0), expected=expected,
                            status="provisional", detected_by="rule"))
    return out
