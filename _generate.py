#!/usr/bin/env python3
"""
Generate 20 vCon JSON files conforming to draft-ietf-vcon-vcon-core-02
plus selected extension drafts:

  - draft-ietf-vcon-cc-extension-01    (Contact Center)
  - draft-howe-vcon-wtf-extension-02   (World Transcription Format)
  - draft-howe-vcon-consent-00         (Consent Attachment)
  - draft-howe-vcon-sip-signaling-00   (SIP signaling)
  - draft-howe-vcon-lifecycle-01       (SCITT lifecycle)

10 vCons are "standard" (no extensions array).
10 vCons exercise one or more extensions.

Each vCon includes:
  * parties with realistic identifiers (tel/mailto/name/uuid)
  * dialog objects referencing external media (wav / mp4 / txt) by URL + sha-512
  * analysis objects (transcripts, summaries, sentiment, tone, translation)
  * attachments where appropriate (slides, screen recordings, documents)
  * full ISO-8601 timestamps and durations

Outputs to ./ (the same directory this script lives in) and writes an
`index.json` summarising all 20 vCons for dashboard ingestion.
"""

import json
import hashlib
import uuid
import os
from datetime import datetime, timedelta, timezone

OUT_DIR = os.path.dirname(os.path.abspath(__file__))
NS = uuid.UUID("11111111-2222-3333-4444-555555555555")  # deterministic namespace

# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------

def did(slug: str) -> str:
    return str(uuid.uuid5(NS, slug))

def iso(dt: datetime) -> str:
    return dt.replace(microsecond=0).isoformat()

def fake_hash(seed: str) -> str:
    # spec uses lowercase hex sha-512 string
    return "sha512-" + hashlib.sha512(seed.encode()).hexdigest()

def media_url(slug: str, ext: str) -> str:
    # synthetic external media host (purely illustrative — not a real bucket)
    return f"https://media.vcon.example.net/{slug}.{ext}"

def party(name, *, tel=None, mailto=None, role=None, contact_list=None,
          tz="America/New_York", validation=None, civic=None, uid=None):
    p = {"name": name}
    if tel:        p["tel"] = tel
    if mailto:     p["mailto"] = mailto
    if validation: p["validation"] = validation
    if tz:         p["timezone"] = tz
    if civic:      p["civicaddress"] = civic
    if uid:        p["uuid"] = uid
    if role:       p["role"] = role             # CC extension
    if contact_list: p["contact_list"] = contact_list  # CC extension
    return p

def dialog_recording(slug, *, start, duration, parties, originator,
                     mediatype="audio/x-wav", ext="wav",
                     disposition="answered", **extras):
    d = {
        "type":         "recording",
        "start":        iso(start),
        "duration":     duration,
        "parties":      parties,
        "originator":   originator,
        "mediatype":    mediatype,
        "filename":     f"{slug}.{ext}",
        "url":          media_url(slug, ext),
        "content_hash": fake_hash(slug),
        "alg":          "SHA-512",
        "disposition":  disposition,
    }
    d.update(extras)
    return d

def dialog_text(slug, *, start, parties, originator, body=None, mediatype="text/plain"):
    d = {
        "type":      "text",
        "start":     iso(start),
        "parties":   parties,
        "originator": originator,
        "mediatype": mediatype,
    }
    if body is not None:
        d["body"]     = body
        d["encoding"] = "none"
    else:
        d["url"]          = media_url(slug, "txt")
        d["content_hash"] = fake_hash(slug)
        d["alg"]          = "SHA-512"
    return d

def analysis(*, atype, dialog_refs, vendor, product, body=None, schema=None,
             mediatype="text/plain", filename=None, encoding="none"):
    a = {
        "type":      atype,
        "dialog":    dialog_refs,
        "mediatype": mediatype,
        "vendor":    vendor,
        "product":   product,
    }
    if schema:   a["schema"]   = schema
    if filename: a["filename"] = filename
    if body is not None:
        a["body"]     = body
        a["encoding"] = encoding
    return a

def attachment(*, atype, party_idx=None, dialog_refs=None, mediatype, slug, ext,
               start=None, body=None, encoding=None):
    a = {
        "type":       atype,
        "mediatype":  mediatype,
        "filename":   f"{slug}.{ext}",
    }
    if party_idx is not None: a["party"]  = party_idx
    if dialog_refs:           a["dialog"] = dialog_refs
    if start:                 a["start"]  = iso(start)
    if body is not None:
        a["body"]     = body
        a["encoding"] = encoding or "none"
    else:
        a["url"]          = media_url(slug, ext)
        a["content_hash"] = fake_hash(slug)
        a["alg"]          = "SHA-512"
    return a

def base_vcon(slug, *, subject, parties, dialog, analysis_=None,
              attachments=None, extensions=None, must_support=None,
              created=None):
    v = {
        "vcon":       "0.0.2",
        "uuid":       did(slug),
        "created_at": iso(created or datetime.now(timezone.utc)),
        "subject":    subject,
        "parties":    parties,
        "dialog":     dialog,
    }
    if analysis_:    v["analysis"]     = analysis_
    if attachments:  v["attachments"]  = attachments
    if extensions:   v["extensions"]   = extensions
    if must_support: v["must_support"] = must_support
    return v

def write_vcon(name, vcon):
    path = os.path.join(OUT_DIR, name)
    with open(path, "w") as f:
        json.dump(vcon, f, indent=2)
    return path

# -----------------------------------------------------------------------------
# Sample transcripts (kept short for readability; each is one paragraph)
# -----------------------------------------------------------------------------

T_SALES = """[00:00:02] Agent: Good morning, this is Marcus from Northwind Software, am I speaking with Priya?
[00:00:06] Customer: Yes, this is Priya. You sent over the proposal yesterday.
[00:00:10] Agent: Perfect. I wanted to walk through the licensing tiers and answer any questions on the migration plan.
[00:00:18] Customer: Pricing looked reasonable but I want to understand the SSO add-on.
[00:00:24] Agent: SSO is included in the Enterprise tier — SAML and OIDC, with SCIM provisioning.
[00:01:02] Customer: Send the redlined MSA by Friday and we have a deal.
[00:01:08] Agent: Will do, thanks Priya."""

