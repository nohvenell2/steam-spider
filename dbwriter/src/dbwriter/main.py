"""Main entry point for DB Writer"""

import sys
import signal
import json
import logging
import os
import ssl
from datetime import datetime
from pathlib import Path

import redis

from dbwriter.config import Config
from dbwriter.batch_processor import BatchProcessor, transform_data
from dbwriter.db.connection import init_db
from dbwriter.exceptions import RedisConnectionError, DatabaseConnectionError

# Global shutdown flag
shutdown_requested = False


def signal_handler(signum, frame):
    """Handle SIGINT and SIGTERM signals for graceful shutdown."""
    global shutdown_requested
    signal_name = signal.Signals(signum).name
    logger.info(f"Received {signal_name}. Initiating graceful shutdown...")
    shutdown_requested = True


def setup_logging(config: Config):
    """
    Setup logging configuration.

    Args:
        config: Configuration object
    """
    # Create logs directory if it doesn't exist
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)

    # Generate timestamped log file name
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = log_dir / f"dbwriter_{timestamp}.log"

    # Configure logging
    log_format = "[%(asctime)s] %(message)s"
    date_format = "%Y-%m-%d %H:%M:%S"

    # Setup root logger
    logging.basicConfig(
        level=getattr(logging, config.LOG_LEVEL),
        format=log_format,
        datefmt=date_format,
        handlers=[
            logging.FileHandler(log_file, encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )

    global logger
    logger = logging.getLogger(__name__)
    logger.info(f"Logging initialized | log_file={log_file} | level={config.LOG_LEVEL}")


def connect_redis(config: Config) -> redis.Redis:
    """
    Connect to Redis with retry logic.

    Args:
        config: Configuration object

    Returns:
        Redis client

    Raises:
        RedisConnectionError: If connection fails after max retries
    """
    max_retries = config.MAX_REDIS_RETRIES
    base_delay = config.RETRY_BASE_DELAY

    for attempt in range(1, max_retries + 1):
        try:
            connection_kwargs = {
                'host': config.REDIS_HOST,
                'port': config.REDIS_PORT,
                'db': config.REDIS_DB,
                'username': config.REDIS_ID_DBWRITER if config.REDIS_ID_DBWRITER else None,
                'password': config.REDIS_PW_DBWRITER if config.REDIS_PW_DBWRITER else None,
                'decode_responses': True,
                'socket_connect_timeout': 5,
                'socket_timeout': 30,  # BRPOP timeout(10s)보다 충분히 길게 설정
            }

            # Add TLS/SSL configuration if enabled
            if config.REDIS_SSL_ENABLED:
                logger.info(f"Enabling TLS connection | CA={config.REDIS_SSL_CA_CERT}")
                connection_kwargs['ssl'] = True
                connection_kwargs['ssl_cert_reqs'] = ssl.CERT_REQUIRED

                if config.REDIS_SSL_CA_CERT:
                    connection_kwargs['ssl_ca_certs'] = config.REDIS_SSL_CA_CERT
                if config.REDIS_SSL_CERT:
                    connection_kwargs['ssl_certfile'] = config.REDIS_SSL_CERT
                if config.REDIS_SSL_KEY:
                    connection_kwargs['ssl_keyfile'] = config.REDIS_SSL_KEY

                connection_kwargs['ssl_check_hostname'] = config.REDIS_SSL_CHECK_HOSTNAME

            client = redis.Redis(**connection_kwargs)

            # Test connection
            client.ping()
            logger.info(
                f"Redis connected | host={config.REDIS_HOST} | port={config.REDIS_PORT} | db={config.REDIS_DB} | TLS={'enabled' if config.REDIS_SSL_ENABLED else 'disabled'}"
            )
            return client

        except redis.ConnectionError as e:
            if attempt == max_retries:
                logger.error(f"Redis connection failed after {max_retries} attempts | error={str(e)}")
                raise RedisConnectionError(f"Failed to connect to Redis: {str(e)}")

            delay = base_delay * attempt
            logger.warning(
                f"Redis connection failed | retry={attempt}/{max_retries} | delay={delay}s | error={str(e)}"
            )
            import time
            time.sleep(delay)


def consumer_loop(config: Config):
    """
    Main consumer loop - Redis에서 결과를 소비하여 DB에 저장.

    Args:
        config: Configuration object
    """
    # Connect to Redis
    redis_client = connect_redis(config)

    # Initialize batch processor WITH redis_client
    processor = BatchProcessor(config, redis_client)

    # Create DateParser for transformation
    from dbwriter.date_parser import DateParser
    date_parser = DateParser()

    logger.info("Consumer loop started | queue=queue:result -> queue:saving")

    try:
        while not shutdown_requested:
            try:
                # BRPOPLPUSH from queue:result to queue:saving with timeout
                raw_message = redis_client.brpoplpush(
                    src="queue:result",
                    dst="queue:saving",
                    timeout=10
                )

                if raw_message:
                    # Parse JSON
                    try:
                        game_data = json.loads(raw_message)
                    except json.JSONDecodeError as e:
                        logger.error(
                            f"Invalid JSON from queue | error={str(e)} | "
                            f"message_preview={raw_message[:100]} | "
                            f"action=message_kept_in_queue_saving"
                        )
                        continue

                    # Transform data (moved from BatchProcessor)
                    try:
                        transformed_data = transform_data(game_data, date_parser)

                        # Add both transformed data AND raw JSON to buffer
                        processor.add_to_buffer(transformed_data, raw_message)

                    except Exception as e:
                        game_id = game_data.get("game_id", "unknown")
                        logger.error(
                            f"Transformation failed | game_id={game_id} | error={str(e)} | "
                            f"action=message_kept_in_queue_saving"
                        )
                        continue

                # Check if we need to flush due to timeout
                elif processor.should_flush():
                    processor.flush_buffer()

            except redis.ConnectionError as e:
                logger.error(f"Redis connection lost | error={str(e)}")
                # Try to reconnect
                redis_client = connect_redis(config)
                # Re-initialize processor with new client
                processor = BatchProcessor(config, redis_client)

            except Exception as e:
                logger.error(f"Unexpected error in consumer loop | error={str(e)}")
                # Continue processing despite errors

    finally:
        # Graceful shutdown: flush remaining buffer
        logger.info("Flushing remaining buffer before shutdown...")
        try:
            processor.flush_buffer()
        except Exception as e:
            logger.error(f"Failed to flush buffer on shutdown | error={str(e)}")

        # Log final statistics
        stats = processor.get_statistics()
        logger.info(
            f"Shutdown complete | processed={stats['total_processed']} | "
            f"inserted={stats['total_inserted']} | failed={stats['total_failed']}"
        )

        # Close Redis connection
        try:
            redis_client.close()
        except:
            pass


def main():
    """Main entry point."""
    global logger

    try:
        # Load configuration
        config = Config()

        # Setup logging
        setup_logging(config)

        logger.info("=" * 60)
        logger.info("DB Writer starting...")
        logger.info(f"Configuration: {config}")
        logger.info("=" * 60)

        # Register signal handlers
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        logger.info("Signal handlers registered | signals=[SIGINT, SIGTERM]")

        # Initialize database
        database_url = config.get_database_url()
        init_db(database_url, echo=config.DB_ECHO)
        logger.info(f"Database initialized | host={config.POSTGRES_HOST} | db={config.POSTGRES_DB}")

        # Start consumer loop
        consumer_loop(config)

    except KeyboardInterrupt:
        logger.info("Interrupted by user (Ctrl+C)")

    except Exception as e:
        if 'logger' in globals():
            logger.error(f"Fatal error | error={str(e)}", exc_info=True)
        else:
            print(f"Fatal error: {e}", file=sys.stderr)
        sys.exit(1)

    logger.info("DB Writer stopped")


if __name__ == "__main__":
    main()
