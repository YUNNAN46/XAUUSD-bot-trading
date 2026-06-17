#!/usr/bin/env python3
"""Patch MT5 common.ini to enable AlgoTrading before each launch."""
import os

path = "/config/.wine/drive_c/Program Files/MetaTrader 5/Config/common.ini"
if not os.path.exists(path):
    exit(0)

with open(path, "rb") as f:
    raw = f.read()

bom = b"\xff\xfe" if raw[:2] == b"\xff\xfe" else b""
text = raw[2:].decode("utf-16-le") if bom else raw.decode("utf-16-le", errors="replace")

in_experts = False
lines = []
for line in text.splitlines():
    stripped = line.strip()
    if stripped == "[Experts]":
        in_experts = True
    elif stripped.startswith("[") and stripped.endswith("]"):
        in_experts = False
    if in_experts and stripped == "Enabled=0":
        line = line.replace("Enabled=0", "Enabled=1")
    lines.append(line)

with open(path, "wb") as f:
    f.write(bom + "\r\n".join(lines).encode("utf-16-le"))

print("AlgoTrading enabled in MT5 common.ini")
