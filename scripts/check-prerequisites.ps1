[CmdletBinding()]
param()

# Read-only: no processes started, downloads, config changes, or installs.
$ErrorActionPreference = 'Stop'
$candidates = @{}
foreach ($name in @('codex', 'blender', 'python', 'python3', 'py', 'uv', 'uvx')) {
    $command = Get-Command $name -CommandType Application -ErrorAction SilentlyContinue
    foreach ($item in $command) { $candidates[$item.Source] = $name }
}
$knownFiles = @(
    "$env:USERPROFILE\.local\bin\uv.exe",
    "$env:USERPROFILE\.local\bin\uvx.exe",
    "$env:USERPROFILE\.cargo\bin\uv.exe",
    "$env:USERPROFILE\.cargo\bin\uvx.exe"
)
foreach ($file in $knownFiles) {
    if (Test-Path -LiteralPath $file -PathType Leaf) { $candidates[$file] = [IO.Path]::GetFileNameWithoutExtension($file) }
}
$blenderRoots = @(
    'C:\Program Files\Blender Foundation',
    'C:\Program Files (x86)\Blender Foundation',
    "$env:LOCALAPPDATA\Programs\Blender Foundation"
)
foreach ($root in $blenderRoots) {
    if (-not (Test-Path -LiteralPath $root -PathType Container)) { continue }
    foreach ($install in (Get-ChildItem -LiteralPath $root -Directory)) {
        $blender = Join-Path $install.FullName 'blender.exe'
        if (Test-Path -LiteralPath $blender -PathType Leaf) { $candidates[$blender] = 'blender' }
        foreach ($version in (Get-ChildItem -LiteralPath $install.FullName -Directory | Where-Object Name -Match '^\d+\.\d+$')) {
            $python = Join-Path $version.FullName 'python\bin\python.exe'
            if (Test-Path -LiteralPath $python -PathType Leaf) { $candidates[$python] = 'python (Blender)' }
        }
    }
}
$pythonRoot = "$env:LOCALAPPDATA\Programs\Python"
if (Test-Path -LiteralPath $pythonRoot -PathType Container) {
    foreach ($install in (Get-ChildItem -LiteralPath $pythonRoot -Directory)) {
        $python = Join-Path $install.FullName 'python.exe'
        if (Test-Path -LiteralPath $python -PathType Leaf) { $candidates[$python] = 'python' }
    }
}
foreach ($entry in ($candidates.GetEnumerator() | Sort-Object Value, Key)) {
    [PSCustomObject]@{ Tool = $entry.Value; Path = $entry.Key }
}
foreach ($name in @('codex', 'blender', 'python', 'uv', 'uvx')) {
    if (-not ($candidates.Values | Where-Object { $_ -like "$name*" })) {
        Write-Warning "$name not found on PATH or in the checked standard locations."
    }
}
