<#
.SYNOPSIS
    Delete one or more functions from the local nuclio dashboard.

.DESCRIPTION
    Uses the endpoint documented in the nuclio Dashboard HTTP API:

        DELETE /api/functions
        Content-Type: application/json
        X-nuclio-function-namespace: nuclio
        {"metadata": {"name": "<name>", "namespace": "nuclio"}}

    Do NOT use `DELETE /api/functions/<name>`: that route only accepts GET/PUT
    and answers HTTP 405, which silently leaves the function in place. That was
    the bug in the first version of tools/deploy_nuclio.ps1.

    Port 8070 of the `nuclio` container is not published on the host, so the
    request is issued from a throwaway `curlimages/curl` container attached to
    the same docker network.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File tools/delete_nuclio.ps1 -Name sam2-large-api

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File tools/delete_nuclio.ps1 -Name sam2-large-api,foo -WhatIf
#>
[CmdletBinding(SupportsShouldProcess)]
param(
    [Parameter(Mandatory)][string[]]$Name,
    [string]$Network = "cvat_cvat",
    [string]$Dashboard = "http://nuclio:8070",
    [string]$Namespace = "nuclio",
    [int]$TimeoutSeconds = 120
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$buildDir = Join-Path $repoRoot "nuclio\build"
New-Item -ItemType Directory -Force -Path $buildDir | Out-Null

function Invoke-Dashboard {
    param([string]$Method, [string]$Path, [string]$BodyFile)

    $dockerArgs = @(
        "run", "--rm", "--network", $Network,
        "-v", "${buildDir}:/b:ro",
        "curlimages/curl", "-s", "-S", "-m", "$TimeoutSeconds",
        "-X", $Method, "$Dashboard$Path",
        "-H", "x-nuclio-function-namespace: $Namespace",
        "-w", "`n%{http_code}"
    )
    if ($BodyFile) {
        $dockerArgs += @(
            "-H", "Content-Type: application/json",
            "--data-binary", "@/b/$((Split-Path -Leaf $BodyFile))"
        )
    }

    $raw = (& docker @dockerArgs 2>&1 | Out-String).TrimEnd()
    $parts = $raw -split "`n"
    $status = 0
    if ($parts.Count -ge 1) { [void][int]::TryParse($parts[-1].Trim(), [ref]$status) }
    $body = if ($parts.Count -ge 2) { ($parts[0..($parts.Count - 2)] -join "`n") } else { "" }
    return [pscustomobject]@{ Status = $status; Body = $body }
}

$failed = @()

foreach ($functionName in $Name) {
    Write-Host ""
    Write-Host "==> $functionName" -ForegroundColor Cyan

    $bodyFile = Join-Path $buildDir ".delete-$functionName.json"
    $json = @{ metadata = @{ name = $functionName; namespace = $Namespace } } |
        ConvertTo-Json -Depth 5 -Compress
    # Windows PowerShell 5.1 `Set-Content -Encoding utf8` prepends a BOM, which
    # makes the dashboard reject the body with "invalid character 'ï'".
    # WriteAllText with an explicit BOM-less encoder is the portable fix.
    [System.IO.File]::WriteAllText($bodyFile, $json, (New-Object System.Text.UTF8Encoding($false)))

    try {
        # Confirm it exists first, so a typo is reported instead of silently "succeeding".
        $exists = Invoke-Dashboard -Method GET -Path "/api/functions/$functionName"
        if ($exists.Status -ne 200) {
            Write-Host "    not found (HTTP $($exists.Status)) - nothing to do" -ForegroundColor Yellow
            continue
        }

        if (-not $PSCmdlet.ShouldProcess($functionName, "delete nuclio function")) { continue }

        $deleted = Invoke-Dashboard -Method DELETE -Path "/api/functions" -BodyFile $bodyFile
        if ($deleted.Status -eq 204) {
            Write-Host "    DELETED (HTTP 204)" -ForegroundColor Green
        } else {
            Write-Host "    delete failed: HTTP $($deleted.Status) $($deleted.Body)" -ForegroundColor Red
            $failed += $functionName
        }
    } finally {
        Remove-Item -Force -ErrorAction SilentlyContinue $bodyFile
    }
}

Write-Host ""
if ($failed.Count -gt 0) {
    Write-Host "Failed: $($failed -join ', ')" -ForegroundColor Red
    exit 1
}
Write-Host "Done. Check with:  powershell -File tools/nuclio_status.ps1" -ForegroundColor Green
