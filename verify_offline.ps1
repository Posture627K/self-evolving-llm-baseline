$ErrorActionPreference = 'Stop'
& python -B -X utf8 (Join-Path $PSScriptRoot 'verify_snapshot.py')
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
