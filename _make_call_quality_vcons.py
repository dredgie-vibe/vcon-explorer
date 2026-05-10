#!/usr/bin/env python3
"""
Generate 5 metadata-only 2-party vCons + matching SIP/RTP pcaps, each
carrying a call_quality analysis with ITU-T / RFC 3611 voice-quality
metrics: MOS, R-Factor, concealed seconds, jitter buffer discards,
burst loss avg, codec impact (Ie).

Profiles span the quality spectrum from pristine to bad so the
"Call quality over time" chart on the dashboard has a useful range.

Outputs:
  vcon-21..25-*.json
  media/<slug>-trace.pcap
"""

import os, json, struct, hashlib, uuid
from datetime import datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
NS   = uuid.UUID("11111111-2222-3333-4444-555555555555")

# -------------------------------------------------------------------
# pcap helpers (SIP + RTP packets, IPv4 + UDP + Ethernet)
# -------------------------------------------------------------------
def ip_csum(hdr: bytes) -> int:
    s = 0
    for i in range(0, len(hdr), 2):
        w = (hdr[i] << 8) | (hdr[i+1] if i+1 < len(hdr) else 0)
        s += w
    s = (s >> 16) + (s & 0xffff); s += s >> 16
    return (~s) & 0xffff

def build_pkt(src_mac, dst_mac, src_ip, dst_ip, sport, dport, payload, ident):
    eth = struct.pack("!6s6sH", dst_mac, src_mac, 0x0800)
    udp_len = 8 + len(payload)
    udp_hdr = struct.pack("!HHHH", sport, dport, udp_len, 0)
    total_len = 20 + udp_len
    no_csum = struct.pack("!BBHHHBBH4s4s",
        0x45, 0x00, total_len, ident & 0xffff, 0, 64, 17, 0, src_ip, dst_ip)
    csum = ip_csum(no_csum)
    ip_hdr = struct.pack("!BBHHHBBH4s4s",
        0x45, 0x00, total_len, ident & 0xffff, 0, 64, 17, csum, src_ip, dst_ip)
    return eth + ip_hdr + udp_hdr + payload

def sip_msg(line, *headers, body=""):
    crlf = "\r\n"
    h = list(headers) + [f"Content-Length: {len(body.encode())}"]
    return (line + crlf + crlf.join(h) + crlf + crlf + body).encode("utf-8")

def rtp_packet(seq, ts, ssrc, payload_type, payload_size=160):
    # Version=2, padding=0, ext=0, CC=0, Marker=0, PT=payload_type
    b1 = 0x80
    b2 = payload_type & 0x7f
    return struct.pack("!BBHII", b1, b2, seq, ts, ssrc) + b"\x00" * payload_size

def write_pcap(path, packets):
    """packets: list of (timestamp_seconds_float, packet_bytes)"""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(struct.pack("<IHHIIII",
            0xa1b2c3d4, 2, 4, 0, 0, 65535, 1))
        for ts, pkt in packets:
            ts_s = int(ts); ts_u = int(round((ts - ts_s) * 1_000_000))
            f.write(struct.pack("<IIII", ts_s, ts_u, len(pkt), len(pkt)))
            f.write(pkt)

# -------------------------------------------------------------------
# Codec table (RTP payload types and SDP rtpmap)
# -------------------------------------------------------------------
CODECS = {
    "G711U":  {"pt": 0,   "rtpmap": "PCMU/8000",     "ptime_ms": 20, "samples": 160},
    "G722":   {"pt": 9,   "rtpmap": "G722/8000",     "ptime_ms": 20, "samples": 160},
    "G729":   {"pt": 18,  "rtpmap": "G729/8000",     "ptime_ms": 20, "samples": 20},
    "OPUS":   {"pt": 111, "rtpmap": "opus/48000/2",  "ptime_ms": 20, "samples": 80},
}

