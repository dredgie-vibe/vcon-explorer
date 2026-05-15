#!/usr/bin/env python3
"""
Generate real, verifiable SCITT receipts for every receipt URN referenced
by any vCon in this directory with a Lifecycle attachment.

Each receipt is a COSE_Sign1 (RFC 9052, CBOR tag 18) carrying:
  - protected header: alg (ES256), kid, vds (RFC9162-SHA256), issuer, subject-uuid
  - unprotected header: inclusion proof (tree_size, leaf_index, audit_path[])
  - detached payload (nil on the wire; the *Merkle root* is the signed payload
    placed into the Sig_structure when computing the signature)
  - signature: ES256 (ECDSA P-256 / SHA-256), raw r||s (64 bytes)

The full COSE_Sign1 bytes are written to .cbor. A small sidecar JSON next to
each receipt carries the public JWK and the leaf so the browser viewer can
independently verify the signature and the Merkle inclusion proof without
having to derive anything from the receipt's binary form.

Each vCon gets its own Merkle tree (i.e. is a separate "log slice"). Within
a tree, the vCon's events occupy a contiguous block of leaf positions; the
remaining positions are random filler representing other artifacts the TS
has logged. All receipts within one vCon's tree resolve to the same root.

Run from the vcon-explorer root:
    python3 _make_scitt_receipts.py
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import sys
from pathlib import Path

import cbor2
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature

HERE = Path(__file__).resolve().parent
OUT_DIR = HERE / "media" / "scitt-receipts"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# Labels used in the receipt. The COSE-receipts draft has flopped on exact
# integer assignments at least twice; -111/-112 below are "private use" range
# numbers chosen for this demo and not normative anywhere. The header keys
# that ARE normative (1=alg, 4=kid) follow RFC 9052; 395/396 are the values
# the COSE WG was using for vds and inclusion-proof at last check.
ALG = 1
KID = 4
VDS = 395
INCLUSION_PROOF = 396
ISSUER = -111   # demo label
SUBJECT = -112  # demo label

ALG_ES256 = -7
VDS_RFC9162_SHA256 = 1

# RFC 9162 hashing convention:
#   leaf = SHA256(0x00 || raw_leaf_bytes)
#   inner_node = SHA256(0x01 || left || right)
def _leaf_hash(raw: bytes) -> bytes:
    return hashlib.sha256(b"\x00" + raw).digest()


def _inner(left: bytes, right: bytes) -> bytes:
    return hashlib.sha256(b"\x01" + left + right).digest()


def _root_from_proof(leaf: bytes, leaf_index: int, audit_path: list[bytes]) -> bytes:
    """Walk an RFC 9162 audit path upward, deriving the tree root."""
    node = leaf
    idx = leaf_index
    for sibling in audit_path:
        if idx & 1:
            node = _inner(sibling, node)   # we're on the right
        else:
            node = _inner(node, sibling)   # we're on the left
        idx >>= 1
    return node


def _b64u(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def _build_receipt(
    *,
    receipt_urn: str,
    issued_at: str,
    subject_vcon_uuid: str,
    statement_bytes: bytes,
    leaf_index: int,
    tree_size: int,
    audit_path: list[bytes],
) -> tuple[bytes, dict]:
    """Return (cose_sign1_bytes, sidecar_dict)."""

    # 1. Generate an ES256 keypair for the Transparency Service.
    #    In production this is the TS's persistent signing key; here we mint
    #    a fresh one per run so the demo is fully self-contained.
    priv = ec.generate_private_key(ec.SECP256R1())
    pub_numbers = priv.public_key().public_numbers()
    x_bytes = pub_numbers.x.to_bytes(32, "big")
    y_bytes = pub_numbers.y.to_bytes(32, "big")
    kid = hashlib.sha256(b"scitt.example.org\x00" + x_bytes + y_bytes).digest()[:8]

    # 2. Compute the leaf hash, then derive the tree root via the audit path.
    leaf = _leaf_hash(statement_bytes)
    root = _root_from_proof(leaf, leaf_index, audit_path)

    # 3. Build the protected header (CBOR canonical encoding, then bstr-wrap).
    protected = {
        ALG: ALG_ES256,
        KID: kid,
        VDS: VDS_RFC9162_SHA256,
        ISSUER: "scitt.example.org",
        SUBJECT: subject_vcon_uuid,
    }
    protected_bytes = cbor2.dumps(protected, canonical=True)

    # 4. Build the unprotected header. The inclusion proof is carried as a
    #    3-element array [tree_size, leaf_index, audit_path[]]. The COSE
    #    receipts draft formalises this as a labelled map; for the demo we
    #    use the array form which is what most reference implementations
    #    emit today.
    unprotected = {
        INCLUSION_PROOF: [tree_size, leaf_index, audit_path],
    }

    # 5. Build Sig_structure per RFC 9052 §4.4. For a *detached* payload, the
    #    wire form puts `null` in the payload slot but we MUST sign over the
    #    real payload bytes (here: the tree root) when computing the signature.
    sig_structure = ["Signature1", protected_bytes, b"", root]
    to_be_signed = cbor2.dumps(sig_structure, canonical=True)

    # 6. ECDSA-sign. cryptography returns DER; COSE wants raw r||s, each
    #    left-padded to the curve size (32 bytes for P-256).
    der_sig = priv.sign(to_be_signed, ec.ECDSA(hashes.SHA256()))
    r, s = decode_dss_signature(der_sig)
    raw_sig = r.to_bytes(32, "big") + s.to_bytes(32, "big")

    # 7. Assemble the COSE_Sign1 (tag 18). Payload slot is null (detached).
    cose_sign1 = cbor2.CBORTag(18, [protected_bytes, unprotected, None, raw_sig])
    receipt_bytes = cbor2.dumps(cose_sign1, canonical=True)

    # 8. Sidecar: everything the viewer needs to verify without secret
    #    knowledge. The viewer recomputes the leaf from `statement_bytes`,
    #    walks the audit path to derive the root, rebuilds the Sig_structure,
    #    and verifies the signature using the JWK below.
    sidecar = {
        "receipt_urn": receipt_urn,
        "transparency_service": "https://scitt.example.org/v1",
        "issued_at": issued_at,
        "subject_vcon_uuid": subject_vcon_uuid,
        "alg": "ES256",
        "vds": "RFC9162_SHA256",
        "kid_b64u": _b64u(kid),
        "jwk": {
            "kty": "EC",
            "crv": "P-256",
            "x": _b64u(x_bytes),
            "y": _b64u(y_bytes),
        },
        "statement": {
            # Base64url of the bytes that were leaf-hashed. The viewer
            # recomputes the leaf as SHA256(0x00 || statement_bytes).
            "bytes_b64u": _b64u(statement_bytes),
            "description": (
                "Canonical JSON of the vCon attachment that this receipt attests to."
            ),
        },
        "merkle": {
            "tree_size": tree_size,
            "leaf_index": leaf_index,
            "audit_path_b64u": [_b64u(p) for p in audit_path],
            "expected_root_b64u": _b64u(root),
            "hash_alg": "SHA-256",
            "convention": "RFC 9162 (CT): leaf = SHA256(0x00||x), inner = SHA256(0x01||L||R)",
        },
    }
    return receipt_bytes, sidecar


# ---------------------------------------------------------------------------
# Tree construction helpers
# ---------------------------------------------------------------------------

def _canonical(obj) -> bytes:
    """RFC 8785-ish: sorted keys, no whitespace, UTF-8."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _statement_for_event(vcon_obj: dict, event: dict) -> bytes:
    """Build the canonical bytes that the TS would have logged for this event.

    For demo purposes we pin to a stable per-event statement:
       { "kind", "vcon_uuid", "vcon_sha256", "event", "at", "actor", "details?" }
    Including the SHA-256 of the canonical vCon JSON binds the statement to
    a specific vCon snapshot, which is what a real registration policy would
    require.
    """
    vcon_canon = _canonical(vcon_obj)
    vcon_digest = hashlib.sha256(vcon_canon).hexdigest()
    statement = {
        "kind": "vcon-lifecycle-event",
        "vcon_uuid": vcon_obj["uuid"],
        "vcon_sha256": vcon_digest,
        "event": event["event"],
        "at": event["at"],
        "actor": event.get("actor"),
    }
    if "details" in event:
        statement["details"] = event["details"]
    return _canonical(statement)


