# 任务规划：stockaskill 数据引擎与功能演进路线

## 目标
评估并规划 `stockaskill` 的两条主线工作：

1. 确认 HK / US / ETF / FUND 相关增量同步能力是否符合当前仓库的产品定位。
2. 基于与 `3rdparty` 投资类 skills 的对比分析，给出 `stockaskill` 的功能演进路线图，并拆分为可落地的 `P0 / P1 / P2` 模块与文件级改造点。

当前结论是：仓库应继续保持“本地优先、任务作用域、决策支持型投资分析引擎”定位，而不是向全市场数据平台或超重型研究平台演化。

## 当前阶段
阶段 36

## 阶段列表

### 阶段 1：需求确认与仓库发现
- [x] 理解用户意图
- [x] 识别产品范围约束
- [x] 记录关键背景信息
- 状态：已完成

### 阶段 2：评估框架建立
- [x] 定义产品适配性判断标准
- [x] 区分产品问题与实现问题
- [x] 固化评估边界
- 状态：已完成

### 阶段 3：现状评估
- [x] 评估当前数据同步与缓存模式
- [x] 评估 HK / US / ETF / FUND 支持深度
- [x] 评估与仓库定位的一致性
- 状态：已完成

### 阶段 4：产品建议输出
- [x] 给出是否应做全量增量同步的建议
- [x] 区分应立即支持与应延期支持的范围
- [x] 明确风险与假设
- 状态：已完成

### 阶段 5：首次交付
- [x] 复核规划文件
- [x] 向用户输出结论
- 状态：已完成

### 阶段 6：优化方向框定
- [x] 确认本地优先、任务作用域定位
- [x] 明确优化原则
- [x] 区分近期改进与远期增强
- 状态：已完成

### 阶段 7：数据引擎优化路线图
- [x] 定义数据层改造方向
- [x] 设计分阶段实现方案
- [x] 映射到具体模块
- 状态：已完成

### 阶段 8：优化路线图交付
- [x] 向用户交付优化提案
- [x] 明确优先级与风险
- 状态：已完成

### 阶段 9：可执行开发计划
- [x] 将路线图转为代码级改造计划
- [x] 定义首批 schema / API 变更
- [x] 规划实现与验证顺序
- 状态：已完成

### 阶段 10：开发计划交付
- [x] 输出可执行开发计划
- [x] 标明 MVP 与后续批次边界
- 状态：已完成

### 阶段 11：MVP 第 1 批实现
- [x] 增加 market-aware cache v2 表与 sync_state
- [x] 增加 symbol 级同步能力
- [x] 增加最小 `sync` CLI 入口
- 状态：已完成

### 阶段 12：MVP 第 2 批实现
- [x] 增加 watchlist / portfolio / scan-universe 作用域同步
- [x] 增加最小 `status data` 诊断
- 状态：已完成

### 阶段 13：MVP 第 3 批实现
- [x] 让 scanner 更直接消费 readiness / sync 摘要
- [x] 增强 `status data` 聚合 freshness / error 视图
- 状态：已完成

### 阶段 14：MVP 第 4 批实现
- [x] 增加 ETF 专属同步与 readiness
- [x] 将 FUND 明确收紧为 ETF-first 语义
- 状态：已完成

### 阶段 15：MVP 第 5 批实现
- [x] 增加 ETF 语义别名与路径清晰度
- [x] 改善 HK / US metadata 抽取与 inactive 过滤
- 状态：已完成

### 阶段 16：MVP 第 6 批实现
- [x] 增加 metadata source / status / completeness 可见性
- [x] 在 readiness 摘要中展示 metadata 质量
- 状态：已完成

### 阶段 17：MVP 第 7 批实现
- [x] 在 scan / ranking 中消费 metadata 质量信号
- [x] 在 `status data` 中增加市场级 metadata 健康摘要
- 状态：已完成

### 阶段 18：文档与技能定义对齐
- [x] 更新 `SKILL.md`
- [x] 更新 `README.md`
- [x] 更新 `AGENTS.md`
- 状态：已完成

### 阶段 19：技能定义收口
- [x] 缩窄触发词到 ETF-first 范围
- [x] 精简 frontmatter
- [x] 收紧 scope boundary 表达
- 状态：已完成

### 阶段 20：3rdparty 能力对比分析
- [x] 对比 `stockaskill` 与 `serenity-skill`
- [x] 对比 `stockaskill` 与 `claude-trading-skills`
- [x] 对比 `stockaskill` 与 `UZI deep-analysis`
- 状态：已完成

### 阶段 21：功能演进路线规划
- [x] 将对比结论转为演进主题
- [x] 按 `P0 / P1 / P2` 归类优先级
- [x] 明确每个主题的产品目标
- 状态：已完成

