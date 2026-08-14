import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app as _flask_app  # noqa: E402


class _StripDestinationPrefix:
    """The rewrite in vercel.json sends every request to this file, but some
    Vercel runtimes (notably `vercel dev`) leak the rewrite's *destination*
    path ("/api/index") into PATH_INFO instead of preserving the original
    request path, so none of Flask's routes match. Strip it back off."""

    def __init__(self, wsgi_app):
        self.wsgi_app = wsgi_app

    def __call__(self, environ, start_response):
        path = environ.get("PATH_INFO", "")
        for prefix in ("/api/index", "/api"):
            if path == prefix:
                environ["PATH_INFO"] = "/"
                break
            if path.startswith(prefix + "/"):
                environ["PATH_INFO"] = path[len(prefix):]
                break
        return self.wsgi_app(environ, start_response)


app = _StripDestinationPrefix(_flask_app)
