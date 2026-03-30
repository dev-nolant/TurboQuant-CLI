from __future__ import annotations

from hashlib import sha256
from pathlib import Path
from typing import Literal

from platformdirs import user_cache_dir, user_config_dir
from pydantic import BaseModel, Field

APP_NAME = "tq"
APP_AUTHOR = "tq"

CacheType = Literal["turbo2", "turbo3", "turbo4"]
BackendType = Literal["metal", "cuda", "cpu"]
InstallStepStatus = Literal["pending", "running", "done", "failed", "skipped"]
EndpointType = Literal["native-completion", "openai-completion", "openai-chat", "unknown"]


class GenerationSettings(BaseModel):
    temperature: float = 0.7
    top_p: float = 0.9
    top_k: int = 40
    repeat_penalty: float = 1.1
    max_tokens: int = 128
    seed: int = -1
    preset: str = "balanced"


class HardwareProfile(BaseModel):
    os: str = "unknown"
    arch: str = "unknown"
    chip_name: str = "unknown"
    total_memory_gb: float = 0.0
    backend: BackendType = "cpu"
    cuda_version: str | None = None
    recommended_cache_type: CacheType = "turbo3"
    max_safe_context: int = 8192


class InstallStepState(BaseModel):
    name: str
    status: InstallStepStatus = "pending"
    detail: str = ""


class InstallState(BaseModel):
    install_path: Path = Field(default_factory=lambda: Path(user_cache_dir(APP_NAME, APP_AUTHOR)) / "llama-cpp-turboquant")
    binary_dir: Path = Field(default_factory=lambda: Path(user_cache_dir(APP_NAME, APP_AUTHOR)) / "llama-cpp-turboquant" / "build" / "bin")
    binary_name: str = "llama-server.exe" if __import__("os").name == "nt" else "llama-server"
    cli_name: str = "llama-cli.exe" if __import__("os").name == "nt" else "llama-cli"
    source: Literal["built", "system"] = "built"
    system_binary: Path | None = None
    last_commit: str | None = None
    validation_repo: Path = Field(default_factory=lambda: Path(user_cache_dir(APP_NAME, APP_AUTHOR)) / "turboquant_plus")
    help_cache: str = ""
    turboquant_verified: bool = False
    sparse_v_verified: bool = False
    web_ui_installed: bool = False
    steps: list[InstallStepState] = Field(
        default_factory=lambda: [
            InstallStepState(name="hardware", status="done"),
            InstallStepState(name="dependencies", status="done"),
            InstallStepState(name="clone"),
            InstallStepState(name="build"),
            InstallStepState(name="validate"),
            InstallStepState(name="done"),
        ]
    )

    @property
    def server_binary(self) -> Path:
        if self.source == "system" and self.system_binary:
            return self.system_binary
        return self.binary_dir / self.binary_name

    @property
    def cli_binary(self) -> Path:
        if self.source == "system" and self.system_binary:
            sibling = self.system_binary.parent / self.cli_name
            if sibling.exists():
                return sibling
        return self.binary_dir / self.cli_name


class BenchResult(BaseModel):
    cache_type: CacheType
    compression_ratio: float
    prefill_tps: float
    decode_tps: float


class BenchReport(BaseModel):
    model: str
    arch: str
    hardware: HardwareProfile
    results: list[BenchResult] = Field(default_factory=list)
    recommendation: CacheType
    timestamp: str
    raw_log_path: str | None = None


class ServerState(BaseModel):
    host: str = "127.0.0.1"
    port: int = 8080
    backend_port: int = 8092
    model_path: str = ""
    context_size: int = 32768
    cache_type: CacheType = "turbo3"
    sparse_v: bool = True
    running: bool = False
    pid: int | None = None
    ui_pid: int | None = None
    pid_file: Path = Field(default_factory=lambda: Path(user_config_dir(APP_NAME, APP_AUTHOR)) / "llama-server.pid")
    ui_pid_file: Path = Field(default_factory=lambda: Path(user_config_dir(APP_NAME, APP_AUTHOR)) / "tq-web.pid")
    detached_log: Path = Field(default_factory=lambda: Path(user_config_dir(APP_NAME, APP_AUTHOR)) / "llama-server.log")
    ui_log: Path = Field(default_factory=lambda: Path(user_config_dir(APP_NAME, APP_AUTHOR)) / "tq-web.log")
    last_command: list[str] = Field(default_factory=list)
    detected_endpoint: EndpointType = "unknown"


class AppConfig(BaseModel):
    install: InstallState = Field(default_factory=InstallState)
    last_bench_results: dict[str, BenchReport] = Field(default_factory=dict)
    default_port: int = 8080
    default_ctx: int = 32768
    hardware_profile: HardwareProfile | None = None
    generation: GenerationSettings = Field(default_factory=GenerationSettings)
    server: ServerState = Field(default_factory=ServerState)

    @classmethod
    def config_dir(cls) -> Path:
        path = Path(user_config_dir(APP_NAME, APP_AUTHOR))
        path.mkdir(parents=True, exist_ok=True)
        return path

    @classmethod
    def cache_dir(cls) -> Path:
        path = Path(user_cache_dir(APP_NAME, APP_AUTHOR))
        path.mkdir(parents=True, exist_ok=True)
        return path

    @classmethod
    def config_path(cls) -> Path:
        return cls.config_dir() / "config.json"

    @classmethod
    def load(cls) -> "AppConfig":
        path = cls.config_path()
        if not path.exists():
            return cls()
        return cls.model_validate_json(path.read_text())

    def save(self) -> Path:
        path = self.config_path()
        path.write_text(self.model_dump_json(indent=2))
        return path



def model_key(model_path: str | Path) -> str:
    return sha256(str(Path(model_path).expanduser().resolve()).encode()).hexdigest()
