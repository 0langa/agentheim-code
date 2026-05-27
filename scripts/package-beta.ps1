param(
    [string]$PythonExe = "python"
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$venvRoot = Join-Path $env:TEMP "agentheim-code-wheel-smoke"
$projectVersion = Select-String -Path (Join-Path $repoRoot "pyproject.toml") -Pattern '^version = "([^"]+)"' |
    Select-Object -First 1 |
    ForEach-Object { $_.Matches[0].Groups[1].Value }

if (-not $projectVersion) {
    throw "Could not read project version from pyproject.toml"
}

function Invoke-Step([string]$Label, [scriptblock]$Action) {
    Write-Host ""
    Write-Host "==> $Label" -ForegroundColor Cyan
    & $Action
}

Push-Location $repoRoot
try {
    Invoke-Step "Clean prior build artifacts" {
        foreach ($path in @("build", "dist", "src/agentheim_code.egg-info")) {
            $target = Join-Path $repoRoot $path
            if (Test-Path $target) {
                Remove-Item -LiteralPath $target -Recurse -Force
            }
        }
    }

    Invoke-Step "Build web assets" {
        & npm --prefix apps/web run build
    }

    Invoke-Step "Build Windows desktop installer" {
        & npm --prefix apps/desktop run build
    }

    Invoke-Step "Build wheel" {
        & $PythonExe -m build --wheel
    }

    Invoke-Step "Create clean smoke venv" {
        if (Test-Path $venvRoot) {
            Remove-Item -LiteralPath $venvRoot -Recurse -Force
        }
        & $PythonExe -m venv $venvRoot
    }

    $venvPython = Join-Path $venvRoot "Scripts\\python.exe"
    $venvAgentheim = Join-Path $venvRoot "Scripts\\agentheim-code.exe"
    $wheelPath = Get-ChildItem -Path (Join-Path $repoRoot "dist\\*.whl") |
        Sort-Object LastWriteTime -Descending |
        Select-Object -First 1 -ExpandProperty FullName

    if (-not $wheelPath) {
        throw "No built wheel found under dist\\"
    }

    Invoke-Step "Sync wheel into desktop backend interpreter" {
        & $PythonExe -m pip install --force-reinstall --no-deps $wheelPath
    }

    Invoke-Step "Install wheel into clean venv" {
        & $venvPython -m pip install --upgrade pip
        & $venvPython -m pip install $wheelPath
    }

    Invoke-Step "Run clean wheel smoke" {
        & $venvAgentheim --help
        $modelsJson = & $venvAgentheim models --json
        if ($LASTEXITCODE -ne 0) {
            throw "agentheim-code models --json failed"
        }
        $modelsJson | ConvertFrom-Json | Out-Null
        & $venvPython -c "from agentheim_code.backend import create_app; create_app('.')"
    }

    Invoke-Step "Locate NSIS installer" {
        $installers = Get-ChildItem -Path "apps/desktop/src-tauri/target/release/bundle/nsis/*.exe" |
            Where-Object { $_.Name -like "*_$projectVersion*_setup.exe" -or $_.Name -like "*_$projectVersion*_x64-setup.exe" }

        if (-not $installers) {
            throw "No NSIS installer found for version $projectVersion"
        }

        $installers |
            Select-Object FullName, Length, LastWriteTime |
            Format-Table -AutoSize
    }
}
finally {
    Pop-Location
}
