#!/usr/bin/env python3
"""Minimal SNMPv2c agent stub used to verify the printer probe paths.

Answers a handful of OIDs with realistic value types so that both the
plain probe and the supply-level logic can be exercised locally.
"""
import socket

SUPPLY_DESC = '1.3.6.1.2.1.43.11.1.1.6.1.'
SUPPLY_MAX = '1.3.6.1.2.1.43.11.1.1.8.1.'
SUPPLY_LEVEL = '1.3.6.1.2.1.43.11.1.1.9.1.'


def tlv(tag, value):
    if isinstance(value, int):
        value = bytes([value])
    n = len(value)
    if n < 0x80:
        length = bytes([n])
    else:
        raw = n.to_bytes((n.bit_length() + 7) // 8, 'big')
        length = bytes([0x80 | len(raw)]) + raw
    return bytes([tag]) + length + value


def int_tlv(v):
    size = max(1, (v.bit_length() + 7) // 8)
    raw = v.to_bytes(size, 'big')
    if raw[0] & 0x80:
        raw = b'\x00' + raw
    return tlv(0x02, raw)


def decode_oid(raw):
    if not raw:
        return ''
    parts = [raw[0] // 40, raw[0] % 40]
    val = 0
    for b in raw[1:]:
        val = (val << 7) | (b & 0x7F)
        if not b & 0x80:
            parts.append(val)
            val = 0
    return '.'.join(str(p) for p in parts)


def answer(oid):
    if oid == '1.3.6.1.2.1.1.1.0':
        return tlv(0x04, b'mock-snmp-device')
    if oid == '1.3.6.1.2.1.43.10.2.1.4.1.1':
        return int_tlv(12345)
    if oid.startswith(SUPPLY_DESC):
        idx = oid[len(SUPPLY_DESC):]
        name = 'Toner Black' if idx == '1' else 'Drum'
        return tlv(0x04, name.encode())
    if oid.startswith(SUPPLY_MAX):
        return int_tlv(100)
    if oid.startswith(SUPPLY_LEVEL):
        idx = oid[len(SUPPLY_LEVEL):]
        return int_tlv(8 if idx == '1' else 82)
    return tlv(0x80, b'')


def handle(data):
    i = 2
    i += 2 + data[i + 1]
    comm_len = data[i + 1]
    community = data[i + 2: i + 2 + comm_len]
    i += 2 + comm_len
    pdu_len = data[i + 1]
    pdu = data[i + 2: i + 2 + pdu_len]
    j = 0
    req_id = pdu[j: j + 2 + pdu[j + 1]]
    j += len(req_id) + 6
    vb_len = pdu[j + 1]
    vb = pdu[j + 2: j + 2 + vb_len]
    oid_len = vb[3]
    oid = decode_oid(vb[4: 4 + oid_len])
    varbind = tlv(0x30, tlv(0x06, vb[4: 4 + oid_len]) + answer(oid))
    resp_pdu = tlv(0xA2, req_id + b'\x02\x01\x00' + b'\x02\x01\x00'
                   + tlv(0x30, varbind))
    body = tlv(0x02, b'\x01') + tlv(0x04, community) + resp_pdu
    return tlv(0x30, body)


def main():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(('0.0.0.0', 161))
    print('mock snmp agent listening on udp/161', flush=True)
    while True:
        data, addr = sock.recvfrom(4096)
        try:
            sock.sendto(handle(data), addr)
        except Exception as exc:
            import traceback
            print('handle error:', exc, flush=True)
            traceback.print_exc()


if __name__ == '__main__':
    main()
