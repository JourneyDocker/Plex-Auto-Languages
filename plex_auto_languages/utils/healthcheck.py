import logging
from typing import Callable
from threading import Thread
from flask import Flask, jsonify
from werkzeug.serving import make_server

flask_logger = logging.getLogger("werkzeug")
flask_logger.setLevel(logging.ERROR)

class HealthcheckServer(Thread):
    """
    A server that provides health and readiness check endpoints.

    This class runs a Flask web server in a separate thread to expose health and
    readiness check endpoints for the application. It allows external systems
    (like Kubernetes) to monitor the application's status.

    Attributes:
        _is_healthy (Callable): A function that returns True if the application is healthy.
        _is_ready (Callable): A function that returns True if the application is ready.
        _app (Flask): The Flask application instance.
        _server: The WSGI server instance.
        _ctx: The Flask application context.
    """

    def __init__(self, name: str, is_ready: Callable[[], bool], is_healthy: Callable[[], bool], port: int = 9880):
        """
        Initialize the HealthcheckServer.

        Sets up a Flask application with health and readiness check endpoints.

        Args:
            name (str): The name of the Flask application.
            is_ready (Callable[[], bool]): A function that returns True if the application is ready.
            is_healthy (Callable[[], bool]): A function that returns True if the application is healthy.
            port (int): The port to run the server on.
        """
        super().__init__(daemon=True)
        self._is_healthy = is_healthy
        self._is_ready = is_ready
        self._app = Flask(name)
        self._server = make_server("0.0.0.0", port, self._app)
        self._ctx = self._app.app_context()
        self._ctx.push()

        self._setup_routes()

    def _setup_routes(self):
        """Set up the health and readiness check endpoints."""
        @self._app.route("/")
        @self._app.route("/health")
        def health_check():
            """
            Health check endpoint.

            Returns:
                tuple: A JSON response with health status and appropriate HTTP status code.
                       200 if healthy, 503 if unhealthy.
            """
            healthy = self._is_healthy()
            status_code = 200 if healthy else 503
            logging.info(f"Health check: {'healthy' if healthy else 'unhealthy'} (status {status_code})")
            return jsonify({"healthy": healthy}), status_code

        @self._app.route("/ready")
        def readiness_check():
            """
            Readiness check endpoint.

            Returns:
                tuple: A JSON response with readiness status and appropriate HTTP status code.
                       200 if ready, 503 if not ready.
            """
            ready = self._is_ready()
            status_code = 200 if ready else 503
            logging.info(f"Readiness check: {'ready' if ready else 'not ready'} (status {status_code})")
            return jsonify({"ready": ready}), status_code

    def run(self) -> None:
        """
        Start the health check server.

        This method is called when the thread is started. It runs the Flask
        server in the background until shutdown is called.

        Returns:
            None
        """
        logging.info("Starting Healthcheck Server...")
        self._server.serve_forever()

    def shutdown(self) -> None:
        """
        Shutdown the health check server.

        Gracefully stops the Flask server.

        Returns:
            None
        """
        logging.info("Shutting down Healthcheck Server...")
        self._server.shutdown()
        logging.info("Healthcheck Server stopped")
