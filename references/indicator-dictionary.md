# 指标字典（Indicator Dictionary）— US GAAP 版 v2

> 本文件是美股财报诊断的**唯一指标来源**。执行诊断时只允许使用本字典中的指标、公式与裁决规则，禁止自创指标、禁止修改公式、禁止脱离口径计算。
> 指标 ID 与 A 股版（a-share-fin-report-analysis）保持同构，便于跨市场对比；US 特有指标以 `U` 前缀编号。
> 标注〔经验值〕的阈值为初筛代理指标，最终裁决必须落到「自身连续 ≥5 个财年趋势 + 同行业 2–3 家对比」。

## 通用口径（适用于全部指标）

- 报表口径：合并报表（consolidated statements），禁止使用母公司单体数据
- 利润口径：net income attributable to common shareholders / parent（归母口径），剔除 noncontrolling interests
- 财年对齐：按公司自身财年（fiscal year），跨公司对比时注意财年截止月份差异
- 披露载体：10-K（年报）为主，10-Q 仅作参考；外国私人发行人（FPI，含中概股）看 20-F 与 6-K
- 平均值定义：（期初 + 期末）÷ 2；单位与币种必须在数据回执中注明，跨币种先统一折算

### MISSING 分层处置（数据缺失时的固定规则）

- 字段级：取不到的字段在回执中标注 `MISSING`，禁止估算、禁止编造
- 指标级：某指标所需字段 MISSING → 该指标状态记为「无法计算」，不参与红灯/预警/加分任何计数
- 评级级：▲核心字段缺失导致任一否决级指标无法计算 → 输出「数据不足，暂不定级」；非否决级指标「无法计算」≥3 个 → 触发降档（仅适用于正向评级，见评级聚合规则）；无法计算指标清单必须列入诊断报告

---

## 第 0 层 前置闸口（任一不过则终止）

> 执行顺序：**G0-05 行业适用性与 G0-06 风险警示优先于 G0-01～G0-04 执行**；中概股另须先过 U0-01。G0-07（going-concern）为红灯项而非终止项，随 G0-01 审计意见一并检查。

| ID | 检查项 | 通过条件 | 所需数据 |
|---|---|---|---|
| G0-05 | 行业适用性（优先执行） | 非银行/保险/券商/REITs/多元金融行业，且非 MLP/BDC/royalty trust 等 pass-through 结构；金融业（含 REITs）与 pass-through 结构 → 终止诊断并输出标准说明：「金融、REITs 与 MLP/BDC 等 pass-through 企业报表结构与指标体系完全不同（资本充足率/FFO/不良率/可分配现金流等），本框架强行套用会产生系统性误判，建议使用金融专用分析框架」 | 行业分类（数据源可得口径，回执标注） |
| G0-06 | 风险警示状态 | 当前未处于 Chapter 11 破产保护、退市警告（持续低于 $1 报价缺陷通知）、OTC 降级状态；命中 → 直接排除 | 公司最新状态（行情/公告/8-K） |
| G0-01 | 审计意见 | 近 5 个财年全部为 unqualified opinion，更早年度不追溯；带 critical audit matters（CAM）提示的无保留意见 → 通过，须阅读 CAM 内容并写入报告；大盘股普遍有 CAM，常规存在**不计预警**，仅以下任一命中才记预警：① CAM 涉及收入确认/商誉减值/并购对价/金融工具估值高危科目；② 数量同比异常增加（如 1 → 3+）；③ 指向科目与其他红灯互证 | 10-K/20-F 审计意见（D01，含 going-concern 段落） |
| G0-07 | going-concern 疑虑 | 近 5 个财年审计意见无持续经营疑虑（going-concern）段落；命中**不终止**，记风险级红灯进入评级聚合（濒死信号，与 G0-06 呼应） | 10-K/20-F 审计意见（D01） |
| G0-02 | 报表口径 | consolidated + 归母口径 | 数据源元信息 |
| G0-03 | 上市年限 | 以**上市后财报年份**计满 5 年为正向评级完整窗口；不足 → 评级上限「可关注」+ 状态标注「短历史」（「降权」的机械映射，见评级聚合规则）；**SPAC 借壳自 de-SPAC 起重新起算**；无法核验借壳史时标注「未核验借壳史」 | IPO/de-SPAC 日期（D09） |
| G0-04 | 数据完备性（双轨制） | ① 正向评级资格：≥5 个上市后财年三表齐备方可进入「优质候选/可关注」正常档，不足 → 上限「可关注」+「短历史」标注，不终止；招股说明书（S-1/F-1）年份可用于趋势观察与排雷否决，但不计入正向窗口。② **排雷否决权不受年限限制**：任何数据窗口命中否决级红灯 → 直接排除。③ <3 财年且无否决级红灯 → 输出「数据不足，暂不定级」。④ 仅同行对照组不齐 → 进入「无同行对比降级模式」（裁决改用 5 财年趋势 + 绝对参照线，评级上限「可关注」，见评级聚合规则） | 数据需求清单覆盖检查 |
| U0-01 | 中概股结构闸口 | 中概股：检查 VIE 结构、审计所 PCAOB 可检查性、HFCAA 状态；二分裁决——重大异常（VIE 不透明/审计不可检查/HFCAA 倒计时）→ 终止；一般瑕疵 → 评级上限「可关注」+ 状态标注 | 20-F 风险因素、PCAOB 公开名单 |

