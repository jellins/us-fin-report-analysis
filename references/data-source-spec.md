# 数据源规范（Data Source Specification）— 美股版

> 定义美股财报诊断的数据获取架构：默认源路由、自定义数据源准入、数据回执与降级规则。
> 核心原则：**方法论不可替换，数据源可以替换**；任何数据源都只是「数据需求清单」的填空者。

## 1. 架构分层

```
方法论层（不可变）     七层诊断框架 + 指标字典（indicator-dictionary.md，US GAAP 版）
        │ 反推
契约层（固定格式）     数据需求清单（A–E 五组字段，含 XBRL tag 提示）
        │ 路由
数据源层（可插拔）     默认源 = 本项目 scripts/ 自研实现（SEC EDGAR 主源 + 东财兜底 +
                       交叉核对 + 治理字段，见 §2）；自定义源（声明 → 校验 → 分级，见 §3）
        │ 产出
回执层（强制）         scripts/receipts/<TICKER>.json：每字段携带
                       {值序列, 期末日, 来源, raw_tag/unit, filed, accn}
```

## 2. 默认数据源：本项目自研实现（scripts/，不依赖任何外部 skill）

默认路由即本项目 `scripts/` 目录的自包含实现（纯 Python 标准库，零第三方依赖），
主入口 `fetch_manifest.py` 一次输出全字段回执 JSON：

| 通道 | 模块 | 负责范围 |
|---|---|---|
| 主源（法定披露） | `scripts/sec_edgar.py` | **SEC EDGAR XBRL**（companyconcept API，A/B/C 组主体字段，同义 tag 组回退 + 验收三条件：期数充足/新鲜度 ≤450 天/单位正确）；**submissions**（10-K/10-Q/8-K/20-F/DEF 14A filing 列表） |
| 兜底 + 次源 | `scripts/eastmoney_us.py` | 东财美股三表（中文字段）：SEC 缺失字段补齐（中概 20-F 稀疏场景）、七字段锚定交叉核对次源 |
| 交叉核对 | `scripts/cross_check.py` | revenue/net_income/total_equity/OCF/FCF/毛利/营业利润七字段：币种一致走绝对值锚定（字段等权中位数基准，偏离 >10% 且 ≥2 字段 → divergent）；币种不一致走 YoY 增幅模式（>10pp 记偏离年）。只标注、不静默修正 |
| 治理字段 | `scripts/gov_filings.py` | D 组：8-K Item 4.01/4.02/5.02 扫描（D20/D22）、10-K 审计意见证据（going-concern/CAM/ICFR，D01/D21）、Form 4 内部人交易 P/S 统计（D16） |

派生字段（C10 Δ应收/Δ递延收入、FCF=C02−C03、毛利=B01−B02）由回执内已取字段确定性计算，**禁止 LLM 估算**。

路由与合规规则：
1. SEC EDGAR 为法定披露源，优先级最高：调用时必须携带声明身份的 User-Agent（邮箱带真实域名，可用环境变量 `SEC_EDGAR_UA` 覆盖），遵守 ≤10 req/s 限速（脚本已内置 0.1s 间隔）
2. XBRL tag 在不同公司间可能有自定义扩展，取数按「同义 tag 组回退」（如 Revenues 与 RevenueFromContractWithCustomerExcludingAssessedTax 互为候选），仍取不到在回执 `missing` 标注
3. 中概股（20-F/6-K 申报人）：XBRL 覆盖可能不全且存在 USD 便利折算与本地币种混合（回执 `unit_mix` 透出），缺口由东财美股三表补齐并标注 `source=eastmoney-us`；东财填充同样过新鲜度门槛（过期序列记入 `stale_rejected`，不冒充当前值）
4. 8-K Item 4.01（审计师变更）、8-K Item 4.02（财报重述/往期报表不可信赖声明）、Form 4（内部人交易）、DEF 14A（关联交易/股权结构）是 D 组治理字段的法定来源；ICFR 意见与 material weakness 披露在 10-K（D21）；going-concern 段落随审计意见（D01）。治理脚本只取证据（命中列表/上下文片段/交易计数），语义裁决由分析层执行
5. 任何字段无法获取 → 回执 `missing` 标注，禁止估算填充；`manual_fields`（如 Non-GAAP 调节表、商誉分 reporting unit 明细）无结构化接口，回执给 filing 阅读入口
6. 跨市场对照组（E 组）：美股/ADR 对照公司用同一套 `fetch_manifest.py` 跑各自 ticker 即可；A 股对照为可选增强，可由用户自定义源提供（本 skill 不捆绑 A 股数据通道）

