# stockaskill

A 股中长期投资分析 Skill — 基于多因子量化模型, 覆盖选股、组合构建、风险控制、买卖时机全流程。数据源为 AKShare, 本地 SQLite 积累式缓存。

当前项目定位已经明确为:

- 本地优先、按任务补数据的投资分析/量化决策引擎
- 不是港股/美股/ETF/基金全市场全量同步平台
- `FUND` 路径当前按 ETF-first 语义支持, 不等同于广义公募基金全覆盖

## 适用框架

兼容以下智能体框架, 均使用标准 `SKILL.md` 格式:

| 框架 | 技能路径 | 加载方式 | 调用方式 |
|------|---------|---------|---------|
| [opencode](https://opencode.ai) | `.opencode/skills/stockaskill/` 或 `~/.config/opencode/skills/stockaskill/` | 按需加载 (skill 工具) | 自动匹配用户意图 / `skill stockaskill` |
| [claudecode](https://docs.anthropic.com/en/docs/claude-code/overview) | `.claude/skills/stockaskill/` 或 `~/.claude/skills/stockaskill/` | 按需加载 (描述匹配) | 自动触发 / `/stockaskill` |
| [codex](https://developers.openai.com/codex) | `.agents/skills/stockaskill/` (项目) 或 `~/.agents/skills/stockaskill/` (全局) | 按需加载 (描述匹配) | 自动触发 / `$stockaskill` / `/skills` |
| [openclaw](https://docs.openclaw.ai) | `<workspace>/skills/stockaskill/` 或 `~/.openclaw/skills/stockaskill/` 或 `.agents/skills/stockaskill/` | 会话启动时加载 (支持 gating 过滤) | 自动注入 / `/stockaskill` |
| Cursor | `.cursor/rules/stockaskill.mdc` | 按规则匹配 | 自动匹配文件上下文 |
| Windsurf | `.windsurf/rules/` | 会话启动时加载 | 自动注入 |
| 其他 | 参照对应框架的 skill 放置说明 | — | — |

> 所有框架共享同一份 `SKILL.md`, 只需将 `stockaskill/` 目录复制到对应路径即可。

## 快速开始

### 环境准备

```bash
pip install akshare efinance baostock pandas numpy scipy
```

### 安装

#### 一键安装 (推荐)

使用 [Agent Skills CLI](https://github.com/vercel-labs/skills) 自动检测已安装的框架并安装到对应路径:

```bash
# 全局安装 (当前用户所有项目可用)
npx skills add axjing/stockaskill --skill stockaskill -g

# 或项目级安装 (仅当前项目)
npx skills add axjing/stockaskill --skill stockaskill

# 仅安装到指定框架
npx skills add axjing/stockaskill --skill stockaskill -a claude-code -a opencode -a codex -g
```

`npx skills add` 自动识别以下框架:

| 框架 | 目标路径 |
|------|---------|
| opencode | `~/.config/opencode/skills/stockaskill/` |
| claudecode | `~/.claude/skills/stockaskill/` |
| codex | `~/.agents/skills/stockaskill/` |
| openclaw | `~/.openclaw/skills/stockaskill/` |
| Cursor | `.cursor/rules/stockaskill.mdc` |
| 全部 (ClawHub) | 发布后支持 `openclaw skills install @axjing/stockaskill` |

> 详细命令选项: `npx skills add --help` 或查看 [Agent Skills CLI 文档](https://github.com/vercel-labs/skills)。

#### 手动安装 (按框架)

以下为各框架的手动安装方法, 适用于无法使用 `npx skills add` 的环境。

##### opencode

```bash
# 全局安装 (所有项目可用)
mkdir -p ~/.config/opencode/skills
cp -r stockaskill ~/.config/opencode/skills/stockaskill

# 或项目级安装
mkdir -p .opencode/skills
cp -r stockaskill .opencode/skills/stockaskill
```

opencode 也兼容 `.claude/skills/` 路径, 可直接复用 claudecode 配置。

##### claudecode

```bash
# 全局安装
mkdir -p ~/.claude/skills
cp -r stockaskill ~/.claude/skills/stockaskill

# 或项目级安装
mkdir -p .claude/skills
cp -r stockaskill .claude/skills/stockaskill
```

claudecode 会自动发现 `.claude/skills/*/SKILL.md` 中的技能。

##### codex (OpenAI Codex CLI)

```bash
# 项目安装 (推荐, 按路径发现)
mkdir -p .agents/skills
cp -r stockaskill .agents/skills/stockaskill

# 或全局安装
mkdir -p ~/.agents/skills
cp -r stockaskill ~/.agents/skills/stockaskill
```

codex 从当前目录向上扫描 `.agents/skills/` 直至仓库根目录。也可在 `~/.codex/config.toml` 中配置技能路径:

```toml
[[skills.config]]
path = "/path/to/stockaskill"
enabled = true
```

##### openclaw

```bash
# 工作区安装 (推荐)
cp -r stockaskill ./skills/stockaskill

# 或个人全局安装
cp -r stockaskill ~/.openclaw/skills/stockaskill

# 或用 ClawHub 发布后安装
# clawhub install stockaskill
```

也可通过 `~/.openclaw/openclaw.json` 的 `skills.load.extraDirs` 添加自定义搜索路径:

```json5
{
  skills: {
    load: {
      extraDirs: ["/path/to/stockaskill"]
    }
  }
}
```

##### Cursor

```bash
mkdir -p .cursor/rules
# 将 SKILL.md 复制为 Cursor 规则
cp stockaskill/SKILL.md .cursor/rules/stockaskill.mdc
```

##### Windsurf

```bash
mkdir -p .windsurf/rules
cp stockaskill/SKILL.md .windsurf/rules/stockaskill.md
```

#### 通过 ClawHub 发布后安装

当 stockaskill 发布到 [ClawHub](https://clawhub.ai) 后, 可使用 OpenClaw 原生命令安装:

```bash
# 安装到当前工作区
openclaw skills install @axjing/stockaskill

# 或全局安装 (所有项目可用)
openclaw skills install @axjing/stockaskill --global
```

### 首次运行

首次使用时本地尚无数据, 系统会自动执行以下操作:

1. 创建 `.cache/quant_cache.db` (SQLite 数据库)
2. 按市场获取股票池/基金池元数据
3. 按当前任务范围分批拉取缺失的 K 线、财务数据、基金净值、指数数据

系统遵循“本地优先”原则:

- 已缓存且仍然新鲜的数据不会重复调用 API
- `analyze` / `diagnose` 会先补齐单标的所需历史与基本面
- `scan` / `alpha` 会先补齐候选池的必要数据, 再做本地评分
- `backtest` 只会对缺失历史做有上限的预热, 不会每次都全市场全历史重拉

最近几批优化后, 本地缓存还新增了以下可见能力:

- 显式有界同步: `sync symbol/watchlist/portfolio/scan-universe/etf`
- 显式数据诊断: `status data ...`
- HK/US 元数据质量信号: `metadata_source` / `metadata_status` / `metadata_completeness`
- HK/US 低质量元数据在 realtime scan 中会被轻量降权, 但不会被粗暴硬过滤

首次完整积累多市场历史数据仍会受到 API 限速保护 (500 次/天) 影响, 但不影响日常使用; 未缓存部分才会触发增量抓取。

### 后续使用

个股分析、市场扫描、基金筛选、组合构建、回测都优先从本地读取。
缓存命中不足时, 系统只补当前任务必需的数据, 然后立即继续分析。

## 核心功能

### 1. 多因子选股

7+1 维度评分系统, 自动过滤 ST/退市/次新, 输出评分排名。

| 因子 | 权重 | 说明 | 参考策略 |
|------|:----:|------|---------|
| 估值因子 | 20% | PE/PB/股息率复合估值 | 华泰证券 EP+BP 因子 |
| 质量因子 | 25% | ROE/毛利率/负债率/FCF 质量 | 长江证券雪球因子 |
| 成长因子 | 17% | 营收/净利润同比增长 | 中信建投超预期因子 |
| 动量因子 | 17% | 6月动量(剔除近1月反转) | A 股动量因子 |
| 低波因子 | 11% | 12月日波动率 | 国泰君安低波因子 |
| 市值因子 | 9% | log(总市值)负向打分 | A 股小市值溢价 |

增强版 (Core-Satellite) 权重: 动量 35% / 低波 18% / 质量 20% / 估值 17% / 成长 10%。

### 2. 组合构建

均值-方差优化, 施加以下约束:

- 单只股票权重上限: 20%
- 持仓数量: 6-30 只
- 目标最大回撤: 20% (稳健型)
- 再平衡频率: 30 天
- 止损线: 15%

支持三种风险偏好:

- **保守型**: 高评分 (>=70), 20 只股票, 预期回撤 <=10%
- **稳健型** (默认): 评分 >=60, 15 只, 预期回撤 <=15%
- **进取型**: 评分 >=50, 10 只, 预期回撤 <=25%

### 3. 买卖时机

基于三层信号判断:

- **估值位置**: PE 历史百分位 (低估/合理/高估)
- **均线趋势**: MA5/MA20/MA60 多头/空头/震荡
- **因子趋势**: 多因子综合得分

输出: 买入/持有/减仓/卖出 + 核心逻辑 + 止损/止盈参考

### 4. 行业轮动

计算各行业多因子平均得分, 输出超配/标配/低配建议, 辅助行业配置决策。

### 5. 回测验证

逐日模拟组合表现, 包含:

- 止损线检查 (个股止损)
- 定期再平衡
- 输出: 总收益/年化收益/最大回撤/夏普比率/卡玛比率/胜率/净值曲线

## 数据架构

### SQLite 表结构 (`quant_cache.db`)

| 表 | 内容 | 更新策略 |
|:---|:-----|:---------|
| `stock_pool` | 全市场股票池 (A / HK / US / FUND) | 按市场独立 TTL 更新 |
| `stock_pool_v2` | 市场感知股票池 + 元数据质量字段 | 当前主读取路径 |
| `daily_price` | 个股日 K 线 (前复权) | 按需增量, 只有缺失区间才拉取 |
| `daily_price_v2` | 市场感知 K 线缓存 | 当前主读取路径 |
| `factor_snapshot` | 基本面快照 (PE/PB/ROE/增速) | 按 TTL 过期更新 |
| `factor_snapshot_v2` | 市场感知基本面快照 | 当前主读取路径 |
| `computed_factors` | 计算因子值 | 本地计算, 无需 API |
| `sentiment` | 情绪分析结果 | 按需增量 |
| `sync_state` | scope 级同步状态 / 覆盖日期 / 错误信息 | `sync` / `status data` 使用 |
| `cache_meta` | 缓存元信息 (防重复) | 自动维护 |
| `api_usage` | API 调用计数 (限速) | 自动记录 |

### API 调用策略

- 个股分析: 0-2 次 API (数据已缓存则 0 次)
- 全市场选股: 候选数据齐备时 0 次, 冷缓存时按候选集补齐
- 组合优化: 数据齐备时 0 次, 否则按持仓标的增量补齐
- 回测: 仅对缺失历史执行有上限的批量预热
- 失败退避: 2^n 秒, 最多 3 次重试
- 日配额上限: 500 次 (硬限制, 超出后返回本地数据)

## 当前支持边界

- A 股: 支持最深, 也是当前最稳定的市场
- HK / US: 支持有界候选池、watchlist、portfolio、scan-universe 工作流
- ETF: 一等支持对象, 当前通过 `FUND` / `etf` 路径使用
- 广义公募基金: 暂不作为核心路线, 不建议按“全市场基金平台”理解当前项目

## 元数据质量说明

HK/US 池子会缓存以下额外字段:

- `metadata_source`: 元数据来源
- `metadata_status`: 归一化状态, 如 `active` / `delisted` / `suspended`
- `metadata_completeness`: 0-1 之间的完整度分数

这些信号目前用于两类目的:

- `status data` 中显示 market-level 元数据健康摘要
- realtime `scan` 中对 HK/US 低质量元数据做轻量降权

它们当前是软信号, 不是硬过滤条件。

## 配置参数

直接在 `stockaskill/scripts/config.py` 中修改 `_DEFAULTS` 字典。

## 与框架集成

### opencode

将 `stockaskill/` 放入技能路径后, opencode 自动发现 SKILL.md 并根据用户自然语言路由到对应功能。

**验证加载**:
```bash
opencode -e 'skill list'
# 或在会话中询问 "可用的技能有哪些?"
```

**权限配置** (可选, 在 `opencode.json` 中):
```json
{
  "permission": {
    "skill": {
      "stockaskill": "allow"
    }
  }
}
```

**使用方式**:
- 直接输入分析需求 (如 "分析 600519", "扫描 A 股 top 20")
- 或在对话中加载技能: `skill stockaskill`

### claudecode

**验证加载**:
```bash
# 在 claudecode 会话中运行
/skills
# 应看到 stockaskill 出现在技能列表中
```

**使用方式**:
- 自动触发: 当你的问题匹配 SKILL.md 中的 `description` 时, claudecode 自动加载并执行
- 手动调用: 在会话中输入 `/stockaskill` 直接调用技能
- claudecode 仅加载技能的名称和描述到上下文, 完整指令按需注入

**禁用自动调用** (可选):
在 SKILL.md 前部添加 `disable-model-invocation: true` 可阻止自动触发, 仅允许 `/stockaskill` 手动调用。

### codex (OpenAI Codex CLI)

**验证加载**:
```bash
# codex 会话中查看可用技能
/skills
# 或列出所有技能
ls .agents/skills/
```

**使用方式**:
- 自动触发: 任务描述匹配技能 `description` 时自动加载
- 显式调用: 在提示中使用 `$stockaskill` 或 `/skills` 选择技能
- 项目指令: 在仓库根目录创建 `CODEX.md` 或 `AGENTS.md` 编写持久化项目指引
- 全局指令: `~/.codex/AGENTS.md` 用于个人默认设置
- 建议在项目指令中明确写入“本地优先、按任务补数据、避免全市场全量同步”这一产品边界

**禁用技能** (在 `~/.codex/config.toml` 中):
```toml
[[skills.config]]
path = "/path/to/stockaskill/SKILL.md"
enabled = false
```

### openclaw

**验证加载**:
```bash
# 新会话启动时自动加载
# 或检查技能状态
openclaw skills list
```

**使用方式**:
- 会话启动时自动注入到 agent 上下文
- 手动调用: `/stockaskill`
- 通过 `~/.openclaw/openclaw.json` 中的 `skills.entries` 控制启用/禁用

**配置示例** (`~/.openclaw/openclaw.json`):
```json5
{
  skills: {
    entries: {
      stockaskill: { enabled: true }
    }
  }
}
```

**Gating 条件** (可选, 在 SKILL.md frontmatter 中):
```yaml
metadata:
  openclaw: '{"requires":{"bins":["python"]}}'
```

只有满足 gating 条件时, openclaw 才加载该技能。

### Cursor / Windsurf

**Cursor**:
```bash
# 将 SKILL.md 复制为 Cursor 规则
cp stockaskill/SKILL.md .cursor/rules/stockaskill.mdc
# 在规则文件头添加 paths 过滤:
# ---
# description: A-share stock analysis
# paths: "**/*.py"
# ---
```

**Windsurf**:
```bash
cp stockaskill/SKILL.md .windsurf/rules/stockaskill.md
```

### 直接使用 Python 脚本

```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent / "stockaskill" / "scripts"))

from advisor.diagnosis import StockDiagnosis
from factors.composite import CompositeAnalyzer
from strategies.aggregator import StrategyAggregator
from portfolio.builder import PortfolioBuilder
from data_engine import get_stock_pool, get_kline

# 1. 获取股票池
pool = get_stock_pool(market="A")

# 2. 个股深度分析 - 返回完整诊断报告
diagnosis = StockDiagnosis("600519", "A").full_report()

# 3. 量化策略综合评分
strategies = StrategyAggregator("600519", "A").analyze_all()

# 4. 多因子分析 + F-Score
factors = CompositeAnalyzer("600519", "A").analyze()

# 5. 构建组合
builder = PortfolioBuilder("我的组合", capital=1000000)
builder.add_from_strategy("600519", "A")
builder.add_from_strategy("000858", "A")
portfolio = builder.build()
print(portfolio.summary())
```

### 直接使用命令行

```bash
cd path/to/stockaskill
python stockaskill/scripts/run.py diagnose 600519 --market A       # 深度诊断
python stockaskill/scripts/run.py scan A --top 20                  # 全市场扫描
python stockaskill/scripts/run.py alpha A --top 10                 # Alpha动量扫描
python stockaskill/scripts/run.py analyze 600519 --market A        # 个股分析
python stockaskill/scripts/run.py portfolio --codes 600519,000858  # 组合构建
python stockaskill/scripts/run.py backtest                         # 回测验证
python stockaskill/scripts/run.py fetch pool                       # 刷新数据池
python stockaskill/scripts/run.py sync symbol 600519 --market A    # 单标的有界同步
python stockaskill/scripts/run.py sync etf --codes 510300,159915   # ETF有界同步
python stockaskill/scripts/run.py status data watchlist --market US # 数据状态诊断
```

### 有界同步与诊断

项目已经不再建议“先全量拉完再分析”的使用方式。推荐直接按任务范围同步:

```bash
python stockaskill/scripts/run.py sync symbol 600519 --market A
python stockaskill/scripts/run.py sync watchlist --market HK
python stockaskill/scripts/run.py sync portfolio --codes AAPL,MSFT --market US
python stockaskill/scripts/run.py sync scan-universe --market A --limit 200
python stockaskill/scripts/run.py sync etf --codes 510300,159915
```

查看数据状态与元数据健康度:

```bash
python stockaskill/scripts/run.py status data symbol 600519 --market A
python stockaskill/scripts/run.py status data watchlist --market US
python stockaskill/scripts/run.py status data portfolio --codes 0700,9988 --market HK
python stockaskill/scripts/run.py status data etf --codes 510300,159915
python stockaskill/scripts/run.py status data scan-universe --market A --limit 200
```

## 数据来源

所有数据通过 [AKShare](https://akshare.akfamily.xyz) 获取, 中间数据源为东方财富、新浪财经等公开财经平台。AKShare 是免费开源库, 无需注册或 Token。

## 参考策略

因子参数参考了以下 A 股市场验证有效的量化研究成果:

- 华泰证券: 因子周期与因子选股体系 (2010-2024)
- 长江证券: 雪球因子与高质量选股 (2012-2024)
- 中信建投: 超预期因子与财报选股 (2013-2024)
- 国泰君安: 低波动异象与低波因子 (2009-2024)
- 沪深 A 股: 小市值溢价与动量反转效应 (2000-2024)
- 沪深港通: 北向资金跟踪与聪明钱效应 (2016-2024)

## 风险提示

- 本工具的输出仅作为投资参考, 不构成投资建议
- 所有数据来源为第三方公开平台, 数据延迟约为 0-15 分钟
- 历史回测结果不代表未来收益
- 投资有风险, 入市需谨慎
