from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable


@dataclass(slots=True)
class MetricSample:
    name: str
    labels: dict[str, str]
    value: float


@dataclass(slots=True)
class MetricsSnapshot:
    samples: list[MetricSample] = field(default_factory=list)

    def values_for(self, *names: str) -> list[MetricSample]:
        wanted = set(names)
        return [sample for sample in self.samples if sample.name in wanted]

    def first_value(self, *names: str) -> float | None:
        for sample in self.samples:
            if sample.name in names:
                return sample.value
        return None



def parse_prometheus_text(text: str) -> MetricsSnapshot:
    snapshot = MetricsSnapshot()
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        left, _, right = line.partition(" ")
        if not right:
            continue
        try:
            value = float(right.strip())
        except ValueError:
            continue
        if "{" not in left:
            snapshot.samples.append(MetricSample(name=left, labels={}, value=value))
            continue
        metric, _, rest = left.partition("{")
        label_blob = rest.rstrip("}")
        labels: dict[str, str] = {}
        for match in re.finditer(r'(\w+)="([^"]*)"', label_blob):
            labels[match.group(1)] = match.group(2)
        snapshot.samples.append(MetricSample(name=metric, labels=labels, value=value))
    return snapshot



def summarize_metrics(snapshot: MetricsSnapshot) -> dict[str, float | str]:
    summary: dict[str, float | str] = {}
    aliases: list[tuple[str, Iterable[str]]] = [
        ("kv_cache_usage_ratio", ("llamacpp:kv_cache_usage_ratio", "kv_cache_usage_ratio")),
        ("requests_processing", ("llamacpp:requests_processing", "requests_processing")),
        ("requests_deferred", ("llamacpp:requests_deferred", "requests_deferred")),
        ("prompt_tokens_total", ("llamacpp:prompt_tokens_total", "prompt_tokens_total")),
        ("generation_tokens_total", ("llamacpp:generation_tokens_total", "generation_tokens_total")),
    ]
    for display, candidates in aliases:
        value = snapshot.first_value(*tuple(candidates))
        if value is not None:
            summary[display] = value

    token_rates = [sample for sample in snapshot.samples if sample.name.endswith("tokens_per_second")]
    for sample in token_rates[:4]:
        suffix = ",".join(f"{k}={v}" for k, v in sorted(sample.labels.items())) or "default"
        summary[f"{sample.name}[{suffix}]"] = sample.value
    return summary
