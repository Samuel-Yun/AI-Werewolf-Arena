# AI Werewolf Arena

以规则正确性和信息隔离为先的狼人杀引擎。默认使用 MockAgent 离线运行；也支持一个 DeepSeek API 驱动一个或全部座位。

## 环境与运行

需要 Python 3.12+。本工作区已准备 Python 3.13 的 `.venv`。

```powershell
# 新环境首次安装
python -m venv .venv
.venv\Scripts\python -m pip install -e ".[dev]"

# 使用本工作区已准备的环境
.venv\Scripts\Activate.ps1
python -m pytest
python -m werewolf play --mock --seed 123
python -m werewolf simulate --games 1000 --seed 123
```

如果 PowerShell 不允许激活，可直接使用 `.venv\Scripts\python.exe` 执行命令。

## Phase 1 的明确规则

- 12 人：4 狼人、1 预言家、7 平民。身份随机分配，座位与嘉宾配置固定。
- 好人清空所有狼人获胜。默认狼人存活人数达到好人存活人数获胜；`wolf_win: eliminate_good` 可改成清空好人。
- 每个存活狼人提交一次刀人票，只能选择存活的非狼人；多数票决定狼刀，平票按引擎种子随机选目标。
- 存活预言家每夜可验一个其他存活玩家，结果为狼人或好人；可以重复验同一玩家。
- 同一夜被刀的预言家仍能行动并收到验人结果。所有夜间行动收集完成后统一计算，在黎明公布死亡。
- 每个存活玩家按座位顺序发言一次，然后同时统计投票。禁止投自己、死人、不存在的座位；可以弃票。
- 默认白天平票不放逐；`vote_tie: seeded_random` 可配置随机裁决。
- 白天和黎明都进行胜负检查。没有警长、遗言、警徽、真实模型或视频系统。

## 架构与边界

```text
Provider -> AgentContext -> Action schema -> rule validation
                                               |
                                            Engine
                                               |
                                        pure resolution
                                               |
                                          Event -> reducer -> GameState
                                               |
                                      logs / transcript / replay
```

- `game/engine.py` 负责调度；`phase_handlers.py` 是明确的阶段处理表；`rules.py` 定义可行动者和合法目标。
- `actions.py` 使用 Pydantic 判别联合，拒绝未知字段、错误类型、无效 JSON；再进行游戏规则验证。
- `state.py` 区分 PublicState 和 SecretState。唯一状态修改路径是 `reducer.apply_event`。
- `resolver.py` 是不修改状态的结算函数；`win_conditions.py` 集中判断胜负。
- `agents/context.py` 只构造冻结且分离的玩家视图。村民只见公开信息和自身身份；狼队共享狼队信息；预言家只见自己的验人结果。
- 死者不能提交普通行动，也不会收到死亡之后新增的私密信息。游戏结束不会自动向 Agent 揭示全部身份。
- `providers/base.py` 定义 Provider 协议；MockProvider 只有 Context，没有引擎引用。
- Persona 是数据结构；MemoryStore 只读取每座位少量 JSON/YAML/Markdown 文本。PlayerBelief 与真实身份分离，预留 `expert_examples`。

这是受信任 Python 主程序中的接口隔离；未来第三方插件或不受信任的 Python 代码应放进独立进程。

## CLI

```powershell
python -m werewolf play --mode auto --mock --seed 123
python -m werewolf play --mode director --mock --seed 123
python -m werewolf play --seed 123 --quiet
python -m werewolf play --board configs/boards/phase1.yaml --players configs/players.yaml
python -m werewolf simulate --games 1000 --seed 123
python -m werewolf simulate --games 10000 --seed 123 --report data/simulations/large.json
python -m werewolf replay <game_id>
python -m werewolf replay data/games/<game_id>
```

从项目根目录运行，或用 `--board` 和 `--players` 显式指定配置。

## 日志与复现

`play` 每局在 `data/games/<game_id>/` 保存：

- `metadata.json`：种子、板型、固定玩家。
- `events.jsonl`：包括私密信息的完整引擎审计日志。
- `transcript.txt`：仅公开发言、投票和结果，供后续字幕使用。
- `result.json`：结果和完整最终状态，供 Replay 比对。

`events.jsonl` 和 `result.json` 是上帝视角文件，应由受信任的控制器读取，不进入 Agent 提示词。

