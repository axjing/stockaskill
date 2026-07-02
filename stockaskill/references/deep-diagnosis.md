# Deep Diagnosis 说明

## 目标

为 `stockaskill` 增加一个显式 opt-in 的长报告模式，用来做单票深度复核。

它建立在现有 `diagnose` 之上，但更强调：

- 冲突呈现
- 失效条件
- 下一步检查
- 长文本研究摘要

## 命令

```bash
python stockaskill/scripts/run.py deep-diagnose 601318 --market A
python stockaskill/scripts/run.py deep-diagnose AAPL --market US --format md
```

## 与 `diagnose` 的区别

- `diagnose`
  - 保持轻量
  - 适合快速单票判断
  - 以结构化分数、bull/bear/invalidation 为主
- `deep-diagnose`
  - 是更重的研究复核模式
  - 增加 executive summary、variant perception、conflict matrix、next checks
  - 更适合进入 thesis capture 前的最后一轮核查

## 输出结构

`deep-diagnose` 结果至少包含：

- `executive_summary`
- `variant_perception`
- `supporting_evidence`
- `conflict_matrix`
- `bear_case`
- `invalidation_conditions`
- `next_checks`
- `confidence`
- `provenance`
- `diagnosis_report`

## 当前边界

- 仍然是本地优先、确定性、任务作用域实现。
- 不引入新增 agent、persona 或估值建模系统。
- 不替代现有轻量 `diagnose`，而是作为更重的可选模式。

## 推荐使用路径

1. `diagnose <CODE>` 做快速判断
2. `deep-diagnose <CODE>` 做冲突复核
3. `thesis capture <CODE>` 留痕

如果研究从主题开始，则先走：

1. `theme-scan <THEME>`
2. `deep-diagnose <TOP_CODE>`
3. `thesis capture <TOP_CODE>`