冒烟验证基线见 `scripts/README.md`（AAPL 双源 levels 一致、BABA 兜底+growth 核对实测）。

## 3. 自定义数据源准入（对话声明 + 即时校验）

### 3.1 触发方式

用户声明使用自有数据源（Excel/CSV、Bloomberg/FactSet/CapIQ 终端、内部数据平台、自建 API 等）时，自定义源**优先于默认源**，但须先通过准入校验。

### 3.2 准入校验清单

| # | 校验项 | 通过标准 |
|---|---|---|
| C1 | 能力覆盖声明 | 明确覆盖数据需求清单 A–E 中哪些组、缺哪些组；缺失组是否同意回落默认源 |
| C2 | 口径合规 | 确认为合并报表口径；利润字段为归母口径（attributable to common shareholders）；能区分财年；注明币种与单位（千/百万美元等） |
| C3 | 字段完整性 | A+B+C 组必需字段 100% 覆盖为完全通过；核心字段（3.4）缺失 → 不得通过 |
| C4 | 可溯源性 | 每个数值能标注来源与财年；无法溯源的数值拒绝采用 |
| C5 | 样本抽验 | 随机抽 1–2 个科目（建议 revenue、CFO）与 SEC XBRL 公开数据交叉核对，偏差须在舍入误差范围内 |

### 3.3 校验结果分级

| 等级 | 条件 | 处置 |
|---|---|---|
| ✅ 完全通过 | C1–C5 全部通过 | 全部采用自定义源 |
| ⚠️ 部分通过 | 非核心字段缺失且用户同意回落 | 缺失字段回落默认源，回执注明混合来源 |
| ❌ 不通过 | 核心字段缺失/口径不合规/不可溯源/抽验异常 | 拒绝采用，说明原因与补齐路径，询问改用默认源或补充数据 |

### 3.4 核心字段（▲ 不可缺失清单）

revenue｜COGS｜归母净利润｜net income｜NCI 损益｜CFO｜total assets｜total liabilities｜归母股东权益｜cash & equivalents｜short-term + long-term debt｜accounts receivable｜inventory｜goodwill

## 4. 数据回执机制（防幻觉强制约束）

默认源回执由 `scripts/fetch_manifest.py` 生成（`scripts/receipts/<TICKER>.json`），
逐字段携带值序列与溯源信息，指标级回执从字段回执派生：

```json
{
  "ticker": "AAPL",
  "retrieved_at": "2026-10-19T08:00:00+00:00",
  "fields": {
    "C02": {"name": "CFO", "unit": "USD", "source": "sec-edgar",
            "tag": "NetCashProvidedByUsedInOperatingActivities",
            "values": [{"end": "2025-09-27", "val": 111482000000,
                        "filed": "2025-10-31", "form": "10-K", "accn": "..."}]}
  },
  "cross_check": {"status": "consistent", "median_factor": 1.0},
  "missing": {}, "errors": {}
}
```

纪律：无回执数值禁止进入计算与结论；取不到标 `missing`，禁止估算编造；
`cross_check.status=divergent` 时报告「数据说明」节必须列出偏离字段明细；
关键指标必须可回溯来源（raw_tag + accession 可定位到具体 filing）。

## 5. 合规声明

- 本 Skill 只提供方法论、指标定义与数据源调用指引，**不分发、不转售任何市场数据**
- SEC EDGAR 数据为公共披露，使用时须遵守 SEC 公平访问政策（声明 User-Agent、限速）；商业终端数据（Bloomberg 等）由使用者按授权协议自行使用
- 本 Skill 输出为企业质地判断，不构成投资建议；美股诊断还须注意各州与联邦证券法规差异
