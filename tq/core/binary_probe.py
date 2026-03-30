from __future__ import annotations

import subprocess
from pathlib import Path

from tq.core.config import CacheType


class BinaryCapabilities(dict):
    @property
    def supports_cache_type_flags(self) -> bool:
        return bool(self.get("supports_cache_type_flags", False))

    @property
    def supports_turboquant(self) -> bool:
        return bool(self.get("supports_turboquant", False))

    @property
    def supports_sparse_v(self) -> bool:
        return bool(self.get("supports_sparse_v", False))

    @property
    def help_text(self) -> str:
        return str(self.get("help_text", ""))



def read_help(binary: Path) -> str:
    try:
        return subprocess.check_output([str(binary), "--help"], text=True, stderr=subprocess.STDOUT)
    except Exception as exc:
        return str(exc)



def probe_binary(binary: Path) -> BinaryCapabilities:
    text = read_help(binary)
    low = text.lower()
    return BinaryCapabilities(
        help_text=text,
        supports_cache_type_flags=("--cache-type-k" in text and "--cache-type-v" in text),
        supports_turboquant=("turbo2" in low or "turbo3" in low or "turbo4" in low),
        supports_sparse_v=("sparse-v" in low or "sparse v" in low or "turbo_sparse_v" in low),
    )



def verify_cache_mode(binary: Path, cache_type: CacheType) -> tuple[bool, str]:
    caps = probe_binary(binary)
    if not caps.supports_cache_type_flags:
        return False, "missing --cache-type-k/--cache-type-v flags"
    if cache_type not in caps.help_text.lower():
        return False, f"{cache_type} not advertised in --help"
    return True, f"{cache_type} advertised in --help"
