#!/usr/bin/env bash
# Provisions the server/ deploy target per ADR-0004 (docs/adr.md):
# Azure Container Apps + PostgreSQL Flexible Server (Burstable B1ms) + Key Vault.
# G3-optional flex (docs/01 §6) — the actual demo runs on localhost + cloudflared
# regardless, so this is not a blocker if it doesn't get run before the pitch.
#
# Prereqs: `az login`, an Azure for Students subscription (ADR-0004's reasoning
# for why this provider). Run from repo root: bash deploy/provision-azure.sh
#
# This is a one-shot CLI script, not bicep/terraform — deliberately, for a
# single hackathon resource group nobody will iterate on repeatedly.
set -euo pipefail

RESOURCE_GROUP="${RESOURCE_GROUP:-beacon-hackathon-rg}"
LOCATION="${LOCATION:-southafricanorth}"
ACA_ENV="${ACA_ENV:-beacon-env}"
APP_NAME="${APP_NAME:-beacon-server}"
PG_SERVER="${PG_SERVER:-beacon-pg}"
PG_ADMIN_USER="${PG_ADMIN_USER:-beaconadmin}"
KEYVAULT_NAME="${KEYVAULT_NAME:-beacon-kv-$RANDOM}"
IMAGE_TAG="${IMAGE_TAG:-beacon-server:latest}"

echo "==> Resource group"
az group create --name "$RESOURCE_GROUP" --location "$LOCATION" --output none

echo "==> Key Vault (secrets: DB creds, WeatherAPI/EskomSePush keys — never in .env for this deploy)"
az keyvault create \
  --name "$KEYVAULT_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --location "$LOCATION" \
  --output none

echo "==> PostgreSQL Flexible Server (Burstable B1ms per ADR-0004)"
read -rsp "Postgres admin password: " PG_ADMIN_PASSWORD
echo
az postgres flexible-server create \
  --name "$PG_SERVER" \
  --resource-group "$RESOURCE_GROUP" \
  --location "$LOCATION" \
  --admin-user "$PG_ADMIN_USER" \
  --admin-password "$PG_ADMIN_PASSWORD" \
  --sku-name Standard_B1ms \
  --tier Burstable \
  --storage-size 32 \
  --version 16 \
  --public-access 0.0.0.0-255.255.255.255 \
  --output none

az postgres flexible-server db create \
  --resource-group "$RESOURCE_GROUP" \
  --server-name "$PG_SERVER" \
  --database-name beacon \
  --output none

DATABASE_URL="postgresql://${PG_ADMIN_USER}:${PG_ADMIN_PASSWORD}@${PG_SERVER}.postgres.database.azure.com/beacon"
az keyvault secret set --vault-name "$KEYVAULT_NAME" --name "database-url" --value "$DATABASE_URL" --output none

echo "==> Container Apps environment"
az containerapp env create \
  --name "$ACA_ENV" \
  --resource-group "$RESOURCE_GROUP" \
  --location "$LOCATION" \
  --output none

echo "==> Building and deploying server/ (az containerapp up handles build+push+deploy in one step)"
az containerapp up \
  --name "$APP_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --environment "$ACA_ENV" \
  --source ./server \
  --ingress external \
  --target-port 8000 \
  --env-vars "DATABASE_URL=secretref:database-url" \
  --output none

echo "==> Wiring Key Vault secret into the Container App"
IDENTITY=$(az containerapp identity assign --name "$APP_NAME" --resource-group "$RESOURCE_GROUP" --system-assigned --query principalId -o tsv)
az keyvault set-policy --name "$KEYVAULT_NAME" --object-id "$IDENTITY" --secret-permissions get list --output none

echo "Done. Fetch the app URL with:"
echo "  az containerapp show --name $APP_NAME --resource-group $RESOURCE_GROUP --query properties.configuration.ingress.fqdn -o tsv"
