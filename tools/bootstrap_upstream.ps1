[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$projectRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$pinsPath = [IO.Path]::GetFullPath((Join-Path $projectRoot 'configs\upstream-pins.json'))

function Resolve-ProjectPath {
    param([Parameter(Mandatory)][string]$RelativePath)

    if ([IO.Path]::IsPathRooted($RelativePath)) {
        throw "Project path must be relative: $RelativePath"
    }
    $resolved = [IO.Path]::GetFullPath((Join-Path $projectRoot $RelativePath))
    $scopedRoot = $projectRoot.TrimEnd(
        [IO.Path]::DirectorySeparatorChar,
        [IO.Path]::AltDirectorySeparatorChar
    )
    $prefix = "$scopedRoot$([IO.Path]::DirectorySeparatorChar)"
    if (-not $resolved.Equals($scopedRoot, [StringComparison]::OrdinalIgnoreCase) -and
        -not $resolved.StartsWith($prefix, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Resolved path escaped the project root: $resolved"
    }
    return $resolved
}

function Assert-NoReparsePoint {
    param(
        [Parameter(Mandatory)][string]$TargetPath,
        [Parameter(Mandatory)][string]$Label
    )

    $resolved = [IO.Path]::GetFullPath($TargetPath)
    $scopedRoot = $projectRoot.TrimEnd(
        [IO.Path]::DirectorySeparatorChar,
        [IO.Path]::AltDirectorySeparatorChar
    )
    $prefix = "$scopedRoot$([IO.Path]::DirectorySeparatorChar)"
    if (-not $resolved.Equals($scopedRoot, [StringComparison]::OrdinalIgnoreCase) -and
        -not $resolved.StartsWith($prefix, [StringComparison]::OrdinalIgnoreCase)) {
        throw "$Label escaped the project root: $resolved"
    }

    $current = $scopedRoot
    if (Test-Path -LiteralPath $current) {
        $rootItem = Get-Item -LiteralPath $current -Force
        if (($rootItem.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
            throw "$Label crosses a reparse point: $current"
        }
    }
    $relative = $resolved.Substring($scopedRoot.Length).TrimStart(
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
            throw "$Label crosses a reparse point: $current"
        }
    }
}

function Assert-NoReparseTree {
    param(
        [Parameter(Mandatory)][string]$RootPath,
        [Parameter(Mandatory)][string]$Label
    )

    Assert-NoReparsePoint -TargetPath $RootPath -Label $Label
    if (-not (Test-Path -LiteralPath $RootPath -PathType Container)) { return }
    $pending = New-Object 'System.Collections.Generic.Stack[string]'
    $pending.Push([IO.Path]::GetFullPath($RootPath))
    while ($pending.Count -gt 0) {
        $current = $pending.Pop()
        foreach ($entryPath in [IO.Directory]::EnumerateFileSystemEntries($current)) {
            $entry = Get-Item -LiteralPath $entryPath -Force
            if (($entry.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
                throw "$Label contains a reparse point: $entryPath"
            }
            if ($entry.PSIsContainer) {
                $pending.Push($entry.FullName)
            }
        }
    }
}

Assert-NoReparsePoint -TargetPath $pinsPath -Label 'Upstream pin manifest'

try {
    $pins = Get-Content -LiteralPath $pinsPath -Raw | ConvertFrom-Json
    $upstreamUrl = [string]$pins.lelab.repository
    $upstreamCommit = [string]$pins.lelab.commit
    $patchSet = @($pins.patch_set)
}
catch {
    throw "Unable to read the authoritative upstream pin manifest at $pinsPath."
}
if (-not [Uri]::IsWellFormedUriString($upstreamUrl, [UriKind]::Absolute) -or
    -not $upstreamUrl.StartsWith('https://', [StringComparison]::OrdinalIgnoreCase)) {
    throw 'Pinned LeLab repository must be an absolute HTTPS URL.'
}
if ($upstreamCommit -notmatch '^[0-9a-f]{40}$') {
    throw 'Pinned LeLab commit must be a full lowercase Git object ID.'
}
if ($patchSet.Count -ne 1 -or -not ($patchSet[0] -is [string])) {
    throw 'The upstream pin manifest must name exactly one tracked patch.'
}
$vendorRoot = Resolve-ProjectPath -RelativePath '_vendor\lelab'
$patchPath = Resolve-ProjectPath -RelativePath ([string]$patchSet[0])
Assert-NoReparsePoint -TargetPath $patchPath -Label 'Tracked LeLab patch'
Assert-NoReparsePoint -TargetPath $vendorRoot -Label 'LeLab vendor checkout'
if (-not (Test-Path -LiteralPath $patchPath)) {
    throw "Tracked LeLab patch is missing: $patchPath"
}

function Assert-ExactPatchedSource {
    $expectedBlobs = @{}
    $currentPath = $null
    foreach ($line in Get-Content -LiteralPath $patchPath) {
        if ($line -match '^diff --git a/(.+) b/(.+)$') {
            $currentPath = $Matches[2]
            continue
        }
        if ($null -ne $currentPath -and $line -match '^index [0-9a-f]{40}\.\.([0-9a-f]{40})(?: [0-7]{6})?$') {
            # dist is a reviewed, packaged output in the patch, but it is not
            # source inventory: npm build below regenerates and verifies it.
            if (-not $currentPath.StartsWith('frontend/dist/', [StringComparison]::Ordinal)) {
                $expectedBlobs[$currentPath] = $Matches[1]
            }
        }
    }
    if (-not $expectedBlobs.Count) {
        throw 'Tracked LeLab patch does not contain full-index blob identities.'
    }

    $modified = @(git -C $vendorRoot diff --name-only HEAD -- . ':(exclude)frontend/dist')
    if ($LASTEXITCODE -ne 0) { throw 'Unable to inspect the patched LeLab worktree.' }
    $untracked = @(git -C $vendorRoot ls-files --others --exclude-standard -- . ':(exclude)frontend/dist')
    if ($LASTEXITCODE -ne 0) { throw 'Unable to inspect untracked LeLab source.' }
    $actualPaths = @($modified + $untracked | Sort-Object -Unique)
    $pathDifference = @(Compare-Object -ReferenceObject @($expectedBlobs.Keys | Sort-Object) `
            -DifferenceObject $actualPaths)
    if ($pathDifference.Count) {
        throw "Vendor source differs from the tracked patch inventory: $($pathDifference | ConvertTo-Json -Compress)."
    }

    foreach ($relative in $expectedBlobs.Keys) {
        $expected = [string]$expectedBlobs[$relative]
        $sourcePath = Join-Path $vendorRoot $relative
        if ($expected -eq [string]::new([char]'0', 40)) {
            if (Test-Path -LiteralPath $sourcePath) {
                throw "Patched source should be deleted but exists: $relative"
            }
            continue
        }
        if (-not (Test-Path -LiteralPath $sourcePath -PathType Leaf)) {
            throw "Patched source is missing: $relative"
        }
        $actual = git -C $vendorRoot hash-object "--path=$relative" -- $relative
        if ($LASTEXITCODE -ne 0 -or $actual -ne $expected) {
            throw "Patched source blob differs from the reviewed patch: $relative"
        }
    }
}

$gitRoot = Join-Path $vendorRoot '.git'
if (-not (Test-Path -LiteralPath $gitRoot)) {
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $vendorRoot) | Out-Null
    git clone --filter=blob:none --no-checkout $upstreamUrl $vendorRoot
    if ($LASTEXITCODE -ne 0) { throw 'Unable to clone the pinned LeLab source.' }
    git -C $vendorRoot fetch --depth 1 origin $upstreamCommit
    if ($LASTEXITCODE -ne 0) { throw 'Unable to fetch the pinned LeLab commit.' }
    git -C $vendorRoot checkout --detach $upstreamCommit
    if ($LASTEXITCODE -ne 0) { throw 'Unable to check out the pinned LeLab commit.' }
}
elseif (-not (Test-Path -LiteralPath $gitRoot -PathType Container)) {
    throw 'The LeLab checkout must use a local .git directory, not a worktree indirection file.'
}

# Existing checkouts are untrusted input. Walk the tree without following links
# before Git, npm, or a package script can dereference a junction elsewhere.
Assert-NoReparseTree -RootPath $vendorRoot -Label 'LeLab vendor checkout'

$origin = git -C $vendorRoot remote get-url origin
$head = git -C $vendorRoot rev-parse HEAD
if ($origin -ne $upstreamUrl -or $head -ne $upstreamCommit) {
    throw "Existing vendor checkout does not match the pinned source. origin=$origin HEAD=$head"
}

$vendorChanges = @(git -C $vendorRoot status --porcelain --untracked-files=all)
if ($LASTEXITCODE -ne 0) { throw 'Unable to inspect the LeLab vendor checkout.' }
$alreadyApplied = $false
if ($vendorChanges.Count -gt 0) {
    # Only a modified tree can already contain the patch. Avoid asking Git to
    # reverse-check a multi-megabyte patch against a pristine checkout: on
    # Windows PowerShell the expected error stream can fill the native pipe
    # and stall a first bootstrap indefinitely.
    git -C $vendorRoot apply --reverse --check $patchPath 2>$null
    $alreadyApplied = $LASTEXITCODE -eq 0
    if (-not $alreadyApplied) {
        throw 'Vendor checkout has changes that are not exactly the tracked patch; preserve it and inspect the diff.'
    }
}
else {
    git -C $vendorRoot apply --check $patchPath
    if ($LASTEXITCODE -ne 0) {
        throw 'Tracked patch does not apply to the clean pinned vendor checkout.'
    }
    git -C $vendorRoot apply $patchPath
    if ($LASTEXITCODE -ne 0) { throw 'Failed to apply the tracked LeLab patch.' }
}

Assert-NoReparseTree -RootPath $vendorRoot -Label 'Patched LeLab vendor checkout'
Assert-ExactPatchedSource

$frontendRoot = Join-Path $vendorRoot 'frontend'
Assert-NoReparsePoint -TargetPath $frontendRoot -Label 'LeLab frontend'
Assert-NoReparsePoint -TargetPath (Join-Path $frontendRoot 'node_modules') -Label 'LeLab node_modules'
Assert-NoReparsePoint -TargetPath (Join-Path $frontendRoot 'dist') -Label 'LeLab frontend dist'
npm ci --prefix $frontendRoot
if ($LASTEXITCODE -ne 0) { throw 'npm ci failed for the pinned LeLab frontend lock.' }
npm run build --prefix $frontendRoot
if ($LASTEXITCODE -ne 0) { throw 'The patched LeLab frontend build failed.' }

[pscustomobject]@{
    upstream = $upstreamUrl
    commit = $head
    patch = $patchPath
    patch_was_already_applied = $alreadyApplied
    frontend_dist = Join-Path $frontendRoot 'dist'
} | ConvertTo-Json -Depth 4
