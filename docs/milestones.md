# 里程碑验收记录

环境：Python 3.13，工作区 `.venv`，全部使用 MockProvider。每个阶段都在通过测试和完整 demo 后推进。

| 阶段 | 测试通过数 | Demo seed | Demo 结果 | Simulation |
| --- | ---: | ---: | --- | --- |
| Phase 1：狼 / 预言家 / 平民 | 42 | 123 | 狼人胜，第 4 天 | 1,000 / 1,000 完成 |
| Phase 2：女巫 | 57 | 123 | 狼人胜，第 5 天 | 1,000 / 1,000 完成 |
| Phase 3：猎人 / 白痴 | 72 | 123 | 狼人胜，第 4 天 | 1,000 / 1,000 完成 |
| Phase 4：混血儿 / 正式完整板 | 94 | 123 | 狼人胜，第 4 天 | 5,000 / 5,000 完成 |
| 离线 Director | 101 | 123 | 审核接受流程完整结束 | 已测试各审核选项与 Replay |

所有阶段模拟的 crash、deadlock、invariant violation 均为 0。Phase 4 最大 8 天，平均 3.632 天；好人胜 184 局，狼人胜 4,816 局。随机 Mock 的胜率仅用于记录模拟分布。

原始汇总报告保存在工作区的 `data/simulations/phase1.json` 至 `phase4.json`（生成数据不纳入 Git）。失败局会输出 seed 并保存诊断及事件日志。

最终收尾验收：106 项测试通过，覆盖双方同时清空的胜负配置、不合法目标和错误胜者不变量；基础板再次模拟 1,000 局全部完成，三类错误仍为 0，报告为 `data/simulations/final-phase1.json`。种子 123 的最终 demo 与早期 Phase 1 日志的 Replay 均通过。

## 核心模块

- 规则与状态：`game/state.py`、`actions.py`、`rules.py`、`validation.py`。
- 状态机与结算：`game/engine.py`、`phase_handlers.py`、`resolver.py`、`win_conditions.py`。
- 事件与重放：`game/events.py`、`reducer.py`、`storage/replay.py`。
- 信息隔离：`agents/context.py`；Provider 只接收 AgentContext。
- 角色配置：`config.py`、`roles/skills.py`、`roles/alignment.py`、`configs/boards/`。
- 自动对局与创作：`runner.py`、`simulation.py`、`director/cli.py`。

## 建议提交信息

```text
feat: implement event-driven werewolf core and simulation validation
feat: add configurable witch potions and night resolution
feat: add hunter death queue and idiot voting rules
feat: add configurable hybrid alignment and full twelve-seat board
feat: add offline director speech review
```

当前目录最初没有 Git 仓库。这些是建议提交信息；本轮未创建提交。

## 下一里程碑

DeepSeek Provider 已接入。按用户明确选择，首次真实测试为 12 个座位共用一个 API / 模型，使用 DeepSeek-V4.1-Flash、种子 123、非思考模式和完整板型。

本局第 3 天狼人获胜，70 次聊天请求，1 次合法兜底，Replay 比对通过。测试结果被标记为排除长期记忆/历史。原始文件在 `data/games/fd33e80675e844b6bd9a179d84a61033/`。

首盘暴露模型的存活状态跟踪和发言规则理解问题；后续提示词已补充当前存活/死亡名单和明确的座位发言规则，没有重跑或替换原始结果。

建议提交：`feat: add stateless DeepSeek API provider and isolated test runs`。
