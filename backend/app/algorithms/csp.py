from __future__ import annotations

import math
import time

from app.utils.metrics import minutes_to_time, time_to_minutes

DEFAULT_MISSING_TRAVEL_MINUTES = 15


def _intervals_overlap(a_start: int, a_end: int, b_start: int, b_end: int) -> bool:
    return a_start < b_end and b_start < a_end


def _fractional_knapsack_upper_bound(
    items: list[tuple[int, int]],
    capacity: int,
    max_items: int,
) -> int:
    """Admissible LP-relaxation upper bound on additional priority sum."""
    if capacity <= 0 or max_items <= 0 or not items:
        return 0
    # Sort by priority-per-minute descending for fractional knapsack
    ranked = sorted(items, key=lambda item: (item[0] / max(1, item[1]), item[0]), reverse=True)
    rem_cap = float(capacity)
    total_prio = 0.0
    used_items = 0.0
    for prio, dur in ranked:
        if rem_cap <= 0 or used_items >= max_items:
            break
        d = max(1, dur)
        take_frac = min(1.0, rem_cap / d, max_items - used_items)
        total_prio += prio * take_frac
        rem_cap -= d * take_frac
        used_items += take_frac
    return int(math.floor(total_prio + 1e-9))


def run_csp_scheduler(distributors: list[dict], config: dict) -> dict:
    """
    Week 5: Constraint Satisfaction Problem (CSP) Visit Scheduler.
    Uses unary domain filtering (including office-to-first-stop travel feasibility)
    + priority-ordered Branch-and-Bound backtracking with forward checking and LCV ordering.
    Hard constraints:
      1. Officer working hours & office-to-first-stop travel time
      2. Distributor opening/closing windows
      3. Mandatory lunch break interval (if enabled)
      4. Non-overlapping visits + directed road travel times (or fixed fallback buffer)
      5. Maximum visits per day
    Optimizes (total_priority_sum, scheduled_count) without ever violating hard constraints,
    and reports exact reasons for any unscheduled distributors.
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
    uses_fixed_buffer = not bool(travel_matrix) and not bool(office_travel_map)
    data_source = str(config.get("dataSource") or "simulated_fallback")
    enforce_min_buffer = bool(config.get("enforceMinimumBuffer", False))
    road_times_expected = config.get("useRoadTravelTimes") is not False

    if work_end <= work_start:
        raise ValueError("Work end time must be strictly after work start time.")

    def _missing_travel_fallback() -> int:
        if buffer_min > 0:
            return buffer_min
        return DEFAULT_MISSING_TRAVEL_MINUTES if road_times_expected else 0

    def _travel_between(from_id: str, to_id: str) -> int:
        if travel_matrix and from_id in travel_matrix and to_id in travel_matrix[from_id]:
            raw_val = travel_matrix[from_id][to_id]
            if raw_val is not None:
                val = float(raw_val)
                if math.isfinite(val):
                    minutes = max(0, int(math.ceil(val)))
                    return max(buffer_min, minutes) if enforce_min_buffer else minutes
        return _missing_travel_fallback()

    def _office_travel_to(did: str) -> int:
        if did in office_travel_map and office_travel_map[did] is not None:
            val = float(office_travel_map[did])
            if math.isfinite(val):
                minutes = max(0, int(math.ceil(val)))
                return max(buffer_min, minutes) if enforce_min_buffer else minutes
        return _missing_travel_fallback()

    # Pass 1: Build base domains (working hours, opening window, lunch, slot increment)
    base_domains: dict[str, list[int]] = {}
    unary_rejected: dict[str, dict] = {}
    dist_by_id: dict[str, dict] = {}

    for dist in distributors:
        did = dist["id"]
        dist_by_id[did] = dist
        open_min = time_to_minutes(dist["openingTime"])
        close_min = time_to_minutes(dist["closingTime"])
        dur = int(dist["visitDurationMinutes"])

        earliest_start = max(work_start, open_min)
        latest_start = min(work_end - dur, close_min - dur)

        if latest_start < earliest_start:
            unary_rejected[did] = {
                "distributorId": did,
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
        # Include the exact earliest_start if it falls between work_start grid points
        candidate_slots: set[int] = set()
        if earliest_start <= latest_start:
            candidate_slots.add(earliest_start)
        t = work_start
        while t <= latest_start:
            if t >= earliest_start:
                candidate_slots.add(t)
            t += increment

        for slot_time in sorted(candidate_slots):
            t_end = slot_time + dur
            if lunch_enabled and _intervals_overlap(slot_time, t_end, lunch_start, lunch_end):
                blocked_by_lunch_only = True
            else:
                domain.append(slot_time)

        if not domain:
            reason = (
                f"Conflicts with mandatory lunch break ({config.get('lunchStartTime', '12:30')}, {lunch_duration}m) within opening window."
                if blocked_by_lunch_only
                else "No valid time slot matches slot increment and opening hours."
            )
            unary_rejected[did] = {
                "distributorId": did,
                "distributorName": dist["name"],
                "priority": int(dist["priority"]),
                "visitDurationMinutes": dur,
                "openingTime": dist["openingTime"],
                "closingTime": dist["closingTime"],
                "reason": reason,
            }
            continue

        base_domains[did] = domain

    # Pass 2: Filter slots unreachable from office (either directly or via any feasible predecessor)
    variables: list[tuple[dict, list[int]]] = []
    for dist in distributors:
        did = dist["id"]
        if did not in base_domains:
            continue

        office_travel = _office_travel_to(did)
        direct_arrival = work_start + office_travel

        earliest_via_other = direct_arrival
        for other_id, other_dom in base_domains.items():
            if other_id == did:
                continue
            other_office_arrival = work_start + _office_travel_to(other_id)
            valid_other_starts = [s for s in other_dom if s >= other_office_arrival]
            if not valid_other_starts:
                continue
            other_dur = int(dist_by_id[other_id]["visitDurationMinutes"])
            via_arrival = valid_other_starts[0] + other_dur + _travel_between(other_id, did)
            if via_arrival < earliest_via_other:
                earliest_via_other = via_arrival

        filtered_domain = [t for t in base_domains[did] if t >= earliest_via_other]
        if not filtered_domain:
            dur = int(dist["visitDurationMinutes"])
            earliest_reach_str = minutes_to_time(direct_arrival)
            unary_rejected[did] = {
                "distributorId": did,
                "distributorName": dist["name"],
                "priority": int(dist["priority"]),
                "visitDurationMinutes": dur,
                "openingTime": dist["openingTime"],
                "closingTime": dist["closingTime"],
                "reason": (
                    f"Cannot be reached from office after {office_travel}m travel (arrives {earliest_reach_str}) "
                    f"to complete a {dur}m visit within opening hours ({dist['openingTime']}–{dist['closingTime']}) "
                    f"and working hours ({config['workStartTime']}–{config['workEndTime']})."
                ),
            }
            continue

        variables.append((dist, filtered_domain))

    # Priority-first ordering, then MRV (smallest domain first), then earliest closing time
    variables.sort(
        key=lambda item: (
            -int(item[0]["priority"]),
            len(item[1]),
            time_to_minutes(item[0]["closingTime"]),
            int(item[0]["visitDurationMinutes"]),
        )
    )

    best_assignment: list[tuple[dict, int, int]] = []
    best_priority_sum = -1
    backtracks = 0
    found_optimal = False
    max_steps = 40_000
    steps = 0

    lunch_overlap = (
        max(0, min(work_end, lunch_end) - max(work_start, lunch_start))
        if lunch_enabled
        else 0
    )
    total_visit_budget = (work_end - work_start) - lunch_overlap
    global_max_count = min(len(variables), max_visits)
    global_max_priority = sum(int(variables[i][0]["priority"]) for i in range(global_max_count))

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

    def is_schedule_office_feasible(placed: list[tuple[dict, int, int]]) -> bool:
        if not placed:
            return True
        earliest_dist, earliest_start, _ = min(placed, key=lambda item: item[1])
        return earliest_start >= work_start + _office_travel_to(earliest_dist["id"])

    def can_slot_be_first_or_preceded(
        placed: list[tuple[dict, int, int]],
        var_idx: int,
        cur_id: str,
        slot: int,
        remaining_domains: list[list[int]],
    ) -> bool:
        if slot >= work_start + _office_travel_to(cur_id):
            return True
        for p_dist, _, p_end in placed:
            if p_end + _travel_between(p_dist["id"], cur_id) <= slot:
                return True
        for idx in range(var_idx + 1, len(variables)):
            f_dist = variables[idx][0]
            f_id = f_dist["id"]
            f_dur = int(f_dist["visitDurationMinutes"])
            needed = _travel_between(f_id, cur_id)
            for ft in remaining_domains[idx]:
                if ft + f_dur + needed <= slot:
                    return True
        return False

    def order_candidate_slots(
        var_idx: int,
        placed: list[tuple[dict, int, int]],
        remaining_domains: list[list[int]],
    ) -> list[tuple[int, list[list[int]]]]:
        current_dist = variables[var_idx][0]
        cur_id = current_dist["id"]
        cur_dur = int(current_dist["visitDurationMinutes"])
        slots_left_after = max_visits - len(placed) - 1

        candidates: list[tuple[int, int, int, list[list[int]]]] = []
        for slot in remaining_domains[var_idx]:
            if not is_conflict_free(placed, cur_id, slot, cur_dur):
                continue
            if not can_slot_be_first_or_preceded(placed, var_idx, cur_id, slot, remaining_domains):
                continue

            next_end = slot + cur_dur
            next_domains: list[list[int]] = []
            alive_priorities: list[int] = []
            alive_slots = 0

            for idx, dom in enumerate(remaining_domains):
                if idx <= var_idx:
                    next_domains.append(dom)
                else:
                    future_dist = variables[idx][0]
                    future_id = future_dist["id"]
                    future_dur = int(future_dist["visitDurationMinutes"])
                    filtered = [
                        t
                        for t in dom
                        if is_pair_compatible(
                            cur_id, slot, next_end, future_id, t, t + future_dur
                        )
                    ]
                    next_domains.append(filtered)
                    if filtered:
                        alive_priorities.append(int(future_dist["priority"]))
                        alive_slots += len(filtered)

            future_prio_bound = (
                sum(alive_priorities[:slots_left_after])
                if slots_left_after > 0
                else 0
            )
            candidates.append((-future_prio_bound, slot, -alive_slots, next_domains))

        candidates.sort(key=lambda item: (item[0], item[1], item[2]))
        return [(item[1], item[3]) for item in candidates]

    # Greedy priority-first warm start to seed best_assignment immediately
    if variables:
        greedy_placed: list[tuple[dict, int, int]] = []
        greedy_prio = 0
        greedy_domains = [list(dom) for _, dom in variables]
        for v_idx in range(len(variables)):
            if len(greedy_placed) >= max_visits:
                break
            if not greedy_domains[v_idx]:
                continue
            cand_dist = variables[v_idx][0]
            cand_dur = int(cand_dist["visitDurationMinutes"])
            cand_prio = int(cand_dist["priority"])
            ordered = order_candidate_slots(v_idx, greedy_placed, greedy_domains)
            for slot, next_doms in ordered:
                trial_placed = greedy_placed + [(cand_dist, slot, slot + cand_dur)]
                # Only commit greedy step if it keeps the partial schedule office-feasible
                # (or has a clear feasible predecessor already placed).
                if is_schedule_office_feasible(trial_placed):
                    greedy_placed = trial_placed
                    greedy_prio += cand_prio
                    greedy_domains = next_doms
                    break

        if greedy_placed and is_schedule_office_feasible(greedy_placed):
            best_assignment = greedy_placed
            best_priority_sum = greedy_prio
            if (
                best_priority_sum == global_max_priority
                and len(best_assignment) == global_max_count
            ):
                found_optimal = True

    def backtrack(
        var_idx: int,
        placed: list[tuple[dict, int, int]],
        priority_sum: int,
        remaining_domains: list[list[int]],
    ) -> None:
        nonlocal best_assignment, best_priority_sum, backtracks, found_optimal, steps
        if found_optimal or steps > max_steps:
            return
        steps += 1

        if is_schedule_office_feasible(placed):
            if priority_sum > best_priority_sum or (
                priority_sum == best_priority_sum and len(placed) > len(best_assignment)
            ):
                best_assignment = list(placed)
                best_priority_sum = priority_sum
                if (
                    best_priority_sum == global_max_priority
                    and len(best_assignment) == global_max_count
                ):
                    found_optimal = True
                    return

        slots_left = max_visits - len(placed)
        if slots_left <= 0 or var_idx >= len(variables):
            return

        rem_active = [
            (int(variables[idx][0]["priority"]), int(variables[idx][0]["visitDurationMinutes"]))
            for idx in range(var_idx, len(variables))
            if remaining_domains[idx]
        ]
        if not rem_active:
            return

        used_visit_minutes = sum(p_end - p_start for _, p_start, p_end in placed)
        rem_visit_budget = total_visit_budget - used_visit_minutes
        top_count_bound = sum(p for p, _ in rem_active[:slots_left])
        dur_bound = _fractional_knapsack_upper_bound(rem_active, rem_visit_budget, slots_left)
        max_possible_prio = priority_sum + min(top_count_bound, dur_bound)
        max_possible_count = len(placed) + min(slots_left, len(rem_active))

        if max_possible_prio < best_priority_sum or (
            max_possible_prio == best_priority_sum and max_possible_count <= len(best_assignment)
        ):
            return

        current_dist, _ = variables[var_idx]
        cur_dur = int(current_dist["visitDurationMinutes"])
        cur_prio = int(current_dist["priority"])

        ordered_slots = order_candidate_slots(var_idx, placed, remaining_domains)
        for slot, next_domains in ordered_slots:
            next_end = slot + cur_dur
            next_placed = placed + [(current_dist, slot, next_end)]
            backtrack(var_idx + 1, next_placed, priority_sum + cur_prio, next_domains)
            if found_optimal:
                return

        if ordered_slots:
            backtracks += 1
        backtrack(var_idx + 1, placed, priority_sum, remaining_domains)

    if variables and not found_optimal:
        backtrack(0, [], 0, [dom for _, dom in variables])

    best_assignment.sort(key=lambda item: item[1])
    scheduled_ids = {item[0]["id"] for item in best_assignment}

    scheduled: list[dict] = []
    for idx, (dist, start_min, end_min) in enumerate(best_assignment):
        did = dist["id"]
        if idx == 0:
            travel_prev = _office_travel_to(did)
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
    scheduled_prios = [int(s["priority"]) for s in scheduled]
    min_scheduled_prio = min(scheduled_prios) if scheduled_prios else 0
    for dist in distributors:
        did = dist["id"]
        if did in scheduled_ids:
            continue
        unary = unary_rejected.get(did)
        if unary:
            unscheduled.append(unary)
            continue

        dist_prio = int(dist["priority"])
        travel_desc = (
            "directed road travel times (including office travel)"
            if not uses_fixed_buffer
            else f"{_missing_travel_fallback()}m travel buffers (including office travel)"
        )
        if len(scheduled) >= max_visits:
            if dist_prio <= min_scheduled_prio:
                reason = (
                    f"Maximum daily visit cap ({max_visits}) reached by equal or higher-priority visits."
                )
            else:
                reason = (
                    f"Could not fit within opening hours ({dist['openingTime']}–{dist['closingTime']}) "
                    f"alongside higher-total-priority scheduled visits before daily visit cap ({max_visits})."
                )
        else:
            reason = (
                f"No non-overlapping slot remains within opening hours ({dist['openingTime']}–{dist['closingTime']}) "
                f"and working hours ({config['workStartTime']}–{config['workEndTime']}) after accounting for "
                f"higher-priority visits and {travel_desc}."
            )

        unscheduled.append(
            {
                "distributorId": did,
                "distributorName": dist["name"],
                "priority": dist_prio,
                "visitDurationMinutes": int(dist["visitDurationMinutes"]),
                "openingTime": dist["openingTime"],
                "closingTime": dist["closingTime"],
                "reason": reason,
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
