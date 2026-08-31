[CmdletBinding()]
param(
    [Parameter(ValueFromPipeline = $true)]
    [string] $InputObject
)

# Windows-адаптер не содержит собственной policy: он передаёт Codex JSON в
# тот же Python hook, который использует Claude Code. Любое изменение policy
# поэтому сразу действует для обоих вендоров.

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

try {
    $payload = if ($PSBoundParameters.ContainsKey('InputObject')) {
        $InputObject
    }
    else {
        [Console]::In.ReadToEnd()
    }

    # Codex называет shell tool `Bash` на всех платформах, но commandWindows
    # исполняется PowerShell. Нормализуем только vendor-поле перед общей
    # policy, иначе PowerShell-команды разбирались бы как Bash.
    try {
        $hookEvent = $payload | ConvertFrom-Json
        $toolName = $hookEvent.PSObject.Properties['tool_name']
        if ($null -ne $toolName -and $toolName.Value -eq 'Bash') {
            $toolName.Value = 'PowerShell'
            $payload = $hookEvent | ConvertTo-Json -Compress -Depth 20
        }
    }
    catch {
        # Невалидный JSON передаём общей fail-open policy без догадок.
    }

    $repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..') -ErrorAction Stop).Path
    if ([string]::IsNullOrWhiteSpace($repoRoot)) {
        exit 0
    }

    $pythonCandidates = @()
    $localPython = Join-Path $env:LOCALAPPDATA 'Python\bin\python.exe'
    if (Test-Path -LiteralPath $localPython) {
        $pythonCandidates += $localPython
    }
    $pythonCandidates += @(Get-Command -Name python.exe, python3.exe -All -ErrorAction SilentlyContinue |
        Where-Object { $_.Source -notmatch '\\WindowsApps\\' } |
        Select-Object -ExpandProperty Source)

    $python = $pythonCandidates | Select-Object -First 1
    if ($null -eq $python) {
        # Совпадает с fail-open семантикой общей policy: отсутствие runtime не
        # должно блокировать легитимную команду без диагностируемого способа.
        exit 0
    }

    $hook = Join-Path $repoRoot '.claude\hooks\block_wide_fs_search.py'
    # ProcessStartInfo сохраняет точный exit code. Обычный PowerShell pipeline
    # превращает native stderr в ErrorRecord и на Windows PowerShell 5 может
    # заменить штатный блокирующий код 2 на общий код 1.
    $startInfo = [System.Diagnostics.ProcessStartInfo]::new()
    $startInfo.FileName = $python
    $startInfo.Arguments = "-B `"$hook`""
    $startInfo.UseShellExecute = $false
    $startInfo.RedirectStandardInput = $true

    $process = [System.Diagnostics.Process]::Start($startInfo)
    $process.StandardInput.Write($payload)
    $process.StandardInput.Close()
    $process.WaitForExit()
    exit $process.ExitCode
}
catch {
    # Policy намеренно fail-open; обоснование находится в общем Python hook.
    exit 0
}
