#!/usr/bin/env python3
"""cross_check.py — 七字段锚定交叉核对（SEC XBRL 主源 vs 东财次源）。

参考 stock_aiagent_research 项目 normalizer.apply_em_anchor 的设计独立重写，
仅依赖 Python 标准库。

机制（实证校准）：
- 七个锚定字段：revenue / net_income / total_equity / ocf / fcf /
  gross_profit / operating_income；
- 币种一致才可比（主源 XBRL unit 与东财 CURRENCY 规范化结果相等才进入核对，
  否则 skipped）；
- 按财年对齐，每个 (字段, 财年) 计算 factor = em_value / xbrl_value；
- 先压成字段级代表值（字段内多年取中位），再对字段代表值取中位数作基准——
  字段等权，避免某字段年份多就绑架基准（样本池污染教训）；
- 任一 (字段, 财年) 出现符号相反 → 该字段直接记偏离（重大质量信号）；
- 单字段代表值偏离基准 >10% 记一个偏离字段；偏离字段 >=2 → 整体 divergent；
- 只标注、不静默修正（数据分歧由分析层按框架裁决）。

稳健性边界：中位数基准要求参与字段 >=5 个才抗多数污染；3–4 个字段时
结论仅供参考，回执以 "small_sample" 注记。
"""
from __future__ import annotations

import statistics

ANCHOR_FIELDS: tuple[str, ...] = (
    "revenue",
    "net_income",
    "total_equity",
    "ocf",
    "fcf",
    "gross_profit",
    "operating_income",
)

DIVERGENCE_THRESHOLD = 0.10  # 字段代表值偏离基准中位数的阈值
MIN_DIVERGENT_FIELDS = 2  # 判定 divergent 所需的最少偏离字段数
MIN_FIELDS = 3  # 参与核对的最少字段数
ROBUST_FIELDS = 5  # 中位数基准抗多数污染所需字段数
_FACTOR_BOUNDS = (1e-4, 1e4)  # 防极端脏数据污染中位数
GROWTH_DIFF_THRESHOLD = 0.10  # 增幅模式：单年增幅差 >10pp 记偏离年


def cross_check(
    xbrl: dict[str, dict[str, float]],
    em: dict[str, dict[str, float]],
    *,
    currency_match: bool = True,
) -> dict:
    """两源锚定字段核对。

    参数：xbrl / em 均为 {字段名: {财年(YYYY 字符串): 原币值}}；
    currency_match=False 时直接跳过（币种不同，数值不可比）。

    返回 {"status": consistent|divergent|insufficient|skipped,
          "median_factor", "field_count", "sample_count",
          "compared", "divergent_fields", "detail"}。
    """
    if not currency_match:
        return {"status": "skipped", "reason": "currency_mismatch"}

    field_factors: dict[str, list[tuple[str, float]]] = {}  # field → [(year, factor)]
    sign_mismatch: dict[str, list[str]] = {}  # field → [year...]
    for field in ANCHOR_FIELDS:
        xs, es = xbrl.get(field) or {}, em.get(field) or {}
        for year in sorted(set(xs) & set(es)):
            xv, ev = xs[year], es[year]
            if xv is None or ev is None or xv == 0:
                continue
            if (xv < 0) != (ev < 0) and ev != 0:
                sign_mismatch.setdefault(field, []).append(year)
                continue
            f = ev / xv
            if _FACTOR_BOUNDS[0] < f < _FACTOR_BOUNDS[1]:
                field_factors.setdefault(field, []).append((year, f))

    compared_fields = sorted(set(field_factors) | set(sign_mismatch))
    if len(field_factors) < MIN_FIELDS:
        return {
            "status": "insufficient",
            "field_count": len(field_factors),
            "compared": compared_fields,
        }

    # 字段等权：先压字段代表值，再跨字段取基准中位数
    field_medians = {f: statistics.median(x for _, x in v) for f, v in field_factors.items()}
    baseline = statistics.median(field_medians.values())

    detail: dict[str, dict] = {}
    divergent: list[dict] = []
    for field in ANCHOR_FIELDS:
        ffs = field_factors.get(field, [])
        mismatched_years = sign_mismatch.get(field, [])
        if not ffs and not mismatched_years:
            continue
        fmed = field_medians.get(field)
        dev = abs(fmed / baseline - 1) if (fmed is not None and baseline) else None
        detail[field] = {
            "median_factor": round(fmed, 6) if fmed is not None else None,
            "deviation": round(dev, 4) if dev is not None else None,
            "years": [y for y, _ in ffs],
            "sign_mismatch_years": mismatched_years,
        }
        if mismatched_years or (dev is not None and dev > DIVERGENCE_THRESHOLD):
            divergent.append(
                {
                    "field": field,
                    "median_factor": round(fmed, 6) if fmed is not None else None,
                    "deviation": round(dev, 4) if dev is not None else None,
                    "sign_mismatch_years": mismatched_years,
                }
            )

    result = {
        "status": "divergent" if len(divergent) >= MIN_DIVERGENT_FIELDS else "consistent",
        "median_factor": round(baseline, 6),
        "field_count": len(compared_fields),
        "sample_count": sum(len(v) for v in field_factors.values()),
        "compared": {f: [y for y, _ in field_factors.get(f, [])] for f in compared_fields},
        "divergent_fields": divergent,
        "detail": detail,
    }
    if len(field_factors) < ROBUST_FIELDS:
        result["robustness_note"] = (
            f"参与核对字段仅 {len(field_factors)} 个（<{ROBUST_FIELDS}），"
            "中位数基准可能被多数污染，结论仅供参考"
        )
    return result