事件包含版本、序号、游戏 ID、日数、阶段、类型、actor、target、visibility、recipients、payload 和 UTC 时间。Replay 使用同一 reducer，验证连续序号、游戏 ID、阶段顺序和状态不变量，并和保存的最终状态比对。

种子固定身份分配、Mock 行为、平票随机结果和完整 GameState。游戏 ID 和真实时间戳用于区分运行，允许不同。

Simulation 使用 `seed, seed+1, ...`，正常局只汇总统计，失败局保存完整日志和 `diagnostic.json`。报告包含完成数、崩溃数、不变量错误、平均/最大日数、阵营胜率和保护上限触发数；失败返回非零退出码。

`MAX_DAYS`、`MAX_EVENTS`、行动修正次数由 BoardConfig 配置。达到上限直接报告失败，绝不伪造胜者。当前 `deadlocks` 统计保护上限触发；真实 Provider 尚未接入。

## 渐进里程碑

1. Phase 1：狼人、预言家、平民，自动完整对局、信息隔离、日志、Replay、模拟验收。
2. Phase 2：女巫，解毒资源与夜间交互（已实现，`configs/boards/phase2.yaml`）。
3. Phase 3：猎人和白痴，死亡技能与投票资格（已实现，`configs/boards/phase3.yaml`）。
4. Phase 4：混血儿，配置化阵营和胜利条件（已实现，完整板型见下方）。

每阶段通过测试和 demo 后再推进。Director 和 DeepSeek Provider 已实现；复杂记忆、多服务商 Provider 与媒体系统属于后续里程碑。

### 女巫规则

女巫拥有一次解药和一次毒药。默认首夜可自救，每夜最多使用一瓶药；毒药只能选其他存活玩家。允许不使用药物。解药只能救当夜刀口，救人不能抵消毒药。同一目标同时被刀和被毒只死亡一次。

`witch.self_save` 可设为 `never` / `first_night` / `always`；`allow_both_potions` 控制一夜双药。默认解药耗尽后不再提供刀口；`see_victim_without_antidote` 可调整这一点。刀口仅在存活女巫的行动窗口提供。

```powershell
python -m werewolf play --mock --seed 123 --board configs/boards/phase2.yaml
python -m werewolf simulate --games 1000 --seed 123 --board configs/boards/phase2.yaml
```

### 猎人与白痴规则

默认猎人因狼刀、放逐、其他猎人开枪而死亡可开枪；含毒药的死亡不能开枪，包括刀毒同中。`hunter.allowed_causes` / `blocked_causes` 可配置，禁止原因优先。可以不开枪，技能只能使用一次，不能射死人。死亡技能按队列结算，支持连锁死亡，全部完成后才检查胜负。

猎人响应死亡技能时公开身份，包括选择不开枪。若双方同时清空，`simultaneous_elimination` 配置胜负优先级，默认 `good`，也可设为 `wolf`。

白痴首次被投出时公开身份、存活且失去投票权，之后仍能发言。默认翻牌白痴免疫后续放逐，不能成为投票目标；`idiot.exile_after_reveal: dies` 允许再次被投死。狼刀、毒药和猎人枪正常造成死亡。

```powershell
python -m werewolf play --mock --seed 123 --board configs/boards/phase3.yaml
```

### 预女猎白混与混血儿规则

完整板型为 4 狼、1 预言家、1 女巫、1 猎人、1 白痴、3 平民、1 混血儿。CLI 默认保留 Phase 1 基础板；通过 `--board` 使用正式完整板。

混血儿在首夜、狼队行动之前选择其他玩家为榜样，只能选择一次。默认跟随榜样的初始阵营，榜样死亡后不改变阵营。混血儿不是额外狼人，不加入狼队刀人，也不知道狼队、榜样身份或自身阵营；默认预言家查验为好人。

`hybrid` 配置独立决定规则：

| 字段 | 可选值与含义 |
| --- | --- |
| `alignment` | `follow_model` 跟随榜样；`good` / `wolf` 固定阵营 |
| `victory` | `aligned_team` 随所属阵营获胜；`model_team` 随榜样初始阵营获胜；`survive` 游戏结束时存活即个人获胜 |
| `counts_for_win` | 默认 `false`，不计入全局人数判定；`true` 按所属阵营计入人数 |
| `seer_result` | 配置验人结果 `good` / `wolf`，与所属阵营解耦 |
| `reveal_alignment` | 默认 `false`；设为 `true` 才向混血儿本人提供阵营 |

