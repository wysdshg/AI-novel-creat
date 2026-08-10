"""模型配置（需求 7）。"""
from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, Literal


VENDORS = Literal[
    "deepseek", "qwen", "ernie", "spark", "kimi",
    "openai", "claude", "ollama", "custom", "placeholder",
    "siliconflow", "nvidia", "zhipu",
]
ROLES = Literal["primary", "memory", "parse", "foreshadow"]


class ModelConfigBase(BaseModel):
    model_config = ConfigDict(protected_namespaces=())
    name: str
    vendor: VENDORS
    api_base: str
    api_key: str = Field("", description="加密存储")
    model_name: str
    context_window: int = 32768
    temperature: float = 0.4
    top_p: float = 0.9
    max_tokens: int = 6000
    role: ROLES = "primary"
    is_backup: bool = False
    status: str = Field("active", description="active|disabled")
    is_default: bool = False
    enable_thinking: bool = True


class ModelConfigCreate(ModelConfigBase):
    pass


class ModelConfigUpdate(BaseModel):
    model_config = ConfigDict(protected_namespaces=())
    name: Optional[str] = None
    vendor: Optional[VENDORS] = None
    api_base: Optional[str] = None
    api_key: Optional[str] = None
    model_name: Optional[str] = None
    context_window: Optional[int] = None
    temperature: Optional[float] = None
    top_p: Optional[float] = None
    max_tokens: Optional[int] = None
    role: Optional[ROLES] = None
    is_backup: Optional[bool] = None
    status: Optional[str] = None
    is_default: Optional[bool] = None
    enable_thinking: Optional[bool] = None


class ModelConfig(ModelConfigBase):
    id: str


class ModelTestRequest(BaseModel):
    model_config = ConfigDict(protected_namespaces=())
    vendor: VENDORS
    api_base: str
    api_key: str = ""
    model_name: str
    model_id: Optional[str] = None  # 若提供，则使用已保存的配置进行测试
