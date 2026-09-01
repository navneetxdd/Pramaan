from __future__ import annotations

import hashlib


def collect_v1_routes(app) -> list[str]:
    routes: list[str] = []
    for route in app.routes:
        methods = getattr(route, "methods", None) or set()
        path = getattr(route, "path", None)
        if not path or not str(path).startswith("/api/v1"):
            continue
        for method in sorted(methods):
            if method in {"HEAD", "OPTIONS"}:
                continue
            routes.append(f"{method} {path}")
    return sorted(routes)


def routes_digest(app) -> tuple[int, str]:
    routes = collect_v1_routes(app)
    digest = hashlib.sha256("\n".join(routes).encode("utf-8")).hexdigest()[:16]
    return len(routes), digest
