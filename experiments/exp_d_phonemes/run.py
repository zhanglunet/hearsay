"""实验 D：OpenPronounce 音素级输出对照 speechocean762 的音素标注。

样本是 test 切分全部 2500 条（实验 B 的 39 条是子集，结果里单独汇总）。
音素字段来自 ``phones.compare_phones``：``compare_audio_with_text`` 在音素模型
开启时把该返回值原样写入 ``differences.expected_phones`` / ``heard_phones`` /
``errors``（见 openpronounce/speech.py），声学距离和词转写不改变这三项。

阈值和判定写在 align.py，跑模型之前就定死。本脚本只负责识别和落盘。
"""

import io
import json
import os
import sys
import time
import traceback
from collections import Counter
from pathlib import Path

os.environ.setdefault("OPENPRONOUNCE_DEVICE", "cpu")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

import numpy as np
import pandas as pd
import soundfile as sf
import librosa
import Levenshtein

HERE = Path(__file__).parent
DATA = HERE.parent / "data" / "speechocean762_test.parquet"
B_RUNS = HERE.parent / "exp_b_pronounce" / "runs.csv"
B_WORDS = HERE.parent / "exp_b_pronounce" / "words.csv"
JSONL = HERE / "utterances.jsonl"
SR = 16000


def norm_speaker(value) -> str:
    text = str(value).strip()
    if text.isdigit():
        return text.zfill(4)
    return text


def decode(audio) -> np.ndarray:
    raw = audio["bytes"] if isinstance(audio, dict) else audio
    wav, sr = sf.read(io.BytesIO(raw))
    if wav.ndim > 1:
        wav = wav.mean(1)
    if sr != SR:
        wav = librosa.resample(wav.astype(np.float32), orig_sr=sr, target_sr=SR)
    return wav.astype(np.float32)


def as_str_list(values) -> list[str]:
    if hasattr(values, "tolist"):
        values = values.tolist()
    return [str(v) for v in values]


def gt_words_of(words) -> list[dict]:
    if hasattr(words, "tolist"):
        words = words.tolist()
    out = []
    for wd in words:
        mis = wd["mispronunciations"]
        if hasattr(mis, "tolist"):
            mis = mis.tolist()
        out.append({
            "text": str(wd["text"]),
            "phones": as_str_list(wd["phones"]),
            "phones_accuracy": [float(x) for x in as_str_list(wd["phones-accuracy"])],
            "mispronunciations": [
                {
                    "index": int(item["index"]),
                    "canonical": str(item["canonical-phone"]),
                    "pronounced": str(item["pronounced-phone"]),
                }
                for item in mis
            ],
        })
    return out


def align_heard(expected: list[str], heard: list[str]) -> list[set[int]]:
    """Same index map as openpronounce.phones._align (insertions stick to the previous phone)."""
    alignment = [set() for _ in expected]
    for tag, i1, i2, j1, j2 in Levenshtein.opcodes(list(expected), list(heard)):
        if tag == "equal":
            for k, l in zip(range(i1, i2), range(j1, j2)):
                alignment[k].add(l)
        elif tag == "replace":
            len_i, len_j = i2 - i1, j2 - j1
            for k in range(i1, i2):
                start = j1 + int((k - i1) * len_j / max(len_i, 1))
                end = j1 + int((k - i1 + 1) * len_j / max(len_i, 1))
                if start == end:
                    if j2 > j1:
                        alignment[k].add(min(start, j2 - 1))
                else:
                    alignment[k].update(range(start, end))
        elif tag == "insert":
            k = i1 - 1 if i1 > 0 else i1
            if k < len(alignment):
                alignment[k].update(range(j1, j2))
    return alignment


def heard_lists(candidate: list[str], actual: list[str]) -> list[list[str]]:
    actual = list(actual)
    alignment = align_heard(candidate, actual)
    return [[actual[j] for j in sorted(idxs) if 0 <= j < len(actual)] for idxs in alignment]


def load_done(path: Path) -> set[int]:
    done = set()
    if not path.exists():
        return done
    keep = []
    with path.open() as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                done.add(int(json.loads(line)["row_id"]))
                keep.append(line)
            except json.JSONDecodeError:
                continue
    if len(keep) != sum(1 for _ in path.open()):
        path.write_text("\n".join(keep) + ("\n" if keep else ""))
    return done


def b39_index() -> dict[tuple[str, str], int]:
    runs = pd.read_csv(B_RUNS)
    orig = runs[runs.cond == "orig"]
    return {
        (norm_speaker(r.speaker), str(r.text)): int(r.idx)
        for r in orig.itertuples(index=False)
    }