# -------------------------------------------------------------------
# Build a SIP+RTP capture for one call
# -------------------------------------------------------------------
def generate_pcap(profile, out_path):
    p = profile
    codec = CODECS[p["codec"]]
    caller_mac = bytes.fromhex("aa11bb22cc{:02x}".format(p["idx"]))
    callee_mac = bytes.fromhex("dd44ee55ff{:02x}".format(p["idx"]))
    caller_ip  = bytes(p["caller"]["ip"])
    callee_ip  = bytes(p["callee"]["ip"])
    sip_port_caller, sip_port_callee = 5060, 5060
    rtp_port_caller, rtp_port_callee = 49170 + p["idx"]*2, 51022 + p["idx"]*2

    call_id = f"{uuid.uuid5(NS, p['slug']+':callid')}"
    from_tag = f"ft{p['idx']:02d}{uuid.uuid5(NS, p['slug']+':ft').hex[:6]}"
    to_tag   = f"tt{p['idx']:02d}{uuid.uuid5(NS, p['slug']+':tt').hex[:6]}"
    branch   = f"z9hG4bK{uuid.uuid5(NS, p['slug']+':br').hex[:8]}"

    caller_tel = p["caller"]["tel"].replace("-","").replace(" ","")
    callee_tel = p["callee"]["tel"].replace("-","").replace(" ","")
    caller_uri = f"sip:{caller_tel}@carrier.example"
    callee_uri = f"sip:{callee_tel}@northwind.example"

    SDP_OFFER = (
        f"v=0\r\no=caller 1 1 IN IP4 {p['caller']['ip_str']}\r\ns=Voice quality demo\r\n"
        f"c=IN IP4 {p['caller']['ip_str']}\r\nt=0 0\r\n"
        f"m=audio {rtp_port_caller} RTP/AVP {codec['pt']}\r\n"
        f"a=rtpmap:{codec['pt']} {codec['rtpmap']}\r\na=ptime:{codec['ptime_ms']}\r\na=sendrecv\r\n"
    )
    SDP_ANSWER = (
        f"v=0\r\no=callee 2 2 IN IP4 {p['callee']['ip_str']}\r\ns=Voice quality demo\r\n"
        f"c=IN IP4 {p['callee']['ip_str']}\r\nt=0 0\r\n"
        f"m=audio {rtp_port_callee} RTP/AVP {codec['pt']}\r\n"
        f"a=rtpmap:{codec['pt']} {codec['rtpmap']}\r\na=ptime:{codec['ptime_ms']}\r\na=sendrecv\r\n"
    )

    via_caller = f"Via: SIP/2.0/UDP {p['caller']['ip_str']}:5060;branch={branch}"
    common_to  = f"To: <{callee_uri}>"
    common_to_with_tag = f"To: <{callee_uri}>;tag={to_tag}"
    common_from = f'From: "{caller_tel}" <{caller_uri}>;tag={from_tag}'
    common_callid = f"Call-ID: {call_id}"
    contact_caller = f"Contact: <sip:{caller_tel}@{p['caller']['ip_str']}:5060>"
    contact_callee = f"Contact: <sip:{callee_tel}@{p['callee']['ip_str']}:5060>"

    invite = sip_msg(f"INVITE {callee_uri} SIP/2.0",
        via_caller, "Max-Forwards: 70",
        common_from, common_to, common_callid,
        "CSeq: 314159 INVITE", contact_caller,
        "Content-Type: application/sdp", body=SDP_OFFER)

    trying = sip_msg("SIP/2.0 100 Trying",
        via_caller, common_from, common_to, common_callid, "CSeq: 314159 INVITE")

    ringing = sip_msg("SIP/2.0 180 Ringing",
        via_caller, common_from, common_to_with_tag, common_callid,
        contact_callee, "CSeq: 314159 INVITE")

    ok_invite = sip_msg("SIP/2.0 200 OK",
        via_caller, common_from, common_to_with_tag, common_callid,
        "CSeq: 314159 INVITE", contact_callee,
        "Content-Type: application/sdp", body=SDP_ANSWER)

    ack = sip_msg(f"ACK {callee_uri} SIP/2.0",
        via_caller.replace(branch, branch+"-ack"),
        "Max-Forwards: 70",
        common_from, common_to_with_tag, common_callid, "CSeq: 314159 ACK")

    bye = sip_msg(f"BYE {callee_uri} SIP/2.0",
        via_caller.replace(branch, branch+"-bye"),
        "Max-Forwards: 70",
        common_from, common_to_with_tag, common_callid, "CSeq: 314160 BYE")

    bye_ok = sip_msg("SIP/2.0 200 OK",
        via_caller.replace(branch, branch+"-bye"),
        common_from, common_to_with_tag, common_callid, "CSeq: 314160 BYE")

    # Build the timeline
    t0 = p["start"].timestamp()
    duration = p["duration_s"]
    pkts = []
    def c2s(t, payload, ident):
        pkts.append((t, build_pkt(caller_mac, callee_mac, caller_ip, callee_ip,
                                   sip_port_caller, sip_port_callee, payload, ident)))
    def s2c(t, payload, ident):
        pkts.append((t, build_pkt(callee_mac, caller_mac, callee_ip, caller_ip,
                                   sip_port_callee, sip_port_caller, payload, ident)))
    def c2s_rtp(t, payload, ident):
        pkts.append((t, build_pkt(caller_mac, callee_mac, caller_ip, callee_ip,
                                   rtp_port_caller, rtp_port_callee, payload, ident)))
    def s2c_rtp(t, payload, ident):
        pkts.append((t, build_pkt(callee_mac, caller_mac, callee_ip, caller_ip,
                                   rtp_port_callee, rtp_port_caller, payload, ident)))

    base = 0x4000 + p["idx"]*0x100
    c2s(t0 + 0.000, invite,    base+0x01)
    s2c(t0 + 0.012, trying,    base+0x81)
    s2c(t0 + 0.450, ringing,   base+0x82)
    s2c(t0 + 3.870, ok_invite, base+0x83)
    c2s(t0 + 3.880, ack,       base+0x02)

    # ~12 RTP packets covering ~240 ms of media to keep the file small,
    # with deliberate seq gaps reflecting the loss pattern advertised in
    # the call_quality analysis.  This is illustrative — a quality probe
    # in the wild would compute these numbers from a longer capture.
    rtp_start = t0 + 3.900
    rtp_period = codec["ptime_ms"] / 1000.0
    rtp_count = 24
    loss_pattern = p["loss_pattern"]   # set of seq numbers to skip
    ssrc_caller = 0xCAFE0000 | p["idx"]
    ssrc_callee = 0xDEAD0000 | p["idx"]

    for i in range(rtp_count):
        seq_caller = i + 1
        seq_callee = i + 1
        ts = rtp_start + i * rtp_period
        if seq_caller not in loss_pattern:
            c2s_rtp(ts, rtp_packet(seq_caller, codec["samples"]*i, ssrc_caller, codec["pt"], 16),
                    base + 0x10 + i)
        # callee always sends (loss in this direction is rarer in our fake data)
        s2c_rtp(ts + 0.0005,
                rtp_packet(seq_callee, codec["samples"]*i, ssrc_callee, codec["pt"], 16),
                base + 0x90 + i)

    c2s(t0 + duration, bye,    base+0x03)
    s2c(t0 + duration + 0.01, bye_ok, base+0x84)

    # Sort by timestamp (RTP packets may bracket SIP)
    pkts.sort(key=lambda x: x[0])
    write_pcap(out_path, pkts)
    return os.path.getsize(out_path), len(pkts)