## 第 1 层 安全性

| ID | 指标 | 公式 | 参照线 | 裁决规则 | 红灯分级 |
|---|---|---|---|---|---|
| S1-01 | 类现金覆盖短期有息负债 | （cash & equivalents + short-term investments）÷ 短期有息负债* | ≥1 | <1 → 红灯（短期偿付生死线失守） | 风险级 |
| S1-02 | 有息负债率 | 有息负债 ÷ 总资产 | >60%〔经验值〕高危 | 超线 → 原则上回避；回购驱动型公司须结合 U6-01 判断 | 风险级 |
| S1-03 | 存贷双高变体 | 类现金充裕却大量发债，且 interest income ÷ 平均类现金显著低于市场利率 | 利息收入匹配 | 双高 + 利息收入异常偏低 → 红灯（现金真实性存疑；中概股从严）；结构性差异（境内外币种错配）须在报告中注明 | 否决级 |
| S1-04 | 流动比率 / 速动比率 | current assets ÷ current liabilities；速动剔除存货 | 参照约 2 / 约 1 | 仅辅助预警：持续恶化或显著低于同行 → 预警 | — |
| S1-05 | 利息保障倍数 | （pretax income + interest expense）÷ interest expense | 越高越好 | 逼近 1 或持续下滑 → 预警 | — |
| S1-06 | 债务现金流杠杆 | 全部有息负债 ÷ CFO（≈ 现有现金流还清全部债务所需年数） | >5〔经验值〕警惕 | 单年超线 → 预警；持续多年超线且趋势恶化，或超线与 U1-01 到期墙同时命中 → 红灯 | 风险级 |
| U1-01 | 债务到期墙 | 未来 2 年到期债务 ÷（类现金 + 年 CFO）；浮动利率占比 | 到期集中 + 高浮动占比 | 紧缩周期命中 → 预警升级 | — |

*短期有息负债 = commercial paper + short-term debt + current portion of long-term debt；全部有息负债 = 短期有息负债 + long-term debt + finance lease liabilities；operating lease liabilities 作债务等价物附注。美股回购文化下公司主动低息发债，**总债务覆盖不是生死线**（回购驱动型公司须结合 U6-01 判断）；报告须并列呈现「类现金 + 非流动有价证券（A36）vs 全部有息负债」作补充观察

## 第 2 层 资产质量

