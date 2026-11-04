# Mantiene la app de Streamlit siempre activa en Windows, sin depender de la terminal ni del reenvío de puertos
# de VS Code: una tarea programada la arranca al iniciar sesión y la relanza si se cae.
# Escucha en 127.0.0.2 (también loopback): VS Code Remote-SSH reenvía decenas de puertos del servidor remoto en
# 127.0.0.1 (8501, 8601...), y esa dirección nunca la toca. Chrome/Edge la tratan como origen seguro (micrófono).
# Uso: powershell -ExecutionPolicy Bypass -File scripts/app_service.ps1 -Action install|uninstall|start|stop|restart|status|logs
param(
    [ValidateSet('install', 'uninstall', 'start', 'stop', 'restart', 'status', 'logs', 'run')]
    [string]$Action = 'status',
    [string]$Address = '127.0.0.2',
    [int]$Port = 8601,
    [string]$Uv = ''
)
$ErrorActionPreference = 'Stop'

$TaskName = 'EmersonAdvisorApp'
$RepoRoot = Split-Path -Parent $PSScriptRoot
$StateDir = Join-Path $env:LOCALAPPDATA 'EmersonAdvisor'
$LogFile = Join-Path $StateDir 'app.log'
$PidFile = Join-Path $StateDir 'supervisor.pid'
$Url = "http://${Address}:$Port"

function Resolve-Uv {
    if ($Uv) { return $Uv }
    $cmd = Get-Command uv -ErrorAction SilentlyContinue
    if (-not $cmd) { throw 'No se encontró uv en el PATH; instálalo o pasa -Uv <ruta a uv.exe>.' }
    return $cmd.Source
}

function Test-Health {
    try {
        $r = Invoke-WebRequest "$Url/_stcore/health" -UseBasicParsing -TimeoutSec 3
        return $r.StatusCode -eq 200
    } catch { return $false }
}

function Stop-App {
    if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) { Stop-ScheduledTask -TaskName $TaskName }
    # Detener la tarea no mata a los hijos (uv -> python); se corta el árbol completo del supervisor.
    # taskkill va por cmd para que su stderr no se vuelva excepción en PowerShell 5.1.
    if (Test-Path $PidFile) {
        $supervisor = Get-Content $PidFile
        & cmd.exe /c "taskkill /T /F /PID $supervisor >nul 2>&1"
        Remove-Item $PidFile -ErrorAction SilentlyContinue
    }
    # Solo procesos de Python: si el puerto lo ocupa otro programa (p. ej. VS Code) no se toca.
    Get-PortOwner | Where-Object { $_.ProcessName -eq 'python' } |
        ForEach-Object { & cmd.exe /c "taskkill /T /F /PID $($_.Id) >nul 2>&1" }
}

function Get-PortOwner {
    Get-NetTCPConnection -LocalAddress $Address, '0.0.0.0' -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
        ForEach-Object { Get-Process -Id $_.OwningProcess -ErrorAction SilentlyContinue }
}

function Wait-Healthy([int]$Seconds = 90) {
    for ($i = 0; $i -lt $Seconds; $i++) {
        if (Test-Health) { Write-Host "App activa en $Url"; return }
        Start-Sleep -Seconds 1
    }
    Write-Warning "La app no respondió en $Seconds s; revisa el log: $LogFile"
}

New-Item -ItemType Directory -Force $StateDir | Out-Null

switch ($Action) {
    'run' {
        # Supervisor: lo ejecuta la tarea programada; relanza Streamlit si termina por cualquier motivo.
        $uvExe = Resolve-Uv
        Set-Content -Path $PidFile -Value $PID
        Set-Location $RepoRoot
        while ($true) {
            Add-Content $LogFile "==> $(Get-Date -Format s) arrancando Streamlit en $Url"
            & cmd.exe /c "`"$uvExe`" run --extra voice --extra claude streamlit run app/streamlit_app.py --server.address $Address --server.port $Port --server.headless true >> `"$LogFile`" 2>&1"
            Add-Content $LogFile "==> $(Get-Date -Format s) Streamlit terminó (código $LASTEXITCODE); reintento en 5 s"
            Start-Sleep -Seconds 5
        }
    }
    'install' {
        $uvExe = Resolve-Uv
        Stop-App
        $arguments = "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$PSCommandPath`" -Action run -Address $Address -Port $Port -Uv `"$uvExe`""
        $taskAction = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument $arguments -WorkingDirectory $RepoRoot
        $trigger = New-ScheduledTaskTrigger -AtLogOn -User "$env:USERDOMAIN\$env:USERNAME"
        $settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit ([TimeSpan]::Zero) -MultipleInstances IgnoreNew `
            -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1)
        $principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive -RunLevel Limited
        Register-ScheduledTask -TaskName $TaskName -Action $taskAction -Trigger $trigger -Settings $settings `
            -Principal $principal -Description "Emerson Replacement Advisor (Streamlit) en $Url" -Force | Out-Null
        Start-ScheduledTask -TaskName $TaskName
        Write-Host "Tarea '$TaskName' instalada: arranca al iniciar sesión. Log: $LogFile"
        Wait-Healthy
    }
    'uninstall' {
        Stop-App
        if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
            Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
        }
        Write-Host "Tarea '$TaskName' eliminada."
    }
    'start' { Start-ScheduledTask -TaskName $TaskName; Wait-Healthy }
    'stop' { Stop-App; Write-Host 'App detenida.' }
    'restart' { Stop-App; Start-ScheduledTask -TaskName $TaskName; Wait-Healthy }
    'status' {
        $task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
        $state = if ($task) { $task.State } else { 'no instalada' }
        $health = if (Test-Health) { 'responde' } else { 'no responde' }
        Write-Host "Tarea: $state | ${Address}:$Port : $health | Log: $LogFile"
        $owner = Get-PortOwner | Where-Object { $_.ProcessName -ne 'python' } | Select-Object -First 1
        if ($owner) {
            Write-Warning "El puerto $Port lo ocupa $($owner.ProcessName) (PID $($owner.Id)). Si es VS Code, detén el reenvío en el panel Ports."
        }
    }
    'logs' { if (Test-Path $LogFile) { Get-Content $LogFile -Tail 40 } }
}
