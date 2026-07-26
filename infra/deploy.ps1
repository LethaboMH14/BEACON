<#
.SYNOPSIS
  Deploy BEACON to Azure. You run this; nobody else needs your credentials.

.DESCRIPTION
  Creates the resource group, deploys infra/main.bicep, builds and pushes the
  API and vision images, and prints the values you paste into server/.env.

  The Postgres admin password is prompted for as a SecureString and passed
  straight to the deployment. It is never written to disk, never echoed, and
  never placed in a file this repo tracks — which matters, because the repo is
  public.

.EXAMPLE
  az login
  ./infra/deploy.ps1 -ResourceGroup beacon-rg

.NOTES
  Run from the repo root. Requires the Azure CLI and Docker (for `az acr build`
  you do NOT need Docker locally — the build happens in Azure).
#>
[CmdletBinding()]
param(
    [string]$ResourceGroup = 'beacon-rg',
    [string]$Location = 'southafricanorth',
    [string]$Prefix = 'beacon',
    [switch]$InfraOnly,
    [switch]$SkipImages
)

$ErrorActionPreference = 'Stop'

function Say($msg) { Write-Host "==> $msg" -ForegroundColor Cyan }
function Warn($msg) { Write-Host "!!  $msg" -ForegroundColor Yellow }

# --- preflight -------------------------------------------------------------
Say "Checking Azure CLI login"
$account = az account show 2>$null | ConvertFrom-Json
if (-not $account) {
    throw "Not logged in. Run 'az login' first — this script never handles your credentials."
}
Write-Host "    Subscription: $($account.name)"
Write-Host "    Tenant:       $($account.tenantId)"

# A student subscription is the expected case; say so rather than letting a
# quota error 20 minutes in be the first hint.
if ($account.name -match 'Student|Free') {
    Warn "Student/Free subscription detected. Azure OpenAI and some regions are restricted;"
    Warn "main.bicep leaves Azure OpenAI OFF for that reason. See infra/README.md."
}

# --- resource group --------------------------------------------------------
Say "Ensuring resource group '$ResourceGroup' in $Location"
az group create --name $ResourceGroup --location $Location --output none

# --- your public IP, so you can reach Postgres from this machine -----------
Say "Detecting this machine's public IP for the Postgres firewall rule"
try {
    $clientIp = (Invoke-RestMethod -Uri 'https://api.ipify.org?format=json' -TimeoutSec 10).ip
    Write-Host "    $clientIp"
} catch {
    $clientIp = ''
    Warn "Could not detect public IP. Postgres will only accept connections from Azure;"
    Warn "add your IP later with: az postgres flexible-server firewall-rule create ..."
}

# --- password --------------------------------------------------------------
# Prompted, not parameterised: a password passed on the command line lands in
# PowerShell's history file.
Say "Postgres admin password"
Write-Host "    8-128 chars, must include 3 of: uppercase, lowercase, number, symbol." -ForegroundColor DarkGray
Write-Host "    Save it in your password manager now — this script will not show it again." -ForegroundColor DarkGray
$pgPassword = Read-Host -AsSecureString -Prompt "    Password"
$pgPlain = [Runtime.InteropServices.Marshal]::PtrToStringAuto(
    [Runtime.InteropServices.Marshal]::SecureStringToBSTR($pgPassword))
if ($pgPlain.Length -lt 8) { throw "Password too short." }

# --- deploy ----------------------------------------------------------------
Say "Deploying infra/main.bicep (this takes ~10 minutes, mostly Postgres)"
$deployName = "beacon-$(Get-Date -Format 'yyyyMMdd-HHmmss')"
$result = az deployment group create `
    --name $deployName `
    --resource-group $ResourceGroup `
    --template-file infra/main.bicep `
    --parameters prefix=$Prefix location=$Location clientIp=$clientIp pgAdminPassword=$pgPlain `
    --output json | ConvertFrom-Json

if (-not $result) { throw "Deployment failed. Run 'az deployment group show -g $ResourceGroup -n $deployName' for detail." }

$out = $result.properties.outputs
$apiFqdn   = $out.apiFqdn.value
$memberUrl = $out.memberAppHostname.value
$pgFqdn    = $out.postgresFqdn.value
$acrName   = $out.acrName.value
$acrServer = $out.acrLoginServer.value
$kvUri     = $out.keyVaultUri.value
$storage   = $out.storageAccountName.value

Say "Infrastructure deployed"

if ($InfraOnly) { Write-Host "`n-InfraOnly set; stopping before images." -ForegroundColor DarkGray; exit 0 }

# --- images ----------------------------------------------------------------
# `az acr build` builds in Azure, so Docker Desktop is not required locally.
if (-not $SkipImages) {
    Say "Building API image in ACR (no local Docker needed)"
    az acr build --registry $acrName --image "beacon-api:latest" --file server/Dockerfile server --output none

    foreach ($svc in @(
        @{ name = 'plate';  path = 'vision/backend' },
        @{ name = 'weapon'; path = 'vision/weapen_backend' }
    )) {
        if (Test-Path "$($svc.path)/Dockerfile") {
            Say "Building vision-$($svc.name) image"
            az acr build --registry $acrName --image "beacon-vision-$($svc.name):latest" `
                --file "$($svc.path)/Dockerfile" $svc.path --output none
        } else {
            Warn "No Dockerfile at $($svc.path) — skipping vision-$($svc.name). Build it before the demo."
        }
    }

    Say "Pointing container apps at the real images"
    az containerapp update --name "$Prefix-api" --resource-group $ResourceGroup `
        --image "$acrServer/beacon-api:latest" --output none
}

# --- PostGIS ---------------------------------------------------------------
Say "Enabling PostGIS"
Write-Host "    Run this once, from a machine whose IP is in the firewall:" -ForegroundColor DarkGray
Write-Host "    psql `"host=$pgFqdn port=5432 dbname=beacon user=beaconadmin sslmode=require`" -c 'CREATE EXTENSION IF NOT EXISTS postgis;'" -ForegroundColor DarkGray

# --- what to put in .env ---------------------------------------------------
Say "Done. Paste these into server/.env (which is gitignored — keep it that way)"
Write-Host ""
Write-Host "DATABASE_URL=postgresql://beaconadmin:<the-password-you-just-typed>@${pgFqdn}:5432/beacon?sslmode=require"
Write-Host "AZURE_STORAGE_ACCOUNT=$storage"
Write-Host "KEY_VAULT_URI=$kvUri"
Write-Host "CORS_ORIGINS=https://$memberUrl"
Write-Host ""
Write-Host "API:        https://$apiFqdn"
Write-Host "Member app: https://$memberUrl"
Write-Host ""
Warn "The password is deliberately NOT printed above. Take it from your password manager."
Warn "Postgres cannot scale to zero. Stop it between sessions or it will drain the credit:"
Write-Host "    az postgres flexible-server stop -g $ResourceGroup -n $($pgFqdn.Split('.')[0])" -ForegroundColor DarkGray