| ID | 指标 | 公式 | 参照线 | 裁决规则 | 红灯分级 |
|---|---|---|---|---|---|
| S2-01 | 应收类资产占比 | （accounts receivable + contract assets/unbilled）÷ 总资产 | >30%〔经验值〕警惕 | 超线或持续上行 → 预警/红灯 | 风险级 |
| S2-02 | 应收-营收增速差 | 应收类增速 − revenue 增速 | 持续为正 | 连续多年为正 → 红灯（渠道压货/收入注水嫌疑） | 否决级 |
| S2-03 | 坏账宽松度 | allowance for doubtful accounts ÷ gross receivables，同行对比 | 不劣于同行 | 显著宽松 → 预警 | — |
| S2-05 | 存货周转率 | COGS ÷ 平均存货 | 同行对比 | 见 S2-06 组合裁决；轻资产行业豁免见豁免表 | — |
| S2-06 | 存货-毛利悖论 | 存货周转率趋势 × gross margin 趋势 | 同向为常 | 周转降 + 毛利率升 → 红灯（产量分摊造假嫌疑） | 否决级 |
| S2-07 | CIP 异常 | construction in progress 长期挂账且持续追加 | 长期不转固 | 命中 → 红灯 | 风险级 |
| S2-08 | 商誉占比 | 主口径：goodwill ÷ 总资产（机械稳定，不受回购缩表影响）；参照口径：goodwill ÷ 归母净资产（仅净资产 >0 时并列呈现，不参与预警计数） | 总资产口径 >25%〔经验值〕警惕 | 超线 → 预警 + 下钻（美股并购文化下须同行校准）；显著高于同行，或大额收购后 2–3 年内出现减值迹象/减值历史恶劣（D04）→ 红灯 | 风险级 |
| S2-09 | 费用资产化占比 | （capitalized software + deferred costs 等）÷ 总资产 | 越小越好 | 大且增长 → 预警 | — |
| S2-10 | 杂项资产占比 | other assets / other receivables ÷ 总资产 | 优秀公司低 | 巨大且无解释 → 红灯（垃圾筐科目） | 否决级 |
| S2-13 | 非主业资产占比 | 非主业股权投资与金融资产 ÷ 总资产 | 持续走高 | 预警（主业见顶信号） | — |
| S2-14 | 递延收入强度（正向） | deferred revenue ÷ revenue；趋势 | 持续为正且上行 | 上行 → 加分；SaaS 行业天然高，按行业语境裁决 | — |
| S2-15 | 上游占款强度（正向） | accounts payable ÷ COGS | 高且稳定 | 高 → 加分（无偿占用上游 = 产业链强势） | — |
| S2-16 | 递延所得税异动 | deferred tax assets/liabilities 年度变动幅度 | 突变 | 异常变动 → 预警（利润调节旁证） | — |
| U2-01 | 股本稀释率 | 加权稀释股数年增速 + SBC ÷ revenue | 股数年增 >3%〔经验值〕或 SBC/revenue 高企 | 命中 → 预警（EPS 增长被稀释填充） | — |
| U2-02 | 无形资产依赖度 | acquired intangibles ÷ 总资产；摊销政策对比 | 并购堆出的高占比 | 高占比 + 长摊销年限 → 预警 | — |

## 第 3 层 盈利质量

| ID | 指标 | 公式 | 参照线 | 裁决规则 | 红灯分级 |
|---|---|---|---|---|---|
| S3-01 | 毛利率 | （revenue − COGS）÷ revenue | 稳定 >40%〔经验值〕多有护城河；<20% 红海 | 同行对比优先；无支撑显著高于同行 → 红灯（造假嫌疑） | 否决级 |
| S3-02 | 运营费用率 | （SG&A + R&D）÷ gross profit | <30% 优秀；30–70% 正常；>70%〔经验值〕排除 | 单年超线 → 预警 + 下钻（禁止单年定性）；连续多年超线 → 红灯；interest expense 由第 1 层处理 | 否决级（须连续多年命中） |
| S3-03' | 资本化软件检查 | capitalized software 新增额 ÷ 当年研发相关投入 | 显著高于同行 | US GAAP 研发原则费用化；大量资本化软件 → 红灯 | 风险级 |
| S3-04' | 主业成色（US 口径） | 非经营损益（investment gains + disposal gains + other non-operating income）÷ pretax income | 占比低 | 占比高 → 红灯；同时必须查 U3-01 | 风险级 |
| S3-05 | 经营利润率 | operating income ÷ revenue（或营业利润替代口径，注明） | 趋势与同行 | 持续下滑 → 预警 | — |
| U3-01 | Non-GAAP 差异率 | （Non-GAAP net income − GAAP net income）÷ \|GAAP net income\|；**分母保护**：\|GAAP net income\| ÷ revenue < 2% 或 GAAP 亏损时，改用（Non-GAAP − GAAP）÷ revenue 裁决 | 持续 \|差异率\| >30%〔经验值〕警惕；分母保护口径下差异额 ÷ revenue > 5%〔经验值〕警惕 | 连续多年超阈 → 红灯；**方向反转（正负号切换）本身即红灯**——GAAP 被一次性收益粉饰或 Non-GAAP 美化，皆属利润质量警报；GAAP 亏损而 Non-GAAP 盈利本身记预警；逐项审查调整项名实 | 风险级 |
| S3-06 | 少数股东损益占比 | NCI 损益 ÷ net income | 异常高 | 高 → 预警，盈利指标改归母口径复核 | — |
| S3-07 | OCI 背离度 | comprehensive income − net income | 显著背离 | 背离巨大 → 预警；金融属性标的升级为红灯级 | — |
| S3-08 | 折旧摊销政策 | 年限/残值率与同行对比（附注） | 不异于同行 | 显著偏松 → 预警 | — |

