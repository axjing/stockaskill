# 研究发现与路线决策

## 一、任务背景

本轮工作分为两部分：

1. 评估多市场增量同步是否应继续扩张。
2. 基于 `3rdparty` 中投资类 skills 的对比分析，为 `stockaskill` 设计后续功能演进路线。

目标不是把仓库做成“更大”，而是确认“什么更适合这个仓库”。

## 二、仓库现状判断

### 1. 当前仓库的产品形态
- `stockaskill` 已经是一个本地优先、任务作用域的投资分析引擎。
- 它的主价值来自：
  - 单票分析
  - 诊断
  - 市场扫描
  - alpha 排名
  - 组合构建
  - 回测
  - bounded sync 与状态诊断
- 它不是：
  - 全市场数据平台
  - 长期后台调度系统
  - 完整研究工作台
  - 重型估值建模平台

### 2. 当前已建立的技术基础
- market-aware cache v2
- symbol / watchlist / portfolio / scan-universe / ETF 作用域同步
- readiness 与 `status data` 诊断
- HK / US metadata completeness 可见性
- ETF-first FUND 语义

这些基础说明：仓库已经具备“决策引擎”雏形，但还缺少更高层的工作流与研究框架。

## 三、对 3rdparty 项目的对比结论

### 1. 与 `serenity-skill` 的对比

#### 它的优势
- 主题研究方法非常强
- 擅长从主题叙事拆解到产业链层级
- 强调 scarce layer / 卡点判断
- 强调证据强弱与反证条件
- 输出可解释性很强

#### 它的不足
- 本地可执行能力弱
- 更偏方法论和对话协议
- 不适合作为日常批量扫描和组合执行主引擎

#### 对 `stockaskill` 的启发
- 借鉴“主题研究模式”
- 借鉴“证据链与反证条件”
- 借鉴“先排层级，再排公司”的主题扫描逻辑
- 不需要复制整个 Serenity 工作流

### 2. 与 `claude-trading-skills` 的对比

#### 它的优势
- 工作流编排成熟
- 有 market regime / exposure posture 逻辑
- 有 thesis memory / postmortem 闭环
- 有 navigator 负责把自然语言目标路由到合适工作流
- 对日常投研运营流程支持完整

#### 它的不足
- 更像 skill 生态而不是单一分析引擎
- 技能数量多，结构重
- 偏美股流程化操作，不能直接照搬

#### 对 `stockaskill` 的启发
- 借鉴 workflow router
- 借鉴 market regime / risk posture 层
- 借鉴 thesis lifecycle / review / postmortem
- 不建议把 `stockaskill` 拆成几十个 skill

### 3. 与 `UZI-Skill/deep-analysis` 的对比

#### 它的优势
- 个股深度分析约束非常强
- 输出报告完整，质化分析比重高
- 强制冲突呈现
- 对“空话”容忍度低

#### 它的不足
- 非常重
- 多 agent、硬门控、persona 系统复杂
- 不适合默认分析路径

#### 对 `stockaskill` 的启发
- 借鉴 deep-diagnose 的硬门控思想
- 借鉴 bull / bear / invalidation 的强制输出结构
- 不建议复制 65 评委、重型 persona、完整估值建模体系

## 四、总体产品方向结论

### 应坚持的方向
- 本地优先
- 任务作用域
- 多市场分析引擎
- ETF-first FUND 范围
- 可执行、可验证、可缓存

### 不应演化成的方向
- 全市场后台同步平台
- 广泛 mutual-fund / NAV 平台
- 复杂 persona 驱动的重型研究系统
- 分裂成庞大 skill marketplace

## 五、能力缺口归纳

当前最明显的缺口不是“没有更多命令”，而是以下几层：

### 1. 工作流入口缺失
用户必须自己知道该跑 `scan`、`alpha`、`diagnose`、`portfolio` 还是 `backtest`。

### 2. 市场状态层缺失
现在可以直接做扫描和组合，但缺少先判断市场风险姿态的系统层。

### 3. 主题研究层薄弱
对主题、产业链、卡点、证据链、反证条件支持不足。

