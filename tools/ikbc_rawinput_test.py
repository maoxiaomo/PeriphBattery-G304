# -*- coding: utf-8 -*-
"""用 Windows Raw Input 归因按键来源 + 同步轮询 ikbc feature 0x06。
判定目标：用户在 W200 上按键时，是否真的走 3554:FC03 接收器；以及 0x06 是否随键盘连接状态变化。"""
import ctypes, time, threading, sys
from ctypes import wintypes
import hid

FEAT = b'\\\\?\\HID#VID_3554&PID_FC03&MI_01&Col06#8&3a9ffd85&0&0005#{4d1e55b2-f16f-11cf-88cb-001111000030}'
FF01 = b'\\\\?\\HID#VID_3554&PID_FC03&MI_01&Col02#8&3a9ffd85&0&0001#{4d1e55b2-f16f-11cf-88cb-001111000030}'

u32, k32 = ctypes.windll.user32, ctypes.windll.kernel32
T0 = time.time()
def ts(): return f"{time.time()-T0:6.1f}s"

WM_INPUT = 0x00FF
RIM_TYPEKEYBOARD = 1
RID_INPUT = 0x10000003
RIDI_DEVICENAME = 0x20000007
RIDEV_INPUTSINK = 0x00000100

class RAWINPUTDEVICE(ctypes.Structure):
    _fields_ = [("usUsagePage", wintypes.USHORT), ("usUsage", wintypes.USHORT),
                ("dwFlags", wintypes.DWORD), ("hwndTarget", wintypes.HWND)]
class RAWINPUTHEADER(ctypes.Structure):
    _fields_ = [("dwType", wintypes.DWORD), ("dwSize", wintypes.DWORD),
                ("hDevice", wintypes.HANDLE), ("wParam", wintypes.WPARAM)]
class MSG(ctypes.Structure):
    _fields_ = [("hwnd", wintypes.HWND), ("message", wintypes.UINT),
                ("wParam", wintypes.WPARAM), ("lParam", wintypes.LPARAM),
                ("time", wintypes.DWORD), ("pt", wintypes.POINT)]

WNDPROC = ctypes.WINFUNCTYPE(ctypes.c_long, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)
_devname_cache = {}
_counts = {"ikbc": 0, "other": 0}

def devname(h):
    if h in _devname_cache: return _devname_cache[h]
    n = wintypes.UINT(0)
    u32.GetRawInputDeviceInfoW(wintypes.HANDLE(h), RIDI_DEVICENAME, None, ctypes.byref(n))
    buf = ctypes.create_unicode_buffer(n.value + 1)
    u32.GetRawInputDeviceInfoW(wintypes.HANDLE(h), RIDI_DEVICENAME, buf, ctypes.byref(n))
    s = buf.value or ""
    _devname_cache[h] = s
    print(f"[{ts()}] 新输入设备句柄 -> {s}")
    return s

_events = []
def wndproc(hwnd, msg, wp, lp):
    if msg == WM_INPUT:
        size = wintypes.UINT(0)
        u32.GetRawInputData(wintypes.HANDLE(lp), RID_INPUT, None, ctypes.byref(size), ctypes.sizeof(RAWINPUTHEADER))
        buf = (ctypes.c_byte * size.value)()
        if u32.GetRawInputData(wintypes.HANDLE(lp), RID_INPUT, buf, ctypes.byref(size), ctypes.sizeof(RAWINPUTHEADER)) > 0:
            hdr = RAWINPUTHEADER.from_buffer(buf)
            if hdr.dwType == RIM_TYPEKEYBOARD:
                name = devname(hdr.hDevice)
                who = "ikbc" if "VID_3554" in name.upper() else "other"
                _counts[who] += 1
                _events.append((time.time() - T0, who))
        return 0
    return u32.DefWindowProcW(hwnd, msg, wp, lp)

_wp = WNDPROC(wndproc)

class WNDCLASSW(ctypes.Structure):
    _fields_ = [("style", wintypes.UINT), ("lpfnWndProc", WNDPROC), ("cbClsExtra", ctypes.c_int),
                ("cbWndExtra", ctypes.c_int), ("hInstance", wintypes.HINSTANCE), ("hIcon", wintypes.HANDLE),
                ("hCursor", wintypes.HANDLE), ("hbrBackground", wintypes.HANDLE),
                ("lpszMenuName", wintypes.LPCWSTR), ("lpszClassName", wintypes.LPCWSTR)]

hinst = k32.GetModuleHandleW(None)
wc = WNDCLASSW(0, _wp, 0, 0, hinst, None, None, None, None, "IkbcProbeWnd")
u32.RegisterClassW(ctypes.byref(wc))
hwnd = u32.CreateWindowExW(0, "IkbcProbeWnd", "probe", 0, 0, 0, 0, 0, wintypes.HWND(-3), None, hinst, None)  # HWND_MESSAGE
rid = RAWINPUTDEVICE(0x01, 0x06, RIDEV_INPUTSINK, hwnd)
ok = u32.RegisterRawInputDevices(ctypes.byref(rid), 1, ctypes.sizeof(rid))
print(f"[{ts()}] RegisterRawInputDevices -> {ok}")

stop = threading.Event()

def poll_feat():
    d = hid.device(); d.open_path(FEAT); d.set_nonblocking(0)
    last = None
    while not stop.is_set():
        try:
            r = bytes(d.get_feature_report(0x06, 8))
            if r != last:
                print(f"[{ts()}] FEAT 0x06 -> {r.hex()}"); last = r
        except Exception as e:
            if last != "ERR":
                print(f"[{ts()}] FEAT 0x06 读取失败: {e}"); last = "ERR"
        time.sleep(0.3)
    d.close()

def listen_ff01():
    try:
        d = hid.device(); d.open_path(FF01); d.set_nonblocking(1)
    except Exception as e:
        print(f"[{ts()}] ff01 open fail {e}"); return
    while not stop.is_set():
        try:
            r = d.read(64)
            if r: print(f"[{ts()}] ff01 RAW: {bytes(r).hex()}")
        except Exception:
            pass
        time.sleep(0.01)
    d.close()

threading.Thread(target=poll_feat, daemon=True).start()
threading.Thread(target=listen_ff01, daemon=True).start()

DURATION = int(sys.argv[1]) if len(sys.argv) > 1 else 70
print(f"[{ts()}] 监听 {DURATION}s —— 请在 W200 上打字 / 按其背面电源开关")
msg = MSG()
end = time.time() + DURATION
while time.time() < end:
    while u32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 1):
        u32.TranslateMessage(ctypes.byref(msg))
        u32.DispatchMessageW(ctypes.byref(msg))
    time.sleep(0.01)

stop.set()
print(f"[{ts()}] 结束。ikbc 键盘事件数={_counts['ikbc']}  其他键盘事件数={_counts['other']}")
ev = [e for e in _events if e[1] == "ikbc"]
if ev:
    print("ikbc 事件时间轴:", ", ".join(f"{t:.1f}s" for t, _ in ev[:30]))