## 第 4 层 现金验证

| ID | 指标 | 公式 | 参照线 | 裁决规则 | 红灯分级 |
|---|---|---|---|---|---|
| S4-01' | 营收含金量（间接法推导） | 估算收现 = revenue − Δ应收类（A04+A05）+ Δ递延收入（A26）；比值 = 估算收现 ÷ revenue（美国无增值税，健康值约 1.0，不同于 A 股含税口径） | 长期累计 ≥1 | 单年 <1 → 预警 + 下钻（禁止单年定性）；长期累计 <1 → 红灯（收入真实性质疑） | 否决级（累计口径） |
| S4-02 | 利润含金量 | CFO ÷ 归母净利润；长期累计 = 近 5 财年合计 CFO ÷ 合计归母净利润 | 长期累计 ≥1 | 长期累计 <0.5 或为负 → 红灯；单年 <1 → 预警。旁证口径（不计数、须在报告并列呈现）：(CFO − SBC) ÷ 归母净利——间接法将 SBC 加回 CFO，高 SBC 公司须观察扣除后的含金量 | 否决级（累计口径） |
| S4-03 | CFO 符号 | 直接取值 | 长期为正 | 常年为负 → 红灯 | 否决级 |
| S4-04 | 自由现金流 | CFO − capex（C03）；长期 = 近 5 财年合计。capex 口径脚注：C03 不含融资租赁新增与资本化软件采购（非现金或其他科目列支），lease-heavy 公司 FCF 存在高估，须在报告附注说明 | 长期为正 | 长期为负 → 预警（扩张耗血）；单年转负 → 预警 + 下钻投向 | — |
| S4-05 | 投资现金流方向 | CFI 符号 + 投向（capex / M&A / 证券） | 为负且投向主业能力圈 | 长期为正 → 预警；频繁大额跨界并购 → 红灯 | 风险级 |
| S4-06 | 现金流肖像 | （CFO, CFI, CFF）符号八分类（连续 5 财年逐年判定） | 见下表 | 按多期判定五条规则定性 | 否决级（排除类主导型） |
| S4-07' | 股东回报检验 | （dividends + net buybacks）÷ FCF；累计融资 vs 累计回报 | 回报可持续且不超 FCF | 举债回购/回报持续超 FCF → 预警；高价回购毁价值须注明 | — |

**S4-06 现金流肖像分类表**（顺序：经营 / 投资 / 筹资）

| 组合 | 类型 | 定性 |
|---|---|---|
| + − − | 奶牛型 | 最优：主业造血、对内扩张、回报股东 |
| + − + | 蛮牛型 | 高风险高关注：裁决点为项目可靠性与资金链紧绷度 |
| + + − | 老母鸡型 | 成熟期现金牛；成长视角下为主业见顶信号 |
| + + + | 妖精型 | 三面来钱去向不明，警惕圈钱 |
| − + + | 骗吃骗喝型 | 排除 |
| − + − | 混吃等死型 | 排除 |
| − − + | 赌徒型 | 排除（融资收紧即断裂） |
| − − − | 大出血型 | 直接排除 |

