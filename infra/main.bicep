// BEACON — Azure infrastructure.
//
// WHAT THIS DEPLOYS, AND WHAT IT DELIBERATELY DOESN'T
// Everything in the architecture table except Azure OpenAI and Notification
// Hubs, which are declared but switched OFF by default. See the flags below —
// both have real blockers on an Azure for Students subscription, and a template
// that fails halfway through is worse than one that tells you why up front.
//
// COST POSTURE: this is written for a $100 student credit, not a production
// budget. Every service is on its cheapest viable tier, the container apps
// scale to zero between demos, and Postgres is Burstable B1ms. Rough steady
// state with nothing running is a few dollars a month; the thing that will eat
// the credit is leaving Postgres up, because a database cannot scale to zero.
// Stop it between work sessions (see infra/README.md).
//
// Deploy: infra/deploy.ps1 (Windows) or infra/deploy.sh. Never commit outputs
// containing connection strings — the repo is public.

targetScope = 'resourceGroup'

@description('Short name used as a prefix for every resource. Lowercase alphanumeric.')
@minLength(3)
@maxLength(11)
param prefix string = 'beacon'

@description('Region. South Africa North keeps member location and claims data in-country.')
param location string = 'southafricanorth'

@description('Postgres admin username.')
param pgAdminUser string = 'beaconadmin'

@description('Postgres admin password. Passed in by the deploy script from a prompt — never defaulted, never committed.')
@secure()
param pgAdminPassword string

@description('Your current public IP, so the Postgres firewall lets your laptop in. The deploy script fills this in.')
param clientIp string = ''

@description('Azure OpenAI is off by default: Azure for Students subscriptions usually cannot create it without a separate access application, and South Africa North does not currently host it. Turn on only once you have confirmed both.')
param enableAzureOpenAI bool = false

@description('Region for Azure OpenAI if enabled. NOT southafricanorth — that region has no OpenAI capacity. This is a real data-residency compromise; see docs/HANDOVER-SBU.md.')
param openAiLocation string = 'swedencentral'

@description('Notification Hubs is off by default — it is only needed once there is a real mobile build to receive pushes.')
param enableNotificationHubs bool = false

@description('Azure for Students subscriptions cannot provision Static Web Apps — confirmed by testing all five SWA-capable regions (RequestDisallowedByAzure on every one, not a location issue). Off by default; member app + ops console are hosted on GitHub Pages/Vercel/Netlify instead. Flip on only if this subscription is ever upgraded off the student plan.')
param enableStaticWebApp bool = false

@description('Roboflow key for the hosted vision backend (server/src/vision/detectors.py). Passed in by whoever holds the key — never defaulted, never committed. Empty is valid: the API degrades to a clear startup error on vision endpoints only, everything else still runs.')
@secure()
param roboflowApiKey string = ''

@description('SendGrid key for escalation email (server/src/notify/email.py). Same handling as roboflowApiKey — empty just means escalation email is not wired up yet.')
@secure()
param sendgridApiKey string = ''

@description('Verified SendGrid sender address for escalation emails. Not secret, but meaningless without sendgridApiKey.')
param escalationFrom string = ''

@description('Comma-separated recipient address(es) for escalation emails.')
param escalationTo string = ''

var uniq = uniqueString(resourceGroup().id)
var tags = {
  project: 'BEACON'
  managedBy: 'bicep'
  costCentre: 'gradhack'
}

// ─────────────────────────────────────────────────────────────────────────────
// Storage — video clips and evidence.
//
// Two containers, different rules. Clips are working data. Evidence is the
// thing we claim is tamper-evident, so it gets versioning and a legal-hold-
// capable container: our SHA-256 chain proves a record was not edited *by us*,
// and immutable storage backs that with a service-level guarantee we do not
// control. One without the other is a weaker claim than it sounds.
// ─────────────────────────────────────────────────────────────────────────────
resource storage 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: '${prefix}st${uniq}'
  location: location
  tags: tags
  sku: { name: 'Standard_LRS' }
  kind: 'StorageV2'
  properties: {
    minimumTlsVersion: 'TLS1_2'
    supportsHttpsTrafficOnly: true
    // Public blob access off: clips are read through short-lived SAS tokens.
    // Several demo clips are copyrighted broadcast footage — an anonymously
    // readable container would be a licensing problem, not just a privacy one.
    allowBlobPublicAccess: false
  }
}

