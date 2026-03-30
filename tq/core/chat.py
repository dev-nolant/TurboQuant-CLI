from __future__ import annotations

import json
from typing import Any

import httpx

from tq.core.config import AppConfig


async def completion(config: AppConfig, prompt: str) -> str:
    base = f"http://{config.server.host}:{config.server.port}"
    gen = config.generation
    system_prompt = "You are a helpful concise assistant. Answer directly and clearly."
    async with httpx.AsyncClient(timeout=120.0) as client:
        attempts = [
            (
                "native-completion",
                f"{base}/completion",
                {
                    "prompt": f"<|system|>\n{system_prompt}\n<|user|>\n{prompt}\n<|assistant|>\n",
                    "n_predict": gen.max_tokens,
                    "temperature": gen.temperature,
                    "top_p": gen.top_p,
                    "top_k": gen.top_k,
                    "repeat_penalty": gen.repeat_penalty,
                    "seed": gen.seed,
                    "stop": ["<|user|>", "<|end|>", "<|im_end|>"],
                    "stream": False,
                },
            ),
            (
                "openai-completion",
                f"{base}/v1/completions",
                {
                    "model": "local",
                    "prompt": prompt,
                    "max_tokens": gen.max_tokens,
                    "temperature": gen.temperature,
                    "top_p": gen.top_p,
                    "stream": False,
                },
            ),
            (
                "openai-chat",
                f"{base}/v1/chat/completions",
                {
                    "model": "local",
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": prompt},
                    ],
                    "max_tokens": gen.max_tokens,
                    "temperature": gen.temperature,
                    "top_p": gen.top_p,
                    "stream": False,
                },
            ),
        ]
        last_error = None
        for endpoint_type, url, payload in attempts:
            try:
                response = await client.post(url, json=payload)
                response.raise_for_status()
                data = response.json()
                parsed = _clean_text(_extract_text(data))
                if parsed:
                    config.server.detected_endpoint = endpoint_type
                    config.save()
                    return parsed
            except Exception as exc:
                last_error = exc
        raise RuntimeError(f"no working completion endpoint found: {last_error}")



def _extract_text(data: Any) -> str:
    if isinstance(data, dict):
        for key in ("content", "response", "text"):
            value = data.get(key)
            if isinstance(value, str):
                return value
        if "choices" in data and isinstance(data["choices"], list) and data["choices"]:
            first = data["choices"][0]
            if isinstance(first, dict):
                text = first.get("text")
                if isinstance(text, str):
                    return text
                message = first.get("message")
                if isinstance(message, dict):
                    content = message.get("content")
                    if isinstance(content, str):
                        return content
                delta = first.get("delta")
                if isinstance(delta, dict) and isinstance(delta.get("content"), str):
                    return delta["content"]
        if "data" in data:
            return _extract_text(data["data"])
    if isinstance(data, list):
        parts = [_extract_text(item) for item in data]
        return "\n".join(part for part in parts if part)
    return str(data)



def _clean_text(text: str) -> str:
    text = text.strip()
    if not text:
        return text
    if text.startswith("{") or text.startswith("["):
        try:
            decoded = json.loads(text)
            if isinstance(decoded, str):
                text = decoded
            else:
                nested = _extract_text(decoded)
                if nested:
                    text = nested
        except Exception:
            pass
    text = text.replace("\\n", "\n").replace("\\t", "\t")
    text = text.replace("\\\"", '"')
    text = text.replace("<|assistant|>", "").replace("<|system|>", "").replace("<|user|>", "")
    text = text.replace("<|im_end|>", "").replace("<|end|>", "")
    lines = [line.rstrip() for line in text.splitlines()]
    cleaned = "\n".join(line for line in lines if line.strip() or len(lines) == 1)
    return cleaned.strip()