**S4-06 多期判定规则（替代单年定性，与总则「禁止单年数据定性」对齐）**

1. **逐年分类**：连续 5 个财年各自按符号八分类，序列全量呈现于报告
2. **主导型**：5 年中出现频次最高的类型为定性标签；并列取较差者，优劣序固定：奶牛 > 老母鸡 > 蛮牛 > 妖精 > 排除类四型
3. **最新年校验**：最新年优于主导型 → 标「边际改善」；劣于主导型 → 标「边际恶化」并触发当年大额现金事件下钻
4. **红灯分级**：主导型为排除类 → 否决级红灯；主导型非排除类但 5 年内 ≥2 年落入排除类 → 风险级红灯；仅最新 1 年为排除类且此前健康 → 预警 + 下钻当年事件，不定红灯
5. **事件扰动**：某年符号由一次性事件（增发/大额并购/出售资产）造成时，报告注明「事件驱动型波动」作裁决参考，但**不从序列中剔除**——剔除权不交 Agent

## 第 5 层 管理层与治理

| ID | 指标 | 公式/来源 | 参照线 | 裁决规则 | 红灯分级 |
|---|---|---|---|---|---|
| U5-01 | 内部人行为 | Form 4 insider 交易、insider 持股（DEF 14A） | 无合理理由持续大额卖出 | 命中 → 红灯；10b5-1 预设计划内卖出须剔除干扰 | 风险级 |
| S5-03 | 审计师/CFO 稳定性 | 8-K Item 4.01（审计师变更强制披露）、CFO 变更记录 | 频繁更换 | 命中 → 红灯 | 风险级 |
| S5-04 | 会计政策风格 | 计提严格度、Non-GAAP 使用习惯、披露坦诚度 | 保守为佳 | 激进 → 记预警（「减分」统一映射为预警，见评级聚合规则） | — |
| S5-05 | 关联交易 | DEF 14A related-party transactions | 高 | 高 → 红灯 | 风险级 |
| S5-06 | 表外或有事项 | commitments & contingencies、重大诉讼 | 无重大异常 | 重大异常 → 红灯 | 风险级 |
| U5-02 | 做空报告跟踪 | 知名做空机构报告记录 | 被命中且未有效澄清 | 做空指控与财报异常互证 → 直接排除；**复活通道**：经独立调查（董事会特别委员会/监管机构结论）实质性澄清，且后续 2 个财年无互证异常 → 可解除排除并全程标注记录 | 否决级 |
| U5-03 | 中概专项 | VIE 结构、VIE 资产占比、PCAOB/HFCAA 状态 | 结构透明可审 | 重大不透明 → 降权或排除 | 风险级 |
| U5-04 | ICFR 内控意见 | 10-K 审计师内控意见（SOX 404）与 material weakness 披露（D21） | 无 adverse ICFR opinion 且无 material weakness | adverse ICFR opinion 或披露 material weakness → 红灯 | 风险级 |
| U5-05 | 财报重述史 | 8-K Item 4.02（往期报表不可信赖声明）与重述记录（D22） | 近 5 财年无 | 命中 Item 4.02 → 直接排除；非 Item 4.02 的技术性小重述 → 预警 + 下钻 | 否决级 |
| S5-07 | 高危行业标记 | SPAC 遗留股、临床前 biotech、无收入概念股 | 命中 | 全清单执行更严标准并在结论中标注 | — |

## 第 6 层 综合判定

