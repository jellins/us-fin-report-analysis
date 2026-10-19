#!/usr/bin/env python3
"""eastmoney_us.py — 东财美股三表通道（兜底 + 交叉核对 + 中概补齐）。

参考 stock_aiagent_research 项目 em_finstmt_provider 的生产实证参数独立重写，
仅依赖 Python 标准库。

实证基线（来自参考项目 PoC 与本项目冒烟校准）：
- API：datacenter-web.eastmoney.com/api/data/v1/get
- 报表名：利润表 RPT_USF10_FN_INCOME / 资产负债表 RPT_USF10_FN_BALANCE /
  现金流量表 RPT_USSK_FN_CASHFLOW
- SECUCODE 候选：{TICKER}.O 不通回退 {TICKER}.N
- 币种铁律：以东财返回的 CURRENCY/CURRENCY_ABBR 字段为数值真实币种，
  严禁借用其他源的币种判定（联想 00992 教训）
- capex 符号口径混杂（部分期次正数记账）→ 抽取一律 abs 规范化
- 行级 sanity 两规则：净利 > 营收×1.05 / 营收 ≤0 → 整行拒绝。
  【刻意不吸收参考项目的第三规则"权益<0 拒绝"：美股回购文化下负净资产
  合法（麦当劳/星巴克），该规则会系统性误伤】
- 任何异常 → None（调用方走 MISSING/降级），静默失败禁令仅约束主源 SEC 通道；
  本通道为兜底层，失败语义是"无数据"而非"接口异常"，但 rejected_rows 必须透出。
"""
from __future__ import annotations

import json
import urllib.parse
import urllib.request
from datetime import date

_BASE = "https://datacenter-web.eastmoney.com/api/data/v1/get"
_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
_TIMEOUT = 15

REPORTS = ("RPT_USF10_FN_INCOME", "RPT_USF10_FN_BALANCE", "RPT_USSK_FN_CASHFLOW")

#: 内部字段 → 东财科目名候选（按优先级取第一个命中；冒烟校准维护）
#: 校准基线：AAPL/BABA 实测 dump-raw（见 scripts/README.md 冒烟记录）
FIELD_CANDIDATES: dict[str, tuple[str, ...]] = {
    "revenue": ("营业总收入", "营业收入", "主营收入", "总收入"),
    "cogs": ("营业成本", "主营成本", "销售成本"),
    "gross_profit": ("毛利", "毛利润"),
    "operating_income": ("营业利润", "经营溢利"),
    "pretax_income": ("持续经营税前利润", "税前利润", "利润总额"),
    "net_income": ("净利润",),
    "net_income_parent": ("归属于母公司股东净利润", "归属于普通股股东净利润", "归母净利润", "净利润"),
    "rd_expense": ("研发费用", "研发开支"),
    "sga_expense": ("销售、一般及行政费用", "销售及管理费用"),
    "interest_expense": ("利息费用",),
    "sbc": ("基于股票的补偿费",),
    "oci": ("其他全面收益合计项", "其他综合收益"),
    "comprehensive_income": ("全面收益总额",),
    "shares_diluted": ("摊薄加权平均股数-普通股", "稀释加权平均股数"),
    "total_assets": ("总资产", "资产总计"),
    "total_liabilities": ("总负债", "负债合计"),
    "total_equity": ("归属于母公司股东权益合计", "归属于母公司股东权益", "股东权益合计"),
    "cash": ("现金及现金等价物", "现金及等价物"),
    "short_term_investments": ("短期投资", "有价证券投资(流动)"),
    "long_term_investments": ("有价证券投资(非流动)", "长期投资"),
    "accounts_receivable": ("应收账款净额", "应收账款", "应收账款及票据"),
    "inventory": ("存货",),
    "goodwill": ("商誉",),
    "intangibles": ("无形资产",),
    "accounts_payable": ("应付账款", "应付账款及票据"),
    "deferred_revenue": ("递延收入", "递延收入(流动)", "合同负债"),
    "short_term_debt": ("短期债务", "短期借款"),
    "long_term_debt": ("长期负债", "长期借款", "长期债务"),
    "ocf": ("经营活动产生的现金流量净额", "经营现金流净额"),
    "icf": ("投资活动产生的现金流量净额",),
    "fcf_financing": ("筹资活动产生的现金流量净额",),
    "dividends_paid": ("股息支付", "支付股利", "已付股息"),
    "buybacks": ("回购股份", "回购普通股", "股票回购"),
}

