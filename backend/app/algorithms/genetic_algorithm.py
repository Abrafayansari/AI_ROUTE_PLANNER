from __future__ import annotations

import math
import time
import numpy as np

from app.utils.metrics import CostMatrixResult, evaluate_route_metrics, get_objective_weights


def _tour_cost(chromosome: list[int], weights: list[list[float]], return_to_office: bool) -> float:
    if not chromosome:
        return 0.0
    cost = weights[0][chromosome[0]]
    for i in range(len(chromosome) - 1):
        cost += weights[chromosome[i]][chromosome[i + 1]]
    if return_to_office:
        cost += weights[chromosome[-1]][0]
    return cost


def _order_crossover(parent1: list[int], parent2: list[int], rng: np.random.Generator) -> list[int]:
    """Order Crossover (OX1) preserves permutation validity."""
    length = len(parent1)
    if length <= 1:
        return list(parent1)

    a = int(rng.integers(0, length))
    b = int(rng.integers(0, length))
    start, end = min(a, b), max(a, b)

    child = [-1] * length
    used: set[int] = set()
    for i in range(start, end + 1):
        child[i] = parent1[i]
        used.add(parent1[i])

    p2_idx = (end + 1) % length
    child_idx = (end + 1) % length
    remaining = length - (end - start + 1)

    while remaining > 0:
        candidate = parent2[p2_idx]
        if candidate not in used:
            child[child_idx] = candidate
            used.add(candidate)
            child_idx = (child_idx + 1) % length
            remaining -= 1
        p2_idx = (p2_idx + 1) % length

    return child


def _mutate_permutation(chrom: list[int], rng: np.random.Generator) -> list[int]:
    """Inversion (2-opt slice) or swap mutation preserving exact permutation."""
    copy = list(chrom)
    length = len(copy)
    if length <= 1:
        return copy

    i = int(rng.integers(0, length))
    j = int(rng.integers(0, length))
    if i == j:
        j = (i + 1) % length

    if float(rng.random()) < 0.6:
        start, end = min(i, j), max(i, j)
        copy[start : end + 1] = reversed(copy[start : end + 1])
    else:
        copy[i], copy[j] = copy[j], copy[i]
    return copy


def validate_permutation(chromosome: list[int], num_distributors: int) -> bool:
    if len(chromosome) != num_distributors:
        return False
    seen: set[int] = set()
    for gene in chromosome:
        if not isinstance(gene, (int, np.integer)) or gene < 1 or gene > num_distributors or int(gene) in seen:
            return False
        seen.add(int(gene))
    return len(seen) == num_distributors


