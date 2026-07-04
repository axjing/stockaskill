# Workflow 说明

## 目标

为 `stockaskill` 提供两层 workflow 能力：

- `route / recommend`
  - 轻量、确定性的意图路由
- `workflow list / workflow run`
  - manifest 式 routine 固化与参数化展开

## 命令

```bash
python stockaskill/scripts/run.py route 我要找A股机会 --market A
python stockaskill/scripts/run.py recommend 复核 601318 的投资逻辑 --market A --code 601318
python stockaskill/scripts/run.py route 构建组合 --market A --codes 600519,000858
python stockaskill/scripts/run.py workflow list
python stockaskill/scripts/run.py workflow run market-regime-daily --market A
python stockaskill/scripts/run.py workflow run portfolio-review-weekly --market A --codes 600519,000858
python stockaskill/scripts/run.py workflow run theme-research-weekly --market A --theme AI基础设施 --code 300100
```

`route` 与 `recommend` 是等价入口，都会输出：

- `intent`
- `market`
- `summary`
- `rationale`
- `steps`
- `notes`

`workflow run` 会输出：

- manifest 元信息
- 参数化后的 step 列表
- 缺失参数
- 建议产物路径

## 当前支持的意图

### 1. `opportunity_scan`
- 默认意图。
- 适用于“找机会”“筛股票”“看有哪些可买标的”等请求。
- 推荐路径：
  - `market-regime`
  - `scan`
  - `alpha`
  - `diagnose <TOP_CODE>`

### 2. `market_check`
- 适用于“先看风险姿态”“市场现在能不能加仓”等请求。
- 推荐路径：
  - `market-regime`
  - 条件允许后再进入 `scan`

### 3. `analyze_symbol`
- 适用于用户给出 `--code`，但目标更偏基础分析而不是冲突诊断。
- 推荐路径：
  - `sync symbol`
  - `analyze`
  - `diagnose`

### 4. `diagnose_symbol`
- 适用于“诊断”“复核”“失效条件”“bull / bear”类请求。
- 推荐路径：
  - `sync symbol`
  - `diagnose`

### 5. `build_portfolio`
- 适用于“建仓”“组合”“再平衡”“持仓构建”，或显式给出 `--codes`。
- 推荐路径：
  - `market-regime`
  - `sync portfolio`
  - `portfolio`

### 6. `sync_data`
- 适用于“同步”“刷新”“预热数据”等请求。
- 推荐路径：
  - `sync ...`
  - `status data ...`

### 7. `backtest_strategy`
- 适用于“回测”“历史表现”类请求。
- 推荐路径：
  - `backtest`
  - `market-regime`

## 当前内置 manifest

### 1. `market-regime-daily`
- 适用于每日开盘前或收盘后例行检查。
- 典型路径：
  - `market-regime`
  - `scan`

### 2. `portfolio-review-weekly`
- 适用于每周组合 review。
- 需要：
  - `--codes`
- 典型路径：
  - `market-regime`
  - `thesis list --status active`
  - `sync portfolio`
  - `portfolio`

### 3. `theme-research-weekly`
- 适用于每周围绕一个主题做跟踪。
- 需要：
  - `--theme`
- 可选：
  - `--code`
- 典型路径：
  - `theme-scan`
  - `deep-diagnose`
  - `thesis capture`

## 设计边界

- 不做开放式 LLM 意图理解，只做关键词匹配。
- `workflow run` 当前只解析并展开 routine，不直接执行 shell。
- manifest 当前使用 stdlib 可解析的 JSON-compatible YAML 形式，避免引入新依赖。
- 不新增新的分析能力，只负责把用户目标路由或编排到既有命令。
- 不改变 `scan / alpha / diagnose / portfolio / backtest / sync / status` 的现有语义。