### 4. 决策记忆层缺失
没有 thesis 生命周期、review、postmortem。

### 5. 深度诊断输出约束偏轻
当前 `diagnose` 有用，但还不够“可审计”。

## 六、演进主题

### 主题 A：工作流路由与引导入口
目标：
- 把“我该运行什么”变成系统能力。

适配度：
- 高

主要借鉴来源：
- `claude-trading-skills` 的 navigator 与 workflow manifest

### 主题 B：市场状态与风险姿态层
目标：
- 在扫描和建仓前先评估市场允许度与风险预算。

适配度：
- 高

主要借鉴来源：
- `market-regime-daily`
- `market-top-detector`
- `exposure-coach`

### 主题 C：主题研究与证据链模式
目标：
- 支持从主题到价值链到候选公司的研究路径。

适配度：
- 中高

主要借鉴来源：
- `serenity-skill`

#### 当前落地结论
- 已新增 `theme-scan` 入口。
- 当前采用“本地主题模板 + 本地股票池映射 + 本地因子缓存”的实现方式。
- 已支持的主题模板：
  - `AI基础设施`
  - `机器人`
  - `电池 / 储能`
- 未命中的主题会进入 `custom` 模式，仍然输出：
  - 产业链层级
  - 产业链卡点
  - 支持证据
  - 反证/降级信号
  - 下一步检查
- 当前设计判断：
  - 这已经足够把“热门叙事”拉回到“先排层级，再排公司”的研究框架。
  - 现阶段不需要把它扩成联网主题数据库或长期主题知识库。
  - 下一步更值得补的是跨 `scan / diagnose / theme / thesis` 的统一 confidence / provenance 展示。

### 主题 D：thesis memory 与 postmortem
目标：
- 让分析结果能够进入长期记录、回顾和复盘闭环。

适配度：
- 高

主要借鉴来源：
- `trader-memory-core`

#### 当前落地结论
- 已形成最小闭环：
  - `capture`
  - `list`
  - `review`
  - `postmortem`
- 已采用本地文件存储：
  - 默认目录 `memory/theses`
  - 每条 thesis 生成 `.json` 与 `.md`
- 已复用现有 `diagnose` 结构字段：
  - `signal`
  - `score`
  - `confidence`
  - `bull_case`
  - `bear_case`
  - `invalidation_conditions`
- 当前设计判断：
  - 对当前仓库来说，这已经足够满足“观点留痕、回看、复盘”三类核心需求。
  - 没必要在这一阶段引入数据库、后台任务或复杂多实体研究台。
  - 后续更值得补的是主题研究入口与证据链结构，而不是先扩 thesis 基础设施。

### 主题 E：深度诊断输出约束
目标：
- 提升单票分析的冲突表达、失效条件表达与报告完整性。

适配度：
- 中高

主要借鉴来源：
- `UZI deep-analysis`

### 主题 F：全链路 confidence / provenance 展示
目标：
- 把数据完整度、来源、freshness 直接前台化，而不是只藏在内部状态里。

适配度：
- 高

#### 当前落地结论
- 已统一 `confidence` / `provenance` schema。
- 当前已接入：
  - `data_readiness`
  - `market-regime`
  - `diagnose`
  - `theme-scan`
  - `thesis`
  - `scanner` 候选结果
- 已在 markdown 报告层统一渲染 `Confidence` / `Provenance` 区块。
- 当前设计判断：
  - 这层的价值在于“可解释地暴露数据质量和来源”，不是追求更复杂的伪精度评分。
  - 当前统一 schema 已足以支撑后续 `deep-diagnose`、workflow manifest 和 scorecards 的扩展。

## 七、P0 / P1 / P2 演进路线图

---

## P0：优先补齐决策质量和使用体验

P0 原则：
- 不改变产品形态
- 不引入过重新依赖
- 直接提升 `scan` / `alpha` / `diagnose` / `portfolio` 的可用性和可信度

### P0.1 工作流路由与推荐入口

#### 目标
增加一个轻量的推荐层，把用户意图映射到合适的 `stockaskill` 使用路径。

