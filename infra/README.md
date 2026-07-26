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

**4. This Azure for Students subscription cannot deploy in South Africa North,
and cannot deploy Static Web Apps at all.** Confirmed by direct testing, not
assumption:
- `southafricanorth` is blocked by a subscription-level "best available
  regions" policy for Storage, ACR, Postgres, and Key Vault
  (`RequestDisallowedByAzure`). The actual deploy used **`francecentral`**
  instead — still EU data residency, just not in-country. Say this plainly in
  the pitch: data lives in the EU (France), not South Africa, because of a
  subscription restriction, not a design choice.
- `Microsoft.Web/staticSites` (Static Web Apps) is blocked in **every** one of
  its five supported regions on this subscription (centralus, eastus2,
  westus2, westeurope, eastasia all returned the identical
  `RequestDisallowedByAzure`) — a resource-type block, not a location problem.
  `enableStaticWebApp` defaults to `false` in `main.bicep` because of this.
  The member app and ops console are hosted on a free non-Azure static host
  instead (GitHub Pages or Vercel) — pick one when it's time to actually
  publish them; nothing here depends on which. Flip `enableStaticWebApp=true`
  only if this subscription is ever upgraded off the student plan.

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

Then enable PostGIS once. If you have `psql` locally:

```bash
psql "host=<pg-fqdn> port=5432 dbname=beacon user=beaconadmin sslmode=require" -c "CREATE EXTENSION IF NOT EXISTS postgis;"
```

If you don't, the `rdbms-connect` az CLI extension does it without a local
Postgres client:

```bash
az extension add --name rdbms-connect --yes
az postgres flexible-server execute \
  --name <server-name> --admin-user beaconadmin --admin-password <password> \
  --database-name beacon --querytext "CREATE EXTENSION IF NOT EXISTS postgis;"
```

Finally paste the printed values into `server/.env` (gitignored — keep it that way).

### Vision + email keys (Roboflow, SendGrid)

`deploy.ps1` also prompts for these — blank is valid, it just leaves vision
detection / escalation email unwired on the deployed API until you supply
them. To set them later without a full redeploy:

```powershell
./infra/set-vision-secrets.ps1 -ResourceGroup beacon-rg
```

Same non-echo, non-history handling as the Postgres password — run it
yourself, on your own machine, with your own keys.

Note there is no separate vision Container App to deploy: `server/src/vision/
detectors.py` calls Roboflow's hosted model directly from inside the API
container. An earlier version of this template provisioned two standalone
vision services (`vision/backend`, `vision/weapen_backend`) — removed, they
called Roboflow *workflows* instead of the model directly, which also render
an annotated image server-side that nothing here uses; measured 3.5x slower
(3.7-7.0s vs 1.05s) for no benefit.

---

## What gets created, and why each tier

| Resource | Tier | Scales to zero? | Note |
|---|---|---|---|
| Postgres Flexible Server | B1ms Burstable, 32 GB | **No** | PostGIS allow-listed via `azure.extensions`. The one real cost. |
| Container App — API/WS | 0.5 vCPU, `minReplicas: 1` | **No, deliberately** | A WebSocket to a scaled-to-zero app is a connection to nothing. The cold start would land exactly on the first alert. Vision detection runs inside this app too — no separate vision Container App, see above. |
| Container Apps Job — rescore | cron `0 2 * * *` | n/a | 02:00 UTC = 04:00 SAST. Same image as the API. |
| Static Web App | Free | n/a | **Off by default** (`enableStaticWebApp=false`) — blocked on this subscription in all 5 supported regions, see landmine #4 above. Member app + ops console instead hosted on GitHub Pages/Vercel. |
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
