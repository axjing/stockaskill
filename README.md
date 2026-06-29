# stockaskill

A 股中长期投资分析 Skill — 基于多因子量化模型, 覆盖选股、组合构建、风险控制、买卖时机全流程。数据源为 AKShare, 本地 SQLite 积累式缓存。

## 适用框架

兼容以下智能体框架:

- [opencode](https://opencode.ai)
- [claudecode](https://docs.anthropic.com/en/docs/claude-code/overview)
- OpenClaw
- Codex
- 其他支持 `SKILL.md` 或 Python 脚本调用的 Agent 框架

## 快速开始

### 环境准备

```bash
pip install akshare pandas numpy
```

### 安装

将 `stockaskill/` 目录放入框架技能的搜索路径:

- **opencode**: `~/.opencode/skills/stockaskill/`
- **claudecode**: `~/.claude/skills/stockaskill/`
- **其他框架**: 参照对应框架的 skill 放置说明

### 首次运行

首次使用时本地尚无数据, 系统会自动执行以下操作:

1. 创建 `.cache/quant_cache.db` (SQLite 数据库)
2. 调用 AKShare 获取全市场股票池
3. 按需分批拉取个股 K 线、财务数据

首次全量拉取因受 API 限速保护 (500 次/天), 约需几天完成全部数据积累。在此期间功能正常可用, 仅未缓存的数据会实时拉取。

### 后续使用

个股分析数据优先从本地读取, 仅缺失数据触发增量 API 调用。

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
| `stock_pool` | 全市场股票池 (A/ HK/ US) | 按 TTL 过期更新 |
| `daily_price` | 个股日 K 线 (前复权) | 按需增量, 只有缺失区间才拉取 |
| `factor_snapshot` | 基本面快照 (PE/PB/ROE/增速) | 按 TTL 过期更新 |
| `computed_factors` | 计算因子值 | 本地计算, 无需 API |
| `sentiment` | 情绪分析结果 | 按需增量 |
| `cache_meta` | 缓存元信息 (防重复) | 自动维护 |
| `api_usage` | API 调用计数 (限速) | 自动记录 |

### API 调用策略

- 个股分析: 0-2 次 API (数据已缓存则 0 次)
- 全市场选股: 0 次 (纯本地计算)
- 组合优化: 0 次 (纯本地计算)
- 失败退避: 2^n 秒, 最多 3 次重试
- 日配额上限: 500 次 (硬限制, 超出后返回本地数据)

## 配置参数

直接在 `scripts/config.py` 中修改 `_DEFAULTS` 字典。

## 与框架集成

### opencode 集成

将 `stockaskill/` 放入 `~/.opencode/skills/` 后, opencode 会自动识别 SKILL.md 并根据用户自然语言路由到对应功能。

### 直接使用 Python 脚本

```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent / "scripts"))

from advisor.diagnosis import StockDiagnosis
from factors.composite import CompositeAnalyzer
from strategies.aggregator import StrategyAggregator
from portfolio.builder import PortfolioBuilder
from data_engine import get_stock_pool, get_kline

# 1. 获取股票池
pool = get_stock_pool(market='A')

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
python scripts/run.py diagnose 600519 --market A       # 深度诊断
python scripts/run.py scan A --top 20                   # 全市场扫描
python scripts/run.py alpha A --top 10                  # Alpha动量扫描
python scripts/run.py analyze 600519 --market A         # 个股分析
python scripts/run.py portfolio --codes 600519,000858   # 组合构建
python scripts/run.py backtest                          # 回测验证
python scripts/run.py fetch pool                        # 刷新数据池
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
