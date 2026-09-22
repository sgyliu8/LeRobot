[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$projectRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
$target = [IO.Path]::GetFullPath((Join-Path $projectRoot '.local\upstream\mujoco_menagerie'))
$repository = 'https://github.com/google-deepmind/mujoco_menagerie.git'
$commit = '8161bba264d7fa7c99ca301e91e7fb44737676ad'

if (-not (Test-Path -LiteralPath (Join-Path $target '.git'))) {
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $target) | Out-Null
    git clone --filter=blob:none --sparse $repository $target
    if ($LASTEXITCODE -ne 0) { throw 'Unable to clone the pinned MuJoCo Menagerie source.' }
    git -C $target sparse-checkout set robotstudio_so101
    if ($LASTEXITCODE -ne 0) { throw 'Unable to select the SO101 model assets.' }
    git -C $target checkout --detach $commit
    if ($LASTEXITCODE -ne 0) { throw 'Unable to check out the pinned Menagerie commit.' }
}

$origin = git -C $target remote get-url origin
$head = git -C $target rev-parse HEAD
$dirty = @(git -C $target status --porcelain)
if ($origin -ne $repository -or $head -ne $commit -or $dirty.Count -ne 0) {
    throw "Existing Menagerie checkout is not the clean pinned source. origin=$origin HEAD=$head"
}

$model = Join-Path $target 'robotstudio_so101\scene.xml'
$license = Join-Path $target 'LICENSE'
if (-not (Test-Path -LiteralPath $model -PathType Leaf) -or
    -not (Test-Path -LiteralPath $license -PathType Leaf)) {
    throw 'Pinned SO101 model or repository licence is missing.'
}

[pscustomobject]@{
    repository = $repository
    commit = $commit
    model = $model
    license = $license
} | ConvertTo-Json
