from pydantic import BaseModel, Field
from typing import List, Optional

class LogEvent(BaseModel):
    ts: Optional[str] = ""
    cmd: str
    exit: int = 0
    cwd: Optional[str] = ""
    out: Optional[str] = ""

class Suggestion(BaseModel):
    cmd: str
    reason: str = ""
    safety: str = Field(pattern="^(read-only|intrusive|exploit)$")
    noise: str = Field(pattern="^(low|med|high)$")

class Plan(BaseModel):
    next_actions: List[Suggestion] = []
    notes: List[str] = []
    escalation_paths: List[str] = []