def score_words(text: str, wav: np.ndarray) -> tuple[list[dict], dict]:
    from openpronounce import phones as op_phones

    recognition = op_phones.recognize_phones(wav)
    public = op_phones.compare_phones(recognition, text)
    reports = {rep["position"]: rep for rep in op_phones._word_reports(recognition, text)}
    flagged = {err["position"] for err in public["errors"]}
    words, groups = op_phones.get_expected_phones(text)
    op_words = []
    flag_disagree = 0
    for pos, (word, group) in enumerate(zip(words, groups)):
        rep = reports.get(pos)
        if rep is None:
            op_words.append({
                "word": word,
                "expected": list(group),
                "candidate": list(group),
                "confidence": [0.0] * len(group),
                "heard": [[phone] for phone in group],
                "distance": 0,
                "word_flagged": pos in flagged,
            })
            continue
        if rep["phones"]:
            candidate = [phone["expected"] for phone in rep["phones"]]
            confidence = [round(float(phone["confidence"]), 3) for phone in rep["phones"]]
            edits = sum(float(phone["confidence"]) for phone in rep["phones"])
            length = max(1, len(rep["expected"]))
            formula = bool(rep["distance"]) and (
                edits / length >= op_phones.PHONE_ERROR_THRESHOLD
                or edits >= op_phones.PHONE_ERROR_MIN_EDITS
            )
            if formula != (pos in flagged):
                flag_disagree += 1
        else:
            candidate = list(rep["expected"])
            confidence = [0.0] * len(candidate)
        heard = heard_lists(candidate, list(rep["actual"]))
        if len(heard) != len(candidate):
            raise RuntimeError(f"heard/candidate length {len(heard)} != {len(candidate)} for {word!r}")
        op_words.append({
            "word": rep["word"],
            "expected": list(rep["expected"]),
            "candidate": candidate,
            "confidence": confidence,
            "heard": heard,
            "distance": int(rep["distance"]),
            "word_flagged": pos in flagged,
        })
    audit = {
        "phoneme_error_rate": public["phone_error_rate"],
        "n_word_errors": len(public["errors"]),
        "flag_disagree": flag_disagree,
        "heard_phones": public["heard_phones"],
    }
    return op_words, audit


def age_block(ages: list[int]) -> dict:
    series = pd.Series(ages)
    return {
        "n": int(series.size),
        "min": int(series.min()) if len(series) else None,
        "p25": None if series.empty else round(float(series.quantile(0.25)), 1),
        "median": None if series.empty else round(float(series.median()), 1),
        "p75": None if series.empty else round(float(series.quantile(0.75)), 1),
        "max": int(series.max()) if len(series) else None,
        "mean": None if series.empty else round(float(series.mean()), 2),
        "n_under_18": int((series < 18).sum()),
        "n_18_or_over": int((series >= 18).sum()),
    }


def word_flag_agreement(records: list[dict]) -> dict:
    words = pd.read_csv(B_WORDS)
    by_idx = {idx: grp for idx, grp in words.groupby("idx")}
    n_words = 0
    n_agree = 0
    missing = 0
    for rec in records:
        if rec.get("b39_idx") is None:
            continue
        ref = by_idx.get(int(rec["b39_idx"]))
        if ref is None:
            missing += 1
            continue
        pred = [w["word"] for w in rec["op_words"]]
        flags = [bool(w["word_flagged"]) for w in rec["op_words"]]
        ref_words = ref.word.str.lower().tolist()
        ref_flags = ref.flagged.astype(bool).tolist()
        if pred != ref_words:
            # Annotation words can differ from the phonemizer's word list by a
            # token; compare the shared prefix only when the sequences diverge.
            n = min(len(pred), len(ref_words))
            for i in range(n):
                if pred[i] != ref_words[i]:
                    break
                n_words += 1
                n_agree += int(flags[i] == ref_flags[i])
            continue
        n_words += len(pred)
        n_agree += sum(int(a == b) for a, b in zip(flags, ref_flags))
    return {
        "n_words_compared": n_words,
        "n_flag_agree": n_agree,
        "agreement": None if n_words == 0 else round(n_agree / n_words, 4),
        "n_b39_missing_from_words_csv": missing,
    }


def write_metrics(records: list[dict]) -> dict:
    from align import summarize

    phone_rows = []
    sub_rows = []
    notes = Counter()
    b39_phones = []
    b39_subs = []
    for rec in records:
        if rec.get("failed"):
            notes["failed_utterances"] += 1
            continue
        phones, subs, utt_notes = summarize_one(rec)
        phone_rows.extend(phones)
        sub_rows.extend(subs)
        notes.update(utt_notes)
        if rec["in_b39"]:
            b39_phones.extend(phones)
            b39_subs.extend(subs)
    full = summarize(phone_rows, sub_rows, notes)
    subset = summarize(b39_phones, b39_subs, Counter())
    # The subset is a report, not a second place to move the gate.
    subset.pop("by_phone", None)
    subset.pop("direction_focus", None)
    ages = [int(r["age"]) for r in records if not r.get("failed")]
    b_ages = [int(r["age"]) for r in records if r.get("in_b39") and not r.get("failed")]
    versions = package_versions()
    result = {
        "sample": {
            "corpus": "mispeech/speechocean762 test split",
            "n_utterances_scored": sum(1 for r in records if not r.get("failed")),
            "n_failed": sum(1 for r in records if r.get("failed")),
            "includes_experiment_b_39": sum(1 for r in records if r.get("in_b39") and not r.get("failed")),
            "why_not_only_39": (
                "The 39 utterances contain 35 phones with phones-accuracy < 0.5 "
                "(2 of them TH/DH, 0 V). Focus-phone gates need the full test split. "
                "That count was computed from the labels before any OpenPronounce call."
            ),
            "age_full": age_block(ages),
            "age_b39": age_block(b_ages),
        },
        "full_test": full,
        "subset_experiment_b": subset,
        "word_flag_agreement_with_experiment_b": word_flag_agreement(records),
        "versions": versions,
        "seconds_median": _median([r.get("sec") for r in records if r.get("sec") is not None]),
    }
    phones_df = pd.DataFrame(phone_rows)
    subs_df = pd.DataFrame(sub_rows)
    phones_df.to_csv(HERE / "phones.csv", index=False)
    subs_df.to_csv(HERE / "substitutions.csv", index=False)
    by_phone = pd.DataFrame(full["by_phone"])
    by_phone.to_csv(HERE / "by_phone.csv", index=False)
    (HERE / "results.json").write_text(json.dumps(result, indent=1, ensure_ascii=False) + "\n")
    return result


