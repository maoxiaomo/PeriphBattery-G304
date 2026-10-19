"""PeriphBattery - 在 Windows 托盘显示无线鼠标的电池电量。

鼠标 Logitech G304（接收器 046D:C53F，HID++ 2.0）
    feature 0x1000 BATTERY_STATUS -> 百分比 / 充电状态

（键盘 ikbc W200 的 3554:FC03 接收器经实测不提供电量，已移除相关代码。）

用法：
    pythonw periph_battery.py          托盘常驻
    python  periph_battery.py --probe  一次性打印读数，便于排查
"""
from __future__ import annotations

import ctypes
import json
import logging
import os
import sys
import threading
import time

import hid
from PIL import Image, ImageDraw, ImageFont

APP = "PeriphBattery"
LOGITECH_VID, LOGITECH_PID = 0x046D, 0xC53F
POLL_S = 120                      # 轮询周期
POLL_FAST_S = 12                  # 尚无有效读数时的快速重试周期
STALE_AFTER_S = 30 * 60           # 超过这么久没读到，丢弃旧读数
CONFIG = os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), APP, "config.json")
LOGPATH = os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), APP, "log.txt")

log = logging.getLogger(APP)


def setup_log():
    os.makedirs(os.path.dirname(LOGPATH), exist_ok=True)
    h = logging.FileHandler(LOGPATH, encoding="utf-8")
    h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    log.addHandler(h)
    log.setLevel(logging.INFO)


# ----------------------------------------------------------------------------- HID++
class HIDPP:
    """Logitech HID++ 2.0 最小客户端：短报告 7B / 长报告 20B。"""

    def __init__(self, short_path: bytes, long_path: bytes):
        self.short = hid.device()
        self.short.open_path(short_path)
        self.short.set_nonblocking(1)
        self.long = hid.device()
        self.long.open_path(long_path)
        self.long.set_nonblocking(1)

    def close(self):
        for d in (self.short, self.long):
            try:
                d.close()
            except Exception:
                pass

    def _drain(self):
        for d in (self.short, self.long):
            try:
                while d.read(64):
                    pass
            except Exception:
                pass

    def request(self, idx: int, feat_idx: int, func_sw: int, params=(), timeout=1.2, tries=2):
        body = bytes([idx, feat_idx, func_sw]) + bytes(params)
        short = len(body) + 1 <= 7
        buf = (b"\x10" if short else b"\x11") + body + bytes((6 if short else 19) - len(body))
        handle = self.short if short else self.long
        for _ in range(tries):
            try:
                handle.write(buf)
            except Exception:
                return None
            end = time.time() + timeout
            while time.time() < end:
                for d in (self.long, self.short):
                    try:
                        r = d.read(64)
                    except Exception:
                        r = None
                    if not r:
                        continue
                    r = bytes(r)
                    if len(r) > 2 and r[2] == 0x8F:      # 错误回包，忽略
                        continue
                    if len(r) >= 2 and r[1] == idx:
                        return r
                time.sleep(0.01)
        return None

    def feature(self, idx: int, fid: int):
        r = self.request(idx, 0x00, 0x00, [fid >> 8, fid & 0xFF])
        return r[4] if r and len(r) > 4 and r[4] else None

    def battery(self, idx: int):
        """(百分比, 是否充电, 下一档位, 原始hex) 或 (None, False, None, None)。
        HID++ 2.0 x1000: byte0=discharge_level(粗档位百分比), byte1=next_level
        (固件下次会报的档位，粒度提示), byte2=status(1-4=充电中)"""
        fi = self.feature(idx, 0x1000)
        if fi:
            r = self.request(idx, fi, 0x00)
            if r and len(r) > 6:
                p = r[4:]
                if 0 < p[0] <= 100:
                    return p[0], p[2] in (1, 2, 3, 4), p[1], r.hex()
        fi = self.feature(idx, 0x1004)               # 部分新设备用 UNIFIED_BATTERY
        if fi:
            r = self.request(idx, fi, 0x10)
            if r and len(r) > 6:
                p = r[4:]
                if 0 < p[0] <= 100:
                    return p[0], p[2] in (1, 2, 3, 4), None, r.hex()
        return None, False, None, None


