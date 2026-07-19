param(
    [switch]$Unregister,
    [switch]$NoStart
)

$ErrorActionPreference = 'Stop'
$TaskName = 'AIKing-CodeSextant'

if ($Unregister) {
    $existing = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    if ($null -ne $existing) {
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
        Write-Output "unregistered=$TaskName"
    } else {
        Write-Output "already-absent=$TaskName"
    }
    exit 0
}

$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$Supervisor = Join-Path $ProjectRoot 'codesextant\supervisor.py'
if (-not (Test-Path -LiteralPath $Supervisor -PathType Leaf)) {
    throw "supervisor not found: $Supervisor"
}

$Candidates = @()
if ($env:CODESEXTANT_PYTHON) { $Candidates += $env:CODESEXTANT_PYTHON }
$Candidates += @(
    'C:\Python311\python.exe',
    'C:\Python312\python.exe',
    'C:\Python313\python.exe',
    'C:\Python310\python.exe'
)
$Python = $Candidates | Where-Object { Test-Path -LiteralPath $_ -PathType Leaf } |
    Select-Object -First 1
if (-not $Python) { throw 'No supported Python installation found.' }
$PythonW = Join-Path (Split-Path -Parent $Python) 'pythonw.exe'
if (-not (Test-Path -LiteralPath $PythonW -PathType Leaf)) {
    throw "pythonw not found beside: $Python"
}

$UserId = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$IsAdmin = ([System.Security.Principal.WindowsPrincipal]::new(
    [System.Security.Principal.WindowsIdentity]::GetCurrent()
)).IsInRole([System.Security.Principal.WindowsBuiltInRole]::Administrator)
$Action = New-ScheduledTaskAction `
    -Execute $PythonW `
    -Argument ('"{0}" run' -f $Supervisor) `
    -WorkingDirectory $ProjectRoot
$Heartbeat = New-ScheduledTaskTrigger `
    -Once `
    -At (Get-Date).AddMinutes(1) `
    -RepetitionInterval (New-TimeSpan -Minutes 1) `
    -RepetitionDuration (New-TimeSpan -Days 3650)
if ($IsAdmin) {
    $StartupMode = 'system-boot-and-logon'
    $Triggers = @(
        (New-ScheduledTaskTrigger -AtStartup),
        (New-ScheduledTaskTrigger -AtLogOn -User $UserId),
        $Heartbeat
    )
    $Principal = New-ScheduledTaskPrincipal `
        -UserId $UserId `
        -LogonType S4U `
        -RunLevel Limited
} else {
    # A standard user cannot register an AtStartup/S4U task.  AtLogOn is the
    # earliest reliable non-elevated startup point and still supports restart.
    $StartupMode = 'user-logon'
    $Triggers = @(
        (New-ScheduledTaskTrigger -AtLogOn -User $UserId),
        $Heartbeat
    )
    $Principal = New-ScheduledTaskPrincipal `
        -UserId $UserId `
        -LogonType Interactive `
        -RunLevel Limited
}
$Settings = New-ScheduledTaskSettingsSet `
    -MultipleInstances IgnoreNew `
    -RestartCount 255 `
    -RestartInterval (New-TimeSpan -Minutes 1) `
    -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -StartWhenAvailable `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -Hidden
$Task = New-ScheduledTask `
    -Action $Action `
    -Trigger $Triggers `
    -Principal $Principal `
    -Settings $Settings `
    -Description 'CodeSextant supervisor: startup plus one-minute recovery heartbeat.'
try {
    Register-ScheduledTask -TaskName $TaskName -InputObject $Task -Force `
        -ErrorAction Stop | Out-Null
} catch {
    throw "Task registration failed ($StartupMode): $($_.Exception.Message)"
}

if (-not $NoStart) {
    $Current = Get-ScheduledTask -TaskName $TaskName -ErrorAction Stop
    if ($Current.State -ne 'Running') {
        Start-ScheduledTask -TaskName $TaskName -ErrorAction Stop
        Start-Sleep -Seconds 2
    }
}

$Registered = Get-ScheduledTask -TaskName $TaskName -ErrorAction Stop
$Info = Get-ScheduledTaskInfo -TaskName $TaskName -ErrorAction Stop
[pscustomobject]@{
    TaskName = $Registered.TaskName
    StartupMode = $StartupMode
    State = $Registered.State
    LastRunTime = $Info.LastRunTime
    LastTaskResult = $Info.LastTaskResult
    Execute = $Registered.Actions.Execute
    Arguments = $Registered.Actions.Arguments
    TriggerCount = @($Registered.Triggers | Where-Object { $null -ne $_ }).Count
    RestartCount = $Registered.Settings.RestartCount
    MultipleInstances = $Registered.Settings.MultipleInstances
} | Format-List