#### 预期能力
- 输入“我要找 A 股里适合买的股票”
- 输出“先跑 market-regime，再跑 scan / alpha，再对前几名 diagnose”
- 对新用户形成引导

#### 模块拆分
- intent parser
- workflow recommendation
- workflow description layer

#### 文件级改造点
- `stockaskill/scripts/run.py`
  - 增加 `recommend` 或 `route` 命令
  - 为常见意图输出引导式建议
- `stockaskill/scripts/models.py`
  - 增加 workflow recommendation 数据模型
- `stockaskill/scripts/utils.py`
  - 增加意图分类辅助函数
- 新增 `stockaskill/scripts/workflows.py`
  - 定义内置 workflow 描述
- 新增 `stockaskill/references/workflows.md`
  - 记录用户侧工作流说明

#### 验证重点
- 常见请求映射稳定
- 不破坏现有命令路径

#### 已落地结果
- 已新增 `route` / `recommend` CLI 入口。
- 已采用确定性关键词分类，不依赖额外模型或开放式推理。
- 已覆盖的核心意图：
  - `opportunity_scan`
  - `market_check`
  - `analyze_symbol`
  - `diagnose_symbol`
  - `build_portfolio`
  - `sync_data`
  - `backtest_strategy`
- 已输出结构：
  - `intent`
  - `market`
  - `summary`
  - `rationale`
  - `steps`
  - `notes`
- 当前实现结论：
  - 该层足以解决“我该先跑什么”的入口问题。
  - 保持了现有 `scan / alpha / diagnose / portfolio / backtest / sync / status` 语义稳定。
  - 适合作为后续 thesis memory 与 theme research 的上层入口，而不是终态工作台。

### P0.2 市场状态 / 风险姿态层

#### 目标
在扫描、组合、再平衡前引入市场风险姿态判断。

#### 预期能力
- 输出当前市场是否适合积极选股
- 给出 risk budget / posture
- 给 `portfolio` 和 `scan` 一个前置约束

#### 模块拆分
- benchmark / breadth input collection
- regime scoring
- posture decision
- risk-budget integration

#### 文件级改造点
- 新增 `stockaskill/scripts/market_regime.py`
  - 计算 regime / posture / risk budget
- `stockaskill/scripts/data_engine.py`
  - 获取或缓存相关基准输入
- `stockaskill/scripts/cache.py`
  - 视需要增加 regime snapshot 存储
- `stockaskill/scripts/run.py`
  - 增加 `market-regime` 命令
  - 在 `scan`、`alpha`、`portfolio` 中引用姿态摘要
- `stockaskill/scripts/portfolio/builder.py`
  - 消费 posture / risk budget
- `stockaskill/scripts/portfolio/rebalance.py`
  - 可选纳入 posture 约束
- 新增 `tests/test_market_regime.py`
- 扩展 `tests/test_run.py`
- 扩展 `tests/test_portfolio.py`

#### 验证重点
- regime 分类可重复
- 输入缺失时能优雅降级

### P0.3 `diagnose` 输出硬化

#### 目标
让 `diagnose` 从“有结论”升级为“可审计”。

#### 预期能力
- 强制输出 bull case
- 强制输出 bear case
- 强制输出 invalidation 条件
- 强制输出 data confidence

#### 模块拆分
- diagnosis contract hardening
- confidence summary
- stronger report rendering

#### 文件级改造点
- `stockaskill/scripts/advisor/diagnosis.py`
  - 增加 bull / bear / invalidation / confidence 结构
- `stockaskill/scripts/report_generator.py`
  - 渲染新结构
- `stockaskill/scripts/data_readiness.py`
  - 输出 confidence 输入
- `stockaskill/references/output-style-and-language.md`
  - 增加禁止空泛总结的规则
- 新增 `tests/test_diagnosis.py`

#### 验证重点
- JSON 契约稳定
- 所有诊断都包含关键区块

---

## P1：增加差异化研究和记忆闭环

P1 原则：
- 在 P0 形成更稳主路径后，引入更高价值但稍重的增强层

### P1.1 主题研究模式

#### 目标
增加一个可选主题研究路径，从“主题 -> 价值链 -> 稀缺层 -> 候选公司”推进。

