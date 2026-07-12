# Knowledge Authoring and Document Ingestion

## Outcome

The knowledge-table Create modal supports the five knowledge categories with
category-aware structured fields. Skills and playbooks are stored in the shared
SKILL.md-compatible representation; declarative categories retain their normal
knowledge content plus structured metadata.

Users can upload PDF, DOCX, XLSX, TXT, Markdown, and CSV sources. Uploads are
staged privately, extracted by the existing document/vision pipeline, reviewed,
and optionally sent to a category-aware LLM to produce an editable proposal.
Creation remains an explicit user action and links the original sources as
provenance.

## Safety boundaries

- Uploads are limited to 25 MB each and a bounded extraction limit of 200 PDF pages.
- Legacy synchronous document parsing keeps its three-page behavior for compatibility.
- Text-native PDF pages use local text extraction; vision/OCR is used for image pages.
- Attachment binaries are stored separately from the knowledge row.
- Agent retrieval returns canonical knowledge, not raw document binaries.
- Staged attachments expire after 24 hours unless linked to a knowledge record.
- Draft/Approved is the user-facing activation language; `active` remains the compatible database value.

## Workflow

1. Select a category and enter or upload source material.
2. Wait for extraction status to become ready; review warnings and extracted text.
3. Insert extracted text or generate an editable category-aware proposal.
4. Complete or edit the structured contract fields, facets, signals, tags, and content.
5. Save as Draft or Approved.
6. The server creates the canonical embedding and links the source attachments for administrator review.

## Follow-up hardening

- Add a dedicated extraction progress dashboard and cleanup job for expired staged files.
- Add page/sheet-level source traceability in the modal.
- Add encrypted object storage when document volume makes PostgreSQL BYTEA storage unsuitable.
- Add document chunk embeddings for direct source-document retrieval; canonical knowledge remains the default retrieval unit.
