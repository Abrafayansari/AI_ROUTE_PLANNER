from app.services.db_service import (
    apply_migrations_idempotently,
    check_database_health,
    clear_demo_data,
    is_database_configured,
    load_demo_data,
    log_api_request,
)
from app.services.clustering_service import get_latest_clusters, run_and_save_clusters
from app.services.scheduling_service import get_latest_schedule, run_and_save_schedule
from app.services.route_service import (
    create_route_plan,
    delete_route_plan,
    generate_local_matrix,
    get_analytics_summary,
    get_route_plan_algorithms,
    get_route_plan_detail,
    list_route_plans,
    optimize_route_plan,
    preview_optimization,
    update_route_plan,
    update_stop_status,
)

from app.services.prediction_service import (
    get_cpt_data,
    get_model_info,
    list_prediction_history,
    predict_route_plan_delays,
    predict_single_visit,
)

__all__ = [
    "apply_migrations_idempotently",
    "check_database_health",
    "clear_demo_data",
    "is_database_configured",
    "load_demo_data",
    "log_api_request",
    "get_latest_clusters",
    "run_and_save_clusters",
    "get_latest_schedule",
    "run_and_save_schedule",
    "create_route_plan",
    "delete_route_plan",
    "generate_local_matrix",
    "get_analytics_summary",
    "get_route_plan_algorithms",
    "get_route_plan_detail",
    "list_route_plans",
    "optimize_route_plan",
    "preview_optimization",
    "update_route_plan",
    "update_stop_status",
    "get_cpt_data",
    "get_model_info",
    "list_prediction_history",
    "predict_route_plan_delays",
    "predict_single_visit",
]

