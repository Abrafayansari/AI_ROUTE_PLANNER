from __future__ import annotations

import os
from app import create_app

app = create_app()

if __name__ == "__main__":
    try:
        port = int(os.getenv("PORT", "5000"))
    except ValueError:
        port = 5000
    if not (1 <= port <= 65535):
        port = 5000
    debug = os.getenv("FLASK_ENV", "development") == "development"
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)
