[CmdletBinding()]
param(
    [string]$BlenderPath = 'C:\Program Files\Blender Foundation\Blender 5.2\blender.exe',
    [string]$CodexPath = 'codex',
    [string]$PackagePath,
    [int]$McpPort = 0,
    [switch]$NoConnect
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
if (-not $PackagePath) { $PackagePath = Join-Path $projectRoot 'dist/blender_codex.zip' }
$PackagePath = (Resolve-Path -LiteralPath $PackagePath).Path
if (-not (Test-Path -LiteralPath $BlenderPath -PathType Leaf)) { throw 'Set BlenderPath to an installed Blender executable.' }
$runtimeRoot = Join-Path $projectRoot '.runtime/official-mcp'
if (-not (Test-Path -LiteralPath (Join-Path $runtimeRoot 'installation.json'))) { throw 'Prepare the official MCP runtime first.' }
if ($McpPort -eq 0) {
    $listener = [Net.Sockets.TcpListener]::new([Net.IPAddress]::Loopback, 0)
    $listener.Start()
    try { $McpPort = $listener.LocalEndpoint.Port } finally { $listener.Stop() }
}
if ($McpPort -lt 1024 -or $McpPort -gt 65535) { throw 'McpPort must be between 1024 and 65535.' }
$candidateId = [DateTime]::UtcNow.ToString('yyyyMMdd-HHmmss') + '-' + [Guid]::NewGuid().ToString('N').Substring(0,8)
$candidateRoot = Join-Path $projectRoot ('.runtime/previews/' + $candidateId)
$null = New-Item -ItemType Directory -Path $candidateRoot
Add-Type -AssemblyName System.IO.Compression.FileSystem
$archive = [IO.Compression.ZipFile]::OpenRead($PackagePath)
try {
    foreach ($entry in $archive.Entries) {
        $relative = $entry.FullName.Replace('\','/')
        if ($relative -notlike 'blender_codex/*' -or $relative.Split('/') -contains '..') {
            throw 'Preview package contains an entry outside the add-on.'
        }
    }
} finally { $archive.Dispose() }
[IO.Compression.ZipFile]::ExtractToDirectory($PackagePath, $candidateRoot)
if (-not (Test-Path -LiteralPath (Join-Path $candidateRoot 'blender_codex/__init__.py'))) { throw 'Package has no add-on entrypoint.' }
@{ package_sha256=(Get-FileHash -LiteralPath $PackagePath -Algorithm SHA256).Hash; mcp_port=$McpPort; candidate=$candidateId } |
    ConvertTo-Json | Set-Content -LiteralPath (Join-Path $candidateRoot 'receipt.json') -Encoding utf8
# Environment changes apply only to this launch process and its children.
# The running add-on and web assets are a fixed package, never the editing tree.
$env:BLENDER_CODEX_PREVIEW_ROOT = $candidateRoot
$env:BLENDER_CODEX_OFFICIAL_RUNTIME = $runtimeRoot
$env:BLENDER_CODEX_EXECUTABLE = $CodexPath
if (-not $env:HI3D_ENV_FILE -and (Test-Path -LiteralPath (Join-Path $projectRoot '.env') -PathType Leaf)) {
    # Reference the user-selected development credentials without copying or
    # printing their contents into the frozen package or launch receipt.
    $env:HI3D_ENV_FILE = Join-Path $projectRoot '.env'
}
$env:BLENDER_CODEX_PREVIEW_CONNECT = $(if ($NoConnect) { '0' } else { '1' })
$env:BLENDER_MCP_PORT = [string]$McpPort
$env:BLENDER_USER_RESOURCES = Join-Path $projectRoot '.runtime/blender-data'
$env:BLENDER_USER_EXTENSIONS = Join-Path $projectRoot '.runtime/blender-extensions'
$previewScript = Join-Path $PSScriptRoot 'preview.py'
$previewProcess = Start-Process -FilePath $BlenderPath -ArgumentList @(
    '--factory-startup', '--online-mode', '--gpu-backend', 'vulkan', '--python', ('"' + $previewScript + '"')
) -WorkingDirectory $projectRoot -RedirectStandardOutput (Join-Path $candidateRoot 'stdout.log') -RedirectStandardError (Join-Path $candidateRoot 'stderr.log') -PassThru
$previewProcess.Id | Set-Content -LiteralPath (Join-Path $candidateRoot 'process-id.txt')
Write-Output ('Preview started: PID ' + $previewProcess.Id + ', package ' + $candidateId)
# Keep the launcher alive while Blender owns its UI and pipes.
$previewProcess.WaitForExit()
Write-Output ('Preview exited: ' + $previewProcess.ExitCode)