#### 预期能力
- 支持 `theme-scan`
- 输出 value chain layer
- 输出 scarce layer proximity
- 输出 evidence / disconfirming signals

#### 模块拆分
- theme scope parser
- value-chain mapping
- evidence/disconfirmation schema

#### 文件级改造点
- 新增 `stockaskill/scripts/theme_research.py`
  - 主题研究主逻辑
- `stockaskill/scripts/advisor/scanner.py`
  - 支持 theme 或 theme filter
- `stockaskill/scripts/models.py`
  - 新增 theme research 模型
- `stockaskill/scripts/run.py`
  - 增加 `theme-scan` 或 `scan --theme`
- 新增 `stockaskill/references/theme-research.md`
- `stockaskill/references/research-sources.md`
  - 补充主题研究来源说明
- 新增 `tests/test_theme_research.py`

#### 验证重点
- 输出结构稳定
- 不强依赖“必须联网”的研究路径

### P1.2 Thesis memory / review / postmortem

#### 目标
把分析结果纳入生命周期管理，而不是一次性输出后丢失。

#### 预期能力
- 记录 thesis
- 管理状态变化
- 定期 review
- 关闭后 postmortem

#### 模块拆分
- thesis store
- review scheduling
- postmortem summarization

#### 文件级改造点
- `stockaskill/scripts/cache.py`
  - 增加 thesis / review / postmortem 表
- 新增 `stockaskill/scripts/thesis_store.py`
  - thesis 生命周期管理
- 新增 `stockaskill/scripts/postmortem.py`
  - 复盘摘要生成
- `stockaskill/scripts/run.py`
  - 增加 `thesis create/list/review/close`
- `stockaskill/scripts/portfolio/builder.py`
  - 可选生成 thesis 链接
- `stockaskill/scripts/report_generator.py`
  - thesis / postmortem markdown 输出
- 新增 `tests/test_thesis_store.py`
- 新增 `tests/test_postmortem.py`

#### 验证重点
- 状态流转清晰
- 对一次性分析用户保持可选，不强制绑定

### P1.3 全链路 confidence / provenance 展示

#### 目标
把 data freshness、metadata completeness、readiness 直接前台化。

#### 预期能力
- 所有主报告都有 confidence/provenance 区块
- 不再把数据质量仅作为内部状态

#### 模块拆分
- confidence schema
- report-level provenance rendering

#### 文件级改造点
- `stockaskill/scripts/data_readiness.py`
  - 统一 confidence schema
- `stockaskill/scripts/advisor/scanner.py`
  - 在结果中输出 confidence 摘要
- `stockaskill/scripts/advisor/diagnosis.py`
  - 嵌入 confidence
- `stockaskill/scripts/report_generator.py`
  - 统一渲染
- 扩展 `tests/test_data_readiness.py`
- 扩展 `tests/test_advisor.py`

#### 验证重点
- confidence 不应变成误导性的伪精度

---

## P2：面向更深研究与运营流程的增强

P2 原则：
- 默认路径保持轻
- 高复杂度能力显式 opt-in

### P2.1 `deep-diagnose` 模式

#### 目标
增加更重型、更完整的单票深度分析模式。

#### 预期能力
- 比 `diagnose` 更强调 qualitative conflict
- 更长报告
- 更严格输出门控

#### 模块拆分
- staged deep diagnosis
- long-form report rendering

#### 文件级改造点
- `stockaskill/scripts/advisor/diagnosis.py`
  - 保留轻量 diagnose
- 新增 `stockaskill/scripts/deep_diagnosis.py`
  - 深度诊断主逻辑
- `stockaskill/scripts/run.py`
  - 增加 `deep-diagnose`
- 新增 `stockaskill/references/deep-diagnosis.md`
- `stockaskill/scripts/report_generator.py`
  - 增加长报告模板
- 新增 `tests/test_deep_diagnosis.py`