### 阶段 22：文件级落地映射
- [x] 为每个优先级识别文件级改造点
- [x] 记录依赖关系与推荐顺序
- [x] 输出可实施路线图
- 状态：已完成

### 阶段 23：规划文档中文化
- [x] 将 `task_plan.md` 改为中文
- [x] 将 `findings.md` 改为中文
- [x] 将 `progress.md` 改为中文
- 状态：已完成

### 阶段 24：P0.2 市场状态 / 风险姿态层首批实现
- [x] 增加轻量 `market_regime` 模块
- [x] 增加 `market-regime` CLI 命令
- [x] 将 risk budget 接入 `portfolio` / `portfolio-enhanced`
- [x] 在 `scan` / `refresh-scan` / `alpha` 中展示 posture 摘要
- [x] 补充定向测试与最小验证
- 状态：已完成

### 阶段 25：测试环境修复与全量验证
- [x] 在当前 `.venv` 中补齐 `pip`
- [x] 在当前 `.venv` 中安装 `pytest`
- [x] 运行全量测试并确认通过
- 状态：已完成

### 阶段 26：P0.3 `diagnose` 输出硬化
- [x] 为 `diagnose` 增加 confidence 结构
- [x] 为 `final_decision` 增加 bull / bear / invalidation 字段
- [x] 更新 markdown 摘要渲染
- [x] 补充定向测试与全量验证
- 状态：已完成

### 阶段 27：P0.1 workflow router / 引导入口
- [x] 增加轻量 workflow recommendation 数据模型
- [x] 增加确定性 intent 分类与内置 workflow 描述
- [x] 增加 `route` / `recommend` CLI 命令
- [x] 增加中文 workflow 参考文档
- [x] 补充定向测试与全量验证
- 状态：已完成

### 阶段 28：P1.1 thesis memory / postmortem
- [x] 增加 thesis / postmortem 数据模型
- [x] 增加本地文件化 thesis memory 存储层
- [x] 增加 `thesis capture/list/review/postmortem` CLI 命令
- [x] 增加 thesis markdown 摘要渲染
- [x] 增加中文 thesis memory 说明文档
- [x] 补充定向测试与全量验证
- 状态：已完成

### 阶段 29：P1.2 主题研究 / 证据链模式
- [x] 增加主题研究数据模型
- [x] 增加本地优先 `theme_research` 模块
- [x] 增加 `theme-scan` CLI 命令
- [x] 将 workflow router 接入主题研究意图
- [x] 增加主题研究 markdown 摘要渲染
- [x] 增加中文 theme research 说明文档
- [x] 补充定向测试与全量验证
- 状态：已完成

### 阶段 30：P1.3 全链路 confidence / provenance 展示
- [x] 在 `data_readiness` 中统一 confidence / provenance schema
- [x] 为 `market-regime` 增加 confidence / provenance
- [x] 为 `diagnose` 注入 provenance 并合并 data-quality confidence
- [x] 为 `theme-scan` / `thesis` 增加 provenance 展示
- [x] 为 `scanner` 候选结果增加 confidence / provenance 摘要
- [x] 在 `report_generator` 中统一渲染 confidence / provenance 区块
- [x] 补充定向测试与全量验证
- 状态：已完成

### 阶段 31：P2.1 `deep-diagnose` 长报告模式
- [x] 新增 `deep_diagnosis` 长报告合成模块
- [x] 新增 `deep-diagnose` CLI 命令
- [x] 在 `report_generator` 中增加长报告 markdown 模板
- [x] 新增中文 `deep-diagnosis` 参考文档
- [x] 补充定向测试与全量验证
- 状态：已完成

### 阶段 32：P2.2 manifest 式 workflow 运行
- [x] 增加 workflow manifest 数据模型
- [x] 新增 `workflow_runner` 模块
- [x] 新增 `workflow list/run` CLI 命令
- [x] 新增内置 routine manifests
- [x] 更新 workflow 参考文档
- [x] 补充定向测试与全量验证
- 状态：已完成

### 阶段 33：P2.3 高级 scorecard / attribution
- [x] 新增 scorecard / attribution 数据模型
- [x] 新增 `scorecards.py` 与 `postmortem.py`
- [x] 将 thesis / theme research 接入 scorecard
- [x] 将 thesis postmortem 接入 attribution
- [x] 新增 `scorecard` CLI 命令
- [x] 更新中文 scorecards 参考文档
- [x] 补充定向测试与全量验证
- 状态：已完成

### 阶段 34：质量门禁工具补齐与基线验证
- [x] 在当前 `.venv` 中安装 `ruff`
- [x] 在当前 `.venv` 中安装 `mypy`
- [x] 运行 `ruff check stockaskill/scripts tests`
- [x] 运行 `mypy stockaskill/scripts tests`
- [x] 记录当前 lint / type-check 基线问题
- 状态：已完成

