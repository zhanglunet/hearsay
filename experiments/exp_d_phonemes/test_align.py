"""Unit checks for the phoneme alignment rules. No model, no dataset."""

from align import (
    GATE_DIRECTION_ACC,
    GATE_PRECISION,
    ipa_to_arpa,
    parse_pronounced,
    repetition_k,
    score_utterance,
    summarize,
)


def _utt(gt_words, op_words):
    return {
        "row_id": 0,
        "in_b39": True,
        "speaker": "0001",
        "age": 10,
        "gt_words": gt_words,
        "op_words": op_words,
    }


def _op(word, expected, heard, confidence, flagged, distance):
    return {
        "word": word,
        "expected": expected,
        "candidate": expected,
        "confidence": confidence,
        "heard": heard,
        "distance": distance,
        "word_flagged": flagged,
    }


def test_ipa_map():
    assert ipa_to_arpa("θ") == ["TH"]
    assert ipa_to_arpa("ð") == ["DH"]
    assert ipa_to_arpa("ɪ") == ["IH"]
    assert ipa_to_arpa("iː") == ["IY"]
    assert ipa_to_arpa("ə") == ["AH"]
    assert ipa_to_arpa("ʌ") == ["AH"]
    assert ipa_to_arpa("ɚ") == ["ER"]
    assert ipa_to_arpa("ɹ") == ["R"]
    assert ipa_to_arpa("tʃ") == ["CH"]
    assert ipa_to_arpa("ɑ") == ["AA"]
    assert ipa_to_arpa("ɔɪ") == ["OY"]
    assert ipa_to_arpa("ɑːɹ") == ["AA", "R"]
    assert ipa_to_arpa("ɔːɹ") == ["AO", "R"]
    assert ipa_to_arpa("ɾ") == ["T"]


def test_rhotic_expansion_shares_one_op_decision():
    utt = _utt(
        [{"text": "MARK", "phones": ["M", "AA0", "R", "K"], "phones_accuracy": [2, 2, 2, 2], "mispronunciations": []}],
        [_op("mark", ["m", "ɑɹ", "k"], [["m"], ["ʌ"], ["k"]], [0.0, 1.0, 0.0], True, 1)],
    )
    phones, _, notes = score_utterance(utt)
    assert [p["arpabet"] for p in phones] == ["M", "AA", "R", "K"]
    assert [p["aligned"] for p in phones] == [True, True, True, True]
    assert [p["pred_primary"] for p in phones] == [False, True, True, False]
    assert phones[1]["op_heard_ipa"] == "ʌ"
    assert notes["unknown_ipa:ʌ"] == 0


def test_th_substitution_direction_and_detection():
    utt = _utt(
        [{
            "text": "THREE",
            "phones": ["TH", "R", "IY0"],
            "phones_accuracy": [0.2, 2, 2],
            "mispronunciations": [{"index": 0, "canonical": "TH", "pronounced": "S"}],
        }],
        [_op("three", ["θ", "ɹ", "i"], [["s"], ["ɹ"], ["i"]], [1.0, 0.0, 0.0], True, 1)],
    )
    phones, subs, _ = score_utterance(utt)
    assert phones[0]["gt_error"] is True and phones[0]["pred_primary"] is True
    assert phones[1]["pred_primary"] is False
    assert subs[0]["reason"] == "match" and subs[0]["direction_match"] is True
    summary = summarize(phones, subs, _)
    assert summary["primary"]["tp"] == 1 and summary["primary"]["fp"] == 0
    assert summary["direction"]["accuracy"] == 1.0


def test_deletion_and_inexact_labels():
    utt = _utt(
        [{
            "text": "BALL",
            "phones": ["B", "AO1", "L"],
            "phones_accuracy": [2, 2, 0.0],
            "mispronunciations": [
                {"index": 2, "canonical": "L", "pronounced": "<DEL>"},
            ],
        }],
        [_op("ball", ["b", "ɑ", "l"], [["b"], ["ɑ"], []], [0.0, 0.0, 1.0], True, 1)],
    )
    _, subs, _ = score_utterance(utt)
    assert subs[0]["reason"] == "match"
    # AO aligns to ɑ (AA) by the cot-caught equivalence, and is not an error.
    phones, _, _ = score_utterance(utt)
    assert phones[1]["arpabet"] == "AO" and phones[1]["aligned"] and phones[1]["aa_ao_equivalence"]
    assert phones[1]["pred_primary"] is False

    utt2 = _utt(
        [{
            "text": "LISA",
            "phones": ["L", "IY1", "S", "AH0"],
            "phones_accuracy": [2, 2, 2, 0.4],
            "mispronunciations": [{"index": 3, "canonical": "AH", "pronounced": "AH*"}],
        }],
        [_op("lisa", ["l", "i", "s", "ə"], [["l"], ["i"], ["s"], ["ə"]], [0, 0, 0, 0], False, 0)],
    )
    _, subs2, _ = score_utterance(utt2)
    assert subs2[0]["reason"] == "inexact_gt"
    summary = summarize([], subs2, _)
    assert summary["direction"]["n_primary"] == 0
    assert summary["direction"]["n_inexact_excluded"] == 1


def test_word_gate_hides_a_near_miss():
    utt = _utt(
        [{
            "text": "THINK",
            "phones": ["TH", "IH1", "NG", "K"],
            "phones_accuracy": [0.0, 2, 2, 2],
            "mispronunciations": [{"index": 0, "canonical": "TH", "pronounced": "S"}],
        }],
        [_op("think", ["θ", "ɪ", "ŋ", "k"], [["s"], ["ɪ"], ["ŋ"], ["k"]], [0.5, 0.0, 0.0, 0.0], False, 1)],
    )
    phones, subs, _ = score_utterance(utt)
    assert phones[0]["pred_primary"] is False
    assert phones[0]["pred_conf50"] is False
    assert phones[0]["pred_ungeared_50"] is True
    assert subs[0]["direction_match"] is True
    summary = summarize(phones, subs, _)
    assert summary["primary"]["recall"] == 0.0
    assert summary["operating_points"]["ignore_word_gate_conf_ge_0.5"]["recall"] == 1.0


def test_parse_and_repetition_rule():
    assert parse_pronounced("<DEL>") == []
    assert parse_pronounced("<unk>") is None
    assert parse_pronounced("EH R") == ["EH", "R"]
    assert parse_pronounced("R*") is None
    assert repetition_k(0.8)["k"] == 3 and repetition_k(0.8)["auto_confirm"] is True
    assert repetition_k(0.3)["auto_confirm"] is False
    assert GATE_PRECISION == 0.60 and GATE_DIRECTION_ACC == 0.70


def test_multi_phone_pronounced():
    utt = _utt(
        [{
            "text": "CAIRO",
            "phones": ["K", "IH"],
            "phones_accuracy": [2, 0.0],
            "mispronunciations": [{"index": 1, "canonical": "IH", "pronounced": "EH R"}],
        }],
        [_op("cairo", ["k", "ɪ"], [["k"], ["ɛ", "ɹ"]], [0.0, 1.0], True, 1)],
    )
    _, subs, _ = score_utterance(utt)
    assert subs[0]["reason"] == "match"
    assert subs[0]["heard_arpa"] == "EH R"


if __name__ == "__main__":
    test_ipa_map()
    test_rhotic_expansion_shares_one_op_decision()
    test_th_substitution_direction_and_detection()
    test_deletion_and_inexact_labels()
    test_word_gate_hides_a_near_miss()
    test_parse_and_repetition_rule()
    test_multi_phone_pronounced()
    print("ok")
