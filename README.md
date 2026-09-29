# Zoho Books Reports MCP (read-only)

A cloud-hosted MCP server for ChatGPT/Composio to read Zoho Books data. It is intentionally read-only.

## What it exposes

- `list_organizations`
- `list_invoices`
- `list_credit_notes`
- `list_customer_payments`
- `list_contacts`
- `list_items`
- `list_sales_orders`
- `list_sales_receipts`
- `zoho_books_read` — advanced GET-only access to other Zoho Books v3 endpoints

The generic GET tool is useful for report endpoints that are not yet wrapped as dedicated MCP tools.

## 1. Create Zoho OAuth credentials

Create a Zoho OAuth client in the Zoho API Console for the India data center. Use only the scopes you need. Suggested read-only scopes:

- `ZohoBooks.invoices.READ`
- `ZohoBooks.creditnotes.READ`
- `ZohoBooks.customerpayments.READ`
- `ZohoBooks.contacts.READ`
- `ZohoBooks.salesorders.READ`
- `ZohoBooks.settings.READ`
- `ZohoBooks.reports.READ`

You need a long-lived **refresh token**, plus the client ID and client secret.

Do not put secrets in the source code or send them in chat. Add them only as secret environment variables in your cloud host.

## 2. Deploy to Render

1. Put these files in a private GitHub repository.
2. In Render, create a new Web Service from that repository.
3. Build command: `pip install -r requirements.txt`
4. Start command: `uvicorn server:app --host 0.0.0.0 --port $PORT --proxy-headers`
5. Add environment variables:
   - `ZOHO_DC=in`
   - `ZOHO_ORG_ID=<your org id>`
   - `ZOHO_CLIENT_ID=<secret>`
   - `ZOHO_CLIENT_SECRET=<secret>`
   - `ZOHO_REFRESH_TOKEN=<secret>`
   - `ALLOWED_HOST=<your Render hostname, without https://>`
6. Deploy.

Your MCP URL will be:

`https://YOUR-SERVICE.onrender.com/mcp`

## 3. Connect in Composio

In **Add Custom MCP**:

- Display name: `Zoho Books Reports`
- MCP server URL: `https://YOUR-SERVICE.onrender.com/mcp`
- Authentication: choose the authentication method that your deployment is configured to require.

This starter package keeps Zoho OAuth credentials on the server and does not yet implement separate client authentication for the MCP endpoint. For a private test deployment, restrict access at the cloud/network layer. Before broader or team use, add bearer-token or OAuth protection to the MCP endpoint.

## 4. Test

After Composio can see the tools, try:

- `List my Zoho Books organizations.`
- `Show invoices from 2026-09-01 to 2026-09-30.`
- `Read the inventory aging report if the Zoho report endpoint is available.`

## Important limitation about Inventory Aging

Zoho Books' UI includes Inventory Aging reports, but the exact public API endpoint is not consistently documented/exposed in the standard connector. The `zoho_books_read` tool is included so a verified report path can be added without redeploying new code. If Zoho does not expose Inventory Aging through the public API for your edition, the fallback is a Zoho Deluge/custom-function endpoint that returns the report as JSON, and this MCP can call that endpoint through an additional tool.

## Security

- Read-only by design: this server only sends HTTP GET requests to Zoho Books.
- Never commit `.env`, client secrets, or refresh tokens.
- Use a private repository.
- Protect the deployed `/mcp` endpoint before production/team use.
