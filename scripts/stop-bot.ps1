$projectRoot = Split-Path -Parent $PSScriptRoot
$pidFile = Join-Path $projectRoot "logs\bot.pid"

if (Test-Path $pidFile) {
    $botPid = Get-Content $pidFile | Select-Object -First 1
    if ($botPid) {
        Stop-Process -Id $botPid -Force -ErrorAction SilentlyContinue
    }
    Remove-Item $pidFile -Force -ErrorAction SilentlyContinue
}

Get-CimInstance Win32_Process |
    Where-Object { $_.CommandLine -like '*earthquake_bot.main*' -and ($_.Name -eq 'python.exe' -or $_.Name -eq 'pythonw.exe') } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force }

Write-Output "Earthquake bot stopped."
