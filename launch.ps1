param(
    [ValidateSet('1','2','3')]
    [string]$Mode = '',
    [switch]$CheckOnly,
    [switch]$NoPrompts,
    [switch]$Fast
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Invoke-Checked([string]$FilePath, [string[]]$ArgumentList) {
    & $FilePath @ArgumentList | Out-Default
    if ($LASTEXITCODE -ne 0) {
        $argsText = ($ArgumentList -join ' ')
        throw "Command failed (exit $LASTEXITCODE): $FilePath $argsText"
    }
}

function Resolve-RepoRoot {
    if ($PSScriptRoot) {
        return $PSScriptRoot
    }
    if ($PSCommandPath) {
        return (Split-Path -Parent $PSCommandPath)
    }
    $def = $MyInvocation.MyCommand.Definition
    if (-not $def) {
        throw 'Unable to resolve script path.'
    }
    return (Split-Path -Parent $def)
}

function Test-CommandExists([string]$Name) {
    try {
        $null = Get-Command $Name -ErrorAction Stop
        return $true
    } catch {
        return $false
    }
}

function Wait-HttpReady([string]$Url, [int]$TimeoutSeconds = 20) {
    $deadline = (Get-Date).AddSeconds([Math]::Max(1, $TimeoutSeconds))
    while ((Get-Date) -lt $deadline) {
        try {
            $resp = $null
            try {
                $resp = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 2
            } catch {
                $resp = Invoke-WebRequest -Uri $Url -TimeoutSec 2
            }
            if ($null -ne $resp -and $resp.StatusCode -ge 200 -and $resp.StatusCode -lt 500) {
                return $true
            }
        } catch {
        }
        Start-Sleep -Milliseconds 250
    }
    return $false
}

function Assert-File([string]$Path, [string]$Message) {
    if (-not (Test-Path -LiteralPath $Path)) {
        throw $Message
    }
}

function Select-ShellExe {
    if (Test-CommandExists 'pwsh') { return 'pwsh.exe' }
    if (Test-CommandExists 'powershell') { return 'powershell.exe' }
    throw 'Neither pwsh nor powershell was found in PATH.'
}

function Get-VenvPython([string]$RepoRoot) {
    $py = Join-Path $RepoRoot '4t\Scripts\python.exe'
    Assert-File $py "Python venv not found: $py  (expected venv folder: 4t)"
    return $py
}

function Test-PipPackage([string]$PythonExe, [string]$PackageName) {
    $pkg = $PackageName
    if ($null -eq $pkg) { $pkg = '' }
    $pkg = $pkg.Trim()
    if (-not $pkg) { return }

    $p = Start-Process -FilePath $PythonExe -ArgumentList @('-m', 'pip', 'show', $pkg) -NoNewWindow -PassThru -Wait
    if ($p.ExitCode -ne 0) {
        if ($NoPrompts) {
            throw "Missing python package '$pkg' in venv. Install with: `"$PythonExe -m pip install -r requirements.txt`""
        }
        Write-Host "Missing python package '$pkg' in venv." -ForegroundColor Yellow
        $ans = Read-Host "Run pip install -r requirements.txt now? (y/N)"
        if ($ans -match '^(y|yes)$') {
            Invoke-Checked -FilePath $PythonExe -ArgumentList @('-m', 'pip', 'install', '-r', 'requirements.txt')
        } else {
            throw "Missing python package '$pkg' in venv. Install with: `"$PythonExe -m pip install -r requirements.txt`""
        }
    }
}

function Test-PythonImports([string]$PythonExe, [string[]]$Imports) {
    $parts = @()
    foreach ($i in $Imports) {
        $s = $i
        if ($null -eq $s) { $s = '' }
        $s = $s.Trim()
        if ($s) { $parts += "import $s" }
    }
    if ($parts.Count -eq 0) { return }

    $code = ($parts -join '; ')
    Invoke-Checked -FilePath $PythonExe -ArgumentList @('-c', $code)
}

function Validate-Python([string]$RepoRoot) {
    Write-Host "[1/4] Validating Python environment (4t)..." -ForegroundColor Cyan

    $pythonExe = Get-VenvPython -RepoRoot $RepoRoot
    Assert-File (Join-Path $RepoRoot 'requirements.txt') "requirements.txt not found in repo root."

    Invoke-Checked -FilePath $pythonExe -ArgumentList @('-c', 'import sys; print(sys.version)')
    Invoke-Checked -FilePath $pythonExe -ArgumentList @('-m', 'pip', '--version')

    if ($Fast) {
        Write-Host "Fast mode: skipping pip package checks." -ForegroundColor DarkYellow
        Test-PythonImports -PythonExe $pythonExe -Imports @('fastapi', 'uvicorn', 'requests')
        Write-Host "Python environment OK (fast)." -ForegroundColor Green
        return $pythonExe
    }

    $reqs = Get-Content -LiteralPath (Join-Path $RepoRoot 'requirements.txt')
    foreach ($line in $reqs) {
        $t = $line
        if ($null -eq $t) { $t = '' }
        $t = $t.Trim()
        if (-not $t) { continue }
        if ($t.StartsWith('#')) { continue }
        Test-PipPackage -PythonExe $pythonExe -PackageName $t
    }

    Write-Host "Running pip check..." -ForegroundColor DarkCyan
    Invoke-Checked -FilePath $pythonExe -ArgumentList @('-m', 'pip', 'check')

    Test-PythonImports -PythonExe $pythonExe -Imports @('fastapi', 'uvicorn', 'requests', 'pandas', 'freqtrade')
    Test-PythonImports -PythonExe $pythonExe -Imports @('PyQt6')
    Test-PythonImports -PythonExe $pythonExe -Imports @('tkinter')

    Write-Host "Python environment OK." -ForegroundColor Green
    return $pythonExe
}

function Validate-Node([string]$RepoRoot) {
    Write-Host "[2/4] Validating Node/NPM (web client)..." -ForegroundColor Cyan

    if (-not (Test-CommandExists 'node')) {
        throw 'Node.js not found in PATH.'
    }
    if (-not (Test-CommandExists 'npm')) {
        throw 'npm not found in PATH.'
    }

    $clientDir = Join-Path $RepoRoot 'client'
    Assert-File $clientDir "client/ directory not found at: $clientDir"
    Assert-File (Join-Path $clientDir 'package.json') "client/package.json not found."

    Invoke-Checked -FilePath 'node' -ArgumentList @('--version')
    Invoke-Checked -FilePath 'npm' -ArgumentList @('--version')

    $nodeModules = Join-Path $clientDir 'node_modules'
    if (-not (Test-Path -LiteralPath $nodeModules)) {
        if ($NoPrompts) {
            throw 'Web dependencies are missing (node_modules). Run: npm --prefix client install'
        }
        Write-Host "node_modules not found. The web UI cannot start until you run npm install." -ForegroundColor Yellow
        $ans = Read-Host "Run npm install now? (y/N)"
        if ($ans -match '^(y|yes)$') {
            Invoke-Checked -FilePath 'npm' -ArgumentList @('--prefix', $clientDir, 'install')
        } else {
            throw 'Web dependencies are missing (node_modules).'
        }
    }

    if ($Fast) {
        Write-Host "Fast mode: skipping npm dependency tree check." -ForegroundColor DarkYellow
        Write-Host "Node/NPM environment OK (fast)." -ForegroundColor Green
        return $clientDir
    }

    Write-Host "Running npm ls (dependency check)..." -ForegroundColor DarkCyan
    Invoke-Checked -FilePath 'npm' -ArgumentList @('--prefix', $clientDir, 'ls', '--depth=0')

    Write-Host "Node/NPM environment OK." -ForegroundColor Green
    return $clientDir
}

function Show-Menu {
    Write-Host "" 
    Write-Host "Select UI mode:" -ForegroundColor Cyan
    Write-Host "  1) TK (Tkinter)" 
    Write-Host "  2) GUI (PyQt6)" 
    Write-Host "  3) Web GUI (FastAPI + Vite)" 
    return (Read-Host "Enter 1, 2, or 3")
}

function Start-NewTerminal([string]$ShellExe, [string]$Title, [string]$Command) {
    $cmd = "`$Host.UI.RawUI.WindowTitle = '$Title'; $Command"
    Start-Process -FilePath $ShellExe -ArgumentList @('-NoExit', '-Command', $cmd) | Out-Null
}

function Launch-Tk([string]$ShellExe, [string]$RepoRoot, [string]$PythonExe) {
    Write-Host "[4/4] Launching Tkinter UI..." -ForegroundColor Cyan
    $script = Join-Path $RepoRoot 'ui\tk\main_tk.py'
    Assert-File $script "Tk UI entrypoint not found: $script"

    $cmd = "Set-Location `"$RepoRoot`"; & `"$PythonExe`" `"$script`""
    Start-NewTerminal -ShellExe $ShellExe -Title 'SmartTrade TK' -Command $cmd
}

function Launch-PyQt([string]$ShellExe, [string]$RepoRoot, [string]$PythonExe) {
    Write-Host "[4/4] Launching PyQt6 UI..." -ForegroundColor Cyan
    $script = Join-Path $RepoRoot 'main.py'
    Assert-File $script "PyQt6 UI entrypoint not found: $script"

    $cmd = "Set-Location `"$RepoRoot`"; & `"$PythonExe`" `"$script`""
    Start-NewTerminal -ShellExe $ShellExe -Title 'SmartTrade PyQt6' -Command $cmd
}

function Launch-Web([string]$ShellExe, [string]$RepoRoot, [string]$PythonExe, [string]$ClientDir) {
    Write-Host "[4/4] Launching Web UI (backend + frontend)..." -ForegroundColor Cyan

    $api = Join-Path $RepoRoot 'web_api.py'
    Assert-File $api "Web API entrypoint not found: $api"

    $backendCmd = "Set-Location `"$RepoRoot`"; & `"$PythonExe`" -m uvicorn web_api:app --host 127.0.0.1 --port 8000"
    $frontendCmd = "Set-Location `"$RepoRoot`"; npm --prefix `"$ClientDir`" run dev"

    $backendAlready = Wait-HttpReady -Url "http://127.0.0.1:8000/api/health" -TimeoutSeconds 1
    if ($backendAlready) {
        Write-Host "Backend already running: http://127.0.0.1:8000" -ForegroundColor DarkGreen
    } else {
        Start-NewTerminal -ShellExe $ShellExe -Title 'SmartTrade Web Backend' -Command $backendCmd
    }

    $frontendAlready = Wait-HttpReady -Url "http://127.0.0.1:5173/" -TimeoutSeconds 1
    if ($frontendAlready) {
        Write-Host "Frontend already running: http://127.0.0.1:5173" -ForegroundColor DarkGreen
    } else {
        Start-NewTerminal -ShellExe $ShellExe -Title 'SmartTrade Web Frontend' -Command $frontendCmd
    }

    try {
        $backendOk = Wait-HttpReady -Url "http://127.0.0.1:8000/api/health" -TimeoutSeconds 25
        if (-not $backendOk) {
            Write-Host "Backend not ready yet (http://127.0.0.1:8000). Opening browser anyway." -ForegroundColor Yellow
        }

        $frontendOk = Wait-HttpReady -Url "http://127.0.0.1:5173/" -TimeoutSeconds 25
        if (-not $frontendOk) {
            Write-Host "Frontend not ready yet (http://127.0.0.1:5173). Opening browser anyway." -ForegroundColor Yellow
        }

        Start-Process "http://127.0.0.1:5173/" | Out-Null
        Start-Process "http://127.0.0.1:8000/docs" | Out-Null
    } catch {
        return
    }
}

$repoRoot = Resolve-RepoRoot
Set-Location -LiteralPath $repoRoot

Write-Host "SmartTrade Launcher" -ForegroundColor Green
Write-Host "Repo: $repoRoot" -ForegroundColor DarkGray

$shellExe = Select-ShellExe
$pythonExe = Validate-Python -RepoRoot $repoRoot

$choice = $Mode
if (-not $choice) {
    $choice = Show-Menu
}

if ($CheckOnly) {
    if ($choice -eq '3') {
        $null = Validate-Node -RepoRoot $repoRoot
    }
    Write-Host "Validation complete. Ready to launch." -ForegroundColor Green
    exit 0
}

switch ($choice) {
    '1' {
        Launch-Tk -ShellExe $shellExe -RepoRoot $repoRoot -PythonExe $pythonExe
        break
    }
    '2' {
        Launch-PyQt -ShellExe $shellExe -RepoRoot $repoRoot -PythonExe $pythonExe
        break
    }
    '3' {
        $clientDir = Validate-Node -RepoRoot $repoRoot
        Launch-Web -ShellExe $shellExe -RepoRoot $repoRoot -PythonExe $pythonExe -ClientDir $clientDir
        break
    }
    default {
        throw "Invalid selection: '$choice'"
    }
}

Write-Host "Done." -ForegroundColor Green
