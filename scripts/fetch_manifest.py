#!/usr/bin/env python3
"""fetch_manifest.py — 主入口：按指标字典「数据需求清单」全字段取数 + 回执 JSON。

通道架构（静默失败禁令：任何失败透出到回执 errors/missing，绝不返回空数据冒充成功）：
1. SEC EDGAR XBRL（主源）：companyconcept API，同义 tag 组回退 + 验收三条件；
2. 东方财富美股三表（兜底 + 交叉核对 + 中概 20-F 稀疏补齐）；
3. 治理字段（gov_filings）：8-K 条款 / 审计意见证据 / Form 4；
4. 派生字段（C10 Δ应收/Δ递延、FCF、毛利）：由已取字段确定性计算，非 LLM 估算。

用法：
    python3 scripts/fetch_manifest.py AAPL
    python3 scripts/fetch_manifest.py BABA --out receipts/BABA.json
    python3 scripts/fetch_manifest.py AAPL --skip-gov --skip-em   # 仅主源快取
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from sec_edgar import (  # noqa: E402
    SecRequestError,
    fetch_annual_with_fallback,
    get_cik,
    get_submissions,
)
from eastmoney_us import fetch_em_us_annual  # noqa: E402
from cross_check import cross_check, cross_check_growth  # noqa: E402
import gov_filings  # noqa: E402

MAX_AGE_DAYS = 450  # 与 sec_edgar 验收口径一致（僵尸 tag 防护）

# ═══ 字段 → XBRL tag 映射（唯一权威来源：references/indicator-dictionary.md 数据需求清单） ═══
# spec 键：kind=duration(流量)/instant(存量)；tags=同义回退组；
# composite=分量求和（先试综合 tag）；subfields=子字段分列；em=东财内部字段名；
# optional=非核心字段；manual=无结构化接口，须读 filing 原文（附阅读入口）。

MANIFEST: dict[str, dict] = {
    # ── A 组 合并资产负债表（instant）──
    "A01": {"name": "cash & cash equivalents", "kind": "instant",
            "tags": ("CashAndCashEquivalentsAtCarryingValue",), "em": "cash"},
    "A02": {"name": "short-term investments / marketable securities", "kind": "instant",
            "tags": ("ShortTermInvestments", "MarketableSecuritiesCurrent",
                     "AvailableForSaleSecuritiesDebtSecuritiesCurrent"),
            "em": "short_term_investments", "optional": True},
    "A04": {"name": "accounts receivable (net)", "kind": "instant",
            "tags": ("AccountsReceivableNetCurrent", "ReceivablesNetCurrent"),
            "em": "accounts_receivable"},
    "A05": {"name": "contract assets / unbilled receivables", "kind": "instant",
            "tags": ("ContractWithCustomerAssetNet", "ContractWithCustomerAssetCurrent"),
            "optional": True},
    "A08": {"name": "inventory", "kind": "instant",
            "tags": ("InventoryNet",), "em": "inventory", "optional": True},
    "A10": {"name": "current assets 合计", "kind": "instant", "tags": ("AssetsCurrent",)},
    "A14": {"name": "PP&E net", "kind": "instant",
            "tags": ("PropertyPlantAndEquipmentNet",)},
    "A16": {"name": "operating lease ROU assets", "kind": "instant",
            "tags": ("OperatingLeaseRightOfUseAsset",), "optional": True},
    "A17": {"name": "acquired intangibles", "kind": "instant",
            "tags": ("FiniteLivedIntangibleAssetsNet", "IntangibleAssetsNetExcludingGoodwill"),
            "em": "intangibles", "optional": True},
    "A18": {"name": "capitalized software / deferred costs",
            "manual": "无稳定 XBRL tag，须读 10-K 附注（PP&E/无形资产/递延成本章节）"},
    "A19": {"name": "goodwill", "kind": "instant", "tags": ("Goodwill",), "em": "goodwill"},
    "A21": {"name": "deferred tax assets", "kind": "instant",
            "tags": ("DeferredIncomeTaxAssetsNet", "DeferredTaxAssetsNet"), "optional": True},
    "A22": {"name": "total assets", "kind": "instant", "tags": ("Assets",), "em": "total_assets"},
    "A23": {"name": "short-term debt（含 current portion of LTD）", "kind": "instant",
            "tags": ("DebtCurrent",),
            "composite": {"mode": "sum", "parts": {
                "short_borrowings": ("ShortTermBorrowings", "ShortTermDebt"),
                "commercial_paper": ("CommercialPaper",),
                "current_ltd": ("LongTermDebtCurrent",),
            }},
            "em": "short_term_debt"},
    "A25": {"name": "accounts payable", "kind": "instant",
            "tags": ("AccountsPayableCurrent", "AccountsPayableTradeCurrent"),
            "em": "accounts_payable"},
    "A26": {"name": "deferred revenue / contract liabilities", "kind": "instant",
            "tags": ("ContractWithCustomerLiability", "ContractWithCustomerLiabilityCurrent",
                     "DeferredRevenueCurrent"),
            "em": "deferred_revenue"},
    "A28": {"name": "current liabilities 合计", "kind": "instant",
            "tags": ("LiabilitiesCurrent",)},
    "A29": {"name": "long-term debt（含 senior notes）", "kind": "instant",
            "tags": ("LongTermDebtNoncurrent", "LongTermDebt"),
            "em": "long_term_debt"},
    "A31": {"name": "lease liabilities（finance + operating 分列）", "kind": "instant",
            "subfields": {
                "finance_lease_liabilities": ("FinanceLeaseLiability", "FinanceLeaseLiabilityNoncurrent"),
                "operating_lease_liabilities": ("OperatingLeaseLiability", "OperatingLeaseLiabilityNoncurrent"),
            }, "optional": True},
    "A32": {"name": "deferred tax liabilities", "kind": "instant",
            "tags": ("DeferredIncomeTaxLiabilitiesNet",), "optional": True},
    "A33": {"name": "total liabilities", "kind": "instant",
            "tags": ("Liabilities",), "em": "total_liabilities"},
    "A34": {"name": "归母股东权益", "kind": "instant",
            "tags": ("StockholdersEquity",), "em": "total_equity"},
    "A35": {"name": "NCI 权益", "kind": "instant", "tags": ("MinorityInterest",), "optional": True},
    "A36": {"name": "非流动有价证券", "kind": "instant",
            "tags": ("MarketableSecuritiesNoncurrent",
                     "AvailableForSaleSecuritiesDebtSecuritiesNoncurrent"),
            "em": "long_term_investments", "optional": True},
    # ── B 组 合并利润表（duration）──
    "B01": {"name": "revenue", "kind": "duration",
            "tags": ("Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax",
                     "RevenueFromContractWithCustomerIncludingAssessedTax", "SalesRevenueNet"),
            "em": "revenue"},
    "B02": {"name": "COGS", "kind": "duration",
            "tags": ("CostOfRevenue", "CostOfGoodsAndServicesSold", "CostOfGoodsSold",
                     "CostOfServicesRevenue"),
            "em": "cogs"},
    "B03": {"name": "SG&A（或销售/管理分列求和）", "kind": "duration",
            "tags": ("SellingGeneralAndAdministrativeExpense",),
            "composite": {"mode": "sum", "parts": {
                "selling": ("SellingAndMarketingExpense",),
                "g_and_a": ("GeneralAndAdministrativeExpense",),
            }},
            "em": "sga_expense"},
    "B05": {"name": "R&D", "kind": "duration",
            "tags": ("ResearchAndDevelopmentExpense",), "em": "rd_expense"},
    "B06": {"name": "interest expense / interest income 子字段", "kind": "duration",
            "subfields": {
                "interest_expense": ("InterestExpense", "InterestExpenseNonoperating"),
                "interest_income": ("InterestIncomeNonoperating", "InvestmentIncomeInterest"),
            }, "em": "interest_expense"},
    "B08": {"name": "investment & disposal gains（非经营损益）", "kind": "duration",
            "tags": ("GainLossOnInvestments", "RealizedInvestmentGainsLosses",
                     "GainLossOnSaleOfPropertyPlantEquipment"),
            "optional": True},
    "B11": {"name": "operating income", "kind": "duration",
            "tags": ("OperatingIncomeLoss",), "em": "operating_income"},
    "B14": {"name": "pretax income", "kind": "duration",
            "tags": ("IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
                     "IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments"),
            "em": "pretax_income"},
    "B15": {"name": "income tax", "kind": "duration",
            "tags": ("IncomeTaxExpenseBenefit",)},
    "B16": {"name": "net income", "kind": "duration",
            "tags": ("NetIncomeLoss", "ProfitLoss"), "em": "net_income"},
    "B17": {"name": "归母净利润", "kind": "duration",
            "tags": ("NetIncomeLossAttributableToParent",
                     "NetIncomeLossAvailableToCommonStockholdersBasic", "NetIncomeLoss"),
            "em": "net_income_parent"},
    "B18": {"name": "NCI 损益", "kind": "duration",
            "tags": ("NetIncomeLossAttributableToNoncontrollingInterest",),
            "optional": True, "episodic": True},
    "B19": {"name": "OCI", "kind": "duration",
            "tags": ("OtherComprehensiveIncomeLossNetOfTax",), "em": "oci", "optional": True},
    "B20": {"name": "comprehensive income", "kind": "duration",
            "tags": ("ComprehensiveIncomeNetOfTax",), "em": "comprehensive_income", "optional": True},
    "B21": {"name": "SBC", "kind": "duration",
            "tags": ("ShareBasedCompensation", "AllocatedShareBasedCompensationExpense"),
            "em": "sbc", "optional": True},
    "B22": {"name": "加权稀释股数", "kind": "duration",
            "tags": ("WeightedAverageNumberOfDilutedSharesOutstanding",),
            "em": "shares_diluted"},
    "B23": {"name": "Non-GAAP 净利润与调节表",
            "manual": "XBRL 无结构化数据，须读 earnings release（8-K/6-K EX-99.1）"},
    # ── C 组 合并现金流量表（duration）──
    "C02": {"name": "CFO", "kind": "duration",
            "tags": ("NetCashProvidedByUsedInOperatingActivities",), "em": "ocf"},
    "C03": {"name": "capex", "kind": "duration",
            "tags": ("PaymentsToAcquirePropertyPlantAndEquipment",
                     "PaymentsToAcquireProductiveAssets"),
            "em": "capex"},
    "C04": {"name": "CFI", "kind": "duration",
            "tags": ("NetCashProvidedByUsedInInvestingActivities",), "em": "icf"},
    "C05": {"name": "dividends paid", "kind": "duration",
            "tags": ("PaymentsOfDividends", "PaymentsOfDividendsCommonStock",
                     "PaymentsOfDividendsAndDividendEquivalentsOnCommonStockAndRestrictedStockUnits"),
            "em": "dividends_paid", "optional": True},
    "C06": {"name": "CFF", "kind": "duration",
            "tags": ("NetCashProvidedByUsedInFinancingActivities",), "em": "fcf_financing"},
    "C08": {"name": "buybacks", "kind": "duration",
            "tags": ("PaymentsForRepurchaseOfCommonStock",
                     "PaymentsForRepurchaseOfCommonStockAndEquity"),
            "em": "buybacks", "optional": True},
    "C09": {"name": "M&A 支出", "kind": "duration",
            "tags": ("PaymentsToAcquireBusinessesNetOfCashAcquired",),
            "optional": True, "episodic": True},
    "C11": {"name": "股票发行所得（S4-07' 净回购口径用）", "kind": "duration",
            "tags": ("ProceedsFromIssuanceOfCommonStock",
                     "ProceedsFromIssuanceOfCommonStockAndEquity"),
            "optional": True, "episodic": True},
}

#: ▲核心字段（16 项，回执中单独核对覆盖；准入校验口径见字典）
CORE_FIELDS = (
    "B01", "B02", "B17", "B16", "B18", "C02", "A22", "A33",
    "A34", "A01", "A23", "A29", "A04", "A08", "A19", "C03",
)

#: D 组手工字段说明与阅读入口（gov_* 覆盖 D01/D16/D20/D21/D22，其余为手工阅读）
MANUAL_D: dict[str, str] = {
    "D04": "商誉分 reporting unit 明细与减值历史 → 最新 10-K 商誉附注",
    "D05": "关联交易 → DEF 14A",
    "D06": "commitments & contingencies、重大诉讼 → 10-K 附注",
    "D07": "研发投入见 B05；资本化软件金额 → 10-K 附注",
    "D09": "IPO / de-SPAC 日期 → 公开信息核实（S-1/8-K）",
    "D15": "债务到期结构表 → 10-K 债务附注",
    "D17": "做空报告记录 → 公开信息，脚本不抓取",
    "D18": "VIE 结构与资产占比 → 中概 20-F 风险因素/组织架构章节",
    "D19": "PCAOB/HFCAA 状态 → PCAOB 公开名单",
}


# ═══ 取数执行 ═══


def _fresh_enough(values: list[dict]) -> bool:
    try:
        latest = date.fromisoformat(values[0]["end"])
    except (ValueError, KeyError, IndexError):
        return False
    return (date.today() - latest).days <= MAX_AGE_DAYS


def _fetch_fallback(cik: str, spec: dict, min_years: int) -> dict | None:
    """同义 tag 组取数：先按 min_years 验收，不足则放宽到 1 期并标 partial。"""
    kind = spec.get("kind", "duration")
    r = fetch_annual_with_fallback(cik, spec["tags"], kind=kind, min_years=min_years)
    if r is not None:
        r["coverage"] = "full"
        return r
    r = fetch_annual_with_fallback(cik, spec["tags"], kind=kind, min_years=1)
    if r is not None:
        r["coverage"] = "partial"  # 数据真实存在但不足 min_years 期（如次新股）
    return r


def _fetch_composite(cik: str, spec: dict, min_years: int) -> dict | None:
    """组合字段：先试综合 tag（如 DebtCurrent），失败再分量求和。

    分量期数门槛放宽到 2 期；缺失分量按 0 处理并记入 parts_missing（透出，不静默）。
    """
    kind = spec.get("kind", "duration")
    if spec.get("tags"):
        r = fetch_annual_with_fallback(cik, spec["tags"], kind=kind, min_years=2)
        if r is not None and len(r["values"]) >= min_years:
            r["coverage"] = "full"
            r["via"] = "combined_tag"
            return r
    parts = spec["composite"]["parts"]
    year_sums: dict[str, float] = {}
    part_meta: dict[str, dict] = {}
    included: list[str] = []
    missing: list[str] = []
    for pname, ptags in parts.items():
        r = fetch_annual_with_fallback(cik, ptags, kind=kind, min_years=2)
        if r is None:
            missing.append(pname)
            continue
        included.append(pname)
        part_meta[pname] = {"tag": r["tag"], "unit": r["unit"]}
        for v in r["values"]:
            year_sums[v["end"]] = year_sums.get(v["end"], 0.0) + v["val"]
    if not included:
        return None
    values = [{"end": e, "val": v} for e, v in sorted(year_sums.items(), reverse=True)]
    if not _fresh_enough(values):
        return None
    unit = next(iter(part_meta.values()))["unit"]
    return {
        "tag": None,
        "unit": unit,
        "values": values,
        "coverage": "full" if len(values) >= min_years else "partial",
        "via": "composite_sum",
        "parts_included": included,
        "parts_missing": missing,
        "part_tags": part_meta,
    }


def _fetch_subfields(cik: str, spec: dict, min_years: int) -> dict | None:
    """子字段分列（如 B06 利息费用/利息收入；A31 租赁负债分列）。"""
    kind = spec.get("kind", "duration")
    subs: dict[str, dict] = {}
    for sname, stags in spec["subfields"].items():
        r = fetch_annual_with_fallback(cik, stags, kind=kind, min_years=min_years)
        if r is None:
            r = fetch_annual_with_fallback(cik, stags, kind=kind, min_years=1)
            if r is not None:
                r["coverage"] = "partial"
        else:
            r["coverage"] = "full"
        if r is not None:
            subs[sname] = r
    if not subs:
        return None
    unit = next(iter(subs.values()))["unit"]
    coverage = "full" if all(s["coverage"] == "full" for s in subs.values()) else "partial"
    return {"tag": None, "unit": unit, "coverage": coverage, "subfields": subs, "values": []}


def fetch_field(cik: str, spec: dict, min_years: int) -> dict | None:
    if "subfields" in spec:
        return _fetch_subfields(cik, spec, min_years)
    if "composite" in spec:
        return _fetch_composite(cik, spec, min_years)
    return _fetch_fallback(cik, spec, min_years)


# ═══ 东财兜底 + 交叉核对 ═══


def _em_year_map(em_annual: dict, em_field: str) -> dict[str, float]:
    return {
        dt[:4]: f[em_field]
        for dt, f in em_annual.items()
        if f.get(em_field) is not None
    }


def fill_from_em(fields: dict, missing: dict, em_data: dict, min_years: int) -> tuple[dict, dict]:
    """SEC 缺失字段用东财序列补齐（标注 source=eastmoney-us，币种为东财 CURRENCY）。

    新鲜度门槛与主源一致（MAX_AGE_DAYS）：过期序列不填充——实证：AAPL 的东财
    商誉序列最新值停在 2016 年（苹果 2017 起不再单列商誉），若不拦截会把
    十年前旧值当当前数据。
    返回 (filled {fid: em_field}, stale_rejected {fid: {latest, age_days}})。
    """
    filled: dict[str, str] = {}
    stale: dict[str, dict] = {}
    for fid in list(missing):
        spec = MANIFEST.get(fid)
        if not spec or not spec.get("em"):
            continue
        series = {dt: f[spec["em"]] for dt, f in em_data["annual"].items() if f.get(spec["em"]) is not None}
        if not series:
            continue
        latest = max(series)  # ISO 日期字符串字典序=时间序
        try:
            age = (date.today() - date.fromisoformat(latest)).days
        except ValueError:
            age = MAX_AGE_DAYS + 1
        if age > MAX_AGE_DAYS:
            stale[fid] = {"latest": latest, "age_days": age}
            continue
        values = [{"end": dt, "val": v} for dt, v in sorted(series.items(), reverse=True)]
        fields[fid] = {
            "name": spec["name"],
            "unit": em_data.get("currency"),
            "source": "eastmoney-us",
            "coverage": "full" if len(values) >= min_years else "partial",
            "values": values,
            "note": "sec-miss-em-fill",
        }
        filled[fid] = spec["em"]
        del missing[fid]
    return filled, stale


def _ym(entry: dict) -> dict[str, float]:
    return {v["end"][:4]: v["val"] for v in entry.get("values") or [] if v.get("val") is not None}


def build_canon(fields: dict, em_data: dict | None) -> tuple[dict, dict]:
    """构造七字段锚定核对的双源 canonical 映射 {field: {year: value}}。"""
    sec: dict[str, dict[str, float]] = {}
    for anchor, fid in (("revenue", "B01"), ("net_income", "B16"),
                        ("total_equity", "A34"), ("ocf", "C02"),
                        ("operating_income", "B11")):
        e = fields.get(fid)
        if e and e.get("source", "sec-edgar") == "sec-edgar" and e.get("values"):
            sec[anchor] = _ym(e)
    c02, c03 = _ym(fields.get("C02") or {}), _ym(fields.get("C03") or {})
    sec["fcf"] = {y: c02[y] - c03[y] for y in c02.keys() & c03.keys()}
    b01, b02 = _ym(fields.get("B01") or {}), _ym(fields.get("B02") or {})
    sec["gross_profit"] = {y: b01[y] - b02[y] for y in b01.keys() & b02.keys()}
    sec = {k: v for k, v in sec.items() if v}

    em: dict[str, dict[str, float]] = {}
    if em_data:
        annual = em_data["annual"]
        for anchor, emn in (("revenue", "revenue"), ("total_equity", "total_equity"),
                            ("ocf", "ocf"), ("operating_income", "operating_income")):
            m = _em_year_map(annual, emn)
            if m:
                em[anchor] = m
        ni = _em_year_map(annual, "net_income_parent") or _em_year_map(annual, "net_income")
        if ni:
            em["net_income"] = ni
        fcf = _em_year_map(annual, "fcf")
        if fcf:
            em["fcf"] = fcf
        gp = _em_year_map(annual, "gross_profit")
        if not gp:
            rev, cogs = _em_year_map(annual, "revenue"), _em_year_map(annual, "cogs")
            gp = {y: rev[y] - cogs[y] for y in rev.keys() & cogs.keys()}
        if gp:
            em["gross_profit"] = gp
    return sec, em


# ═══ 派生字段（确定性计算，非 LLM 估算） ═══


def _diff_series(entry: dict) -> dict[str, float]:
    vals = sorted(entry.get("values") or [], key=lambda v: v["end"])
    return {cur["end"]: cur["val"] - prev["val"] for prev, cur in zip(vals, vals[1:])}


def compute_derived(fields: dict) -> dict:
    derived: dict[str, dict] = {}
    c02, c03 = fields.get("C02"), fields.get("C03")
    if c02 and c03:
        m02, m03 = _ym(c02), _ym(c03)
        fcf = {y: m02[y] - m03[y] for y in m02.keys() & m03.keys()}
        if fcf:
            derived["FCF_DERIVED"] = {"formula": "C02 − C03", "by_year": dict(sorted(fcf.items(), reverse=True))}
    b01, b02 = fields.get("B01"), fields.get("B02")
    if b01 and b02:
        m01, m02v = _ym(b01), _ym(b02)
        gp = {y: m01[y] - m02v[y] for y in m01.keys() & m02v.keys()}
        if gp:
            derived["GROSS_PROFIT_DERIVED"] = {"formula": "B01 − B02", "by_year": dict(sorted(gp.items(), reverse=True))}
    # C10：Δ应收类 = Δ(A04+A05)；Δ递延收入 = Δ(A26)。A05 缺失按 0 处理（透出 note）。
    recv: dict[str, float] = {}
    for fid in ("A04", "A05"):
        e = fields.get(fid)
        if not e:
            continue
        for v in e.get("values") or []:
            recv[v["end"]] = recv.get(v["end"], 0.0) + v["val"]
    c10: dict[str, dict] = {}
    if recv:
        ends = sorted(recv)
        c10["delta_receivables"] = {
            "formula": "Δ(A04+A05)，A05 缺失按 0",
            "by_end": {e: recv[e] - recv[prev] for prev, e in zip(ends, ends[1:])},
        }
    if fields.get("A26"):
        c10["delta_deferred_revenue"] = {
            "formula": "Δ(A26)",
            "by_end": _diff_series(fields["A26"]),
        }
    if c10:
        derived["C10"] = c10
    return derived


# ═══ 主流程 ═══


def run(ticker: str, *, min_years: int = 5, skip_gov: bool = False, skip_em: bool = False) -> dict:
    cik = get_cik(ticker)
    if not cik:
        raise SystemExit(f"ticker {ticker} 无法解析 CIK（SEC company_tickers 无此代码）")
    company = (get_submissions(cik) or {}).get("name")

    fields: dict[str, dict] = {}
    missing: dict[str, str] = {}
    episodic_absent: list[str] = []
    manual: dict[str, str] = {}
    errors: dict[str, str] = {}
    for fid, spec in MANIFEST.items():
        if spec.get("manual"):
            manual[fid] = spec["manual"]
            continue
        try:
            entry = fetch_field(cik, spec, min_years)
        except SecRequestError as e:
            errors[fid] = str(e)  # 静默失败禁令：网络层错误必须透出
            continue
        if entry is None:
            missing[fid] = spec["name"]
            if spec.get("episodic"):
                # 偶发字段无近期值 ≠ 通道故障，通常表示该类业务未发生（如无并购/增发）
                episodic_absent.append(fid)
        else:
            entry["name"] = spec["name"]
            entry.setdefault("source", "sec-edgar")
            fields[fid] = entry

    # 东财通道：兜底补齐 + 交叉核对
    em_data = None
    em_filled: dict[str, str] = {}
    em_stale: dict[str, dict] = {}
    if not skip_em:
        em_data = fetch_em_us_annual(ticker)
        if em_data:
            em_filled, em_stale = fill_from_em(fields, missing, em_data, min_years)

    # 交叉核对（双源都有数据才核对；币种一致走绝对值模式，不一致走 YoY 增幅模式）
    sec_canon, em_canon = build_canon(fields, em_data)
    sec_units = [e["unit"] for e in fields.values() if e.get("source") == "sec-edgar" and e.get("unit")]
    sec_ccy = max(set(sec_units), key=sec_units.count) if sec_units else None
    em_ccy = (em_data or {}).get("currency")
    currency_match = bool(sec_ccy and em_ccy and sec_ccy == em_ccy)
    if currency_match:
        cc = cross_check(sec_canon, em_canon, currency_match=True)
        cc["mode"] = "levels"
    elif sec_canon and em_canon:
        cc = cross_check_growth(sec_canon, em_canon)
        cc["reason"] = "currency_mismatch→YoY 增幅模式"
    else:
        cc = {"status": "skipped", "reason": "single_source_only"}
    cc["sec_currency"] = sec_ccy
    cc["em_currency"] = em_ccy
    # 单位一致性摘要：ADR 可能混合 USD 便利折算与本地币种，跨字段计算前必须核对
    from collections import Counter
    unit_mix = dict(Counter(e.get("unit") for e in fields.values() if e.get("values")))

    # 治理字段（D 组）
    gov: dict = {}
    if not skip_gov:
        gov["D20_D22_8k_items"] = gov_filings.scan_8k_items(cik)
        gov["D01_D21_audit_evidence"] = gov_filings.audit_flags(cik)
        gov["D16_form4"] = gov_filings.form4_summary(cik)
        idx = gov_filings.filing_index(cik)
        gov["filing_index"] = idx
        manual.update(MANUAL_D)
        refs = {}
        if idx["annual_reports"]:
            refs["latest_annual_report"] = idx["annual_reports"][0].get("url")
        if idx["proxy_statements"]:
            refs["latest_proxy"] = idx["proxy_statements"][0].get("url")
        gov["manual_field_refs"] = refs

    derived = compute_derived(fields)
    partial = {fid: len(e.get("values") or []) for fid, e in fields.items() if e.get("coverage") == "partial"}
    core_missing = [f for f in CORE_FIELDS if f in missing or f in errors]

    return {
        "ticker": ticker.upper(),
        "cik": cik,
        "company": company,
        "retrieved_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "min_years_required": min_years,
        "currency": {"sec": sec_ccy, "em": em_ccy, "unit_mix": unit_mix},
        "fields": fields,
        "derived": derived,
        "missing": missing,
        "episodic_absent": episodic_absent,
        "partial_coverage": partial,
        "manual_fields": manual,
        "em_fallback": {"enabled": not skip_em, "filled": em_filled,
                        "stale_rejected": em_stale,
                        "rejected_rows": (em_data or {}).get("rejected") or []},
        "governance": gov,
        "cross_check": cc,
        "core_missing": core_missing,
        "errors": errors,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="美股财报数据需求清单全字段取数（回执 JSON）")
    parser.add_argument("ticker", help="如 AAPL / BABA")
    parser.add_argument("--min-years", type=int, default=5, help="年度期数门槛（默认 5）")
    parser.add_argument("--skip-gov", action="store_true", help="跳过治理字段（8-K/审计证据/Form 4）")
    parser.add_argument("--skip-em", action="store_true", help="跳过东财通道（兜底+交叉核对）")
    parser.add_argument("--out", default=None, help="回执输出路径（默认 scripts/receipts/<TICKER>.json；'-' 仅打印）")
    args = parser.parse_args()

    receipt = run(args.ticker, min_years=args.min_years, skip_gov=args.skip_gov, skip_em=args.skip_em)
    payload = json.dumps(receipt, ensure_ascii=False, indent=1)

    if args.out == "-":
        print(payload)
    else:
        out = Path(args.out) if args.out else (
            Path(__file__).resolve().parent / "receipts" / f"{args.ticker.upper()}.json"
        )
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(payload)
        n = len(receipt["fields"])
        print(f"[回执] {receipt['ticker']} ({receipt['company']}) → {out}")
        print(f"  字段: 取到 {n} / 缺失 {len(receipt['missing'])} / 部分覆盖 {len(receipt['partial_coverage'])}"
              f" / 手工 {len(receipt['manual_fields'])} / 错误 {len(receipt['errors'])}")
        print(f"  币种: SEC={receipt['currency']['sec']} EM={receipt['currency']['em']}；"
              f"交叉核对: {receipt['cross_check']['status']}"
              f"（偏离字段 {[d['field'] for d in receipt['cross_check'].get('divergent_fields', [])]}）")
        if receipt["core_missing"]:
            print(f"  ▲核心字段缺失: {receipt['core_missing']}")
        if receipt["errors"]:
            print(f"  错误透出: {receipt['errors']}")


if __name__ == "__main__":
    main()