T_SUPPORT = """[00:00:01] Agent: Thanks for calling Helix Support, my name is Jordan.
[00:00:05] Customer: Hi Jordan — my account is locked after the password reset and I have an investor demo in two hours.
[00:00:12] Agent: Understood. Can I confirm your registered email and the last four of your phone?
[00:00:22] Customer: blanca.ortega@example.com, last four is 4417.
[00:00:30] Agent: Verified. I'm clearing the lockout and forcing a one-time reset link to that email.
[00:01:05] Customer: Got it, logged in. Thank you.
[00:01:09] Agent: Anything else I can help with today?"""

T_STANDUP = """Standup notes — Platform team — vCon dashboard initiative.
Yesterday: Maya finished the parties parser; Eli wired up the search index.
Today: Maya integrates analysis filtering; Eli adds attachment previews; Devi
investigates SCITT receipt verification. Blockers: waiting on the design system
update from Brand for the dialog timeline component."""

T_INTERVIEW = """[00:00:00] Interviewer: Welcome, thanks for making the time. Tell me a bit about your last project.
[00:00:08] Candidate: Sure — I led the rebuild of the realtime media stack at my previous company...
[00:14:22] Interviewer: How did you handle the SIP/WebRTC interop edge cases?
[00:14:30] Candidate: We sat between a Kamailio edge proxy and an Asterisk B2BUA..."""

T_TELEHEALTH = """[00:00:04] Doctor: Hi Mr. Chen, I have your labs in front of me. How are you feeling since we last spoke?
[00:00:11] Patient: A bit better. The new dosage didn't make me dizzy this week.
[00:00:18] Doctor: Good. Your A1C is down half a point. Let's keep the dose and revisit in 90 days."""

T_VOICEMAIL = """Hi, this is Carla from Lakeshore Title — calling about the closing
package on 412 Maple Avenue. We need a wet signature on page seven by Wednesday.
Please call me back at extension 2210."""

T_WEBCHAT = [
    ("customer", "Hey, my dashboard is showing 500 errors on the metrics page."),
    ("agent",    "Sorry about that — can you share your workspace ID?"),
    ("customer", "ws_8e2c4f"),
    ("agent",    "Thanks. I see a stuck job on the rollup worker. Restarting it now."),
    ("agent",    "Should clear in about a minute. Let me know if it persists."),
    ("customer", "Confirmed, working again. Thanks!"),
]

T_SMS = [
    ("a", "Hey, are we still on for the 3pm walkthrough?"),
    ("b", "Yes — sending the Zoom link in a sec."),
    ("a", "Thanks. Should I bring the redlined SOW?"),
    ("b", "Please. Lisa wants to see the changes before we sign."),
]

T_EMAIL = [
    ("from", "Re: Q3 partner integration roadmap"),
    ("body", "Team — attaching the updated roadmap. Key changes: pulled the Salesforce connector forward to August, pushed the Hubspot one to October to align with their API v4 GA. Let me know by EOW if anything looks off. — Theo"),
    ("body", "Reply: Looks good. The August date is tight but doable if we get the sandbox creds by next Friday. — Aiyana"),
]

T_CONFCALL = """[00:00:00] Host: Welcome everyone — this is the architecture review for the
billing platform migration. We've got engineering, finance ops, and security on the line.
[00:00:18] Engineering: We're proposing a strangler-fig approach over six months...
[00:08:42] Security: I want to flag the PCI scope expansion that comes with the new tokenizer."""

# -----------------------------------------------------------------------------
# Generators
# -----------------------------------------------------------------------------

vcons = []

# ============================================================
# STANDARD vCons (no extensions) -- 1 through 10
# ============================================================

# 01 — outbound sales call (audio)
def v01():
    slug = "01-sales-call-priya-northwind"
    start = datetime(2026, 4, 12, 14, 5, 22, tzinfo=timezone.utc)
    parties = [
        party("Marcus Bell",   tel="+1-617-555-0142", mailto="marcus.bell@northwind.example",
              validation="STIR-A", civic={"country":"US","region":"MA","locality":"Boston"}),
        party("Priya Shah",    tel="+1-415-555-0177", mailto="priya@kestrelpay.example",
              tz="America/Los_Angeles"),
    ]
    dialogs = [dialog_recording(slug, start=start, duration=78.4,
                                parties=[0,1], originator=0)]
    an = [
        analysis(atype="transcript", dialog_refs=[0], vendor="Deepgram",
                 product="Nova-3", body=T_SALES, mediatype="text/plain"),
        analysis(atype="summary", dialog_refs=[0], vendor="Anthropic", product="Claude Sonnet 4.6",
                 body="Northwind sales rep walked Priya through Enterprise-tier SSO and pricing; Priya committed to redlined MSA by Friday.",
                 mediatype="text/plain"),
        analysis(atype="sentiment", dialog_refs=[0], vendor="Recall.ai", product="Sentiment v2",
                 body=json.dumps({"agent_sentiment":"positive","customer_sentiment":"positive","overall":0.74}),
                 mediatype="application/json", encoding="json"),
    ]
    return base_vcon(slug, subject="Northwind Enterprise license — pricing walkthrough",
                     parties=parties, dialog=dialogs, analysis_=an,
                     created=start + timedelta(minutes=4))

# 02 — inbound support call (audio)
def v02():
    slug = "02-support-account-lockout"
    start = datetime(2026, 5, 1, 13, 28, 4, tzinfo=timezone.utc)
    parties = [
        party("Jordan Reyes", tel="+1-512-555-0186", mailto="jordan.reyes@helix.example",
              validation="STIR-A"),
        party("Blanca Ortega", tel="+1-415-555-0144", mailto="blanca.ortega@example.com",
              tz="America/Los_Angeles"),
    ]
    dialogs = [dialog_recording(slug, start=start, duration=82.1,
                                parties=[0,1], originator=1)]
    an = [
        analysis(atype="transcript", dialog_refs=[0], vendor="OpenAI", product="Whisper Large v3",
                 body=T_SUPPORT, mediatype="text/plain"),
        analysis(atype="summary", dialog_refs=[0], vendor="Helix", product="Internal Summarizer",
                 body="Customer locked out post-password-reset before investor demo; identity verified, lockout cleared, OTP reset link sent.",
                 mediatype="text/plain"),
        analysis(atype="tone", dialog_refs=[0], vendor="Cogito", product="Tone Analyzer",
                 body=json.dumps({"customer_stress":"high_to_low","agent_empathy":0.88}),
                 mediatype="application/json", encoding="json"),
    ]
    return base_vcon(slug, subject="Account lockout — Blanca Ortega",
                     parties=parties, dialog=dialogs, analysis_=an,
                     created=start + timedelta(minutes=2))