# -------------------------------------------------------------------
# Profiles
# -------------------------------------------------------------------
def loc(name, region, country):
    return {"locality": name, "region": region, "country": country}

PROFILES = [
    {
        "idx": 1,
        "slug": "21-quality-santaclarita-scottsdale-pristine",
        "subject": "Santa Clarita CA → Scottsdale AZ — pristine line",
        "caller": {"name":"Mariana Velasco",  "tel":"+1-661-555-0142", "ip":[198,51,100,10],
                   "ip_str":"198.51.100.10",  "civic": loc("Santa Clarita","CA","US"),
                   "tz":"America/Los_Angeles"},
        "callee": {"name":"Trent Halverson",  "tel":"+1-480-555-0188", "ip":[203,0,113,10],
                   "ip_str":"203.0.113.10",   "civic": loc("Scottsdale","AZ","US"),
                   "tz":"America/Phoenix"},
        "start":      datetime(2026, 5, 4, 17, 12,  0, tzinfo=timezone.utc),
        "duration_s": 392.7,
        "codec":      "G722",
        "loss_pattern": set(),  # no loss
        "quality": {
            "mos": 4.42, "r_factor": 92.0,
            "concealed_seconds": 0.0,
            "jitter_buffer_discards": 3,
            "burst_loss_avg_packets": 0.0,
            "codec_impact_ie": 5,
            "codec": "G.722/16000",
            "jitter_ms": 4.1,
            "avg_loss_pct": 0.05,
            "latency_ms_round_trip": 36,
            "samples_total": 19635,
            "rating": "excellent",
        },
    },
    {
        "idx": 2,
        "slug": "22-quality-nyc-boston-good",
        "subject": "Manhattan NY → Boston MA — good narrowband",
        "caller": {"name":"Devorah Greenwald", "tel":"+1-212-555-0301", "ip":[198,51,100,20],
                   "ip_str":"198.51.100.20",   "civic": loc("New York","NY","US"),
                   "tz":"America/New_York"},
        "callee": {"name":"Marcus O'Connell",  "tel":"+1-617-555-0719", "ip":[203,0,113,20],
                   "ip_str":"203.0.113.20",    "civic": loc("Boston","MA","US"),
                   "tz":"America/New_York"},
        "start":      datetime(2026, 5, 5, 14, 33, 18, tzinfo=timezone.utc),
        "duration_s": 184.2,
        "codec":      "G711U",
        "loss_pattern": {7, 13},
        "quality": {
            "mos": 4.08, "r_factor": 84.6,
            "concealed_seconds": 1.2,
            "jitter_buffer_discards": 22,
            "burst_loss_avg_packets": 1.4,
            "codec_impact_ie": 0,
            "codec": "G.711µ/8000",
            "jitter_ms": 11.8,
            "avg_loss_pct": 0.4,
            "latency_ms_round_trip": 58,
            "samples_total": 9210,
            "rating": "good",
        },
    },
    {
        "idx": 3,
        "slug": "23-quality-chicago-denver-degraded",
        "subject": "Chicago IL → Denver CO — degraded (jitter+loss)",
        "caller": {"name":"Solomon Patel",   "tel":"+1-312-555-0466", "ip":[198,51,100,30],
                   "ip_str":"198.51.100.30", "civic": loc("Chicago","IL","US"),
                   "tz":"America/Chicago"},
        "callee": {"name":"Camila Riviera",  "tel":"+1-720-555-0210", "ip":[203,0,113,30],
                   "ip_str":"203.0.113.30",  "civic": loc("Denver","CO","US"),
                   "tz":"America/Denver"},
        "start":      datetime(2026, 5, 6,  9, 47,  5, tzinfo=timezone.utc),
        "duration_s": 612.4,
        "codec":      "OPUS",
        "loss_pattern": {3, 4, 9, 10, 17, 21, 22},
        "quality": {
            "mos": 3.52, "r_factor": 70.1,
            "concealed_seconds": 8.3,
            "jitter_buffer_discards": 87,
            "burst_loss_avg_packets": 2.8,
            "codec_impact_ie": 4,
            "codec": "Opus/16000",
            "jitter_ms": 41.2,
            "avg_loss_pct": 2.1,
            "latency_ms_round_trip": 92,
            "samples_total": 30620,
            "rating": "fair",
        },
    },
    {
        "idx": 4,
        "slug": "24-quality-london-tokyo-latency",
        "subject": "London → Tokyo — high-latency international",
        "caller": {"name":"Niamh Ó Briain",   "tel":"+44-20-7946-0123", "ip":[198,51,100,40],
                   "ip_str":"198.51.100.40", "civic": loc("London","England","GB"),
                   "tz":"Europe/London"},
        "callee": {"name":"Aiko Tanaka",       "tel":"+81-3-5555-1234",  "ip":[203,0,113,40],
                   "ip_str":"203.0.113.40",   "civic": loc("Tokyo","Tokyo","JP"),
                   "tz":"Asia/Tokyo"},
        "start":      datetime(2026, 5, 7, 11,  4, 12, tzinfo=timezone.utc),
        "duration_s": 248.0,
        "codec":      "G729",
        "loss_pattern": {5, 11, 18},
        "quality": {
            "mos": 2.91, "r_factor": 58.4,
            "concealed_seconds": 5.1,
            "jitter_buffer_discards": 34,
            "burst_loss_avg_packets": 2.0,
            "codec_impact_ie": 11,
            "codec": "G.729/8000",
            "jitter_ms": 22.5,
            "avg_loss_pct": 1.0,
            "latency_ms_round_trip": 248,
            "samples_total": 12400,
            "rating": "poor",
        },
    },
    {
        "idx": 5,
        "slug": "25-quality-atlanta-miami-burst-loss",
        "subject": "Atlanta GA → Miami FL — heavy burst loss",
        "caller": {"name":"Tyrese Rutherford", "tel":"+1-404-555-0922", "ip":[198,51,100,50],
                   "ip_str":"198.51.100.50",   "civic": loc("Atlanta","GA","US"),
                   "tz":"America/New_York"},
        "callee": {"name":"Renata Aguilar",    "tel":"+1-305-555-0501", "ip":[203,0,113,50],
                   "ip_str":"203.0.113.50",    "civic": loc("Miami","FL","US"),
                   "tz":"America/New_York"},
        "start":      datetime(2026, 5, 8, 21, 19, 41, tzinfo=timezone.utc),
        "duration_s": 158.7,
        "codec":      "G722",
        "loss_pattern": {2,3,4,5, 11,12,13, 19,20,21,22},
        "quality": {
            "mos": 2.41, "r_factor": 47.8,
            "concealed_seconds": 19.4,
            "jitter_buffer_discards": 142,
            "burst_loss_avg_packets": 6.7,
            "codec_impact_ie": 5,
            "codec": "G.722/16000",
            "jitter_ms": 38.4,
            "avg_loss_pct": 4.1,
            "latency_ms_round_trip": 71,
            "samples_total": 7935,
            "rating": "bad",
        },
    },
]

