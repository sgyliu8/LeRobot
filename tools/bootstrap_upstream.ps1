[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$projectRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$vendorRoot = [IO.Path]::GetFullPath((Join-Path $projectRoot '_vendor\lelab'))
$patchPath = [IO.Path]::GetFullPath((Join-Path $projectRoot 'patches\lelab-6091a458-so101-lab.patch'))
$upstreamUrl = 'https://github.com/huggingface/leLab.git'
$upstreamCommit = '6091a45811ef926a06b9b3622a9ab69fefb8bb7b'

foreach ($scopedPath in @($vendorRoot, $patchPath)) {
    if (-not $scopedPath.StartsWith($projectRoot, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Resolved path escaped the project root: $scopedPath"
    }
}
if (-not (Test-Path -LiteralPath $patchPath)) {
    throw "Tracked LeLab patch is missing: $patchPath"
}

if (-not (Test-Path -LiteralPath (Join-Path $vendorRoot '.git'))) {
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $vendorRoot) | Out-Null
    git clone --filter=blob:none --no-checkout $upstreamUrl $vendorRoot
    if ($LASTEXITCODE -ne 0) { throw 'Unable to clone the pinned LeLab source.' }
    git -C $vendorRoot fetch --depth 1 origin $upstreamCommit
    if ($LASTEXITCODE -ne 0) { throw 'Unable to fetch the pinned LeLab commit.' }
    git -C $vendorRoot checkout --detach $upstreamCommit
    if ($LASTEXITCODE -ne 0) { throw 'Unable to check out the pinned LeLab commit.' }
}

$origin = git -C $vendorRoot remote get-url origin
$head = git -C $vendorRoot rev-parse HEAD
if ($origin -ne $upstreamUrl -or $head -ne $upstreamCommit) {
    throw "Existing vendor checkout does not match the pinned source. origin=$origin HEAD=$head"
}

git -C $vendorRoot apply --reverse --check $patchPath 2>$null
$alreadyApplied = $LASTEXITCODE -eq 0
if (-not $alreadyApplied) {
    git -C $vendorRoot apply --check $patchPath
    if ($LASTEXITCODE -ne 0) {
        throw 'Vendor checkout is neither clean nor exactly patched; preserve it and inspect the diff.'
    }
    git -C $vendorRoot apply $patchPath
    if ($LASTEXITCODE -ne 0) { throw 'Failed to apply the tracked LeLab patch.' }
}

$frontendRoot = Join-Path $vendorRoot 'frontend'
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
