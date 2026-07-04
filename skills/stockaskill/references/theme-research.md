# Theme Research 说明

## 目标

为 `stockaskill` 增加一个本地优先、可选的主题研究模式，从：

- 主题
- 产业链层级
- 产业链卡点
- 候选公司

逐层收缩，而不是直接把“最热股票”当成研究结论。

## 命令

```bash
python stockaskill/scripts/run.py theme-scan AI基础设施 --market A
python stockaskill/scripts/run.py theme-scan 机器人 --market A --top 3
python stockaskill/scripts/run.py theme-scan 储能 --market A --candidates 150
```

## 当前支持主题

- `AI基础设施 / AI / 算力`
- `机器人 / automation`
- `电池 / 储能 / 新能源`

未命中的主题会走 `custom` 模式：

- 仍然输出层级、证据、反证和下一步检查
- 但层级模板会更通用

## 输出结构

主题研究结果至少包含：

- `theme`
- `resolved_theme`
- `market`
- `summary`
- `key_question`
- `layers`
- `lower_priority_areas`
- `next_checks`

每个 layer 至少包含：

- `layer`
- `scarce_layer`
- `rank`
- `score`
- `why_here`
- `evidence`
- `disconfirming_signals`
- `candidates`

## 当前方法边界

- 优先依赖本地股票池、metadata 和本地因子缓存。
- 不强依赖联网数据，因此更像“主题研究入口”而不是完整主题数据库。
- 当前研究方法强调：
  - 先排产业链层级，再排公司
  - 给出支持证据
  - 给出反证/降级信号
  - 给出下一步应验证的点

## 推荐使用路径

1. `theme-scan <THEME>`
2. `diagnose <TOP_CODE>`
3. `thesis capture <TOP_CODE>`

这条路径对应当前仓库最合适的“主题 -> 个股 -> 研究留痕”闭环。
