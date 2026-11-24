#!/usr/bin/env python3
"""Packages the Bouchra app without the Android SDK.

Writes the binary AndroidManifest.xml and resources.arsc by hand, draws the
pink heart icons, and zips them with classes.dex into an unsigned APK.

usage: build.py <classes.dex> <out-unsigned.apk>
"""
import io
import math
import struct
import sys
import zipfile

from PIL import Image, ImageDraw

PACKAGE = "com.bouchra.love"
VERSION_CODE = 1
VERSION_NAME = "1.0"
MIN_SDK = 21
TARGET_SDK = 28

# android.R.attr IDs (checked against android.jar)
ATTR = {
    "theme": 0x01010000,
    "label": 0x01010001,
    "icon": 0x01010002,
    "name": 0x01010003,
    "exported": 0x01010010,
    "minSdkVersion": 0x0101020C,
    "versionCode": 0x0101021B,
    "versionName": 0x0101021C,
    "targetSdkVersion": 0x01010270,
    "allowBackup": 0x01010280,
    "supportsRtl": 0x010103AF,
}
THEME_MATERIAL_LIGHT_NOACTIONBAR = 0x01030241
IC_LAUNCHER = 0x7F010000
IC_NOTIF = 0x7F010001
ANDROID_NS = "http://schemas.android.com/apk/res/android"

# Res_value types
T_REF, T_STRING, T_INT, T_BOOL = 0x01, 0x03, 0x10, 0x12


# ---------------------------------------------------------------- icons
def heart_points(cx, cy, scale, n=400):
    pts = []
    for i in range(n):
        t = 2 * math.pi * i / n
        x = 16 * math.sin(t) ** 3
        y = 13 * math.cos(t) - 5 * math.cos(2 * t) - 2 * math.cos(3 * t) - math.cos(4 * t)
        pts.append((cx + x * scale, cy - y * scale))
    return pts


def launcher_icon(size=192):
    S = size * 4
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    # vertical pink gradient inside a circle
    grad = Image.new("RGBA", (S, S))
    top, bottom = (255, 128, 171), (194, 24, 91)
    gd = ImageDraw.Draw(grad)
    for y in range(S):
        k = y / (S - 1)
        gd.line([(0, y), (S, y)], fill=tuple(int(top[i] + (bottom[i] - top[i]) * k) for i in range(3)) + (255,))
    mask = Image.new("L", (S, S), 0)
    ImageDraw.Draw(mask).ellipse([S * 0.02, S * 0.02, S * 0.98, S * 0.98], fill=255)
    img.paste(grad, (0, 0), mask)
    d = ImageDraw.Draw(img)
    # soft shadow + white heart + small sparkle hearts
    d.polygon(heart_points(S / 2, S * 0.53 + S * 0.015, S * 0.0185), fill=(140, 10, 60, 90))
    d.polygon(heart_points(S / 2, S * 0.53, S * 0.0185), fill=(255, 255, 255, 255))
    d.polygon(heart_points(S * 0.5, S * 0.505, S * 0.0075), fill=(255, 64, 129, 255))
    d.polygon(heart_points(S * 0.78, S * 0.24, S * 0.0045), fill=(255, 255, 255, 230))
    d.polygon(heart_points(S * 0.23, S * 0.30, S * 0.003), fill=(255, 255, 255, 200))
    return img.resize((size, size), Image.LANCZOS)


def notif_icon(size=96):
    S = size * 4
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    ImageDraw.Draw(img).polygon(heart_points(S / 2, S * 0.53, S * 0.028), fill=(255, 255, 255, 255))
    return img.resize((size, size), Image.LANCZOS)


def png_bytes(img):
    b = io.BytesIO()
    img.save(b, "PNG", optimize=True)
    return b.getvalue()


