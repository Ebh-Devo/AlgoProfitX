"""Every route that can reach SQL persistence must also have a Catalyst-provider branch.

In the Catalyst provider there is no SQL session (the dependency yields ``None``), so a route that
uses the session without a Catalyst branch would crash at request time. This keeps new routes honest.
"""

import inspect

from fastapi.routing import APIRoute

from app.db.session import get_session
from app.main import create_app

# Routes that depend on a session only through the shared authentication dependency (which has its
# own Catalyst branch) and never touch persistence themselves.
SESSION_ONLY_VIA_AUTH = {
    ("GET", "/api/v1/auth/me"),
    ("GET", "/api/v1/strategies/definition-vocabulary"),
    ("POST", "/api/v1/strategies/definitions/validate"),
}


def _walk(routes, prefix=""):
    for route in routes:
        if isinstance(route, APIRoute):
            yield prefix + route.path, route
        elif type(route).__name__ == "_IncludedRouter":
            yield from _walk(
                route.original_router.routes,
                prefix + (getattr(route.include_context, "prefix", "") or ""),
            )


def _dependencies(dependant):
    yield dependant
    for child in dependant.dependencies:
        yield from _dependencies(child)


def _api_routes():
    for path, route in _walk(create_app().routes):
        if path.startswith("/api/"):
            yield path, route


def test_the_route_walk_finds_the_application_routes():
    paths = {path for path, _ in _api_routes()}
    assert len(paths) > 20
    assert {"/api/v1/auth/login", "/api/v1/strategies", "/api/v1/allocations"} <= paths


def test_every_session_dependent_route_has_a_catalyst_branch():
    missing = []
    for path, route in _api_routes():
        if not any(dep.call is get_session for dep in _dependencies(route.dependant)):
            continue
        if "catalyst" in inspect.getsource(route.endpoint).lower():
            continue
        for method in sorted(route.methods or ()):
            if (method, path) not in SESSION_ONLY_VIA_AUTH:
                missing.append(f"{method} {path}")
    assert missing == [], "Routes using the SQL session without a Catalyst branch: " + ", ".join(missing)


def test_the_allow_list_only_names_routes_that_exist():
    existing = {
        (method, path) for path, route in _api_routes() for method in (route.methods or ())
    }
    assert SESSION_ONLY_VIA_AUTH <= existing
