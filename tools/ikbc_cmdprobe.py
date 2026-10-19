import hid, time

P = b'\\\\?\\HID#VID_3554&PID_FC03&MI_01&Col06#8&3a9ffd85&0&0005#{4d1e55b2-f16f-11cf-88cb-001111000030}'
d = hid.device(); d.open_path(P); d.set_nonblocking(0)

BASE = bytes(d.get_feature_report(0x06, 8))
print('基线:', BASE.hex())

# 只用 Compx 协议里的只读查询命令，绝不碰 0x05/0x07/0x13（配对/EEPROM 写）
OPS = {0x03:'GetOnline', 0x04:'GetBatteryLevel', 0x08:'GetEEPROM', 0x10:'GetCIDMID', 0x12:'GetMouseVersion', 0x1D:'GetDongleVersion'}

for op, name in OPS.items():
    frame = bytes([0x06, op, 0, 0, 0, 0, 0, 0])
    try:
        n = d.send_feature_report(frame)
    except Exception as e:
        print(f'op 0x{op:02x} {name}: SET 被拒 {e}')
        continue
    time.sleep(0.15)
    vals = []
    for _ in range(3):
        try:
            vals.append(bytes(d.get_feature_report(0x06, 8)).hex())
        except Exception as e:
            vals.append(f'ERR {e}')
        time.sleep(0.15)
    changed = [v for v in vals if v != BASE.hex()]
    print(f'op 0x{op:02x} {name:16s} SET 写入 {n}B -> GET: {vals[0]}', '<== 有变化!' if changed else '')

final = bytes(d.get_feature_report(0x06, 8))
print('最终值:', final.hex(), '| 与基线一致:', final == BASE)
d.close()
