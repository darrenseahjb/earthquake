$projectRoot = Split-Path -Parent $PSScriptRoot
$python = Join-Path $projectRoot ".venv\Scripts\python.exe"
$pidFile = Join-Path $projectRoot "logs\bot.pid"
$logDir = Join-Path $projectRoot "logs"

New-Item -ItemType Directory -Force -Path $logDir | Out-Null

Get-CimInstance Win32_Process |
    Where-Object { $_.CommandLine -like '*earthquake_bot.main*' -and $_.Name -eq 'python.exe' } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force }

Get-CimInstance Win32_Process |
    Where-Object { $_.CommandLine -like '*earthquake_bot.main*' -and $_.Name -eq 'pythonw.exe' } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force }

Start-Sleep -Seconds 1
$proc = Start-Process -FilePath $python -ArgumentList '-m','earthquake_bot.main' -WorkingDirectory $projectRoot -PassThru -WindowStyle Hidden
Set-Content -Path $pidFile -Value $proc.Id -Encoding ascii
Write-Output "Earthquake bot started in the background. PID: $($proc.Id)"
