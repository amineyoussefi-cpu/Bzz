# Install (first run) and start the OpenJev decision service on Windows + NVIDIA.
# Usage (PowerShell, from the repository):  .\decision\start.ps1
# Reads ..\.env if present; every OPENJEV_* variable is optional (see .env.example).
# TORCH_CUDA picks the CUDA build of torch: cu126 by default, cu130 for RTX 50xx (compute capability 12.x).
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (Test-Path ..\.env) {
    foreach ($line in Get-Content ..\.env) {
        if ($line -match '^\s*([A-Z_][A-Z0-9_]*)\s*=\s*(.*?)\s*$' -and $Matches[2] -ne '') {
            [Environment]::SetEnvironmentVariable($Matches[1], $Matches[2], "Process")
        }
    }
}

$python = if ($env:PYTHON) { $env:PYTHON } else { "py" }
$venvPy = ".venv\Scripts\python.exe"

if (-not (Test-Path $venvPy)) {
    Write-Host "Creating the decision service environment (decision\.venv)..."
    if ($python -eq "py") { & py -3 -m venv .venv } else { & $python -m venv .venv }
    if ($LASTEXITCODE -ne 0) { throw "Python 3.10+ is required (https://www.python.org/downloads/)" }

    $cuda = $env:TORCH_CUDA
    if (-not $cuda) {
        $cap = (& nvidia-smi --query-gpu=compute_cap --format=csv,noheader 2>$null | Select-Object -First 1)
        $cuda = if ($cap -and [double]$cap -ge 12) { "cu130" } else { "cu126" }
    }
    Write-Host "Installing torch 2.14.1 for CUDA ($cuda)..."
    & $venvPy -m pip install --quiet --disable-pip-version-check torch==2.14.1 --index-url "https://download.pytorch.org/whl/$cuda"
    if ($LASTEXITCODE -ne 0) { throw "torch installation failed" }
}
& $venvPy -m pip install --quiet --disable-pip-version-check -r requirements.txt
if ($LASTEXITCODE -ne 0) { throw "dependency installation failed" }

& $venvPy service.py
