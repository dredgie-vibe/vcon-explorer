#!/usr/bin/env python3
"""
Generate a small but real .pcap file containing a SIP/UDP call exchange
that mirrors the parties on vcon-18-cc-sip-signaling.

Output: media/vcon-18-cc-sip-signaling-attached-trace.pcap

Pure stdlib — no scapy, no Wireshark needed to produce.
The resulting file opens cleanly in Wireshark / tshark / tcpdump.
"""
import struct, os
from datetime import datetime, timezone

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                   "media", "vcon-18-cc-sip-signaling-attached-trace.pcap")

# ----- Endpoints (match the vcon-18 fictional exchange) ---------------
CALLER_MAC = bytes.fromhex("aa11bb22cc33")
CALLEE_MAC = bytes.fromhex("dd44ee55ff66")
CALLER_IP  = bytes([192,168,1,10])
CALLEE_IP  = bytes([10,0,5,20])
CALLER_PORT = 5060
CALLEE_PORT = 5060
CALL_ID    = "a47f8b2e-9c1d-4a5b-9f3a-1e2f3a4b5c6d@edge1.northwind.example"
FROM_TAG   = "as5d8f9a"
TO_TAG     = "r19f8c2b"
BRANCH     = "z9hG4bK74bf9"
CALLER_URI = "sip:+14155550998@carrier.example"
CALLEE_URI = "sip:+17375550911@northwind.example"

# Anchor the capture to vcon-18's start time (2026-05-07 20:11:00 UTC)
T0 = datetime(2026, 5, 7, 20, 11, 0, tzinfo=timezone.utc).timestamp()

# ----- Helpers --------------------------------------------------------
def ip_csum(hdr: bytes) -> int:
    s = 0
    for i in range(0, len(hdr), 2):
        w = (hdr[i] << 8) | (hdr[i+1] if i+1 < len(hdr) else 0)
        s += w
    s = (s >> 16) + (s & 0xffff); s += s >> 16
    return (~s) & 0xffff

def build_pkt(src_mac, dst_mac, src_ip, dst_ip, sport, dport, payload, ident):
    eth = struct.pack("!6s6sH", dst_mac, src_mac, 0x0800)
    udp_len  = 8 + len(payload)
    udp_hdr  = struct.pack("!HHHH", sport, dport, udp_len, 0)  # csum 0 (legal for UDP/IPv4)
    total_len = 20 + udp_len
    ip_no_csum = struct.pack("!BBHHHBBH4s4s",
        0x45, 0x00, total_len, ident & 0xffff, 0, 64, 17, 0, src_ip, dst_ip)
    csum = ip_csum(ip_no_csum)
    ip_hdr = struct.pack("!BBHHHBBH4s4s",
        0x45, 0x00, total_len, ident & 0xffff, 0, 64, 17, csum, src_ip, dst_ip)
    return eth + ip_hdr + udp_hdr + payload

def sip(method_or_status, *headers, body=""):
    """Build a SIP message (CRLF-terminated lines, blank line, body)."""
    crlf = "\r\n"
    h = list(headers) + [f"Content-Length: {len(body.encode())}"]
    return (method_or_status + crlf + crlf.join(h) + crlf + crlf + body).encode("utf-8")

# ----- SIP message bodies --------------------------------------------
SDP_OFFER = (
    "v=0\r\n"
    "o=caller 1 1 IN IP4 192.168.1.10\r\n"
    "s=Northwind STIR/SHAKEN call\r\n"
    "c=IN IP4 192.168.1.10\r\n"
    "t=0 0\r\n"
    "m=audio 49170 RTP/AVP 111\r\n"
    "a=rtpmap:111 opus/48000/2\r\n"
    "a=fmtp:111 useinbandfec=1\r\n"
    "a=sendrecv\r\n"
)
SDP_ANSWER = (
    "v=0\r\n"
    "o=callee 2 2 IN IP4 10.0.5.20\r\n"
    "s=Northwind STIR/SHAKEN call\r\n"
    "c=IN IP4 10.0.5.20\r\n"
    "t=0 0\r\n"
    "m=audio 51022 RTP/AVP 111\r\n"
    "a=rtpmap:111 opus/48000/2\r\n"
    "a=sendrecv\r\n"
)

def via(host, port, branch=BRANCH):
    return f"Via: SIP/2.0/UDP {host}:{port};branch={branch}"

# Caller -> Callee: INVITE
m_invite = sip("INVITE " + CALLEE_URI + " SIP/2.0",
    via("192.168.1.10", 5060),
    "Max-Forwards: 70",
    "From: \"+14155550998\" <" + CALLER_URI + ">;tag=" + FROM_TAG,
    "To: <" + CALLEE_URI + ">",
    "Call-ID: " + CALL_ID,
    "CSeq: 314159 INVITE",
    "Contact: <sip:+14155550998@192.168.1.10:5060>",
    "Identity: eyJhbGciOiJFUzI1NiIsInBwdCI6InNoYWtlbiJ9..."  # truncated PASSporT
        ";info=<https://cert.carrier.example/v.crt>"
        ";alg=ES256;ppt=shaken",
    "Content-Type: application/sdp",
    body=SDP_OFFER)