### 阶段 35：`ruff` 收口与质量门禁首轮通过
- [x] 对 `stockaskill/scripts` 与 `tests` 做首轮格式化
- [x] 清理 import 排序与未使用 import
- [x] 收口剩余 `E501` 长行问题
- [x] 重新运行 `ruff check stockaskill/scripts tests`
- [x] 运行相关定向测试确认无回归
- 状态：已完成

### 阶段 36：文档入口与说明同步
- [x] 检查 `README.md` 是否覆盖新增 CLI 能力
- [x] 检查 `stockaskill/SKILL.md` 是否覆盖新增 skill workflow
- [x] 检查 `AGENTS.md` 是否仍包含过时示例
- [x] 同步更新三个文件
- 状态：已完成

## 当前关键问题
1. 仓库是否应继续保持任务作用域分析引擎，而非扩张为数据平台？
2. 哪些上游项目能力真正适合借鉴到 `stockaskill`？
3. 哪些增强最能提升用户决策质量，而不会显著增加复杂度？
4. 如何在不拆散当前统一 skill 形态的前提下，引入工作流、市场状态和研究记忆能力？
5. 首个实施批次应从哪一层切入，才能带来最大边际收益？

## 已确认的决策
| 决策 | 理由 |
|------|------|
| 使用文件化规划方式跟踪该任务 | 用户显式调用了 `planning-with-files-zh`，且任务是多阶段研究与规划 |
| 不将全市场全量增量同步作为主要产品方向 | 当前仓库定位不是数据仓库或后台同步平台 |
| 将 `FUND` 明确视为 ETF-first | 当前数据来源与缓存路径本质上是交易所 ETF 语义 |
| 先优化数据正确性、bounded sync、readiness 可见性 | 这些改造最符合当前仓库价值密度 |
| `stockaskill` 应保持统一本地执行引擎形态 | 当前结构更适合一个整合式 skill，而不是拆成数十个微 skill |
| 优先引入 market regime、workflow routing、thesis memory | 这三类能力比引入重型 persona / 估值系统更高性价比 |
| 将 `serenity-skill` 作为主题研究方法借鉴源，而非整体复制目标 | 其强项在主题投研与证据链，不在本地执行层 |
| 将 `claude-trading-skills` 作为流程编排与研究记忆借鉴源 | 其强项在 workflow、posture、memory loop |
| 将 `UZI deep-analysis` 作为深度报告约束借鉴源 | 其强项在输出硬门控，不适合整体照搬 |
| 按建议优先启动 `P0.2` 而不是 `P0.1` | 市场状态 / 风险姿态层能直接提升 `scan`、`alpha`、`portfolio` 三条主路径的决策质量，并为后续 workflow router 提供前置判断 |
| 修复当前 `.venv` 测试能力而不是绕回系统 Python | 用户明确要求在当前 `.venv` 中安装 `pytest` 并跑通测试，且仓库测试路径已经依赖项目内环境 |
| 在 `P0.3` 中优先增强结构化输出而不是引入更重的 deep-diagnose 新命令 | 当前阶段目标是提高现有 `diagnose` 的可审计性和解释力，并保持主路径接口稳定 |
| `P0.1` 采用确定性关键词路由而不是开放式自由解析 | 当前目标是补齐入口层，不引入新的模型依赖或不可控行为 |
| `P1.1` 采用本地文件存储而不是引入数据库/后台服务 | thesis memory 当前只需满足留痕、回看、复盘闭环，没必要扩大基础设施复杂度 |
| `P1.2` 采用本地主题模板 + 股票池映射，而不是直接依赖联网主题数据库 | 当前目标是补“主题研究入口”和证据链框架，不把仓库扩成外部主题研究平台 |
| `P1.3` 采用“低伪精度”的 confidence/provenance 摘要，而不是复杂评分仪表盘 | 当前阶段重点是把数据质量和来源前台化，而不是制造看似精确但不可解释的分数系统 |
| 当前先记录 `ruff` / `mypy` 基线，而不在同一轮混入大规模风格/类型清理 | 当前目标是先补齐质量门禁工具并确认真实问题分布，再按 lint 与 typing 分两段收敛 |

## 发生过的问题
| 问题 | 次数 | 处理方式 |
|------|------|----------|
| 仓库初始没有专属规划文件 | 1 | 在项目根目录创建 `task_plan.md`、`findings.md`、`progress.md` |

## 备注
- 现阶段更适合做“分层增强”，而不是大规模重构。
- 后续任何实现都应优先保留现有 `scan / diagnose / portfolio / backtest / sync / status` 主路径的稳定性。
- 下一候选阶段优先考虑 `mypy` 本地代码修复与第三方 typing 策略收口，因为 `ruff` 已通过，而 `mypy` 仍未通过。