# ---------------------------------------------------------------- binary chunks
def string_pool(strings):
    """UTF-16 ResStringPool chunk."""
    offsets, data = [], b""
    for s in strings:
        offsets.append(len(data))
        u = s.encode("utf-16-le")
        n = len(u) // 2
        assert n < 0x8000
        data += struct.pack("<H", n) + u + b"\x00\x00"
    while len(data) % 4:
        data += b"\x00"
    header_size = 28
    strings_start = header_size + 4 * len(strings)
    size = strings_start + len(data)
    return (struct.pack("<HHIIIIII", 0x0001, header_size, size, len(strings), 0, 0, strings_start, 0)
            + b"".join(struct.pack("<I", o) for o in offsets) + data)


def res_value(dtype, data):
    return struct.pack("<HBBI", 8, 0, dtype, data & 0xFFFFFFFF)


# ---------------------------------------------------------------- manifest (AXML)
class Axml:
    def __init__(self):
        # attribute names that map to resource IDs must come first in the pool
        self.attr_names = list(ATTR.keys())
        self.strings = list(self.attr_names)
        self.body = b""
        self.line = 1

    def s(self, text):
        if text not in self.strings:
            self.strings.append(text)
        return self.strings.index(text)

    def start(self, tag, attrs):
        """attrs: list of (name, kind, value); kind in str/int/bool/ref; name w/o ns is plain."""
        ns = self.s(ANDROID_NS)
        enc = []
        for name, kind, value in attrs:
            has_ns = name in ATTR
            name_idx = self.s(name)
            raw = 0xFFFFFFFF
            if kind == "str":
                raw = self.s(value)
                rv = res_value(T_STRING, raw)
            elif kind == "int":
                rv = res_value(T_INT, value)
            elif kind == "bool":
                rv = res_value(T_BOOL, 0xFFFFFFFF if value else 0)
            elif kind == "ref":
                rv = res_value(T_REF, value)
            else:
                raise ValueError(kind)
            sort_key = ATTR.get(name, 0xFFFFFFFF)
            enc.append((sort_key, struct.pack("<III", ns if has_ns else 0xFFFFFFFF, name_idx, raw) + rv))
        enc.sort(key=lambda e: e[0])
        attr_bytes = b"".join(e[1] for e in enc)
        ext = struct.pack("<IIHHHHHH", 0xFFFFFFFF, self.s(tag), 20, 20, len(enc), 0, 0, 0)
        size = 16 + len(ext) + len(attr_bytes)
        self.body += struct.pack("<HHIII", 0x0102, 16, size, self.line, 0xFFFFFFFF) + ext + attr_bytes
        self.line += 1

    def end(self, tag):
        self.body += struct.pack("<HHIIIII", 0x0103, 16, 24, self.line, 0xFFFFFFFF, 0xFFFFFFFF, self.s(tag))
        self.line += 1

    def build(self):
        prefix, uri = self.s("android"), self.s(ANDROID_NS)
        ns_start = struct.pack("<HHIIIII", 0x0100, 16, 24, 1, 0xFFFFFFFF, prefix, uri)
        ns_end = struct.pack("<HHIIIII", 0x0101, 16, 24, self.line, 0xFFFFFFFF, prefix, uri)
        pool = string_pool(self.strings)
        resmap = struct.pack("<HHI", 0x0180, 8, 8 + 4 * len(self.attr_names)) + b"".join(
            struct.pack("<I", ATTR[n]) for n in self.attr_names)
        content = pool + resmap + ns_start + self.body + ns_end
        return struct.pack("<HHI", 0x0003, 8, 8 + len(content)) + content


