#!/usr/bin/env python3
"""
Produce vcon-27 — a JWE-form (encrypted) vCon for demo purposes.

The plaintext vCon is built in memory, then sealed with AES-256-GCM.
The symmetric key is generated once and discarded, so once written
the contents are genuinely unreadable from the repo alone.

The unprotected JWE header carries:
  - vcon-uuid    : so the dashboard can list / link to the vCon
  - vcon-created : so the timeline chart can place it
  - cty          : "vcon+json" — what the plaintext WOULD have been

Output: vcon-27-encrypted-internal-meeting.json
"""

import os, json, base64, secrets, uuid
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
NS   = uuid.UUID("11111111-2222-3333-4444-555555555555")

slug = "27-encrypted-internal-meeting"
vcon_uuid = str(uuid.uuid5(NS, slug))
created   = datetime(2026, 5, 9, 10, 0, 0, tzinfo=timezone.utc).replace(microsecond=0).isoformat()

def b64u(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()

# ---- Build the plaintext vCon (this is what's *inside* the encrypted blob) ----
# We never serialise it to disk; only the encrypted form is written.
plaintext_vcon = {
    "vcon": "0.0.2",
    "uuid": vcon_uuid,
    "created_at": created,
    "subject": "[INTERNAL] Board pre-read — Q3 acquisition target review",
    "parties": [
        {"name":"CEO — Alva Sundström", "mailto":"alva@northwind.example"},
        {"name":"CFO — Rajiv Banerjee",  "mailto":"rajiv@northwind.example"},
        {"name":"GC — Hana Mizuhara",     "mailto":"hana@northwind.example"},
    ],
    "dialog": [{
        "type":"recording", "start": created, "duration": 2820.0,
        "parties":[0,1,2], "originator":0,
        "mediatype":"audio/x-wav",
        "filename":"27-encrypted-internal-meeting.wav",
        "disposition":"answered",
        "metadata_only": True,
    }],
    "analysis": [{
        "type":"summary", "dialog":[0],
        "vendor":"Anthropic", "product":"Claude Sonnet 4.6",
        "mediatype":"text/plain", "encoding":"none",
        "body":"M&A pre-read covering target valuation, deal mechanics, and disclosure obligations. Highly confidential."
    }],
    "extensions":[],
}
plaintext_bytes = json.dumps(plaintext_vcon, separators=(",",":")).encode()

# ---- Encrypt with AES-256-GCM (cryptography lib if available; else fallback) ----
try:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    key = AESGCM.generate_key(bit_length=256)   # 32 bytes
    iv  = secrets.token_bytes(12)               # 96-bit nonce, recommended for GCM
    aesgcm = AESGCM(key)
    protected = {"alg":"dir", "enc":"A256GCM",
                 "kid":"vcon-explorer-demo-key-1",
                 "cty":"vcon+json"}
    aad = b64u(json.dumps(protected, separators=(",",":")).encode()).encode()
    ct_and_tag = aesgcm.encrypt(iv, plaintext_bytes, aad)
    ciphertext, tag = ct_and_tag[:-16], ct_and_tag[-16:]
    real_crypto = True
except Exception as e:
    # Fallback: keep the JWE *shape* but with random ciphertext/tag bytes.
    # Still shows up as opaque to the dashboard — the demo intent is preserved.
    print(f"  (cryptography not available — using fake ciphertext: {e})")
    iv         = secrets.token_bytes(12)
    ciphertext = secrets.token_bytes(len(plaintext_bytes))
    tag        = secrets.token_bytes(16)
    protected  = {"alg":"dir", "enc":"A256GCM",
                  "kid":"vcon-explorer-demo-key-1",
                  "cty":"vcon+json", "x-fake":True}
    real_crypto = False

# ---- Wrap into JWE JSON serialization ----
jwe = {
    "protected":    b64u(json.dumps(protected, separators=(",",":")).encode()),
    "encrypted_key":"",   # alg=dir → no wrapped key
    "iv":           b64u(iv),
    "ciphertext":   b64u(ciphertext),
    "tag":          b64u(tag),
    "unprotected": {
        # These claims are visible in the clear so the dashboard can list/route the vCon
        # without ever decrypting it. They are NOT integrity-protected (anyone could
        # rewrite this header), so a production deployment would only put non-sensitive
        # routing metadata here.
        "vcon-uuid":    vcon_uuid,
        "vcon-created": created,
        "cty":          "vcon+json",
        "note":         "Encrypted form (per draft-ietf-vcon-vcon-core §encrypted-form, JWE/RFC 7516).",
    },
}

out = os.path.join(HERE, f"vcon-{slug}.json")
with open(out, "w") as f:
    json.dump(jwe, f, indent=2)

# DELETE the key from memory immediately - we want this to be unrecoverable.
key = b"\x00" * 32 if real_crypto else b""
del key

print(f"Wrote {out}")
print(f"  uuid:        {vcon_uuid}")
print(f"  cipher:      {'AES-256-GCM (real)' if real_crypto else 'fake (cryptography lib unavailable)'}")
print(f"  ciphertext:  {len(ciphertext)} bytes")
print(f"  key:         discarded — vCon is now genuinely opaque")
