#!/usr/bin/env python3
"""sec_edgar.py — SEC EDGAR 取数通道（us-fin-report-analysis 自包含实现）。

参考 stock_aiagent_research 项目 dataflows/prosperity 模块的生产实证实现独立重写，
不 import、不依赖任何外部项目。仅依赖 Python 标准库。

硬约束（SEC 公平访问政策 + 实证教训）：
1. User-Agent 必须声明可联系身份且邮箱带真实域名后缀
   （Akamai 对 "@local" 类无域名邮箱直接 403；可用环境变量 SEC_EDGAR_UA 覆盖默认值）；
2. 全局限速 <=10 req/s（进程内最小请求间隔 0.1s，SEC 官方阈值，超限封 IP 10 分钟）；
3. 失败即抛 SecRequestError：HTTP 非 200 → 带 status_code 抛出（404 = 该公司无此科目，
   属正常语义）；绝不返回空 dict 冒充无数据（静默失败禁令）。

取数要点（实证校准）：
- ticker → CIK：company_tickers.json，CIK 10 位零填充；文件缓存 24h（CLI 进程独立）。
- companyconcept 响应 units 单位键优先级：USD > USD/shares > shares > 首个可用。
- 同义 tag 组验收三条件（不是"取到就行"）：
  ① 期次充足（年度值 >=min_years 个不同财年）；② 新鲜度（最新期 end 距今 <=max_age_days，
  排除僵尸 tag——实证：AMZN 2017 年后停披 PaymentsToAcquirePropertyPlantAndEquipment）；
  ③ 单位正确。
- 年度/季度甄别：同一 tag 下 10-K 年度值与 10-Q 季度/YTD 值混杂——
  流量字段（利润表/现金流量表）按 start/end 跨度 300–380 天筛年度；
  存量字段（资产负债表）优先 fp=="FY"，不足回退 form in (10-K/20-F)。
- 同一财年末多版本（重述/更正）→ 按 filed 最新者为准。
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime
from pathlib import Path

SEC_UA = os.environ.get(
    "SEC_EDGAR_UA", "us-fin-report-analysis/1.0 (research; contact: research@example.com)"
)
SEC_MIN_INTERVAL = 0.1  # 秒，<=10 req/s
_TIMEOUT = 20

_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
_CONCEPT_API = "https://data.sec.gov/api/xbrl/companyconcept"
_SUBMISSIONS_API = "https://data.sec.gov/submissions"
_ARCHIVES = "https://www.sec.gov/Archives"

_CACHE_DIR = Path(__file__).resolve().parent / ".cache"
_TICKERS_CACHE_TTL = 86400  # 24h

_LAST_REQUEST_TS = 0.0


class SecRequestError(RuntimeError):
    """SEC 请求失败（HTTP 非 200 / 解析失败）。status_code 供调用方分流 404。"""

    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


def _throttle() -> None:
    global _LAST_REQUEST_TS
    wait = (_LAST_REQUEST_TS + SEC_MIN_INTERVAL) - time.monotonic()
    if wait > 0:
        time.sleep(wait)
    _LAST_REQUEST_TS = time.monotonic()


def sec_get_json(url: str, params: dict | None = None, timeout: float = _TIMEOUT) -> dict:
    """带 UA + 限速的 GET，返回解析后的 JSON。失败即抛，绝不吞成空 dict。"""
    if params:
        url = f"{url}?{urllib.parse.urlencode(params)}"
    _throttle()
    req = urllib.request.Request(url, headers={"User-Agent": SEC_UA})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise SecRequestError(f"SEC HTTP {e.code}: {url}", status_code=e.code) from e
    except (urllib.error.URLError, TimeoutError) as e:
        raise SecRequestError(f"SEC 网络异常: {url}: {e}") from e
    except json.JSONDecodeError as e:
        raise SecRequestError(f"SEC 响应非 JSON: {url}") from e
    if not isinstance(payload, dict):
        raise SecRequestError(f"SEC 响应非对象载荷: {url}")
    return payload


def sec_get_text(url: str, timeout: float = 60) -> str:
    """取 filing 原文（HTML/文本），用于治理字段证据抽取。失败即抛。"""
    _throttle()
    req = urllib.request.Request(url, headers={"User-Agent": SEC_UA})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        raise SecRequestError(f"SEC HTTP {e.code}: {url}", status_code=e.code) from e
    except (urllib.error.URLError, TimeoutError) as e:
        raise SecRequestError(f"SEC 网络异常: {url}: {e}") from e


# ═══ ticker → CIK ═══


def get_cik(ticker: str) -> str | None:
    """ticker → 10 位零填充 CIK；company_tickers.json 文件缓存 24h（CLI 进程独立）。"""
    _CACHE_DIR.mkdir(exist_ok=True)
    cache_file = _CACHE_DIR / "company_tickers.json"
    payload: dict | None = None
    if cache_file.exists() and time.time() - cache_file.stat().st_mtime < _TICKERS_CACHE_TTL:
        try:
            payload = json.loads(cache_file.read_text())
        except (json.JSONDecodeError, OSError):
            payload = None
    if payload is None:
        payload = sec_get_json(_TICKERS_URL, timeout=30)
        try:
            cache_file.write_text(json.dumps(payload))
        except OSError:
            pass
    for row in payload.values():
        if isinstance(row, dict) and str(row.get("ticker", "")).upper() == ticker.upper():
            return f"{int(row['cik_str']):010d}"
    return None


# ═══ companyconcept XBRL ═══

_UNIT_PRIORITY = ("USD", "USD/shares", "shares")


def fetch_concept(cik: str, tag: str, taxonomy: str = "us-gaap") -> dict:
    """取单 tag 全量事实。404 → SecRequestError(status_code=404)（该公司无此科目）。"""
    return sec_get_json(f"{_CONCEPT_API}/CIK{cik}/{taxonomy}/{tag}.json")


def pick_unit_facts(payload: dict, prefer: tuple[str, ...] = _UNIT_PRIORITY) -> tuple[str, list[dict]]:
    """units 中按优先级选单位键，返回 (unit, facts)；无可用返回 ("", [])。"""
    units = payload.get("units") or {}
    for u in prefer:
        if u in units and units[u]:
            return u, units[u]
    for u, facts in units.items():
        if facts:
            return u, facts
    return "", []


def _span_days(fact: dict) -> int | None:
    start, end = fact.get("start"), fact.get("end")
    if not start or not end:
        return None
    try:
        return (date.fromisoformat(end) - date.fromisoformat(start)).days
    except ValueError:
        return None


def _dedup_latest_filed(facts: list[dict]) -> list[dict]:
    """同一 end 多版本（重述/更正）按 filed 最新者为准；按 end 倒序。"""
    by_end: dict[str, dict] = {}
    for f in facts:
        end = f.get("end")
        if not end or f.get("val") is None:
            continue
        cur = by_end.get(end)
        if cur is None or (f.get("filed") or "") > (cur.get("filed") or ""):
            by_end[end] = f
    return [by_end[k] for k in sorted(by_end, reverse=True)]


def select_annual_facts(
    facts: list[dict],
    *,
    kind: str = "duration",
    min_years: int = 5,
    max_age_days: int = 450,
) -> list[dict] | None:
    """从 units 中筛年度值并按验收三条件判定。

    kind="duration"（利润/现金流）：start/end 跨度 300–380 天为年度（10-K 财年值；
    排除 10-Q 的季度值与 YTD 累计值）。
    kind="instant"（资产负债表）：优先 fp=="FY"，不足回退 form in (10-K/20-F)。

    验收：① 不同财年末 >=min_years；② 最新期末距今 <=max_age_days（僵尸 tag 防护）。
    通过返回 [{end,val,filed,form,accn}, ...]（新→旧），不通过返回 None。
    """
    if kind == "duration":
        annual = [f for f in facts if (s := _span_days(f)) is not None and 300 <= s <= 380]
    else:  # instant
        fy = [f for f in facts if f.get("fp") == "FY" and not f.get("start")]
        if len({f.get("end") for f in fy}) < min_years:
            fy = [
                f for f in facts
                if not f.get("start") and f.get("form") in ("10-K", "20-F", "10-K/A", "20-F/A")
            ]
        annual = fy
    annual = _dedup_latest_filed(annual)
    if len(annual) < min_years:
        return None
    try:
        latest_end = date.fromisoformat(annual[0]["end"])
    except (ValueError, KeyError):
        return None
    if (date.today() - latest_end).days > max_age_days:
        return None  # 僵尸 tag：有历史数据但已停披
    return annual


def fetch_annual_tag(
    cik: str,
    tag: str,
    *,
    kind: str = "duration",
    min_years: int = 5,
    max_age_days: int = 450,
) -> dict | None:
    """单 tag 年度值取数：404/不足/不新鲜 → None（调用方走同义 tag 回退）。

    多单位处理（ADR 实证坑）：20-F 发行人同一 tag 常同时有本地币种全序列
    与 USD 便利折算（仅最近 1-2 期）。固定偏好 USD 会把多年 CNY 序列丢弃，
    故按单位偏好序逐个尝试验收三条件，首个通过的单位胜出。

    返回 {"tag", "unit", "values": [{end,val,filed,form,accn}...]}。
    """
    try:
        payload = fetch_concept(cik, tag)
    except SecRequestError as e:
        if e.status_code == 404:
            return None
        raise
    units = payload.get("units") or {}
    if not units:
        return None
    # 单位候选序：USD > USD/shares > shares > 其余（按事实数降序，多者优先）
    ordered = [u for u in _UNIT_PRIORITY if units.get(u)]
    ordered += sorted(
        (u for u in units if u not in _UNIT_PRIORITY and units[u]),
        key=lambda u: -len(units[u]),
    )
    for unit in ordered:
        annual = select_annual_facts(
            units[unit], kind=kind, min_years=min_years, max_age_days=max_age_days
        )
        if annual is not None:
            return {
                "tag": tag,
                "unit": unit,
                "values": [
                    {k: f.get(k) for k in ("end", "val", "filed", "form", "accn")} for f in annual
                ],
            }
    return None


def fetch_annual_with_fallback(
    cik: str,
    tags: tuple[str, ...] | list[str],
    *,
    kind: str = "duration",
    min_years: int = 5,
    max_age_days: int = 450,
) -> dict | None:
    """同义 tag 组按序回退，取第一个通过验收三条件的 tag。"""
    for tag in tags:
        result = fetch_annual_tag(
            cik, tag, kind=kind, min_years=min_years, max_age_days=max_age_days
        )
        if result is not None:
            return result
    return None


# ═══ submissions（filing 列表，D 组治理字段索引源） ═══


def get_submissions(cik: str) -> dict:
    """公司完整 filing 索引（data.sec.gov/submissions/CIK{cik}.json）。"""
    return sec_get_json(f"{_SUBMISSIONS_API}/CIK{cik}.json")


def list_filings(
    cik: str,
    forms: tuple[str, ...] | list[str],
    *,
    years: int = 6,
    limit: int = 50,
) -> list[dict]:
    """近 years 年指定 form 的 filing 列表（新→旧），含主文档 URL。"""
    payload = get_submissions(cik)
    recent = payload.get("filings", {}).get("recent", {})
    forms_set = {f.upper() for f in forms}
    cutoff = date.today().replace(year=date.today().year - years)
    out: list[dict] = []
    keys = ("form", "filingDate", "accessionNumber", "primaryDocument", "items")
    for i, form in enumerate(recent.get("form", [])):
        if form.upper() not in forms_set:
            continue
        fdate = recent.get("filingDate", [""])[i]
        try:
            if date.fromisoformat(fdate) < cutoff:
                continue
        except ValueError:
            continue
        row = {k: (recent.get(k, [None])[i] if i < len(recent.get(k, [])) else None) for k in keys}
        accn = (row["accessionNumber"] or "").replace("-", "")
        doc = row.get("primaryDocument") or ""
        row["url"] = f"{_ARCHIVES}/edgar/data/{int(cik)}/{accn}/{doc}" if accn and doc else None
        out.append(row)
        if len(out) >= limit:
            break
    return out


def filing_document_url(cik: str, accession: str, primary_doc: str) -> str:
    """拼接 filing 主文档 URL。"""
    return f"{_ARCHIVES}/edgar/data/{int(cik)}/{accession.replace('-', '')}/{primary_doc}"


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="SEC EDGAR 通道自检")
    parser.add_argument("ticker", help="如 AAPL")
    parser.add_argument("--tag", default="Revenues", help="XBRL tag")
    args = parser.parse_args()

    cik = get_cik(args.ticker)
    print(f"ticker={args.ticker} CIK={cik}")
    if cik:
        r = fetch_annual_tag(cik, args.tag)
        if r:
            print(f"tag={r['tag']} unit={r['unit']} 年度期数={len(r['values'])}")
            for v in r["values"][:6]:
                print(f"  {v['end']}: {v['val']:,} (filed {v['filed']}, {v['form']})")
        else:
            print(f"tag={args.tag} 年度值不足 5 期或不新鲜（或为 IFRS 报送 ADR）")