#: capex 由多个现金流科目 abs 求和构成（符号规范化）
_CAPEX_ITEMS: tuple[str, ...] = ("购买固定资产", "购建固定资产、无形资产和其他长期资产", "购建无形资产及其他资产", "购置固定资产", "资本支出")

_CCY_MAP = {
    "人民币": "CNY", "韩元": "KRW", "韩国元": "KRW", "美元": "USD",
    "港元": "HKD", "港币": "HKD", "新台币": "TWD", "日元": "JPY",
}
_CCY_ISO = {"CNY", "KRW", "USD", "HKD", "TWD", "JPY"}


def to_secucode_candidates(symbol: str) -> list[str]:
    """美股 SECUCODE 候选：.O（OTC/纳斯达克实证可用）→ .N 回退。"""
    base = symbol.upper().split(".")[0]
    return [f"{base}.O", f"{base}.N"]


def _normalize_currency(raw: str | None) -> str | None:
    if not raw:
        return None
    s = str(raw).strip()
    if s.upper() in _CCY_ISO:
        return s.upper()
    return _CCY_MAP.get(s)


_MAX_PAGES = 4  # 单报表分页上限（pageSize=500，实测美股全科目全期次约需 2-3 页）


def _fetch_report(report_name: str, secucode: str) -> list[dict]:
    """拉单张报表全部分页（科目行展开）。网络/解析异常 → 已拉到的部分（可能为空）。

    不分页会截断历史期次（pageSize=500 上限），导致年度序列不足 5 期。
    """
    rows: list[dict] = []
    for page in range(1, _MAX_PAGES + 1):
        params = {
            "reportName": report_name,
            "columns": "ALL",
            "filter": f'(SECUCODE="{secucode}")',
            "pageNumber": str(page),
            "pageSize": "500",
            "sortColumns": "REPORT_DATE",
            "sortTypes": "-1",
            "source": "WEB",
            "client": "WEB",
        }
        url = f"{_BASE}?{urllib.parse.urlencode(params)}"
        req = urllib.request.Request(url, headers={"User-Agent": _UA})
        try:
            with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
                batch = (json.loads(resp.read().decode("utf-8")).get("result") or {}).get("data") or []
        except Exception:
            break
        rows.extend(batch)
        if len(batch) < 500:  # 最后一页
            break
    return rows


def fetch_raw_rows(symbol: str) -> tuple[str, list[dict]]:
    """拉三表原始行。返回 (命中的 secucode, rows)；两个候选均无数据 → ("", [])。"""
    for secucode in to_secucode_candidates(symbol):
        rows: list[dict] = []
        for rn in REPORTS:
            rows.extend(_fetch_report(rn, secucode))
        if rows:
            return secucode, rows
    return "", []


def _is_annual_row(row: dict) -> bool:
    """年报行识别：优先报告类型字段；回退到期末间距由调用方处理。

    东财美股实证（冒烟校准维护）：DATE_TYPE_CODE '001'=年报（YTD 累计口径）。
    """
    code = str(row.get("DATE_TYPE_CODE") or "").strip()
    if code:
        return code == "001"
    rtype = str(row.get("REPORT_TYPE") or row.get("REPORT_TYPE_NAME") or "")
    return "年报" in rtype


