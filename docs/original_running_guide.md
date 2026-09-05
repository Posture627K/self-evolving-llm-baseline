> Historical setup notes. These notes describe earlier local defaults and LS1 workflows. For the current LS3 snapshot and portable commands, use the [main README](../README.md) and [reproduction guide](reproduction.md).

# Training-Free Artifact Baseline

本目录用于复现 SkillEvolBench 的三个基础条件，并为后续 same-source MVP 提供运行基线。

## 对比条件

| 研究条件 | SkillEvolBench 配置 | 含义 |
|---|---|---|
| No Artifact | `no_skill` | 不使用持久化经验 |
| Episodic | `raw_trajectory_rag` | 检索历史 trajectory |
| Procedural | `selfgen_experience_always` | 将 acquisition experience 写成并持续修订 skill |

Model、Harness、任务顺序和模型参数保持不变，只改变外部 artifact 条件。默认固定 `gpt-5.4`、order seed `A`；可在运行时替换为实际可访问的官方 model preset。

## 目录

- `SkillEvolBench/`：官方仓库，固定于 commit `9e3daa339987c3cfa624121e1be442593a53d43c`；
- `run_baseline.ps1`：Windows 运行入口；
- `setup_wsl_env.sh`：创建 WSL Python 3.12 环境并安装固定版本的 Harbor；
- `install_docker_wsl.sh`：按 Docker 官方 apt 源安装 Docker Engine；
- `build_agent_runtime_wsl.sh`：在临时构建上下文中兼容当前 OpenClaw 非交互初始化，并构建 Agent 运行镜像；
- `run_baseline_wsl.sh`：WSL 校验、dry-run 和真实运行入口；
- `run_smoke_wsl.sh`：默认用 Gemini 只执行一个真实任务，用于验证凭据与端到端调用；
- `run_acquisition_policy_wsl.sh`：在固定配置下按次数上限获取第一条完全通过 verifier 的 T1 source，并保留所有尝试；
- `latest_selected_source.json`：最近一次完全通过的 source 指针与验证摘要；
- `sync_runtime_fixes_wsl.sh`：同步 trajectory 解析、DeepSeek 成本和 replay 审计字段三项本地修复；
- `check_deepseek_api_wsl.sh`：不启动 Docker，仅检查 DeepSeek key 与模型可用性；
- `run_paired_mvp_wsl.sh`：复用一条已验证 T1 经验，以统一入口运行 No Artifact、Normalized Episodic、Procedural 三路同源 T4 比较；
- `baseline_manifest.yaml`：实验条件与创新边界。

## WSL 环境准备

运行代码、虚拟环境和实验结果位于 WSL 原生文件系统：

```text
/home/posture627ka/workspaces/skillevolbench-baseline/
```

Windows 目录仅保存论文材料、配置模板和启动脚本，避免 Git、pip 和 benchmark 的密集 I/O 经过 `/mnt/c`。

在 Ubuntu WSL 中进入本目录，执行：

```bash
./setup_wsl_env.sh
./install_docker_wsl.sh
```

第二条命令会由 Ubuntu 请求 `sudo` 密码。安装后刷新用户组并构建任务镜像：

```bash
newgrp docker
docker run --rm hello-world
bash ./build_agent_runtime_wsl.sh
```

上游版本仍固定在指定 commit；运行入口会同步三项可审计的本地工程修复。Agent runtime 的 OpenClaw 兼容改动只发生在临时构建副本中。

复制 `.harbor-agents.env.example` 为 `.harbor-agents.env`，只填写一个模型提供商，并在运行前加载：

```bash
set -a
source .harbor-agents.env
set +a
```

### Direct Anthropic Claude

将 Anthropic Console 的 key 写入本地 `.harbor-agents.env`：

```bash
ANTHROPIC_API_KEY=your_key_here
```

