[CmdletBinding()]
param(
    [ValidateSet("check", "dry-run", "run")]
    [string]$Mode = "check",

    [string]$ModelPreset = "gpt-5.4",

    [ValidateSet("A", "B", "C")]
    [string]$OrderSeed = "A",

    [string]$PythonCommand = "python",

    [switch]$ConfirmFullRun
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$baselineRoot = $PSScriptRoot
$repoRoot = Join-Path $baselineRoot "SkillEvolBench"
$localModelConfig = Join-Path $baselineRoot ("model_presets\{0}.yaml" -f $ModelPreset)
$upstreamModelConfig = Join-Path $repoRoot ("configs\models\{0}.yaml" -f $ModelPreset)
$modelConfig = if (Test-Path -LiteralPath $localModelConfig) {
    $localModelConfig
} else {
    $upstreamModelConfig
}
$conditions = @(
    "no_skill",
    "raw_trajectory_rag",
    "selfgen_experience_always"
)

if (-not (Test-Path -LiteralPath $repoRoot)) {
    throw "SkillEvolBench repository not found: $repoRoot"
}

if (-not (Test-Path -LiteralPath $modelConfig)) {
    $available = @(
        Get-ChildItem -LiteralPath (Join-Path $repoRoot "configs\models") -Filter "*.yaml"
        Get-ChildItem -LiteralPath (Join-Path $baselineRoot "model_presets") -Filter "*.yaml"
    ) | ForEach-Object { $_.BaseName } | Sort-Object -Unique
    throw "Unknown model preset '$ModelPreset'. Available presets: $($available -join ', ')"
}

function Invoke-BaselinePython {
    param([Parameter(Mandatory = $true)][string[]]$Arguments)

    & $PythonCommand -X utf8 @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed with exit code ${LASTEXITCODE}: $PythonCommand -X utf8 $($Arguments -join ' ')"
    }
}

Push-Location $repoRoot
try {
    Write-Host "[1/3] Validating benchmark configs..."
    Invoke-BaselinePython -Arguments @("-m", "scripts.validate_configs")

    Write-Host "[2/3] Validating benchmark assets..."
    Invoke-BaselinePython -Arguments @("-m", "scripts.validate_assets")

    Write-Host "[3/3] Checking runtime prerequisites..."
    Invoke-BaselinePython -Arguments @("-m", "scripts.preflight")

    if ($Mode -eq "check") {
        Write-Host "Baseline static checks completed."
        exit 0
    }

    if ($Mode -eq "run") {
        if (-not $ConfirmFullRun) {
            throw "A real run schedules 180-270 tasks per condition. Re-run with -ConfirmFullRun after configuring Docker, Harbor, and model credentials."
        }
        Invoke-BaselinePython -Arguments @("-m", "scripts.preflight", "--strict")
    }

    $timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
    foreach ($condition in $conditions) {
        $safeModel = $ModelPreset -replace '[^A-Za-z0-9_.-]', '-'
        $runId = "baseline__${condition}__${safeModel}__seed${OrderSeed}__${timestamp}"
        $arguments = @(
            "-m", "scripts.run",
            "--baseline-name", $condition,
            "--model-yaml", $modelConfig,
            "--order-seed", $OrderSeed,
            "--run-id", $runId
        )
        if ($Mode -eq "dry-run") {
            $arguments += "--dry-run"
        }

        Write-Host "Running condition: $condition"
        Invoke-BaselinePython -Arguments $arguments
    }
}
finally {
    Pop-Location
}
