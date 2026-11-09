param(
    [string]$PythonPath = 'C:\Program Files\Blender Foundation\Blender 5.2\5.2\python\bin\python.exe',
    [string]$RuntimeRoot = (Join-Path $PSScriptRoot '..\.runtime\official-mcp'),
    [switch]$PatchOnly
)
$ErrorActionPreference = 'Stop'
$SourceUrl = 'https://projects.blender.org/lab/blender_mcp.git'
$Revision = 'dbbf836ad4b1025f14a2b3b504c43903f39e0b04'
$RuntimeRoot = [IO.Path]::GetFullPath($RuntimeRoot)
$SourcePath = Join-Path $RuntimeRoot 'source'
$VenvPath = Join-Path $RuntimeRoot 'venv'
$ServerPython = Join-Path $VenvPath 'Scripts\python.exe'
if (-not $PatchOnly -and -not (Test-Path -LiteralPath $PythonPath -PathType Leaf)) { throw 'Set -PythonPath to an installed Python 3.10+ executable.' }
if ($PatchOnly -and -not (Test-Path -LiteralPath (Join-Path $RuntimeRoot 'installation.json') -PathType Leaf)) { throw 'PatchOnly requires an existing installation manifest.' }
if ($PatchOnly -and -not (Test-Path -LiteralPath $ServerPython -PathType Leaf)) { throw 'PatchOnly requires the existing virtual environment.' }
New-Item -ItemType Directory -Path $RuntimeRoot -Force | Out-Null
if ($PatchOnly -and -not (Test-Path -LiteralPath $SourcePath)) { throw 'PatchOnly requires the pinned source checkout.' }
if (-not (Test-Path -LiteralPath $SourcePath)) {
    & git init --initial-branch=main $SourcePath
    if ($LASTEXITCODE) { throw 'Could not initialize the isolated official source checkout.' }
    & git -C $SourcePath remote add origin $SourceUrl
    if ($LASTEXITCODE) { throw 'Could not configure the official source remote.' }
}
$Origin = & git -C $SourcePath remote get-url origin
if ($LASTEXITCODE -or $Origin.Trim() -ne $SourceUrl) { throw 'Refusing an existing source checkout from a different origin.' }
$Current = & git -C $SourcePath rev-parse --verify HEAD 2>$null
if ($LASTEXITCODE -ne 0) {
    & git -C $SourcePath fetch --depth 1 origin $Revision
    if ($LASTEXITCODE) { throw 'Could not fetch the pinned official Blender Lab MCP source.' }
    & git -C $SourcePath checkout --detach FETCH_HEAD
    if ($LASTEXITCODE) { throw 'Could not check out the pinned source.' }
    $Current = & git -C $SourcePath rev-parse HEAD
}
if ($Current.Trim() -ne $Revision) { throw 'Existing runtime uses another revision. Select a fresh -RuntimeRoot; no files were overwritten.' }
$Dirty = & git -C $SourcePath status --porcelain --untracked-files=no
if ($Dirty) { throw 'Official source has local modifications; refusing to install it.' }
if (-not (Test-Path -LiteralPath $ServerPython -PathType Leaf)) {
    & $PythonPath -m venv $VenvPath
    if ($LASTEXITCODE) { throw 'Could not create a project-local Python virtual environment.' }
}
if (-not $PatchOnly) {
$PackagePath = Join-Path $SourcePath 'mcp'
# The main package comes ONLY from the pinned official checkout. PyPI supplies
# its declared SDK/documentation dependencies, never a same-named MCP server.
& $ServerPython -m pip --isolated --disable-pip-version-check --no-cache-dir install $PackagePath
if ($LASTEXITCODE) { throw 'Official MCP package installation failed.' }
}
if ($PatchOnly) {
    $Existing = Get-Content -Raw -LiteralPath (Join-Path $RuntimeRoot 'installation.json') | ConvertFrom-Json
    if ($Existing.source_url -ne $SourceUrl -or $Existing.revision -ne $Revision -or $Existing.python -ne $ServerPython) { throw 'Existing manifest does not match this pinned runtime.' }
}
$PatchScript = Join-Path $PSScriptRoot '..\patches\apply_blender_mcp_cli_stdin.py'
$PatchJson = & $ServerPython $PatchScript
if ($LASTEXITCODE) { throw 'Official MCP compatibility patch failed; installation manifest not updated.' }
$PatchRecord = $PatchJson | ConvertFrom-Json
& $ServerPython -c "import blmcp; from importlib.metadata import version; print(version('blender-mcp'))"
if ($LASTEXITCODE) { throw 'Official MCP import verification failed.' }
$AddonPath = Join-Path $SourcePath 'addon\blender_mcp_addon'
$AddonZip = Join-Path $RuntimeRoot 'blender-lab-mcp-addon.zip'
if (-not $PatchOnly) {
Compress-Archive -Path @((Join-Path $AddonPath '*'), (Join-Path $SourcePath 'LICENSE')) -DestinationPath $AddonZip -Force
$Record = @{
    source_url = $SourceUrl; revision = $Revision; version = '1.0.2'; license = 'GPL-3.0-or-later'
    python = $ServerPython; addon_source = $AddonPath; addon_zip = $AddonZip
}
} else {
    $Record = @{}
    foreach ($property in $Existing.PSObject.Properties) { $Record[$property.Name] = $property.Value }
}
$Record.compatibility_patch = @{ id = $PatchRecord.id; patch_sha256_lf = $PatchRecord.patch_sha256_lf; original_sha256 = $PatchRecord.original_sha256; installed_sha256 = $PatchRecord.installed_sha256 }
$ManifestPath = Join-Path $RuntimeRoot 'installation.json'
$TemporaryManifest = Join-Path $RuntimeRoot 'installation.json.tmp'
$Record | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $TemporaryManifest -Encoding utf8
Move-Item -LiteralPath $TemporaryManifest -Destination $ManifestPath -Force
if (-not $PatchOnly) { & $ServerPython -m pip --isolated freeze | Set-Content -LiteralPath (Join-Path $RuntimeRoot 'dependencies.txt') -Encoding utf8 }
Write-Output ('MCP executable: ' + $ServerPython)
Write-Output 'MCP arguments: ["-m","blmcp","--transport","stdio"]'
Write-Output ('Official add-on ZIP: ' + $AddonZip)
Write-Output 'Prepared only: no Blender preferences or normal Codex configuration were changed.'
