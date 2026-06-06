"""
Logging configuration for Kubernetes Platform Engineer MCP Server.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import loguru


import logging
import logging.handlers
import sys
from pathlib import Path
from typing import Optional

from loguru import logger


def setup_logging(
    level: str = "INFO",
    file_path: Optional[str] = None,
    max_size: str = "10MB",
    backup_count: int = 5,
    format_string: Optional[str] = None
) -> None:
    """
    Setup comprehensive logging for the MCP server.
    
    Args:
        level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        file_path: Optional file path for log output
        max_size: Maximum size of log files before rotation
        backup_count: Number of backup files to keep
        format_string: Custom format string for log messages
    """
    
    # Clear any existing handlers
    logging.getLogger().handlers.clear()
    logger.remove()
    
    # Setup console logging with Rich for beautiful output
        
    # Default format
    if format_string is None:
        format_string = "{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} | {message}"
    
    # Add console handler with Rich
    logger.add(
        sys.stderr,
        level=level,
        format=format_string,
        colorize=True,
        backtrace=True,
        diagnose=True
    )
    
    # Add file handler if specified
    if file_path:
        log_path = Path(file_path)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        
        logger.add(
            str(log_path),
            level=level,
            format=format_string,
            rotation=max_size,
            retention=backup_count,
            compression="gz",
            backtrace=True,
            diagnose=True
        )
    
    # Setup standard library logging to work with loguru
    class InterceptHandler(logging.Handler):
        """Intercept standard logging and redirect to loguru."""
        
        def emit(self, record: logging.LogRecord) -> None:
            # Get corresponding Loguru level if it exists
            try:
                level = logger.level(record.levelname).name
            except ValueError:
                level = record.levelno
            
            # Find caller from where originated the logged message
            frame, depth = logging.currentframe(), 2
            while frame.f_code.co_filename == logging.__file__:
                frame = frame.f_back
                depth += 1
            
            logger.opt(depth=depth, exception=record.exc_info).log(
                level, record.getMessage()
            )
    
    # Configure standard library logging
    logging.basicConfig(handlers=[InterceptHandler()], level=0, force=True)
    
    # Configure specific loggers
    loggers_to_configure = [
        "kubernetes",
        "urllib3",
        "httpx",
        "asyncio",
        "uvicorn",
        "fastapi"
    ]
    
    for logger_name in loggers_to_configure:
        logging.getLogger(logger_name).handlers = [InterceptHandler()]
        logging.getLogger(logger_name).propagate = False
    
    logger.info(f"Logging initialized - Level: {level}, File: {file_path or 'Console only'}")


def get_logger(name: str) -> "loguru.Logger":
    """
    Get a configured logger instance.
    
    Args:
        name: Logger name (usually __name__)
        
    Returns:
        Configured logger instance
    """
    return logger.bind(name=name)


# Kubernetes-specific logging helpers
def log_k8s_operation(operation: str, resource: str, namespace: str = None, **kwargs):
    """Log Kubernetes operations with structured data."""
    log_data = {
        "operation": operation,
        "resource": resource,
        "namespace": namespace,
        **kwargs
    }
    logger.bind(**log_data).info(f"K8s Operation: {operation} {resource}")


def log_diagnostic_result(diagnostic_type: str, status: str, details: dict = None):
    """Log diagnostic results with structured data."""
    log_data = {
        "diagnostic_type": diagnostic_type,
        "status": status,
        "details": details or {}
    }
    logger.bind(**log_data).info(f"Diagnostic: {diagnostic_type} - {status}")


def log_performance_metric(metric_name: str, value: float, unit: str = None, **tags):
    """Log performance metrics with structured data."""
    log_data = {
        "metric_name": metric_name,
        "value": value,
        "unit": unit,
        **tags
    }
    logger.bind(**log_data).info(f"Metric: {metric_name}={value}{unit or ''}")


def log_security_event(event_type: str, severity: str, details: dict = None):
    """Log security events with structured data."""
    log_data = {
        "event_type": event_type,
        "severity": severity,
        "details": details or {}
    }
    logger.bind(**log_data).warning(f"Security Event: {event_type} - {severity}")


# Exception logging helpers
def log_k8s_error(operation: str, error: Exception, **context):
    """Log Kubernetes-related errors with context."""
    logger.bind(operation=operation, **context).opt(exception=error).error(
        f"K8s Error in {operation}: {error}"
    )


def log_diagnostic_error(diagnostic_type: str, error: Exception, **context):
    """Log diagnostic errors with context."""
    logger.bind(diagnostic_type=diagnostic_type, **context).opt(exception=error).error(
        f"Diagnostic Error in {diagnostic_type}: {error}"
    )
