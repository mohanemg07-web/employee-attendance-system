"""
Structured JSON logging setup for production.
"""
import logging
import json
from datetime import datetime, timezone

class JSONFormatter(logging.Formatter):
    """
    Custom formatter that outputs log records as structured JSON.
    """
    def format(self, record: logging.LogRecord) -> str:
        log_obj = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "message": record.getMessage(),
            "logger": record.name,
            "endpoint": getattr(record, "endpoint", "N/A"),
            "user_id": getattr(record, "user_id", "N/A"),
        }
        
        if record.exc_info:
            log_obj["exception"] = self.formatException(record.exc_info)
            
        return json.dumps(log_obj)

def setup_json_logging():
    """
    Configures the root logger to output structured JSON.
    Call this early in the application lifecycle (e.g., in main.py).
    """
    root_logger = logging.getLogger()
    
    # Remove any existing handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
        
    # Create console handler with JSON formatter
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(JSONFormatter())
    
    root_logger.addHandler(console_handler)
    root_logger.setLevel(logging.INFO)
    
    # Silence overly verbose loggers if needed
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