def find_logitech_paths():
    short = long_ = None
    for d in hid.enumerate(LOGITECH_VID, LOGITECH_PID):
        if d["usage_page"] != 0xFF00:
            continue
        if d["usage"] == 0x0001:
            short = d["path"]
        elif d["usage"] == 0x0002:
            long_ = d["path"]
    return (short, long_) if short and long_ else (None, None)


def read_mouse():
    """-> dict(level, charging, name) 或 None"""
    sp, lp = find_logitech_paths()
    if not sp:
        return None
    pp = HIDPP(sp, lp)
    try:
        pp._drain()
        for idx in (1, 2, 3, 4, 5, 6):
            if pp.request(idx, 0x00, 0x00, [0x00, 0x00], timeout=0.8, tries=1) is None:
                continue
            level, charging, next_level, raw = pp.battery(idx)
            if level is None:
                continue
            name = f"Logitech 设备 {idx}"
            fi = pp.feature(idx, 0x0005)
            if fi:
                r = pp.request(idx, fi, 0x00)
                if r:
                    cnt, buf = r[4], b""
                    for c in range(0, min(cnt, 48), 16):
                        rr = pp.request(idx, fi, 0x10, [c])
                        if rr:
                            buf += bytes(rr[4:4 + min(16, cnt - c)])
                    if buf:
                        name = buf.decode("utf-8", "replace").strip("\x00 ")
            return {"level": level, "charging": charging, "name": name,
                    "next": next_level, "raw": raw}
        return None
    finally:
        pp.close()


