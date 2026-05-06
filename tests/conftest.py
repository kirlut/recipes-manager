import os
import pathlib
import sys

import pytest

_REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


@pytest.fixture(scope="session")
def base_url() -> str:
    """Default `base_url` fixture for pytest-playwright's session-scoped
    `browser_context_args` consumer.

    The pytest-base-url plugin (transitive via pytest-playwright) is
    disabled in pyproject.toml because its session-scoped `_verify_url`
    autouse fixture conflicts with phase-1's function-scoped `base_url`.
    Providing a session-scoped default here keeps Playwright happy
    while letting phase-specific conftests override at any scope.
    """
    return os.environ.get("HOST_PORT") and f"http://127.0.0.1:{os.environ['HOST_PORT']}" or "http://127.0.0.1:8080"
