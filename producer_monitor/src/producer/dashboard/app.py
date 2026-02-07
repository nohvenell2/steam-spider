"""Flask dashboard application."""

import signal
import sys
import logging
from typing import Generator, Any
from flask import Flask, render_template, Response, jsonify, request
import json
import time
import errno
import os

from .config import DashboardConfig
from .monitor import QueueMonitor
from .metrics import calculate_progress
from .db_health import DatabaseHealth
from .admin import (
    REQUIRED_CONFIRMATION_PHRASE,
    execute_reset,
    get_producer_status,
    start_producer,
    check_rate_limit
)
from .scheduler import AutomationScheduler
from ..queue import RedisQueue

logger = logging.getLogger(__name__)


class NoHealthCheckFilter(logging.Filter):
    """Filter out health check and frequent API requests from logs."""

    def filter(self, record: logging.LogRecord) -> bool:
        # Filter out health check requests
        if "/health" in record.getMessage():
            return False
        # Filter out SSE and polling endpoints
        if "/api/stream" in record.getMessage():
            return False
        if "/api/status" in record.getMessage():
            return False
        if "/api/admin/producer/status" in record.getMessage():
            return False
        if "/api/admin/scheduler/status" in record.getMessage():
            return False
        return True


def create_app(config: DashboardConfig) -> Flask:
    """
    Create Flask application.

    Args:
        config: DashboardConfig instance

    Returns:
        Configured Flask app
    """
    app = Flask(__name__)

    # Initialize Redis connection (shared)
    redis_queue = RedisQueue(
        host=config.redis_host,
        port=config.redis_port,
        db=config.redis_db,
        username=config.redis_id_producer_monitor,
        password=config.redis_pw_producer_monitor,
        decode_responses=True
    )
    
    # Template filters
    @app.template_filter('datetime')
    def format_datetime(value, format="%Y-%m-%d %H:%M"):
        """Format a unix timestamp to a readable date string."""
        if value is None: 
            return ""
        try:
            import datetime
            return datetime.datetime.fromtimestamp(float(value)).strftime(format)
        except (ValueError, TypeError):
            return value

    # Initialize monitor, health checker, and scheduler
    db_health = DatabaseHealth(config.get_database_url())
    monitor = QueueMonitor(redis_queue, db_health)
    scheduler = AutomationScheduler(
        redis_queue=redis_queue,
        db_health=db_health,
        producer_mode=config.scheduler_producer_mode,
        producer_sample_count=config.scheduler_sample_count,
        poll_interval=config.scheduler_poll_interval,
        clone_db_name=config.scheduler_clone_db_name,
        max_wait_time=config.scheduler_max_wait_time,
        db_host=config.postgres_host,
        db_port=config.postgres_port,
        db_user=config.postgres_user,
        db_password=config.postgres_password,
        db_name=config.postgres_db,
    )

    @app.route("/")
    def index():  # type: ignore
        """Render main dashboard."""
        return render_template("index.html", refresh_interval=config.refresh_interval_long)

    @app.route("/health")
    def health():  # type: ignore
        """Health check endpoint (lightweight)."""
        return jsonify({"status": "ok"}), 200

    @app.route("/api/status")
    def status():  # type: ignore
        """Get current status as JSON."""
        snapshot = monitor.get_snapshot()

        db_status = db_health.check()

        return jsonify({
            "timestamp": snapshot.timestamp,
            "producer_start_time": snapshot.producer_start_time,
            "total_games": snapshot.total_games,
            "database": db_status,
        })

    @app.route("/api/stream")
    def stream():  # type: ignore
        """SSE stream for real-time updates."""
        def generate() -> Generator[str, None, None]:
            try:
                while True:
                    snapshot = monitor.get_snapshot()
                    progress = calculate_progress(snapshot)

                    data = {
                        "timestamp": snapshot.timestamp,
                        "queues": {
                            "work": snapshot.work,
                            "processing": snapshot.processing,
                            "result": snapshot.result,
                            "crawling_failed": snapshot.crawling_failed,
                            "saving": snapshot.saving,
                            "saving_failed": snapshot.saving_failed,
                        },
                        "progress": progress,
                        "updated_games": snapshot.updated_games,
                        "scheduler": scheduler.get_status().to_dict()
                    }

                    yield f"data: {json.dumps(data)}\n\n"
                    time.sleep(config.refresh_interval)

            except GeneratorExit:
                logger.info("SSE client disconnected (GeneratorExit)")

            except OSError as e:
                # 1. Windows 에러 체크 (winerror 속성이 있는 경우만)
                win_error = getattr(e, 'winerror', None)
                if win_error in [233, 10053, 10054]:
                    logger.info(f"SSE client disconnected (Windows Error {win_error})")
                    return

                # 2. Linux/Unix 에러 체크 (errno 사용)
                # EPIPE(32): Broken pipe, ECONNRESET(104): Connection reset by peer
                if e.errno in [errno.EPIPE, errno.ECONNRESET]:
                    logger.info(f"SSE client disconnected (Unix Error {e.errno})")
                    return

                # 3. 그 외 진짜 에러는 로그 남기기
                logger.error(f"Stream error: {e}")
                raise e

        return Response(
            generate(),
            mimetype="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no"
            }
        )

    # ========================================
    # Admin Endpoints
    # ========================================

    @app.route("/api/admin/reset", methods=["POST"])
    def api_reset():  # type: ignore
        """Execute system reset."""
        data = request.get_json()

        # Validate action
        action = data.get("action")
        if action not in ["redis", "database", "all"]:
            return jsonify({
                "success": False,
                "error": "Invalid action. Must be 'redis', 'database', or 'all'."
            }), 400

        # Validate confirmation phrase
        confirmation = data.get("confirmation_phrase", "")
        if confirmation != REQUIRED_CONFIRMATION_PHRASE:
            return jsonify({
                "success": False,
                "error": f"Invalid confirmation phrase. Please type: {REQUIRED_CONFIRMATION_PHRASE}"
            }), 400

        # Rate limit check
        if not check_rate_limit(
            redis_queue,
            f"reset_{action}",
            config.rate_limit_reset_count,
            config.rate_limit_reset_window
        ):
            return jsonify({
                "success": False,
                "error": "Rate limit exceeded. Please wait before trying again."
            }), 429

        # Execute reset
        success, result = execute_reset(action)

        if success:
            return jsonify({"success": True, **result}), 200
        else:
            return jsonify({"success": False, **result}), 500

    @app.route("/api/admin/producer/status")
    def api_producer_status():  # type: ignore
        """Get producer execution status."""
        status = get_producer_status(redis_queue)
        return jsonify(status), 200

    @app.route("/api/admin/producer/start", methods=["POST"])
    def api_producer_start():  # type: ignore
        """Start producer execution."""
        data = request.get_json()

        # Validate mode
        mode = data.get("mode")
        if mode not in ["production", "test"]:
            return jsonify({
                "success": False,
                "error": "Invalid mode. Must be 'production' or 'test'."
            }), 400

        # Validate sample_count for test mode
        sample_count = data.get("sample_count")
        if mode == "test":
            if not sample_count or not isinstance(sample_count, int):
                return jsonify({
                    "success": False,
                    "error": "sample_count is required for test mode and must be an integer."
                }), 400

            if sample_count < 1 or sample_count > 10000:
                return jsonify({
                    "success": False,
                    "error": "sample_count must be between 1 and 10000."
                }), 400

        # Rate limit check
        if not check_rate_limit(
            redis_queue,
            "producer_start",
            config.rate_limit_producer_count,
            config.rate_limit_producer_window
        ):
            return jsonify({
                "success": False,
                "error": "Too many producer starts. Please wait before trying again."
            }), 429

        # Start producer
        success, result = start_producer(redis_queue, mode, sample_count)

        if success:
            return jsonify({"success": True, **result}), 200
        else:
            # Check if error is due to duplicate execution
            if "already running" in result.get("error", ""):
                return jsonify({"success": False, **result}), 409
            return jsonify({"success": False, **result}), 500

    @app.route("/api/admin/jobs/retry", methods=["POST"])
    def api_retry_jobs():  # type: ignore
        """Retry all failed jobs."""
        try:
            redis_queue.push_failed_jobs()
            return jsonify({"success": True}), 200
        except Exception as e:
            logger.error(f"Failed to retry jobs: {e}")
            return jsonify({"success": False, "error": str(e)}), 500

    @app.route("/api/admin/jobs/retry-processing", methods=["POST"])
    def api_retry_processing_jobs():  # type: ignore
        """Retry all processing jobs."""
        try:
            redis_queue.push_processing_jobs()
            return jsonify({"success": True}), 200
        except Exception as e:
            logger.error(f"Failed to retry processing jobs: {e}")
            return jsonify({"success": False, "error": str(e)}), 500

    # ========================================
    # Scheduler Endpoints
    # ========================================

    @app.route("/api/admin/scheduler/status")
    def api_scheduler_status():  # type: ignore
        """Get scheduler status."""
        status = scheduler.get_status()
        return jsonify(status.to_dict()), 200

    @app.route("/api/admin/scheduler/start", methods=["POST"])
    def api_scheduler_start():  # type: ignore
        """Start the automation scheduler."""
        success = scheduler.start()
        if success:
            return jsonify({"success": True, "message": "Scheduler started"}), 200
        else:
            return jsonify({"success": False, "error": "Scheduler is already running"}), 409

    @app.route("/api/admin/scheduler/stop", methods=["POST"])
    def api_scheduler_stop():  # type: ignore
        """Stop the automation scheduler."""
        success = scheduler.stop()
        if success:
            return jsonify({"success": True, "message": "Scheduler stopped"}), 200
        else:
            return jsonify({"success": False, "error": "Scheduler is not running"}), 409

    @app.route("/dlq/crawling")
    def dlq_crawling():  # type: ignore
        """Render DLQ Crawling page."""
        page = request.args.get('page', 1, type=int)
        per_page = 20
        
        total_items = redis_queue.get_crawling_failed_queue_length()
        total_pages = (total_items + per_page - 1) // per_page
        
        # Ensure page is within valid range
        page = max(1, min(page, total_pages)) if total_pages > 0 else 1
        
        start_index = (page - 1) * per_page
        end_index = start_index + per_page - 1
        
        # redis lrange is inclusive for both start and end
        raw_data = redis_queue.get_failed_crawling_data(start_index, end_index)
        items = raw_data
        
        return render_template(
            "dlq_crawling.html",
            items=items,
            page=page,
            total_pages=total_pages,
            start_index=start_index
        )

    @app.route("/dlq/insert")
    def dlq_insert():  # type: ignore
        """Render DLQ DB Insert page."""
        page = request.args.get('page', 1, type=int)
        per_page = 1  # Show one item at a time
        
        total_items = redis_queue.get_saving_failed_queue_length()
        total_pages = (total_items + per_page - 1) // per_page
        
        # Ensure page is within valid range
        page = max(1, min(page, total_pages)) if total_pages > 0 else 1
        
        start_index = (page - 1) * per_page
        end_index = start_index + per_page - 1
        
        # Get data
        raw_data = redis_queue.get_failed_insert_data(start_index, end_index)
        item = raw_data[0] if raw_data else None
        
        return render_template(
            "dlq_insert.html",
            item=item,
            page=page,
            total_pages=total_pages,
            total_items=total_items
        )



    return app


def main() -> int:
    """
    Main entry point for dashboard.

    Returns:
        Exit code
    """
    # Load configuration
    try:
        config = DashboardConfig()
    except Exception as e:
        print(f"Configuration error: {e}")
        return 1

    # Setup logging
    logging.basicConfig(
        level=config.log_level,
        format="[%(asctime)s] %(levelname)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    # Graceful shutdown handler
    def signal_handler(signum: int, frame: Any) -> None:  # type: ignore
        logger.info("Received shutdown signal, stopping dashboard...")
        os._exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Create Flask app
    app = create_app(config)

    logger.info(f"Starting dashboard at http://{config.dashboard_host}:{config.dashboard_port}")

    try:
        # Set Flask logger to INFO but filter out noisy endpoints
        flask_logger = logging.getLogger('werkzeug')
        flask_logger.setLevel(logging.INFO)
        flask_logger.addFilter(NoHealthCheckFilter())

        app.run(
            host=config.dashboard_host,
            port=config.dashboard_port,
            debug=False,
            use_reloader=False,
            threaded=True
        )
        return 0
    except Exception as e:
        logger.error(f"Dashboard error: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
