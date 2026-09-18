<#
.SYNOPSIS
    Show the state of every nuclio function in the `cvat` project, with logs
    for anything that is not healthy.

.EXAMPLE
    powershell -File tools/nuclio_status.ps1
    powershell -File tools/nuclio_status.ps1 -Name smart-bbox -Logs 40
#>
[CmdletBinding()]
param(
    [string]$Name,
    [string]$Network = "cvat_cvat",
    [string]$Dashboard = "http://nuclio:8070",
    [int]$Logs = 0
)

$ErrorActionPreference = "Stop"

function Invoke-NuclioApi {
    param([string]$Path)
    $raw = (& docker run --rm --network $Network curlimages/curl -s -S -m 60 "$Dashboard$Path" 2>&1 | Out-String)
    return $raw
}

$path = if ($Name) { "/api/functions/$Name" } else { "/api/functions" }
$raw = Invoke-NuclioApi -Path $path
if (-not $raw.Trim()) { throw "empty response from $Dashboard$path" }

$json = $raw | ConvertFrom-Json

$functions = if ($Name) { @($json) } else { @($json.PSObject.Properties | ForEach-Object { $_.Value }) }

$rows = foreach ($fn in $functions) {
    [pscustomobject]@{
        Name    = $fn.metadata.name
        State   = $fn.status.state
        Message = $fn.status.message
        Type    = $fn.metadata.annotations.type
        Title   = $fn.metadata.annotations.name
    }
}
$rows | Format-Table -AutoSize

if ($Logs -gt 0) {
    $targets = if ($Name) { $functions } else { $functions | Where-Object { $_.status.state -ne "ready" } }
    foreach ($fn in $targets) {
        Write-Host ""
        Write-Host "--- logs: $($fn.metadata.name) ---" -ForegroundColor Cyan
        $entries = @($fn.status.logs) | Select-Object -Last $Logs
        foreach ($entry in $entries) {
            Write-Host ("[{0}] {1}" -f $entry.level, $entry.message)
        }
    }
}
