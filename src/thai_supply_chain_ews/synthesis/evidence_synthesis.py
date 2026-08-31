"""Synthesis guards and the locked-test closeout (Task E1).

The closeout has to survive being read by someone who wants the project to look
better than it was — including, eventually, its own author. So the sentences that
would flatter the record are refused by name rather than by discipline.

**Six collapses.** Inconclusive is not no effect. Not supported is not disproven.
Unresolved is not absent. A selected reference is not a proven superior. A
development evaluation is not a production validation. A latest-vintage
evaluation is not a real-time backtest. Each has its own guard, because each is a
different mistake and a single "be careful" catches none of them.

**The locked test is verified without being opened.** The manifest is key-only —
issue months and nothing else — so the closeout can confirm the range, the purge
buffer and the untouched status by reading keys alone. Hashing the outcomes would
also be reading them, and :func:`assert_locked_outcomes_untouched` refuses that
too.

**"Project failed" is not available.** The engineering and evaluation programme
ran to completion and produced a reproducible pipeline, a registered operational
reference and four honest negative or inconclusive results. What did not happen
is that a candidate earned promotion. Those are different sentences and the
guard keeps them apart.
"""

from __future__ import annotations

import hashlib
import json

__all__ = [
    "PROHIBITED_LOCKED_PHRASES",
    "PROHIBITED_PORTFOLIO_PHRASES",
    "REQUIRED_PROJECT_STATUS",
    "SynthesisError",
    "assert_baseline_reference_not_superiority",
    "assert_d3_not_a_production_model",
    "assert_development_not_production_validation",
    "assert_inconclusive_not_absence",
    "assert_locked_outcomes_untouched",
    "assert_no_project_failed_language",
    "assert_not_real_time",
    "assert_portfolio_wording",
    "assert_project_status",
    "content_checksum",
    "verify_locked_test_closeout",
]


REQUIRED_PROJECT_STATUS = {
    "development_program_status":
        "closed_without_supported_incremental_commodity_model",
    "registered_operational_reference_available": True,
    "registered_operational_reference_source": "D3",
    "operational_model_selected": False,
    "production_deployment_authorized": False,
    "commodity_incremental_signal_supported": False,
    "model_feature_approved": False,
    "confirmatory_claim_authorized": False,
    "locked_test_status": "sealed_unopened",
    "locked_test_outcomes_read": False,
    "fully_real_time_backtest": False,
    "latest_vintage_target_evaluation": True,
    "future_reopening_requires_new_external_evidence": True,
}

PROHIBITED_LOCKED_PHRASES = (
    "locked test passed", "locked test was passed", "locked test validated",
    "locked test confirms", "validated on the locked test",
    "unused data proving generalization", "unused data proves generalisation",
    "held-out validation confirms", "out-of-sample performance confirmed",
    "final test passed",
)

PROHIBITED_PORTFOLIO_PHRASES = (
    "beat the baseline", "beats the baseline", "beat the benchmark",
    "beats the benchmark", "outperformed the benchmark", "outperforms the benchmark",
    "deployable early-warning model", "deployable early warning model",
    "production ready", "production-ready", "fully real-time", "fully real time",
    "real-time backtest", "real time backtest",
    "commodities have no predictive value", "proved commodities do not predict",
    "validated on unseen final-test outcomes", "locked test confirms",
)

_INCONCLUSIVE_AS_ABSENCE = (
    "has no effect", "no effect on", "no predictive relationship",
    "there is no relationship", "proved there is no", "shown to be irrelevant",
    "disproved", "null hypothesis proven", "commodities have no predictive value",
)

_SUPERIORITY = (
    "persistence is statistically superior", "persistence is proven superior",
    "significantly better than no-contraction", "statistically superior to",
    "proven superiority", "significantly outperforms no-contraction",
)

#: Deployment senses only. "in production" alone is too loose in this domain:
#: the target is built from industrial PRODUCTION data, and forbidding the
#: phrase would distort the prose rather than protect the claim.
_PRODUCTION = (
    "production model", "deployed model", "deployed system",
    "in production use", "put into production", "running in production",
    "deployed in production", "d3 model is deployed", "production deployment",
    "deployed to production", "is deployed",
)

_REAL_TIME = (
    "fully real-time", "fully real time", "real-time backtest",
    "real time backtest", "point-in-time backtest", "true real-time evaluation",
)


class SynthesisError(ValueError):
    """The synthesis was asked to state something the evidence does not carry."""


#: Words that turn a banned phrase into its own denial. A report that must
#: explain "a model that did not beat its benchmark has not DISPROVED the
#: hypothesis" cannot be forbidden from writing the word it is disowning.
_NEGATIONS = ("not ", "never ", "cannot ", "no claim ", "without ", "neither ")

