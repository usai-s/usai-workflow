[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..\..') -ErrorAction Stop).Path
$runner = (Resolve-Path (Join-Path $PSScriptRoot '..\run-pre-tool-use.ps1') -ErrorAction Stop).Path
$powerShell = (Get-Command powershell.exe -ErrorAction Stop).Source
$cases = @(
    [pscustomobject]@{ Expected = 0; Command = 'rg pattern src' },
    [pscustomobject]@{ Expected = 2; Command = 'find / -name x' },
    [pscustomobject]@{ Expected = 2; Command = 'Get-ChildItem C:\ -Recurse' },
    [pscustomobject]@{ Expected = 2; Command = 'gci C:\Users -Recurse' }
)

$failures = 0
foreach ($testCase in $cases) {
    $payload = @{
        hook_event_name = 'PreToolUse'
        tool_name = 'Bash'
        cwd = $repoRoot
        tool_input = @{ command = $testCase.Command }
    } | ConvertTo-Json -Compress

    $startInfo = [System.Diagnostics.ProcessStartInfo]::new()
    $startInfo.FileName = $powerShell
    $startInfo.Arguments = "-NoProfile -ExecutionPolicy Bypass -File `"$runner`""
    $startInfo.UseShellExecute = $false
    $startInfo.RedirectStandardInput = $true
    $startInfo.RedirectStandardError = $true
    $startInfo.CreateNoWindow = $true

    $process = [System.Diagnostics.Process]::Start($startInfo)
    $process.StandardInput.Write($payload)
    $process.StandardInput.Close()
    $stderr = $process.StandardError.ReadToEnd()
    $process.WaitForExit()

    $markerOk = $testCase.Expected -eq 0 -or $stderr.Contains('block_wide_fs_search')
    $passed = $process.ExitCode -eq $testCase.Expected -and $markerOk
    $status = if ($passed) { 'ok' } else { 'FAIL' }
    Write-Output ("  {0,-4} expect={1} got={2} {3}" -f
        $status, $testCase.Expected, $process.ExitCode, $testCase.Command)

    if (-not $passed) {
        $failures++
        if ($stderr) {
            [Console]::Error.WriteLine($stderr.Trim())
        }
    }
}

Write-Output "Codex Windows hook: $($cases.Count) cases, $failures failed."
if ($failures -gt 0) {
    exit 1
}
exit 0
