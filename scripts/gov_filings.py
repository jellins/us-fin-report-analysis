#!/usr/bin/env python3
"""gov_filings.py — D 组治理字段通道（8-K 条款扫描 / 审计意见证据 / Form 4 统计）。

参考 stock_aiagent_research 项目 sec_edgar_provider 的检索用法独立重写，
仅依赖 Python 标准库 + 本项目 sec_edgar 通道。

职责边界（重要）：本模块只取「证据」——条款命中列表、关键词上下文片段、
交易代码计数；语义裁决（ICFR 是否 adverse、CFO 变更是否异常、CAM 缺失
是否异常）由分析层按诊断框架执行。脚本不代替判断，但为判断提供可追溯证据，
绝不允许分析层在无证据下结论。
"""
from __future__ import annotations

import html
import re

from sec_edgar import SecRequestError, filing_document_url, list_filings, sec_get_json, sec_get_text

#: 8-K 重点条款（D20/D22 数据源）
WATCH_8K_ITEMS: tuple[str, ...] = ("4.01", "4.02", "5.02")

#: 条款语义标签（仅展示用，裁决口径见指标字典 U5-04/U5-05/D20）
ITEM_LABELS: dict[str, str] = {
    "4.01": "审计师变更（Changes in Registrant's Certifying Accountant）",
    "4.02": "财报不可依赖/重述（Non-Reliance on Previously Issued Financial Statements）",
    "5.02": "董事/高管变更（含 CFO 离职任命）",
}

_FALLBACK_FETCH_LIMIT = 20  # items 列缺失时抓 8-K 全文的上限（限速纪律）


