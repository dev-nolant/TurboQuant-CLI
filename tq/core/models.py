from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Iterable
from urllib.parse import urlparse

import httpx
from pydantic import BaseModel, Field

from tq.core.config import AppConfig


class ModelRecord(BaseModel):
    name: str
    path: str
    size_bytes: int = 0
    sha256_prefix: str | None = None
    source_url: str | None = None


class ModelRegistry(BaseModel):
    models: list[ModelRecord] = Field(default_factory=list)
    default_model: str | None = None



def models_dir() -> Path:
    path = AppConfig.cache_dir() / "models"
    path.mkdir(parents=True, exist_ok=True)
    return path



def registry_path() -> Path:
    return AppConfig.config_dir() / "models.json"



def load_registry() -> ModelRegistry:
    path = registry_path()
    if not path.exists():
        return ModelRegistry()
    return ModelRegistry.model_validate_json(path.read_text())



def save_registry(registry: ModelRegistry) -> Path:
    path = registry_path()
    path.write_text(registry.model_dump_json(indent=2))
    return path



def infer_name(path: Path) -> str:
    return path.stem



def _sha256_prefix(path: Path, limit_mb: int = 8) -> str:
    h = hashlib.sha256()
    remaining = limit_mb * 1024 * 1024
    with path.open("rb") as f:
        while remaining > 0:
            chunk = f.read(min(1024 * 1024, remaining))
            if not chunk:
                break
            h.update(chunk)
            remaining -= len(chunk)
    return h.hexdigest()[:16]



def upsert_model(path: Path, source_url: str | None = None) -> ModelRecord:
    path = path.expanduser().resolve()
    if not path.exists():
        raise FileNotFoundError(path)
    if path.suffix.lower() != ".gguf":
        raise ValueError("only .gguf models are supported")
    record = ModelRecord(
        name=infer_name(path),
        path=str(path),
        size_bytes=path.stat().st_size,
        sha256_prefix=_sha256_prefix(path),
        source_url=source_url,
    )
    registry = load_registry()
    replaced = False
    for i, existing in enumerate(registry.models):
        if existing.path == record.path or existing.name == record.name:
            registry.models[i] = record
            replaced = True
            break
    if not replaced:
        registry.models.append(record)
    registry.models.sort(key=lambda m: m.name.lower())
    if registry.default_model is None:
        registry.default_model = record.path
    save_registry(registry)
    return record



def remove_model(name_or_path: str) -> bool:
    registry = load_registry()
    before = len(registry.models)
    registry.models = [m for m in registry.models if m.name != name_or_path and m.path != name_or_path]
    if registry.default_model == name_or_path:
        registry.default_model = registry.models[0].path if registry.models else None
    save_registry(registry)
    return len(registry.models) != before



def scan_directory(directory: Path) -> list[ModelRecord]:
    found: list[ModelRecord] = []
    for path in directory.expanduser().rglob("*.gguf"):
        found.append(upsert_model(path))
    return found



def set_default_model(name_or_path: str) -> ModelRecord:
    registry = load_registry()
    for model in registry.models:
        if model.name == name_or_path or model.path == name_or_path:
            registry.default_model = model.path
            save_registry(registry)
            config = AppConfig.load()
            config.server.model_path = model.path
            config.save()
            return model
    raise KeyError(name_or_path)


async def download_model(url: str, filename: str | None = None) -> Iterable[tuple[int, int | None]]:
    target_name = filename or Path(urlparse(url).path).name or "model.gguf"
    if not target_name.endswith(".gguf"):
        raise ValueError("download target must be a .gguf file")
    target = models_dir() / target_name
    async with httpx.AsyncClient(follow_redirects=True, timeout=None) as client:
        async with client.stream("GET", url) as response:
            response.raise_for_status()
            total = int(response.headers.get("content-length", "0")) or None
            downloaded = 0
            with target.open("wb") as f:
                async for chunk in response.aiter_bytes():
                    f.write(chunk)
                    downloaded += len(chunk)
                    yield downloaded, total
    upsert_model(target, source_url=url)



def list_models() -> list[ModelRecord]:
    registry = load_registry()
    registry.models = [m for m in registry.models if Path(m.path).exists()]
    save_registry(registry)
    return registry.models



def default_model() -> ModelRecord | None:
    registry = load_registry()
    if registry.default_model is None:
        return None
    for model in registry.models:
        if model.path == registry.default_model:
            return model
    return None



def format_size(size_bytes: int) -> str:
    value = float(size_bytes)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            return f"{value:.1f} {unit}"
        value /= 1024.0
    return f"{size_bytes} B"