#### 当前落地结论
- 已新增 `deep-diagnose` 显式重模式。
- 当前实现方式：
  - 复用现有 `StockDiagnosis.full_report()` 作为底层数据骨架
  - 在 `deep_diagnosis.py` 中追加确定性合成层
  - 增加以下长报告区块：
    - `executive_summary`
    - `variant_perception`
    - `supporting_evidence`
    - `conflict_matrix`
    - `bear_case`
    - `invalidation_conditions`
    - `next_checks`
- 当前设计判断：
  - 这样可以显著增强单票研究的冲突表达和复核深度，同时不破坏现有轻量 `diagnose` 路径。
  - 当前实现仍然保持本地优先、确定性、无新增 agent 依赖，符合仓库边界。
  - 后续若继续增强，更值得往 workflow manifest / routine automation 走，而不是继续堆更重的 persona 系统。

### P2.2 manifest 式 workflow 运行

#### 目标
将日常例行任务固化为可执行 routine。

#### 预期能力
- `workflow run market-regime-daily`
- `workflow run portfolio-review-weekly`

#### 模块拆分
- workflow manifest
- workflow runner
- artifact handoff

#### 文件级改造点
- 新增 `stockaskill/workflows/market-regime-daily.yaml`
- 新增 `stockaskill/workflows/portfolio-review-weekly.yaml`
- 新增 `stockaskill/workflows/theme-research-weekly.yaml`
- 新增 `stockaskill/scripts/workflow_runner.py`
- `stockaskill/scripts/run.py`
  - 增加 `workflow run <name>`
- 新增 `tests/test_workflow_runner.py`

#### 当前落地结论
- 已新增 `workflow list` / `workflow run` 入口。
- 当前实现方式：
  - 在 `models.py` 中增加 workflow manifest / run-plan 数据模型
  - 在 `workflow_runner.py` 中加载本地 manifest，并做参数替换
  - 在 `stockaskill/workflows/` 下内置三类 routine：
    - `market-regime-daily`
    - `portfolio-review-weekly`
    - `theme-research-weekly`
- 当前 runner 边界：
  - 只解析、展开、输出 routine
  - 不直接执行 shell
  - manifest 采用 stdlib 可解析的 JSON-compatible YAML，避免新增 `PyYAML` 依赖
- 当前设计判断：
  - 这已经足以把已有的 market-regime、theme、thesis、portfolio 路径固化成可复用例行流程。
  - 现阶段不需要把它扩成后台调度器或自动执行系统。
  - 下一步更值得补的是 scorecard / attribution，让 routine 结果能进入质量评分与复盘归因层。

### P2.3 高级 scorecard / attribution

#### 目标
增加研究评分卡、thesis 质量评分和复盘归因。

#### 文件级改造点
- 新增 `stockaskill/scripts/scorecards.py`
- `stockaskill/scripts/postmortem.py`
- `stockaskill/scripts/theme_research.py`
- 新增 `stockaskill/references/scorecards.md`
- 新增 `tests/test_scorecards.py`

## 八、推荐实施顺序

### 若目标是“先提升决策质量”
推荐顺序：
1. `P0.2` 市场状态 / 风险姿态层
2. `P0.3` `diagnose` 输出硬化
3. `P0.1` 工作流路由

### 若目标是“先改善新用户体验”
推荐顺序：
1. `P0.1` 工作流路由
2. `P0.2` 市场状态 / 风险姿态层
3. `P0.3` `diagnose` 输出硬化

### 若只开一个首批 PR
最推荐：
- `P0.2 Market-Regime and Risk Posture`

理由：
- 直接提升 `scan`、`alpha`、`portfolio`
- 为未来 workflow routing 提供前置判断
- 与当前本地优先产品形态最一致

## 九、依赖关系说明

- `P0.2` 最适合作为第一条实现主线。
- `P0.1` 的推荐逻辑最好建立在 `P0.2` 存在后，否则只能做静态路由。
- `P1.1` 主题研究最好复用 `P0` 阶段形成的 confidence / readiness 结构。
- `P1.2` thesis memory 应复用现有 cache / report 体系，而不是另建一套持久层。
- `P2` 所有功能都应保持显式可选，不能拖慢默认主路径。

## 十、最终建议

最适合 `stockaskill` 的演化方向不是“变大”，而是“分层变强”：

