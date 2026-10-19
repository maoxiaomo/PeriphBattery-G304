# PeriphBattery-G304

在 Windows 托盘显示 Logitech G304（LIGHTSPEED 2.4G 接收器）的电池电量。**无需安装 G HUB**，程序直接通过 HID++ 2.0 协议与接收器通信。

![License](https://img.shields.io/badge/license-MIT-green)

## 功能

- **托盘图标实时显示电量**：圆环弧长表示百分比，悬停 tooltip 显示精确值
- **三色提醒机制**：
  - 🟢 绿色 — 电量充足（≥ 60%）
  - 🟡 黄色 — 电量偏低（20%–59%），跨档时弹 Windows 通知一次
  - 🔴 红色 — 电量危险（< 20%），跨档时弹 Windows 通知一次
  - 🔵 青色 — 充电中（G304 用干电池，此状态不会出现，为兼容充电型 Logitech 设备保留）
- **睡眠感知**：鼠标休眠时不应答 HID++ 查询，程序保留上次读数 30 分钟并置灰显示；尚未取得读数时每 12 秒快速重试，鼠标一动即恢复
- **单实例**：重复启动自动退出
- **开机自启**：右键菜单勾选，写入 `HKCU\...\Run`
- **右键菜单**：电量显示 / 立即刷新 / 开机自启 / 退出

## 关于电量粒度（重要）

G304 的电量**不是按 1% 或 10% 平滑变化，而是固件粗档位跳变**。依据（三方交叉验证）：

1. Logitech HID++ 2.0 `0x1000 batteryStatus` 线格式（[OpenLogi 文档](https://openlogi.org/hidpp/features/x1000-battery-status)）：
   - `byte0 discharge_level`：百分比，*"Firmware reports it in coarse steps, not as a continuous value"*
   - `byte1 next_level`：*"The next lower discharge step the firmware will report"*（固件粒度提示）
2. [Solaar 源码](https://github.com/pwr-Solaar/Solaar/blob/master/lib/logitech_receiver/hidpp20.py) 的 `parse_battery_status` 字段定义一致
3. 本机实测原始字节：`5a 32 00` → 当前档 **90%**、下一档 **50%**、放电中

即已知档位阶梯为 `90 → 50 → …`。更低的档位序列会在长期使用中由日志自动记录（每次读取都记录原始字节，见 `%LOCALAPPDATA%\PeriphBattery\log.txt`）。

## 使用

**直接运行（推荐）**：下载/自行构建 `PeriphBattery.exe`，双击即可，托盘出现圆环图标。

**从源码运行**：

```bash
pip install -r requirements.txt
pythonw periph_battery.py          # 托盘常驻
python periph_battery.py --probe   # 一次性打印读数（调试用）
```

## 构建 exe

```bash
pip install pyinstaller
python -m PyInstaller --noconfirm --clean --onefile --windowed --name PeriphBattery --icon periph.ico periph_battery.py
# 产物在 dist/PeriphBattery.exe（单文件，约 15 MB，不依赖 Python 环境）
```

## 原理

```
G304 ←2.4G→ 接收器(VID 046D:PID C53F) ←HID++ 2.0→ 本程序
```

- 接收器的 vendor interface（usage page `0xFF00`）提供短报告（7 字节，report `0x10`）和长报告（20 字节，report `0x11`）两个通道
- 通过 feature discovery 找到 `0x1000 BATTERY_STATUS`，调用 fn 0 `getBatteryLevelStatus` 读取
- 设备名通过 feature `0x0005` 读取（用于确认配对设备身份）
- 详细探测脚本见 `tools/`

## 已验证环境

- Windows 10 21H2 (19044)，Logitech G304 + C53F 接收器
- 数据交叉验证：本程序读取结果与 [HaloBattery](https://github.com/HeyOkay/HaloBattery) 独立实现一致（同为 90%）

## 已知限制

- 鼠标休眠（约数分钟无操作）时不应答 HID++ 查询 —— 这是硬件省电行为，程序会显示上次的读数
- 16px 托盘图标内的数字受物理尺寸限制不清晰，精确值请看悬停 tooltip
- 仅支持通过 HID++ 2.0 上报电量的 Logitech 设备（实测 G304；同协议的其他 Logitech 鼠标理论上兼容）

## 致谢

协议资料参考：[Solaar](https://github.com/pwr-Solaar/Solaar)、[OpenLogi](https://openlogi.org/)、[HaloBattery](https://github.com/HeyOkay/HaloBattery)。

## License

[MIT](LICENSE)