def summarize_one(rec: dict):
    from align import score_utterance
    return score_utterance(rec)


def _median(values) -> float | None:
    nums = sorted(float(v) for v in values if v is not None)
    if not nums:
        return None
    mid = len(nums) // 2
    if len(nums) % 2:
        return round(nums[mid], 3)
    return round((nums[mid - 1] + nums[mid]) / 2, 3)


def package_versions() -> dict:
    import torch
    from importlib.metadata import version

    names = ["openpronounce", "transformers", "phonemizer", "numpy", "pandas"]
    out = {"python": sys.version.split()[0], "torch": torch.__version__}
    for name in names:
        try:
            out[name] = version(name)
        except Exception:
            out[name] = None
    return out


def main() -> None:
    metrics_only = "--metrics-only" in sys.argv
    limit = int(os.environ.get("HEARSAY_EXP_D_LIMIT", "0"))
    if metrics_only:
        records = [json.loads(line) for line in JSONL.read_text().splitlines() if line.strip()]
        result = write_metrics(records)
        print(json.dumps({
            "primary": result["full_test"]["primary"],
            "direction": result["full_test"]["direction"],
            "focus": result["full_test"]["focus"],
            "b39_primary": result["subset_experiment_b"]["primary"],
        }, indent=1, ensure_ascii=False))
        return

    import torch
    torch.set_num_threads(int(os.environ.get("OMP_NUM_THREADS", "4")))

    df = pd.read_parquet(DATA)
    b39 = b39_index()
    done = load_done(JSONL)
    n_target = len(df) if limit <= 0 else min(limit, len(df))
    print(f"rows {len(df)} already {len(done)} target {n_target}", flush=True)

    t_all = time.time()
    n_new = 0
    with JSONL.open("a") as fh:
        for row_id, row in df.iterrows():
            row_id = int(row_id)
            if row_id >= n_target:
                break
            if row_id in done:
                continue
            speaker = norm_speaker(row["speaker"])
            text = str(row["text"])
            rec = {
                "row_id": row_id,
                "speaker": speaker,
                "age": int(row["age"]),
                "gender": str(row["gender"]),
                "text": text,
                "human_total": int(row["total"]),
                "human_accuracy": int(row["accuracy"]),
                "in_b39": (speaker, text) in b39,
                "b39_idx": b39.get((speaker, text)),
            }
            t0 = time.time()
            try:
                wav = decode(row["audio"])
                op_words, audit = score_words(text, wav)
                rec.update({
                    "gt_words": gt_words_of(row["words"]),
                    "op_words": op_words,
                    "phoneme_error_rate": audit["phoneme_error_rate"],
                    "n_word_errors": audit["n_word_errors"],
                    "flag_disagree": audit["flag_disagree"],
                    "sec": round(time.time() - t0, 3),
                    "failed": None,
                })
            except Exception as exc:  # keep going; a failed row stays in the file
                rec.update({
                    "failed": f"{type(exc).__name__}: {exc}",
                    "traceback": traceback.format_exc().splitlines()[-3:],
                    "sec": round(time.time() - t0, 3),
                })
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
            fh.flush()
            n_new += 1
            if n_new % 25 == 0 or rec.get("failed"):
                elapsed = time.time() - t_all
                print(
                    f"row {row_id} new {n_new} {elapsed:.0f}s failed={bool(rec.get('failed'))} "
                    f"{text[:40]!r}",
                    flush=True,
                )
    print(f"scored_new {n_new} in {time.time() - t_all:.0f}s", flush=True)
    if limit > 0:
        print("limit set; not writing results.json", flush=True)
        return
    records = [json.loads(line) for line in JSONL.read_text().splitlines() if line.strip()]
    if len(records) < len(df):
        print(f"jsonl has {len(records)} of {len(df)}; not writing official metrics", flush=True)
        return
    result = write_metrics(records)
    primary = result["full_test"]["primary"]
    direction = result["full_test"]["direction"]
    print(json.dumps({"primary": primary, "direction": direction, "focus": result["full_test"]["focus"]}, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
