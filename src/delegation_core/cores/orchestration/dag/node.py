from typing import Callable, List, Any, Optional

class TaskNode:
    def __init__(self, name: str, action: Callable, dependencies: List[str] = None, max_retries: int = 1):
        self.name = name
        self.action = action
        self.dependencies = dependencies or []
        self.max_retries = max_retries
        self.status = "PENDING"
        self.result: Any = None
        self.duration_sec: float = 0.0
        self.error: Optional[str] = None
