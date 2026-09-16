"""Known-value leak detection at the privacy boundary."""

import json

from app.evaluation.models import EvaluationDataset, EvaluationSuiteResult, PrivacyCase
from app.evaluation.suites.base import SuiteContext, evaluate_cases, pass_fail
from app.privacy import PrivacyProcessor


def leaked_values(text: str, protected_values: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(value for value in protected_values if value in text)


def evaluate(dataset: EvaluationDataset, context: SuiteContext) -> EvaluationSuiteResult:
    del context

    def one(raw_case):
        case = PrivacyCase.model_validate(raw_case)
        result = PrivacyProcessor().process(case.question)
        safe_payload = json.dumps(
            {
                "safe_text": result.safe_text,
                "redaction_counts": result.redaction_counts.model_dump(),
            },
            sort_keys=True,
        )
        leaks = leaked_values(safe_payload, case.protected_values)
        deterministic_reuse = len(result.token_mappings) == len(
            {entry.original_value for entry in result.token_mappings}
        )
        counts_ok = (
            result.redaction_counts.identifier_occurrences == case.expected_identifier_occurrences
            and result.redaction_counts.email_occurrences == case.expected_email_occurrences
            and result.redaction_counts.phone_occurrences == case.expected_phone_occurrences
        )
        mapping_absent = (
            "original_value" not in safe_payload and "token_mappings" not in safe_payload
        )
        passed = not leaks and deterministic_reuse and counts_ok and mapping_absent
        return pass_fail(
            case,
            passed,
            metrics={"privacy_leaks": float(len(leaks))},
            expected="no known protected values",
            actual=f"{len(leaks)} known-value leak(s)" if leaks else "no leaks",
        )

    return evaluate_cases(
        dataset,
        one,
        lambda items: {"privacy_leak_count": sum(i.metrics.get("privacy_leaks", 0) for i in items)},
    )