# 03 — internal video standup (mp4)
def v03():
    slug = "03-team-standup-vcon-dashboard"
    start = datetime(2026, 5, 4, 13, 0, 0, tzinfo=timezone.utc)
    parties = [
        party("Maya Lindholm", mailto="maya@alianza.example"),
        party("Eli Chen",      mailto="eli@alianza.example"),
        party("Devi Rao",      mailto="devi@alianza.example"),
        party("Tomás Fuentes", mailto="tomas@alianza.example"),
    ]
    dialogs = [dialog_recording(slug, start=start, duration=912.0,
                                parties=[0,1,2,3], originator=0,
                                mediatype="video/mp4", ext="mp4")]
    atts = [
        attachment(atype="slides", dialog_refs=[0],
                   mediatype="application/pdf", slug=slug+"-slides", ext="pdf"),
    ]
    an = [
        analysis(atype="transcript", dialog_refs=[0], vendor="Otter.ai", product="Otter v3",
                 body=T_STANDUP, mediatype="text/plain"),
        analysis(atype="summary", dialog_refs=[0], vendor="Otter.ai", product="Action Items",
                 body=json.dumps([
                    {"owner":"Maya", "task":"Integrate analysis filtering"},
                    {"owner":"Eli",  "task":"Add attachment previews"},
                    {"owner":"Devi", "task":"Investigate SCITT receipt verification"},
                 ]),
                 mediatype="application/json", encoding="json"),
    ]
    return base_vcon(slug, subject="Platform standup — vCon dashboard initiative",
                     parties=parties, dialog=dialogs, analysis_=an, attachments=atts,
                     created=start + timedelta(minutes=20))

# 04 — SMS thread (no recording)
def v04():
    slug = "04-sms-walkthrough-3pm"
    start = datetime(2026, 4, 22, 18, 12, 0, tzinfo=timezone.utc)
    parties = [
        party("Aisha Holloway", tel="+1-646-555-0190"),
        party("Lisa Bertrand",  tel="+1-646-555-0123"),
    ]
    dialogs = []
    for i, (who, msg) in enumerate(T_SMS):
        dialogs.append(dialog_text(f"{slug}-{i}",
                                   start=start + timedelta(minutes=3*i),
                                   parties=[0,1],
                                   originator=0 if who == "a" else 1,
                                   body=msg, mediatype="text/plain"))
    return base_vcon(slug, subject="SMS — 3pm walkthrough confirmation",
                     parties=parties, dialog=dialogs,
                     created=start + timedelta(hours=1))

# 05 — email thread
def v05():
    slug = "05-email-q3-roadmap"
    start = datetime(2026, 4, 28, 16, 4, 0, tzinfo=timezone.utc)
    parties = [
        party("Theo Vance",    mailto="theo.vance@northwind.example"),
        party("Aiyana Whitehorse", mailto="aiyana@northwind.example"),
        party("Diego Halpert", mailto="diego@northwind.example"),
    ]
    dialogs = [
        dialog_text(slug+"-1", start=start, parties=[0,1,2], originator=0,
                    body="Subject: Re: Q3 partner integration roadmap\n\n" + T_EMAIL[1][1],
                    mediatype="message/rfc822"),
        dialog_text(slug+"-2", start=start + timedelta(hours=4), parties=[0,1,2], originator=1,
                    body="Subject: Re: Q3 partner integration roadmap\n\n" + T_EMAIL[2][1],
                    mediatype="message/rfc822"),
    ]
    atts = [
        attachment(atype="document", dialog_refs=[0],
                   mediatype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                   slug=slug+"-roadmap", ext="xlsx"),
    ]
    return base_vcon(slug, subject="Q3 partner integration roadmap",
                     parties=parties, dialog=dialogs, attachments=atts,
                     created=start + timedelta(hours=5))

# 06 — webchat
def v06():
    slug = "06-webchat-metrics-500"
    start = datetime(2026, 5, 5, 17, 41, 12, tzinfo=timezone.utc)
    parties = [
        party("Customer (workspace ws_8e2c4f)", uid=did("ws_8e2c4f")),
        party("Helix Agent — Lior Avraham", mailto="lior@helix.example"),
    ]
    dialogs = []
    for i, (who, msg) in enumerate(T_WEBCHAT):
        dialogs.append(dialog_text(f"{slug}-{i}",
                                   start=start + timedelta(seconds=20*i),
                                   parties=[0,1],
                                   originator=0 if who == "customer" else 1,
                                   body=msg))
    an = [
        analysis(atype="summary", dialog_refs=list(range(len(dialogs))),
                 vendor="Helix", product="ChatSummarizer",
                 body="Customer reported 500 on metrics page; agent identified stuck rollup worker, restarted it, customer confirmed resolution.",
                 mediatype="text/plain"),
    ]
    return base_vcon(slug, subject="Web chat — metrics page 500 errors",
                     parties=parties, dialog=dialogs, analysis_=an,
                     created=start + timedelta(minutes=5))

# 07 — voicemail (audio, one-way)
def v07():
    slug = "07-voicemail-lakeshore-title"
    start = datetime(2026, 5, 6, 22, 14, 30, tzinfo=timezone.utc)
    parties = [
        party("Carla Mendez (Lakeshore Title)", tel="+1-312-555-0119",
              mailto="carla@lakeshore-title.example", validation="STIR-A"),
        party("Recipient — Sam Greaves", tel="+1-312-555-0188"),
    ]
    dialogs = [
        dialog_recording(slug, start=start, duration=42.7,
                         parties=[0,1], originator=0,
                         disposition="voicemail")
    ]
    an = [
        analysis(atype="transcript", dialog_refs=[0], vendor="Google", product="Speech-to-Text v2",
                 body=T_VOICEMAIL, mediatype="text/plain"),
        analysis(atype="summary", dialog_refs=[0], vendor="OpenAI", product="GPT-4o-mini",
                 body="Title agent left a voicemail requesting a wet signature on page 7 of the closing package by Wednesday.",
                 mediatype="text/plain"),
    ]
    return base_vcon(slug, subject="Voicemail — closing package signature",
                     parties=parties, dialog=dialogs, analysis_=an,
                     created=start + timedelta(minutes=1))