resource blobService 'Microsoft.Storage/storageAccounts/blobServices@2023-05-01' = {
  parent: storage
  name: 'default'
  properties: {
    isVersioningEnabled: true
    deleteRetentionPolicy: { enabled: true, days: 7 }
  }
}

resource clipsContainer 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-05-01' = {
  parent: blobService
  name: 'clips'
  properties: { publicAccess: 'None' }
}

resource evidenceContainer 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-05-01' = {
  parent: blobService
  name: 'evidence'
  properties: { publicAccess: 'None' }
}

// ─────────────────────────────────────────────────────────────────────────────
// Postgres Flexible Server + PostGIS.
//
// PostGIS is the reason this is not just "a database": "which hotspots are
// within 2 km of this route polyline" becomes ST_DWithin against a GIST index
// instead of the Python loop in routing/safest.py. That loop is correct and
// fast enough for 709 suburbs; it is not fast enough for 709 suburbs x every
// member's route, which is the whole point of moving.
//
// B1ms Burstable is the smallest tier that runs PostGIS comfortably. 32 GB is
// the minimum disk. This is the single largest line on the bill.
// ─────────────────────────────────────────────────────────────────────────────
resource postgres 'Microsoft.DBforPostgreSQL/flexibleServers@2023-06-01-preview' = {
  name: '${prefix}-pg-${uniq}'
  location: location
  tags: tags
  sku: { name: 'Standard_B1ms', tier: 'Burstable' }
  properties: {
    version: '16'
    administratorLogin: pgAdminUser
    administratorLoginPassword: pgAdminPassword
    storage: { storageSizeGB: 32 }
    backup: { backupRetentionDays: 7, geoRedundantBackup: 'Disabled' }
    highAvailability: { mode: 'Disabled' }
    authConfig: { passwordAuth: 'Enabled', activeDirectoryAuth: 'Disabled' }
  }
}

// PostGIS must be allow-listed at the server level before CREATE EXTENSION
// works. Forgetting this is the classic "extension postgis is not allow-listed"
// wall people hit an hour into setup.
resource pgExtensions 'Microsoft.DBforPostgreSQL/flexibleServers/configurations@2023-06-01-preview' = {
  parent: postgres
  name: 'azure.extensions'
  properties: { value: 'POSTGIS,PG_TRGM,UUID-OSSP', source: 'user-override' }
}

resource pgDatabase 'Microsoft.DBforPostgreSQL/flexibleServers/databases@2023-06-01-preview' = {
  parent: postgres
  name: 'beacon'
  properties: { charset: 'UTF8', collation: 'en_US.utf8' }
}

// Allows other Azure services (our Container Apps) to reach the server.
resource pgAllowAzure 'Microsoft.DBforPostgreSQL/flexibleServers/firewallRules@2023-06-01-preview' = {
  parent: postgres
  name: 'AllowAllAzureServices'
  properties: { startIpAddress: '0.0.0.0', endIpAddress: '0.0.0.0' }
}

// Your laptop, so you can run migrations and the seed scripts.
resource pgAllowClient 'Microsoft.DBforPostgreSQL/flexibleServers/firewallRules@2023-06-01-preview' = if (!empty(clientIp)) {
  parent: postgres
  name: 'AllowDevMachine'
  properties: { startIpAddress: clientIp, endIpAddress: clientIp }
}

