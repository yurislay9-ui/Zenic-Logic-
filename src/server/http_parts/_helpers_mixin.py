"""
CORS and JSON helpers mixin for TitanHTTPHandler.
"""

from ._imports import json, _cors_origin


class HelpersMixin:
    """CORS and JSON helper methods for TitanHTTPHandler."""

    def log_message(self, format, *args):
        from ._imports import logger
        logger.info("HTTP: %s", format % args)

    def do_OPTIONS(self):
        self.send_response(200)
        self._set_cors_headers()
        self.end_headers()

    def _set_cors_headers(self):
        self.send_header('Access-Control-Allow-Origin', _cors_origin)
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type, Authorization')

    def _send_json(self, data, status=200):
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self._set_cors_headers()
        body = json.dumps(data, ensure_ascii=False).encode('utf-8')
        self.send_header('Content-Length', len(body))
        self.end_headers()
        self.wfile.write(body)
