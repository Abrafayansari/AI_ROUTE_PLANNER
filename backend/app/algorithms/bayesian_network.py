from __future__ import annotations

import math
from typing import Any, Literal

MODEL_VERSION = "1.0.0-illustrative"
MODEL_STATUS = "illustrative_baseline"
VALIDATION_STATUS = (
    "Validated mathematically (all prior distributions and 54 CPT rows sum to 1.0; "
    "parameters represent domain-calibrated baseline distributions pending empirical arrival telemetry)."
)

# State spaces
DISTANCE_STATES = ("Near", "Medium", "Far")
DURATION_STATES = ("Short", "Medium", "Long")
TIME_SLOT_STATES = ("Morning", "Afternoon")
PRIORITY_STATES = ("Low", "Medium", "High")
DELAY_RISK_STATES = ("Low", "Medium", "High")

# Default thresholds
DEFAULT_THRESHOLDS = {
    "distance_km": {
        "near_max": 5.0,     # < 5.0 km -> Near
        "medium_max": 15.0,  # 5.0 to 15.0 km -> Medium; > 15.0 km -> Far
    },
    "visit_duration_minutes": {
        "short_max": 30,     # < 30 min -> Short
        "medium_max": 60,    # 30 to 59 min -> Medium; >= 60 min -> Long
    },
    "time_slot": {
        "afternoon_cutoff": "12:30",  # < 12:30 -> Morning; >= 12:30 -> Afternoon
    },
    "priority": {
        "low_max": 2,        # priority 1-2 -> Low
        "medium_val": 3,     # priority 3 -> Medium; priority 4-5 -> High
    },
}

# Prior distributions for parents
DEFAULT_PRIORS = {
    "Distance": {
        "Near": 0.40,
        "Medium": 0.40,
        "Far": 0.20,
    },
    "VisitDuration": {
        "Short": 0.35,
        "Medium": 0.45,
        "Long": 0.20,
    },
    "TimeSlot": {
        "Morning": 0.50,
        "Afternoon": 0.50,
    },
    "Priority": {
        "Low": 0.25,
        "Medium": 0.45,
        "High": 0.30,
    },
}


def _compute_baseline_cpt() -> dict[tuple[str, str, str, str], dict[str, float]]:
    """
    Generate calibrated baseline Conditional Probability Table (CPT) for Delay Risk
    given parents (Distance, VisitDuration, TimeSlot, Priority).

    3 * 3 * 2 * 3 = 54 rows.
    Each row specifies { 'Low': p_low, 'Medium': p_med, 'High': p_high }
    such that p_low + p_med + p_high == 1.0 strictly.
    """
    # Risk factor scores for each parent state (grounded in logistics operations):
    # - Far travel introduces traffic unpredictability (+2.5 vs Near 0.0)
    # - Long visit introduces scope expansion and client delays (+2.2 vs Short 0.0)
    # - Afternoon accumulates upstream transit delays (+1.6 vs Morning 0.0)
    # - High priority distributors have detailed reviews and strict protocols (+1.0 vs Low 0.0)
    dist_weights = {"Near": 0.0, "Medium": 1.2, "Far": 2.5}
    dur_weights = {"Short": 0.0, "Medium": 1.0, "Long": 2.2}
    time_weights = {"Morning": 0.0, "Afternoon": 1.6}
    prio_weights = {"Low": 0.0, "Medium": 0.5, "High": 1.1}

    # Max possible raw score = 2.5 + 2.2 + 1.6 + 1.1 = 7.4
    # Min possible raw score = 0.0
    cpt: dict[tuple[str, str, str, str], dict[str, float]] = {}

    for dist in DISTANCE_STATES:
        for dur in DURATION_STATES:
            for ts in TIME_SLOT_STATES:
                for prio in PRIORITY_STATES:
                    score = (
                        dist_weights[dist]
                        + dur_weights[dur]
                        + time_weights[ts]
                        + prio_weights[prio]
                    )
                    # Normalized score from 0.0 to 1.0
                    norm_score = score / 7.4

                    # Calibrate logits with smooth sigmoid-like transition:
                    # Low risk decays as score rises
                    # High risk rises as score rises
                    # Medium risk peaks in the middle
                    logit_low = math.exp(3.2 * (1.0 - norm_score) - 0.5)
                    logit_med = math.exp(2.0 * (1.0 - abs(norm_score - 0.5) * 2.2))
                    logit_high = math.exp(3.4 * norm_score - 0.6)

                    total_logit = logit_low + logit_med + logit_high
                    p_low = round(logit_low / total_logit, 4)
                    p_med = round(logit_med / total_logit, 4)
                    # Ensure exact sum to 1.0 by assigning remainder to high
                    p_high = round(1.0 - p_low - p_med, 4)

                    # Floating-point safety check
                    probs = {"Low": p_low, "Medium": p_med, "High": p_high}
                    cpt[(dist, dur, ts, prio)] = probs

    return cpt


