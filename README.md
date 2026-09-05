# Self-Evolving LLM: Artifact Transfer Baseline

**研究问题：同一条成功经验，保留为 episodic trajectory，或抽象为 procedural skill，是否会改变后续任务的迁移表现？**

本仓库在固定 Model 与 Harness 的条件下比较外部 Artifacts。上游是 [SkillEvolBench](https://github.com/AIoT-MLSys-Lab/SkillEvolBench/tree/9e3daa339987c3cfa624121e1be442593a53d43c)，固定 commit `9e3daa339987c3cfa624121e1be442593a53d43c`。这里新增的核心实验是 **same-source、matched-delivery 的三条件比较**：复用同一条 acquisition experience，并把 Episodic 和 Procedural 放在相同的 prompt 入口，关闭原生 retrieval。

**当前主实验：E1-LS3，已完成 27/27 个 target branches。** 一个通过 verifier 的 `E1-LS3-T1` source，三个 targets `T4/T5/T6`，三个条件，每个条件三次匹配重复。运行记录中的模型为 `claude-sonnet-5`（ANU gateway），Harness 为 Claude Code。A/B/C 是配置匹配的独立重复，不是可控生成随机种子。

| 当前 LS3 主实验 | No Artifact | Episodic | Procedural |
|---|---:|---:|---:|
| T4：context shift | 0.4167 | 0.9375 | 0.5625 |
| T5：adversarial | 1.0000 | 1.0000 | 1.0000 |
| T6：composition | 0.9375 | 0.9792 | 0.9792 |

数值为三次重复的平均 normalized score。**T4 的差异主要体现在架构与流程契约，不能直接归因为抽象导致信息损失；T5 有天花板效应；T6 的小幅分差来自非功能契约。** 当前结果不能支持 Episodic 普遍优于 Procedural，也不构成统计稳定性或机制因果证据。详见[当前发现与局限](paired_repetition_findings.md)和[按构念拆分的结果](paired_repetition_summary.md)。

老师审阅时希望讨论：

1. 下一步是否优先增加独立 source / task family，检验 T4 差异是否具有可重复性？
2. 功能迁移和 contract compliance 应如何分别作为主要指标与辅助指标？
3. 是否应针对 T4 做受控的信息补回/删除实验，定位候选信息变化，而不是仅扩大总分比较？

## 阅读顺序

1. [实验设计：上游 baseline 与新增同源比较](docs/experiment_design.md)
2. [当前 LS3 发现](paired_repetition_findings.md) → [完整结果表](paired_repetition_summary.md) → [逐分支索引](results/branch_index.json)
3. [共享 source 与冻结 skill](artifacts/shared_source/) → [verifier construct audit](verifier_construct_audit.md)
4. [无需 API 的离线核验 / 需要凭据的实验运行](docs/reproduction.md)
5. [四处上游工程修改及其原因](docs/engineering_changes.md)

## 已完成与尚未完成

| 内容 | 状态与证据 |
|---|---|
| 官方 baseline 运行基础设施 | 已有配置/任务资产校验、dry-run、smoke 和运行脚本；三个官方条件分别为 `no_skill`、`raw_trajectory_rag`、`selfgen_experience_always` |
| 官方三个条件的全量真实实验 | 本快照没有完成证据，不将单任务 smoke 计为全量复现 |
| 当前 LS3 paired pilot | 27/27 分支，0 Agent exception；九组 Episodic 输入及九组冻结 Procedural artifact 各自哈希一致 |
| 分数解释 | 同时保留 functional、contract、form 分类与失败检查，不将综合分数变化自动视为功能迁移 |
| 成本口径 | target branches 估算合计 `$8.722002`，不含 source acquisition 与 procedural authoring；不是实际账单 |
| 发布整理验证 | 见[验证记录](docs/validation.md)；本次整理没有重新调用模型 |

## 两个入口

**只查看和核验已发布结果：Python 3.10+，标准库即可；不需要 API key、Docker 或安装上游。**

```powershell
# Windows PowerShell，在本仓库根目录运行
.\verify_offline.ps1
```

```bash
# Linux / Ubuntu WSL，在本仓库根目录运行
bash ./verify_offline.sh
```

**需要新跑实验：Ubuntu / WSL、Docker、Python 3.12 及模型凭据。** 路径通过 `BASELINE_RUNTIME_ROOT` 指定，默认 `$HOME/workspaces/self-evolving-llm-baseline`。完整的安装、source 获取、三目标重复运行和费用确认步骤见[复现说明](docs/reproduction.md)。新运行不会得到与原 API 调用逐字相同的轨迹。

## 历史 LS1 pilots，与当前 LS3 分开阅读

| 历史试验 | 范围 | 结果解释 |
|---|---|---|
| [LS1 / DeepSeek](docs/pilots/ls1_deepseek_pilot.md) | `E1-LS1-T1 → T4`，三条件各一次 | 三条件均为 0.350，没有观察到 score-level representation effect |
| [LS1 / Claude](docs/pilots/ls1_claude_pilot.md) | `E1-LS1-T1 → T4`，三条件各一次 | 0.400 / 0.400 / 0.250；额外扣分来自位置敏感的 process check，未证明额外功能退化 |
| **当前 LS3** | `E1-LS3-T1 → T4/T5/T6`，27 分支 | 本 README 顶部结果表；独立保留功能与契约指标 |

历史报告保留原始结论，但不是当前实验的状态入口。早期 acquisition policy 脚本仍用于 LS1；LS3 的 source 命令显式指定 `--task-id E1-LS3-T1`。

## 仓库内容与凭据边界

- 根目录：运行/分析入口、当前 LS3 报告、配置清单、依赖版本快照。
- `tests/`：工程回归检查；`results/`：27 分支及 source 的结果、verifier 报告。
- `artifacts/`：共享 source input 与冻结 skill，仅保存一份，附九组哈希映射。
- `upstream/`：固定 commit、四文件补丁及校验值；通过 `bootstrap_upstream.py` 重建上游，不上传重复 checkout。
- `docs/pilots/`：早期 LS1 报告；`docs/original_running_guide.md`：明确标注的历史运行说明。

仓库只包含空白 `.harbor-agents.env.example` 模板。真实凭据、环境文件备份、虚拟环境、IDE 配置、完整运行配置及 Agent session backups 均排除。`security_check.py` 可检查最终暂存的 Git blobs，且只报告文件名与风险类型，不输出密钥值。上游原有权利不因本仓库发生变化，详见[来源与补丁说明](docs/engineering_changes.md)。
