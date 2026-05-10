#!/usr/bin/env python3
"""
Generate vCon-26 — a webchat → voice escalation case.

Customer (Diane Metzger) starts on Helix's web chat about a duplicate
billing charge.  After a few messages the agent (Naomi Sayid, who
already appears on vCon-11) suggests a voice call.  The customer calls
in, gets routed back to Naomi, authenticates a new card on file
(PCI-redacted), confirms her email (PII-redacted), and the renewal of
service is processed.

Demonstrates: CC extension; WTF transcript with redactions; explicit
consent attachment; SCITT lifecycle covering both the chat and the
voice segments. Reuses Naomi's tel +1-737-555-0101 so the Top phone
numbers chart on the dashboard now has a number with count=2.
"""

import json, os, uuid, hashlib
from datetime import datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
NS   = uuid.UUID("11111111-2222-3333-4444-555555555555")

slug = "26-cc-webchat-to-voice-escalation"

agent  = {
    "name":       "Agent — Naomi Sayid",
    "tel":        "+1-737-555-0101",          # SAME number as vCon-11 (count -> 2)
    "mailto":     "naomi.sayid@helix.example",
    "timezone":   "America/Chicago",
    "role":       "agent",
}
customer = {
    "name":       "Customer — Diane Metzger",
    "tel":        "+1-415-555-0388",
    "mailto":     "diane.metzger@example.com",
    "timezone":   "America/Los_Angeles",
    "role":       "customer",
}

# Timeline -----------------------------------------------------------------
chat_start  = datetime(2026, 5, 6, 16, 12,  0, tzinfo=timezone.utc)
voice_start = datetime(2026, 5, 6, 16, 28, 30, tzinfo=timezone.utc)  # ~16 min later
voice_dur   = 286.4

INTERACTION_ID = "INT-OMNI-44219"
CAMPAIGN       = "billing-inbound"
SKILL          = "billing-tier2"

cc_fields = {
    "interaction_id":   INTERACTION_ID,
    "campaign":         CAMPAIGN,
    "skill":            SKILL,
}

def chat(idx, who, text, offset_seconds):
    """One webchat message dialog."""
    d = {
        "type":              "text",
        "start":             (chat_start + timedelta(seconds=offset_seconds)).replace(microsecond=0).isoformat(),
        "parties":           [0, 1],
        "originator":        0 if who == "agent" else 1,
        "mediatype":         "text/plain",
        "body":              text,
        "encoding":          "none",
        "interaction_type":  "webchat",
    }
    d.update(cc_fields)
    return d

# --- Webchat segment ---
chat_dialogs = [
    chat(0, "customer", "Hi — I see two identical charges on my April invoice for $284. Can someone help?", 0),
    chat(1, "agent",    "Hi Diane, I'm Naomi — sorry about that. Can I have your account email so I can pull up the invoice?", 32),
    chat(2, "customer", "diane.metzger@example.com", 71),
    chat(3, "agent",    "Thanks. I can see a duplicate prorate from the seat-count change on the 12th. There's a credit memo workflow I'd rather walk through on a quick call so we don't bounce links back and forth — okay if I send you our number?", 102),
    chat(4, "customer", "Sure.", 165),
    chat(5, "agent",    "Great — call +1-737-555-0101 and quote ticket BL-44219, you'll route straight back to me.", 180),
    chat(6, "customer", "On my way.", 220),
]

# --- Voice segment ---
voice_dialog = {
    "type":         "recording",
    "start":        voice_start.replace(microsecond=0).isoformat(),
    "duration":     voice_dur,
    "parties":      [0, 1],
    "originator":   1,                  # customer dials in
    "mediatype":    "audio/mp4",        # .m4a — AAC in MP4
    "filename":     f"{slug}.m4a",
    "url":          f"https://media.vcon.example.net/{slug}.m4a",
    "content_hash": "sha512-" + hashlib.sha512(slug.encode()).hexdigest(),
    "alg":          "SHA-512",
    "disposition":  "answered",
    "interaction_type": "voice",
    **{k:v for k,v in cc_fields.items() if k != "interaction_type"},
}

dialog = chat_dialogs + [voice_dialog]

