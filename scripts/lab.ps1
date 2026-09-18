[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [ValidateSet('start', 'status', 'logs', 'stop')]
    [string]$Action = 'status',

    [ValidateRange(1, 1000)]
    [int]$Tail = 80
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$projectRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$runtimeRoot = [IO.Path]::GetFullPath((Join-Path $projectRoot '.local\runtime'))
$logRoot = [IO.Path]::GetFullPath((Join-Path $projectRoot '.local\logs'))
$recordingEvidenceRoot = [IO.Path]::GetFullPath((Join-Path $projectRoot '.local\evidence\recordings'))
$statePath = [IO.Path]::GetFullPath((Join-Path $runtimeRoot 'lelab-process.json'))
$pythonExe = [IO.Path]::GetFullPath((Join-Path $projectRoot '.venv\Scripts\python.exe'))
$healthUrl = 'http://127.0.0.1:8000/health'
$runtimeStatusUrl = 'http://127.0.0.1:8000/lab-runtime-status'
$shutdownFenceUrl = 'http://127.0.0.1:8000/lab-shutdown-fence'

function Test-ContainedPath {
    param(
        [Parameter(Mandatory)][string]$Root,
        [Parameter(Mandatory)][string]$Candidate
    )

    $resolvedRoot = [IO.Path]::GetFullPath($Root).TrimEnd(
        [IO.Path]::DirectorySeparatorChar,
        [IO.Path]::AltDirectorySeparatorChar
    )
    $resolvedCandidate = [IO.Path]::GetFullPath($Candidate)
    $prefix = "$resolvedRoot$([IO.Path]::DirectorySeparatorChar)"
    return (
        $resolvedCandidate.Equals($resolvedRoot, [StringComparison]::OrdinalIgnoreCase) -or
        $resolvedCandidate.StartsWith($prefix, [StringComparison]::OrdinalIgnoreCase)
    )
}

function Assert-NoReparsePath {
    param(
        [Parameter(Mandatory)][string]$Root,
        [Parameter(Mandatory)][string]$Candidate
    )

    if (-not (Test-ContainedPath -Root $Root -Candidate $Candidate)) {
        throw "Resolved path escaped the project root: $Candidate"
    }
    $resolvedRoot = [IO.Path]::GetFullPath($Root).TrimEnd(
        [IO.Path]::DirectorySeparatorChar,
        [IO.Path]::AltDirectorySeparatorChar
    )
    $resolvedCandidate = [IO.Path]::GetFullPath($Candidate)
    $current = $resolvedRoot
    if (Test-Path -LiteralPath $current) {
        $rootItem = Get-Item -LiteralPath $current -Force
        if (($rootItem.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
            throw "Project path crosses a reparse point: $current"
        }
    }
    $relative = $resolvedCandidate.Substring($resolvedRoot.Length).TrimStart(
        [IO.Path]::DirectorySeparatorChar,
        [IO.Path]::AltDirectorySeparatorChar
    )
    if (-not $relative) { return }
    foreach ($part in $relative.Split(@(
                [IO.Path]::DirectorySeparatorChar,
                [IO.Path]::AltDirectorySeparatorChar
            ), [StringSplitOptions]::RemoveEmptyEntries)) {
        $current = Join-Path $current $part
        if (-not (Test-Path -LiteralPath $current)) { break }
        $item = Get-Item -LiteralPath $current -Force
        if (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
            throw "Project path crosses a reparse point: $current"
        }
    }
}

foreach ($scopedPath in @($runtimeRoot, $logRoot, $recordingEvidenceRoot, $statePath, $pythonExe)) {
    if (-not (Test-ContainedPath -Root $projectRoot -Candidate $scopedPath)) {
        throw "Resolved path escaped the project root: $scopedPath"
    }
    Assert-NoReparsePath -Root $projectRoot -Candidate $scopedPath
}

function Read-ProcessState {
    if (-not (Test-Path -LiteralPath $statePath)) {
        return $null
    }
    Assert-NoReparsePath -Root $projectRoot -Candidate $statePath
    try {
        $state = Get-Content -LiteralPath $statePath -Raw | ConvertFrom-Json
    }
    catch {
        throw "Invalid project process state at $statePath. Inspect it before retrying."
    }

    $required = @(
        'schema_version', 'pid', 'start_filetime_utc', 'executable',
        'project_root', 'port', 'stdout_log', 'stderr_log'
    )
    foreach ($name in $required) {
        if ($state.PSObject.Properties.Name -notcontains $name) {
            throw "Project process state failed ownership validation: missing $name."
        }
    }
    try {
        $recordedProjectRoot = [IO.Path]::GetFullPath([string]$state.project_root)
        $recordedExecutable = [IO.Path]::GetFullPath([string]$state.executable)
        $stdoutLog = [IO.Path]::GetFullPath([string]$state.stdout_log)
        $stderrLog = [IO.Path]::GetFullPath([string]$state.stderr_log)
        $validNumbers = (
            [int]$state.schema_version -eq 1 -and
            [int]$state.pid -gt 0 -and
            [int64]$state.start_filetime_utc -gt 0 -and
            [int]$state.port -eq 8000
        )
    }
    catch {
        throw 'Project process state failed ownership validation: invalid field type or path.'
    }
    if (-not $validNumbers -or
        -not $recordedProjectRoot.Equals($projectRoot, [StringComparison]::OrdinalIgnoreCase) -or
        -not $recordedExecutable.Equals($pythonExe, [StringComparison]::OrdinalIgnoreCase) -or
        -not (Test-ContainedPath -Root $logRoot -Candidate $stdoutLog) -or
        -not (Test-ContainedPath -Root $logRoot -Candidate $stderrLog) -or
        $stdoutLog -eq $stderrLog -or
        [IO.Path]::GetFileName($stdoutLog) -notlike 'lelab-*.stdout.log' -or
        [IO.Path]::GetFileName($stderrLog) -notlike 'lelab-*.stderr.log') {
        throw 'Project process state failed ownership validation; no process or log was accessed.'
    }
    Assert-NoReparsePath -Root $projectRoot -Candidate $stdoutLog
    Assert-NoReparsePath -Root $projectRoot -Candidate $stderrLog
    return $state
}

function Resolve-OwnedProcess {
    param([Parameter(Mandatory)]$State)

    $process = Get-Process -Id ([int]$State.pid) -ErrorAction SilentlyContinue
    if ($null -eq $process) {
        return $null
    }

    $actualStart = $process.StartTime.ToUniversalTime().ToFileTimeUtc()
    $actualPath = [IO.Path]::GetFullPath($process.Path)
    $recordedPath = [IO.Path]::GetFullPath([string]$State.executable)
    if ($actualStart -ne [int64]$State.start_filetime_utc -or
        -not $actualPath.Equals($recordedPath, [StringComparison]::OrdinalIgnoreCase)) {
        throw "PID $($State.pid) exists but does not match this project's recorded LeLab process."
    }
    if ($State.PSObject.Properties.Name -contains 'command_line') {
        $actualCommand = (Get-CimInstance Win32_Process -Filter "ProcessId=$($process.Id)").CommandLine
        if ($actualCommand -ne [string]$State.command_line) {
            throw "PID $($State.pid) command line does not match this project's recorded LeLab process."
        }
    }
    return $process
}

function Get-PortOwners {
    $listeners = @(Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue)
    return @($listeners | Select-Object -ExpandProperty OwningProcess -Unique)
}

function Invoke-LocalJson {
    param([Parameter(Mandatory)][string]$Uri)
    return Invoke-RestMethod -Uri $Uri -Method Get -TimeoutSec 3 -Proxy $null
}

function Invoke-LocalJsonPost {
    param(
        [Parameter(Mandatory)][string]$Uri,
        [object]$Body = $null
    )
    if ($null -eq $Body) {
        return Invoke-RestMethod -Uri $Uri -Method Post -TimeoutSec 3 -Proxy $null
    }
    return Invoke-RestMethod -Uri $Uri -Method Post -TimeoutSec 3 -Proxy $null `
        -ContentType 'application/json' -Body ($Body | ConvertTo-Json -Compress)
}

function Show-Status {
    $state = Read-ProcessState
    if ($null -eq $state) {
        $owners = @(Get-PortOwners)
        [pscustomobject]@{
            state = if ($owners.Count) { 'foreign_port_owner' } else { 'stopped' }
            port = 8000
            owning_pids = $owners
        } | ConvertTo-Json -Depth 4
        return
    }

    $process = Resolve-OwnedProcess -State $state
    if ($null -eq $process) {
        [pscustomobject]@{
            state = 'stale_state_file'
            recorded_pid = $state.pid
            state_file = $statePath
        } | ConvertTo-Json -Depth 4
        return
    }

    $owners = @(Get-PortOwners)
    $health = $null
    $mode = 'unknown'
    try {
        $health = Invoke-LocalJson -Uri $healthUrl
        $mode = (Invoke-LocalJson -Uri $runtimeStatusUrl).hardware_mode
    }
    catch {
        $health = @{ status = 'unavailable'; error = $_.Exception.Message }
    }
    [pscustomobject]@{
        state = if ($owners -contains $process.Id) { 'running' } else { 'process_without_listener' }
        pid = $process.Id
        started_at_utc = $state.started_at_utc
        executable = $state.executable
        url = 'http://127.0.0.1:8000/'
        hardware_mode = $mode
        health = $health
        stdout_log = $state.stdout_log
        stderr_log = $state.stderr_log
    } | ConvertTo-Json -Depth 6
}

switch ($Action) {
    'start' {
        if (-not (Test-Path -LiteralPath $pythonExe)) {
            throw "LeLab is not installed in the project environment. Run uv sync --frozen first."
        }

        New-Item -ItemType Directory -Force -Path $runtimeRoot, $logRoot, $recordingEvidenceRoot | Out-Null
        foreach ($createdPath in @($runtimeRoot, $logRoot, $recordingEvidenceRoot)) {
            Assert-NoReparsePath -Root $projectRoot -Candidate $createdPath
        }
        $state = Read-ProcessState
        if ($null -ne $state) {
            $existing = Resolve-OwnedProcess -State $state
            if ($null -ne $existing) {
                Show-Status
                break
            }
            Remove-Item -LiteralPath $statePath -Force
        }

        $owners = @(Get-PortOwners)
        if ($owners.Count) {
            $details = foreach ($ownerPid in $owners) {
                $owner = Get-Process -Id $ownerPid -ErrorAction SilentlyContinue
                [pscustomobject]@{ pid = $ownerPid; name = $owner.ProcessName; path = $owner.Path }
            }
            throw "Port 8000 is already owned by another process: $($details | ConvertTo-Json -Compress)."
        }

        $stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
        $stdoutLog = Join-Path $logRoot "lelab-$stamp.stdout.log"
        $stderrLog = Join-Path $logRoot "lelab-$stamp.stderr.log"
        $previousEvidenceRoot = $env:LELAB_RECORDING_EVIDENCE_ROOT
        try {
            $env:LELAB_RECORDING_EVIDENCE_ROOT = $recordingEvidenceRoot
            $process = Start-Process -FilePath $pythonExe -ArgumentList '-m', 'lelab.scripts.lelab', '--no-open' `
                -WorkingDirectory $projectRoot -RedirectStandardOutput $stdoutLog `
                -RedirectStandardError $stderrLog -WindowStyle Hidden -PassThru
        }
        finally {
            if ($null -eq $previousEvidenceRoot) {
                Remove-Item Env:LELAB_RECORDING_EVIDENCE_ROOT -ErrorAction SilentlyContinue
            }
            else {
                $env:LELAB_RECORDING_EVIDENCE_ROOT = $previousEvidenceRoot
            }
        }
        $process.Refresh()
        $state = [ordered]@{
            schema_version = 1
            pid = $process.Id
            started_at_utc = $process.StartTime.ToUniversalTime().ToString('o')
            start_filetime_utc = $process.StartTime.ToUniversalTime().ToFileTimeUtc()
            executable = [IO.Path]::GetFullPath($process.Path)
            project_root = $projectRoot
            port = 8000
            stdout_log = [IO.Path]::GetFullPath($stdoutLog)
            stderr_log = [IO.Path]::GetFullPath($stderrLog)
        }
        $state | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $statePath -Encoding utf8

        $ready = $false
        for ($attempt = 0; $attempt -lt 60; $attempt++) {
            Start-Sleep -Milliseconds 500
            if ($process.HasExited) {
                break
            }
            try {
                $response = Invoke-LocalJson -Uri $healthUrl
                if ($response.status -eq 'ok') {
                    $ready = $true
                    break
                }
            }
            catch {
            }
        }
        if (-not $ready) {
            if (-not $process.HasExited) {
                Stop-Process -Id $process.Id -Force
            }
            Remove-Item -LiteralPath $statePath -Force -ErrorAction SilentlyContinue
            throw "LeLab did not become ready. Inspect $stdoutLog and $stderrLog."
        }

        $owners = @(Get-PortOwners)
        if ($owners.Count -ne 1) {
            Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
            Remove-Item -LiteralPath $statePath -Force -ErrorAction SilentlyContinue
            throw "LeLab became healthy but port 8000 did not have exactly one owner."
        }
        $serverPid = [int]$owners[0]
        $serverCim = Get-CimInstance Win32_Process -Filter "ProcessId=$serverPid"
        if ($null -eq $serverCim -or
            ($serverPid -ne $process.Id -and [int]$serverCim.ParentProcessId -ne $process.Id)) {
            Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
            Remove-Item -LiteralPath $statePath -Force -ErrorAction SilentlyContinue
            throw "LeLab listener PID $serverPid is not the launched process or its direct child."
        }
        $serverProcess = Get-Process -Id $serverPid
        $state.pid = $serverPid
        $state.started_at_utc = $serverProcess.StartTime.ToUniversalTime().ToString('o')
        $state.start_filetime_utc = $serverProcess.StartTime.ToUniversalTime().ToFileTimeUtc()
        $state.executable = [IO.Path]::GetFullPath($serverProcess.Path)
        $state.command_line = [string]$serverCim.CommandLine
        $state.launcher_pid = $process.Id
        $state | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $statePath -Encoding utf8
        Show-Status
    }

    'status' {
        Show-Status
    }

    'logs' {
        $state = Read-ProcessState
        if ($null -ne $state) {
            $logPaths = @([string]$state.stdout_log, [string]$state.stderr_log)
        }
        else {
            $logPaths = @(Get-ChildItem -LiteralPath $logRoot -Filter 'lelab-*.log' -File -ErrorAction SilentlyContinue |
                    Sort-Object LastWriteTime -Descending | Select-Object -First 2 -ExpandProperty FullName)
        }
        if (-not $logPaths.Count) {
            Write-Output 'No project LeLab logs found.'
            break
        }
        foreach ($logPath in $logPaths) {
            Write-Output "===== $logPath ====="
            if (Test-Path -LiteralPath $logPath) {
                Get-Content -LiteralPath $logPath -Tail $Tail
            }
        }
    }

    'stop' {
        $state = Read-ProcessState
        if ($null -eq $state) {
            Write-Output 'Project LeLab is not running; no process state exists.'
            break
        }
        $process = Resolve-OwnedProcess -State $state
        if ($null -eq $process) {
            Remove-Item -LiteralPath $statePath -Force
            Write-Output 'Removed stale project process state; no process was stopped.'
            break
        }

        $fence = $null
        try {
            $fence = Invoke-LocalJsonPost -Uri $shutdownFenceUrl
            if (-not $fence.success -or [int]$fence.pid -ne $process.Id) {
                throw "Shutdown fence did not identify the recorded LeLab PID $($process.Id)."
            }
            $process = Resolve-OwnedProcess -State $state
            $owners = @(Get-PortOwners)
            if ($null -eq $process -or $owners.Count -ne 1 -or [int]$owners[0] -ne $process.Id) {
                throw 'Owned process identity or port ownership changed after the shutdown fence.'
            }
            Stop-Process -Id $process.Id -Force
            $exited = $process.WaitForExit(5000)
            if (-not $exited -or -not $process.HasExited) {
                throw "Owned LeLab PID $($process.Id) did not exit within 5 seconds; process state was preserved."
            }
            $remainingOwners = @(Get-PortOwners)
            if ($remainingOwners -contains $process.Id) {
                throw "Owned LeLab PID $($process.Id) still owns port 8000 after exit wait; process state was preserved."
            }
        }
        catch {
            if ($null -ne $fence -and $fence.fence_token) {
                try {
                    Invoke-LocalJsonPost -Uri "$shutdownFenceUrl/release" -Body @{ token = [string]$fence.fence_token } | Out-Null
                }
                catch {
                }
            }
            throw
        }
        Remove-Item -LiteralPath $statePath -Force
        [pscustomobject]@{
            state = 'stopped'
            pid = $process.Id
            note = 'Software process stopped under an atomic idle fence; this is not a torque-off guarantee.'
        } | ConvertTo-Json -Depth 4
    }
}