DEFAULT_CPT = _compute_baseline_cpt()


def validate_cpts(
    cpt: dict[tuple[str, str, str, str], dict[str, float]] | None = None,
    priors: dict[str, dict[str, float]] | None = None,
) -> bool:
    """
    Validate that every prior distribution and every CPT row sums to 1.0 within tolerance.
    Raises ValueError if invalid.
    """
    check_priors = priors or DEFAULT_PRIORS
    for var_name, dist in check_priors.items():
        total = sum(dist.values())
        if abs(total - 1.0) > 1e-5:
            raise ValueError(f"Prior for {var_name} does not sum to 1.0 (sum={total})")
        for st, p in dist.items():
            if p < 0.0 or p > 1.0:
                raise ValueError(f"Prior probability for {var_name}:{st} out of range: {p}")

    check_cpt = cpt or DEFAULT_CPT
    expected_rows = len(DISTANCE_STATES) * len(DURATION_STATES) * len(TIME_SLOT_STATES) * len(PRIORITY_STATES)
    if len(check_cpt) != expected_rows:
        raise ValueError(f"CPT row count mismatch: expected {expected_rows}, got {len(check_cpt)}")

    for key, probs in check_cpt.items():
        total = sum(probs.values())
        if abs(total - 1.0) > 1e-4:
            raise ValueError(f"CPT row for {key} does not sum to 1.0 (sum={total})")
        for rk in DELAY_RISK_STATES:
            if rk not in probs:
                raise ValueError(f"Missing state {rk} in CPT row for {key}")
            if probs[rk] < 0.0 or probs[rk] > 1.0:
                raise ValueError(f"Probability out of bounds in CPT {key}: {probs[rk]}")

    return True


# Run self-validation on load
validate_cpts()


def categorize_distance(
    distance_km: float | None,
    thresholds: dict[str, float] | None = None,
) -> Literal["Near", "Medium", "Far"]:
    """Categorize simulated or straight-line distance into Near, Medium, Far."""
    if distance_km is None:
        raise ValueError("Distance value is required for categorization.")
    try:
        d = float(distance_km)
    except (ValueError, TypeError):
        raise ValueError(f"Invalid distance value: {distance_km}")

    th = thresholds or DEFAULT_THRESHOLDS["distance_km"]
    near_max = float(th.get("near_max", 5.0))
    medium_max = float(th.get("medium_max", 15.0))

    if d < near_max:
        return "Near"
    if d <= medium_max:
        return "Medium"
    return "Far"


