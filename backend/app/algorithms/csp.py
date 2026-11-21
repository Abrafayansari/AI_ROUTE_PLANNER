from __future__ import annotations

import math
import time

from app.utils.metrics import minutes_to_time, time_to_minutes


def _intervals_overlap(a_start: int, a_end: int, b_start: int, b_end: int) -> bool:
    return a_start < b_end and b_start < a_end


def run_csp_scheduler(distributors: list[dict], config: dict) -> dict:
    """
    Week 5: Constraint Satisfaction Problem (CSP) Visit Scheduler.
    Uses unary domain filtering + backtracking with forward checking + MRV/priority ordering.
    Hard constraints:
      1. Officer working hours
      2. Distributor opening/closing windows
      3. Mandatory lunch break interval (if enabled)
      4. Non-overlapping visits + directed road travel times (or fixed fallback buffer)
      5. Maximum visits per day
    Never violates hard constraints for priority; reports exact failure reasons for unscheduled stops.
    """
    start_t = time.perf_counter()
    work_start = time_to_minutes(config["workStartTime"])
    work_end = time_to_minutes(config["workEndTime"])
    increment = max(5, int(config.get("slotIncrementMinutes", 15)))
    buffer_min = max(0, int(config.get("travelBufferMinutes", 15)))
    lunch_enabled = bool(config.get("lunchBreakEnabled", True))
    lunch_start = time_to_minutes(config.get("lunchStartTime", "12:30"))
    lunch_duration = int(config.get("lunchDurationMinutes", 60))
    lunch_end = lunch_start + lunch_duration
    max_visits = max(1, int(config.get("maxVisitsPerDay", 10)))

    travel_matrix: dict[str, dict[str, float]] | None = config.get("travelTimesMatrix")
    office_travel_map: dict[str, float] = config.get("officeToDistributorMinutes") or {}
    distance_matrix: dict[str, dict[str, float]] | None = config.get("distanceKmMatrix")
    office_distance_map: dict[str, float] = config.get("officeToDistributorKm") or {}
    uses_fixed_buffer = not bool(travel_matrix)
    data_source = str(config.get("dataSource") or "simulated_fallback")

    if work_end <= work_start:
        raise ValueError("Work end time must be strictly after work start time.")

    def _travel_between(from_id: str, to_id: str) -> int:
        if travel_matrix and from_id in travel_matrix and to_id in travel_matrix[from_id]:
            return max(buffer_min if config.get("enforceMinimumBuffer", False) else 0, int(math.ceil(float(travel_matrix[from_id][to_id]))))
        return buffer_min

    variables: list[tuple[dict, list[int]]] = []
    unary_rejected: dict[str, dict] = {}

    for dist in distributors:
        open_min = time_to_minutes(dist["openingTime"])
        close_min = time_to_minutes(dist["closingTime"])
        dur = int(dist["visitDurationMinutes"])

        earliest_start = max(work_start, open_min)
        latest_start = min(work_end - dur, close_min - dur)

        if latest_start < earliest_start:
            unary_rejected[dist["id"]] = {
                "distributorId": dist["id"],
                "distributorName": dist["name"],
                "priority": int(dist["priority"]),
                "visitDurationMinutes": dur,
                "openingTime": dist["openingTime"],
                "closingTime": dist["closingTime"],
                "reason": (
                    f"Does not fit within opening hours ({dist['openingTime']}–{dist['closingTime']}) "
                    f"and working hours ({config['workStartTime']}–{config['workEndTime']}) for a {dur}m visit."
                ),
            }
            continue

        domain: list[int] = []
        blocked_by_lunch_only = False
        t = work_start
        while t <= latest_start:
            if t >= earliest_start:
                t_end = t + dur
                if lunch_enabled and _intervals_overlap(t, t_end, lunch_start, lunch_end):
                    blocked_by_lunch_only = True
                else:
                    domain.append(t)
            t += increment

        if not domain:
            reason = (
                f"Conflicts with mandatory lunch break ({config.get('lunchStartTime', '12:30')}, {lunch_duration}m) within opening window."
                if blocked_by_lunch_only
                else "No valid time slot matches slot increment and opening hours."
            )
            unary_rejected[dist["id"]] = {
                "distributorId": dist["id"],
                "distributorName": dist["name"],
                "priority": int(dist["priority"]),
                "visitDurationMinutes": dur,
                "openingTime": dist["openingTime"],
                "closingTime": dist["closingTime"],
                "reason": reason,
            }
            continue

        variables.append((dist, domain))

    # MRV (smallest domain first), then highest priority, then earliest closing time
    variables.sort(
        key=lambda item: (
            len(item[1]),
            -int(item[0]["priority"]),
            time_to_minutes(item[0]["closingTime"]),
        )
    )

    best_assignment: list[tuple[dict, int, int]] = []
    best_priority_sum = -1
    backtracks = 0
    found_complete = False
    max_steps = 25_000
    steps = 0

    def is_pair_compatible(
        id_a: str, start_a: int, end_a: int, id_b: str, start_b: int, end_b: int
    ) -> bool:
        if _intervals_overlap(start_a, end_a, start_b, end_b):
            return False
        if end_a <= start_b:
            return end_a + _travel_between(id_a, id_b) <= start_b
        return end_b + _travel_between(id_b, id_a) <= start_a

    def is_conflict_free(
        placed: list[tuple[dict, int, int]],
        cand_id: str,
        start_min: int,
        dur_min: int,
    ) -> bool:
        end_min = start_min + dur_min
        for p_dist, p_start, p_end in placed:
            if not is_pair_compatible(p_dist["id"], p_start, p_end, cand_id, start_min, end_min):
                return False
        return True

    def backtrack(
        var_idx: int,
        placed: list[tuple[dict, int, int]],
        priority_sum: int,
        remaining_domains: list[list[int]],
    ) -> None:
        nonlocal best_assignment, best_priority_sum, backtracks, found_complete, steps
        if found_complete or steps > max_steps:
            return
        steps += 1

        if len(placed) > len(best_assignment) or (
            len(placed) == len(best_assignment) and priority_sum > best_priority_sum
        ):
            best_assignment = list(placed)
            best_priority_sum = priority_sum

        if len(placed) == min(len(variables), max_visits):
            found_complete = True
            return

        if var_idx >= len(variables):
            return

        max_possible_count = min(max_visits, len(placed) + (len(variables) - var_idx))
        if max_possible_count < len(best_assignment):
            return

        current_dist, _ = variables[var_idx]
        cur_id = current_dist["id"]
        cur_dur = int(current_dist["visitDurationMinutes"])
        cur_prio = int(current_dist["priority"])
        domain = remaining_domains[var_idx]

        for slot in domain:
            if not is_conflict_free(placed, cur_id, slot, cur_dur):
                continue

            next_end = slot + cur_dur
            next_placed = placed + [(current_dist, slot, next_end)]

            # Forward checking using directed O-D travel times (or fixed buffer)
            next_domains: list[list[int]] = []
            for idx, dom in enumerate(remaining_domains):
                if idx <= var_idx:
                    next_domains.append(dom)
                else:
                    future_dist = variables[idx][0]
                    future_id = future_dist["id"]
                    future_dur = int(future_dist["visitDurationMinutes"])
                    next_domains.append(
                        [
                            t
                            for t in dom
                            if is_pair_compatible(
                                cur_id, slot, next_end, future_id, t, t + future_dur
                            )
                        ]
                    )

            backtrack(var_idx + 1, next_placed, priority_sum + cur_prio, next_domains)
            if found_complete:
                return

        backtracks += 1
        backtrack(var_idx + 1, placed, priority_sum, remaining_domains)

    if variables:
        backtrack(0, [], 0, [dom for _, dom in variables])

    best_assignment.sort(key=lambda item: item[1])
    scheduled_ids = {item[0]["id"] for item in best_assignment}

    scheduled: list[dict] = []
    for idx, (dist, start_min, end_min) in enumerate(best_assignment):
        did = dist["id"]
        if idx == 0:
            travel_prev = (
                int(math.ceil(float(office_travel_map[did])))
                if did in office_travel_map
                else buffer_min
            )
            dist_prev = (
                round(float(office_distance_map[did]), 2)
                if did in office_distance_map
                else None
            )
        else:
            prev_did = best_assignment[idx - 1][0]["id"]
            travel_prev = _travel_between(prev_did, did)
            dist_prev = (
                round(float(distance_matrix[prev_did][did]), 2)
                if (distance_matrix and prev_did in distance_matrix and did in distance_matrix[prev_did])
                else None
            )

        scheduled.append(
            {
                "distributorId": did,
                "distributorName": dist["name"],
                "priority": int(dist["priority"]),
                "startTime": minutes_to_time(start_min),
                "endTime": minutes_to_time(end_min),
                "startMinutes": start_min,
                "endMinutes": end_min,
                "durationMinutes": int(dist["visitDurationMinutes"]),
                "bufferMinutes": travel_prev,
                "travelMinutesFromPrevious": travel_prev,
                "distanceKm": dist_prev,
                "openingTime": dist["openingTime"],
                "closingTime": dist["closingTime"],
            }
        )

    unscheduled: list[dict] = []
    for dist in distributors:
        if dist["id"] in scheduled_ids:
            continue
        unary = unary_rejected.get(dist["id"])
        if unary:
            unscheduled.append(unary)
        elif len(scheduled) >= max_visits:
            unscheduled.append(
                {
                    "distributorId": dist["id"],
                    "distributorName": dist["name"],
                    "priority": int(dist["priority"]),
                    "visitDurationMinutes": int(dist["visitDurationMinutes"]),
                    "openingTime": dist["openingTime"],
                    "closingTime": dist["closingTime"],
                    "reason": f"Maximum daily visit cap ({max_visits}) reached by higher-priority or tighter-window visits.",
                }
            )
        else:
            travel_desc = (
                "directed road travel times"
                if not uses_fixed_buffer
                else f"{buffer_min}m travel buffers"
            )
            unscheduled.append(
                {
                    "distributorId": dist["id"],
                    "distributorName": dist["name"],
                    "priority": int(dist["priority"]),
                    "visitDurationMinutes": int(dist["visitDurationMinutes"]),
                    "openingTime": dist["openingTime"],
                    "closingTime": dist["closingTime"],
                    "reason": f"No non-overlapping slot remains within working hours ({config['workStartTime']}–{config['workEndTime']}) after accounting for {travel_desc}.",
                }
            )

    lunch_note = (
        f" · Lunch {config.get('lunchStartTime', '12:30')} ({lunch_duration}m)"
        if lunch_enabled
        else ""
    )
    travel_mode_note = (
        f"Road travel times ({data_source})"
        if not uses_fixed_buffer
        else f"Fixed {buffer_min}m travel buffer"
    )

    return {
        "allDistributorsScheduled": len(unscheduled) == 0,
        "usesFixedTravelBuffer": uses_fixed_buffer,
        "dataSource": data_source,
        "scheduled": scheduled,
        "unscheduled": unscheduled,
        "backtracks": backtracks,
        "executionTimeMs": round((time.perf_counter() - start_t) * 1000.0, 3),
        "constraintsSummary": (
            f"CSP Backtracking + Forward Checking · Working hours {config['workStartTime']}–{config['workEndTime']} "
            f"· {travel_mode_note}{lunch_note} · Max {max_visits} visits/day."
        ),
    }
