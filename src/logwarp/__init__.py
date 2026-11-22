try:
    from logwarp._version import __version__
except ImportError:  # package not installed (e.g. running from source without build)
    __version__ = "0.0.0.dev0"

from logwarp.cli import main

__all__ = ["__version__", "main"]
