from __future__ import annotations

import platform as _platform
from pathlib import Path
from typing import List, Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    openrouter_api_key: Optional[str] = None
    openai_api_key: Optional[str] = None
    dashscope_api_key: Optional[str] = None
    anthropic_api_key: Optional[str] = None
    google_api_key: Optional[str] = None
    deepseek_api_key: Optional[str] = None
    groq_api_key: Optional[str] = None
    mistral_api_key: Optional[str] = None
    togetherai_api_key: Optional[str] = None
    fireworks_api_key: Optional[str] = None
    xai_api_key: Optional[str] = None
    cerebras_api_key: Optional[str] = None
    sambanova_api_key: Optional[str] = None
    azure_api_key: Optional[str] = None
    azure_api_base: Optional[str] = None
    azure_api_version: Optional[str] = None
    openai_api_base: Optional[str] = None
    dashscope_api_base: str = "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"
    ollama_base_url: Optional[str] = None

    reasoning_model: str = "reasoning"
    coding_model: str = "coding"
    quick_model: str = "fast"
    local_model: str = "ollama/llama3.1"

    max_cost_per_task_usd: float = 10.0
    max_tokens_per_task: int = 120000
    max_api_calls_per_minute: int = 40
    enable_cost_tracking: bool = True

    sandbox_enabled: bool = True
    sandbox_network_enabled: bool = False
    sandbox_worktree_only: bool = True
    docker_image: str = "viki-sandbox:latest"
    sandbox_memory_limit: str = "2g"
    sandbox_nano_cpus: int = 2000000000
    sandbox_pids_limit: int = 256
    max_execution_time_seconds: int = 300
    max_repair_attempts: int = 2
    approval_mode: str = "auto"
    approval_session_grants_enabled: bool = True
    approval_risk_threshold: int = 50
    high_risk_command_tokens: List[str] = Field(default_factory=lambda: [
        "git push", "gh pr create", "docker push", "kubectl apply", "terraform apply", "rm -rf", "chmod 777",
    ])
    forbidden_modules: List[str] = Field(default_factory=lambda: [
        r"os\.system",
        r"subprocess\.Popen",
        r"socket\.",
        r"requests\.(get|post|put|delete)",
    ])
    secret_patterns: List[str] = Field(default_factory=lambda: ["sk-", "AKIA", "ghp_", "private_key"])
    allowed_command_prefixes: List[str] = Field(default_factory=lambda: [
        "python", "python3", "pytest", "pip", "uv", "poetry", "ruff", "mypy",
        "npm", "pnpm", "yarn", "bun", "node", "npx",
        "cargo", "go", "javac", "java", "gradle", "./gradlew",
        "make", "cmake", "ctest", "git", "bash", "sh", "pwsh", "powershell",
    ])

    max_swarm_depth: int = 3
    max_agents_per_swarm: int = 5
    max_parallel_swarms: int = 8
    enable_fractal_recursion: bool = True
    context_budget_chars: int = 18000
    route_large_repo_threshold: int = 250

    database_url: str = "sqlite:///./.viki-workspace/viki.db"
    checkpoint_interval_seconds: int = 20
    session_timeout_hours: int = 24

    workspace_dir: str = ".viki-workspace"
    sandbox_dir: str = ".viki-workspace/sandbox"
    memory_dir: str = ".viki-workspace/memory"
    log_dir: str = ".viki-workspace/logs"
    temp_dir: str = ".viki-workspace/temp"
    skill_dir: str = ".viki-workspace/skills"
    runs_dir: str = ".viki-workspace/runs"
    benchmark_dir: str = ".viki-workspace/benchmarks"
    skill_env_dir: str = ".viki-workspace/skill_envs"
    skill_manifest_name: str = "manifest.yaml"

    log_level: str = "INFO"
    metrics_enabled: bool = True
    metrics_port: int = 9090
    structured_logging: bool = True

    api_host: str = "127.0.0.1"
    api_port: int = 8787


    telegram_enabled: bool = False
    telegram_bot_token: Optional[str] = None
    telegram_webhook_secret: Optional[str] = None
    telegram_allowed_chat_ids: str = ""
    telegram_reply_max_chars: int = 3500

    whatsapp_enabled: bool = False
    whatsapp_account_sid: Optional[str] = None
    whatsapp_auth_token: Optional[str] = None
    whatsapp_from_number: Optional[str] = None
    whatsapp_allowed_senders: str = ""
    whatsapp_validate_signature: bool = True
    whatsapp_webhook_url: Optional[str] = None
    whatsapp_reply_max_chars: int = 3000

    platform: str = Field(default_factory=lambda: _platform.system().lower())
    shell_path: Optional[str] = None

    @field_validator("shell_path", mode="before")
    @classmethod
    def set_shell(cls, value: Optional[str]) -> str:
        if value:
            return value
        return "powershell.exe" if _platform.system().lower().startswith("win") else "/bin/bash"

    def ensure_workspace(self, root: str | Path = ".") -> Path:
        root_path = Path(root).resolve()
        workspace = root_path / self.workspace_dir
        for relative in [
            self.workspace_dir,
            self.sandbox_dir,
            self.memory_dir,
            self.log_dir,
            self.temp_dir,
            self.skill_dir,
            self.runs_dir,
            self.benchmark_dir,
            self.skill_env_dir,
        ]:
            (root_path / relative).mkdir(parents=True, exist_ok=True)
        return workspace


settings = Settings()