#: How far back to look for one. Long enough for "has not been", short enough
#: that a negation two sentences earlier does not launder a later assertion.
_NEGATION_WINDOW = 24


def _strip_named_terms(text: str) -> str:
    """Remove backticked and quoted spans, which NAME a term rather than assert it."""
    import re

    return re.sub(r'"[^"]*"', " ", re.sub(r"`[^`]*`", " ", str(text)))


def _negated(lowered: str, position: int) -> bool:
    window = lowered[max(0, position - _NEGATION_WINDOW):position]
    return any(negation in window for negation in _NEGATIONS)


def _check(text, phrases, message_builder, strip_named_terms: bool = True) -> None:
    """Raise on an asserted prohibited phrase, not on a named or denied one."""
    source = _strip_named_terms(text) if strip_named_terms else str(text)
    lowered = source.lower()
    for phrase in phrases:
        start = 0
        while (position := lowered.find(phrase, start)) != -1:
            if not _negated(lowered, position):
                raise SynthesisError(message_builder(phrase))
            start = position + len(phrase)


def assert_inconclusive_not_absence(text) -> None:
    """Raise on wording that reads an inconclusive result as proof of absence."""
    _check(text, _INCONCLUSIVE_AS_ABSENCE, lambda p: (
        f"{p!r} turns an inconclusive result into proof of absence. D5's "
        "intervals crossed zero on fifteen issue-month clusters and D4's "
        "specification was fixed: neither could rule an effect out"
    ))


def assert_baseline_reference_not_superiority(text) -> None:
    """Raise on claiming the registered reference is a proven superior.

    D3 selected persistence as the reference under a preregistered rule. The
    paired comparison against no-contraction was **inconclusive** at both
    horizons, so "registered" and "superior" are not interchangeable.
    """
    _check(text, _SUPERIORITY, lambda p: (
        f"{p!r} claims statistical superiority. D3's paired comparison against "
        "no-contraction was inconclusive at both horizons; persistence is the "
        "REGISTERED reference, chosen under a preregistered tie-break"
    ))


def assert_d3_not_a_production_model(text) -> None:
    """Raise on describing the operational reference as a deployed model."""
    _check(text, _PRODUCTION, lambda p: (
        f"{p!r} describes a deployed production model. D3 established a "
        "registered operational EVALUATION REFERENCE; no model was selected, "
        "approved or deployed"
    ))


def assert_development_not_production_validation(status: dict) -> None:
    """Raise if a development evaluation is recorded as production validation."""
    if status.get("operational_model_selected"):
        raise SynthesisError("operational_model_selected is true; none was")
    if status.get("production_deployment_authorized"):
        raise SynthesisError(
            "production deployment is recorded as authorized. Every candidate "
            "failed its development gate"
        )
    if status.get("confirmatory_claim_authorized"):
        raise SynthesisError(
            "a confirmatory claim is recorded as authorized. Every evaluation in "
            "this project was exploratory or a registered reference"
        )


def assert_not_real_time(text, status: dict = None) -> None:
    """Raise on calling the project real-time.

    The feature side of the World Bank path is archived first-release. The
    target side is latest vintage for every source, so no part of the evaluation
    reproduces what was knowable at the time on the target.
    """
    _check(text, _REAL_TIME, lambda p: (
        f"{p!r} claims a real-time backtest. Targets are LATEST VINTAGE "
        "throughout; the evaluation is release-aware, not point-in-time on the "
        "target side"
    ))
    if status is not None:
        if status.get("fully_real_time_backtest"):
            raise SynthesisError("fully_real_time_backtest is true; it is not")
        if not status.get("latest_vintage_target_evaluation"):
            raise SynthesisError(
                "latest_vintage_target_evaluation is false; every target value "
                "used in this project is a latest-vintage value"
            )


def assert_no_project_failed_language(text) -> None:
    """Raise on 'the project failed'.

    The programme completed: a reproducible pipeline, a registered reference and
    four honest results. The candidates did not earn promotion. Collapsing the
    two is inaccurate in a way that happens to be self-flagellating rather than
    self-flattering, and it is still inaccurate.
    """
    lowered = str(text).lower()
    for phrase in ("project failed", "the project was a failure",
                   "failed project", "project_failed"):
        if phrase in lowered:
            raise SynthesisError(
                f"{phrase!r} misstates the outcome. The engineering and "
                "evaluation programme completed and produced a reproducible "
                "pipeline, a registered operational reference and four honest "
                "results; the candidate models did not earn promotion"
            )


