from tq.core.metrics import parse_prometheus_text, summarize_metrics


def test_parse_prometheus_text_and_summary() -> None:
    text = '''
# HELP kv cache usage
llamacpp:kv_cache_usage_ratio 0.42
llamacpp:requests_processing 2
llamacpp:generation_tokens_total 120
llamacpp:decode_tokens_per_second{slot="0"} 56.5
'''
    snapshot = parse_prometheus_text(text)
    summary = summarize_metrics(snapshot)
    assert summary["kv_cache_usage_ratio"] == 0.42
    assert summary["requests_processing"] == 2
    assert summary["generation_tokens_total"] == 120
    key = next(k for k in summary if k.startswith("llamacpp:decode_tokens_per_second"))
    assert summary[key] == 56.5