def cross_check_growth(
    xbrl: dict[str, dict[str, float]],
    em: dict[str, dict[str, float]],
) -> dict:
    """币种不一致时的币种无关核对：逐字段比较同比增幅（YoY）。

    增幅对币种/单位倍率天然免疫（USD 便利折算 vs CNY 原值，增长趋势应一致）。
    对每字段取各自序列内相邻年对，要求基期值 >0（防零穿越失真）；
    |em_growth − xbrl_growth| > 10pp 记一个偏离年；字段含任一偏离年 → 字段偏离；
    >=2 字段偏离 → divergent。注意：汇率波动本身可造成个位数 pp 差异，
    10pp 阈值只抓实质性分歧，不抓汇率噪声。
    """
    per_field: dict[str, list[dict]] = {}
    divergent: list[dict] = []
    for field in ANCHOR_FIELDS:
        xs, es = xbrl.get(field) or {}, em.get(field) or {}
        ys_x = sorted(y for y, v in xs.items() if v is not None and v > 0)
        ys_e = sorted(y for y, v in es.items() if v is not None and v > 0)
        gx = {b: xs[b] / xs[a] - 1 for a, b in zip(ys_x, ys_x[1:])}
        ge = {b: es[b] / es[a] - 1 for a, b in zip(ys_e, ys_e[1:])}
        rows = []
        for y in sorted(set(gx) & set(ge)):
            d = abs(ge[y] - gx[y])
            rows.append({"year": y, "xbrl_growth": round(gx[y], 4),
                         "em_growth": round(ge[y], 4), "diff_pp": round(d * 100, 2)})
        if rows:
            per_field[field] = rows
            bad = [r for r in rows if r["diff_pp"] > GROWTH_DIFF_THRESHOLD * 100]
            if bad:
                divergent.append({"field": field, "divergent_years": bad})
    compared = sorted(per_field)
    if len(compared) < MIN_FIELDS:
        return {"status": "insufficient", "mode": "growth", "field_count": len(compared)}
    return {
        "status": "divergent" if len(divergent) >= MIN_DIVERGENT_FIELDS else "consistent",
        "mode": "growth",
        "field_count": len(compared),
        "compared": {f: [r["year"] for r in rows] for f, rows in per_field.items()},
        "divergent_fields": divergent,
        "detail": per_field,
        "note": "YoY 增幅含汇率波动影响（如 USD/CNY 年波动可达 ±9%），单年 10–15pp "
                "偏离多为汇率噪声；持续多年偏离方为口径分歧信号（如归母 vs 总额净利）",
    }


if __name__ == "__main__":
    # 自检 1：五字段全部一致的样本 → consistent
    _x = {f: {"2024": 100.0, "2023": 90.0} for f in
          ("revenue", "net_income", "ocf", "gross_profit", "operating_income")}
    _e_ok = {f: {"2024": 101.0, "2023": 91.0} for f in _x}
    r1 = cross_check(_x, _e_ok)
    print("一致样本:", r1["status"])
    assert r1["status"] == "consistent"

    # 自检 2：五字段中两个系统性偏离 ~2x → divergent（字段等权，基准不被绑架）
    _e_bad = {f: {"2024": 101.0, "2023": 91.0} for f in _x}
    _e_bad["net_income"] = {"2024": 202.0, "2023": 182.0}
    _e_bad["ocf"] = {"2024": 202.0, "2023": 182.0}
    r2 = cross_check(_x, _e_bad)
    print("偏离样本:", r2["status"], "偏离字段:", [d["field"] for d in r2["divergent_fields"]])
    assert r2["status"] == "divergent"
    assert {d["field"] for d in r2["divergent_fields"]} == {"net_income", "ocf"}

    # 自检 3：符号相反 → 该字段直接记偏离
    _e_sign = {f: {"2024": 101.0, "2023": 91.0} for f in _x}
    _e_sign["net_income"] = {"2024": -100.0, "2023": 91.0}
    _e_sign["gross_profit"] = {"2024": -100.0, "2023": 91.0}
    r3 = cross_check(_x, _e_sign)
    print("符号相反样本:", r3["status"], "偏离字段:", [d["field"] for d in r3["divergent_fields"]])
    assert r3["status"] == "divergent"

    # 自检 4：币种不一致 → skipped
    assert cross_check(_x, _e_ok, currency_match=False)["status"] == "skipped"

    # 自检 5：增幅模式——币种无关，趋势一致 → consistent；一字段趋势背离 → divergent
    _xg = {"revenue": {"2022": 90.0, "2023": 100.0, "2024": 110.0},
           "ocf": {"2022": 45.0, "2023": 50.0, "2024": 55.0},
           "net_income": {"2022": 18.0, "2023": 20.0, "2024": 22.0}}
    _eg_ok = {"revenue": {"2022": 91.0, "2023": 101.0, "2024": 111.0},
              "ocf": {"2022": 45.5, "2023": 50.5, "2024": 55.4},
              "net_income": {"2022": 18.2, "2023": 20.2, "2024": 22.1}}
    r5 = cross_check_growth(_xg, _eg_ok)
    print("增幅一致样本:", r5["status"])
    assert r5["status"] == "consistent"
    _eg_bad = {k: dict(v) for k, v in _eg_ok.items()}
    _eg_bad["ocf"] = {"2022": 45.0, "2023": 60.0, "2024": 80.0}  # 增幅远超主源
    _eg_bad["net_income"] = {"2022": 18.0, "2023": 26.0, "2024": 35.0}
    r6 = cross_check_growth(_xg, _eg_bad)
    print("增幅背离样本:", r6["status"], "偏离字段:", [d["field"] for d in r6["divergent_fields"]])
    assert r6["status"] == "divergent"
    print("全部自检通过")
