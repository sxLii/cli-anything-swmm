"""Root conftest.py for cli-anything-swmm tests.

Ensures swmm.toolkit is importable even when pytest adds parent directories
to sys.path (which can create a swmm namespace conflict with cli_anything/swmm/).

Root cause: When pytest uses __init__.py test packages, it adds the rootdir
to sys.path. The cli_anything/ directory (a namespace package) doesn't have
__init__.py, but when pytest processes its children, it can sometimes add
cli_anything/ itself to sys.path, causing cli_anything/swmm/ to be found
as the top-level 'swmm' namespace — shadowing the real swmm.toolkit package.

Fix: Pre-import swmm.toolkit before any test collection, forcing Python to
cache the correct module in sys.modules. Once cached, re-importing 'swmm'
from a shadowed path won't override the cached subpackages.
"""

import sys
import os


def pytest_configure(config):
    """Pre-import swmm.toolkit to prevent namespace shadowing."""
    # Find site-packages containing swmm.toolkit and ensure it's on sys.path
    try:
        import importlib.util

        # First check if swmm.toolkit is already importable
        spec = importlib.util.find_spec("swmm.toolkit")
        if spec is not None:
            # Pre-import to cache in sys.modules
            import swmm.toolkit  # noqa: F401
            return

        # If not found, search site-packages
        import site
        all_sites = []
        try:
            all_sites.extend(site.getsitepackages())
        except AttributeError:
            pass
        try:
            all_sites.append(site.getusersitepackages())
        except AttributeError:
            pass

        for sp in all_sites:
            candidate = os.path.join(sp, "swmm", "toolkit")
            if os.path.isdir(candidate):
                # Ensure site-packages is BEFORE any project dirs in sys.path
                if sp not in sys.path:
                    sys.path.insert(0, sp)
                else:
                    # Move it to front
                    sys.path.remove(sp)
                    sys.path.insert(0, sp)

                # Now pre-import to cache
                import swmm.toolkit  # noqa: F401
                return

    except Exception:
        pass  # Let tests fail naturally if swmm.toolkit is truly missing