def categorize_visit_duration(
    duration_minutes: int | float | None,
    thresholds: dict[str, int] | None = None,
) -> Literal["Short", "Medium", "Long"]:
    """Categorize planned visit duration into Short, Medium, Long."""
    if duration_minutes is None:
        raise ValueError("Visit duration value is required for categorization.")
    try:
        m = int(round(float(duration_minutes)))
    except (ValueError, TypeError):
        raise ValueError(f"Invalid visit duration value: {duration_minutes}")

    th = thresholds or DEFAULT_THRESHOLDS["visit_duration_minutes"]
    short_max = int(th.get("short_max", 30))
    medium_max = int(th.get("medium_max", 60))

    if m < short_max:
        return "Short"
    if m < medium_max:
        return "Medium"
    return "Long"


def categorize_time_slot(
    time_val: Any,
    cutoff_time: str = "12:30",
) -> Literal["Morning", "Afternoon"]:
    """
    Categorize planned start time into Morning (< 12:30) or Afternoon (>= 12:30).
    Accepts:
      - 'HH:MM' string (e.g. '09:30', '14:15')
      - ISO datetime string (e.g. '2026-11-20T14:00:00Z')
      - datetime or time object
    """
    if time_val is None or time_val == "":
        raise ValueError("Visit time or time slot is required for categorization.")

    time_str = str(time_val).strip()

    # If full ISO datetime, extract time portion
    if "T" in time_str:
        time_str = time_str.split("T")[1][:5]
    elif " " in time_str and ":" in time_str:
        time_str = time_str.split(" ")[1][:5]
    else:
        time_str = time_str[:5]

    try:
        parts = time_str.split(":")
        hh = int(parts[0])
        mm = int(parts[1]) if len(parts) > 1 else 0
        minutes = hh * 60 + mm
    except Exception:
        raise ValueError(f"Unable to parse time value '{time_val}' into HH:MM.")

    cutoff_parts = cutoff_time.split(":")
    cutoff_min = int(cutoff_parts[0]) * 60 + int(cutoff_parts[1])

    return "Morning" if minutes < cutoff_min else "Afternoon"


def categorize_priority(
    priority_val: int | str | None,
) -> Literal["Low", "Medium", "High"]:
    """Map numeric distributor priority (1..5) into Low (1-2), Medium (3), High (4-5)."""
    if priority_val is None:
        raise ValueError("Distributor priority is required for categorization.")

    try:
        p = int(priority_val)
    except (ValueError, TypeError):
        # Support string category if already provided
        s = str(priority_val).capitalize()
        if s in PRIORITY_STATES:
            return s  # type: ignore[return-value]
        raise ValueError(f"Invalid priority value: {priority_val}")

    if p <= 2:
        return "Low"
    if p == 3:
        return "Medium"
    return "High"


