# Training-Free Paired MVP：初步发现

## 1. 执行范围

- Source experience：`E1-LS3-T1`，其 source run 得分为 `1.000`，outcome、process 与 verifier 均通过。
- Held-out targets：`E1-LS3-T4`、`E1-LS3-T5`、`E1-LS3-T6`。
- Conditions：No Artifact、Episodic、Procedural。
- 每个 target 运行 A/B/C 三次匹配重复，共完成 27 个 target branches。
- Source 与 target 均使用 `claude-sonnet-5`；三种条件使用 matched prompt delivery，并关闭原生 skill retrieval。
- 九个 Episodic payload 的 SHA-256 完全一致；九个 Procedural artifact 的 SHA-256 也完全一致，确认所有 target 与重复使用同一 source evidence 和同一冻结 abstraction。

A/B/C 是配置匹配的独立重复，不是可控随机种子。当前 Claude 接口不提供 generation seed。

## 2. 综合分数

| Target | No Artifact | Episodic | Procedural |
|---|---:|---:|---:|
| `E1-LS3-T4` | 0.417 | 0.938 | 0.562 |
| `E1-LS3-T5` | 1.000 | 1.000 | 1.000 |
| `E1-LS3-T6` | 0.938 | 0.979 | 0.979 |

表中为三次重复的平均 normalized score。

## 3. 按 verifier construct 拆分

- `T4`：Episodic 的 functional pass rate 为 `0.952`，Procedural 为 `0.857`，No Artifact 为 `0.810`；对应 contract pass rate 分别为 `0.889`、`0.222`、`0.000`。因此，Episodic–Procedural 差异包含功能差异，但更大部分来自任务明确要求的模块化与插件设计契约。
- `T5`：三种条件的 functional 与 contract pass rate 均为 `1.000`，属于 ceiling case，不能据此推断两种 representation 等价。
- `T6`：三种条件的 functional pass rate 均为 `1.000`；综合分数的小幅差异来自 coverage tooling contract，而非功能差异。
- 三个 target 均没有 form 类检查，因而本轮差异不是由固定文件名、符号或代码布局等形式敏感项造成的。

## 4. 当前可以支持的判断

本轮在 `T4` 观察到候选的 representation-dependent transfer：相同 source experience 以 Episodic 与 Procedural 形式提供时，后续结果不同，而且该差异在两次重复中同时出现在功能检查上。不过，差异更明显地体现为架构与流程契约遵循，因此现阶段只能把它视为需要解释的案例，不能直接归因为 procedural abstraction 的信息损失。

`T5` 表明部分 target 缺乏区分度；`T6` 表明综合分数提升可能只反映非功能契约。两者共同说明，论文不能只报告单一 benchmark score，而应持续区分 functional transfer 与 contract compliance。

## 5. 当前不能支持的判断

- 不能声称 Episodic 普遍优于 Procedural；
- 不能声称 Procedural abstraction 必然导致迁移退化；
- 不能从三次 API 重复推断统计稳定性；
- 尚未证明 T4 的差异由哪些 abstraction-induced information changes 导致。

## 6. 运行完整性

- 完成分支：`27 / 27`；
- Agent exceptions：`0`；
- 无法映射到 construct audit 的失败检查：`0`；
- target branch 估算成本：`$8.722002`，不含 source acquisition 与 procedural authoring。
