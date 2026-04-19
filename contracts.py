# contracts.py
from pydantic import BaseModel, Field
from typing import List, Dict, Optional, Any
from enum import Enum


# === Базовые контракты ===

class AgentRole(str, Enum):
    PLANNER = "planner"
    CODER = "coder"
    CRITIC = "critic"
    REFACTOR = "refactor"


class AgentMessage(BaseModel):
    """Сообщение между агентами"""
    role: AgentRole
    content: str
    metadata: Dict[str, Any] = Field(default_factory=dict)


class TaskContext(BaseModel):
    """Контекст задачи"""
    user_request: str
    variables: Dict[str, Any] = Field(default_factory=dict)
    constraints: List[str] = Field(default_factory=list)
    examples: List[Dict] = Field(default_factory=list)
    conversation_history: List[Dict] = Field(default_factory=list)  # история диалога


# === Контракт Планировщика ===

class PlannerInput(BaseModel):
    task: str
    context: Optional[TaskContext] = None


class PlannerOutput(BaseModel):
    task_type: str
    complexity: str
    steps: List[str] = Field(default_factory=list)
    required_variables: List[str] = Field(default_factory=list)
    input_variables: List[str] = Field(default_factory=list)
    init_variables: List[str] = Field(default_factory=list)
    questions: List[str] = Field(default_factory=list)
    plan: str


# === Контракт Кодировщика ===

class CoderInput(BaseModel):
    plan: PlannerOutput
    context: TaskContext


class CoderOutput(BaseModel):
    code: str
    explanation: str = ""
    assumptions: List[str] = Field(default_factory=list)


# === Контракт Критика ===

class CriticInput(BaseModel):
    task: str
    code: str
    context: TaskContext


class CriticOutput(BaseModel):
    is_valid: bool = False
    format_errors: List[str] = Field(default_factory=list)
    syntax_errors: List[str] = Field(default_factory=list)
    jsonpath_errors: List[str] = Field(default_factory=list)
    array_errors: List[str] = Field(default_factory=list)
    logic_errors: List[str] = Field(default_factory=list)
    suggestions: List[str] = Field(default_factory=list)
    score: float = 0.0
    questions: List[str] = Field(default_factory=list)  # вопросы от критика


# === Контракт Рефактора ===

class RefactorInput(BaseModel):
    original_code: str
    criticism: CriticOutput
    context: TaskContext


class RefactorOutput(BaseModel):
    improved_code: str
    changes_made: List[str] = Field(default_factory=list)
    new_score: float = 0.0


# === API Контракты (согласно openapi) ===

class GenerateRequest(BaseModel):
    prompt: str


class GenerateResponse(BaseModel):
    code: str