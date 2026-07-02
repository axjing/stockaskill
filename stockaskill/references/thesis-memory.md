# Thesis Memory 说明

## 目标

为 `stockaskill` 增加本地优先的 thesis lifecycle / postmortem 闭环，让个股诊断结果可以沉淀、回看、复盘。

当前实现坚持以下边界：

- 仅做本地文件存储，不引入数据库或后台服务。
- 只围绕现有 `diagnose` 结果建档，不新增重型研究协议。
- 重点解决“观点留痕、复看、复盘”三个问题。

## 存储位置

- 默认目录：`memory/theses`
- 每条 thesis 会生成：
  - `<thesis_id>.json`
  - `<thesis_id>.md`

## 命令

### 1. 捕获 thesis

```bash
python stockaskill/scripts/run.py thesis capture 601318 --market A --notes "保险龙头，等待赔率改善"
```

行为：

- 自动执行 `diagnose`
- 抽取 `signal / score / confidence / bull / bear / invalidation`
- 生成本地 thesis 记录

### 2. 列出 thesis

```bash
python stockaskill/scripts/run.py thesis list --market A --status active --limit 10
```

适用场景：

- 查看最近在跟踪的 thesis
- 过滤某个市场或某个代码

### 3. 复看 thesis

```bash
python stockaskill/scripts/run.py thesis review --code 601318 --market A
python stockaskill/scripts/run.py thesis review --thesis-id A_601318_20260702_000000
```

行为：

- 默认按 `code + market` 读取最近一条记录
- 也可显式按 `thesis_id` 打开

### 4. 写入 postmortem

```bash
python stockaskill/scripts/run.py thesis postmortem --code 601318 --market A --outcome win --notes "按计划执行，胜率兑现"
```

行为：

- 给最近一条 thesis 增加 `postmortem`
- 默认把 `thesis_status` 更新为 `closed`

## 当前字段

每条 thesis 至少包含：

- `thesis_id`
- `code`
- `market`
- `created_at`
- `source`
- `thesis_status`
- `signal`
- `score`
- `confidence_level`
- `confidence_score`
- `summary`
- `bull_case`
- `bear_case`
- `invalidation_conditions`
- `notes`
- `postmortem`
- `diagnosis_report`

## 当前适配结论

- 这一层已经能支撑最小研究闭环。
- 更重的主题归档、多次跟踪 review、组合级复盘，适合后续阶段继续扩展。
