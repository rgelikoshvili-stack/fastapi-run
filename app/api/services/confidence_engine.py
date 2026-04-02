def adjust_confidence(base_conf: float, context: dict, qa: dict) -> float:
    conf = base_conf

    if context.get("context_used"):
        conf += 0.05

    if qa.get("score", 1) < 0.7:
        conf -= 0.1

    if qa.get("issues"):
        conf -= 0.05 * len(qa.get("issues"))

    return max(min(conf, 1.0), 0.0)