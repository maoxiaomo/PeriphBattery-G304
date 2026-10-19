import hid, time

P = {
 'short': b'\\\\?\\HID#VID_046D&PID_C53F&MI_02&Col01#7&1c74c730&0&0000#{4d1e55b2-f16f-11cf-88cb-001111000030}',
 'long' : b'\\\\?\\HID#VID_046D&PID_C53F&MI_02&Col02#7&1c74c730&0&0001#{4d1e55b2-f16f-11cf-88cb-001111000030}',
}

def op(p):
    d = hid.device(); d.open_path(p); d.set_nonblocking(1)
    return d

H = {'short': op(P['short']), 'long': op(P['long'])}
for d in H.values():
    while d.read(64): pass

def xfer(buf, is_short, tries=3, timeout=2.0):
    """write to matching handle, read replies from both"""
    for _ in range(tries):
        try:
            n = H['short' if is_short else 'long'].write(buf)
        except Exception as e:
            n = -1
        end = time.time() + timeout
        while time.time() < end:
            for name, d in H.items():
                r = d.read(64)
                if not r:
                    continue
                r = bytes(r)
                if len(r) > 2 and r[2] == 0x8F:      # error reply -> retry
                    continue
                if len(r) >= 2 and r[1] == buf[1]:
                    return r, n
            time.sleep(0.01)
    return None, n

def get_feature(idx, fid):
    r, n = xfer(bytes([0x10, idx, 0x00, 0x00, fid >> 8, fid & 0xFF, 0x00]), True)
    return (r[4] if r and len(r) > 4 else None), r

print("=== root / presence ===")
for idx in (0xFF, 0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06):
    r, n = xfer(bytes([0x10, idx, 0x00, 0x00, 0x00, 0x00, 0x00]), True)
    print(f" idx 0x{idx:02x} wr={n} resp={r.hex() if r else None}")

print("\n=== features ===")
res = {}
for idx in (0x01, 0x02, 0x03, 0xFF):
    for fid in (0x1000, 0x1001, 0x1004, 0x1814):
        fi, raw = get_feature(idx, fid)
        print(f" idx 0x{idx:02x} feat {fid:#06x} -> idx={fi} raw={raw.hex() if raw else None}")
        if fi: res[(idx, fid)] = fi

print("\n=== HID++1.0 register 0x07 (battery) ===")
for idx in (0x01, 0x02, 0xFF):
    r, n = xfer(bytes([0x10, idx, 0x81, 0x07, 0x00, 0x00, 0x00]), True)
    print(f" idx 0x{idx:02x} wr={n} resp={r.hex() if r else None}")

print("\n=== battery values ===")
for (idx, fid), fi in res.items():
    if fid == 0x1001:
        r, n = xfer(bytes([0x10, idx, fi, 0x00, 0, 0, 0]), True)
        print(f" BATTERY_VOLTAGE idx 0x{idx:02x}: {r.hex() if r else None}")
    if fid == 0x1000:
        r, n = xfer(bytes([0x10, idx, fi, 0x00, 0, 0, 0]), True)
        print(f" BATTERY_STATUS  idx 0x{idx:02x}: {r.hex() if r else None}")
    if fid == 0x1004:
        r, n = xfer(bytes([0x10, idx, fi, 0x10, 0, 0, 0]), True)
        print(f" UNIFIED_BATTERY idx 0x{idx:02x}: {r.hex() if r else None}")