# Callee -> Caller: 100 Trying
m_trying = sip("SIP/2.0 100 Trying",
    via("192.168.1.10", 5060),
    "From: \"+14155550998\" <" + CALLER_URI + ">;tag=" + FROM_TAG,
    "To: <" + CALLEE_URI + ">",
    "Call-ID: " + CALL_ID,
    "CSeq: 314159 INVITE")

# Callee -> Caller: 180 Ringing
m_ringing = sip("SIP/2.0 180 Ringing",
    via("192.168.1.10", 5060),
    "From: \"+14155550998\" <" + CALLER_URI + ">;tag=" + FROM_TAG,
    "To: <" + CALLEE_URI + ">;tag=" + TO_TAG,
    "Call-ID: " + CALL_ID,
    "Contact: <sip:+17375550911@10.0.5.20:5060>",
    "CSeq: 314159 INVITE")

# Callee -> Caller: 200 OK (with SDP answer)
m_200 = sip("SIP/2.0 200 OK",
    via("192.168.1.10", 5060),
    "From: \"+14155550998\" <" + CALLER_URI + ">;tag=" + FROM_TAG,
    "To: <" + CALLEE_URI + ">;tag=" + TO_TAG,
    "Call-ID: " + CALL_ID,
    "CSeq: 314159 INVITE",
    "Contact: <sip:+17375550911@10.0.5.20:5060>",
    "Content-Type: application/sdp",
    body=SDP_ANSWER)

# Caller -> Callee: ACK
m_ack = sip("ACK " + CALLEE_URI + " SIP/2.0",
    via("192.168.1.10", 5060, branch="z9hG4bK74bf9-ack"),
    "Max-Forwards: 70",
    "From: \"+14155550998\" <" + CALLER_URI + ">;tag=" + FROM_TAG,
    "To: <" + CALLEE_URI + ">;tag=" + TO_TAG,
    "Call-ID: " + CALL_ID,
    "CSeq: 314159 ACK")

# ... ~240s of conversation here (RTP packets omitted for brevity) ...

# Caller -> Callee: BYE (after 240.5s, the dialog duration in vcon-18)
m_bye = sip("BYE " + CALLEE_URI + " SIP/2.0",
    via("192.168.1.10", 5060, branch="z9hG4bK74bf9-bye"),
    "Max-Forwards: 70",
    "From: \"+14155550998\" <" + CALLER_URI + ">;tag=" + FROM_TAG,
    "To: <" + CALLEE_URI + ">;tag=" + TO_TAG,
    "Call-ID: " + CALL_ID,
    "CSeq: 314160 BYE")

# Callee -> Caller: 200 OK to BYE
m_bye_ok = sip("SIP/2.0 200 OK",
    via("192.168.1.10", 5060, branch="z9hG4bK74bf9-bye"),
    "From: \"+14155550998\" <" + CALLER_URI + ">;tag=" + FROM_TAG,
    "To: <" + CALLEE_URI + ">;tag=" + TO_TAG,
    "Call-ID: " + CALL_ID,
    "CSeq: 314160 BYE")

# ----- Build the packet timeline -------------------------------------
flow = [
    # (offset_seconds, direction, payload, ip_ident)
    (0.000, "c2s", m_invite,  0x4001),
    (0.012, "s2c", m_trying,  0x5001),
    (0.450, "s2c", m_ringing, 0x5002),
    (3.870, "s2c", m_200,     0x5003),
    (3.880, "c2s", m_ack,     0x4002),
    (240.500, "c2s", m_bye,   0x4003),
    (240.510, "s2c", m_bye_ok, 0x5004),
]

os.makedirs(os.path.dirname(OUT), exist_ok=True)
with open(OUT, "wb") as f:
    # Global pcap header
    f.write(struct.pack("<IHHIIII",
        0xa1b2c3d4,  # magic (microsecond)
        2, 4,        # version
        0, 0,        # thiszone, sigfigs
        65535,       # snaplen
        1))          # network = Ethernet
    for offset, direction, payload, ident in flow:
        ts = T0 + offset
        ts_sec = int(ts); ts_usec = int(round((ts - ts_sec) * 1_000_000))
        if direction == "c2s":
            pkt = build_pkt(CALLER_MAC, CALLEE_MAC, CALLER_IP, CALLEE_IP,
                            CALLER_PORT, CALLEE_PORT, payload, ident)
        else:
            pkt = build_pkt(CALLEE_MAC, CALLER_MAC, CALLEE_IP, CALLER_IP,
                            CALLEE_PORT, CALLER_PORT, payload, ident)
        f.write(struct.pack("<IIII", ts_sec, ts_usec, len(pkt), len(pkt)))
        f.write(pkt)

print(f"Wrote {OUT}  ({os.path.getsize(OUT)} bytes, {len(flow)} packets)")
