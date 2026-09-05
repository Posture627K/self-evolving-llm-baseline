# DeepSeek 最小 Paired MVP：初步结果

## 运行设置

- Model：`deepseek-v4-flash`
- Harness：Claude Code
- Source：通过 outcome、process 与整体 verifier 的 `E1-LS1-T1`
- Target：held-out context-shift task `E1-LS1-T4`
- Delivery：matched prompt；三路均禁用原生 retrieval
- 唯一干预：No Artifact、Episodic Representation、Procedural Representation
- Source payload：17 个 events、72 个 evidence units、506,508 characters；无语义筛选和截断

## 结果

| Condition | Score | Outcome | Process | Verifier | Target-Agent cost estimate |
|---|---:|---|---|---|---:|
| No Artifact | 0.350 | Fail | Fail | Fail | $0.022877 |
| Episodic | 0.350 | Fail | Fail | Fail | $0.017925 |
| Procedural | 0.350 | Fail | Fail | Fail | $0.017507 |

三路均无 Agent exception，且失败的十项 outcome/process tests 完全相同。因此，在这个单一 source-target case 中，没有观察到 score-level representation effect：

$$
\Delta J_{\mathrm{episodic-no\ artifact}}
=
\Delta J_{\mathrm{procedural-no\ artifact}}
=0.
$$

相对于 No Artifact 的增量均为 0。

## 初步观察

1. Episodic payload 已确认完整注入，但没有改善 T4，说明“提供原始成功经验”本身不足以保证迁移。
2. Procedural skill 已确认生成并注入，但其内容主要围绕 T1 的 Flask 并发、single-flight 与共享 registry；T4 的显式需求则是 CI failure、用户 schema 与 webhook HMAC。该 source-specific scope mismatch 是 abstraction boundary/failure 的候选解释，但尚未形成因果证据。
3. 三路 Agent 都声称完成修复，但 verifier 给出相同失败集合，提示当前结果也受到共同的 target-solving bottleneck 影响。

## 解释边界

- 只有一个 source、一个 target、每个 condition 一次随机执行，不能推断普遍规律。
- 当前只能表述为“该 case 未观察到 transfer utility 差异”，不能表述为 Episodic 与 Procedural 等价。
- 本次跳过 abstraction-delta ledger，因此对信息保留、遗漏和过度泛化的判断仍是待验证解释。
- 三个 target Agent 分支成本估计合计 `$0.058309`；该数值不包括一次失败和一次成功的 procedural-author API 调用，也不包括 source acquisition。

## 结果位置

```text
/home/posture627ka/workspaces/skillevolbench-baseline/SkillEvolBench/workspace/paired_mvp/paired_deepseek_v4_flash_E1LS1T1_T4_mvp01
```

核心文件：`paired_summary.json`、`paired_summary.md`、`evidence/procedural/SKILL.md`、三路 `paired_branch_result.json`。