# 08 — multi-party conference call
def v08():
    slug = "08-conference-billing-arch-review"
    start = datetime(2026, 4, 30, 15, 0, 0, tzinfo=timezone.utc)
    parties = [
        party("Renata Oduya (Host, Architecture)",   mailto="renata@northwind.example"),
        party("Engineering — Hiro Tanaka",            mailto="hiro@northwind.example"),
        party("Finance Ops — Marlene Sokol",          mailto="marlene@northwind.example"),
        party("Security — Quentin Yarrow",            mailto="quentin@northwind.example"),
        party("Legal — Anya Petrović",                mailto="anya@northwind.example"),
    ]
    dialogs = [dialog_recording(slug, start=start, duration=3540.0,
                                parties=list(range(5)), originator=0)]
    an = [
        analysis(atype="transcript", dialog_refs=[0], vendor="Otter.ai", product="Otter v3",
                 body=T_CONFCALL, mediatype="text/plain"),
        analysis(atype="summary", dialog_refs=[0], vendor="Anthropic", product="Claude Sonnet 4.6",
                 body="Architecture review for billing platform migration. Engineering proposed strangler-fig over six months; Security flagged PCI scope expansion from new tokenizer; Legal noted contractual carve-outs in two key processor agreements.",
                 mediatype="text/plain"),
    ]
    return base_vcon(slug, subject="Billing platform migration — architecture review",
                     parties=parties, dialog=dialogs, analysis_=an,
                     created=start + timedelta(hours=1, minutes=10))

# 09 — telehealth video call
def v09():
    slug = "09-telehealth-chen-followup"
    start = datetime(2026, 5, 2, 19, 30, 0, tzinfo=timezone.utc)
    parties = [
        party("Dr. Helena Park", mailto="hpark@summitclinic.example",
              validation="HPID-verified"),
        party("Liam Chen — Patient", mailto="liam.chen@example.com",
              validation="MyChart-verified", tz="America/Chicago"),
    ]
    dialogs = [dialog_recording(slug, start=start, duration=624.0,
                                parties=[0,1], originator=0,
                                mediatype="video/mp4", ext="mp4")]
    an = [
        analysis(atype="transcript", dialog_refs=[0], vendor="Augmedix", product="MedTranscribe v4",
                 body=T_TELEHEALTH, mediatype="text/plain"),
        analysis(atype="summary", dialog_refs=[0], vendor="Augmedix", product="ClinicalNotes",
                 body="Follow-up on T2D management. A1C improved 0.5 points on revised metformin dose; no dizziness reported. Plan: continue current dose; reassess in 90 days.",
                 mediatype="text/plain"),
    ]
    atts = [
        attachment(atype="lab_report", party_idx=1, dialog_refs=[0],
                   mediatype="application/pdf",
                   slug=slug+"-labs-2026-04", ext="pdf"),
    ]
    return base_vcon(slug, subject="Telehealth follow-up — Liam Chen",
                     parties=parties, dialog=dialogs, analysis_=an, attachments=atts,
                     created=start + timedelta(minutes=15))

# 10 — job interview video
def v10():
    slug = "10-interview-staff-platform-eng"
    start = datetime(2026, 4, 26, 16, 0, 0, tzinfo=timezone.utc)
    parties = [
        party("Yusuf Ademola (Interviewer, Eng Manager)", mailto="yusuf@northwind.example"),
        party("Candidate — River Kobayashi", mailto="river.kobayashi@example.com"),
    ]
    dialogs = [dialog_recording(slug, start=start, duration=2700.0,
                                parties=[0,1], originator=0,
                                mediatype="video/mp4", ext="mp4")]
    an = [
        analysis(atype="transcript", dialog_refs=[0], vendor="OpenAI", product="Whisper Large v3",
                 body=T_INTERVIEW, mediatype="text/plain"),
        analysis(atype="scorecard", dialog_refs=[0], vendor="Greenhouse", product="Structured Interview",
                 body=json.dumps({
                    "rubric":"staff_platform_engineer_v3",
                    "scores":{"systems_design":4, "rt_media":5, "leadership":4, "communication":4},
                    "recommendation":"hire"
                 }),
                 mediatype="application/json", encoding="json"),
    ]
    return base_vcon(slug, subject="Interview — Staff Platform Engineer (River Kobayashi)",
                     parties=parties, dialog=dialogs, analysis_=an,
                     created=start + timedelta(hours=1))

# ============================================================
# EXTENDED vCons -- 11 through 20
# ============================================================

# 11 — Contact center inbound (CC extension)
def v11():
    slug = "11-cc-inbound-support-billing"
    start = datetime(2026, 5, 7, 14, 22, 18, tzinfo=timezone.utc)
    parties = [
        party("Agent — Naomi Sayid",  tel="+1-737-555-0101", mailto="naomi.sayid@helix.example",
              role="agent"),
        party("Customer — Petros Andriotis", tel="+1-617-555-0173",
              mailto="petros@example.com", role="customer"),
    ]
    dialogs = [dialog_recording(slug, start=start, duration=298.6,
                                parties=[0,1], originator=1,
                                campaign="2026-Q2-billing-inbound",
                                interaction_type="voice",
                                interaction_id="INT-8814226",
                                skill="billing-tier2")]
    an = [
        analysis(atype="transcript", dialog_refs=[0], vendor="Deepgram", product="Nova-3",
                 body="[00:00:02] Naomi: Helix billing, this is Naomi. [00:00:05] Petros: Hi, my invoice double-charged me for seats this month...",
                 mediatype="text/plain"),
        analysis(atype="summary", dialog_refs=[0], vendor="Anthropic", product="Claude Sonnet 4.6",
                 body="Customer reported duplicate seat charge on April invoice. Agent verified prorate bug from mid-cycle plan change, issued credit memo CM-44219 ($284.00), confirmed customer would see credit on next invoice.",
                 mediatype="text/plain"),
    ]
    return base_vcon(slug, subject="Inbound — duplicate seat charge",
                     parties=parties, dialog=dialogs, analysis_=an,
                     extensions=["CC"],
                     created=start + timedelta(minutes=6))

