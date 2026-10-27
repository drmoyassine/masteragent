"""
test_ingestion_placeholder.py — voice-note placeholder strip (escalation #871).

Pure-function coverage only (no app boot): enrichment is append-only, so the
leading '[Sent|Incoming voice note — transcript pending]' placeholder that
n8nclaw posts as the whole content must be dropped exactly once a transcript
has landed (parsed_content marker), and never otherwise.
"""
from memory_system.ingest.ingestion import _strip_pending_voice_note_placeholder as strip

ENRICHED_INCOMING = (
    "[Incoming voice note — transcript pending]"
    "\n\n---\n[Attachment (audio/ogg): voice_note.ogg]\ntranscript body"
)
ENRICHED_SENT_HYPHEN = (
    "[Sent voice note - transcript pending]"
    "\n\n---\n[Attachment (audio/x-wav): note.wav]\ntranscript body"
)


def test_strips_incoming_variant_em_dash():
    out = strip(ENRICHED_INCOMING, [{"parsed_content": "transcript body"}])
    assert out == "---\n[Attachment (audio/ogg): voice_note.ogg]\ntranscript body"


def test_strips_sent_variant_hyphen():
    out = strip(ENRICHED_SENT_HYPHEN, [{"parsed_content": "transcript body"}])
    assert out == "---\n[Attachment (audio/x-wav): note.wav]\ntranscript body"


def test_no_transcript_placeholder_stays():
    # Enrichment failed or hasn't landed: the placeholder IS the content — keep it.
    assert strip("[Incoming voice note — transcript pending]", [{"parse_failed": True}]) == \
        "[Incoming voice note — transcript pending]"


def test_idempotent_on_clean_content():
    once = strip(ENRICHED_INCOMING, [{"parsed_content": "transcript body"}])
    assert strip(once, [{"parsed_content": "transcript body"}]) == once


def test_non_voice_content_untouched():
    assert strip("Regular message body", [{"parsed_content": "doc text"}]) == \
        "Regular message body"


def test_placeholder_not_leading_is_untouched():
    body = "prefix text\n[Incoming voice note — transcript pending]\nmore"
    assert strip(body, [{"parsed_content": "x"}]) == body


def test_gate_requires_dict_attachment_with_parsed_content():
    # parse_failed alone, non-dict junk, or empty refs must not trigger the strip
    assert strip(ENRICHED_INCOMING, [{"parse_failed": True}]) == ENRICHED_INCOMING
    assert strip(ENRICHED_INCOMING, ["junk"]) == ENRICHED_INCOMING
    assert strip(ENRICHED_INCOMING, []) == ENRICHED_INCOMING
    assert strip(ENRICHED_INCOMING, [{"parsed_content": ""}]) == ENRICHED_INCOMING


def test_unsettled_attachment_keeps_placeholder():
    # fetch_error = retriable, no marker yet: a later duplicate delivery can
    # still append the voice block, so the placeholder must survive for now.
    assert strip(ENRICHED_INCOMING, [{"fetch_error": "timeout"}]) == ENRICHED_INCOMING
    assert strip(
        ENRICHED_INCOMING,
        [{"parsed_content": "doc text"}, {"fetch_error": "timeout"}],
    ) == ENRICHED_INCOMING


def test_mixed_settled_attachments_strip():
    # One parsed + one permanently failed: nothing more can land, strip.
    out = strip(ENRICHED_INCOMING, [{"parsed_content": "doc text"}, {"parse_failed": True}])
    assert out == "---\n[Attachment (audio/ogg): voice_note.ogg]\ntranscript body"


def test_strip_refuses_to_empty_content():
    # Externally-clobbered row (marker present, block gone): keep placeholder
    # rather than saving an empty string.
    assert strip("[Incoming voice note — transcript pending]", [{"parsed_content": "x"}]) == \
        "[Incoming voice note — transcript pending]"


def test_strip_refuses_whitespace_only_remainder():
    # Companion to the empty refusal: a remainder of just whitespace must not
    # be saved either — the guard is stripped.strip(), not bare truthiness, so
    # an externally-clobbered row keeps its placeholder over a blank string.
    body = "[Incoming voice note — transcript pending]  \n\t "
    assert strip(body, [{"parsed_content": "x"}]) == body