# --- WTF transcript for the voice dialog only ---
wtf = {
    "wtf_version": "1.0",
    "provider":    {"name":"Deepgram", "model":"nova-3", "language":"en-US"},
    "channels":    2,
    "speakers": [
        {"speaker":"S0", "party": 0, "role":"agent",    "talk_time_s": 132.0},
        {"speaker":"S1", "party": 1, "role":"customer", "talk_time_s": 148.0},
    ],
    "segments": [
        {"start":  1.6, "end":  6.4, "speaker":"S0",
         "text":"Helix billing, this is Naomi — I see we were just chatting."},
        {"start":  6.7, "end": 11.5, "speaker":"S1",
         "text":"Yes, you said to mention BL-44219."},
        {"start": 11.7, "end": 22.0, "speaker":"S0",
         "text":"Got it. Quick recording disclosure: this call is recorded for QA, transcripts may be reviewed. Okay to proceed?"},
        {"start": 22.2, "end": 24.4, "speaker":"S1",
         "text":"Yes, that's fine."},
        {"start": 24.6, "end": 41.8, "speaker":"S0",
         "text":"Great. I've issued credit memo CM-44219 for $284. Want to apply it to next month or refund to the card on file? If you'd rather refund to a different card, give me the new one."},
        {"start": 42.0, "end": 47.5, "speaker":"S1",
         "text":"Refund to a new card — let me read it out."},
        # PCI window
        {"start": 47.7, "end": 78.6, "speaker":"S1",
         "text":"[REDACTED:PCI]", "redaction":"pci"},
        {"start": 78.8, "end": 84.9, "speaker":"S0",
         "text":"Got it — confirming the email for the refund receipt."},
        # PII window
        {"start": 85.1, "end": 89.4, "speaker":"S1",
         "text":"[REDACTED:PII-email]", "redaction":"pii"},
        {"start": 89.6, "end":102.2, "speaker":"S0",
         "text":"Perfect — refund will hit in 3–5 business days, you'll get a confirmation email shortly. Anything else?"},
        {"start":102.4, "end":104.8, "speaker":"S1",
         "text":"That's all, thanks Naomi."},
    ],
    "quality": {"overall_confidence": 0.92, "redaction_applied": True},
}

analysis = [
    {
        "type":      "transcript",
        "dialog":    [7],          # voice dialog index
        "vendor":    "Deepgram", "product": "Nova-3",
        "schema":    "WTF/1.0",
        "mediatype": "application/json", "encoding": "json",
        "filename":  f"{slug}-wtf.json",
        "body":      json.dumps(wtf),
    },
    {
        "type":      "summary",
        "dialog":    list(range(len(dialog))),  # whole conversation, chat + voice
        "vendor":    "Anthropic", "product": "Claude Sonnet 4.6",
        "mediatype": "text/plain", "encoding": "none",
        "body":      "Customer reported a duplicate $284 prorate on the April invoice via web chat (BL-44219). Agent Naomi authenticated her by email, escalated to a voice call for the refund workflow, captured explicit recording consent, processed credit memo CM-44219 with refund to a new card. PCI (card number) and PII (email) segments redacted from the transcript and recording.",
    },
    {
        "type":      "redaction_log",
        "dialog":    [7],
        "vendor":    "Helix", "product": "Redactor v2",
        "mediatype": "application/json", "encoding": "json",
        "body": json.dumps([
            {"start": 47.7, "end": 78.6, "category": "PCI",       "reason": "card-number-spoken"},
            {"start": 85.1, "end": 89.4, "category": "PII-email", "reason": "email-spoken"},
        ]),
    },
]

# --- Consent attachment (per draft-howe-vcon-consent) ---
consent_payload = {
    "consent_version": "vCon-Consent/0.1",
    "expires_at": (voice_start + timedelta(days=365)).replace(microsecond=0).isoformat(),
    "parties": [1],
    "dialog":  [7],
    "consents": [
        {"purpose": "recording",         "granted": True,
         "granted_at": (voice_start + timedelta(seconds=24)).replace(microsecond=0).isoformat()},
        {"purpose": "transcription",     "granted": True,
         "granted_at": (voice_start + timedelta(seconds=24)).replace(microsecond=0).isoformat()},
        {"purpose": "qa_review",         "granted": True,
         "granted_at": (voice_start + timedelta(seconds=24)).replace(microsecond=0).isoformat()},
        {"purpose": "ai_training",       "granted": False},
        {"purpose": "third_party_share", "granted": False},
    ],
    "ai_preferences": {"allow_inference": True, "allow_training": False},
    "scitt_receipt": {
        "transparency_service": "https://scitt.example.org/v1",
        "receipt_id":           "urn:scitt:receipt:01HZR1B8",
    },
}

