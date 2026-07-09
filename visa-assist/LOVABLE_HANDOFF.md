# Lovable Handoff — visa-assist (Visa Form Auto-Fill)

Paste everything below into Lovable as the build prompt. The backend is **already built and deployed** on Supabase — you are building **only the frontend**, wired to existing tables and edge functions. Do **not** create new tables or rebuild the fill logic.

---

## 1. What we're building

A feature inside our CRM that fills **official government visa PDFs** with applicant data and produces a finished PDF on a **"Generate Visa Form"** click. Two parts:

- **A. Template Setup (admin, one-time per form)** — a *visual field-mapping editor*: render the real PDF, draw/confirm a box over each form field, and bind each field to a data source (CRM column, CRM detail, or "collect later").
- **B. Generate flow (per applicant)** — pick a template for a contact → prefill from CRM → **review & complete** the fields → generate the filled PDF (which is saved to the contact's documents).

The engine (PDF reading/filling) is done server-side with `pdf-lib` in Supabase Edge Functions. You call three functions and read/write one JSON field. That's it.

---

## 2. Supabase connection

- **Project URL:** `https://uwzosvzynnpbxpnwqgkm.supabase.co`
- **Publishable (anon) key:** `sb_publishable_6HXHgXwS-X6XhoP0Kat05Q_QUds8k2V`
- Auth: the logged-in user's Supabase session JWT. **All edge-function calls must include the user's `Authorization: Bearer <jwt>`** — use `supabase.functions.invoke(...)` which attaches it automatically.

---

## 3. Data model (existing tables — reuse, do not recreate)

### Templates live in `knowledge`
A visa template = one `knowledge` row.
- `id` (int), `title`, `related_country_id` (int), `tags` (contains `visa_template`), `status`.
- **`content` (text) = the field map, stored as a JSON string** (see §4). Parse on read, stringify on write.
- Discover templates: `select * from knowledge where tags ilike '%visa_template%'`.

### Template PDF lives in `knowledge_attachments`
- Rows: `id, knowledge_id, kind, file_name, mime_type, file_url`.
- The fillable PDF is the row for that `knowledge_id` with `mime_type='application/pdf'` (or `kind='visa_template_pdf'`). Use `file_url` (public) to render it.

### Applicant data
- **`contacts`** (id, first_name, last_name, full_name, email, phone, street_address, city, country, nationality, org_id, …) — identity basics.
- **`contact_secondary_details`** — an EAV table (`contact_id, field_name, field_content`) holding visa-specific data: passport number, date of birth, place of birth, passport issue/expiry, sex, marital status, etc. This is where most non-basic fields come from.
- **`applications`** (optional) — `id, applicant_contact_id, program_name, institution_name, …`.

### Generated forms land in `documents`
- The generate function inserts a row: `document_type='visa_form_generated'`, `applicant_id=<contact_id>`, `document_url=<pdf url>`, `document_name`, `org_id`.
- Show generated forms in the contact's documents tab by filtering `documents` on `applicant_id` + `document_type='visa_form_generated'`.

---

## 4. The field-map JSON schema (`knowledge.content`)

```jsonc
{
  "guidance": "free text notes about this form",
  "fields": [
    {
      "id": "Texto1",              // stable id; for acro fields == pdf_field_name
      "mode": "acro",              // "acro" (named PDF field) | "overlay" (drawn box)
      "pdf_field_name": "Texto1",  // acro only: the real AcroForm field name
      "label": "Surname(s)",       // human label (editable)
      "hint": "1. Apellido(s)/Surname(s)", // extracted nearby PDF text (read-only aid)
      "type": "text",              // text | checkbox | dropdown | radio | optionlist | unknown
      "options": null,             // string[] for dropdown/radio, else null
      "page": 0,                   // 0-based page index
      "rect": { "x": 52, "y": 204, "w": 390, "h": 24 }, // PDF POINTS, TOP-LEFT origin
      "widget_count": 1,
      "required": false,
      "collect": "crm",            // crm | interview | api | supabase | manual | skip
      "binding": {
        "source_type": "contact_column", // contact_column | contact_detail | application_column | literal | computed | api | supabase | ""
        "source_path": "last_name",
        "transform": ""            // "" | uppercase | lowercase | date:DD-MM-YYYY
      }
    }
  ]
}
```

**`collect` semantics** (drives UI colour + behaviour):
- `crm` — value comes from the binding now (CRM column/detail).
- `manual` — staff types it in the review screen.
- `interview` / `api` / `supabase` — reserved for later automated sources (treat like `manual` for now: empty, user can fill).
- `skip` — **never fill or show** (e.g. "for official use only" sections).

**`binding.source_type`:**
- `contact_column` → `source_path` is a column on `contacts` (e.g. `last_name`).
- `contact_detail` → `source_path` is a `contact_secondary_details.field_name` (e.g. `passport_number`).
- `application_column` → column on `applications`.
- `literal` → `source_path` is a constant string.
- `computed` → `source_path` is a template like `"{city}"` (placeholders filled from `contacts`).
- `""` → unbound.

---

## 5. Edge function contracts

Base: `POST https://uwzosvzynnpbxpnwqgkm.supabase.co/functions/v1/<name>` with the user JWT. Prefer `supabase.functions.invoke('<name>', { body })`.

### `visa-extract-fields` (used in Template Setup)
Reads the template PDF, writes/merges the field map into `knowledge.content` (preserves existing `label`/`binding`/`collect` and any `overlay` fields).
```ts
// body
{ knowledge_id: number, attachment_id?: number }
// response
{ success, knowledge_id, page_count, attachment:{id,file_name},
  acro_field_count, overlay_field_count, has_xfa, warning, fields:[ ...field map... ] }
```
Call this once after uploading a template PDF, and whenever you want to re-detect fields. `has_xfa: true` or `acro_field_count: 0` → the form needs **overlay mode** (draw boxes manually).

### `visa-prefill` (used in Generate flow, step 1)
Resolves bindings against the contact's data. **Returns values only, no PDF.**
```ts
// body
{ knowledge_id: number, contact_id: number, application_id?: number }
// response
{ success, knowledge_id, contact_id, application_id,
  contact:{ id, full_name }, bound_count, field_count,
  fields: [ { id, mode, pdf_field_name, label, type, required, options,
              page, rect, font_size, per_char,
              value,        // prefilled value ("" if unbound/empty)
              source,       // e.g. "contact_column:last_name"
              bound } ] }   // true if a value was resolved
```

### `visa-generate` (used in Generate flow, step 2)
Fills the PDF (acro + overlay), saves it to storage, inserts the `documents` row.
```ts
// body
{ knowledge_id: number, contact_id: number, application_id?: number,
  field_values: { [field_id: string]: string | boolean }, // keyed by field map `id`
  flatten?: boolean,        // true => non-editable output (recommended for final)
  document_name?: string,
  attachment_id?: number }
// response
{ success, document_id, url, filled, failed, skipped, errors? }
```
Value formats by `type`: text → string; checkbox → `true`/`false` (or "yes"/"on"/"1"); dropdown/radio → the option string. **Do not send `collect:'skip'` fields.**

---

## 6. Coordinate contract (critical for the visual editor)

Field `rect` is stored in **PDF points, top-left origin**. pdf.js renders top-left too, so conversion is just the viewport scale `S`:

```
// stored rect (points)  ->  on-screen box (CSS px)
left   = rect.x * S
top    = rect.y * S
width  = rect.w * S
height = rect.h * S

// drawing a NEW overlay box: screen px -> stored points
rect = { x: left/S, y: top/S, w: width/S, h: height/S }
page = <current 0-based page index>
```
`S` = the `scale` you pass to `page.getViewport({ scale: S })`. Render each page in a positioned container and absolutely-position the field boxes over it.

---

## 7. Screens to build

### A. Visa Template Setup (admin)
1. **Template list** — `knowledge` where `tags ilike '%visa_template%'`. Show title, country, and field counts (parse `content`).
2. **Editor** for a selected template:
   - Render the PDF (pdf.js / react-pdf) from the `knowledge_attachments.file_url`, page by page.
   - For each `content.fields[]` entry, draw a clickable box at its `rect`/`page` (see §6). **Colour by `collect`:** crm=green, manual=amber, interview/api/supabase=blue, skip=grey, unbound=red outline.
   - Click a box → side panel to edit: `label`, `collect`, and `binding` (`source_type` dropdown + `source_path` input; show `contacts` columns for `contact_column`, free text for `contact_detail`, etc.). Show `hint` and `type` as read-only aids.
   - **Save** → write the updated array back to `knowledge.content` (JSON.stringify). Preserve untouched fields.
   - **"Re-extract fields"** → call `visa-extract-fields` (it merges, keeping your edits).
   - **"Add overlay field"** → let the user draw a rectangle on a page → create a new field `{ mode:'overlay', id: crypto.randomUUID(), rect, page, label, type:'text', collect, binding }`. Use this for forms with no AcroForm fields, or extra boxes.

### B. Generate Visa Form (from a contact)
1. On a contact, **"Generate Visa Form"** → choose a template (optionally filter by `related_country_id` matching the contact's country).
2. Call **`visa-prefill`** → render a **review form**: fields ordered by `page` then position; group into sections.
   - Show prefilled `value` with a **source badge** (`bound` = "from CRM", else "needs input").
   - `collect:'manual'|'interview'|'api'|'supabase'` → empty editable input for staff to complete.
   - `collect:'skip'` → **hidden**.
   - Render by `type`: text input, checkbox, select (use `options`). Mark `required`.
   - (Optional, nice-to-have) live PDF preview with current values overlaid.
3. **"Generate"** → call **`visa-generate`** with `field_values` keyed by field `id` (omit skip/empty). Use `flatten: true` for the final, non-editable PDF.
4. On success: show the `url` (open/download), confirm it was saved to the contact's documents.

### C. Generated forms list
- In the contact's documents tab, show `documents` where `applicant_id = contact.id` and `document_type = 'visa_form_generated'`, with a download link (`document_url`).

---

## 8. Tech notes & gotchas

- Use **`pdfjs-dist`** (or `react-pdf`) for rendering; absolutely-positioned overlay `<div>`s for boxes.
- `knowledge.content` is a **JSON string** — always `JSON.parse` / `JSON.stringify`, and **never drop fields you didn't edit** (especially `overlay` fields and existing `binding`s).
- Coordinates are **top-left points** — multiply by the pdf.js scale (§6). Getting this wrong puts text in the wrong place.
- Value types must match field `type` (string / boolean / option string).
- Dates for the Spain form use `transform: "date:DD-MM-YYYY"` (handled server-side; you just supply the source value).
- For `contact_detail` bindings to resolve, the matching `contact_secondary_details.field_name` must exist for that contact — your review screen's `manual` inputs are how staff capture missing ones.

---

## 9. Test data (ready now)

- **Template:** `knowledge_id = 149` ("Visa Application Form", Spain, `related_country_id = 7`). Field map already seeded: **59 fields**, 10 pre-bound to CRM, positions on every field, official-use column excluded. PDF attachment = `knowledge_attachments.id = 5`.
- **Flow to verify:** pick any `contacts.id` → `visa-prefill { knowledge_id: 149, contact_id }` → review → `visa-generate` → open the returned `url` and confirm names/address/nationality are filled in the right boxes; confirm a `documents` row appears for that contact.
- Expected EAV keys used by the seed (create/capture these in `contact_secondary_details` to auto-fill): `date_of_birth`, `place_of_birth`, `passport_number`, `passport_issue_date`, `passport_expiry_date`.

---

## 10. Acceptance criteria

- [ ] Template list shows visa templates from `knowledge`.
- [ ] Editor renders the Spain PDF with clickable boxes correctly positioned over the real fields (all 6 pages).
- [ ] Editing a field's label/collect/binding and saving persists to `knowledge.content` without losing other fields.
- [ ] "Add overlay field" creates a correctly-positioned box that fills at the right place on generate.
- [ ] From a contact, prefill returns values; review screen shows prefilled + empty fields with source badges; skip fields hidden.
- [ ] Generate produces a downloadable filled PDF and a `documents` row on the contact.
- [ ] All function calls send the user JWT and succeed (no 401).

---

## 11. Build the review screen to extend into v2 (guided interview) — don't paint yourself into a corner

In **v2** the same fields become a **guided interview**: instead of one long review form, the applicant/staff is walked through fields in ordered steps with conditional logic, and answers are saved back to the CRM. The v1 review screen and the v2 interview are **the same field list, presented differently** — so build v1 so v2 is a re-skin, not a rewrite.

Do these now (cheap), so v2 is additive:

- **Drive the screen entirely from the `visa-prefill` field array** — no hardcoded field lists. Render via one reusable component: `<FieldInput field value onChange />` that switches on `field.type` (text/checkbox/select). Both the v1 flat review and the v2 one-field-per-step interview will reuse it unchanged.
- **Keep answers in a single state object keyed by `field.id`** (`{ [id]: value }`) — this is exactly the `field_values` shape `visa-generate` expects, and also what an interview accumulates step by step.
- **Respect these optional field properties if present** (ignore-if-absent in v1, used heavily in v2):
  - `section` (string) and `step` (number) — for grouping/ordering into interview pages. In v1, group by `section` if present, else by `page`.
  - `visible_if` (e.g. `{ field_id, equals }`) — conditional visibility. In v1, honour it if present (hide the field unless the condition is met); in v2 it drives interview branching.
  - `help` (string) — guidance text shown under the field.
- **Treat `collect` as the interview driver:** v2's interview collects the `interview` (and `manual`) fields; `crm`-bound fields are pre-answered and only surfaced for confirmation; `skip` never appears. Build v1 so the field's `collect` value controls how it's shown — don't special-case by hardcoding field ids.
- **Support a draft/resume save (stub is fine in v1):** persist the in-progress `{ [id]: value }` so a partial interview can be resumed. v1 can keep it in component state/localStorage; v2 will persist it server-side. Just keep the answers object serialisable and separate from UI state.
- **On generate, plan for write-back (v2):** v2 will write collected `manual`/`interview` answers back into `contact_secondary_details` (EAV, keyed by the binding's `source_path`) so each applicant is captured once and auto-prefills next time. Don't implement now — but keep each answer's originating `field` (with its `binding.source_path`) available at generate time so this is a small addition later.

Net: if v1 renders the review from the field array via a reusable `<FieldInput>`, keeps a `{id: value}` answers object, and honours optional `section`/`step`/`visible_if`, then v2 = paginate the same fields into steps + persist drafts + write-back. No structural change.
