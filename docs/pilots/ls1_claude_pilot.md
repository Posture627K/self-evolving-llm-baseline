# Claude Sonnet 5 最小 Paired MVP：初步结果

## 运行设置

- Provider：ANU `strproxy`（通过 ANU VPN）
- Model：`claude-sonnet-5`
- Harness：Claude Code
- Source：`E1-LS1-T1`，得分 `1.000`，outcome、process 与 verifier 全部通过
- Target：held-out context-shift task `E1-LS1-T4`
- Conditions：No Artifact、Episodic Representation、Procedural Representation
- Delivery：matched prompt；三路均禁用原生 retrieval
- Source payload：16 个 events、53 个 evidence units、329,064 characters；无语义筛选和截断

## 结果

| Condition | Score | Outcome | Process | Verifier | Target-Agent cost estimate |
|---|---:|---|---|---|---:|
| No Artifact | 0.400 | Fail | Fail | Fail | $0.300636 |
| Episodic | 0.400 | Fail | Fail | Fail | $0.278774 |
| Procedural | 0.250 | Fail | Fail | Fail | $0.371946 |

分数差为：

$$
\Delta J_{\mathrm{Episodic-NoArtifact}}=0,
$$

$$
\Delta J_{\mathrm{Procedural-NoArtifact}}
=
\Delta J_{\mathrm{Procedural-Episodic}}
=-0.15.
$$

三路均正常完成，无 Agent exception；Episodic 和 Procedural artifacts 均已确认真实注入。

## 分数差异的来源

No Artifact 与 Episodic 失败了相同的9项测试。Procedural 除这9项外，额外失败：

```text
test_p5_hmac_compare_digest
```

该 process test 要求 `compare_digest` 字符串直接出现在
`app/routers/webhooks.py`。Procedural 分支把 HMAC 验证封装到
`app/utils.py` 的 `verify_webhook_signature()`，再由 router 调用，因此没有满足测试对代码位置的静态要求。

所以，目前观察到的是 **verifier-score disagreement**，不能直接解释成真实功能退化。三路的 outcome 失败集合仍然相同，尚未证明 Procedural representation 导致了额外的功能性 transfer failure。

## 初步解释

1. Episodic 相对 No Artifact 没有产生分数变化；在这个单一 case 中，完整重放 source experience 没有带来可见迁移收益。
2. Procedural 分支改变了 Agent 的实现路径，但当前 `-0.15` 完全由一个位置敏感的 process test 解释。
3. 这一结果提示后续分析必须分开报告 functional outcome 与 implementation/process compliance，不能只使用单一综合分数判断 representation-dependent transfer。
4. 当前结果仍是单一 source、单一 target、每个 condition 一次运行，只能作为诊断性 pilot。

## Procedural author 说明

第一次 Claude author 输出完整，但包含未转义换行和引号；第二次输出在4,096-token 上限处截断。解析器已经加入仅针对“完整单文件 upsert”的受限恢复，并复用第一次完整响应，生成6,703字符的 `SKILL.md`。截断响应不会被恢复或使用。

## 成本

- Source acquisition：约 `$0.518728`
- 三个 target Agent 分支合计：约 `$0.951356`
- ANU proxy 本周 spend 在本次序列中约增加 `$4.92`；该增量还包含两次 procedural-author 调用，因此不能等同于三路 target cost。
- 完成后本周累计：约 `$6.80 / $100`

## 解释边界

- 不能据此声称 Procedural abstraction 普遍有害；
- 不能据此声称 Episodic 与 No Artifact 等价；
- 不能将静态 process-test 扣分直接视为功能性 negative transfer；
- 需要多次重复及更多 source-target pairs，才能判断差异是否稳定存在。

## 结果位置

```text
/home/posture627ka/workspaces/skillevolbench-baseline/SkillEvolBench/workspace/paired_mvp/paired_claude_sonnet5_E1LS1T1_T4_mvp01
```

核心文件：`paired_summary.json`、`paired_summary.md`、`evidence/procedural/SKILL.md`、三路 `paired_branch_result.json`。