1. 保持本地执行引擎定位
2. 补上市场状态门
3. 补上工作流引导
4. 补上主题研究模式
5. 补上 thesis 记忆与复盘
6. 将重型深度分析保留为显式高级模式

## 十一、P0.2 首批实现记录

本轮已先落地 `P0.2` 的第一版，而不是继续停留在规划层。

### 已实现内容
- 新增 `stockaskill/scripts/market_regime.py`
  - 基于 benchmark 趋势、20/60/120 均线关系、20 日收益、60 日回撤、20 日波动率，以及样本 breadth 生成 posture / score / risk_budget
- 新增 `market-regime` CLI 命令
- 在 `scan`、`refresh-scan`、`alpha` 中打印市场姿态摘要，并把 regime 数据写入报告 payload
- 在 `portfolio` 与 `portfolio-enhanced` 中消费 `risk_budget`
  - 通过 `PortfolioBuilder.build(..., capital_fraction=...)` 控制实际部署仓位
- 在 `report_generator.py` 中增加 market regime markdown 输出能力

### 当前实现边界
- 当前实现是“轻量版市场状态层”，目标是尽快形成可用闭环
- A 股路径最完整
- HK / US 采用 benchmark symbol + `get_kline()` 的轻量兼容路径
- breadth 采用 bounded sample 估计，而不是更重的全市场 breadth 统计

### 当前实现的价值
- `portfolio` 不再默认 100% 仓位部署
- `scan` / `alpha` 输出前有了市场姿态上下文
- 后续 `P0.1` 做 workflow 路由时，已经有 posture 可作为前置判断输入

### 当前实现的限制
- 还没有独立 regime snapshot 持久化模型
- 还没有把 posture 深度接入 `rebalance`、`backtest`、`diagnose`
- breadth 仍是样本估计，不是全市场统计口径
- HK / US benchmark 配置仍偏启发式，后续需要细化

## 十二、测试环境修复结果

### 现象
- 当前 `.venv` 起初没有可用的 `pip` 模块入口。
- `python -m pytest` 在安装前不可用。

### 处理
- 使用 `.venv/bin/python -m ensurepip --upgrade` 为当前环境补齐 `pip` 基础安装。
- 发现 `.venv/bin/python -m pip` 入口仍异常，但 `.venv/bin/pip3` 可正常工作。
- 通过 `.venv/bin/pip3 install pytest` 安装 `pytest`。
- 直接使用 `.venv/bin/pytest -q` 跑全量测试。

### 结果
- 全量测试通过：
  - `291 passed, 1 warning`
  - 总耗时约 `5m30s`

### 备注
- 当前 `.venv` 对 `python -m pytest` 的入口行为一度不稳定，但 `import pytest` 与 `.venv/bin/pytest` 执行均正常。
- 后续若要进一步清理环境一致性，可单独检查 `.venv` 创建方式与入口脚本生成过程，但这不阻塞当前开发。

## 十三、P0.3 实现结果

### 本轮目标
- 强化现有 `diagnose`，让输出从“有分数”变成“可审计的结论结构”。

### 已落地内容
- `StockDiagnosis.full_report()` 新增 `confidence` 区块。
- `final_decision` 新增：
  - `confidence_level`
  - `confidence_score`
  - `bull_case`
  - `bear_case`
  - `invalidation_conditions`
- `report_generator.format_diagnosis_summary()` 新增：
  - `Confidence`
  - `Bull Case`
  - `Bear Case`
  - `Invalidation`
- `references/output-style-and-language.md` 增加 diagnosis 输出顺序要求。

### 当前实现思路
- 不引入新命令
- 不改变既有 `diagnose` 的入口
- 只增强结果结构和摘要展示

### 当前实现收益
- `diagnose` 的结论更容易解释给用户
- 后续做 `P1` 的 thesis memory 时，可以直接复用 bull / bear / invalidation 字段
- 后续做 `P2 deep-diagnose` 时，已有轻量 contract 可作为基础

### 验证结果
- 定向测试通过：
  - `43 passed`
- 全量测试通过：
  - `294 passed, 1 warning`