def assert_portfolio_wording(text, prohibited=PROHIBITED_PORTFOLIO_PHRASES,
                             task_codes=(), allow_task_codes: bool = False) -> None:
    """Raise on a portfolio claim the evidence does not support.

    Also keeps internal task codes out of the reader-facing narrative: "C11-R1"
    means nothing to someone reading a case study, and a reader who has to
    decode it stops reading.
    """
    _check(text, prohibited, lambda p: (
        f"{p!r} is not supported by the development evidence. No candidate beat "
        "its benchmark, no model was deployed, the evaluation is not real-time, "
        "and the locked test was never opened"
    ))
    if not allow_task_codes and task_codes:
        import re

        found = sorted({
            code for code in task_codes
            if re.search(rf"\b{re.escape(code)}\b", str(text))
        })
        if found:
            raise SynthesisError(
                f"internal task codes {found} appear in the reader-facing "
                "narrative. They belong in the technical appendix or the evidence "
                "links"
            )


def assert_project_status(status: dict) -> None:
    """Raise unless every required project-status field carries its value."""
    missing = [f for f in REQUIRED_PROJECT_STATUS if f not in status]
    if missing:
        raise SynthesisError(f"project status is missing {sorted(missing)}")
    for name, expected in REQUIRED_PROJECT_STATUS.items():
        if status[name] != expected:
            raise SynthesisError(
                f"project status {name} is {status[name]!r}, expected {expected!r}"
            )
    assert_development_not_production_validation(status)
    assert_not_real_time("", status)


# ---------------------------------------------------------------------------
# Locked-test closeout
# ---------------------------------------------------------------------------
def assert_locked_outcomes_untouched(manifest: dict, text: str = "") -> None:
    """Raise if a locked outcome was opened, hashed, summarised or inferred.

    The manifest is key-only by construction, which is what lets the closeout
    verify the reservation without reading anything it must not. Hashing an
    outcome would still be reading it, so the manifest is checked for the
    presence of outcome-shaped content rather than only for a flag.
    """
    if manifest.get("locked_test_evaluated"):
        raise SynthesisError("the manifest reports the locked test as evaluated")
    if manifest.get("locked_test_outcomes_read"):
        raise SynthesisError("the manifest reports locked outcomes as read")
    if manifest.get("runner_can_reach_locked_origins"):
        raise SynthesisError(
            "a runner is recorded as able to reach locked origins"
        )
    outcome_shaped = sorted(
        key for key in manifest
        if any(token in key.lower() for token in
               ("score", "mae", "rmse", "prediction", "metric", "observed",
                "target_value", "outcome_value"))
    )
    if outcome_shaped:
        raise SynthesisError(
            f"the locked-test manifest carries outcome-shaped field(s) "
            f"{outcome_shaped}. It is key-only: issue months and nothing else"
        )
    if text:
        _check(text, PROHIBITED_LOCKED_PHRASES, lambda p: (
            f"{p!r} describes the locked test as used. It was intentionally left "
            "unopened because no independently preregistered candidate earned "
            "access through development evidence"
        ))


def verify_locked_test_closeout(manifest: dict, config: dict,
                                candidate_authorizations: dict) -> dict:
    """Confirm the reservation from keys alone, and that nobody was authorized."""
    assert_locked_outcomes_untouched(manifest)
    expected = config
    horizons = manifest["horizons"]
    h1 = [horizons["1"]["start"], horizons["1"]["end"]]
    h3 = [horizons["3"]["start"], horizons["3"]["end"]]
    authorized = sorted(
        name for name, value in candidate_authorizations.items() if value
    )
    if authorized:
        raise SynthesisError(
            f"candidate(s) {authorized} are recorded as locked-test authorized. "
            "None earned access"
        )
    return {
        "manifest_is_key_only": True,
        "horizon_1_range": h1,
        "horizon_1_range_matches": h1 == list(expected["horizon_1_range"]),
        "horizon_3_range": h3,
        "horizon_3_range_matches": h3 == list(expected["horizon_3_range"]),
        "reserved_months": len(manifest["reserved_months"]),
        "reserved_months_match": (
            len(manifest["reserved_months"]) == expected["reserved_months"]
        ),
        "purge_months": manifest["purge_months"],
        "locked_test_evaluated": False,
        "locked_test_outcomes_read": False,
        "runner_can_reach_locked_origins": False,
        "prediction_or_metric_exists_for_locked_origins": False,
        "any_candidate_locked_test_evaluation_authorized": False,
        "candidate_authorizations": dict(sorted(candidate_authorizations.items())),
        "outcomes_opened_hashed_or_summarised": False,
        "status": "sealed_unopened",
        "required_language": expected["required_language"].strip(),
    }


def content_checksum(payload) -> str:
    """Stable digest of a payload, generation timestamps excluded."""
    dropped = {"generated_at_utc", "run_started_at_utc", "run_finished_at_utc",
               "measured_at_utc"}

    def strip(value):
        if isinstance(value, dict):
            return {k: strip(v) for k, v in value.items() if k not in dropped}
        if isinstance(value, list):
            return [strip(v) for v in value]
        return value

    text = json.dumps(strip(payload), ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
