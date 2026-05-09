#!/usr/bin/env python3
"""
Rebuild index.json by scanning every vcon-*.json file in this directory.

Run this any time you add (or hand-edit) a vCon JSON file. The dashboard
(index.html) reads index.json on load and uses it as the manifest of
files to fetch.

    python3 _index.py
"""

import json, os, glob
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))

EXT_KNOWN = {
    "CC":        "Contact Center (draft-ietf-vcon-cc-extension)",
    "WTF":       "World Transcription Format (draft-howe-vcon-wtf-extension)",
    "Consent":   "Consent attachment (draft-howe-vcon-consent)",
    "SIP":       "SIP signaling (draft-howe-vcon-sip-signaling)",
    "Lifecycle": "SCITT lifecycle (draft-howe-vcon-lifecycle)",
}

def iso_now():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()

def main():
    files = sorted(glob.glob(os.path.join(HERE, "vcon-*.json")))
    rows = []
    for fp in files:
        try:
            v = json.load(open(fp))
        except Exception as e:
            print(f"  ! skipping {os.path.basename(fp)}: {e}")
            continue
        rows.append({
            "file":             os.path.basename(fp),
            "uuid":             v.get("uuid"),
            "subject":          v.get("subject"),
            "created_at":       v.get("created_at"),
            "extensions":       v.get("extensions", []),
            "must_support":     v.get("must_support", []),
            "party_count":      len(v.get("parties",     [])),
            "dialog_count":     len(v.get("dialog",      [])),
            "analysis_count":   len(v.get("analysis",    [])),
            "attachment_count": len(v.get("attachments", [])),
            "category":         "extended" if v.get("extensions") else "standard",
        })

    out = {
        "schema":          "vcon-corpus-index/0.1",
        "generated_at":    iso_now(),
        "spec_references": [
            "draft-ietf-vcon-vcon-core-02",
            "draft-ietf-vcon-cc-extension-01",
            "draft-howe-vcon-wtf-extension-02",
            "draft-howe-vcon-consent-00",
            "draft-howe-vcon-sip-signaling-00",
            "draft-howe-vcon-lifecycle-01",
        ],
        "extensions_known": EXT_KNOWN,
        "count":            len(rows),
        "vcons":            rows,
    }
    with open(os.path.join(HERE, "index.json"), "w") as f:
        json.dump(out, f, indent=2)
    print(f"Reindexed {len(rows)} vCon files -> index.json")

if __name__ == "__main__":
    main()