def manifest():
    x = Axml()
    x.start("manifest", [("versionCode", "int", VERSION_CODE), ("versionName", "str", VERSION_NAME),
                         ("package", "str", PACKAGE)])
    x.start("uses-sdk", [("minSdkVersion", "int", MIN_SDK), ("targetSdkVersion", "int", TARGET_SDK)])
    x.end("uses-sdk")
    for perm in ["android.permission.RECEIVE_BOOT_COMPLETED", "android.permission.VIBRATE",
                 "android.permission.WAKE_LOCK", "android.permission.POST_NOTIFICATIONS"]:
        x.start("uses-permission", [("name", "str", perm)])
        x.end("uses-permission")
    x.start("application", [("theme", "ref", THEME_MATERIAL_LIGHT_NOACTIONBAR), ("label", "str", "Bouchra"),
                            ("icon", "ref", IC_LAUNCHER), ("allowBackup", "bool", True),
                            ("supportsRtl", "bool", True)])
    x.start("activity", [("name", "str", PACKAGE + ".MainActivity"), ("label", "str", "Bouchra"),
                         ("exported", "bool", True)])
    x.start("intent-filter", [])
    x.start("action", [("name", "str", "android.intent.action.MAIN")]); x.end("action")
    x.start("category", [("name", "str", "android.intent.category.LAUNCHER")]); x.end("category")
    x.end("intent-filter")
    x.end("activity")
    x.start("receiver", [("name", "str", PACKAGE + ".ReminderReceiver"), ("exported", "bool", True)])
    x.start("intent-filter", [])
    for a in ["android.intent.action.BOOT_COMPLETED", "android.intent.action.MY_PACKAGE_REPLACED",
              "android.intent.action.QUICKBOOT_POWERON"]:
        x.start("action", [("name", "str", a)]); x.end("action")
    x.end("intent-filter")
    x.end("receiver")
    x.end("application")
    x.end("manifest")
    return x.build()


# ---------------------------------------------------------------- resources.arsc
def resources(paths):
    """One 'drawable' type with entries ic_launcher, ic_notif, density xxxhdpi."""
    values = string_pool(paths)
    type_pool = string_pool(["drawable"])
    key_pool = string_pool(["ic_launcher", "ic_notif"])
    n = len(paths)

    spec = struct.pack("<HHIBBHI", 0x0202, 16, 16 + 4 * n, 1, 0, 0, n) + b"\x00\x00\x00\x00" * n

    config = bytearray(64)
    struct.pack_into("<I", config, 0, 64)        # size
    struct.pack_into("<H", config, 14, 640)      # density = xxxhdpi
    struct.pack_into("<H", config, 24, 4)        # sdkVersion = 4 (like aapt's -v4)
    header_size = 20 + 64
    entries, offsets = b"", []
    for i in range(n):
        offsets.append(len(entries))
        entries += struct.pack("<HHI", 8, 0, i) + res_value(T_STRING, i)
    entries_start = header_size + 4 * n
    type_chunk = (struct.pack("<HHIBBHII", 0x0201, header_size, entries_start + len(entries), 1, 0, 0, n,
                              entries_start) + bytes(config)
                  + b"".join(struct.pack("<I", o) for o in offsets) + entries)

    pkg_header = 288
    name = PACKAGE.encode("utf-16-le").ljust(256, b"\x00")
    type_off = pkg_header
    key_off = type_off + len(type_pool)
    body = type_pool + key_pool + spec + type_chunk
    pkg = struct.pack("<HHII", 0x0200, pkg_header, pkg_header + len(body), 0x7F) + name + struct.pack(
        "<IIIII", type_off, 1, key_off, 2, 0) + body
    content = values + pkg
    return struct.pack("<HHII", 0x0002, 12, 12 + len(content), 1) + content


def main():
    dex, out = sys.argv[1], sys.argv[2]
    launcher_path = "res/drawable-xxxhdpi-v4/ic_launcher.png"
    notif_path = "res/drawable-xxxhdpi-v4/ic_notif.png"
    launcher = launcher_icon()
    launcher.save(out.rsplit("/", 1)[0] + "/icon-preview.png")
    with zipfile.ZipFile(out, "w") as z:
        z.writestr(zipfile.ZipInfo("AndroidManifest.xml"), manifest(), zipfile.ZIP_DEFLATED)
        z.writestr("resources.arsc", resources([launcher_path, notif_path]), zipfile.ZIP_STORED)
        with open(dex, "rb") as f:
            z.writestr("classes.dex", f.read(), zipfile.ZIP_DEFLATED)
        z.writestr(launcher_path, png_bytes(launcher), zipfile.ZIP_STORED)
        z.writestr(notif_path, png_bytes(notif_icon()), zipfile.ZIP_STORED)
    print("wrote", out)


if __name__ == "__main__":
    main()
