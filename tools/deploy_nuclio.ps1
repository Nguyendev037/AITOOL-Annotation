<#
.SYNOPSIS
    Deploy the CVAT smart-annotation functions into the local nuclio dashboard.

.DESCRIPTION
    The nuclio dashboard (port 8070) is not published on the host, so this
    script drives the dashboard REST API from a throwaway `curlimages/curl`
    container attached to the same docker network as nuclio.

    Run `python tools/deploy_nuclio.py --all` first to (re)generate the
    payloads in nuclio/build/ from nuclio/functions/*.yaml + nuclio/src/main.py.
    That command also writes nuclio/build/manifest.json, which is the list of
    files this script is allowed to deploy.

.EXAMPLE
    powershell -File tools/deploy_nuclio.ps1
    powershell -File tools/deploy_nuclio.ps1 -Name smart-bbox
#>
[CmdletBinding()]
param(
    [string[]]$Name = @(),
    [string]$Network = "cvat_cvat",
    [string]$Dashboard = "http://nuclio:8070",
    [int]$TimeoutSeconds = 1800,
    [switch]$NoWait
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$buildDir = Join-Path $repoRoot "nuclio\build"

if (-not (Test-Path $buildDir)) {
    throw "No payloads in $buildDir. Run: python tools/deploy_nuclio.py --all"
}

# Deploy only the payloads tools/deploy_nuclio.py generated. `nuclio/build/` is a
# scratch directory that also collects request fixtures and ad-hoc dumps; a plain
# `Get-ChildItem -Filter *.json` used to try to POST those as functions and fail
# with "Function name must be provided in metadata".
$manifestPath = Join-Path $buildDir "manifest.json"
if (-not (Test-Path $manifestPath)) {
    throw "No manifest at $manifestPath. Run: python tools/deploy_nuclio.py --all"
}
$manifest = Get-Content -Path $manifestPath -Raw | ConvertFrom-Json
$available = @($manifest.functions)

$files = @(
    $available |
        ForEach-Object { Join-Path $buildDir "$_.json" } |
        Where-Object { Test-Path $_ } |
        ForEach-Object { Get-Item $_ }
)
if ($Name.Count -gt 0) {
    $files = @($files | Where-Object { $Name -contains $_.BaseName })
}
if ($files.Count -eq 0) {
    throw "No payload selected. Available in manifest: $($available -join ', ')"
}

function Invoke-NuclioApi {
    param(
        [Parameter(Mandatory)][string]$Method,
        [Parameter(Mandatory)][string]$Path,
        [string]$PayloadFile
    )

    $dockerArgs = @(
        "run", "--rm", "--network", $Network,
        "-v", "${buildDir}:/b:ro",
        "curlimages/curl", "-s", "-S", "-m", "1800",
        "-X", $Method, "$Dashboard$Path",
        "-w", "`n%{http_code}"
    )
    if ($PayloadFile) {
        $dockerArgs += @(
            "-H", "Content-Type: application/json",
            "--data-binary", "@/b/$((Split-Path -Leaf $PayloadFile))"
        )
    }

    $raw = (& docker @dockerArgs 2>&1 | Out-String).TrimEnd()
    $parts = $raw -split "`n"
    $status = 0
    if ($parts.Count -ge 1) { [void][int]::TryParse($parts[-1].Trim(), [ref]$status) }
    $body = if ($parts.Count -ge 2) { ($parts[0..($parts.Count - 2)] -join "`n") } else { "" }
    return [pscustomobject]@{ Status = $status; Body = $body }
}

function Get-FunctionState {
    param([string]$FunctionName)
    $response = Invoke-NuclioApi -Method GET -Path "/api/functions/$FunctionName"
    if ($response.Status -ne 200 -or -not $response.Body) {
        return [pscustomobject]@{ State = "unknown"; Message = "" }
    }
    try {
        $json = $response.Body | ConvertFrom-Json
        return [pscustomobject]@{
            State   = [string]$json.status.state
            Message = [string]$json.status.message
        }
    } catch {
        return [pscustomobject]@{ State = "unknown"; Message = "unparsable response" }
    }
}

$failed = @()

foreach ($file in $files) {
    $functionName = $file.BaseName
    Write-Host ""
    Write-Host "==> $functionName" -ForegroundColor Cyan

    $existing = Invoke-NuclioApi -Method GET -Path "/api/functions/$functionName"
    if ($existing.Status -eq 200) {
        Write-Host "    deleting previous version"
        # nuclio deletes via DELETE /api/functions with a JSON body carrying
        # metadata.name. `DELETE /api/functions/<name>` only accepts GET/PUT and
        # answers HTTP 405, so the old form silently left the function in place.
        $deleteBody = Join-Path $buildDir ".delete-$functionName.json"
        $deleteJson = @{ metadata = @{ name = $functionName; namespace = "nuclio" } } |
            ConvertTo-Json -Depth 5 -Compress
        [System.IO.File]::WriteAllText($deleteBody, $deleteJson, (New-Object System.Text.UTF8Encoding($false)))
        try {
            $deleted = Invoke-NuclioApi -Method DELETE -Path "/api/functions" -PayloadFile $deleteBody
            if ($deleted.Status -notin @(200, 202, 204)) {
                Write-Host "    delete returned HTTP $($deleted.Status): $($deleted.Body)" -ForegroundColor Yellow
            }
        } finally {
            Remove-Item -Force -ErrorAction SilentlyContinue $deleteBody
        }
    }

    Write-Host "    POSTing function config (build may take a few minutes)"
    $posted = Invoke-NuclioApi -Method POST -Path "/api/functions" -PayloadFile $file.FullName
    if ($posted.Status -notin @(200, 201, 202)) {
        Write-Host "    deploy request failed: HTTP $($posted.Status)" -ForegroundColor Red
        Write-Host "    $($posted.Body.Substring(0, [Math]::Min(1200, $posted.Body.Length)))"
        $failed += $functionName
        continue
    }
    Write-Host "    deploy accepted (HTTP $($posted.Status))"

    if ($NoWait) { continue }

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    $state = "unknown"
    while ((Get-Date) -lt $deadline) {
        Start-Sleep -Seconds 5
        $info = Get-FunctionState -FunctionName $functionName
        $state = $info.State
        if ($state -notin @("building", "waitingForDeployment", "unknown", "")) { break }
        Write-Host "    ... $state"
    }

    switch ($state) {
        "ready" {
            Write-Host "    READY" -ForegroundColor Green
        }
        "unhealthy" {
            Write-Host "    UNHEALTHY: build or startup failed" -ForegroundColor Red
            $failed += $functionName
        }
        default {
            Write-Host "    state=$state (timeout or unexpected)" -ForegroundColor Yellow
            $failed += $functionName
        }
    }
}

Write-Host ""
if ($failed.Count -gt 0) {
    Write-Host "Failed: $($failed -join ', ')" -ForegroundColor Red
    Write-Host "Inspect logs with:  powershell -File tools/nuclio_status.ps1"
    exit 1
}
Write-Host "All functions deployed." -ForegroundColor Green
Write-Host "Open CVAT -> Models to see them:  http://localhost:8080/models"
