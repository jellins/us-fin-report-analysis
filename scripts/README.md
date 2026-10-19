# scripts/ — 美股财报数据源（本项目自包含实现）

诊断框架（`references/indicator-dictionary.md` 数据需求清单）所需全部字段的取数实现。
**纯 Python 标准库，零第三方依赖，不 import 任何外部项目/skill。**
参考 stock_aiagent_research 项目的生产实证要点独立重写。

## 模块

| 模块 | 职责 |
|---|---|
| `sec_edgar.py` | SEC EDGAR 主源：ticker→CIK 解析、companyconcept XBRL 取数、submissions filing 列表 |
| `eastmoney_us.py` | 东方财富美股三表：兜底通道 + 交叉核对次源 + 中概 20-F 稀疏补齐 |
| `cross_check.py` | 七字段锚定交叉核对（绝对值模式 + YoY 增幅模式） |
| `gov_filings.py` | D 组治理字段：8-K Item 4.01/4.02/5.02 扫描、10-K 审计意见证据、Form 4 内部人交易统计 |
| `fetch_manifest.py` | **主入口**：全字段取数 + 东财兜底 + 交叉核对 + 治理字段 + 派生字段 + 回执 JSON |

## 用法

```bash
# 全字段取数（默认输出 scripts/receipts/<TICKER>.json）
python3 scripts/fetch_manifest.py AAPL
python3 scripts/fetch_manifest.py BABA --out receipts/BABA.json

# 快速通道自检
python3 scripts/sec_edgar.py AAPL --tag Revenues
python3 scripts/eastmoney_us.py AAPL --dump-raw   # 打印东财原始科目名（校准用）
python3 scripts/gov_filings.py AAPL
python3 scripts/cross_check.py                     # 合成样本自检

# 选项
#   --min-years N   年度期数门槛（默认 5，对应字典"≥5 财年"要求）
#   --skip-gov      跳过治理字段（10-K 原文下载量大，快取时用）
#   --skip-em       跳过东财通道（兜底+交叉核对）
#   --out -         回执仅打印到 stdout
```

环境变量 `SEC_EDGAR_UA` 可覆盖默认 User-Agent（SEC 公平访问政策要求可联系身份，
邮箱须带真实域名后缀，否则 Akamai 直接 403）。

## 回执 JSON 结构

```json
{
  "ticker": "...", "cik": "...", "company": "...", "retrieved_at": "...",
  "currency": {"sec": "USD", "em": "USD", "unit_mix": {"USD": 30, "CNY": 11}},
  "fields":    {"<字段ID>": {"name", "unit", "source", "coverage", "values": [{"end","val","filed","form","accn"}...]}},
  "derived":   {"FCF_DERIVED", "GROSS_PROFIT_DERIVED", "C10"},   // 确定性计算，非 LLM 估算
  "missing":   {"<字段ID>": "字段名"},                            // 双源均无（或僵尸 tag）
  "episodic_absent": ["C09", ...],       // 偶发字段无近期值 ≈ 该类业务未发生
  "partial_coverage": {"<字段ID>": 期数}, // 有数据但不足 min_years 期（次新股等）
  "manual_fields": {"<字段ID>": "阅读指引"}, // XBRL 无结构化数据，须读 filing 原文
  "em_fallback": {"filled": {...}, "stale_rejected": {...}, "rejected_rows": [...]},
  "governance": {"D20_D22_8k_items", "D01_D21_audit_evidence", "D16_form4", "filing_index"},
  "cross_check": {"status": "consistent|divergent|insufficient|skipped", ...},
  "core_missing": ["B18", ...],          // ▲16 项核心字段中缺失者
  "errors": {"<字段ID>": "错误信息"}      // 静默失败禁令：网络错误透出，不吞
}
```

## 通道纪律（与 SKILL.md 数据源铁律对应）

