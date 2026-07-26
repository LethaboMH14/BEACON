# BEACON on Azure — runbook

Everything here is templates and scripts. **You** run `az login` and the deploy;
no one else needs your subscription credentials, and none are stored in this repo.

---

## Before you start — three things that will bite you

**1. Azure OpenAI is off by default, and probably unavailable to you.**
Azure for Students subscriptions generally cannot create an Azure OpenAI
resource without a separate access application, and **South Africa North does
not host Azure OpenAI at all**. That second point matters more than the first:
the architecture picked SA North *for data residency* — so member location and
claims context stay in-country — and there is no version of Azure OpenAI that
satisfies that today. If you turn it on, prompts leave the country. Decide that
deliberately, and say so in the pitch rather than letting the diagram imply
something untrue. `enableAzureOpenAI=false` until then.

**2. Postgres cannot scale to zero.** Everything else in this deployment costs
roughly nothing when idle. Postgres Burstable B1ms runs about **$13–15/month**
if you leave it on — a meaningful slice of a $100 credit. Stop it between
sessions:

```bash
az postgres flexible-server stop -g beacon-rg -n <server-name>
```

**3. SendGrid will reject your first send** unless you have completed **Single
Sender Verification** (Settings → Sender Authentication). Do that before the
demo, not during it.

---

## Deploy

```bash
az login
```

```powershell
./infra/deploy.ps1 -ResourceGroup beacon-rg
```

Takes about 10 minutes, nearly all of it Postgres. The script prompts for the
Postgres admin password as a SecureString — it is never written to disk, never
echoed, and never printed back at the end. Put it in your password manager when
you type it.

Then enable PostGIS once:

```bash
psql "host=<pg-fqdn> port=5432 dbname=beacon user=beaconadmin sslmode=require" -c "CREATE EXTENSION IF NOT EXISTS postgis;"
```

Finally paste the printed values into `server/.env` (gitignored — keep it that way).

---

## What gets created, and why each tier

| Resource | Tier | Scales to zero? | Note |
|---|---|---|---|
| Postgres Flexible Server | B1ms Burstable, 32 GB | **No** | PostGIS allow-listed via `azure.extensions`. The one real cost. |
| Container App — API/WS | 0.5 vCPU, `minReplicas: 1` | **No, deliberately** | A WebSocket to a scaled-to-zero app is a connection to nothing. The cold start would land exactly on the first alert. |
| Container Apps — vision ×2 | 1 vCPU / 2 GB, `minReplicas: 0` | Yes | Internal ingress only — public would let anyone spend our Roboflow quota. 2 GB because local weights OOM at 1 GB. |
| Container Apps Job — rescore | cron `0 2 * * *` | n/a | 02:00 UTC = 04:00 SAST. Same image as the API. |
| Static Web App | Free | n/a | Member app + ops console. |
| Blob Storage | Standard_LRS | n/a | `clips` and `evidence`, both private. Versioning on. |
| Key Vault | Standard, RBAC | n/a | Repo is public; nothing lives in it. |
| ACR | Basic | n/a | `az acr build` builds in Azure — no local Docker needed. |
| Log Analytics | 1 GB/day cap | n/a | The cap exists so a log flood can't drain the credit. |
| Azure OpenAI | S0 | n/a | **Off.** See above. |
| Notification Hubs | Free | n/a | **Off** until there's a mobile build to receive pushes. |
| Web PubSub | — | — | **Not deployed.** Named as the documented next step past a few thousand concurrent WS connections. Don't build it yet. |

---

## Cost control

```bash
# stop the database when you're done for the day
az postgres flexible-server stop -g beacon-rg -n <server-name>

# what you've actually spent
az consumption usage list --output table

# tear the whole thing down
az group delete --name beacon-rg --yes
```

The resource group is the blast radius: everything is tagged `project=BEACON`
and lives in one group, so `az group delete` is a complete, clean removal.

---

## Useful flags

```powershell
./infra/deploy.ps1 -InfraOnly     # skip image builds
./infra/deploy.ps1 -SkipImages    # deploy infra, update apps later
```
