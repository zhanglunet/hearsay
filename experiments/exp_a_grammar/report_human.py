"""实验 A 真人复测汇总：真人 vs 合成音保留率对比（issue #4）。

先跑：
  python exp_a_grammar/run.py                      # 合成音，已有 results.csv 可跳过
  python exp_a_grammar/run.py --audio-root /path/m1_human_audio/audio --out results_human.csv
再跑本脚本，输出 markdown 表格，可直接贴进复测报告。只用标准库。
真人 CSV 里 voice 列是匿名说话人编号（Sxx），阈值沿用实验 A：保留率 ≥ 80%。
"""
import csv, sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).parent
THRESHOLD = 0.80


def load(name):
    with open(HERE / name, newline="") as f:
        return list(csv.DictReader(f))


def counts(rows):
    n = len(rows)
    c = defaultdict(int)
    for r in rows:
        c[r["verdict"]] += 1
    return {k: (c[k], c[k] / n if n else 0.0) for k in ("retained", "corrected", "other")}


def by(rows, key):
    g = defaultdict(list)
    for r in rows:
        g[r[key]].append(r)
    return g


def main():
    synth = load("results.csv")
    human_name = sys.argv[1] if len(sys.argv) > 1 else "results_human.csv"
    human = load(human_name)
    hs, hh = by(synth, "config"), by(human, "config")

    print("## 总保留率：真人 vs 合成（verdict 占比，阈值 retained ≥ 0.80）\n")
    print("| 配置 | 合成 retained | 真人 retained | 真人 corrected | 真人 other | 真人达标 |")
    print("|---|---|---|---|---|---|")
    for cname in hh:
        sc = counts(hs.get(cname, []))
        hc = counts(hh[cname])
        def fmt(c, k):
            n, r = c[k]
            return f"{r:.3f}（{n}）" if n else "—"
        ok = "达到" if hc["retained"][1] >= THRESHOLD else "未达到"
        print(f"| {cname} | {fmt(sc, 'retained')} | {fmt(hc, 'retained')} "
              f"| {fmt(hc, 'corrected')} | {fmt(hc, 'other')} | {ok} |")

    print("\n## 真人保留率：说话人 × 配置\n")
    speakers = sorted({r["voice"] for r in human})
    configs = list(hh)
    print("| 说话人 | " + " | ".join(configs) + " |")
    print("|---" * (len(configs) + 1) + "|")
    for sp in speakers:
        rows_sp = [r for r in human if r["voice"] == sp]
        gs = by(rows_sp, "config")
        cells = [f"{counts(gs[c])['retained'][1]:.3f}" if gs.get(c) else "—" for c in configs]
        print(f"| {sp} | " + " | ".join(cells) + " |")

    base, verb = "whisperx_large-v3_default", "whisperx_large-v3_verbatim_prompt"
    if base in hh and verb in hh:
        d = counts(hh[verb])["retained"][1] - counts(hh[base])["retained"][1]
        print(f"\n## verbatim prompt 在真人上的增益\n\n{verb} 相对 {base}：{d:+.3f}"
              "（正值说明逐字提示在真人语音上仍然有效）")

    print("\n## verdict 分布（真人，配置 × 错误代码）\n")
    print("| code | " + " | ".join(f"{c} retained" for c in configs) + " |")
    print("|---" * (len(configs) + 1) + "|")
    for code in sorted({r["code"] for r in human}):
        rows_c = [r for r in human if r["code"] == code]
        gc = by(rows_c, "config")
        cells = [f"{counts(gc[c])['retained'][1]:.2f}" if gc.get(c) else "—" for c in configs]
        print(f"| {code} | " + " | ".join(cells) + " |")


if __name__ == "__main__":
    main()