# ----------------------------------------------------------------------------- 图标
def make_icon(level, charging, stale=False, kind="mouse", size=64):
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    pad, w = 4, 6
    box = (pad, pad, size - pad, size - pad)

    if level is None:
        color = (160, 160, 160, 235)          # 灰：无数据
    elif charging:
        color = (0, 190, 230, 255)            # 青：充电中
    elif level >= 60:
        color = (70, 200, 100, 255)           # 绿：充足
    elif level >= 20:
        color = (240, 180, 50, 255)           # 黄：偏低
    else:
        color = (230, 70, 70, 255)            # 红：危险
    if stale:
        color = (color[0] // 2 + 60, color[1] // 2 + 60, color[2] // 2 + 60, 170)

    d.arc(box, 0, 360, fill=(255, 255, 255, 55), width=w)     # 浅色轨道，深浅任务栏都可见
    if level is not None:
        sweep = max(3.6 * max(0, min(100, level)), 12)         # 最小弧长，个位数也看得见
        d.arc(box, -90, -90 + sweep, fill=color, width=w)
    else:
        d.arc(box, -90, -90 + 360, fill=(255, 255, 255, 25), width=w)

    txt = "?" if level is None else str(level)
    fsize = 34 if len(txt) == 1 else (27 if len(txt) == 2 else 20)
    try:
        font = ImageFont.truetype("arialbd.ttf", fsize)
    except Exception:
        font = ImageFont.load_default()
    bb = d.textbbox((0, 0), txt, font=font)
    tx = (size - (bb[2] - bb[0])) / 2 - bb[0]
    ty = (size - (bb[3] - bb[1])) / 2 - bb[1]
    d.text((tx, ty), txt, font=font,
           fill=(255, 255, 255, 255) if not stale else (205, 205, 205, 225))
    return img


# ----------------------------------------------------------------------------- 状态
class State:
    def __init__(self):
        self.mouse = None          # dict
        self.mouse_at = 0.0
        self.tier = 0              # 0 充足 1 偏低 2 危险（用于跨档提醒）

    def refresh(self):
        try:
            m = read_mouse()
            if m:
                self.mouse, self.mouse_at = m, time.time()
                log.info("mouse %s %s%% next=%s%% charging=%s raw=%s",
                         m["name"], m["level"], m.get("next"), m["charging"], m.get("raw"))
            else:
                log.info("mouse: 无应答（睡眠或未连接）")
        except Exception as e:
            log.warning("mouse read failed: %s", e)

    def mouse_level(self):
        if self.mouse and time.time() - self.mouse_at < STALE_AFTER_S:
            return self.mouse["level"], self.mouse["charging"], time.time() - self.mouse_at > POLL_S * 2
        return None, False, False


# ----------------------------------------------------------------------------- 托盘
def load_cfg():
    try:
        with open(CONFIG, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_cfg(cfg):
    os.makedirs(os.path.dirname(CONFIG), exist_ok=True)
    with open(CONFIG, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


def probe():
    st = State()
    st.refresh()
    m = st.mouse
    print(f"鼠标: {m['name']}  电量 {m['level']}%  {'充电中' if m['charging'] else ''}" if m
          else "鼠标: 未读到（睡眠或未连接）")


def main():
    setup_log()
    # 单实例：已运行则直接退出，避免双击重复启动
    mutex = ctypes.windll.kernel32.CreateMutexW(None, False, "PeriphBattery_SingleInstance")
    if ctypes.windll.kernel32.GetLastError() == 183:   # ERROR_ALREADY_EXISTS
        log.info("已在运行，退出重复实例")
        return
    import pystray
    from pystray import Menu, MenuItem

    st = State()
    cfg = load_cfg()
    icon = pystray.Icon(APP, make_icon(None, False), APP)

    def run_path():
        if getattr(sys, "frozen", False):
            return f'"{sys.executable}"'
        pyw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
        return f'"{pyw if os.path.exists(pyw) else sys.executable}" "{os.path.abspath(__file__)}"'

    def autostart_on():
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            r"Software\Microsoft\Windows\CurrentVersion\Run", 0,
                            winreg.KEY_READ) as k:
            try:
                winreg.QueryValueEx(k, APP)
                return True
            except FileNotFoundError:
                return False

    def set_autostart(on):
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            r"Software\Microsoft\Windows\CurrentVersion\Run", 0,
                            winreg.KEY_SET_VALUE) as k:
            if on:
                winreg.SetValueEx(k, APP, 0, winreg.REG_SZ, run_path())
            else:
                try:
                    winreg.DeleteValue(k, APP)
                except FileNotFoundError:
                    pass

    def apply():
        level, charging, stale = st.mouse_level()
        icon.icon = make_icon(level, charging, stale)
        if level is not None:
            icon.title = f"鼠标 {level}%{'（充电中）' if charging else ''}"
        else:
            icon.title = "鼠标电量读取中…（鼠标休眠时无应答，移动鼠标后自动恢复）"
        try:
            icon.update_menu()
        except Exception:
            pass

    def check_alert():
        """跨档下降时弹一次 Windows 通知；回升（换电池）自动重置"""
        level = st.mouse_level()[0]
        if level is None or (st.mouse and st.mouse["charging"]):
            return
        tier = 2 if level < 20 else (1 if level < 60 else 0)
        if tier > st.tier:
            msg = ("鼠标电量不足（%d%%），请准备更换电池" if tier == 2 else "鼠标电量偏低（%d%%）") % level
            try:
                icon.notify(msg, APP)
            except Exception as e:
                log.warning("notify failed: %s", e)
            log.info("alert tier -> %d (%d%%)", tier, level)
        st.tier = tier

    def poll_loop():
        while True:
            st.refresh()
            apply()
            check_alert()
            time.sleep(POLL_S if st.mouse else POLL_FAST_S)

    def do_refresh(_=None):
        threading.Thread(target=lambda: (st.refresh(), apply(), check_alert()), daemon=True).start()

    def toggle_autostart(_=None):
        set_autostart(not autostart_on())

    icon.menu = Menu(
        MenuItem(lambda _: (f"鼠标：{st.mouse['level']}%" + (" 充电中" if st.mouse["charging"] else ""))
                 if st.mouse_level()[0] is not None else "鼠标：读取中…（休眠时移动鼠标唤醒）", None, enabled=False),
        Menu.SEPARATOR,
        MenuItem("立即刷新", do_refresh),
        MenuItem("开机自启", toggle_autostart, checked=lambda _: autostart_on()),
        Menu.SEPARATOR,
        MenuItem("退出", lambda _: icon.stop()),
    )

    st.refresh()
    apply()
    threading.Thread(target=poll_loop, daemon=True).start()
    icon.run()


if __name__ == "__main__":
    if "--probe" in sys.argv:
        setup_log()
        probe()
    else:
        main()
