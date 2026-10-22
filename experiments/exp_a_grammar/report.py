import pandas as pd, sys
from pathlib import Path
df = pd.read_csv(Path(__file__).parent / "results.csv")
def rate(g): return (g.verdict == "retained").mean()
print("## 总保留率（按识别配置）"); print(df.groupby("config").apply(rate).round(3).to_string()); print()
print("## 按配置 × 声音"); print(df.pivot_table(index="config", columns="voice", values="verdict", aggfunc=lambda s: (s=="retained").mean()).round(2).to_string()); print()
print("## 按配置 × 错误代码"); print(df.pivot_table(index="code", columns="config", values="verdict", aggfunc=lambda s: (s=="retained").mean()).round(2).to_string()); print()
print("## verdict 分布"); print(df.groupby(["config","verdict"]).size().unstack(fill_value=0).to_string())

# 敏感性分析：whisper 偶尔把 two/three 写成数字 2/3（"I have 2 book and 3 pen"），错误形式其实保留了，
# 但按字面匹配会被记成 other。这里把转写里的阿拉伯数字换回英文再重判一次，只作参考，不改 results.csv。
import re, json
DIGITS = {"0":"zero","1":"one","2":"two","3":"three","4":"four","5":"five","6":"six","7":"seven","8":"eight","9":"nine","10":"ten"}
def norm(t):
    t = re.sub(r"\b(\d+)\b", lambda m: DIGITS.get(m.group(1), m.group(1)), str(t).lower().replace("’", "'"))
    t = re.sub(r"[^a-z' ]+", " ", t); return " " + re.sub(r"\s+", " ", t).strip() + " "
def rejudge(r):
    n = norm(r.transcript); w, rr = norm(r.wrong).strip(), norm(r.right).strip()
    return "retained" if f" {w} " in n else ("corrected" if f" {rr} " in n else "other")
df["verdict_digits_normalized"] = df.apply(rejudge, axis=1)
print(); print("## 总保留率（转写中的数字归一化为英文后重判，参考）")
print(df.groupby("config").verdict_digits_normalized.apply(lambda s: (s=="retained").mean()).round(3).to_string())
