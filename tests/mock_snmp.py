#!/usr/bin/env python3
"""Minimal SNMPv2c agent stub, used only to verify the positive path of the printer probe."""
import socket


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
    j += len(req_id)
    # error-status + error-index: 各为 02 01 00，共 3 字节，合计 6 字节
    j += 3
    j += 3
    vb_len = pdu[j + 1]
    vb = pdu[j + 2: j + 2 + vb_len]
    oid_len = vb[3]
    oid = vb[4: 4 + oid_len]
    varbind = tlv(0x30, tlv(0x06, oid) + tlv(0x04, b'mock-snmp-device'))
    resp_pdu = tlv(0xA2, req_id + b'\x02\x01\x00' + b'\x02\x01\x00' + tlv(0x30, varbind))
    body = tlv(0x02, b'\x01') + tlv(0x04, community) + resp_pdu
    return tlv(0x30, body)


def main():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(('0.0.0.0', 161))
    print('mock snmp agent listening on udp/161', flush=True)
    while True:
        data, addr = sock.recvfrom(4096)
        print('recv', len(data), 'bytes from', addr, data.hex(), flush=True)
        try:
            sock.sendto(handle(data), addr)
        except Exception as exc:
            import traceback
            print('handle error:', exc, flush=True)
            traceback.print_exc()


if __name__ == '__main__':
    main()
