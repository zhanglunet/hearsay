import pandas as pd, sys
from pathlib import Path
df = pd.read_csv(Path(__file__).parent / "results.csv")
def rate(g): return (g.verdict == "retained").mean()
print("## 总保留率（按识别配置）"); print(df.groupby("config").apply(rate).round(3).to_string()); print()
print("## 按配置 × 声音"); print(df.pivot_table(index="config", columns="voice", values="verdict", aggfunc=lambda s: (s=="retained").mean()).round(2).to_string()); print()
print("## 按配置 × 错误代码"); print(df.pivot_table(index="code", columns="config", values="verdict", aggfunc=lambda s: (s=="retained").mean()).round(2).to_string()); print()
print("## verdict 分布"); print(df.groupby(["config","verdict"]).size().unstack(fill_value=0).to_string())
