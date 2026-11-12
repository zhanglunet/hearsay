# -*- coding: utf-8 -*-
"""PRD-388/T2（trend issue #1892 的 T2 环节）：纠正验证台最小实现。

按 T1 设计（docs/design/2026-11-12-prd-388-correction-verification-bench-design.md）
§4 落地：
  - verify_correction(correction, corpus, recheck_fn)：逐条纠正发音模型
    复核验证——recheck_fn 注入式重跑同一对齐（word_feedback 形态，参考句
    语料只读深拷贝，零新增对齐逻辑 R2）；重跑 error_instances 与纠正一致
    → VERIFIED，否则 UNVERIFIED（词表封闭）；语料指纹 sha16: 前缀确定性；
  - verify_corrections(corrections, corpus, recheck_fn)：陪练反馈出口包装
    （接入点：word_feedback 纠正之后、learner 会话递给学员之前）——
    UNVERIFIED 拦下不进陪练反馈（R1，防教错非母语学员）；
  - CorrectionBenchLedger：机器可读 JSONL 落账（路径注入，append-only
    R3/R4）；八件套缺一 BENCH_INCOMPLETE 拒绝入账；
  - reverify：语料变更二次验证——指纹不符 → BENCH_STALE 拒绝复用旧验证
    （R4 关闭以最新 VERIFIED 为准）。
零网络零子进程零 phoneme 写（PHONEME_PRODUCT_RULE seal 红线不变）；示例
全虚构占位。
测试：prototype/tests/test_correction_verify_bench.py
"""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any, Callable

BENCH_SCHEMA = "correction-verify-bench/v1"
VERDICTS = ("VERIFIED", "UNVERIFIED")
ERROR_CODES = ("BENCH_INCOMPLETE", "BENCH_REPRO_MISMATCH", "BENCH_STALE")


class CorrectionBenchError(ValueError):
    """验证台违规——显形拒绝。"""


def corpus_fingerprint(corpus: Any) -> str:
    """参考句语料快照指纹（sha16: 前缀，canonical JSON 确定性摘要）。"""
    canon = json.dumps(corpus, ensure_ascii=False, sort_keys=True,
                       separators=(",", ":"))
    return "sha16:" + hashlib.sha256(canon.encode("utf-8")).hexdigest()[:16]


def _recusal(code: str, detail: str) -> dict[str, Any]:
    return {"schema": BENCH_SCHEMA, "refused": code, "detail": detail,
            "verdict": None}


def verify_correction(correction: dict[str, Any], corpus: Any,
                      recheck_fn: Callable[[Any], list[dict[str, Any]]],
                      *, at: str = "") -> dict[str, Any]:
    """逐条纠正发音模型复核验证（R1/R2）：重跑对齐一致 → VERIFIED。"""
    if not isinstance(correction, dict):
        return _recusal("BENCH_INCOMPLETE", "correction 非对象")
    missing = [k for k in ("correction_id", "learner_id", "kind",
                           "source_ref", "error_instances")
               if not correction.get(k)]
    if missing:
        return _recusal("BENCH_INCOMPLETE", f"八件套缺 {missing}")
    if not callable(recheck_fn):
        return _recusal("BENCH_INCOMPLETE", "recheck_fn 未注入")
    rerun = recheck_fn(copy.deepcopy(corpus)) or []
    hit = next((r for r in rerun
                if str(r.get("reference")) == str(correction.get("reference"))
                and str(r.get("hypothesis")) ==
                str(correction.get("hypothesis"))), None)
    im = bool(hit and sorted(str(x) for x in hit.get("error_instances") or [])
              == sorted(str(x) for x in correction.get("error_instances") or []))
    return {
        "schema": BENCH_SCHEMA,
        "correction_id": correction["correction_id"],
        "learner_id": correction["learner_id"],
        "kind": correction["kind"],
        "source_ref": correction["source_ref"],
        "corpus_fingerprint": corpus_fingerprint(corpus),
        "correction": copy.deepcopy(correction),
        "reproduce": {"instances_match": im,
                      "detail": f"重跑对齐 {len(rerun)} 条（占位）"},
        "verdict": "VERIFIED" if im else "UNVERIFIED",
        "at": at,
    }