# -------------------------------------------------------------------
# Build vCons + pcaps
# -------------------------------------------------------------------
def iso(dt):
    return dt.replace(microsecond=0).isoformat()

def make_party(p):
    return {
        "name":         p["name"],
        "tel":          p["tel"],
        "civicaddress": p["civic"],
        "timezone":     p["tz"],
    }

def fake_hash(b: bytes) -> str:
    return "sha512-" + hashlib.sha512(b).hexdigest()

def main():
    outputs = []
    for p in PROFILES:
        # 1. pcap
        pcap_filename = f"{p['slug']}-trace.pcap"
        pcap_path = os.path.join(HERE, "media", pcap_filename)
        size, npkts = generate_pcap(p, pcap_path)
        with open(pcap_path,"rb") as f:
            pcap_hash = fake_hash(f.read())

        # 2. vCon
        vcon = {
            "vcon": "0.0.2",
            "uuid": str(uuid.uuid5(NS, p["slug"])),
            "created_at": iso(p["start"] + timedelta(minutes=3)),
            "subject":    p["subject"],
            "parties": [make_party(p["caller"]), make_party(p["callee"])],
            "dialog": [{
                "type":        "recording",
                "start":       iso(p["start"]),
                "duration":    p["duration_s"],
                "parties":     [0, 1],
                "originator":  0,
                "mediatype":   "audio/x-wav",
                "disposition": "answered",
                "metadata_only": True,  # informational; tells the dashboard to skip the player
            }],
            "analysis": [{
                "type":      "call_quality",
                "dialog":    [0],
                "vendor":    "Cygnus Voice Quality Probe",
                "product":   "VQProbe v3.4 (RFC 3611 / G.107 E-model)",
                "schema":    "RFC3611-XR / G.107-Emodel",
                "mediatype": "application/json",
                "encoding":  "json",
                "filename":  f"{p['slug']}-quality.json",
                "body":      json.dumps(p["quality"], indent=2),
            }],
            "attachments": [{
                "type":         "sip_pcap",
                "mediatype":    "application/vnd.tcpdump.pcap",
                "filename":     pcap_filename,
                "dialog":       [0],
                "url":          f"https://media.vcon.example.net/{pcap_filename}",
                "content_hash": pcap_hash,
                "alg":          "SHA-512",
            }],
        }

        # write JSON
        json_filename = f"vcon-{p['slug']}.json"
        with open(os.path.join(HERE, json_filename), "w") as f:
            json.dump(vcon, f, indent=2)
        outputs.append((json_filename, pcap_filename, size, npkts, p["quality"]["mos"]))
        print(f"  wrote {json_filename:50s}  pcap {size:5d}b ({npkts:2d} pkts)  MoS {p['quality']['mos']}")

    print(f"\nGenerated {len(outputs)} vCons + {len(outputs)} pcaps.")
    print("Now run:  python3 _index.py   to refresh index.json")

if __name__ == "__main__":
    main()
