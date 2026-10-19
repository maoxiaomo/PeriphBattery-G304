"""交叉验证脚本：同一电量，三条独立路径。"""
import hid, time, datetime

SP = b'\\\\?\\HID#VID_046D&PID_C53F&MI_02&Col01#7&1c74c730&0&0000#{4d1e55b2-f16f-11cf-88cb-001111000030}'
LP = b'\\\\?\\HID#VID_046D&PID_C53F&MI_02&Col02#7&1c74c730&0&0001#{4d1e55b2-f16f-11cf-88cb-001111000030}'
IKBC = b'\\\\?\\HID#VID_3554&PID_FC03&MI_01&Col06#8&3a9ffd85&0&0005#{4d1e55b2-f16f-11cf-88cb-001111000030}'

print("time:", datetime.datetime.now().isoformat(timespec='seconds'))

def op(p):
    d = hid.device(); d.open_path(p); d.set_nonblocking(1); return d

sh, lg = op(SP), op(LP)
for d in (sh, lg):
    while d.read(64): pass

def xfer(buf, via, timeout=1.5, tries=3):
    """via: 'short'|'long' 写入句柄；两个句柄都监听回包"""
    for _ in range(tries):
        (sh if via == 'short' else lg).write(buf)
        end = time.time() + timeout
        while time.time() < end:
            for name, d in (('short', sh), ('long', lg)):
                r = d.read(64)
                if not r: continue
                r = bytes(r)
                if len(r) > 2 and r[2] == 0x8F: continue
                if len(r) >= 2 and r[1] == buf[1]: return r
            time.sleep(0.01)
    return None

IDX = 0x01
print("\n== A. 短报告通道 (0x10, 写 short) ==")
for i in range(3):
    r = xfer(bytes([0x10, IDX, 0x00, 0x00, 0x10, 0x00, 0x00]), 'short')  # getFeature(0x1000)
    fi = r[4] if r else None
    if fi:
        b = xfer(bytes([0x10, IDX, fi, 0x00, 0, 0, 0]), 'short')
        print(f"  #{i+1} feat_idx={fi} raw={b.hex() if b else None}  level={b[4] if b else '?'}% status={b[6] if b else '?'}")
    else:
        print(f"  #{i+1} getFeature failed")
    time.sleep(0.5)

print("\n== B. 长报告通道 (0x11, 写 long) ==")
for i in range(3):
    r = xfer(bytes([0x11, IDX, 0x00, 0x00, 0x10, 0x00] + [0]*14), 'long')
    fi = r[4] if r else None
    if fi:
        b = xfer(bytes([0x11, IDX, fi, 0x00, 0, 0] + [0]*13), 'long')
        print(f"  #{i+1} feat_idx={fi} raw={b.hex() if b else None}  level={b[4] if b else '?'}% status={b[6] if b else '?'}")
    else:
        print(f"  #{i+1} getFeature failed")
    time.sleep(0.5)

print("\n== C. ikbc feature 0x06 (隔几十分钟再读) ==")
d = op(IKBC); d.set_nonblocking(0)
for i in range(3):
    r = bytes(d.get_feature_report(0x06, 8))
    print(f"  #{i+1} {r.hex()}")
    time.sleep(0.5)
d.close()

print("\n== D. 重复读同一值时的序列号字段检查 (status byte 含义) ==")
# p[1]=0x32 在 HaloBattery 注释里是 "next level"（下一告警档位阈值），不是状态。
r = xfer(bytes([0x10, IDX, 0x00, 0x00, 0x10, 0x00, 0x00]), 'short')
if r:
    fi = r[4]
    b = xfer(bytes([0x10, IDX, fi, 0x00, 0, 0, 0]), 'short')
    if b:
        print(f"  raw={b.hex()}")
        print(f"  p[0]={b[4]}(level) p[1]={b[5]}(nextLevel阈值) p[2]={b[6]}(charging状态)")
sh.close(); lg.close()
