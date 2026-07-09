# Chatwoot WhatsApp Template Sender (Cloudflare Worker)

A Chatwoot **Dashboard App**: an embedded panel inside each conversation where an
agent picks an approved WhatsApp template, fills its parameters, and sends it via
360dialog. Built to give deliberate, manual template control (vs. the bridge's
automatic window-closed fallback).

## Architecture

```
Chatwoot conversation
  └─ "Send Template" dashboard-app tab  (this Worker's HTML)
       ├─ reads appContext via postMessage → conversation_id, contact phone + name
       ├─ GET  /api/templates  ─► Worker ─► n8n wa-tmpl-list   ─► wa_templates table
       └─ POST /api/send       ─► Worker ─► n8n wa-tmpl-send   ─► send_wa_template
                                                                   (explicit mode,
                                                                    AI skipped)
                                                                ─► 360dialog + Chatwoot copy
```

- **Worker** = UI + thin proxy. Holds the n8n webhook URLs server-side so they
  never reach the browser; the form only calls the Worker's own `/api/*`.
- **n8n `wa_template_picker_api`** (id `UP0GDYIIsick3VeZ`) = the two webhooks.
- **n8n `send_wa_template`** (id `AZtptov0hlSDZlKG`) = the single shared send
  engine. In **explicit mode** (`params_json` set, `skip_ai=true`) it uses the
  agent's typed values verbatim and bypasses the Gemini AI-restructure step.

## Deploy

```bash
cd chatwoot-template-sender
npm i -g wrangler      # if needed
wrangler login         # your Cloudflare account
wrangler deploy
```

Deploy prints a URL like `https://chatwoot-template-sender.<subdomain>.workers.dev`.
(Or bind a custom route/domain in the CF dashboard.)

## Register in Chatwoot

Settings → Integrations → **Dashboard Apps** → New:
- **Name:** Send Template
- **Endpoint:** the Worker URL

It then appears as a tab in every conversation. (Can also be created via the
Chatwoot API: `POST /api/v1/accounts/2/dashboard_apps` with `{title, content:[{type:'frame', url}]}`.)

## Security notes (v1)

- Auth is the unguessable n8n webhook paths (same pattern as the existing
  outbound bridge). The browser never sees them.
- The Worker URL itself is open — anyone with it can load the form and POST a
  send. For a staff-only tool this is low risk, but the clean hardening is to put
  the Worker behind **Cloudflare Access (Zero Trust)** so only authenticated
  staff can reach it. Recommended before wide rollout.

## Endpoints (n8n)

- List: `GET  https://api.studygram.me/webhook/wa-tmpl-list-Qx7m2Kp9vT`
- Send: `POST https://api.studygram.me/webhook/wa-tmpl-send-Zr4n8Tj6wB`
  body: `{ conversation_id, recipient_phone, recipient_name, sender_name, template_name, language, params:{<var>:<value>} }`

## Adding templates / languages

Approve the template (with **named** placeholders) in 360dialog, then add a row
to the `wa_templates` data table (id `OTNwOgozEd4myO9V`) with its real
`variables` structure (`[{name, component}]`). It appears in the dropdown
automatically — no Worker or workflow change.