# --- Lifecycle attachment covering chat + voice + redactions ---
def iso(dt): return dt.replace(microsecond=0).isoformat()
lifecycle = {
    "lifecycle_version":     "vCon-Lifecycle-SCITT/0.1",
    "transparency_service":  "https://scitt.example.org/v1",
    "events": [
        {"event":"vcon_created",       "at": iso(chat_start - timedelta(seconds=2)),
         "actor":"helix-chat-edge",     "receipt":"urn:scitt:receipt:01HZR1A2"},
        {"event":"chat_started",       "at": iso(chat_start),
         "actor":"helix-chat-edge",     "receipt":"urn:scitt:receipt:01HZR1A4"},
        {"event":"chat_completed",     "at": iso(chat_start + timedelta(seconds=240)),
         "actor":"helix-chat-edge",     "receipt":"urn:scitt:receipt:01HZR1A9"},
        {"event":"call_started",       "at": iso(voice_start),
         "actor":"helix-recorder-edge1","receipt":"urn:scitt:receipt:01HZR1B0"},
        {"event":"consent_captured",   "at": iso(voice_start + timedelta(seconds=24)),
         "actor":"helix-consent-svc",   "receipt":"urn:scitt:receipt:01HZR1B8"},
        {"event":"recording_completed","at": iso(voice_start + timedelta(seconds=voice_dur)),
         "actor":"helix-recorder-edge1","receipt":"urn:scitt:receipt:01HZR1C9"},
        {"event":"transcribed",        "at": iso(voice_start + timedelta(seconds=voice_dur+220)),
         "actor":"deepgram-nova3",      "receipt":"urn:scitt:receipt:01HZR1F2"},
        {"event":"redacted_pci",       "at": iso(voice_start + timedelta(seconds=voice_dur+340)),
         "actor":"helix-redactor-v2",   "receipt":"urn:scitt:receipt:01HZR1G8",
         "details":{"category":"PCI","ranges":[[47.7, 78.6]]}},
        {"event":"redacted_pii",       "at": iso(voice_start + timedelta(seconds=voice_dur+345)),
         "actor":"helix-redactor-v2",   "receipt":"urn:scitt:receipt:01HZR1H4",
         "details":{"category":"PII","ranges":[[85.1, 89.4]]}},
        {"event":"summarised",         "at": iso(voice_start + timedelta(seconds=voice_dur+560)),
         "actor":"anthropic-claude-sonnet-4.6","receipt":"urn:scitt:receipt:01HZR1J1"},
    ],
}

attachments = [
    {
        "type":      "consent",
        "party":     1,
        "dialog":    [7],
        "mediatype": "application/vcon-consent+json",
        "filename":  f"{slug}-consent.json",
        "start":     iso(voice_start + timedelta(seconds=24)),
        "body":      json.dumps(consent_payload, indent=2),
        "encoding":  "json",
    },
    {
        "type":      "lifecycle",
        "dialog":    [7],
        "mediatype": "application/vcon-lifecycle+json",
        "filename":  f"{slug}-lifecycle.json",
        "body":      json.dumps(lifecycle, indent=2),
        "encoding":  "json",
    },
]

vcon = {
    "vcon":        "0.0.2",
    "uuid":        str(uuid.uuid5(NS, slug)),
    "created_at":  iso(chat_start),
    "updated_at":  iso(voice_start + timedelta(seconds=voice_dur+600)),
    "subject":     "Web chat → voice escalation: duplicate billing prorate (BL-44219)",
    "parties":     [agent, customer],
    "dialog":      dialog,
    "analysis":    analysis,
    "attachments": attachments,
    "extensions":  ["CC", "WTF", "Consent", "Lifecycle"],
    "must_support":["WTF"],
}

out = os.path.join(HERE, f"vcon-{slug}.json")
with open(out, "w") as f:
    json.dump(vcon, f, indent=2)

print(f"Wrote {out}")
print(f"  parties:    {[p['name'] for p in vcon['parties']]}")
print(f"  dialogs:    {len(dialog)}  ({sum(1 for d in dialog if d['type']=='text')} chat + 1 voice)")
print(f"  analysis:   {[a['type'] for a in analysis]}")
print(f"  attach:     {[a['type'] for a in attachments]}")
print(f"  extensions: {vcon['extensions']}")
print()
print("Next: python3 _index.py")