def _build_tree(level0: list[bytes]) -> list[list[bytes]]:
    """Build a Merkle tree level by level. Odd nodes are duplicated upward
    ("duplicate last" convention — fine for a demo)."""
    levels = [level0]
    cur = level0
    while len(cur) > 1:
        nxt: list[bytes] = []
        for i in range(0, len(cur), 2):
            left = cur[i]
            right = cur[i + 1] if i + 1 < len(cur) else cur[i]
            nxt.append(_inner(left, right))
        levels.append(nxt)
        cur = nxt
    return levels


def _audit_path(levels: list[list[bytes]], idx: int) -> list[bytes]:
    path: list[bytes] = []
    for lvl in range(len(levels) - 1):
        row = levels[lvl]
        sib = idx ^ 1
        if sib >= len(row):
            sib = idx  # duplicated last
        path.append(row[sib])
        idx //= 2
    return path


def _discover_lifecycle_vcons() -> list[Path]:
    """Return every vcon-*.json with a Lifecycle attachment, sorted."""
    out = []
    for path in sorted(HERE.glob("vcon-*.json")):
        try:
            v = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if "Lifecycle" not in v.get("extensions", []):
            continue
        if not any(a.get("type") == "lifecycle" for a in v.get("attachments", [])):
            continue
        out.append(path)
    return out


