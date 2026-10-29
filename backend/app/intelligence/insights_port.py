"""AI change-flag port for Health Trends. Fake adapter for CI; BAA endpoint for prod."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class TrendSample:
    effective_at: str
    value: float
    unit: str
    reference_low: float | None
    reference_high: float | None


@dataclass(frozen=True)
class InsightFlag:
    code: str
    severity: str  # info | notable
    title: str
    explanation: str
    framing: str


class InsightsPort(Protocol):
    def explain_changes(
        self,
        *,
        test_code: str,
        test_label: str,
        samples: list[TrendSample],
    ) -> list[InsightFlag]: ...


class FakeInsightsAdapter:
    """
    Deterministic, educational change flags — not diagnosis or clinical advice.
    Production must use a HIPAA-eligible model endpoint under a BAA.
    """

    FRAMING = "educational_support_for_clinician_discussion"

    def explain_changes(
        self,
        *,
        test_code: str,
        test_label: str,
        samples: list[TrendSample],
    ) -> list[InsightFlag]:
        if len(samples) < 2:
            return []

        ordered = sorted(samples, key=lambda s: s.effective_at)
        prev, latest = ordered[-2], ordered[-1]
        flags: list[InsightFlag] = []

        # Prefer point ranges; fall back to latest known range on the series
        def bounds(sample: TrendSample) -> tuple[float | None, float | None]:
            low, high = sample.reference_low, sample.reference_high
            if low is not None and high is not None:
                return low, high
            for candidate in reversed(ordered):
                if candidate.reference_low is not None and candidate.reference_high is not None:
                    return candidate.reference_low, candidate.reference_high
            return None, None

        prev_low, prev_high = bounds(prev)
        latest_low, latest_high = bounds(latest)

        crossed = False
        if prev_low is not None and prev_high is not None and latest_low is not None and latest_high is not None:
            prev_in = prev_low <= prev.value <= prev_high
            latest_in = latest_low <= latest.value <= latest_high
            if prev_in and not latest_in:
                crossed = True
                flags.append(
                    InsightFlag(
                        code=f"{test_code}.range_exit",
                        severity="notable",
                        title=f"{test_label} moved outside the reference range",
                        explanation=(
                            f"Your latest {test_label.lower()} reading "
                            f"({latest.value:g} {latest.unit}) sits outside the typical "
                            f"reference range shown on the chart "
                            f"({latest_low:g}–{latest_high:g} {latest.unit}). "
                            "Reference ranges are laboratory context, not a diagnosis. "
                            "Bring this chart to your next visit so your clinician can "
                            "interpret it with your full history."
                        ),
                        framing=self.FRAMING,
                    )
                )
            elif not prev_in and latest_in:
                flags.append(
                    InsightFlag(
                        code=f"{test_code}.range_return",
                        severity="info",
                        title=f"{test_label} returned inside the reference range",
                        explanation=(
                            f"Compared with the prior result, the latest {test_label.lower()} "
                            f"reading ({latest.value:g} {latest.unit}) is back within the "
                            "reference band drawn on the chart. Only your care team can say "
                            "what that means for you."
                        ),
                        framing=self.FRAMING,
                    )
                )

        if prev.value != 0:
            delta = latest.value - prev.value
            pct = abs(delta) / abs(prev.value) * 100.0
            if pct >= 15 and not crossed:
                direction = "higher" if delta > 0 else "lower"
                flags.append(
                    InsightFlag(
                        code=f"{test_code}.change_{direction}",
                        severity="notable",
                        title=f"{test_label} changed by about {pct:.0f}%",
                        explanation=(
                            f"The most recent {test_label.lower()} value "
                            f"({latest.value:g} {latest.unit} on {latest.effective_at[:10]}) "
                            f"is about {pct:.0f}% {direction} than the previous point "
                            f"({prev.value:g} {prev.unit} on {prev.effective_at[:10]}). "
                            "Lab results vary for many reasons. This note is meant to support "
                            "a conversation with your clinician — it is not a diagnosis or "
                            "treatment recommendation."
                        ),
                        framing=self.FRAMING,
                    )
                )

        # Three consecutive rises/falls — educational pattern note
        if len(ordered) >= 3:
            a, b, c = ordered[-3], ordered[-2], ordered[-1]
            if a.value < b.value < c.value:
                flags.append(
                    InsightFlag(
                        code=f"{test_code}.rising_streak",
                        severity="info",
                        title=f"{test_label} has risen across the last three results",
                        explanation=(
                            f"The last three {test_label.lower()} values "
                            f"({a.value:g} → {b.value:g} → {c.value:g} {c.unit}) each stepped "
                            "higher than the one before. Patterns like this are worth reviewing "
                            "with your clinician alongside the rest of your chart — this is not "
                            "a diagnosis."
                        ),
                        framing=self.FRAMING,
                    )
                )
            elif a.value > b.value > c.value:
                flags.append(
                    InsightFlag(
                        code=f"{test_code}.falling_streak",
                        severity="info",
                        title=f"{test_label} has fallen across the last three results",
                        explanation=(
                            f"The last three {test_label.lower()} values "
                            f"({a.value:g} → {b.value:g} → {c.value:g} {c.unit}) each stepped "
                            "lower than the one before. Your clinician can help put this pattern "
                            "in context with your history and medications."
                        ),
                        framing=self.FRAMING,
                    )
                )

        return flags


def build_insights_adapter() -> InsightsPort:
    return FakeInsightsAdapter()
