[CmdletBinding()]
param(
    [string]$Version = '1.0.4314.35',
    [string]$PackageDirectory,
    [string]$OutputDirectory,
    [switch]$Offline
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
if (-not $PackageDirectory) { $PackageDirectory = Join-Path $projectRoot ".runtime\webview2\$Version" }
if (-not $OutputDirectory) { $OutputDirectory = Join-Path $projectRoot 'blender_codex\native' }
if ($Version -notmatch '^\d+\.\d+\.\d+\.\d+$') { throw 'Expected a stable numeric WebView2 NuGet version' }
$compiler = 'C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe'
if (-not (Test-Path -LiteralPath $compiler -PathType Leaf)) { throw '.NET Framework x64 C# compiler was not found' }
$core = Join-Path $PackageDirectory 'lib\net462\Microsoft.Web.WebView2.Core.dll'
if (-not (Test-Path -LiteralPath $core -PathType Leaf)) {
    if ($Offline) { throw "WebView2 SDK is not cached in $PackageDirectory; omit -Offline for the explicit build-time download" }
    $null = New-Item -ItemType Directory -Path $PackageDirectory -Force
    $archive = Join-Path $PackageDirectory 'webview2.nupkg'
    $uri = "https://api.nuget.org/v3-flatcontainer/microsoft.web.webview2/$Version/microsoft.web.webview2.$Version.nupkg"
    Write-Output "Downloading Microsoft.Web.WebView2 $Version from NuGet (SDK only; no global installation)."
    Invoke-WebRequest -Uri $uri -OutFile $archive -UseBasicParsing
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    [IO.Compression.ZipFile]::ExtractToDirectory($archive, $PackageDirectory)
}
$forms = Join-Path $PackageDirectory 'lib\net462\Microsoft.Web.WebView2.WinForms.dll'
$loader = Join-Path $PackageDirectory 'runtimes\win-x64\native\WebView2Loader.dll'
foreach ($dependency in @($core, $forms, $loader)) {
    if (-not (Test-Path -LiteralPath $dependency -PathType Leaf)) { throw "Missing SDK dependency: $dependency" }
}
$null = New-Item -ItemType Directory -Path $OutputDirectory -Force
$output = Join-Path $OutputDirectory 'WebHost.exe'
$source = Join-Path $projectRoot 'native\WebHost.cs'
& $compiler /nologo /target:exe /platform:x64 /optimize+ "/out:$output" /reference:System.dll /reference:System.Core.dll /reference:System.Drawing.dll /reference:System.Windows.Forms.dll /reference:System.Web.Extensions.dll "/reference:$core" "/reference:$forms" $source
if ($LASTEXITCODE -ne 0) { throw "WebView2 host compilation failed ($LASTEXITCODE)" }
foreach ($dependency in @($core, $forms, $loader)) { Copy-Item -LiteralPath $dependency -Destination $OutputDirectory -Force }
$license = Join-Path $PackageDirectory 'LICENSE.txt'
if (Test-Path -LiteralPath $license) { Copy-Item -LiteralPath $license -Destination (Join-Path $OutputDirectory 'WebView2-LICENSE.txt') -Force }
Write-Output "Built Windows x64 embedded host: $output"
Write-Output 'Requires an existing Microsoft Edge WebView2 Runtime; this script does not install it.'
