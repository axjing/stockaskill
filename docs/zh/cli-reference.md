# CLI 命令行全量参考与智能体工具字典

> **版本**: 2.1.0  
> **入口命令**: `python skills/stockaskill/scripts/run.py <command> [options]`

---

## 1. 全局通用参数

以下参数可在任意子命令后附加使用：

| 参数 | 类型 | 默认值 | 说明 |
|:---|:---|:---|:---|
| `--json` | Flag | `False` | **Agent 工具推荐**：纯净 JSON 直接流式输出至标准输出（stdout），零磁盘 I/O，无终端色彩字符污染 |
| `--output-dir` | String | `reports` | 磁盘报表保存目录 |
| `--format` | Choice | `both` | 报表生成格式：`json`, `md`, `both`, `none` |

---

## 2. 命令速查与分类表

```
+--------------------+-----------------------------------------------------+
| 分类               | 核心命令                                            |
+--------------------+-----------------------------------------------------+
| 选股与组合优化     | screen, portfolio                                   |
| 单股全方位诊断     | diagnose (支持 quick/full/deep), analyze*, deep-diagnose* |
| 投研论据生命周期   | thesis (capture, list, update, track)               |
| 数据增量与保鲜     | sync, cache stats, status                           |
| 市场宏观与情绪     | sentiment, regime, scan                             |
| 自动化工作流与评分 | workflow (list, run), scorecard                     |
+--------------------+-----------------------------------------------------+
* 注：带有星号的命令为保持向后兼容保留的独立别名。
```

---

## 3. 详细命令规范与范例

### 3.1 向量化截面选股与闭环流水线 (`screen`)

在 DuckDB 4,244 万行历史截面中进行亚秒级多因子排序。

#### 参数说明
- `--market`: 目标市场，可选 `A` (默认), `HK`, `US`。
- `--preset`: 策略预设，可选：
  - `momentum_enhanced` (默认): 高动量领涨突破策略
  - `low_vol` / `low_volatility`: 低波动稳健防御策略
  - `deep_value` / `value`: 深度价值与财务质量策略
  - `balanced`: 动量与价值平衡策略
- `--top`: 返回候选数量，默认 `10`。
- `--min-mcap`: 最低总市值过滤（单位：亿元），默认 `0`（不过滤）。
- `--sector`: 指定行业过滤（如 `--sector 医药生物`）。
- `--to-portfolio`: **流水线标志**。选股完成后立即以选出的标的作为资产池启动组合优化。
- `--capital`: 组合总可用资金，默认 `1000000` (100万元)。
- `--track`: **跟踪标志**。将分配的标的自动写入 Thesis 记忆库开启每日失效追踪。

#### 示例
```bash
# 基础截面选股 (JSON 流输出)
python skills/stockaskill/scripts/run.py screen --market A --preset low_vol --top 5 --json

# 一键闭环：选股 -> 优化组合 -> 100万元整手买入票据 -> 自动入库跟踪
python skills/stockaskill/scripts/run.py screen \
  --market A \
  --preset momentum_enhanced \
  --top 5 \
  --to-portfolio \
  --capital 1000000 \
  --track \
  --json
```

#### `--json` 返回示例
```json
{
  "market": "A",
  "preset": "momentum_enhanced",
  "top_n": 2,
  "count": 2,
  "candidates": [
    {
      "code": "688146",
      "name": "中船特气",
      "score": 346.0,
      "f_score": 0,
      "metrics": {"return_20d": 0.42, "close": 58.2}
    }
  ],
  "portfolio_pipeline": {
    "capital": 1000000.0,
    "weights": {"688146": 0.35},
    "trade_tickets": [
      {
        "code": "688146",
        "weight": 0.35,
        "target_value": 350000.0,
        "shares": 6000,
        "actual_value": 349200.0
      }
    ],
    "unallocated_cash": 650800.0,
    "thesis_ids": ["thesis_688146_20261101"]
  }
}
```

---

### 3.2 目标约束现代组合优化 (`portfolio`)

基于 SLSQP 求解最佳夏普比率权重，并自动按 A 股 100 股整手分配交易票据。

#### 参数说明
- `--optimize`: 开启目标约束非线性规划求解。
- `--codes`: 资产池股票代码列表（英文逗号分隔），例如 `600519,000858,601318`。
- `--target-cagr`: 目标年化复合收益率，例如 `0.12` (12%)。
- `--max-drawdown`: 最大允许回撤硬约束，例如 `0.08` (8%)。
- `--capital`: 投资组合本金，默认 `1000000`。
- `--market`: 市场，默认 `A`。

