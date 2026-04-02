from __future__ import annotations

import os
import subprocess


def _total_memory_bytes() -> int:
    try:
        with open("/proc/meminfo", "r", encoding="utf-8") as handle:
            for line in handle:
                if line.startswith("MemTotal:"):
                    return int(line.split()[1]) * 1024
    except FileNotFoundError:
        pass
    if os.name == "posix":
        try:
            return int(subprocess.check_output(["sysctl", "-n", "hw.memsize"], text=True).strip())
        except Exception:
            return 0
    return 0


def resolve(ctx) -> str:
    total = _total_memory_bytes()
    if total <= 0:
        return ""
    gib = max(1, int((total * 0.8) / (1024 ** 3)))
    return f"{gib}GB"
