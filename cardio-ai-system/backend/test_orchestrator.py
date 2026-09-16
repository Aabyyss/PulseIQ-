import json
import os
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.orchestrator import run_diagnosis_from_text  # noqa: E402

CASES = [
    ("I feel chest pressure and breathing difficulty when walking upstairs", "high"),
    ("I feel fine today, just a bit tired after work", "low"),
    ("crushing chest pain with sweating and pain in my left arm", "high"),
]


def main() -> None:
    failures = []
    for text, expected in CASES:
        result = run_diagnosis_from_text(text)
        risk = result["risk_level"].lower()
        status = "PASS" if risk == expected else "FAIL"
        if risk != expected:
            failures.append((text, risk, expected))
        print(
            f"[{status}] risk={risk} (expected {expected}) "
            f"prob={result['probability']:.2f} symptoms={result['symptoms']} :: {text}"
        )

    if failures:
        print(json.dumps({"failed": failures}, indent=2))
        sys.exit(1)
    print("All orchestrator cases passed.")


if __name__ == "__main__":
    main()
