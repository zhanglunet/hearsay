"""Align OpenPronounce IPA phones with speechocean762 ARPAbet annotations.

The scoring rules in this file were fixed before the model run. ``run.py`` only
feeds them saved recognizer output; it does not retune them.

Ground truth
    speechocean762 ``phones-accuracy`` is an average on a 0–2 scale. A
    mispronunciation record exists exactly when that score is < 0.5. The
    primary positive class is therefore ``phones-accuracy < 0.5``. Scores
    < 1.0 are reported only as a sensitivity check.

Primary detector (what ``compare_audio_with_text`` puts in ``differences.errors``)
    A ground-truth phone is predicted wrong when its word is in ``errors``
    and the aligned phone's reported confidence is > 0.

Gates
    precision >= 0.60 and recall >= 0.50 on the primary detector
    (0.60 matches the learner-model rule that confidence < 0.6 does not enter
    ErrorPattern statistics);
    substitution-direction accuracy >= 0.70 on crisp mispronunciation labels;
    each focus group with at least 15 ground-truth errors: precision >= 0.50
    and recall >= 0.40. Fewer than 15 errors is ``insufficient_support``.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from difflib import SequenceMatcher

# --- thresholds (do not tune after seeing scores) ---
GT_ERROR_LT = 0.5
GT_ERROR_LT_SENSITIVITY = 1.0
GATE_PRECISION = 0.60
GATE_RECALL = 0.50
GATE_DIRECTION_ACC = 0.70
GATE_FOCUS_MIN_POSITIVES = 15
GATE_FOCUS_PRECISION = 0.50
GATE_FOCUS_RECALL = 0.40
CONF_HIGH = 0.5

VOWELS = {
    "IY", "IH", "EY", "EH", "AE", "AA", "AO", "AH", "AX",
    "UW", "UH", "OW", "AY", "AW", "OY", "ER",
}

# OpenPronounce already normalizes with these rules (phones.normalize_phone, lang=en).
# Applied again so a raw espeak token and a stored token map the same way.
_ALIASES = {
    "th": "t", "kh": "k", "ph": "p", "tʰ": "t", "kʰ": "k", "pʰ": "p",
    "ai": "aɪ", "ei": "eɪ", "au": "aʊ", "ou": "oʊ",
}
_PHONE_MAP = {"ᵻ": "ɪ", "ɐ": "ə", "ɔ": "ɑ", "ɔɹ": "oɹ", "ɜ": "ɚ", "ɾ": "t", "ɫ": "l"}

# One normalized IPA token -> one or more ARPAbet bases (no stress).
# AA/AO stay distinct here; alignment treats them as equivalent below because
# OpenPronounce merges the cot-caught pair (ɔ → ɑ) and so cannot emit AO.
SINGLE = {
    "p": "P", "b": "B", "t": "T", "d": "D", "k": "K", "ɡ": "G", "g": "G",
    "m": "M", "n": "N", "ŋ": "NG",
    "f": "F", "v": "V", "θ": "TH", "ð": "DH", "s": "S", "z": "Z",
    "ʃ": "SH", "ʒ": "ZH", "h": "HH",
    "tʃ": "CH", "dʒ": "JH",
    "l": "L", "ɹ": "R", "r": "R", "w": "W", "j": "Y",
    "i": "IY", "ɪ": "IH", "ɛ": "EH", "æ": "AE",
    "ɑ": "AA", "ʌ": "AH", "ə": "AH",
    "u": "UW", "ʊ": "UH",
    "eɪ": "EY", "oʊ": "OW", "aɪ": "AY", "aʊ": "AW", "ɔɪ": "OY",
    "ɚ": "ER",
    # Leftovers that survive English normalization. ``o`` is length-stripped
    # espeak ``oː`` (FORCE/NORTH, as in "four" -> f o ɹ), i.e. ARPAbet AO,
    # not the GOAT diphthong oʊ. ``e`` / ``a`` are recognizer leftovers.
    # Occurrences are counted as approx_ipa in the results.
    "e": "EH", "o": "AO", "a": "AA",
}
APPROX_IPA = {"e", "o", "a"}
MULTI = {
    "ɑɹ": ("AA", "R"),
    "oɹ": ("AO", "R"),
    "ɛɹ": ("EH", "R"),
    "ɪɹ": ("IH", "R"),
    "ʊɹ": ("UH", "R"),
    "əl": ("AH", "L"),
    "iə": ("IY", "AH"),
}

FOCUS_GROUPS = (
    ("TH_DH", "P01", lambda base, pos: base in {"TH", "DH"}),
    ("L_N", "P03", lambda base, pos: base in {"L", "N"}),
    ("V_W", "P02", lambda base, pos: base in {"V", "W"}),
    ("final_consonant", "P05", lambda base, pos: pos == "final" and base not in VOWELS),
    ("IH_IY", "P08", lambda base, pos: base in {"IH", "IY"}),
)


def normalize_ipa(phone: str) -> str:
    phone = re.sub(r"\d", "", phone.replace("ː", ""))
    phone = _ALIASES.get(phone, phone)
    return _PHONE_MAP.get(phone, phone)


def ipa_to_arpa(phone: str) -> list[str] | None:
    """Return ARPAbet bases for one IPA token, or None if the token is unknown."""
    phone = normalize_ipa(phone)
    if phone in MULTI:
        return list(MULTI[phone])
    mapped = SINGLE.get(phone)
    if mapped is None:
        return None
    return [mapped]


def base_arpa(phone: str) -> str:
    return re.sub(r"\d", "", str(phone))


def phones_equivalent(a: str, b: str) -> bool:
    if a == b:
        return True
    return {a, b} == {"AA", "AO"}


def position_of(index: int, n_phones: int) -> str:
    """Last phone is ``final`` (a one-phone word is a coda for P05). Otherwise onset or medial."""
    if index == n_phones - 1:
        return "final"
    if index == 0:
        return "initial"
    return "medial"


def expand_ipa(phones: list[str]) -> tuple[list[tuple[str, int]], list[str]]:
    """Expand an IPA sequence to ``(arpabet, source_index)`` tokens.

    ``source_index`` points at the IPA phone the token came from. Unknown IPA
    becomes a single non-matching placeholder so it cannot align as equal.
    The second return value lists unknown IPA tokens.
    """
    tokens: list[tuple[str, int]] = []
    unknown: list[str] = []
    for i, phone in enumerate(phones):
        parts = ipa_to_arpa(phone)
        if parts is None:
            unknown.append(normalize_ipa(phone))
            tokens.append((f"UNK:{normalize_ipa(phone)}", i))
            continue
        for part in parts:
            tokens.append((part, i))
    return tokens, unknown


def align_tokens(left: list[str], right: list[str]) -> list[tuple[int | None, int | None]]:
    """Globally align two ARPAbet sequences. Pair ``(left_i, right_i)``; None is a gap.

    Match cost is 0 when :func:`phones_equivalent` is true, else 1. Indel cost is 1.
    Ties prefer a diagonal step, then consuming ``left`` (deletion), then ``right``.
    """
    n, m = len(left), len(right)
    cost = [[0] * (m + 1) for _ in range(n + 1)]
    back = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(1, n + 1):
        cost[i][0] = i
        back[i][0] = 1
    for j in range(1, m + 1):
        cost[0][j] = j
        back[0][j] = 2
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            sub = 0 if phones_equivalent(left[i - 1], right[j - 1]) else 1
            choices = (
                (cost[i - 1][j - 1] + sub, 0),
                (cost[i - 1][j] + 1, 1),
                (cost[i][j - 1] + 1, 2),
            )
            best = min(choices)
            cost[i][j] = best[0]
            back[i][j] = best[1]
    pairs: list[tuple[int | None, int | None]] = []
    i, j = n, m
    while i > 0 or j > 0:
        step = back[i][j]
        if i > 0 and j > 0 and step == 0:
            pairs.append((i - 1, j - 1))
            i, j = i - 1, j - 1
        elif i > 0 and (j == 0 or step == 1):
            pairs.append((i - 1, None))
            i -= 1
        else:
            pairs.append((None, j - 1))
            j -= 1
    pairs.reverse()
    return pairs


def parse_pronounced(label: str) -> list[str] | None:
    """Parse a speechocean762 ``pronounced-phone``.

    Returns a list of ARPAbet bases (empty list means ``<DEL>``).
    Returns None when the label is inexact (``<unk>``, trailing ``*``) or unexpected.
    """
    text = str(label).strip()
    if text == "<DEL>":
        return []
    tokens = text.split()
    if not tokens or any(tok == "<unk>" or "*" in tok or tok == "<DEL>" for tok in tokens):
        return None
    if any(re.fullmatch(r"[A-Z]+", tok) is None for tok in tokens):
        return None
    return tokens


def sequences_match(hyp: list[str], ref: list[str]) -> bool:
    if len(hyp) != len(ref):
        return False
    return all(phones_equivalent(a, b) for a, b in zip(hyp, ref))


def _link_equal(src_phones: list[str], dst_phones: list[str]) -> dict[int, int]:
    """Map a destination IPA index to a source IPA index when their ARPAbet expansions align as equal.

    If one source phone expands to several tokens, every equal destination token
    that came from the same source keeps that source. A destination phone whose
    tokens disagree, or that does not fully match, is left unmapped.
    """
    src_tokens, _ = expand_ipa(src_phones)
    dst_tokens, _ = expand_ipa(dst_phones)
    grouped: dict[int, list[int]] = {}
    for left_i, right_i in align_tokens(
        [tok for tok, _ in src_tokens], [tok for tok, _ in dst_tokens]
    ):
        if left_i is None or right_i is None:
            if right_i is not None:
                grouped.setdefault(dst_tokens[right_i][1], [])
            continue
        if phones_equivalent(src_tokens[left_i][0], dst_tokens[right_i][0]):
            grouped.setdefault(dst_tokens[right_i][1], []).append(src_tokens[left_i][1])
        else:
            grouped.setdefault(dst_tokens[right_i][1], [])
    out: dict[int, int] = {}
    for dst_i, src_is in grouped.items():
        if src_is and all(s == src_is[0] for s in src_is):
            # Require every expanded token of this destination phone to have matched.
            n_dst_tokens = sum(1 for _, idx in dst_tokens if idx == dst_i)
            if len(src_is) == n_dst_tokens:
                out[dst_i] = src_is[0]
    return out


def _heard_arpa(heard_ipa: list[str]) -> tuple[list[str] | None, list[str]]:
    parts: list[str] = []
    unknown: list[str] = []
    for phone in heard_ipa:
        mapped = ipa_to_arpa(phone)
        if mapped is None:
            unknown.append(normalize_ipa(phone))
            return None, unknown
        parts.extend(mapped)
    return parts, unknown


def pr_counts(rows: list[dict], pred_key: str, truth_key: str = "gt_error") -> dict:
    evaluable = [r for r in rows if r["aligned"]]
    tp = sum(1 for r in evaluable if r[truth_key] and r[pred_key])
    fp = sum(1 for r in evaluable if (not r[truth_key]) and r[pred_key])
    fn = sum(1 for r in evaluable if r[truth_key] and (not r[pred_key]))
    tn = sum(1 for r in evaluable if (not r[truth_key]) and (not r[pred_key]))
    precision = tp / (tp + fp) if (tp + fp) else None
    recall = tp / (tp + fn) if (tp + fn) else None
    return {
        "n_evaluable": len(evaluable),
        "n_gt_error": tp + fn,
        "n_pred": tp + fp,
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "tn": tn,
        "precision": None if precision is None else round(precision, 4),
        "recall": None if recall is None else round(recall, 4),
        "wilson_precision": _wilson(tp, tp + fp),
        "wilson_recall": _wilson(tp, tp + fn),
    }


def _wilson(k: int, n: int, z: float = 1.96) -> list[float] | None:
    if n <= 0:
        return None
    p = k / n
    den = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / den
    margin = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return [round(max(0.0, centre - margin), 4), round(min(1.0, centre + margin), 4)]


def repetition_k(precision: float | None) -> dict:
    """How many independent flags before a confirmed P-class ErrorInstance.

    Floor of 3 utterances even when precision clears 0.60 (one shadow sentence
    is not a pattern). When precision is lower, smallest k with (1 - p)^k <= 0.05.
    k > 8 means repetition alone does not make the flag safe to confirm.
    """
    if precision is None:
        return {"k": None, "auto_confirm": False, "reason": "precision_undefined"}
    if precision >= GATE_PRECISION:
        return {
            "k": 3,
            "auto_confirm": True,
            "reason": "precision_meets_gate_still_require_3_utterances",
        }
    fp = 1 - precision
    if fp <= 0:
        return {"k": 3, "auto_confirm": True, "reason": "no_false_positives_in_sample"}
    k = math.ceil(math.log(0.05) / math.log(fp))
    k = max(k, 3)
    if k > 8:
        return {
            "k": None,
            "auto_confirm": False,
            "k_would_be": int(k),
            "reason": "false_positive_rate_too_high_to_confirm_by_repetition",
        }
    return {
        "k": int(k),
        "auto_confirm": True,
        "reason": "repetition_brings_all_false_confirm_probability_to_at_most_0.05",
    }


def _blank_phone(utt: dict, g: dict, gt_i: int, base: str, acc: float) -> dict:
    return {
        "row_id": utt["row_id"],
        "in_b39": bool(utt["in_b39"]),
        "speaker": utt["speaker"],
        "age": utt["age"],
        "word": g["text"],
        "phone_index": gt_i,
        "arpabet": base,
        "position": position_of(gt_i, len(g["phones"])),
        "gt_accuracy": round(acc, 4),
        "gt_error": acc < GT_ERROR_LT,
        "gt_error_lt_1": acc < GT_ERROR_LT_SENSITIVITY,
        "aligned": False,
        "aa_ao_equivalence": False,
        "op_expected_ipa": None,
        "op_heard_ipa": "",
        "op_confidence": None,
        "word_flagged": False,
        "pred_primary": False,
        "pred_conf50": False,
        "pred_ungeared": False,
        "pred_ungeared_50": False,
        "pred_raw": False,
    }


def _blank_sub(utt: dict, g: dict, mis: dict, reason: str) -> dict:
    return {
        "row_id": utt["row_id"],
        "in_b39": bool(utt["in_b39"]),
        "word": g["text"],
        "phone_index": int(mis["index"]),
        "canonical": base_arpa(mis["canonical"]),
        "pronounced": str(mis["pronounced"]),
        "crisp": parse_pronounced(mis["pronounced"]) is not None,
        "aligned": False,
        "direction_match": False,
        "reason": reason,
        "op_expected_ipa": None,
        "op_heard_ipa": None,
        "expected_arpa": None,
        "heard_arpa": None,
    }


def score_utterance(utt: dict) -> tuple[list[dict], list[dict], Counter]:
    """Return per-phone rows, substitution rows, and a counter of oddities."""
    notes: Counter = Counter()
    phone_rows: list[dict] = []
    sub_rows: list[dict] = []
    gt_words = utt["gt_words"]
    op_words = utt["op_words"]
    gt_text = [g["text"].lower() for g in gt_words]
    op_text = [o["word"] for o in op_words]
    pairs: list[tuple[dict, dict | None]] = []
    if gt_text == op_text:
        pairs = list(zip(gt_words, op_words))
    else:
        notes["word_sequence_mismatch"] += 1
        matcher = SequenceMatcher(a=gt_text, b=op_text, autojunk=False)
        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            if tag == "equal":
                pairs.extend(zip(gt_words[i1:i2], op_words[j1:j2]))
            else:
                pairs.extend((g, None) for g in gt_words[i1:i2])
                notes["gt_words_unpaired"] += i2 - i1

    for g, o in pairs:
        if o is None:
            for gt_i, phone in enumerate(g["phones"]):
                phone_rows.append(_blank_phone(utt, g, gt_i, base_arpa(phone), float(g["phones_accuracy"][gt_i])))
            for mis in g["mispronunciations"]:
                sub_rows.append(_blank_sub(utt, g, mis, "unaligned"))
            continue
        citation = list(o["expected"])
        candidate = list(o["candidate"])
        conf = list(o["confidence"])
        heard = list(o["heard"])
        if not (len(candidate) == len(conf) == len(heard)):
            notes["candidate_shape_mismatch"] += 1
            for gt_i, phone in enumerate(g["phones"]):
                phone_rows.append(_blank_phone(
                    utt, g, gt_i, base_arpa(phone), float(g["phones_accuracy"][gt_i])
                ))
            for mis in g["mispronunciations"]:
                sub_rows.append(_blank_sub(utt, g, mis, "unaligned"))
            continue
        citation_to_cand = {}
        if candidate == citation:
            citation_to_cand = {i: i for i in range(len(citation))}
        else:
            notes["candidate_differs"] += 1
            citation_to_cand = _link_equal(candidate, citation)

        cit_tokens, unknown = expand_ipa(citation)
        notes["approx_ipa"] += sum(1 for p in citation if normalize_ipa(p) in APPROX_IPA)
        for tok in unknown:
            notes[f"unknown_ipa:{tok}"] += 1
        gt_bases = [base_arpa(p) for p in g["phones"]]
        gt_acc = [float(x) for x in g["phones_accuracy"]]
        aligned_src: dict[int, int] = {}
        for left_i, right_i in align_tokens(gt_bases, [tok for tok, _ in cit_tokens]):
            if left_i is None or right_i is None:
                continue
            if phones_equivalent(gt_bases[left_i], cit_tokens[right_i][0]):
                src = cit_tokens[right_i][1]
                # A GT phone that matches several citation tokens (should not, 1-1
                # bases) keeps the first only when they agree.
                aligned_src.setdefault(left_i, src)

        n_ph = len(gt_bases)
        for gt_i, base in enumerate(gt_bases):
            pos = position_of(gt_i, n_ph)
            acc = gt_acc[gt_i]
            src = aligned_src.get(gt_i)
            aligned = src is not None
            equiv = False
            op_expected_ipa = None
            op_heard_ipa: list[str] = []
            op_conf = None
            pred_primary = False
            pred_conf50 = False
            pred_ungeared = False
            pred_ungeared_50 = False
            pred_raw = False
            if aligned:
                op_expected_ipa = citation[src]
                mapped_expected = ipa_to_arpa(op_expected_ipa) or []
                equiv = base not in mapped_expected and any(
                    phones_equivalent(base, part) for part in mapped_expected
                )
                cand_i = citation_to_cand.get(src)
                if cand_i is None:
                    notes["citation_not_in_candidate"] += 1
                    op_conf = 0.0
                    op_heard_ipa = []
                else:
                    op_conf = float(conf[cand_i])
                    op_heard_ipa = list(heard[cand_i])
                flagged = bool(o["word_flagged"])
                positive = op_conf > 0
                high = op_conf >= CONF_HIGH
                pred_primary = flagged and positive
                pred_conf50 = flagged and high
                pred_ungeared = positive
                pred_ungeared_50 = high
                if int(o["distance"]) == 0:
                    pred_raw = False
                else:
                    heard_arpa, unk_h = _heard_arpa(op_heard_ipa)
                    for tok in unk_h:
                        notes[f"unknown_ipa:{tok}"] += 1
                    expected_one = ipa_to_arpa(candidate[cand_i]) if cand_i is not None else mapped_expected
                    if heard_arpa is None or expected_one is None:
                        pred_raw = True
                    else:
                        pred_raw = not sequences_match(heard_arpa, expected_one)
            phone_rows.append({
                "row_id": utt["row_id"],
                "in_b39": bool(utt["in_b39"]),
                "speaker": utt["speaker"],
                "age": utt["age"],
                "word": g["text"],
                "phone_index": gt_i,
                "arpabet": base,
                "position": pos,
                "gt_accuracy": round(acc, 4),
                "gt_error": acc < GT_ERROR_LT,
                "gt_error_lt_1": acc < GT_ERROR_LT_SENSITIVITY,
                "aligned": aligned,
                "aa_ao_equivalence": equiv,
                "op_expected_ipa": op_expected_ipa,
                "op_heard_ipa": " ".join(op_heard_ipa),
                "op_confidence": op_conf,
                "word_flagged": bool(o["word_flagged"]),
                "pred_primary": pred_primary,
                "pred_conf50": pred_conf50,
                "pred_ungeared": pred_ungeared,
                "pred_ungeared_50": pred_ungeared_50,
                "pred_raw": pred_raw,
            })

        by_index = {gt_i: row for gt_i, row in enumerate(phone_rows[-n_ph:])}
        for mis in g["mispronunciations"]:
            idx = int(mis["index"])
            canonical = base_arpa(mis["canonical"])
            pronounced = str(mis["pronounced"])
            crisp = parse_pronounced(pronounced)
            row = by_index.get(idx)
            reason = "ok"
            matched = False
            expected_arpa = None
            heard_arpa_list = None
            if row is None or canonical != row["arpabet"]:
                reason = "index_mismatch"
                notes["mis_index_mismatch"] += 1
            elif not row["aligned"]:
                reason = "unaligned"
            elif crisp is None:
                reason = "inexact_gt"
            else:
                expected_arpa = ipa_to_arpa(row["op_expected_ipa"]) if row["op_expected_ipa"] else None
                heard_arpa_list, unk_h = _heard_arpa(row["op_heard_ipa"].split() if row["op_heard_ipa"] else [])
                for tok in unk_h:
                    notes[f"unknown_ipa:{tok}"] += 1
                if expected_arpa is None or heard_arpa_list is None:
                    reason = "unmapped_heard"
                elif not any(phones_equivalent(canonical, part) for part in expected_arpa):
                    reason = "expected_mismatch"
                elif sequences_match(heard_arpa_list, crisp):
                    matched = True
                    reason = "match"
                else:
                    reason = "direction_mismatch"
            sub_rows.append({
                "row_id": utt["row_id"],
                "in_b39": bool(utt["in_b39"]),
                "word": g["text"],
                "phone_index": idx,
                "canonical": canonical,
                "pronounced": pronounced,
                "crisp": crisp is not None,
                "aligned": bool(row and row["aligned"]),
                "direction_match": matched,
                "reason": reason,
                "op_expected_ipa": None if row is None else row["op_expected_ipa"],
                "op_heard_ipa": None if row is None else row["op_heard_ipa"],
                "expected_arpa": " ".join(expected_arpa) if expected_arpa else None,
                "heard_arpa": " ".join(heard_arpa_list) if heard_arpa_list is not None else None,
            })
    return phone_rows, sub_rows, notes


def _round_pair(block: dict) -> dict:
    return block


def focus_table(rows: list[dict], pred_key: str = "pred_primary") -> list[dict]:
    table = []
    for name, code, pred in FOCUS_GROUPS:
        subset = [
            r for r in rows
            if r["aligned"] and pred(r["arpabet"], r["position"])
        ]
        stats = pr_counts(subset, pred_key)
        n_err = stats["n_gt_error"]
        enough = n_err >= GATE_FOCUS_MIN_POSITIVES
        met = None
        if enough and stats["precision"] is not None and stats["recall"] is not None:
            met = stats["precision"] >= GATE_FOCUS_PRECISION and stats["recall"] >= GATE_FOCUS_RECALL
        table.append({
            "group": name,
            "error_code": code,
            "support": "evaluable" if enough else "insufficient_support",
            "gate_met": met,
            **stats,
        })
    return table


def by_phone_table(rows: list[dict], pred_key: str = "pred_primary") -> list[dict]:
    phones = sorted({r["arpabet"] for r in rows if r["aligned"]})
    table = []
    for phone in phones:
        subset = [r for r in rows if r["aligned"] and r["arpabet"] == phone]
        stats = pr_counts(subset, pred_key)
        stats["arpabet"] = phone
        table.append(stats)
    table.sort(key=lambda r: (-r["n_gt_error"], -r["n_evaluable"], r["arpabet"]))
    return table


def direction_summary(sub_rows: list[dict]) -> dict:
    crisp_aligned = [
        r for r in sub_rows
        if r["crisp"] and r["aligned"] and r["reason"] != "index_mismatch"
    ]
    # Primary denominator: crisp labels that aligned and could be compared
    # (expected side mapped). unaligned and inexact are excluded, not failed.
    primary = [r for r in crisp_aligned if r["reason"] in {"match", "direction_mismatch", "expected_mismatch", "unmapped_heard"}]
    n_match = sum(1 for r in primary if r["direction_match"])
    n = len(primary)
    acc = n_match / n if n else None
    return {
        "n_mispronunciations": len(sub_rows),
        "n_inexact_excluded": sum(1 for r in sub_rows if r["reason"] == "inexact_gt"),
        "n_unaligned_excluded": sum(1 for r in sub_rows if r["reason"] == "unaligned"),
        "n_index_mismatch": sum(1 for r in sub_rows if r["reason"] == "index_mismatch"),
        "n_primary": n,
        "n_match": n_match,
        "accuracy": None if acc is None else round(acc, 4),
        "wilson": _wilson(n_match, n),
        "gate_met": None if acc is None else acc >= GATE_DIRECTION_ACC,
        "reason_counts": dict(Counter(r["reason"] for r in sub_rows)),
    }


def summarize(phone_rows: list[dict], sub_rows: list[dict], notes: Counter) -> dict:
    primary = pr_counts(phone_rows, "pred_primary")
    conf50 = pr_counts(phone_rows, "pred_conf50")
    ungeared = pr_counts(phone_rows, "pred_ungeared")
    ungeared_50 = pr_counts(phone_rows, "pred_ungeared_50")
    raw = pr_counts(phone_rows, "pred_raw")
    sensitivity = pr_counts(phone_rows, "pred_primary", "gt_error_lt_1")
    direction = direction_summary(sub_rows)
    n_gt = len(phone_rows)
    n_aligned = sum(1 for r in phone_rows if r["aligned"])
    n_gt_error_unaligned = sum(1 for r in phone_rows if r["gt_error"] and not r["aligned"])
    prec_ok = primary["precision"] is not None and primary["precision"] >= GATE_PRECISION
    rec_ok = primary["recall"] is not None and primary["recall"] >= GATE_RECALL
    return {
        "thresholds": {
            "gt_error_phones_accuracy_lt": GT_ERROR_LT,
            "sensitivity_phones_accuracy_lt": GT_ERROR_LT_SENSITIVITY,
            "primary_detector": "word_in_differences.errors AND phone confidence > 0",
            "gate_precision": GATE_PRECISION,
            "gate_recall": GATE_RECALL,
            "gate_direction_accuracy": GATE_DIRECTION_ACC,
            "gate_focus_min_gt_errors": GATE_FOCUS_MIN_POSITIVES,
            "gate_focus_precision": GATE_FOCUS_PRECISION,
            "gate_focus_recall": GATE_FOCUS_RECALL,
            "high_confidence": CONF_HIGH,
            "aa_ao_treated_as_equivalent_for_alignment": True,
        },
        "n_gt_phones": n_gt,
        "n_evaluable": n_aligned,
        "n_unaligned": n_gt - n_aligned,
        "n_gt_error_unaligned": n_gt_error_unaligned,
        "frac_evaluable": None if n_gt == 0 else round(n_aligned / n_gt, 4),
        "n_aa_ao_equivalence": sum(1 for r in phone_rows if r["aa_ao_equivalence"]),
        "primary": {**primary, "precision_met": prec_ok, "recall_met": rec_ok},
        "operating_points": {
            "word_gated_conf_gt_0": primary,
            "word_gated_conf_ge_0.5": conf50,
            "ignore_word_gate_conf_gt_0": ungeared,
            "ignore_word_gate_conf_ge_0.5": ungeared_50,
            "raw_expected_ne_heard": raw,
            "primary_detector_gt_accuracy_lt_1": sensitivity,
        },
        "direction": direction,
        "focus": focus_table(phone_rows),
        "by_phone": by_phone_table(phone_rows),
        "recommendation": {
            "error_instance": repetition_k(primary["precision"]),
            "error_instance_if_conf_ge_0.5": repetition_k(conf50["precision"]),
            "error_instance_if_ignore_word_gate_conf_ge_0.5": repetition_k(ungeared_50["precision"]),
            "common_substitution": (
                "set_from_modal_heard_arpabet_when_that_phone_has_count_ge_5_and_share_ge_0.6"
                if direction["gate_met"]
                else "leave_null_until_direction_accuracy_is_revalidated_at_or_above_0.70"
            ),
        },
        "focus_by_position": focus_by_position(phone_rows),
        "direction_focus": direction_focus(sub_rows),
        "notes": dict(notes),
    }


def focus_by_position(rows: list[dict]) -> list[dict]:
    """P03 asks for N/L by position. Same split for the other focus phones. Not a separate gate."""
    table = []
    for phone in ("TH", "DH", "L", "N", "V", "W", "IH", "IY"):
        for pos in ("initial", "medial", "final"):
            subset = [
                r for r in rows
                if r["aligned"] and r["arpabet"] == phone and r["position"] == pos
            ]
            if not subset:
                continue
            stats = pr_counts(subset, "pred_primary")
            stats["arpabet"] = phone
            stats["position"] = pos
            table.append(stats)
    return table


def direction_focus(sub_rows: list[dict]) -> list[dict]:
    focus = {"TH", "DH", "L", "N", "V", "W", "IH", "IY"}
    counts: Counter = Counter()
    for row in sub_rows:
        if row["canonical"] not in focus:
            continue
        heard = row["heard_arpa"] if row["heard_arpa"] else row["reason"]
        counts[(row["canonical"], row["pronounced"], heard, bool(row["direction_match"]))] += 1
    out = []
    for (canonical, pronounced, heard, matched), n in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])):
        out.append({
            "canonical": canonical,
            "pronounced": pronounced,
            "heard_arpa_or_reason": heard,
            "direction_match": matched,
            "n": n,
        })
    return out
