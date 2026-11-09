[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$sourceRoot = Join-Path $projectRoot 'blender_codex'
$requiredFiles = @('__init__.py', 'context.py', 'codex_client.py', 'hi3d.py', 'hi3d_ui.py', 'annotations.py',
    'official_backend.py', 'instructions.txt', 'hi3d_tool.py', 'native_tools.py', 'hi3d_config.py',
    'web_ui.py', 'web_bridge.py', 'web_host.py', 'web/index.html',
    'native/WebHost.exe', 'native/Microsoft.Web.WebView2.Core.dll',
    'native/Microsoft.Web.WebView2.WinForms.dll', 'native/WebView2Loader.dll', 'native/WebView2-LICENSE.txt')
foreach ($name in $requiredFiles) {
    if (-not (Test-Path -LiteralPath (Join-Path $sourceRoot $name) -PathType Leaf)) {
        throw "Add-on incomplete: missing blender_codex/$name"
    }
}
$provenanceFiles = @(
    @{ File = (Join-Path $projectRoot 'LICENSE'); Entry = 'blender_codex/LICENSE' },
    @{ File = (Join-Path $projectRoot 'THIRD_PARTY_NOTICES.md'); Entry = 'blender_codex/THIRD_PARTY_NOTICES.md' }
)
foreach ($record in $provenanceFiles) {
    if (-not (Test-Path -LiteralPath $record.File -PathType Leaf)) { throw "Project license/notice missing: $($record.File)" }
}
$uiSource = Join-Path $projectRoot 'frontend\vendor\deepblick\SOURCE.json'
if (Test-Path -LiteralPath $uiSource -PathType Leaf) {
    $uiBuild = Join-Path $projectRoot 'frontend\BUILD.json'
    $uiLicense = Join-Path $sourceRoot 'web\DEEPBLICK-LICENSE.txt'
    foreach ($file in @($uiBuild, $uiLicense)) {
        if (-not (Test-Path -LiteralPath $file -PathType Leaf)) { throw "Deepblick build incomplete: missing $file. Build frontend first." }
    }
    $provenanceFiles += @(
        @{ File = $uiSource; Entry = 'blender_codex/web/deepblick-source.json' },
        @{ File = $uiBuild; Entry = 'blender_codex/web/deepblick-build.json' }
    )
}
$outputFolder = Join-Path $projectRoot 'dist'
$null = New-Item -ItemType Directory -Path $outputFolder -Force
$outputPath = Join-Path $outputFolder 'blender_codex.zip'
$temporaryOutput = Join-Path $outputFolder ('.blender_codex.' + [Guid]::NewGuid().ToString('N') + '.tmp')

# Include the embedded UI and its Windows host, with the package at the ZIP root.
# Never include protocol schemas, tests, credentials, or Python bytecode.
Add-Type -AssemblyName System.IO.Compression
$webRoot = Join-Path $sourceRoot 'web'
$webExtensions = @('.html', '.css', '.js', '.mjs', '.svg', '.png', '.jpg', '.jpeg', '.webp', '.gif',
    '.ico', '.avif', '.woff', '.woff2', '.ttf', '.otf', '.json', '.wasm', '.txt', '.md')
# Bundle outputs may use nested hashed chunks, fonts and license notices. Reject
# linked trees rather than following developer checkout/node_modules symlinks.
foreach ($item in (Get-ChildItem -LiteralPath $webRoot -Recurse -Force)) {
    if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw "Linked web asset is not portable: $($item.FullName)" }
    if ($item.Name -eq 'node_modules' -or $item.Name -eq '.git' -or $item.Name.StartsWith('.env')) {
        throw "Development files found in built web output: $($item.FullName)"
    }
}
$stream = [System.IO.File]::Open($temporaryOutput, [System.IO.FileMode]::CreateNew)
try {
    $zip = [System.IO.Compression.ZipArchive]::new($stream, [System.IO.Compression.ZipArchiveMode]::Create, $true)
    try {
        $files = @(Get-ChildItem -LiteralPath $sourceRoot -File -Filter '*.py')
        $files += @(Get-Item -LiteralPath (Join-Path $sourceRoot 'instructions.txt'))
        $files += @(Get-ChildItem -LiteralPath $webRoot -Recurse -File | Where-Object { $_.Extension.ToLowerInvariant() -in $webExtensions })
        $files += @($requiredFiles | Where-Object { $_.StartsWith('native/') } | ForEach-Object { Get-Item -LiteralPath (Join-Path $sourceRoot $_) })
        foreach ($file in ($files | Sort-Object FullName)) {
            $relative = $file.FullName.Substring($sourceRoot.Length + 1).Replace('\', '/')
            $entry = $zip.CreateEntry("blender_codex/$relative")
            $entryStream = $entry.Open()
            try {
                $sourceStream = $file.OpenRead()
                try { $sourceStream.CopyTo($entryStream) } finally { $sourceStream.Dispose() }
            } finally { $entryStream.Dispose() }
        }
        foreach ($record in $provenanceFiles) {
            $entryStream = $zip.CreateEntry($record.Entry).Open()
            try {
                $sourceStream = [IO.File]::OpenRead($record.File)
                try { $sourceStream.CopyTo($entryStream) } finally { $sourceStream.Dispose() }
            } finally { $entryStream.Dispose() }
        }
    } finally { $zip.Dispose() }
} finally { $stream.Dispose() }
Move-Item -LiteralPath $temporaryOutput -Destination $outputPath -Force
Write-Output $outputPath