# 12 — Contact center outbound campaign (CC extension + WTF transcript)
def v12():
    slug = "12-cc-outbound-renewal-campaign"
    start = datetime(2026, 5, 6, 19, 15, 0, tzinfo=timezone.utc)
    parties = [
        party("Agent — Tomás Caballero", tel="+1-303-555-0144",
              mailto="tomas.c@kestrelpay.example", role="agent"),
        party("Customer — Yuki Watanabe", tel="+1-415-555-0167",
              mailto="yuki.w@example.com", role="customer",
              contact_list="renewals-q2-2026"),
    ]
    dialogs = [dialog_recording(slug, start=start, duration=412.3,
                                parties=[0,1], originator=0,
                                campaign="renewals-q2-2026",
                                interaction_type="outbound_voice",
                                interaction_id="INT-9001782",
                                skill="renewals-enterprise")]
    wtf_payload = {
        "wtf_version": "1.0",
        "provider":    {"name":"Deepgram", "model":"nova-3", "language":"en-US"},
        "channels":    2,
        "speakers": [
            {"speaker":"S0", "party":0, "role":"agent",    "talk_time_s":201.4},
            {"speaker":"S1", "party":1, "role":"customer", "talk_time_s":174.1},
        ],
        "segments": [
            {"start":2.10,  "end":7.40,  "speaker":"S0",
             "text":"Hi Yuki, this is Tomás from Kestrel Pay calling about your annual renewal."},
            {"start":7.50,  "end":11.20, "speaker":"S1",
             "text":"Hey Tomás — yeah, I saw the email."},
            {"start":11.30, "end":18.85, "speaker":"S0",
             "text":"We have a multi-year option this year that would lock pricing for 24 months."},
        ],
        "quality": {"overall_confidence":0.91, "redaction_applied":True},
    }
    an = [
        analysis(atype="transcript", dialog_refs=[0], vendor="Deepgram", product="Nova-3",
                 schema="WTF/1.0",
                 body=json.dumps(wtf_payload),
                 mediatype="application/json", encoding="json",
                 filename=f"{slug}-wtf.json"),
        analysis(atype="sentiment", dialog_refs=[0], vendor="Recall.ai", product="Sentiment v2",
                 body=json.dumps({"agent":0.62, "customer":0.41, "trend":"warming"}),
                 mediatype="application/json", encoding="json"),
        analysis(atype="disposition", dialog_refs=[0], vendor="Helix", product="DispoClassifier",
                 body=json.dumps({"outcome":"renewed_24mo","commit_value_usd":54000}),
                 mediatype="application/json", encoding="json"),
    ]
    return base_vcon(slug, subject="Outbound renewal — Yuki Watanabe (Q2 2026)",
                     parties=parties, dialog=dialogs, analysis_=an,
                     extensions=["CC","WTF"], must_support=["WTF"],
                     created=start + timedelta(minutes=10))

# 13 — Contact center: omni-channel (voice + SMS) with CC extension
def v13():
    slug = "13-cc-omnichannel-voice-sms"
    start = datetime(2026, 5, 3, 14, 0, 0, tzinfo=timezone.utc)
    parties = [
        party("Agent — Ines Macharia", tel="+1-737-555-0211",
              mailto="ines@helix.example", role="agent"),
        party("Customer — Roland Kühn", tel="+49-30-555-0044",
              mailto="roland.kuehn@example.de", role="customer",
              tz="Europe/Berlin"),
    ]
    dialogs = [
        dialog_recording(slug+"-voice", start=start, duration=540.0,
                         parties=[0,1], originator=1,
                         campaign="omnichannel-eu-support",
                         interaction_type="voice",
                         interaction_id="INT-OMNI-32118",
                         skill="tier2-eu"),
        dialog_text(slug+"-sms-1", start=start + timedelta(minutes=12),
                    parties=[0,1], originator=0,
                    body="Hi Roland — here's the link to verify the new IBAN: https://helix.example/verify/zg83",
                    mediatype="text/plain"),
        dialog_text(slug+"-sms-2", start=start + timedelta(minutes=14),
                    parties=[0,1], originator=1,
                    body="Verified. Danke.",
                    mediatype="text/plain"),
    ]
    # Add CC ext fields to the SMS dialogs as well
    for d in dialogs[1:]:
        d["interaction_id"]   = "INT-OMNI-32118"
        d["interaction_type"] = "sms"
        d["campaign"]         = "omnichannel-eu-support"
        d["skill"]            = "tier2-eu"

    an = [
        analysis(atype="transcript", dialog_refs=[0], vendor="OpenAI", product="Whisper Large v3",
                 body="[00:00:02] Roland: I need to update the IBAN on my account. [00:00:08] Ines: I can help — verifying your identity first...",
                 mediatype="text/plain"),
        analysis(atype="translation", dialog_refs=[0,2], vendor="DeepL", product="DeepL Pro",
                 body="(2) 'Verified. Thanks.'",
                 mediatype="text/plain"),
    ]
    return base_vcon(slug, subject="Omni-channel — IBAN update (Roland Kühn)",
                     parties=parties, dialog=dialogs, analysis_=an,
                     extensions=["CC"],
                     created=start + timedelta(minutes=20))

# 14 — Contact center call with WTF transcript only (no other CC ext fields stretched)
def v14():
    slug = "14-cc-wtf-multispeaker-conference"
    start = datetime(2026, 5, 8, 17, 0, 0, tzinfo=timezone.utc)
    parties = [
        party("Agent — Khalid Mansoor",  tel="+1-303-555-0301", role="agent"),
        party("Supervisor — Reina Esposito", tel="+1-303-555-0302", role="supervisor"),
        party("Customer — Hilde Bjornson", tel="+1-415-555-0421", role="customer"),
        party("SME — Olamide Ajayi", tel="+1-303-555-0388", role="sme"),
    ]
    dialogs = [dialog_recording(slug, start=start, duration=1280.0,
                                parties=[0,1,2,3], originator=2,
                                campaign="esc-tier3",
                                interaction_type="voice",
                                interaction_id="INT-ESC-77251",
                                skill="escalation-billing")]
    wtf_payload = {
        "wtf_version":"1.0",
        "provider":{"name":"AssemblyAI","model":"universal-2","language":"en-US"},
        "channels":4,
        "speakers":[
            {"speaker":"S0","party":0,"role":"agent","talk_time_s":410.0},
            {"speaker":"S1","party":1,"role":"supervisor","talk_time_s":120.0},
            {"speaker":"S2","party":2,"role":"customer","talk_time_s":540.0},
            {"speaker":"S3","party":3,"role":"sme","talk_time_s":210.0},
        ],
        "segments":[
            {"start":3.2,"end":11.7,"speaker":"S2","text":"This is the third time I've been transferred and I just want a refund."},
            {"start":12.0,"end":17.4,"speaker":"S0","text":"I'm sorry — I'm bringing my supervisor onto the line right now."},
            {"start":17.6,"end":24.1,"speaker":"S1","text":"Hi Hilde, this is Reina, the supervisor. I'm reviewing the case now."},
        ],
        "quality":{"overall_confidence":0.88,"redaction_applied":True},
    }
    an = [
        analysis(atype="transcript", dialog_refs=[0], vendor="AssemblyAI", product="Universal-2",
                 schema="WTF/1.0",
                 body=json.dumps(wtf_payload),
                 mediatype="application/json", encoding="json",
                 filename=f"{slug}-wtf.json"),
        analysis(atype="summary", dialog_refs=[0], vendor="Anthropic", product="Claude Sonnet 4.6",
                 body="Escalation: customer frustrated by repeated transfers; supervisor took over and authorized full refund of $1,184.00; SME confirmed the underlying duplicate-charge bug.",
                 mediatype="text/plain"),
    ]
    return base_vcon(slug, subject="Tier-3 escalation — duplicate charge refund",
                     parties=parties, dialog=dialogs, analysis_=an,
                     extensions=["CC","WTF"], must_support=["WTF"],
                     created=start + timedelta(minutes=25))

