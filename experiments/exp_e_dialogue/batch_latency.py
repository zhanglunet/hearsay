"""会话后批处理延迟（M0 §6：5 分钟对话，转写 + 检测 + 复盘 < 60 秒）。

    python exp_e_dialogue/batch_latency.py --audio /path/dialogue-5min.wav

步骤与 M2 batch.py 一致：whisperX large-v3 + verbatim prompt 转写（实验 A 配置）
→ 错误检测（有 HEARSAY_ANTHROPIC_API_KEY 走 Claude，否则规则）→ 模板复盘。
分步计时并判定总耗时是否 < 60 秒。结果写 results_latency.json。

简化口径：整条音频按一个话语处理（真实 M2 是逐轮学习者音频分别转写，
多次小模型调用通常更慢）。所以这里达标不代表 M2 一定达标，报告里要写清。
需要 whisperX 与 ffmpeg 环境（见 experiments/README），模型首次运行下载。
"""
import argparse, json, sys, time
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent.parent / "prototype"))

from m2_dialogue.batch import detect_errors, whisperx_transcriber

THRESHOLD_S = 60.0


def summarize_timings(timings):
    total = round(sum(timings.values()), 2)
    return dict(steps_sec={k: round(v, 2) for k, v in timings.items()},
                total_sec=total, threshold_sec=THRESHOLD_S, passed=total < THRESHOLD_S)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--audio", required=True)
    p.add_argument("--text", help="已有转写时跳过 ASR 步骤（只测检测+复盘，报告注明）")
    args = p.parse_args()

    timings = {}
    if args.text:
        text = args.text
        timings["transcribe"] = 0.0
    else:
        t0 = time.time()
        transcribe = whisperx_transcriber()
        timings["model_load"] = time.time() - t0
        t0 = time.time()
        text = transcribe(args.audio)
        timings["transcribe"] = time.time() - t0
    t0 = time.time()
    transcripts = [dict(utterance_id=1, realtime_text="", batch_text=text, source="whole_file")]
    detected, detection = detect_errors(transcripts)
    timings["detect"] = time.time() - t0
    t0 = time.time()
    summary = f"本次转写 {len(text.split())} 词，检出 {len(detected)} 条候选错误（{detection}）。"
    timings["summary"] = time.time() - t0

    report = summarize_timings(timings)
    report.update(audio=args.audio, detection=detection, words=len(text.split()),
                  errors=len(detected), summary_zh=summary,
                  note="整条音频按一个话语处理；模型加载单列，不计入 60 秒预算时请说明。",
                  model_load_sec=round(timings.get("model_load", 0.0), 2))
    # 60 秒预算指转写+检测+复盘，不含一次性模型加载
    report["total_sec"] = round(report["total_sec"] - report["model_load_sec"], 2)
    report["passed"] = report["total_sec"] < THRESHOLD_S
    print(json.dumps(report, indent=1, ensure_ascii=False))
    out = HERE / "results_latency.json"
    out.write_text(json.dumps(report, indent=1, ensure_ascii=False))
    print("wrote", out)


if __name__ == "__main__":
    main()
