from app.routes.health import health_bp
from app.routes.office import office_bp
from app.routes.distributors import distributors_bp
from app.routes.clustering import clustering_bp
from app.routes.scheduling import scheduling_bp
from app.routes.routes import routes_bp
from app.routes.predictions import predictions_bp
from app.routes.maps import maps_bp

__all__ = [
    "health_bp",
    "office_bp",
    "distributors_bp",
    "clustering_bp",
    "scheduling_bp",
    "routes_bp",
    "predictions_bp",
    "maps_bp",
]