# 15 — Contact center call with consent attachment (CC + Consent ext)
def v15():
    slug = "15-cc-consent-recording-attached"
    start = datetime(2026, 5, 5, 15, 30, 0, tzinfo=timezone.utc)
    parties = [
        party("Agent — Esther Lindqvist", tel="+1-617-555-0501",
              mailto="esther@kestrelpay.example", role="agent"),
        party("Customer — Adaeze Nnamani", tel="+1-202-555-0411",
              mailto="adaeze.n@example.com", role="customer"),
    ]
    dialogs = [dialog_recording(slug, start=start, duration=486.2,
                                parties=[0,1], originator=1,
                                campaign="kyc-refresh",
                                interaction_type="voice",
                                interaction_id="INT-KYC-55421",
                                skill="kyc-verification")]
    consent_payload = {
        "consent_version":"vCon-Consent/0.1",
        "expires_at": iso(start + timedelta(days=365)),
        "parties":[1],
        "dialog":[0],
        "consents":[
            {"purpose":"recording",          "granted":True, "granted_at":iso(start + timedelta(seconds=10))},
            {"purpose":"transcription",      "granted":True, "granted_at":iso(start + timedelta(seconds=10))},
            {"purpose":"qa_review",          "granted":True, "granted_at":iso(start + timedelta(seconds=10))},
            {"purpose":"ai_training",        "granted":False},
            {"purpose":"third_party_share",  "granted":False},
        ],
        "ai_preferences": {"allow_inference":True, "allow_training":False},
        "scitt_receipt": {
            "transparency_service":"https://scitt.example.org/v1",
            "receipt_id":"urn:scitt:receipt:01HZX9KQ4D",
        },
    }
    atts = [
        attachment(atype="consent", party_idx=1, dialog_refs=[0],
                   mediatype="application/vcon-consent+json",
                   slug=slug+"-consent", ext="json",
                   start=start + timedelta(seconds=10),
                   body=json.dumps(consent_payload, indent=2),
                   encoding="json"),
    ]
    an = [
        analysis(atype="transcript", dialog_refs=[0], vendor="Deepgram", product="Nova-3",
                 body="[00:00:00] Esther: ...this call is being recorded for verification purposes; do I have your consent? [00:00:10] Adaeze: Yes, that's fine.",
                 mediatype="text/plain"),
    ]
    return base_vcon(slug, subject="KYC refresh — recorded with explicit consent",
                     parties=parties, dialog=dialogs, analysis_=an, attachments=atts,
                     extensions=["CC","Consent"],
                     created=start + timedelta(minutes=10))

# 16 — Contact center transfer/stitched dialog (CC ext, multi-segment)
def v16():
    slug = "16-cc-multisegment-transfer"
    start = datetime(2026, 4, 29, 18, 5, 0, tzinfo=timezone.utc)
    parties = [
        party("IVR / Bot", uid=did("ivr-bot-1"), role="agent"),
        party("Agent A — Beatriz Romero", tel="+1-737-555-0701", role="agent"),
        party("Agent B — Wendell Okafor", tel="+1-737-555-0702", role="agent"),
        party("Customer — Magnus Eriksen", tel="+1-415-555-0822", role="customer"),
    ]
    seg1_start = start
    seg2_start = start + timedelta(seconds=72)
    seg3_start = start + timedelta(seconds=240)
    dialogs = [
        dialog_recording(slug+"-seg1-ivr",   start=seg1_start, duration=70.0,
                         parties=[0,3], originator=3,
                         campaign="general-inbound",
                         interaction_type="voice",
                         interaction_id="INT-MS-90012",
                         skill="ivr"),
        dialog_recording(slug+"-seg2-agentA", start=seg2_start, duration=165.0,
                         parties=[1,3], originator=3,
                         campaign="general-inbound",
                         interaction_type="voice",
                         interaction_id="INT-MS-90012",
                         skill="general-tier1"),
        dialog_recording(slug+"-seg3-agentB", start=seg3_start, duration=320.0,
                         parties=[2,3], originator=3,
                         campaign="general-inbound",
                         interaction_type="voice",
                         interaction_id="INT-MS-90012",
                         skill="hardware-tier2"),
    ]
    # Simple party_history showing the stitch
    dialogs[1]["party_history"] = [
        {"party":1,"event":"join","time":iso(seg2_start)},
        {"party":3,"event":"transferred","time":iso(seg2_start)},
    ]
    dialogs[2]["party_history"] = [
        {"party":2,"event":"join","time":iso(seg3_start)},
        {"party":1,"event":"drop","time":iso(seg3_start)},
    ]
    an = [
        analysis(atype="summary", dialog_refs=[0,1,2], vendor="Anthropic", product="Claude Sonnet 4.6",
                 body="Customer routed through IVR, briefly held by tier-1 agent, then transferred to hardware tier-2 specialist who replaced the unit under warranty.",
                 mediatype="text/plain"),
    ]
    return base_vcon(slug, subject="Multi-segment hardware support call",
                     parties=parties, dialog=dialogs, analysis_=an,
                     extensions=["CC"],
                     created=start + timedelta(minutes=15))

