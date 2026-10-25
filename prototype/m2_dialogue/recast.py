"""recast 候选的规则扫描：实时纠错链路的离线占位。

只扫少数高确定性的中文母语者迁移错误（代码见 docs/design/l1-zh-error-taxonomy.md）。
产出是 provisional 提示，不是 confirmed ErrorInstance；复盘里必须如实标注。
"""

import re

CODE_RE = re.compile(r"^(?:[GLI]\d{2}|X00)$")

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


def _norm_space(text):
    return " ".join(str(text).lower().split())


def validate_llm_errors(raw_errors, transcripts):
    """逐条校验 LLM 输出：代码只许 G/L/I、话语编号必须存在、observed 必须是原文
    连续片段、confidence >= 0.6（M0 §2.4 以下不进统计）。不合格的静默丢弃。
    实时 recast 抽取与批处理检测共用；detected_by 由调用方覆盖。"""
    by_uid = {t["utterance_id"]: t["batch_text"] for t in transcripts}
    out = []
    for e in raw_errors:
        if not isinstance(e, dict):
            continue
        uid, code = e.get("utterance_id"), e.get("code", "")
        observed, expected = e.get("observed", ""), e.get("expected", "")
        confidence = e.get("confidence", 0)
        if uid not in by_uid or not CODE_RE.match(str(code)):
            continue
        if not isinstance(observed, str) or not observed.strip() or not isinstance(expected, str):
            continue
        if not isinstance(confidence, (int, float)) or confidence < 0.6:
            continue
        if _norm_space(observed) not in _norm_space(by_uid[uid]):
            continue
        out.append(dict(utterance_id=uid, code=code, observed=observed, expected=expected,
                        confidence=round(float(confidence), 3), detected_by="asr_llm"))
    return out