def extract_fields(rows: list[dict]) -> dict:
    """三表原始行 → 年度字段序列。

    返回 {"currency": str|None, "annual": {report_date: {field: value}},
          "rejected": [report_date...], "raw_item_names": [...]}。
    金额 = 报表币种原值，未经汇率换算。capex 派生自多科目 abs 求和。
    """
    by_date: dict[str, dict[str, float]] = {}
    currency_raw: str | None = None
    annual_dates: set[str] = set()
    item_names: set[str] = set()
    for row in rows:
        dt = str(row.get("REPORT_DATE") or "")[:10]
        if not dt:
            continue
        # 年度行隔离：确知非年报的行不入年度聚合，防同 REPORT_DATE 的
        # 季报/Q4 值覆盖年报值（实证：AAPL FY2024 revenue 曾被 Q4 单季值污染）
        code = str(row.get("DATE_TYPE_CODE") or "").strip()
        if code and code != "001":
            continue
        name, amount = row.get("ITEM_NAME"), row.get("AMOUNT")
        if name:
            item_names.add(str(name))
        if name and amount is not None:
            try:
                by_date.setdefault(dt, {})[str(name)] = float(amount)
            except (TypeError, ValueError):
                continue
        if currency_raw is None:
            currency_raw = row.get("CURRENCY_ABBR") or row.get("CURRENCY") or None
        if code == "001":
            annual_dates.add(dt)

    # 年报行回退识别：DATE_TYPE_CODE 缺失时，按期末间距 >=300 天筛年度序列
    if not annual_dates and by_date:
        dates = sorted(by_date)
        annual_dates = {
            dates[i] for i in range(len(dates))
            if i == 0 or (date.fromisoformat(dates[i]) - date.fromisoformat(dates[i - 1])).days >= 300
        }

    annual: dict[str, dict[str, float]] = {}
    rejected: list[str] = []
    for dt in sorted(annual_dates, reverse=True):
        items = by_date.get(dt, {})
        fields: dict[str, float] = {}
        for field, names in FIELD_CANDIDATES.items():
            for name in names:
                if name in items:
                    fields[field] = items[name]
                    break
        capex = sum(abs(items[n]) for n in _CAPEX_ITEMS if n in items)
        if capex:
            fields["capex"] = capex
        # 行级 sanity 两规则（刻意不含"权益<0"——美股回购型公司负净资产合法）
        # 注意不能用 `or` 链取值：net_income 为 0 是合法值，会被 or 短路吞掉
        rev = fields.get("revenue")
        ni = fields.get("net_income")
        if ni is None:
            ni = fields.get("net_income_parent")
        if (rev is not None and ni is not None and ni > rev * 1.05) or (rev is not None and rev <= 0):
            rejected.append(dt)
            continue
        if fields.get("ocf") is not None and fields.get("capex") is not None:
            fields["fcf"] = fields["ocf"] - fields["capex"]
        annual[dt] = fields
    return {
        "currency": _normalize_currency(currency_raw),
        "annual": annual,
        "rejected": rejected,
        "raw_item_names": sorted(item_names),
    }


def fetch_em_us_annual(symbol: str) -> dict | None:
    """美股年度字段序列。任何异常/无数据 → None（调用方走 MISSING/兜底终止）。"""
    secucode, rows = fetch_raw_rows(symbol)
    if not rows:
        return None
    result = extract_fields(rows)
    if not result["annual"]:
        return None
    result["secucode"] = secucode
    result["source"] = "eastmoney-us"
    return result


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="东财美股通道自检")
    parser.add_argument("ticker", help="如 AAPL / BABA")
    parser.add_argument("--dump-raw", action="store_true", help="打印全部原始科目名（校准用）")
    args = parser.parse_args()

    r = fetch_em_us_annual(args.ticker)
    if r is None:
        print(f"{args.ticker}: 东财无数据")
    else:
        print(f"secucode={r['secucode']} currency={r['currency']} 年度期数={len(r['annual'])}")
        for dt, fields in list(r["annual"].items())[:6]:
            print(f"  {dt}: revenue={fields.get('revenue')} ocf={fields.get('ocf')} capex={fields.get('capex')}")
        if r["rejected"]:
            print(f"  sanity 拒绝期次: {r['rejected']}")
        if args.dump_raw:
            print("原始科目名:", json.dumps(r["raw_item_names"], ensure_ascii=False, indent=1))