def run_genetic_algorithm(
    matrix: CostMatrixResult,
    return_to_office: bool = True,
    population_size: int = 80,
    generations: int = 150,
    crossover_rate: float = 0.85,
    mutation_rate: float = 0.18,
    elite_count: int = 4,
    tournament_size: int = 4,
    stagnation_limit: int = 45,
    seed: int | None = None,
    optimization_objective: str | None = None,
) -> dict:
    """
    Week 7: Evolutionary Search — Genetic Algorithm for multi-stop visit permutation.
    Fixed office start (0) and optional fixed office return (0).
    Minimizes total tour duration in FASTEST_TIME mode or total road distance in SHORTEST_DISTANCE mode.
    """
    start_t = time.perf_counter()
    num_distributors = len(matrix.nodes) - 1
    actual_seed = int(seed if seed is not None else matrix.seed)
    elite_count = min(elite_count, population_size)
    tournament_size = min(tournament_size, population_size)

    weights, resolved_obj = get_objective_weights(matrix, optimization_objective)
    cost_unit = "min" if resolved_obj == "FASTEST_TIME" else "km"
    unit_label = "travel time (min)" if resolved_obj == "FASTEST_TIME" else "road distance (km)"
    objective_description = (
        f"Evolutionary heuristic search (OX1 crossover, inversion/swap mutation, elitism) minimizing total {unit_label}; scales beyond 12 stops without guaranteeing global optimality."
    )

    if num_distributors <= 0:
        return {
            "algorithm": "GENETIC_ALGORITHM",
            "optimizationObjective": resolved_obj,
            "dataSource": matrix.dataSource,
            "trafficCalculatedAt": matrix.trafficCalculatedAt,
            "isInformed": False,
            "isHeuristic": True,
            "isOptimalForObjective": False,
            "objectiveDescription": objective_description,
            "routeOrder": [0],
            "totalCost": 0.0,
            "estimatedDistanceKm": 0.0,
            "estimatedDurationMinutes": 0.0,
            "totalStaticDurationMinutes": 0.0,
            "trafficDelayMinutes": 0.0,
            "edgeCount": 0,
            "nodesExpanded": 1,
            "generationsRun": 0,
            "convergenceHistory": [{"generation": 0, "bestCost": 0.0, "unit": cost_unit}],
            "executionTimeMs": round((time.perf_counter() - start_t) * 1000.0, 3),
            "completed": True,
            "parameters": {
                "populationSize": population_size,
                "generations": generations,
                "crossoverRate": crossover_rate,
                "mutationRate": mutation_rate,
                "eliteCount": elite_count,
                "seed": actual_seed,
                "optimizationObjective": resolved_obj,
            },
        }

    rng = np.random.default_rng(actual_seed + 997)
    base_perm = list(range(1, num_distributors + 1))

    def evaluate(chrom: list[int]) -> tuple[float, float, list[int]]:
        cost = _tour_cost(chrom, weights, return_to_office)
        return (cost, 1.0 / (cost + 1e-6), chrom)

    population: list[tuple[float, float, list[int]]] = []

    # Seed one greedy nearest-neighbor candidate + random permutations
    greedy: list[int] = []
    remaining = set(base_perm)
    cur = 0
    while remaining:
        best_next = -1
        best_w = math.inf
        for cand in sorted(remaining):
            if weights[cur][cand] < best_w:
                best_w = weights[cur][cand]
                best_next = cand
        greedy.append(best_next)
        remaining.remove(best_next)
        cur = best_next
    population.append(evaluate(greedy))

    for _ in range(1, population_size):
        perm = [int(x) for x in rng.permutation(base_perm)]
        population.append(evaluate(perm))

    evaluations = len(population)
    population.sort(key=lambda ind: ind[0])

    best_ever = population[0]
    stagnation = 0
    generations_run = 0
    convergence_history = [
        {"generation": 0, "bestCost": round(best_ever[0], 3), "unit": cost_unit}
    ]

    def select_tournament(pop: list[tuple[float, float, list[int]]]) -> tuple[float, float, list[int]]:
        idxs = rng.integers(0, len(pop), size=tournament_size)
        best = pop[int(idxs[0])]
        for idx in idxs[1:]:
            cand = pop[int(idx)]
            if cand[0] < best[0]:
                best = cand
        return best

    for gen in range(1, generations + 1):
        generations_run = gen
        next_pop: list[tuple[float, float, list[int]]] = list(population[:elite_count])

        while len(next_pop) < population_size:
            p1 = select_tournament(population)
            p2 = select_tournament(population)
            child_chrom = (
                _order_crossover(p1[2], p2[2], rng)
                if float(rng.random()) < crossover_rate
                else list(p1[2])
            )
            if float(rng.random()) < mutation_rate:
                child_chrom = _mutate_permutation(child_chrom, rng)
            next_pop.append(evaluate(child_chrom))
            evaluations += 1

        next_pop.sort(key=lambda ind: ind[0])
        population = next_pop

        if population[0][0] + 1e-6 < best_ever[0]:
            best_ever = population[0]
            stagnation = 0
        else:
            stagnation += 1

        if gen % 10 == 0 or gen == generations or stagnation >= stagnation_limit:
            convergence_history.append(
                {"generation": gen, "bestCost": round(best_ever[0], 3), "unit": cost_unit}
            )

        if stagnation >= stagnation_limit:
            break

    if not validate_permutation(best_ever[2], num_distributors):
        raise ValueError("GA produced invalid distributor permutation")

    route_order = (
        [0, *best_ever[2], 0] if return_to_office else [0, *best_ever[2]]
    )
    metrics = evaluate_route_metrics(matrix, route_order, resolved_obj)

    return {
        "algorithm": "GENETIC_ALGORITHM",
        "optimizationObjective": resolved_obj,
        "dataSource": matrix.dataSource,
        "trafficCalculatedAt": matrix.trafficCalculatedAt,
        "isInformed": False,
        "isHeuristic": True,
        "isOptimalForObjective": False,
        "objectiveDescription": objective_description,
        "routeOrder": route_order,
        "totalCost": metrics["objectiveCost"],
        "estimatedDistanceKm": metrics["totalDistanceKm"],
        "estimatedDurationMinutes": metrics["totalDurationMinutes"],
        "totalStaticDurationMinutes": metrics["totalStaticDurationMinutes"],
        "trafficDelayMinutes": metrics["trafficDelayMinutes"],
        "edgeCount": metrics["edgeCount"],
        "nodesExpanded": evaluations,
        "generationsRun": generations_run,
        "convergenceHistory": convergence_history,
        "executionTimeMs": round((time.perf_counter() - start_t) * 1000.0, 3),
        "completed": True,
        "parameters": {
            "populationSize": population_size,
            "generations": generations,
            "crossoverRate": crossover_rate,
            "mutationRate": mutation_rate,
            "eliteCount": elite_count,
            "seed": actual_seed,
            "optimizationObjective": resolved_obj,
        },
    }