默认全局胜负只比较基础狼人和基础好人数。个人胜利包括阵营胜利中的死亡玩家。个人胜者保存在引擎日志和最终状态中，不向 Agent 公布以免泄漏身份；Simulation 额外统计 `hybrid_wins`，它不属于互斥的阵营胜局统计。

`eliminate_good` 不允许与计入人数的无刀人能力混血儿组合，以避免仅剩混血儿与一名好人时投票永久平局。配置加载时明确拒绝这种组合。

```powershell
python -m werewolf play --mock --seed 123 --board configs/boards/seer_witch_hunter_idiot_hybrid.yaml
python -m werewolf simulate --games 5000 --seed 123 --board configs/boards/seer_witch_hunter_idiot_hybrid.yaml
```

## Director 内容审核

```powershell
python -m werewolf play --mode director --mock --seed 123
python -m werewolf play --mode director --mock --seed 123 --board configs/boards/seer_witch_hunter_idiot_hybrid.yaml
```

每次白天发言在发布之前暂停，展示座位、嘉宾、草稿和导演身份视角：

- A：接受当前发言。
- R：用相同合法上下文重新生成。
- N：输入额外表达指导并重生成。
- E：编辑最终发言，仍经过 SpeechAction Schema 校验。
- S：跳过本次发言。
- G：查看完整导演状态。

未接受的草稿不会进入公开发言。审核决定保存在仅引擎可见的事件中；日志 Replay 只重建已接受内容。每次发言最多 20 次审核操作，超过上限产生诊断报告。

导演状态使用独立快照，Provider 自动收到的仍是玩家合法 Context。导演手动输入的指导和文本属于创作输入；引擎不把这些文本当成身份或生死事实。未来 hybrid 模式可通过 `DirectorRunner.review_when` 选择需要人工审核的内容，目前 CLI 提供 auto 和 director 两种模式。

各阶段的验收记录和建议提交信息见 [docs/milestones.md](docs/milestones.md)。

## DeepSeek API 测试

本地 `.env` 或进程环境变量中设置 `DEEPSEEK_API_KEY`。可选 `DEEPSEEK_BASE_URL`，默认官方 `https://api.deepseek.com`。`.env` 被 Git 忽略；Key 不写入配置 YAML、提示词、对局日志或错误正文。系统环境变量优先于 `.env`。

```powershell
# 12 座位使用同一个 API / 模型，按完整板自动跑一盘测试局
python -m werewolf play --provider deepseek --model deepseek-flash --players configs/players.deepseek-test.yaml --board configs/boards/seer_witch_hunter_idiot_hybrid.yaml --test-run --seed 123 --progress

# 也可仅在自定义 players.yaml 中把一个座位改成 provider: deepseek / model: deepseek-flash
python -m werewolf play --players configs/players.mixed.yaml --test-run --seed 123

# 强制离线，即使玩家文件里配置了真实 Provider
python -m werewolf play --mock --players configs/players.deepseek-test.yaml --seed 123
```

截至本次核实，官方将 `deepseek-flash` 对应到 DeepSeek-V4.1-Flash；模型别名可能更新，运行前会读取 `/models` 校验所请求模型，不自动切换旧模型。来源：[官方模型说明](https://api-docs.deepseek.com/zh-cn/quick_start/pricing/)。

`OpenAICompatibleClient` 只共享 HTTP 配置、凭据和用量统计。12 个独立 Provider 每次只发送本座位的 `AgentContext` 和公开板型规则，不共用对话历史，也不读取其他座位的隐藏身份。请求使用 JSON Output；默认关闭思考模式，`--thinking enabled` 可启用低强度思考。

单次连接/读取超时默认 45 秒，`--api-timeout` 可调整；每局最多 240 次聊天请求，`--max-api-requests` 可调整。认证、权限、余额错误或连续三次接口故障直接停止并报告；普通输出错误修正一次，之后从合法动作兜底。日志记录 API 请求成功/失败、Token 用量、实际返回的模型名和兜底次数。

`--test-run` 把 metadata/result 标记为 `test_run: true`、`memory_policy: disabled`、`exclude_from_history: true`。保留事件和 transcript 供查看、Replay；不读取或写入长期记忆，也不作为长期游戏历史导入。当前记忆接口只有读取功能，测试模式始终使用空 MemoryStore。

API 输出不保证由 `--seed` 完整复现；种子固定引擎随机行为，真实输出依靠保存的事件日志 Replay 重建。`simulate` 仍只允许 Mock，以免批量模拟产生 API 费用。