# 17 — Supervisor monitoring (CC ext, party.role=supervisor, recording is silent join)
def v17():
    slug = "17-cc-supervisor-monitor"
    start = datetime(2026, 5, 4, 16, 45, 0, tzinfo=timezone.utc)
    parties = [
        party("Agent — Paloma Ibarra", tel="+1-737-555-0801", role="agent"),
        party("Customer — Felipe Gallego", tel="+1-415-555-0455", role="customer"),
        party("Supervisor — Naila Khoury", tel="+1-737-555-0888", role="supervisor"),
    ]
    dialogs = [dialog_recording(slug, start=start, duration=720.0,
                                parties=[0,1,2], originator=1,
                                campaign="qm-coaching-may26",
                                interaction_type="voice",
                                interaction_id="INT-QM-44189",
                                skill="general-tier1")]
    dialogs[0]["party_history"] = [
        {"party":2,"event":"silent_join","time":iso(start + timedelta(seconds=30))},
        {"party":2,"event":"drop",       "time":iso(start + timedelta(seconds=720))},
    ]
    an = [
        analysis(atype="qm_score", dialog_refs=[0], vendor="Helix", product="QM v3",
                 body=json.dumps({
                    "rubric":"general-tier1-v4",
                    "scores":{"greeting":5,"empathy":4,"resolution":4,"closing":5},
                    "overall":4.5,
                    "scored_by":"Naila Khoury",
                 }),
                 mediatype="application/json", encoding="json"),
        analysis(atype="transcript", dialog_refs=[0], vendor="OpenAI", product="Whisper Large v3",
                 body="[00:00:01] Paloma: Thanks for calling Helix, this is Paloma. [00:00:04] Felipe: Hi, my router keeps dropping every few hours...",
                 mediatype="text/plain"),
    ]
    return base_vcon(slug, subject="QM-monitored support call (router intermittent)",
                     parties=parties, dialog=dialogs, analysis_=an,
                     extensions=["CC"],
                     created=start + timedelta(minutes=15))

# 18 — Contact center with SIP signaling extension attachment
def v18():
    slug = "18-cc-sip-signaling-attached"
    start = datetime(2026, 5, 7, 20, 11, 0, tzinfo=timezone.utc)
    parties = [
        party("Agent — Imani Robertson", tel="+1-737-555-0911",
              mailto="imani.r@northwind.example", validation="STIR-A", role="agent"),
        party("Customer — Sergei Vasiliev", tel="+1-415-555-0998",
              validation="STIR-B", role="customer"),
    ]
    dialogs = [dialog_recording(slug, start=start, duration=240.5,
                                parties=[0,1], originator=1,
                                campaign="general-inbound",
                                interaction_type="voice",
                                interaction_id="INT-SIP-77019",
                                skill="general-tier1")]
    sip_payload = {
        "sip_signaling_version":"0.1",
        "call_id":"a47f8b2e-9c1d-4a5b-9f3a-1e2f3a4b5c6d@edge1.northwind.example",
        "from":   {"uri":"sip:+14155550998@carrier.example", "tag":"as5d8f9a"},
        "to":     {"uri":"sip:+17375550911@northwind.example", "tag":"r19f8c2b"},
        "passport": {
            "verstat":"TN-Validation-Passed-A",
            "attestation":"A",
            "origid":"01HZX0K9ZP",
            "iat": int(start.timestamp()),
        },
        "media":[{"m":"audio","codec":"opus/48000/2","srtp":"AES_CM_128_HMAC_SHA1_80"}],
    }
    atts = [
        attachment(atype="sip_signaling", dialog_refs=[0],
                   mediatype="application/vcon-sip+json",
                   slug=slug+"-sip", ext="json",
                   body=json.dumps(sip_payload, indent=2), encoding="json"),
    ]
    an = [
        analysis(atype="transcript", dialog_refs=[0], vendor="Deepgram", product="Nova-3",
                 body="[00:00:01] Imani: Northwind support, how can I help? ...",
                 mediatype="text/plain"),
    ]
    return base_vcon(slug, subject="STIR/SHAKEN-attested support call",
                     parties=parties, dialog=dialogs, analysis_=an, attachments=atts,
                     extensions=["CC","SIP"],
                     created=start + timedelta(minutes=5))

# 19 — Contact center + SCITT lifecycle group (lifecycle ext)
def v19():
    slug = "19-cc-lifecycle-scitt-group"
    start = datetime(2026, 4, 24, 18, 0, 0, tzinfo=timezone.utc)
    parties = [
        party("Agent — Bea Halloran", tel="+1-617-555-0188", role="agent"),
        party("Customer — Jiang Wei", tel="+1-415-555-0240", role="customer"),
    ]
    dialogs = [dialog_recording(slug, start=start, duration=362.0,
                                parties=[0,1], originator=1,
                                campaign="rest-of-fund-renewals",
                                interaction_type="voice",
                                interaction_id="INT-LC-33001",
                                skill="renewals")]
    lifecycle_events = {
        "lifecycle_version":"vCon-Lifecycle-SCITT/0.1",
        "transparency_service":"https://scitt.example.org/v1",
        "events":[
            {"event":"vcon_created",       "at":iso(start - timedelta(seconds=2)),
             "actor":"helix-recorder-edge1", "receipt":"urn:scitt:receipt:01HZW1A2"},
            {"event":"consent_captured",   "at":iso(start + timedelta(seconds=15)),
             "actor":"helix-consent-svc",   "receipt":"urn:scitt:receipt:01HZW1B7"},
            {"event":"recording_completed","at":iso(start + timedelta(seconds=362)),
             "actor":"helix-recorder-edge1","receipt":"urn:scitt:receipt:01HZW1C9"},
            {"event":"transcribed",        "at":iso(start + timedelta(minutes=8)),
             "actor":"deepgram-nova3",     "receipt":"urn:scitt:receipt:01HZW1F2"},
            {"event":"redacted_pii",       "at":iso(start + timedelta(minutes=10)),
             "actor":"helix-redactor-v2",  "receipt":"urn:scitt:receipt:01HZW1G8"},
        ],
    }
    atts = [
        attachment(atype="lifecycle", dialog_refs=[0],
                   mediatype="application/vcon-lifecycle+json",
                   slug=slug+"-lifecycle", ext="json",
                   body=json.dumps(lifecycle_events, indent=2), encoding="json"),
    ]
    an = [
        analysis(atype="summary", dialog_refs=[0], vendor="Anthropic", product="Claude Sonnet 4.6",
                 body="Renewal call; customer agreed to 12-month renewal at flat pricing. Lifecycle events recorded to SCITT transparency service.",
                 mediatype="text/plain"),
    ]
    v = base_vcon(slug, subject="Renewal call w/ SCITT lifecycle audit",
                  parties=parties, dialog=dialogs, analysis_=an, attachments=atts,
                  extensions=["CC","Lifecycle"],
                  created=start + timedelta(minutes=12))
    # Add a 'group' linking related vCons (illustrative — references siblings)
    v["group"] = [{"uuid": did("11-cc-inbound-support-billing")}]
    return v

