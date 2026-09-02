import socket, os, hashlib, threading, sys, time

CAN_ISOTP = 6
EFF = 0x80000000
IFACE = "vcan0"
TX_ID = 0x18DA0102 | EFF      # 29-bit extended, canon-style
RX_ID = 0x18DA0201 | EFF

def transfer(nbytes, timeout=25.0):
    """Send nbytes over ISO-TP on vcan0 loopback; return (ok, received_len, err)."""
    payload = bytes((i * 7 + 13) & 0xFF for i in range(nbytes))
    want = hashlib.sha256(payload).hexdigest()
    result = {}

    rx = socket.socket(socket.PF_CAN, socket.SOCK_DGRAM, CAN_ISOTP)
    rx.bind((IFACE, TX_ID, RX_ID))          # (iface, rx_addr, tx_addr)
    rx.settimeout(timeout)

    def reader():
        try:
            data = rx.recv(nbytes + 4096)
            result["len"] = len(data)
            result["sha"] = hashlib.sha256(data).hexdigest()
        except Exception as e:
            result["err"] = "%s: %s" % (type(e).__name__, e)

    t = threading.Thread(target=reader, daemon=True)
    t.start()
    time.sleep(0.3)

    tx = socket.socket(socket.PF_CAN, socket.SOCK_DGRAM, CAN_ISOTP)
    tx.bind((IFACE, RX_ID, TX_ID))
    tx.settimeout(timeout)
    t0 = time.time()
    try:
        tx.send(payload)
    except Exception as e:
        rx.close(); tx.close()
        return (False, 0, "send failed: %s: %s" % (type(e).__name__, e), 0.0)
    t.join(timeout)
    dt = time.time() - t0
    rx.close(); tx.close()

    if "err" in result:
        return (False, 0, result["err"], dt)
    ok = result.get("len") == nbytes and result.get("sha") == want
    return (ok, result.get("len", 0), None if ok else "content/length mismatch", dt)

print("iface      :", IFACE)
print("tx id      : 0x%08X (extended)" % (TX_ID & ~EFF))
print("rx id      : 0x%08X (extended)" % (RX_ID & ~EFF))
print()
for n in (64, 4096, 8200, 8201):
    ok, got, err, dt = transfer(n)
    verdict = "PASS" if ok else "FAIL"
    print("%-6d bytes -> %-4s received=%-6d %.2fs %s" % (n, verdict, got, dt, err or ""))
