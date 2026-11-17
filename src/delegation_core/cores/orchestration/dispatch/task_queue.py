import uuid
import time
from typing import Dict, Any, List

class AgentTaskQueue:
    """Fila de tarefas e eventos para agentes locais (Multica + Fleetbase)"""
    def __init__(self):
        self.queue: List[Dict[str, Any]] = []
        self.completed: List[Dict[str, Any]] = []

    def enqueue(self, title: str, payload: Dict[str, Any], priority: int = 1) -> str:
        task_id = f"task_{str(uuid.uuid4())[:8]}"
        item = {
            "id": task_id,
            "title": title,
            "payload": payload,
            "priority": priority,
            "created_at": time.time(),
            "status": "QUEUED"
        }
        self.queue.append(item)
        self.queue.sort(key=lambda x: x["priority"], reverse=True)
        return task_id

    def claim_next(self) -> Dict[str, Any]:
        if not self.queue:
            return None
        task = self.queue.pop(0)
        task["status"] = "IN_PROGRESS"
        return task
