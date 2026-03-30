from tq.core.benchmarker import _extract_tps


def test_extract_tps() -> None:
    lines = [
        "llama_print_timings: prompt eval time =  120.00 ms /  20 tokens (166.67 tokens/s)",
        "llama_print_timings:        eval time = 1000.00 ms / 50 runs   (50.00 tokens/s)",
    ]
    prefill, decode = _extract_tps(lines)
    assert prefill == 166.67
    assert decode == 50.0