| ID | 指标 | 公式 | 参照线 | 裁决规则 | 红灯分级 |
|---|---|---|---|---|---|
| S6-01 | ROE（归母） | 归母净利润 ÷ 平均归母净资产 | 连续多年 ≥15%〔经验值〕 | 必须先过 U6-01 失真检查 | — |
| U6-01 | ROE 失真检查 | 净资产 vs 历史：回购是否致净资产过低或为负 | 净资产异常缩水 | 命中 → ROE 失真，改用 ROIC 裁决并注明。ROIC 固定口径：NOPAT ÷ 投入资本；NOPAT = operating income ×（1 − 有效税率），有效税率 = B15 ÷ B14（税率为负或 >35% 的异常年用 21% 法定税率替代并注明），B11 缺失时 operating income 以（pretax income + interest expense）近似；投入资本 = 全部有息负债 + 归母净资产 − 超额类现金（超额 = 类现金超出 revenue × 10% 的部分，〔经验值〕） | — |
| S6-02 | 杜邦三因子 | ROE = 净利率 × 总资产周转率 × 权益乘数 | — | 优先级：高毛利 > 高周转 > 高杠杆；判断可持续性 | — |
| S6-03 | 周转率家族 | receivable / inventory / fixed / total asset turnover | 同行横向对比 | 营收暴增但周转率恶化 → 红灯（增长真实性存疑） | 否决级 |
| S6-04 | 成长性指标组 | revenue / 归母净利 / 总资产 / 净资产增长率 | 与现金流、资产质量匹配 | 无现金流的成长 → 预警 | — |
| S6-05 | 自洽性总检 | 营收 / 利润 / 现金流 / 应收 / 存货 / 周转率六者互证 | 全部自洽 | 任一独走且无解释 → 不下结论，标注待验证 | — |
| U6-02 | ROIC 持续性（正向） | 按 U6-01 固定口径计算，连续多年观察 | 连续多年 ≥12%〔经验值〕且趋势稳定 | 命中 → 计入加分项池（与 S2-14 / S2-15 / S4-07' 同池） | — |

---

## 评级聚合规则（Rating Aggregation，四档评级的唯一裁决依据）

> 本章节是四档质地评级的**唯一裁决规则**。Agent 只允许按本章节机械裁决，禁止自由裁量聚合。

### 1. 四档门槛

| 评级 | 机械裁决条件 |
|---|---|
| 直接排除 | ① G0 任一闸口不过（含 U0-01 重大异常）；或 ② 任一否决级红灯（经 D 组下钻后嫌疑仍未排除） |
| 高风险回避 | 风险级红灯 ≥1；或预警 ≥3（S5-07 高危行业 ≥2） |
| 优质候选 | 无任何红灯 + 预警 ≤1（高危行业为 0）+ 三硬条件同时满足（S6-01 ROE 连续多年 ≥15%〔经验值〕，U6-01 命中时以 ROIC 替代；S4-06 主导型为奶牛/老母鸡；S4-02 利润含金量长期累计 ≥1）+ 加分项 ≥1（S2-14 / S2-15 / S4-07' / U6-02） |
| 可关注 | 不满足以上三档的其余情形 |

### 2. 裁决顺序总则

按固定顺序机械裁决：① 按四档门槛初步定档 → ② 应用降档规则（非否决级指标「无法计算」≥3 个且初步定档为正向评级〔优质候选/可关注〕→ 降一档；负向评级不降档，改标「暂定」）→ ③ 应用评级上限裁剪（未盈利企业 / 无同行对比降级模式 / 短历史（上市后 <5 财年），上限「可关注」；多个上限同时触发取最严）→ ④ 附加评级状态标注（暂定 / 数据不足 / 短历史）。**双轨制**：否决级红灯（含 G0 闸口终止项）不受数据窗口年限限制，任何窗口命中即「直接排除」；正向评级窗口只认上市后财报年份（招股说明书年份仅用于趋势观察与排雷否决）。**术语机械映射**：字典各处的「降权」一律映射为「评级上限『可关注』+ 状态标注」；「减分」一律映射为记预警；禁止出现无映射的自由裁量词。

### 3. 预警计数口径

「预警」全集 = 全部指标级预警 + 全部闸口级预警（含 G0-01 CAM 预警、S4-06 边际恶化及单年排除类预警），逐条列入评级依据摘要。

### 4. 保护规则

- 下钻后仍「待验证」的嫌疑项 ≥1 → 评级标注「暂定」，数据补齐后复核
- ▲核心字段缺失导致任一否决级指标无法计算 → 输出「数据不足，暂不定级」，不强行给档（行业豁免表已豁免的指标除外）
- 「暂定」「数据不足」等评级状态统一为状态标注，可多值并列（如「高风险回避（暂定）」）

### 5. 评级依据摘要（报告必含）