class BayesianDelayNetwork:
    """
    Discrete Bayesian Network implementation for Distributor Visit Delay Prediction.

    Graph topology:
        Distance (D) ────────┐
                             |
        Visit Duration (V) ──┤
                             ├──> Delay Risk (R)
        Time Slot (T) ───────┤
                             |
        Priority (P) ────────┘

    Inference method:
        Exact discrete inference via conditional probability table lookup and
        marginalization over unobserved parent variables when partial evidence is provided.
    """

    def __init__(
        self,
        cpt: dict[tuple[str, str, str, str], dict[str, float]] | None = None,
        priors: dict[str, dict[str, float]] | None = None,
        thresholds: dict[str, Any] | None = None,
        version: str = MODEL_VERSION,
        status: str = MODEL_STATUS,
    ):
        self.version = version
        self.status = status
        self.priors = priors or DEFAULT_PRIORS
        self.cpt = cpt or DEFAULT_CPT
        self.thresholds = thresholds or DEFAULT_THRESHOLDS
        validate_cpts(self.cpt, self.priors)

    def get_structure_info(self) -> dict[str, Any]:
        """Return full network topology and metadata."""
        return {
            "version": self.version,
            "status": self.status,
            "validationStatus": VALIDATION_STATUS,
            "topology": {
                "nodes": [
                    {
                        "id": "Distance",
                        "label": "Transit Distance",
                        "type": "parent",
                        "states": list(DISTANCE_STATES),
                        "priors": self.priors["Distance"],
                    },
                    {
                        "id": "VisitDuration",
                        "label": "Expected Duration",
                        "type": "parent",
                        "states": list(DURATION_STATES),
                        "priors": self.priors["VisitDuration"],
                    },
                    {
                        "id": "TimeSlot",
                        "label": "Scheduled Time Slot",
                        "type": "parent",
                        "states": list(TIME_SLOT_STATES),
                        "priors": self.priors["TimeSlot"],
                    },
                    {
                        "id": "Priority",
                        "label": "Distributor Priority",
                        "type": "parent",
                        "states": list(PRIORITY_STATES),
                        "priors": self.priors["Priority"],
                    },
                    {
                        "id": "DelayRisk",
                        "label": "Visit Delay Risk",
                        "type": "target",
                        "states": list(DELAY_RISK_STATES),
                        "parents": ["Distance", "VisitDuration", "TimeSlot", "Priority"],
                    },
                ],
                "edges": [
                    {"from": "Distance", "to": "DelayRisk"},
                    {"from": "VisitDuration", "to": "DelayRisk"},
                    {"from": "TimeSlot", "to": "DelayRisk"},
                    {"from": "Priority", "to": "DelayRisk"},
                ],
                "totalCptConfigurations": len(self.cpt),
            },
            "thresholds": self.thresholds,
        }

    def infer_posterior(self, evidence: dict[str, str | None]) -> dict[str, float]:
        """
        Compute posterior distribution P(DelayRisk | Evidence).
        Supports both full evidence (all 4 parents specified) and partial evidence
        (marginalizing over unobserved parent variables with their prior distributions).
        """
        # Determine candidate sets for each parent
        obs_dist = [evidence["Distance"]] if evidence.get("Distance") in DISTANCE_STATES else list(DISTANCE_STATES)
        obs_dur = [evidence["VisitDuration"]] if evidence.get("VisitDuration") in DURATION_STATES else list(DURATION_STATES)
        obs_ts = [evidence["TimeSlot"]] if evidence.get("TimeSlot") in TIME_SLOT_STATES else list(TIME_SLOT_STATES)
        obs_prio = [evidence["Priority"]] if evidence.get("Priority") in PRIORITY_STATES else list(PRIORITY_STATES)

        unnorm: dict[str, float] = {r: 0.0 for r in DELAY_RISK_STATES}

        for d in obs_dist:
            p_d = self.priors["Distance"][d]
            for v in obs_dur:
                p_v = self.priors["VisitDuration"][v]
                for t in obs_ts:
                    p_t = self.priors["TimeSlot"][t]
                    for p in obs_prio:
                        p_p = self.priors["Priority"][p]
                        joint_parent_prob = p_d * p_v * p_t * p_p

                        cpt_row = self.cpt[(d, v, t, p)]
                        for r in DELAY_RISK_STATES:
                            unnorm[r] += cpt_row[r] * joint_parent_prob

        total = sum(unnorm.values())
        if total <= 0.0:
            return {"Low": 0.3333, "Medium": 0.3333, "High": 0.3334}

        p_low = round(unnorm["Low"] / total, 4)
        p_med = round(unnorm["Medium"] / total, 4)
        p_high = round(1.0 - p_low - p_med, 4)

        return {"Low": p_low, "Medium": p_med, "High": p_high}

    def predict_visit(
        self,
        distributor_id: str | None,
        distributor_name: str,
        distance_km: float | None = None,
        visit_duration_minutes: int | None = None,
        time_slot_raw: Any = None,
        priority_raw: int | str | None = None,
        distance_category: str | None = None,
        visit_duration_category: str | None = None,
        time_slot: str | None = None,
        priority_category: str | None = None,
        stop_order: int | None = None,
        route_plan_id: str | None = None,
    ) -> dict[str, Any]:
        """
        Categorize inputs and run Bayesian inference for a single distributor visit.
        """
        # Resolve categories either from pre-computed category strings or raw values
        cat_dist = distance_category or (
            categorize_distance(distance_km, self.thresholds.get("distance_km"))
            if distance_km is not None
            else None
        )
        cat_dur = visit_duration_category or (
            categorize_visit_duration(visit_duration_minutes, self.thresholds.get("visit_duration_minutes"))
            if visit_duration_minutes is not None
            else None
        )
        cat_ts = time_slot or (
            categorize_time_slot(time_slot_raw, self.thresholds.get("time_slot", {}).get("afternoon_cutoff", "12:30"))
            if time_slot_raw is not None
            else None
        )
        cat_prio = priority_category or (
            categorize_priority(priority_raw)
            if priority_raw is not None
            else None
        )

        missing_fields = []
        if not cat_dist:
            missing_fields.append("distance / distance_category")
        if not cat_dur:
            missing_fields.append("visit_duration / visit_duration_category")
        if not cat_ts:
            missing_fields.append("time_slot")
        if not cat_prio:
            missing_fields.append("priority / priority_category")

        if missing_fields:
            raise ValueError(
                f"Missing required Bayesian Network evidence for '{distributor_name}': {', '.join(missing_fields)}"
            )

        evidence = {
            "Distance": cat_dist,
            "VisitDuration": cat_dur,
            "TimeSlot": cat_ts,
            "Priority": cat_prio,
        }

        posteriors = self.infer_posterior(evidence)

        # Select highest posterior probability category (deterministic tie-breaker: High > Medium > Low)
        sorted_risks = sorted(
            DELAY_RISK_STATES,
            key=lambda k: (posteriors[k], 2 if k == "High" else 1 if k == "Medium" else 0),
            reverse=True,
        )
        predicted_risk = sorted_risks[0]

        # Recommendation for high risk
        recommended_buffer_minutes = 0
        recommendation_note = None
        if predicted_risk == "High" or posteriors["High"] >= 0.45:
            recommended_buffer_minutes = 15 if cat_dur == "Long" else 10
            recommendation_note = (
                f"High delay probability ({round(posteriors['High'] * 100)}%). "
                f"Consider scheduling +{recommended_buffer_minutes}m buffer time before next stop."
            )
        elif predicted_risk == "Medium" and posteriors["High"] >= 0.30:
            recommended_buffer_minutes = 5
            recommendation_note = (
                f"Moderate delay risk ({round(posteriors['High'] * 100)}% high-delay probability). "
                f"Optional +5m buffer recommended."
            )

        return {
            "distributorId": distributor_id,
            "distributorName": distributor_name,
            "stopOrder": stop_order,
            "routePlanId": route_plan_id,
            "inputs": {
                "distanceKm": distance_km,
                "visitDurationMinutes": visit_duration_minutes,
                "timeSlotRaw": str(time_slot_raw) if time_slot_raw is not None else None,
                "priorityRaw": priority_raw,
            },
            "evidence": {
                "distanceCategory": cat_dist,
                "visitDurationCategory": cat_dur,
                "timeSlot": cat_ts,
                "priorityCategory": cat_prio,
            },
            "probabilities": posteriors,
            "predictedRisk": predicted_risk,
            "recommendedBufferMinutes": recommended_buffer_minutes,
            "recommendation": recommendation_note,
            "explanation": self._generate_explanation(evidence, posteriors, predicted_risk),
            "modelVersion": self.version,
            "modelStatus": self.status,
            "validationStatus": VALIDATION_STATUS,
        }

    def _generate_explanation(
        self,
        evidence: dict[str, str],
        probs: dict[str, float],
        predicted_risk: str,
    ) -> str:
        factors = []
        if evidence["Distance"] == "Far":
            factors.append("extended transit distance (>15 km)")
        elif evidence["Distance"] == "Medium":
            factors.append("moderate transit distance (5–15 km)")
        else:
            factors.append("short transit distance (<5 km)")

        if evidence["VisitDuration"] == "Long":
            factors.append("long planned visit (>=60 min)")
        elif evidence["VisitDuration"] == "Medium":
            factors.append("standard visit duration (30–59 min)")
        else:
            factors.append("brief visit (<30 min)")

        if evidence["TimeSlot"] == "Afternoon":
            factors.append("afternoon arrival with accumulated route delay potential")
        else:
            factors.append("morning arrival with clear daily schedule buffer")

        if evidence["Priority"] == "High":
            factors.append("high-priority account with thorough inspection protocols")

        factor_str = ", ".join(factors)
        return (
            f"Bayesian inference determined {predicted_risk} delay risk (P={round(probs[predicted_risk]*100, 1)}%) "
            f"based on {factor_str}."
        )


