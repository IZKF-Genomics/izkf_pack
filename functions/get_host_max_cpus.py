from __future__ import annotations

import os


def resolve(ctx) -> int:
    total_cpus = os.cpu_count() or 1
    return max(1, int(total_cpus * 0.8))