固定字段：红灯清单（指标 ID + 分级）｜预警清单（指标 ID + 原因）｜三硬条件命中情况｜加分项命中情况｜降档与上限适用记录｜状态标注。

---

## 数据需求清单（US Data Requirement Manifest）

> 字段编号发布后**冻结**：不得复用、不得重排，新增字段追加对应组尾部号段。自定义源模板与校验以编号为唯一对照键。

**▲核心字段（16 项，准入校验一票否决）**：B01 revenue、B02 COGS、B17 归母净利润、B16 net income、B18 NCI 损益、C02 CFO、A22 total assets、A33 total liabilities、A34 归母股东权益、A01 cash & equivalents、A23 short-term debt、A29 long-term debt、A04 accounts receivable、A08 inventory、A19 goodwill、C03 capex

### A. 合并资产负债表（≥5 财年期末值，附常用 XBRL tag）

| 编号 | 字段 | XBRL tag 提示 |
|---|---|---|
| A01 | cash & cash equivalents | CashAndCashEquivalentsAtCarryingValue |
| A02 | short-term investments / marketable securities | ShortTermInvestments |
| A04 | accounts receivable（net，如有 gross 与 allowance 更佳） | AccountsReceivableNetCurrent |
| A05 | contract assets / unbilled receivables | ContractWithCustomerAssetNet |
| A08 | inventory | InventoryNet |
| A10 | current assets 合计 | AssetsCurrent |
| A14 | PP&E（含 CIP 明细更佳） | PropertyPlantAndEquipmentNet |
| A16 | operating / finance lease ROU assets | OperatingLeaseRightOfUseAsset |
| A17 | acquired intangibles | FiniteLivedIntangibleAssetsNet |
| A18 | capitalized software / deferred costs | — |
| A19 | goodwill | Goodwill |
| A21 | deferred tax assets | DeferredTaxAssetsNet |
| A22 | total assets | Assets |
| A23 | short-term debt（含 current portion of LTD） | ShortTermBorrowings / DebtCurrent |
| A25 | accounts payable | AccountsPayableCurrent |
| A26 | deferred revenue / contract liabilities | ContractWithCustomerLiability |
| A28 | current liabilities 合计 | LiabilitiesCurrent |
| A29 | long-term debt（含 senior notes） | LongTermDebtNoncurrent |
| A31 | lease liabilities（finance + operating 分列） | FinanceLeaseLiability / OperatingLeaseLiability |
| A32 | deferred tax liabilities | DeferredIncomeTaxLiabilitiesNet |
| A33 | total liabilities | Liabilities |
| A34 | 归母股东权益 | StockholdersEquity |
| A35 | NCI 权益 | MinorityInterest |
| A36 | 非流动有价证券（non-current marketable securities） | MarketableSecuritiesNoncurrent |

### B. 合并利润表（≥5 财年）

| 编号 | 字段 | XBRL tag 提示 |
|---|---|---|
| B01 | revenue | Revenues / RevenueFromContractWithCustomerExcludingAssessedTax |
| B02 | COGS | CostOfRevenue / CostOfGoodsAndServicesSold |
| B03 | SG&A（或销售/管理分列） | SellingGeneralAndAdministrativeExpense 等 |
| B05 | R&D | ResearchAndDevelopmentExpense |
| B06 | interest expense / interest income 子字段 | InterestExpense / InterestIncomeNonoperating |
| B08 | investment & disposal gains（非经营损益） | GainLossOnInvestments 等 |
| B11 | operating income（如披露） | OperatingIncomeLoss |
| B14 | pretax income | IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest |
| B15 | income tax | IncomeTaxExpenseBenefit |
| B16 | net income | NetIncomeLoss |
| B17 | 归母净利润 | NetIncomeLossAttributableToParent / ...AvailableToCommonStockholdersBasic |
| B18 | NCI 损益 | NetIncomeLossAttributableToNoncontrollingInterest |
| B19 | OCI | OtherComprehensiveIncomeLossNetOfTax |
| B20 | comprehensive income | ComprehensiveIncomeNetOfTax |
| B21 | SBC | ShareBasedCompensation / AllocatedShareBasedCompensationExpense |
| B22 | 加权稀释股数 | WeightedAverageNumberOfDilutedSharesOutstanding |
| B23 | Non-GAAP 净利润与调节表 | earnings release（6-K/8-K EX-99.1），XBRL 无结构化数据 |

