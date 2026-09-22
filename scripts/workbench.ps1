[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [ValidateSet('menu', 'open', 'setup', 'update', 'check', 'status', 'logs', 'stop')]
    [string]$Action = 'menu'
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$projectRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$pythonExe = Join-Path $projectRoot '.venv\Scripts\python.exe'
$labScript = Join-Path $PSScriptRoot 'lab.ps1'
$checkScript = Join-Path $projectRoot 'tools\runtime_check.py'
$bootstrap = Join-Path $projectRoot 'tools\bootstrap_upstream.ps1'
. (Join-Path $PSScriptRoot 'maintenance.ps1')

function Invoke-Checked {
    param([string]$Program, [string[]]$Arguments)
    & $Program @Arguments
    if ($LASTEXITCODE -ne 0) { throw "$Program failed (exit $LASTEXITCODE). See the message above." }
}

function Assert-Idle {
    $status = & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $labScript status
    if ($LASTEXITCODE -ne 0) { throw 'Unable to verify workbench state; no files were changed.' }
    $state = ($status | Out-String | ConvertFrom-Json).state
    if ($state -notin @('stopped', 'stale_state_file', 'foreign_port_owner')) {
        throw 'Finish active work and use Stop before Setup or Update.'
    }
    if (Test-Path -LiteralPath $pythonExe) {
        Invoke-Checked $pythonExe @('-X', 'utf8', $checkScript, '--maintenance')
    }
}

function Install-Workbench {
    Assert-Idle
    foreach ($command in @('git', 'uv', 'node', 'npm.cmd')) {
        if (-not (Get-Command $command -ErrorAction SilentlyContinue)) {
            throw "Missing $command. Install the prerequisites in docs/GETTING_STARTED.md, then run Setup again."
        }
    }
    $nodeVersion = [version]((& node -p 'process.versions.node') | Select-Object -Last 1)
    if ($nodeVersion -lt [version]'22.13') { throw 'Node.js 22.13+ (24 LTS recommended) is required.' }
    # Check the existing source first. A changed patch needs a staged rebuild;
    # the previous checkout is archived only after the new build succeeds.
    $rebuild = $true
    try {
        & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $bootstrap -CheckOnly 2>$null | Out-Null
        $rebuild = $LASTEXITCODE -ne 0
    }
    catch { $rebuild = $true }
    $bootstrapArgs = @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', $bootstrap)
    if ($rebuild) { $bootstrapArgs += '-Rebuild' }
    Invoke-Checked 'powershell.exe' $bootstrapArgs
    $previousEnvironment = $env:UV_PROJECT_ENVIRONMENT
    try {
        $env:UV_PROJECT_ENVIRONMENT = Join-Path $projectRoot '.venv'
        Invoke-Checked 'uv' @('sync', '--frozen', '--no-active', '--project', $projectRoot,
            '--reinstall-package', 'lelab', '--reinstall-package', 'physicalai-so101-lab')
    }
    finally { $env:UV_PROJECT_ENVIRONMENT = $previousEnvironment }
    Invoke-Checked $pythonExe @('-X', 'utf8', $checkScript, '--record', '--compute')
    Write-Host 'Setup complete. Choose Open workbench.'
}

function Update-Workbench {
    $updateLock = Enter-WorkbenchLock -Root $projectRoot
    try {
    Assert-Idle
    $gitRoot = & git -C $projectRoot rev-parse --show-toplevel
    if ($LASTEXITCODE -ne 0 -or [IO.Path]::GetFullPath($gitRoot) -ne $projectRoot) {
        throw 'This folder is not the expected project Git root.'
    }
    $origin = & git -C $projectRoot remote get-url origin
    if ($origin -ne 'https://github.com/sgyliu8/LeRobot.git') { throw 'Unexpected origin; update refused.' }
    $changes = & git -C $projectRoot status --porcelain
    if ($changes) { throw 'Uncommitted files exist. Commit or preserve them before Update.' }
    $upstream = & git -C $projectRoot rev-parse --abbrev-ref --symbolic-full-name '@{u}'
    if ($LASTEXITCODE -ne 0 -or $upstream -notlike 'origin/*') { throw 'Configure an origin tracking branch first.' }
    Invoke-Checked 'git' @('-C', $projectRoot, 'fetch', 'origin')
    Invoke-Checked 'git' @('-C', $projectRoot, 'merge', '--ff-only', $upstream)
    }
    finally { $updateLock.Dispose() }
    # Use the updated setup script in a new interpreter rather than cached code.
    Invoke-Checked 'powershell.exe' @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', $PSCommandPath, 'setup')
}

function Invoke-Action {
    param([string]$Selected)
    Push-Location -LiteralPath $projectRoot
    try {
        switch ($Selected) {
            'open' {
                if (-not (Test-Path -LiteralPath $pythonExe)) { throw 'First use: choose Setup (2).' }
                Invoke-Checked 'powershell.exe' @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', $labScript, 'start')
                Start-Process 'http://127.0.0.1:8000/'
            }
            'setup' {
                $installLock = Enter-WorkbenchLock -Root $projectRoot
                try { Install-Workbench }
                finally { $installLock.Dispose() }
            }
            'update' { Update-Workbench }
            'check' {
                Write-Host "Project: $projectRoot"
                & git -C $projectRoot status --short --branch
                if (-not (Test-Path -LiteralPath $pythonExe)) { throw 'Environment missing. Choose Setup (2).' }
                Invoke-Checked $pythonExe @('-X', 'utf8', $checkScript, '--compute')
            }
            default { Invoke-Checked 'powershell.exe' @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', $labScript, $Selected) }
        }
    }
    finally { Pop-Location }
}

if ($Action -ne 'menu') {
    try { Invoke-Action $Action; exit 0 }
    catch { Write-Error $_; exit 1 }
}
while ($true) {
    Write-Host "`nPhysicalAI SO101 Lab"
    Write-Host "1 / Enter  Open workbench`n2  Setup / rebuild installed version`n3  Update current Git branch + Setup`n4  Check installation and compute`n5  Status`n6  Logs`n7  Stop idle workbench`n0  Exit"
    $choice = Read-Host 'Choose'
    if ($choice -eq '0') { break }
    $selected = @{ ''='open'; '1'='open'; '2'='setup'; '3'='update'; '4'='check'; '5'='status'; '6'='logs'; '7'='stop' }[$choice]
    if (-not $selected) { continue }
    try { Invoke-Action $selected }
    catch { Write-Host $_.Exception.Message -ForegroundColor Red }
}
