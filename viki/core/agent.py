from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from enum import Enum
import uuid
from .._log import structlog

logger = structlog.get_logger()

class AgentStatus(Enum):
    IDLE = "idle"
    THINKING = "thinking"
    CODING = "coding"
    REVIEWING = "reviewing"
    TESTING = "testing"
    SECURITY_SCAN = "security_scan"
    ERROR = "error"
    DONE = "done"
    CANCELLED = "cancelled"

@dataclass
class AgentCheckpoint:
    timestamp: str
    state: Dict[str, Any]

@dataclass
class Agent:
    """Production-grade Agent with persistence"""
    role: str
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    status: AgentStatus = AgentStatus.IDLE
    current_action: str = ""
    output_buffer: str = ""
    assigned_files: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    checkpoints: List[AgentCheckpoint] = field(default_factory=list)
    error_count: int = 0
    max_retries: int = 3
    
    def transition_to(self, new_status: AgentStatus, action: str = ""):
        logger.debug(f"Agent {self.id} transition: {self.status.value} -> {new_status.value}")
        self.status = new_status
        if action:
            self.current_action = action
    
    def checkpoint(self):
        from datetime import datetime
        self.checkpoints.append(AgentCheckpoint(
            timestamp=datetime.now().isoformat(),
            state={
                "status": self.status.value,
                "action": self.current_action,
                "output_len": len(self.output_buffer)
            }
        ))
        # Keep only last 5 checkpoints
        self.checkpoints = self.checkpoints[-5:]
    
    def record_error(self, error: str):
        self.error_count += 1
        logger.error(f"Agent {self.id} error #{self.error_count}: {error}")
        if self.error_count >= self.max_retries:
            self.transition_to(AgentStatus.ERROR, f"Max retries exceeded: {error}")
            return False
        return True
    
    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "role": self.role,
            "status": self.status.value,
            "current_action": self.current_action,
            "error_count": self.error_count,
            "has_output": len(self.output_buffer) > 0
        }