// ─────────────────────────────────────────────────────────────────────────────
// Key Vault — the repo is public, so no key may ever live in it.
// Container Apps read secrets via managed identity; nothing is echoed to logs.
// ─────────────────────────────────────────────────────────────────────────────
resource keyVault 'Microsoft.KeyVault/vaults@2023-07-01' = {
  name: '${prefix}-kv-${uniq}'
  location: location
  tags: tags
  properties: {
    sku: { family: 'A', name: 'standard' }
    tenantId: subscription().tenantId
    enableRbacAuthorization: true
    enableSoftDelete: true
    softDeleteRetentionInDays: 7
    publicNetworkAccess: 'Enabled'
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Container registry + Container Apps environment.
// ─────────────────────────────────────────────────────────────────────────────
resource acr 'Microsoft.ContainerRegistry/registries@2023-11-01-preview' = {
  name: '${prefix}acr${uniq}'
  location: location
  tags: tags
  sku: { name: 'Basic' }
  properties: { adminUserEnabled: true }
}

resource logAnalytics 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: '${prefix}-logs-${uniq}'
  location: location
  tags: tags
  properties: {
    sku: { name: 'PerGB2018' }
    retentionInDays: 30
    // A student credit does not survive an accidental log flood.
    workspaceCapping: { dailyQuotaGb: 1 }
  }
}

resource containerEnv 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name: '${prefix}-env-${uniq}'
  location: location
  tags: tags
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: logAnalytics.properties.customerId
        sharedKey: logAnalytics.listKeys().primarySharedKey
      }
    }
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// API + WebSocket.
//
// minReplicas: 1, NOT 0. Everything else here scales to zero; this cannot,
// because a WebSocket connection to a scaled-to-zero app is a connection to
// nothing, and the ops console's whole value is that it is already connected
// when something happens. The cold-start cost would land exactly on the first
// alert. This is the one place we pay for always-on, deliberately.
// ─────────────────────────────────────────────────────────────────────────────
resource apiApp 'Microsoft.App/containerApps@2024-03-01' = {
  name: '${prefix}-api'
  location: location
  tags: tags
  identity: { type: 'SystemAssigned' }
  properties: {
    managedEnvironmentId: containerEnv.id
    configuration: {
      ingress: {
        external: true
        targetPort: 8000
        transport: 'auto'          // negotiates HTTP/1.1, HTTP/2 and WebSocket
        allowInsecure: false
        corsPolicy: {
          allowedOrigins: ['*']    // tightened to the SWA hostnames after first deploy
          allowedMethods: ['*']
          allowedHeaders: ['*']
        }
      }
      registries: [{
        server: acr.properties.loginServer
        username: acr.name
        passwordSecretRef: 'acr-password'
      }]
      // Container Apps rejects a secret with an empty value outright, so
      // roboflow/sendgrid are only added — as secrets AND as the env vars
      // that reference them — when actually supplied. Leaving them blank at
      // deploy time must mean "not wired up yet", not a deployment failure.
      secrets: concat(
        [
          { name: 'acr-password', value: acr.listCredentials().passwords[0].value }
          { name: 'database-url', value: 'postgresql://${pgAdminUser}:${pgAdminPassword}@${postgres.properties.fullyQualifiedDomainName}:5432/beacon?sslmode=require' }
        ],
        !empty(roboflowApiKey) ? [{ name: 'roboflow-api-key', value: roboflowApiKey }] : [],
        !empty(sendgridApiKey) ? [{ name: 'sendgrid-api-key', value: sendgridApiKey }] : []
      )
    }
    template: {
      containers: [{
        name: 'api'
        // Placeholder until the first `az acr build` — replaced by deploy.ps1.
        image: 'mcr.microsoft.com/k8se/quickstart:latest'
        resources: { cpu: json('0.5'), memory: '1Gi' }
        env: concat(
          [
            { name: 'DATABASE_URL', secretRef: 'database-url' }
            { name: 'KEY_VAULT_URI', value: keyVault.properties.vaultUri }
            { name: 'AZURE_STORAGE_ACCOUNT', value: storage.name }
            { name: 'VISION_BACKEND', value: 'hosted' }
          ],
          !empty(roboflowApiKey) ? [{ name: 'ROBOFLOW_API_KEY', secretRef: 'roboflow-api-key' }] : [],
          !empty(sendgridApiKey) ? [
            { name: 'EMAIL_PROVIDER', value: 'sendgrid' }
            { name: 'SENDGRID_API_KEY', secretRef: 'sendgrid-api-key' }
            { name: 'ESCALATION_FROM', value: escalationFrom }
            { name: 'ESCALATION_TO', value: escalationTo }
          ] : []
        )
      }]
      scale: { minReplicas: 1, maxReplicas: 3 }
    }
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// NOTE: this used to also deploy two standalone vision Container Apps
// (plate/weapon, calling Roboflow *workflows*). Removed — server/src/vision/
// detectors.py replaced them: it calls the underlying Roboflow model directly
// (detect.roboflow.com) instead of the workflow wrapper, measured 3.5x faster
// (1.05s vs 3.7-7.0s) because it skips server-side box rendering nobody used.
// The API app above is the only vision compute now; ROBOFLOW_API_KEY on it is
// what vision detection actually needs.
// ─────────────────────────────────────────────────────────────────────────────

// ─────────────────────────────────────────────────────────────────────────────
// Nightly re-scoring job — same image as the API, on a cron.
// 02:00 UTC = 04:00 SAST, after the day's claims have landed and before anyone
// opens the dashboard.
// ─────────────────────────────────────────────────────────────────────────────
resource rescoreJob 'Microsoft.App/jobs@2024-03-01' = {
  name: '${prefix}-rescore'
  location: location
  tags: tags
  properties: {
    environmentId: containerEnv.id
    configuration: {
      triggerType: 'Schedule'
      scheduleTriggerConfig: {
        cronExpression: '0 2 * * *'
        parallelism: 1
        replicaCompletionCount: 1
      }
      replicaTimeout: 1800
      replicaRetryLimit: 1
      registries: [{
        server: acr.properties.loginServer
        username: acr.name
        passwordSecretRef: 'acr-password'
      }]
      secrets: [
        { name: 'acr-password', value: acr.listCredentials().passwords[0].value }
        { name: 'database-url', value: 'postgresql://${pgAdminUser}:${pgAdminPassword}@${postgres.properties.fullyQualifiedDomainName}:5432/beacon?sslmode=require' }
      ]
    }
    template: {
      containers: [{
        name: 'rescore'
        image: 'mcr.microsoft.com/k8se/quickstart:latest'
        command: ['python', '-m', 'scripts.rescore']
        resources: { cpu: json('0.5'), memory: '1Gi' }
        env: [{ name: 'DATABASE_URL', secretRef: 'database-url' }]
      }]
    }
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Static Web Apps — member app and ops console.
// Free tier. SWA Free has no SLA and no custom auth, which is fine for both.
// OFF by default: confirmed by direct testing that Azure for Students cannot
// provision Microsoft.Web/staticSites in any of the five SWA-capable regions
// (centralus, eastus2, westus2, westeurope, eastasia all returned
// RequestDisallowedByAzure) — a subscription-tier block, not a region choice.
// See infra/README.md for the GitHub Pages/Vercel fallback actually in use.
// ─────────────────────────────────────────────────────────────────────────────
resource memberApp 'Microsoft.Web/staticSites@2023-12-01' = if (enableStaticWebApp) {
  name: '${prefix}-member'
  location: 'westeurope'
  tags: tags
  sku: { name: 'Free', tier: 'Free' }
  properties: { stagingEnvironmentPolicy: 'Enabled', allowConfigFileUpdates: true }
}

// ─────────────────────────────────────────────────────────────────────────────
// Optional, off by default. See the param descriptions for why.
// ─────────────────────────────────────────────────────────────────────────────
resource openAi 'Microsoft.CognitiveServices/accounts@2023-10-01-preview' = if (enableAzureOpenAI) {
  name: '${prefix}-openai-${uniq}'
  location: openAiLocation
  tags: tags
  kind: 'OpenAI'
  sku: { name: 'S0' }
  properties: {
    customSubDomainName: '${prefix}-openai-${uniq}'
    publicNetworkAccess: 'Enabled'
  }
}

resource notificationNamespace 'Microsoft.NotificationHubs/namespaces@2023-09-01' = if (enableNotificationHubs) {
  name: '${prefix}-ntfns-${uniq}'
  location: location
  tags: tags
  sku: { name: 'Free' }
}

resource notificationHub 'Microsoft.NotificationHubs/namespaces/notificationHubs@2023-09-01' = if (enableNotificationHubs) {
  parent: notificationNamespace
  name: '${prefix}-hub'
  location: location
}

// ─────────────────────────────────────────────────────────────────────────────
// Outputs. Nothing secret: hostnames and names only, so this is safe to paste
// into a chat or a PR. The connection string is assembled locally by the deploy
// script from the password you typed, and never printed.
// ─────────────────────────────────────────────────────────────────────────────
output apiFqdn string = apiApp.properties.configuration.ingress.fqdn
output memberAppHostname string = enableStaticWebApp ? memberApp.properties.defaultHostname : ''
output postgresFqdn string = postgres.properties.fullyQualifiedDomainName
output storageAccountName string = storage.name
output keyVaultUri string = keyVault.properties.vaultUri
output acrLoginServer string = acr.properties.loginServer
output acrName string = acr.name
output resourceGroupName string = resourceGroup().name
