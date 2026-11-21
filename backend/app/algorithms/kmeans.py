from __future__ import annotations

from typing import Literal
import numpy as np

from app.utils.metrics import haversine_km

CLUSTER_LABELS = [
    "Cluster A",
    "Cluster B",
    "Cluster C",
    "Cluster D",
    "Cluster E",
    "Cluster F",
    "Cluster G",
    "Cluster H",
]


def _label_for_cluster(idx: int) -> str:
    return CLUSTER_LABELS[idx] if idx < len(CLUSTER_LABELS) else f"Cluster {idx + 1}"


def run_kmeans(
    points: list[dict],
    k: int,
    seed: int = 42,
    max_iterations: int = 100,
    init_method: Literal["kmeans++", "random"] = "kmeans++",
) -> dict:
    """
    Week 12: Unsupervised Learning — K-Means Geographic Clustering.
    Groups distributors by Haversine coordinate proximity using NumPy arrays.
    Does NOT compute road routes or visit ordering.
    """
    if not points:
        raise ValueError("At least 1 distributor is required for K-Means clustering.")
    if not isinstance(k, int) or k < 1 or k > len(points):
        raise ValueError(
            f"Invalid K={k}. Must satisfy 1 <= K <= {len(points)} selected distributors."
        )

    rng = np.random.default_rng(int(seed))
    coords = np.array(
        [[float(p["latitude"]), float(p["longitude"])] for p in points], dtype=float
    )
    n_points = len(points)

    centroids: list[tuple[float, float]] = []
    if init_method == "random":
        perm = rng.permutation(n_points)
        for c in range(k):
            idx = int(perm[c])
            centroids.append((float(coords[idx, 0]), float(coords[idx, 1])))
    else:
        first_idx = int(rng.integers(0, n_points))
        centroids.append((float(coords[first_idx, 0]), float(coords[first_idx, 1])))
        while len(centroids) < k:
            sq_dists = np.empty(n_points, dtype=float)
            for i in range(n_points):
                min_d = min(
                    haversine_km(coords[i, 0], coords[i, 1], clat, clng)
                    for (clat, clng) in centroids
                )
                sq_dists[i] = min_d * min_d

            sum_sq = float(sq_dists.sum())
            if sum_sq <= 1e-12:
                fb = coords[len(centroids) % n_points]
                centroids.append((float(fb[0]), float(fb[1])))
                continue

            probs = sq_dists / sum_sq
            chosen = int(rng.choice(n_points, p=probs))
            centroids.append((float(coords[chosen, 0]), float(coords[chosen, 1])))

    centroid_arr = np.array(centroids, dtype=float)
    labels = np.full(n_points, -1, dtype=int)
    iterations = 0
    converged = False
    total_wcss = 0.0
    iteration_history: list[dict] = []

    for it in range(1, max_iterations + 1):
        iterations = it
        reassigned_count = 0
        inertia = 0.0
        next_labels = np.empty(n_points, dtype=int)

        for i in range(n_points):
            best_c = 0
            best_dist = float("inf")
            for c in range(k):
                d = haversine_km(
                    coords[i, 0], coords[i, 1], centroid_arr[c, 0], centroid_arr[c, 1]
                )
                if d < best_dist:
                    best_dist = d
                    best_c = c
            next_labels[i] = best_c
            inertia += best_dist * best_dist
            if next_labels[i] != labels[i]:
                reassigned_count += 1

        labels = next_labels
        total_wcss = round(inertia, 4)
        iteration_history.append(
            {
                "iteration": it,
                "inertia": total_wcss,
                "reassignedCount": int(reassigned_count),
            }
        )

        if reassigned_count == 0:
            converged = True
            break

        max_shift = 0.0
        for c in range(k):
            mask = labels == c
            if np.any(mask):
                new_lat = float(coords[mask, 0].mean())
                new_lng = float(coords[mask, 1].mean())
                shift = haversine_km(
                    centroid_arr[c, 0], centroid_arr[c, 1], new_lat, new_lng
                )
                if shift > max_shift:
                    max_shift = shift
                centroid_arr[c, 0] = new_lat
                centroid_arr[c, 1] = new_lng

        if max_shift < 1e-6:
            converged = True
            break

    counts = [0] * k
    assignments: list[dict] = []
    for idx, pt in enumerate(points):
        c = int(labels[idx])
        counts[c] += 1
        dist = haversine_km(
            float(pt["latitude"]),
            float(pt["longitude"]),
            float(centroid_arr[c, 0]),
            float(centroid_arr[c, 1]),
        )
        assignments.append(
            {
                "distributorId": str(pt["id"]),
                "distributorName": str(pt["name"]),
                "latitude": float(pt["latitude"]),
                "longitude": float(pt["longitude"]),
                "clusterIndex": c,
                "clusterLabel": _label_for_cluster(c),
                "distanceToCentroidKm": round(dist, 3),
            }
        )

    centroid_results = [
        {
            "clusterIndex": idx,
            "clusterLabel": _label_for_cluster(idx),
            "centroidLat": round(float(centroid_arr[idx, 0]), 6),
            "centroidLng": round(float(centroid_arr[idx, 1]), 6),
            "count": int(counts[idx]),
        }
        for idx in range(k)
    ]

    return {
        "k": k,
        "seed": int(seed),
        "initMethod": init_method,
        "maxIterations": int(max_iterations),
        "iterations": iterations,
        "converged": converged,
        "totalWcss": total_wcss,
        "centroids": centroid_results,
        "assignments": assignments,
        "iterationHistory": iteration_history,
    }
