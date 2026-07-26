<#
.SYNOPSIS
  Wire Roboflow/SendGrid keys into the already-deployed beacon-api Container
  App, without re-running the full infra/deploy.ps1 deployment.

.DESCRIPTION
  Prompts for both keys as SecureStrings — same handling as deploy.ps1's
  Postgres password: never written to disk, never echoed, never placed in a
  file this repo tracks. Run this yourself, on your own machine, with your
  own keys; nobody else needs to see them.

  Restarts the current active revision afterward so the container actually
  picks up the new env vars.

.EXAMPLE
  az login
  ./infra/set-vision-secrets.ps1 -ResourceGroup beacon-rg
#>
[CmdletBinding()]
param(
    [string]$ResourceGroup = 'beacon-rg',
    [string]$Prefix = 'beacon'
)

$ErrorActionPreference = 'Stop'

function Say($msg) { Write-Host "==> $msg" -ForegroundColor Cyan }
function Warn($msg) { Write-Host "!!  $msg" -ForegroundColor Yellow }

$account = az account show 2>$null | ConvertFrom-Json
if (-not $account) { throw "Not logged in. Run 'az login' first." }

$appName = "$Prefix-api"

function Read-PlainSecure([string]$prompt) {
    $secure = Read-Host -AsSecureString -Prompt $prompt
    return [Runtime.InteropServices.Marshal]::PtrToStringAuto(
        [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure))
}

Say "Roboflow API key (blank to leave unchanged)"
$roboflow = Read-PlainSecure "    Roboflow key"

Say "SendGrid API key (blank to leave unchanged)"
$sendgrid = Read-PlainSecure "    SendGrid key"

$escalationFrom = ''
$escalationTo = ''
if ($sendgrid) {
    $escalationFrom = Read-Host "    Verified SendGrid sender address"
    $escalationTo = Read-Host "    Escalation recipient address(es), comma-separated"
}

$secretArgs = @()
$envArgs = @()

if ($roboflow) {
    $secretArgs += "roboflow-api-key=$roboflow"
    $envArgs += "ROBOFLOW_API_KEY=secretref:roboflow-api-key"
}
if ($sendgrid) {
    $secretArgs += "sendgrid-api-key=$sendgrid"
    $envArgs += "SENDGRID_API_KEY=secretref:sendgrid-api-key"
    $envArgs += "EMAIL_PROVIDER=sendgrid"
    $envArgs += "ESCALATION_FROM=$escalationFrom"
    $envArgs += "ESCALATION_TO=$escalationTo"
}

if ($secretArgs.Count -eq 0) { Warn "Nothing entered — nothing changed."; exit 0 }

Say "Setting secrets on $appName"
az containerapp secret set --name $appName --resource-group $ResourceGroup --secrets $secretArgs --output none

Say "Updating env vars on $appName"
az containerapp update --name $appName --resource-group $ResourceGroup --set-env-vars $envArgs --output none

Say "Restarting active revision so the new env vars actually take effect"
$activeRevision = (az containerapp revision list --name $appName --resource-group $ResourceGroup `
    --query "[?properties.active].name" -o tsv | Select-Object -First 1)
az containerapp revision restart --name $appName --resource-group $ResourceGroup --revision $activeRevision --output none

Say "Done. Check health:"
$fqdn = az containerapp show --name $appName --resource-group $ResourceGroup --query "properties.configuration.ingress.fqdn" -o tsv
Write-Host "    curl https://$fqdn/health"