1. **静默失败禁令**：SEC 主源失败即抛 `SecRequestError`（含 HTTP 状态码）；
   回执 `errors` 节透出，绝不返回空数据冒充成功。东财为兜底层，失败语义是
   「无数据」，但 sanity 拒绝期次（`rejected_rows`）必须透出。
2. **验收三条件**（同义 tag 回退的每个候选）：年度期数 ≥min_years、
   最新期末距今 ≤450 天（僵尸 tag 防护——实证：AMZN capex tag 2017 年后停披）、
   单位正确。
3. **年度/季度甄别**：流量字段按 start/end 跨度 300–380 天筛年度；
   存量字段优先 fp=="FY"，不足回退 form ∈ 10-K/20-F。同财年多版本按 filed 最新去重。
4. **限速**：SEC ≤10 req/s（进程内 0.1s 间隔）；东财分页上限 4 页/报表。
5. **币种铁律**：数值币种以各源自身标注为准（SEC unit / 东财 CURRENCY 字段），
   严禁跨源借用。ADR 混合单位（USD 便利折算 + 本地币种）在 `unit_mix` 透出，
   **跨字段计算比率前必须核对 unit 一致**。
6. **交叉核对**：币种一致走绝对值锚定（字段等权中位数基准，>10% 且 ≥2 字段
   → divergent）；币种不一致走 YoY 增幅模式（币种无关，>10pp 记偏离年）。
   只标注、不静默修正。

## 冒烟验证记录（2026-10-19 实测）

| 用例 | 结果 |
|---|---|
| AAPL 主源 | 39 字段全 USD，B01 FY2025 revenue $416.161B 与 10-K 一致 |
| AAPL 双源核对 | levels 模式 `consistent`，median factor = 1.0，7 字段全对齐 |
| AAPL 治理 | 8-K 命中 11 条（均为 Item 5.02 高管变更）；10-K 审计证据 going-concern 0 段、CAM 5 次；Form 4 解析正常（P/S 计数 + 内部人名单） |
| AAPL 陈旧拦截 | 东财商誉序列最新值 2016（苹果 2017 起不再单列）→ `stale_rejected`，不冒充当前值 |
| BABA 主源 | 44 字段（USD 便利折算 30 + CNY 11 + shares 1），FY2026 revenue $148.4B |
| BABA 兜底 | 东财补齐 A23/A25/A29/A36/C03 共 5 个 20-F 稀疏字段 |
| BABA 双源核对 | growth 模式 `divergent`：net_income FY2023 +7.9% vs +54.6%（46.7pp，归母 vs 总额口径分歧，真实信号）；revenue FY2021 11.4pp 为美元升值汇率噪声 |
| 僵尸 tag 防护 | AAPL `Revenues`（2018 年停披）正确拒绝，回退 `RevenueFromContractWithCustomerExcludingAssessedTax` |

## 已知边界

- **派生字段只由已取字段确定性计算**（C10=Δ(A04+A05)/ΔA26、FCF=C02−C03、
  毛利=B01−B02），任何指标不允许 LLM 凭空捏造。
- `manual_fields`（A18/B23/D04-D09 部分/D15/D17-D19）无结构化接口，
  回执给阅读入口（filing_index 的 10-K/DEF 14A 链接），由分析层读原文。
- Form 4 原始 XML 须绕开 XSLT 渲染版（`xslF345X0X/form4.xml` 是 HTML），
  经 accession 目录 `index.json` 定位根级 XML。
- 东财科目名为中文（`FIELD_CANDIDATES` 按 AAPL/BABA 实测校准）；
  新增公司若字段缺失，跑 `--dump-raw` 核对科目名后补候选。
- 东财 Capex 符号口径混杂（部分期次正数记账）→ 一律 abs 规范化。
- 行级 sanity 仅两条（净利>营收×1.05 / 营收≤0 整行拒绝）；**刻意不做
  「权益<0 拒绝」**——美股回购文化下负净资产合法（麦当劳/星巴克）。