#### 示例
```bash
python skills/stockaskill/scripts/run.py portfolio \
  --optimize \
  --codes 600519,000858,601318 \
  --target-cagr 0.10 \
  --max-drawdown 0.06 \
  --capital 500000 \
  --market A \
  --json
```

---

### 3.3 单股多级诊断统一门面 (`diagnose`)

#### 参数说明
- `code`: 股票代码（必填，如 `600519`）。
- `--market`: 市场，默认 `A`（可选 `HK`, `US`, `FUND`）。
- `--level`: 诊断粒度层级：
  - `quick`: 快速基础指标（K线、估值比率、财务质量、多因子评分）。
  - `full`（默认）: 全量策略分析、买卖信号矩阵、股吧与市场情绪、风险预算。
  - `deep`: 研报级多维度博弈诊断，输出看多/看空逻辑、冲突矩阵与失效监控点。

#### 示例
```bash
# Agent 快速获取个股量化体检
python skills/stockaskill/scripts/run.py diagnose 600519 --level quick --json

# 人工复核完整策略与情绪
python skills/stockaskill/scripts/run.py diagnose 600519 --level full

# 建仓前生成深度博弈报告
python skills/stockaskill/scripts/run.py diagnose 600519 --level deep --json
```

---

### 3.4 动态增量保鲜与同步 (`sync`)

维护本地 DuckDB 数据的最新状态。

#### 参数说明
- 子操作：
  - `update <code>`: 增量更新指定单只股票。
  - `scan-universe`: 扫描并同步全市场股票列表元数据。
  - `symbol <code>`: 单个标的冷启动完整建档。
- `--market`: 市场代码（`A`, `HK`, `US`, `FUND`）。
- `--full-history`: 强制全历史冷启动下载（通常仅在初始化新股票时使用）。

#### 示例
```bash
# 增量保鲜茅台最新数据
python skills/stockaskill/scripts/run.py sync update 600519 --market A

# 检查当前数据就绪状态
python skills/stockaskill/scripts/run.py status data symbol 600519 --market A --json

# 查看 DuckDB 库整体统计
python skills/stockaskill/scripts/run.py cache stats --json
```

---

### 3.5 投资论据全生命周期管理 (`thesis`)

管理从建仓到退出的完整投资逻辑记忆链条。

#### 子操作
- `capture <code>`: 固化一条新论据，自动提取诊断中的 bull/bear/invalidation 条件。
  - 可选参数：`--notes "自定义说明"`, `--status [active|validating|exited]`。
- `list`: 列出当前已持久化的论据清单。
- `track <code>`: 基于最新行情与技术位自动比对失效条件。
- `update <code>`: 手动更新论据状态或追加跟踪进展。

#### 示例
```bash
# 固化建仓论据
python skills/stockaskill/scripts/run.py thesis capture 600519 --market A --notes "突破站稳年线" --json

# 查看所有待跟踪标的
python skills/stockaskill/scripts/run.py thesis list --market A --json

# 自动复核论据有效性
python skills/stockaskill/scripts/run.py thesis track 600519 --market A --json
```

---

### 3.6 宏观市场状态与情绪 (`regime` & `sentiment`)

基于 DuckDB 截面数据秒级计算全市场涨跌比、涨跌停统计及大盘风向。

#### 示例
```bash
# 查看大盘当前风险预算与仓位建议
python skills/stockaskill/scripts/run.py regime --market A --json

# 聚合股吧、资金流向与市场宽度情绪
python skills/stockaskill/scripts/run.py sentiment --market A --json
```

---

## 4. 智能体工具集成最佳实践 (For Agent Integration)

当 AI Agent（例如 Claude Code、OpenCode、Codex 或自定义 ReAct Loop）将 `stockaskill` 作为外部 Tool 调用时，请遵循以下规范：

1. **务必带上 `--json`**：
   - 彻底避免在控制台解析正则表达式或字符串分割；
   - 保证标准输出（stdout）可直接用 `json.loads(stdout)` 安全反序列化。
2. **优先使用 `screen --to-portfolio` 组合拳**：
   - 避免先调用 `screen`，再解析输出，再调用 `portfolio` 的多次往返，降低出错率并节约 70% 的 Token。
3. **日常分析使用 `diagnose --level quick`**：
   - 快速获取关键多因子得分与估值；仅当确认有开仓意向时，再调用 `--level deep` 提取论据。