def _strip_html(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", html.unescape(text))


def _evidence(text: str, pattern: str, *, window: int = 160, max_hits: int = 3) -> list[str]:
    """关键词上下文片段（裁决证据，原样透出不做语义加工）。"""
    out: list[str] = []
    for m in re.finditer(pattern, text, re.I):
        s = max(0, m.start() - window)
        out.append(text[s : m.end() + window].strip())
        if len(out) >= max_hits:
            break
    return out


# ═══ D20 / D22：8-K 条款扫描 ═══


def scan_8k_items(
    cik: str,
    years: int = 6,
    watch: tuple[str, ...] = WATCH_8K_ITEMS,
) -> dict:
    """近 years 年 8-K 的条款命中扫描。

    优先用 submissions 的 items 列（零额外请求）；items 缺失的老 filing
    回退抓主文档正则（上限 _FALLBACK_FETCH_LIMIT 次，遵守限速纪律）。

    返回 {"watched": [...], "item_labels": {...}, "hits": [...],
          "filings_scanned": int, "fulltext_fallbacks": int}。
    """
    filings = list_filings(cik, ("8-K",), years=years, limit=100)
    hits: list[dict] = []
    fetched = 0
    for f in filings:
        items_str = str(f.get("items") or "")
        matched = [it for it in watch if it in items_str]
        if not matched and not items_str.strip() and f.get("url") and fetched < _FALLBACK_FETCH_LIMIT:
            fetched += 1
            try:
                text = sec_get_text(f["url"], timeout=30)
            except SecRequestError:
                continue
            matched = [it for it in watch if re.search(rf"Item\s+{re.escape(it)}\b", text, re.I)]
        if matched:
            hits.append(
                {
                    "filingDate": f.get("filingDate"),
                    "items": matched,
                    "accession": f.get("accessionNumber"),
                    "url": f.get("url"),
                }
            )
    return {
        "watched": list(watch),
        "item_labels": {k: v for k, v in ITEM_LABELS.items() if k in watch},
        "hits": hits,
        "filings_scanned": len(filings),
        "fulltext_fallbacks": fetched,
    }


# ═══ D01 / D21：审计报告证据（going-concern / CAM / ICFR） ═══

_GOING_CONCERN = r"substantial\s+doubt[^.]{0,300}going\s+concern|going\s+concern[^.]{0,300}substantial\s+doubt"
_MATERIAL_WEAKNESS = r"material\s+weakness(?:es)?"
_ICFR_ADVERSE = (
    r"(?:adverse|disclaimer(?:\s+of)?)\s+opinion[^.]{0,240}internal\s+control"
    r"|internal\s+control[^.]{0,240}(?:adverse|disclaimer(?:\s+of)?)\s+opinion"
)
_CAM = r"critical\s+audit\s+matter"


def audit_flags(cik: str, max_filings: int = 2) -> list[dict]:
    """最近 max_filings 份 10-K/20-F 主文档的审计证据扫描。

    每份返回 {"form", "filingDate", "url",
              "going_concern_evidence": [...],       # G0-07 用
              "material_weakness_mentions": int,     # D21 用（出现次数，含否定语境）
              "material_weakness_evidence": [...],
              "icfr_adverse_evidence": [...],        # U5-04 用
              "cam_mentions": int}。                 # CAM 计数；大盘股为 0 需解释
    抓取失败 → 该份记 {"error": ...}（静默失败禁令：透出而非跳过）。
    """
    filings = list_filings(cik, ("10-K", "20-F"), years=4, limit=4)[:max_filings]
    reports: list[dict] = []
    for f in filings:
        url = f.get("url")
        base = {"form": f.get("form"), "filingDate": f.get("filingDate"), "url": url}
        if not url:
            reports.append({**base, "error": "无主文档 URL"})
            continue
        try:
            raw = sec_get_text(url, timeout=90)
        except SecRequestError as e:
            reports.append({**base, "error": str(e)})
            continue
        text = _strip_html(raw)
        reports.append(
            {
                **base,
                "going_concern_evidence": _evidence(text, _GOING_CONCERN),
                "material_weakness_mentions": len(re.findall(_MATERIAL_WEAKNESS, text, re.I)),
                "material_weakness_evidence": _evidence(text, _MATERIAL_WEAKNESS),
                "icfr_adverse_evidence": _evidence(text, _ICFR_ADVERSE),
                "cam_mentions": len(re.findall(_CAM, text, re.I)),
            }
        )
    return reports


# ═══ D16：Form 4 内部人交易统计 ═══


def _raw_ownership_xml_url(cik: str, filing: dict) -> str | None:
    """Form 4 原始 XML URL。

    实证坑：submissions 的 primaryDocument 指向 XSLT 渲染版
    （{accn}/xslF345X0X/form4.xml，实为 HTML），原始 ownership XML 在
    accession 根目录（命名不定），须用 accession 目录的 index.json 定位
    根级 .xml——不能从渲染版 URL 简单剥一层（会停在 xslF345X0X 子目录）。
    """
    accn = (filing.get("accessionNumber") or "").replace("-", "")
    if not accn:
        return None
    folder = filing_document_url(cik, accn, "").rsplit("/", 1)[0]  # accession 根目录
    try:
        idx = sec_get_json(f"{folder}/index.json", timeout=30)
    except SecRequestError:
        return None
    names = [i.get("name", "") for i in (idx.get("directory", {}).get("item") or [])]
    xmls = [n for n in names if n.endswith(".xml") and "/" not in n]
    if not xmls:
        return None
    xmls.sort(key=lambda n: ("form4" not in n.lower(), n))  # 优先 form4 命名
    return f"{folder}/{xmls[0]}"


def form4_summary(cik: str, years: int = 2, limit: int = 25) -> dict:
    """近 years 年 Form 4 统计（上限 limit 份，限速纪律）。

    统计 ownership XML 的 transactionCode：P=公开市场买入，S=公开市场卖出，
    其余代码（A 授予/M 行权/F 缴税代扣/G 赠与等）计入 other_codes——
    只有 P/S 代表内部人真金自掏腰包的方向信号。
    返回 {"filings_found", "filings_parsed", "open_market_buys",
          "open_market_sells", "other_codes", "insiders", "parse_errors"}。
    """
    filings = list_filings(cik, ("4",), years=years, limit=limit)
    buys = sells = other = parsed = 0
    errors: list[str] = []
    insiders: set[str] = set()
    for f in filings:
        raw_url = _raw_ownership_xml_url(cik, f)
        if not raw_url:
            errors.append(f"{f.get('filingDate')}: 无法定位原始 XML")
            continue
        try:
            xml = sec_get_text(raw_url, timeout=30)
        except SecRequestError as e:
            errors.append(f"{f.get('filingDate')}: {e}")
            continue
        parsed += 1
        for name in re.findall(r"<rptOwnerName>([^<]+)</rptOwnerName>", xml):
            insiders.add(name.strip())
        for code in re.findall(r"<transactionCode>\s*([A-Z])\s*</transactionCode>", xml):
            if code == "P":
                buys += 1
            elif code == "S":
                sells += 1
            else:
                other += 1
    return {
        "filings_found": len(filings),
        "filings_parsed": parsed,
        "open_market_buys": buys,
        "open_market_sells": sells,
        "other_codes": other,
        "insiders": sorted(insiders)[:20],
        "parse_errors": errors,
    }


# ═══ 手工字段索引（D04/D05/D06/D15/D18 等无结构化接口字段的 filing 链接） ═══


def filing_index(cik: str, years: int = 6) -> dict:
    """10-K/20-F 与 DEF 14A 列表（手工字段的阅读入口）。"""
    return {
        "annual_reports": list_filings(cik, ("10-K", "20-F"), years=years, limit=years),
        "proxy_statements": list_filings(cik, ("DEF 14A",), years=years, limit=years),
    }


if __name__ == "__main__":
    import argparse
    import json

    from sec_edgar import get_cik

    parser = argparse.ArgumentParser(description="治理字段通道自检")
    parser.add_argument("ticker", help="如 AAPL")
    args = parser.parse_args()

    cik = get_cik(args.ticker)
    print(f"ticker={args.ticker} CIK={cik}")
    if cik:
        r8k = scan_8k_items(cik)
        print(f"8-K 扫描 {r8k['filings_scanned']} 份，条款命中 {len(r8k['hits'])} 条")
        for h in r8k["hits"][:5]:
            print(f"  {h['filingDate']} Item {','.join(h['items'])}")
        f4 = form4_summary(cik, years=1, limit=10)
        print(
            f"Form 4（近1年）: 发现 {f4['filings_found']} 份，"
            f"P(买入)={f4['open_market_buys']} S(卖出)={f4['open_market_sells']}"
        )
