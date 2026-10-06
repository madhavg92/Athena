# Draft email to IT (Shivesh): access for the Athena pilot

**To:** Shivesh (IT)
**From:** Madhav
**Subject:** Athena pilot: Azure, Entra and Teams setup (read-only)

Hi Shivesh,

We have built Athena, an internal assistant for managers. It reads our work systems, alerts the right manager in Teams when something needs action, and answers questions with sources. It has been built and tested on synthetic data. To run a small pilot (about 6 managers) we need the items below. Everything is read-only: Athena never writes to Smartsheet, SharePoint or any other system, never sends anything outside Anka, and does not read email or Teams chats.

**1. Azure (one resource group for the pilot)**
- Resource group in our subscription, region of your choice.
- Function App (Python 3.11, Linux; Flex Consumption or Premium), with a system-assigned managed identity.
- Azure Database for PostgreSQL – Flexible Server (small tier), reachable only from the Function App.
- Key Vault for all secrets; Application Insights for logs.
- I will deploy the code myself; I need Contributor on the resource group.

**2. Entra app registration for Microsoft Graph (read-only)**
- Application permission `User.Read.All` (to map Teams users to our owner list).
- `Sites.Selected`, with read grants only on the SharePoint sites we agree (list to follow). Please confirm those sites hold no patient data.
- Delegated permissions for Teams single sign-on with on-behalf-of, so document search only returns what each user may already see.
- Delegated `Calendars.Read` for pilot users only, so Athena can prepare a pre-read before each meeting. It reads the meeting title, time and attendees; not the body or attachments.
- Admin consent for the above.

**3. Teams bot**
- Azure Bot resource (single tenant) with its own app registration; messaging endpoint `https://<function-app>.azurewebsites.net/api/messages`.
- Permission to upload a custom Teams app and install it for the pilot users only.

**4. Details I need back**
- Tenant ID, the app IDs, and where the secrets are in Key Vault (not by email, please).
- Our internal email domains, for the allow list.

The full technical runbook is in the repo (`docs/RUNBOOK.md`, sections 3–5). Happy to walk through it in 20 minutes.

Thanks,
Madhav
