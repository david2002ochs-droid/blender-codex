$ErrorActionPreference = 'Stop'
$recorderRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$recorderState = Join-Path $recorderRoot '.runtime/screen-recorder-server.json'
$recorderUrl = $null
if (Test-Path -LiteralPath $recorderState) {
    try {
        $recorderSaved = Get-Content -LiteralPath $recorderState -Raw | ConvertFrom-Json
        $recorderUri = [Uri]$recorderSaved.url
        if ($recorderUri.Scheme -eq 'http' -and $recorderUri.Host -eq '127.0.0.1') {
            $recorderHealth = Invoke-RestMethod -Uri ($recorderUri.AbsoluteUri + 'health') -TimeoutSec 2
            if ($recorderHealth.app -eq 'blender-test-recorder' -and $recorderHealth.pid -eq $recorderSaved.pid) { $recorderUrl = $recorderSaved.url }
        }
    } catch { }
}
if (-not $recorderUrl) {
    $recorderNodeCommand = Get-Command node -ErrorAction SilentlyContinue
    $recorderNode = if ($env:RECORDER_NODE) { $env:RECORDER_NODE } elseif ($recorderNodeCommand) { $recorderNodeCommand.Source }
    if (-not $recorderNode -or -not (Test-Path -LiteralPath $recorderNode)) { throw 'Node.js wurde nicht gefunden.' }
    $recorderProcess = Start-Process -FilePath $recorderNode -ArgumentList ('"' + (Join-Path $PSScriptRoot 'server.cjs') + '"') -WindowStyle Hidden -WorkingDirectory $recorderRoot -PassThru
    for ($recorderAttempt=0; $recorderAttempt -lt 30; $recorderAttempt++) {
        Start-Sleep -Milliseconds 100
        if (Test-Path -LiteralPath $recorderState) {
            try { $recorderSaved = Get-Content -LiteralPath $recorderState -Raw | ConvertFrom-Json; if ($recorderSaved.pid -eq $recorderProcess.Id) { $recorderUrl = $recorderSaved.url; break } } catch { }
        }
    }
    if (-not $recorderUrl) { throw 'Der lokale Recorder konnte nicht gestartet werden.' }
}
$recorderBrowser = @('C:/Program Files/Google/Chrome/Application/chrome.exe','C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe') | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
if ($recorderBrowser) { Start-Process -FilePath $recorderBrowser -ArgumentList @('--new-window',$recorderUrl) }
else { Start-Process $recorderUrl }
Write-Output ('Recorder geöffnet: ' + $recorderUrl)
