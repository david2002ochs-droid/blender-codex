param([string]$DependencyRoot = '')
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Push-Location $projectRoot
try {
    if (-not $DependencyRoot -and -not (Test-Path -LiteralPath 'frontend/node_modules/esbuild') -and (Test-Path -LiteralPath '.runtime/deepblick-dependency-root.txt')) {
        $DependencyRoot = (Get-Content -LiteralPath '.runtime/deepblick-dependency-root.txt' -Raw).Trim()
    }
    $buildArgs = @('frontend/build.mjs')
    if ($DependencyRoot) { $buildArgs += @('--dependency-root', $DependencyRoot) }
    & node @buildArgs
    if ($LASTEXITCODE -ne 0) { throw "Chat UI build failed ($LASTEXITCODE)" }
} finally { Pop-Location }