# 20 — Contact center: redacted recording with PII/PCI markers (CC + WTF)
def v20():
    slug = "20-cc-redacted-pci-pii"
    start = datetime(2026, 5, 6, 21, 5, 0, tzinfo=timezone.utc)
    parties = [
        party("Agent — Henrietta Vossberg", tel="+1-737-555-1010", role="agent"),
        party("Customer — Rashid El-Khoury", tel="+1-415-555-1212", role="customer"),
    ]
    dialogs = [dialog_recording(slug, start=start, duration=520.0,
                                parties=[0,1], originator=1,
                                campaign="card-on-file-update",
                                interaction_type="voice",
                                interaction_id="INT-PCI-22087",
                                skill="payments-tier1")]
    wtf_payload = {
        "wtf_version":"1.0",
        "provider":{"name":"Deepgram","model":"nova-3","language":"en-US"},
        "channels":2,
        "speakers":[
            {"speaker":"S0","party":0,"role":"agent","talk_time_s":210.0},
            {"speaker":"S1","party":1,"role":"customer","talk_time_s":280.0},
        ],
        "segments":[
            {"start":1.2,"end":6.4,"speaker":"S0","text":"Thanks for calling — I see you'd like to update the card on file."},
            {"start":7.0,"end":12.1,"speaker":"S1","text":"Yes, my new card is —"},
            {"start":12.1,"end":42.0,"speaker":"S1","text":"[REDACTED:PCI]","redaction":"pci"},
            {"start":42.5,"end":48.7,"speaker":"S0","text":"Got it — and I'll just confirm the billing zip."},
            {"start":48.9,"end":52.4,"speaker":"S1","text":"[REDACTED:PII-zip]","redaction":"pii"},
        ],
        "quality":{"overall_confidence":0.93,"redaction_applied":True},
    }
    an = [
        analysis(atype="transcript", dialog_refs=[0], vendor="Deepgram", product="Nova-3",
                 schema="WTF/1.0",
                 body=json.dumps(wtf_payload),
                 mediatype="application/json", encoding="json",
                 filename=f"{slug}-wtf.json"),
        analysis(atype="redaction_log", dialog_refs=[0], vendor="Helix", product="Redactor v2",
                 body=json.dumps([
                    {"start":12.1,"end":42.0,"category":"PCI","reason":"card-number-spoken"},
                    {"start":48.9,"end":52.4,"category":"PII","reason":"zip-code-spoken"},
                 ]),
                 mediatype="application/json", encoding="json"),
    ]
    return base_vcon(slug, subject="Card-on-file update (PCI/PII redacted)",
                     parties=parties, dialog=dialogs, analysis_=an,
                     extensions=["CC","WTF"], must_support=["WTF"],
                     created=start + timedelta(minutes=8))

# -----------------------------------------------------------------------------
# Build & write
# -----------------------------------------------------------------------------

GENERATORS = [
    ("vcon-01-sales-call.json",                v01,  False),
    ("vcon-02-support-lockout.json",           v02,  False),
    ("vcon-03-team-standup.json",              v03,  False),
    ("vcon-04-sms-thread.json",                v04,  False),
    ("vcon-05-email-thread.json",              v05,  False),
    ("vcon-06-webchat.json",                   v06,  False),
    ("vcon-07-voicemail.json",                 v07,  False),
    ("vcon-08-conference-call.json",           v08,  False),
    ("vcon-09-telehealth.json",                v09,  False),
    ("vcon-10-job-interview.json",             v10,  False),
    ("vcon-11-cc-inbound-billing.json",        v11,  True),
    ("vcon-12-cc-outbound-renewal-wtf.json",   v12,  True),
    ("vcon-13-cc-omnichannel.json",            v13,  True),
    ("vcon-14-cc-escalation-wtf.json",         v14,  True),
    ("vcon-15-cc-with-consent.json",           v15,  True),
    ("vcon-16-cc-multisegment-transfer.json",  v16,  True),
    ("vcon-17-cc-supervisor-monitor.json",     v17,  True),
    ("vcon-18-cc-sip-signaling.json",          v18,  True),
    ("vcon-19-cc-lifecycle-scitt.json",        v19,  True),
    ("vcon-20-cc-redacted-pci-pii.json",       v20,  True),
]

index = []
for fname, fn, is_ext in GENERATORS:
    v = fn()
    write_vcon(fname, v)
    index.append({
        "file":        fname,
        "uuid":        v["uuid"],
        "subject":     v["subject"],
        "created_at":  v["created_at"],
        "extensions":  v.get("extensions", []),
        "must_support":v.get("must_support", []),
        "party_count": len(v.get("parties",[])),
        "dialog_count":len(v.get("dialog",[])),
        "analysis_count":len(v.get("analysis",[])),
        "attachment_count":len(v.get("attachments",[])),
        "category":    "extended" if is_ext else "standard",
    })

with open(os.path.join(OUT_DIR, "index.json"), "w") as f:
    json.dump({
        "schema": "vcon-corpus-index/0.1",
        "generated_at": iso(datetime.now(timezone.utc)),
        "spec_references": [
            "draft-ietf-vcon-vcon-core-02",
            "draft-ietf-vcon-cc-extension-01",
            "draft-howe-vcon-wtf-extension-02",
            "draft-howe-vcon-consent-00",
            "draft-howe-vcon-sip-signaling-00",
            "draft-howe-vcon-lifecycle-01",
        ],
        "count": len(index),
        "vcons": index,
    }, f, indent=2)

print(f"Wrote {len(index)} vCons + index.json to {OUT_DIR}")