def _process_one_vcon(vcon_path: Path) -> list[dict]:
    """Generate receipts for every event in this vCon's lifecycle. Returns
    a list of summary dicts, one per receipt."""
    vcon = json.loads(vcon_path.read_text(encoding="utf-8"))
    lc_attachment = next(
        a for a in vcon["attachments"] if a.get("type") == "lifecycle"
    )
    lifecycle = json.loads(lc_attachment["body"])
    events = [e for e in lifecycle.get("events", []) if e.get("receipt")]
    if not events:
        return []

    rng = os.urandom

    # Place events in the middle of a small tree so audit paths exercise
    # multiple levels. start_idx = 3 keeps paths interesting for small N.
    n_events = len(events)
    start_idx = 3
    tree_size = max(16, start_idx + n_events + 3)

    leaves: list[bytes] = []
    statements: dict[int, bytes] = {}
    receipt_urns: dict[int, str] = {}
    for i in range(tree_size):
        if start_idx <= i < start_idx + n_events:
            ev = events[i - start_idx]
            raw = _statement_for_event(vcon, ev)
            leaves.append(_leaf_hash(raw))
            statements[i] = raw
            receipt_urns[i] = ev["receipt"]
        else:
            leaves.append(_leaf_hash(rng(64)))

    levels = _build_tree(leaves)
    true_root = levels[-1][0]

    summary: list[dict] = []
    for i, raw in statements.items():
        urn = receipt_urns[i]
        rid = urn.rsplit(":", 1)[-1]
        ev = events[i - start_idx]
        audit_path = _audit_path(levels, i)

        receipt_bytes, sidecar = _build_receipt(
            receipt_urn=urn,
            issued_at=ev["at"],
            subject_vcon_uuid=vcon["uuid"],
            statement_bytes=raw,
            leaf_index=i,
            tree_size=tree_size,
            audit_path=audit_path,
        )

        # Sanity-check that the audit path reproduces the true tree root.
        derived = _root_from_proof(_leaf_hash(raw), i, audit_path)
        assert derived == true_root, (
            f"audit path for {urn} does not reproduce the true tree root"
        )

        (OUT_DIR / f"{rid}.cbor").write_bytes(receipt_bytes)
        (OUT_DIR / f"{rid}.json").write_text(
            json.dumps(sidecar, indent=2), encoding="utf-8"
        )
        summary.append(
            {
                "urn": urn,
                "id": rid,
                "event": ev["event"],
                "vcon_uuid": vcon["uuid"],
                "vcon_file": vcon_path.name,
                "size_bytes": len(receipt_bytes),
            }
        )

    return summary


def main() -> int:
    paths = _discover_lifecycle_vcons()
    if not paths:
        print("No vCons with a Lifecycle attachment found.", file=sys.stderr)
        return 1

    all_summaries: list[dict] = []
    transparency_service = None
    for p in paths:
        summaries = _process_one_vcon(p)
        all_summaries.extend(summaries)
        # Pull TS URL from the first lifecycle we see.
        if transparency_service is None:
            v = json.loads(p.read_text(encoding="utf-8"))
            lc = next(a for a in v["attachments"] if a.get("type") == "lifecycle")
            body = json.loads(lc["body"])
            transparency_service = body.get("transparency_service")

    # Manifest. The viewer reads this to know which URNs have real .cbor
    # files backing them, and renders only those as clickable links.
    manifest = {
        "generated_at": None,
        "transparency_service": transparency_service,
        "vcons": sorted({s["vcon_file"] for s in all_summaries}),
        "receipts": all_summaries,
    }
    (OUT_DIR / "_manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )

    print(f"Wrote {len(all_summaries)} receipts across "
          f"{len(manifest['vcons'])} vCons to {OUT_DIR}")
    by_vcon: dict[str, list[dict]] = {}
    for s in all_summaries:
        by_vcon.setdefault(s["vcon_file"], []).append(s)
    for vfile, items in by_vcon.items():
        print(f"  {vfile}: {len(items)} receipts")
        for s in items:
            print(f"    {s['id']}  {s['event']:<22}  {s['size_bytes']} bytes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
