import os
import shutil
import socket
from typing import Dict, Any

class HardwareSupervisor:
    """Fusao de gs-server (Corsair Btrfs / IaC Telemetry) + Grafana (Metrics)"""
    def __init__(self):
        self.host = socket.gethostname()

    def get_server_metrics(self) -> Dict[str, Any]:
        disk_home = shutil.disk_usage("/home")
        load = os.getloadavg() if hasattr(os, "getloadavg") else (0.0, 0.0, 0.0)
        
        return {
            "host": self.host,
            "nvme_corsair_mp600": {
                "subvolume": "@home (Btrfs)",
                "free_gb": round(disk_home.free / (1024**3), 2),
                "total_gb": round(disk_home.total / (1024**3), 2),
                "used_pct": round((disk_home.used / disk_home.total) * 100, 1)
            },
            "system_load": {
                "load_1m": load[0],
                "load_5m": load[1]
            },
            "status": "HEALTHY"
        }