### C. 合并现金流量表（≥5 财年，间接法）

| 编号 | 字段 | XBRL tag 提示 |
|---|---|---|
| C02 | CFO | NetCashProvidedByUsedInOperatingActivities |
| C03 | capex | PaymentsToAcquirePropertyPlantAndEquipment（中概近年可能断档，须备东财等第二源） |
| C04 | CFI | NetCashProvidedByUsedInInvestingActivities |
| C05 | dividends paid | PaymentsOfDividends |
| C06 | CFF | NetCashProvidedByUsedInFinancingActivities |
| C08 | buybacks | PaymentsForRepurchaseOfCommonStock |
| C09 | M&A 支出 | PaymentsToAcquireBusinessesNetOfCashAcquired |
| C10 | Δ应收 / Δ递延收入（S4-01' 推导用） | 由 A04/A05/A26 两期差分计算 |
| C11 | 股票发行所得（S4-07' 净回购口径用） | ProceedsFromIssuanceOfCommonStock |

### D. 附注与治理字段

| 编号 | 字段 |
|---|---|
| D01 | 各年度审计意见与 CAM（10-K/20-F），含 going-concern 段落 |
| D04 | 商誉分 reporting unit 明细与减值历史 |
| D05 | 关联交易（DEF 14A） |
| D06 | commitments & contingencies、重大诉讼 |
| D07 | 研发投入与资本化软件金额 |
| D09 | IPO / de-SPAC 日期 |
| D15 | 债务到期结构表（maturity schedule） |
| D16 | 内部人持股与 Form 4 交易 |
| D17 | 做空报告记录（公开信息） |
| D18 | VIE 结构与资产占比（中概 20-F） |
| D19 | PCAOB/HFCAA 状态（中概） |
| D20 | 审计师/CFO 变更记录（8-K Item 4.01 等） |
| D21 | ICFR 意见与 material weakness 披露（10-K，U5-04 用） |
| D22 | 财报重述史（8-K Item 4.02，U5-05 用） |

### E. 对照组数据

槽位制：E1 / E2 / E3（对照公司 1–3），每槽位提供该公司同期 A 组 + B 组全部字段；编址格式 `E<槽位>-<字段编号>`。对照组可跨市场：美股/ADR 对照直接用 `scripts/fetch_manifest.py <对照ticker>` 各跑一份回执；A 股对照为可选增强，走用户自定义源（本项目不捆绑 A 股数据通道）。

---

## 附录：行业豁免口径表（仅调整既有指标裁决口径，不新增指标）

> 触发豁免的行业，按下表调整对应指标的裁决口径。凡触发豁免，报告「数据说明」节必须逐行列出：`适用行业豁免：<指标ID>，参照线调整为 <新口径>，依据 <行业>豁免`。

| 行业 | 失效指标 | 调整后口径 |
|---|---|---|
| 互联网/平台服务（轻存货） | S2-05 / S2-06 | 存货 ÷ 总资产 <2% 时存货指标豁免（存货非经营核心，悖论检查无意义），报告标注豁免；▲A08 缺失不再触发「数据不足」 |
| 公用事业/基建 | S1-02 | 60%〔经验值〕放宽为同行对比，红灯裁决权移交 S1-05 + S4-03 |
| 零售业 | S1-04 | 流动比率参照线下移至约 1（负营运资本为商业模式而非风险） |
| SaaS/订阅制 | S2-14 | 高递延收入为商业模式属性，正向加分但不做行业内横向比较 |
| 能源/大宗商品（强周期） | S3-01 | 周期底部毛利率触「红海」线为周期属性而非竞争劣势；裁决改用跨周期平均毛利率 + 同行对比，禁止用周期底部单年/短期趋势定性 |
| 未盈利企业（IPO 初期 biotech/科技股） | 第 3 层 / S6-01 | 盈利质量层与 ROE 失效；排雷层（0/1/2/4 层）正常执行；评级上限「可关注」，结论标注「未盈利，盈利层不适用」 |
