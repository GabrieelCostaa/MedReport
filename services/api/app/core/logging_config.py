"""
Structured logging with structlog + OpenTelemetry trace ID correlation.

Provides:
  - JSON-formatted logs in production (machine-readable)
  - Colored console output in development
  - Automatic trace_id injection from OpenTelemetry
  - Request context (user_id, path, method) in every log line
"""
import logging
import os
import sys

import structlog


def setup_logging():
    """
    Configure structlog for the application.
    Call this once at startup (in main.py lifespan).
    """
    is_dev = os.environ.get("ENV", "development") == "development"

    # Shared processors
    shared_processors = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.UnicodeDecoder(),
    ]

    # Add OpenTelemetry trace ID if available (optional dependency)
    try:
        from opentelemetry import trace as otel_trace

        def add_otel_context(logger, method_name, event_dict):
            span = otel_trace.get_current_span()
            if span and span.get_span_context().is_valid:
                ctx = span.get_span_context()
                event_dict["trace_id"] = format(ctx.trace_id, "032x")
                event_dict["span_id"] = format(ctx.span_id, "016x")
            return event_dict

        shared_processors.append(add_otel_context)
    except (ImportError, Exception):
        pass

    if is_dev:
        # Development: colored console output
        renderer = structlog.dev.ConsoleRenderer(colors=True)
    else:
        # Production: JSON output
        renderer = structlog.processors.JSONRenderer()

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    # Configure stdlib logging to use structlog
    formatter = structlog.stdlib.ProcessorFormatter(
        processor=renderer,
        foreign_pre_chain=shared_processors,
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(logging.INFO)

    # Quiet noisy libraries
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("openai").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)


def setup_opentelemetry(app):
    """
    Instrument FastAPI with OpenTelemetry.
    Call after app creation in main.py.
    """
    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

        FastAPIInstrumentor.instrument_app(app)
        logging.getLogger(__name__).info("OpenTelemetry FastAPI instrumentation enabled")
    except ImportError:
        logging.getLogger(__name__).debug("OpenTelemetry instrumentation not available")
    except Exception as e:
        logging.getLogger(__name__).warning("OpenTelemetry setup failed: %s", e)