本地 overlay preset 为 `claude-sonnet-4.6-direct`；现有 Claude presets 仍使用
AWS Bedrock。先用同一 Claude model 重新生成 T1 source：

```bash
bash ./run_smoke_wsl.sh \
  --baseline-name no_skill \
  --model-preset claude-sonnet-4.6-direct \
  --order-seed A \
  --max-tasks 1
```

随后将输出的 Claude smoke run 路径显式传给 paired MVP：

```bash
bash ./run_paired_mvp_wsl.sh \
  --source-run-dir /absolute/path/to/claude_smoke_run \
  --model-preset claude-sonnet-4.6-direct \
  --mvp-id paired_claude_sonnet46_E1LS1T1_T4_mvp01 \
  --conditions all \
  --skip-ledger \
  --author-max-tokens 4096 \
  --confirm-run
```

paired runner 默认拒绝 source/target Agent model 不一致；只有显式传入
`--allow-cross-model-source` 才允许跨模型 source。

### ANU Claude gateway

ANU 提供的 `sk-...` course key 通过仅限 ANU 网络/VPN 的 strproxy 使用。
本项目沿用 `.harbor-agents.env` 中已有的 Claude key，不把它发送到
Anthropic 官方端点。启动脚本会将它映射为 `ANTHROPIC_AUTH_TOKEN`，并使用：

```text
ANTHROPIC_BASE_URL=https://strproxy.comp.anu.edu.au
ANTHROPIC_MODEL=claude-sonnet-5
```

最低成本 smoke test：

```bash
bash ./run_smoke_wsl.sh \
  --baseline-name no_skill \
  --model-preset claude-sonnet-5-anu \
  --order-seed A \
  --max-tasks 1
```

### DeepSeek V4 Flash

在 `.harbor-agents.env` 中填写 DeepSeek 官方 API key：

```bash
DEEPSEEK_API_BASE=https://api.deepseek.com
DEEPSEEK_API_KEY=your_key_here
```

`deepseek-v4-flash` preset 固定使用 Claude Code 作为容器内 Harness，并让宿主侧
SkillAuthor 使用同一个 DeepSeek 模型。先执行无推理任务的凭据检查：

```bash
bash ./check_deepseek_api_wsl.sh
```

随后用固定的三次上限获取第一条完全通过 outcome 与 process verifier 的同模型 T1 source。可将已有同配置 smoke 计为第一次尝试：

```bash
bash ./run_acquisition_policy_wsl.sh \
  --model-preset deepseek-v4-flash \
  --order-seed A \
  --max-attempts 3 \
  --existing-run-dir /absolute/path/to/existing_deepseek_smoke_run
```

脚本会生成 `acquisition_ledger.json` 和 `selected_source.json`。将后者记录的 source 目录传给 paired MVP：

```bash
bash ./run_paired_mvp_wsl.sh \
  --source-run-dir /absolute/path/to/deepseek_smoke_run \
  --model-preset deepseek-v4-flash \
  --mvp-id paired_deepseek_v4_flash_E1LS1T1_T4_mvp01 \
  --conditions all \
  --skip-ledger \
  --author-max-tokens 4096 \
  --confirm-run
```

## 使用

在当前目录打开 PowerShell。

仅检查配置、任务资产和运行依赖：

```powershell
.\run_baseline.ps1 -Mode check
```

对三个条件执行 dry-run，不调用模型：

```powershell
.\run_baseline.ps1 -Mode dry-run -ModelPreset gpt-5.4 -OrderSeed A
```

WSL 等价命令：

```bash
./run_baseline_wsl.sh check
./run_baseline_wsl.sh dry-run gpt-5.4 A
```

首次真实调用先运行单任务 smoke test：

```bash
bash ./run_smoke_wsl.sh --model-preset gemini-3-flash --max-tasks 1
```

Smoke test 只验证运行链路，不作为论文结果。

同源 paired MVP 先执行 dry-run：

```bash
bash ./run_paired_mvp_wsl.sh --dry-run
```

