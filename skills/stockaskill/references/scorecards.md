# Scorecards 说明

## 目标

为 `stockaskill` 增加一层本地优先、确定性的研究质量评分卡与复盘归因能力。

当前重点不是做“更复杂的打分系统”，而是把以下问题前台化：

- 这条 thesis 写得是否完整？
- 这次主题研究的证据链是否够扎实？
- 这份 diagnose 是否把冲突和失效条件说清楚了？
- postmortem 之后，后续应该改什么？

## 命令

```bash
python stockaskill/scripts/run.py scorecard thesis --thesis-id <ID>
python stockaskill/scripts/run.py scorecard thesis --code 601318 --market A
python stockaskill/scripts/run.py scorecard theme AI基础设施 --market A
python stockaskill/scripts/run.py scorecard diagnose 601318 --market A
```

## 当前覆盖对象

### 1. Thesis scorecard

主要看：

- thesis clarity
- bull / bear balance
- invalidation quality
- confidence quality
- provenance visibility

### 2. Theme scorecard

主要看：

- template fit
- layer coverage
- candidate depth
- evidence quality
- next checks quality

### 3. Diagnosis scorecard

主要看：

- signal strength
- conflict visibility
- confidence quality
- risk explicitness
- provenance visibility

## Postmortem Attribution

当 `thesis postmortem` 被写回后，系统会额外生成 attribution：

- `outcome`
- `primary_driver`
- `summary`
- `positives`
- `negatives`
- `adjustments`

这层不是在追求“因果精确”，而是在提供一份更结构化的复盘模板。

## 设计边界

- 当前 scorecard 是启发式、确定性、可解释打分。
- 它不替代原始报告，也不替代研究判断。
- 当前 attribution 只做轻量复盘归因，不引入交易执行日志或后台事件系统。
