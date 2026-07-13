---
name: hermeskevin-research-trigger
description: 从 hermeskevin 触发和跟踪证据门控的多智能体研究流程。用户要求启动、追踪、恢复或查看研究流程时使用；通过 SZ81 的 researchctl 创建任务，不直接绕过数据和独立复核 gate。
---

# 研究流程触发器

当用户要求启动多智能体研究时，先确认研究问题、标的和截止日期；不需要重复询问已在用户材料中的内容。执行：

```bash
/home/ubuntu/.local/bin/hermeskevin-research-trigger.sh create \
  --research-type deep_research \
  --question '研究问题'
```

返回 `run_id` 和当前阶段。流程状态为：`QUALIFY → PLAN → ACQUIRE_DATA → VALIDATE_DATA → ANALYZE → REVIEW → DELIVER → RECORD`。

查看状态：

```bash
/home/ubuntu/.local/bin/hermeskevin-research-trigger.sh status RUN_ID
```

规则：

- 只在 `DONE` 时称研究完成；`BLOCKED_*` 必须清楚告知阻断原因和所需输入。
- 深度研究必须经过数据验证和独立复核，不得直接发送未复核报告。
- 需要实施研究时，按当前阶段的 `handoff.json` 指令委派给相应角色；不要跳过所需 artifact。
