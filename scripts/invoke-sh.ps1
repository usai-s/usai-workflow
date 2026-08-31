[CmdletBinding()]
param(
    [Parameter(Mandatory = $true, Position = 0)]
    [string] $Script,

    [Parameter(Position = 1, ValueFromRemainingArguments = $true)]
    [string[]] $ScriptArguments
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$repoRoot = (& git rev-parse --show-toplevel 2>$null).Trim()
if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($repoRoot)) {
    throw 'Run this command inside a Git worktree.'
}

$scriptPath = Join-Path $repoRoot $Script
if (-not (Test-Path -LiteralPath $scriptPath -PathType Leaf)) {
    throw "Shell script not found: $scriptPath"
}

$bashCandidates = @(
    (Join-Path $env:ProgramFiles 'Git\bin\bash.exe'),
    (Join-Path $env:ProgramFiles 'Git\usr\bin\bash.exe')
)
if (${env:ProgramFiles(x86)}) {
    $bashCandidates += Join-Path ${env:ProgramFiles(x86)} 'Git\bin\bash.exe'
}
$bashCandidates += @(Get-Command bash.exe -All -ErrorAction SilentlyContinue |
    Where-Object { $_.Source -match '\\Git\\' } |
    Select-Object -ExpandProperty Source)

$bash = $bashCandidates | Where-Object { Test-Path -LiteralPath $_ } |
    Select-Object -First 1
if (-not $bash) {
    throw 'Git for Windows Bash was not found.'
}

Push-Location $repoRoot
try {
    # Keep the bootstrap deliberately simple: Windows PowerShell 5.1 corrupts
    # native arguments containing command substitutions, while exec "$@" is
    # stable in both 5.1 and PowerShell 7 and preserves all script arguments.
    & $bash --login -c 'exec "$@"' -- $Script @ScriptArguments
    $exitCode = $LASTEXITCODE
}
finally {
    Pop-Location
}

exit $exitCode
