import ctypes, hid

class _HIDP_CAPS(ctypes.Structure):
    _fields_ = [("Usage", ctypes.c_ushort), ("UsagePage", ctypes.c_ushort),
                ("InputReportByteLength", ctypes.c_ushort),
                ("OutputReportByteLength", ctypes.c_ushort),
                ("FeatureReportByteLength", ctypes.c_ushort),
                ("Reserved", ctypes.c_ushort * 17)] + [
                (n, ctypes.c_ushort) for n in (
                    "NumberLinkCollectionNodes", "NumberInputButtonCaps", "NumberInputValueCaps",
                    "NumberInputDataIndices", "NumberOutputButtonCaps", "NumberOutputValueCaps",
                    "NumberOutputDataIndices", "NumberFeatureButtonCaps", "NumberFeatureValueCaps",
                    "NumberFeatureDataIndices")]

def caps(path):
    p = path.decode("utf-8", "ignore") if isinstance(path, (bytes, bytearray)) else str(path)
    k32, hidd = ctypes.windll.kernel32, ctypes.windll.hid
    k32.CreateFileW.restype = ctypes.c_void_p
    h = k32.CreateFileW(p, 0, 3, None, 3, 0, None)
    if h in (None, ctypes.c_void_p(-1).value):
        return None
    try:
        pp = ctypes.c_void_p()
        if not hidd.HidD_GetPreparsedData(ctypes.c_void_p(h), ctypes.byref(pp)):
            return None
        try:
            c = _HIDP_CAPS()
            if hidd.HidP_GetCaps(pp, ctypes.byref(c)) != 0x00110000:
                return None
            return (c.UsagePage, c.Usage, c.InputReportByteLength, c.OutputReportByteLength,
                    c.FeatureReportByteLength)
        finally:
            hidd.HidD_FreePreparsedData(pp)
    finally:
        k32.CloseHandle(ctypes.c_void_p(h))

for d in hid.enumerate(0, 0):
    if (d['vendor_id'], d['product_id']) not in ((0x046d, 0xc53f), (0x3554, 0xfc03)):
        continue
    c = caps(d['path'])
    tag = f"{d['vendor_id']:04x}:{d['product_id']:04x} if={d['interface_number']}"
    if c:
        print(f"{tag}  up=0x{c[0]:04x} u=0x{c[1]:04x}  in={c[2]:3d} out={c[3]:3d} feat={c[4]:3d}  {d['product_string']}")
    else:
        print(f"{tag}  caps unavailable")
