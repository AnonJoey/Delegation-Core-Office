"""Host metrics for the dashboard and cores_unified_status: disk use of the home folder and load.

Until 17/11/2026 it labelled any machine's disk as a "Corsair MP600 NVMe, @home (Btrfs)" and
reported a fixed "HEALTHY", and it measured "/home" (missing on Windows, size 0 on macOS).
"""

import os
import shutil
import socket
from pathlib import Path
from typing import Any, Dict


class HardwareSupervisor:
    def __init__(self):
        self.host = socket.gethostname()

    def get_server_metrics(self) -> Dict[str, Any]:
        casa = Path.home()
        disco = shutil.disk_usage(casa)
        carga = os.getloadavg() if hasattr(os, "getloadavg") else None
        return {
            "host": self.host,
            "disk_home": {
                "path": str(casa),
                "free_gb": round(disco.free / (1024 ** 3), 2),
                "total_gb": round(disco.total / (1024 ** 3), 2),
                "used_pct": round((disco.used / disco.total) * 100, 1) if disco.total else 0.0,
            },
            # Windows has no load average: null there, not a made-up zero.
            "system_load": {"load_1m": carga[0], "load_5m": carga[1]} if carga else None,
        }
