def compute_metrics(results: list[dict]) -> dict:
    tp = sum(1 for r in results if r["expected_regression"] and r["detected_regression"])
    fp = sum(1 for r in results if not r["expected_regression"] and r["detected_regression"])
    fn = sum(1 for r in results if r["expected_regression"] and not r["detected_regression"])

    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = (
        2 * precision * recall / (precision + recall)
        if (precision + recall) > 0
        else 0.0
    )

    expected_regressions = sum(1 for r in results if r["expected_regression"])
    fixes_verified = sum(1 for r in results if r.get("fix_verified", False))
    fix_success_rate = fixes_verified / max(1, expected_regressions)

    return {
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "fix_success_rate": fix_success_rate,
    }
