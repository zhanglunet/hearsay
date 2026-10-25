"""复述（retell）最小切片：内容覆盖度、流利度、语法反馈。

覆盖度是词级启发式：抽材料实义词，看复述里有没有出现（简单词形归一）。
不是语义覆盖，也不是 LLM 判分；流利度只有词数与（给定时长时的）WPM。
语法反馈复用 M2 的 detect_errors（有 key 走 Claude，否则规则），
confirmed 错误可回流 M3。不写音素、不写 CanDoEvidence。
"""

import re

STOPWORDS = set("""
a an the and or but if then than so because as of at by for with about into over after
before between out off again further once here there when where why how all any both each
few more most other some such no nor not only own same too very can will just should now
i you he she it we they me him her us them my your his its our their this that these those
am is are was were be been being have has had having do does did doing would could ought
i'm you're he's she's it's we're they've i'll you'll he'll she'll we'll they'll
don't doesn't didn't won't wouldn't can't couldn't shouldn't mustn't
to in on up down
""".split())


def norm_word(word):
    w = re.sub(r"[^a-z']", "", word.lower())
    if w.endswith("'s"):
        w = w[:-2]
    if len(w) > 3 and w.endswith("s") and not w.endswith("ss"):
        w = w[:-1]
    return w


def keywords(text, cap=12):
    """材料实义词（去停用词、去重、保序），最多 cap 个。"""
    out = []
    for raw in text.split():
        w = norm_word(raw)
        if w and w not in STOPWORDS and len(w) > 2 and w not in out:
            out.append(w)
    return out[:cap]


def coverage(material_text, retell_text):
    keys = keywords(material_text)
    said = {norm_word(w) for w in retell_text.split()}
    matched = [k for k in keys if k in said]
    missing = [k for k in keys if k not in said]
    return dict(keywords=keys, matched=matched, missing=missing,
                coverage=round(len(matched) / len(keys), 3) if keys else None)


def fluency(retell_text, duration_sec=None):
    words = len(retell_text.split())
    out = dict(words=words, duration_sec=duration_sec, wpm=None)
    if duration_sec and duration_sec > 0:
        out["wpm"] = round(words * 60 / duration_sec, 1)
    return out


def build_summary(material_text, retell_text, duration_sec=None):
    cov = coverage(material_text, retell_text)
    flu = fluency(retell_text, duration_sec)
    if cov["coverage"] is None:
        text = "材料里没有可抽取的实义词，无法计算覆盖度。"
    else:
        text = f"复述覆盖了 {cov['coverage']:.0%} 的材料实义词（{len(cov['matched'])}/{len(cov['keywords'])}）。"
    if cov["missing"]:
        text += "没提到的关键词：" + "、".join(cov["missing"][:8]) + "。"
    text += f"共 {flu['words']} 词"
    if flu["wpm"]:
        text += f"，约 {flu['wpm']} 词/分钟"
    text += "。覆盖度是词级启发式，不代表语义完整；语法反馈见错误清单。"
    return dict(coverage=cov, fluency=flu, summary_zh=text)