确认 source evidence 和目标任务后，执行三个隔离分支：

```bash
bash ./run_paired_mvp_wsl.sh \
  --mvp-id paired_gemini_flash_E1LS1T1_T4_mvp01 \
  --conditions all \
  --skip-ledger \
  --author-max-tokens 4096 \
  --confirm-run
```

如果运行中断，复用已完成的分支与 Procedural artifact：

```bash
bash ./run_paired_mvp_wsl.sh \
  --mvp-id paired_gemini_flash_E1LS1T1_T4_mvp01 \
  --conditions all \
  --skip-ledger \
  --author-max-tokens 4096 \
  --resume \
  --confirm-run
```

`--conditions` 可选择一个或多个分支；不完整的旧分支不会被覆盖，而会使用
`__retryN` 目录。`--skip-ledger` 只跳过分析侧语义审计，不影响三路 verifier
结果；主要结果完成后可通过 `--resume` 去掉该选项，单独补充 Ledger。

分支只有在 Harbor `result.json` 中不存在 Agent exception 时才会成为 completed
checkpoint。API quota、鉴权、网络和 Agent timeout 即使仍产生 verifier 分数，也会
写入 `paired_branch_failure.json`、停止后续分支，并由 `--resume` 重新执行；此类分数
不能作为研究结果。

默认复用最新成功的 `E1-LS1-T1` smoke trajectory，并只评估
`E1-LS1-T4`。结果写入 WSL 的 `SkillEvolBench/workspace/paired_mvp/`。
该运行不会重新执行 acquisition，而是定位 trial 中真正的 ATIF
`agent/trajectory.json`，仅删除时间戳、模型名和 token accounting 等传输字段，
保留完整事件顺序与语义内容。Episodic 与 Procedural 使用同一个 canonical
source packet；SkillAuthor 的默认输入截断在此 MVP 中被移除。

三路执行均使用 `no_skill` execution baseline。Episodic event stream 和生成后的
`SKILL.md` 通过完全相同的 `Prior Experience Artifact` prompt wrapper 进入 Agent；
不启用 trajectory retrieval、skill retrieval 或 native skill mount 内容，从而避免
access channel 与 representation form 混杂。输出还包括：

- `normalized_source_evidence.json`：带稳定 ID 的 source evidence units；
- `target_demand_card.json`：在生成 Procedural representation 前冻结显式目标需求，
  并将行为要求与路径提示分开；
- `abstraction_delta_ledger.json`：source units、procedural spans 与 target demands
  的事后对齐及 source-unit 标注覆盖率。模型生成的语义标注只作为 provisional
  audit，必须人工复核，且不会暴露给任务执行 Agent。

安装 Docker、Harbor 并配置模型凭据后，执行官方全量 baseline：

```powershell
.\run_baseline.ps1 -Mode run -ModelPreset gpt-5.4 -OrderSeed A -ConfirmFullRun
```

WSL 真实结果写入 `/home/posture627ka/workspaces/skillevolbench-baseline/SkillEvolBench/workspace/runs/`。Windows 入口显式启用 Python UTF-8 模式，避免默认 GBK 读取仓库 UTF-8 文件时失败。

## 解释边界

官方 baseline 的作用是确认上游三条件能够运行；因为它们分别执行 acquisition，
不能单独支撑 representation-effect 结论。paired MVP 解决了逐条同源与 delivery
一致性，但目前仍然只有一个 source、一个 target，属于诊断结果而非统计证据。

Abstraction Delta Ledger 的自动语义映射不能代替独立人工标注；隐藏 verifier 中
未写入任务指令的需求也不会被自动加入 target demand card。

## 当前状态

WSL 原生 Python 环境、Docker Engine 和 `agent-runtime:latest` 已就绪；严格 preflight 通过。三个条件的 dry-run 分别生成 180、270、270 个任务。实际依赖版本记录在 `runtime_versions.txt`。
