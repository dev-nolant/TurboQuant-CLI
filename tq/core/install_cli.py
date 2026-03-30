from __future__ import annotations

from tq.core.config import AppConfig
from tq.core.hardware import dependency_status, detect_hardware, make_profile
from tq.core.installer import build_repo, ensure_clone, refresh_install_metadata, validate_build
from tq.core.webui import install_llama_ui


async def run_install(*, with_web_ui: bool = False) -> None:
    config = AppConfig.load()
    hw = detect_hardware()
    profile = make_profile(hw)
    config.hardware_profile = profile
    config.save()

    print(f"hardware: {hw.chip} backend={hw.backend} mem={hw.vram_summary}")
    print(f"recommended cache: {profile.recommended_cache_type} max_ctx={profile.max_safe_context}")
    print("dependencies:")
    for name, (ok, hint) in dependency_status().items():
        print(f"  {'OK' if ok else 'MISSING'} {name}{'' if ok else f' - {hint}'}")

    print("\n[1/4] clone")
    async for line in ensure_clone(config):
        print(line)

    print("\n[2/4] build")
    async for line in build_repo(config, hw):
        print(line)

    print("\n[3/4] validate")
    async for line in validate_build(config):
        print(line)

    if with_web_ui:
        print("\n[4/4] install web ui")
        path = install_llama_ui()
        print(f"installed llama.ui at {path}")
    else:
        print("\n[4/4] web ui skipped")

    refresh_install_metadata(config)
    config = AppConfig.load()
    print("\ninstall complete")
    print(f"server: {config.install.server_binary}")
    print(f"cli: {config.install.cli_binary}")
    print(f"turboquant verified: {config.install.turboquant_verified}")
    print(f"sparse-v verified: {config.install.sparse_v_verified}")
    print(f"web ui installed: {config.install.web_ui_installed}")
