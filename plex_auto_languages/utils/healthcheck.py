import json
import logging
from typing import Callable
from threading import Thread
from flask import Flask, jsonify
from werkzeug.serving import make_server

flask_logger = logging.getLogger("werkzeug")
flask_logger.setLevel(logging.ERROR)

class HealthcheckServer(Thread):
    def __init__(self, name: str, is_ready: Callable, is_healthy: Callable):
        super().__init__()
        self._is_healthy = is_healthy
        self._is_ready = is_ready
        self._app = Flask(name)
        self._server = make_server("0.0.0.0", 9880, self._app)
        self._ctx = self._app.app_context()
        self._ctx.push()

        @self._app.route("/")
        @self._app.route("/health")
        def __health():
            healthy = self._is_healthy()
            status_code = 200 if healthy else 503
            logging.info(f"Health check: {'healthy' if healthy else 'unhealthy'} (status {status_code})")
            return jsonify({"healthy": healthy}), status_code

        @self._app.route("/ready")
        def __ready():
            ready = self._is_ready()
            status_code = 200 if ready else 503
            logging.info(f"Readiness check: {'ready' if ready else 'not ready'} (status {status_code})")
            return jsonify({"ready": ready}), status_code

    def run(self):
        logging.info("Starting HealthcheckServer...")
        self._server.serve_forever()

    def shutdown(self):
        logging.info("Shutting down HealthcheckServer...")
        self._server.shutdown()
        logging.info("HealthcheckServer stopped.")