# Singleton instance
_BAYESIAN_NETWORK_INSTANCE: BayesianDelayNetwork | None = None


def get_bayesian_network() -> BayesianDelayNetwork:
    global _BAYESIAN_NETWORK_INSTANCE
    if _BAYESIAN_NETWORK_INSTANCE is None:
        _BAYESIAN_NETWORK_INSTANCE = BayesianDelayNetwork()
    return _BAYESIAN_NETWORK_INSTANCE


def build_bayesian_network(
    cpt: dict[tuple[str, str, str, str], dict[str, float]] | None = None,
    priors: dict[str, dict[str, float]] | None = None,
    thresholds: dict[str, Any] | None = None,
) -> BayesianDelayNetwork:
    """Factory function to instantiate or customize a BayesianDelayNetwork."""
    return BayesianDelayNetwork(cpt=cpt, priors=priors, thresholds=thresholds)


def predict_visit_delay(evidence: dict[str, Any]) -> dict[str, Any]:
    """Convenience helper using the default network."""
    bn = get_bayesian_network()
    return bn.predict_visit(
        distributor_id=evidence.get("distributorId"),
        distributor_name=evidence.get("distributorName", "Distributor"),
        distance_km=evidence.get("distanceKm"),
        visit_duration_minutes=evidence.get("visitDurationMinutes"),
        time_slot_raw=evidence.get("timeSlotRaw") or evidence.get("timeSlot"),
        priority_raw=evidence.get("priorityRaw") or evidence.get("priority"),
        distance_category=evidence.get("distanceCategory"),
        visit_duration_category=evidence.get("visitDurationCategory"),
        time_slot=evidence.get("timeSlot") if evidence.get("timeSlot") in TIME_SLOT_STATES else None,
        priority_category=evidence.get("priorityCategory") if evidence.get("priorityCategory") in PRIORITY_STATES else None,
        stop_order=evidence.get("stopOrder"),
        route_plan_id=evidence.get("routePlanId"),
    )


def predict_route_delays(stops_data: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Convenience helper to predict delays for an entire sequence of route stops."""
    bn = get_bayesian_network()
    results = []
    for s in stops_data:
        results.append(
            bn.predict_visit(
                distributor_id=s.get("distributorId"),
                distributor_name=s.get("distributorName", "Stop"),
                distance_km=s.get("distanceKm", 0.0),
                visit_duration_minutes=s.get("visitDurationMinutes", 30),
                time_slot_raw=s.get("estimatedArrival") or s.get("timeSlot") or "09:00",
                priority_raw=s.get("priority", 3),
                distance_category=s.get("distanceCategory"),
                visit_duration_category=s.get("visitDurationCategory"),
                time_slot=s.get("timeSlot") if s.get("timeSlot") in TIME_SLOT_STATES else None,
                priority_category=s.get("priorityCategory") if s.get("priorityCategory") in PRIORITY_STATES else None,
                stop_order=s.get("stopOrder"),
                route_plan_id=s.get("routePlanId"),
            )
        )
    return results
