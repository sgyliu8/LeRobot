# Shared exclusive lock for installation/update and the supported start path.
function Enter-WorkbenchLock {
    param([Parameter(Mandatory)][string]$Root)
    $runtime = [IO.Path]::GetFullPath((Join-Path $Root '.local\runtime'))
    foreach ($candidate in @($Root, (Join-Path $Root '.local'), $runtime, (Join-Path $runtime 'maintenance.lock'))) {
        if (Test-Path -LiteralPath $candidate) {
            if (((Get-Item -LiteralPath $candidate -Force).Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
                throw "Maintenance path crosses a reparse point: $candidate"
            }
        }
    }
    New-Item -ItemType Directory -Force -Path $runtime | Out-Null
    try {
        return [IO.File]::Open((Join-Path $runtime 'maintenance.lock'),
            [IO.FileMode]::OpenOrCreate, [IO.FileAccess]::ReadWrite, [IO.FileShare]::None)
    }
    catch { throw 'Another setup, update or start is running. Wait for it to finish.' }
}