def verify_corrections(corrections: list[dict[str, Any]], corpus: Any,
                       recheck_fn: Callable[[Any], list[dict[str, Any]]],
                       *, at: str = "") -> dict[str, Any]:
    """陪练反馈出口包装（接入点）：UNVERIFIED 拦下不进陪练反馈（R1）。"""
    verified: list[dict[str, Any]] = []
    unverified: list[dict[str, Any]] = []
    for c in corrections or []:
        out = verify_correction(c, corpus, recheck_fn, at=at)
        if out.get("refused") or out["verdict"] == "UNVERIFIED":
            unverified.append(out)
        else:
            verified.append(out)
    return {"schema": BENCH_SCHEMA, "verified": verified,
            "unverified": unverified, "unverified_count": len(unverified)}


class CorrectionBenchLedger:
    """验证账本（R3/R4）：JSONL append-only；八件套缺一拒绝入账。"""

    _REQUIRED = ("correction_id", "learner_id", "kind", "source_ref",
                 "corpus_fingerprint", "correction", "verdict")

    def __init__(self, path: str | Path | None = None) -> None:
        self._records: list[dict[str, Any]] = []
        self._path = Path(path) if path else None

    def record(self, out: dict[str, Any], *, at: str = "") -> dict[str, Any]:
        if out.get("refused"):
            raise CorrectionBenchError(f"{out['refused']}：{out['detail']}")
        rec = dict(out, at=at)
        missing = [k for k in self._REQUIRED if rec.get(k) in (None, "")]
        if missing:
            raise CorrectionBenchError(f"BENCH_INCOMPLETE：账目缺 {missing}")
        if rec["verdict"] not in VERDICTS:
            raise CorrectionBenchError(f"BENCH_INCOMPLETE：verdict 词表外 "
                                       f"{rec['verdict']!r}")
        if rec["verdict"] == "VERIFIED" and not rec["reproduce"]["instances_match"]:
            raise CorrectionBenchError("BENCH_REPRO_MISMATCH：声称 VERIFIED "
                                       "但重跑 error_instances 与纠正不一致"
                                       "——验证结论与复现证据不一致")
        self._records.append(copy.deepcopy(rec))
        if self._path is not None:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            with open(self._path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(rec, ensure_ascii=False,
                                    sort_keys=True) + "\n")
        return dict(rec)

    def entries(self) -> list[dict[str, Any]]:
        return [dict(r) for r in self._records]

    def latest_for(self, correction_id: str) -> dict[str, Any] | None:
        found = [r for r in self._records
                 if r["correction_id"] == correction_id]
        return dict(found[-1]) if found else None

    def reverify(self, correction_id: str, corpus: Any,
                 recheck_fn: Callable[[Any], list[dict[str, Any]]],
                 *, at: str = "") -> dict[str, Any]:
        """语料变更二次验证（R4）：指纹不符 → BENCH_STALE 拒绝复用。"""
        prior = self.latest_for(correction_id)
        fp_now = corpus_fingerprint(corpus)
        if prior and prior["corpus_fingerprint"] != fp_now:
            return _recusal("BENCH_STALE",
                            f"{correction_id} 旧验证语料指纹与当前不符——语料"
                            "变更后须重新验证，旧 VERIFIED 不复用")
        prior_corr = (prior or {}).get("correction") or {}
        base = {"correction_id": correction_id,
                "learner_id": (prior or {}).get("learner_id") or "",
                "kind": (prior or {}).get("kind") or "",
                "source_ref": (prior or {}).get("source_ref") or "",
                "reference": prior_corr.get("reference"),
                "hypothesis": prior_corr.get("hypothesis"),
                "error_instances": prior_corr.get("error_instances") or []}
        return self.record(verify_correction(base, corpus, recheck_fn, at=at),
                           at=at)
