import logging
import os
from logging.handlers import RotatingFileHandler
import sys
import traceback

def setup_logger(name, log_file="payment_update.log", log_level=logging.INFO, console_output=False):
    """
    Configure a logger with file output and optional console output
    
    Args:
        name (str): Logger name
        log_file (str): Path to log file
        log_level (int): Logging level (default: INFO)
        console_output (bool): Whether to output logs to console (default: False)
        
    Returns:
        logging.Logger: Configured logger
    """
    logger = logging.getLogger(name)
    logger.setLevel(log_level)
    
    # Only add handlers if they don't exist already
    if not logger.handlers:
        # Create logs directory if it doesn't exist
        log_dir = os.path.dirname(log_file)
        if log_dir and not os.path.exists(log_dir):
            try:
                os.makedirs(log_dir)
            except Exception as e:
                print(f"Warning: Could not create log directory {log_dir}: {e}")
        
        # Create formatter
        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )
        
        # File handler with rotation (10 MB max file size, keep 5 backups)
        try:
            file_handler = RotatingFileHandler(
                log_file, maxBytes=10*1024*1024, backupCount=5
            )
            file_handler.setFormatter(formatter)
            logger.addHandler(file_handler)
        except Exception as e:
            print(f"Warning: Could not set up file logging: {e}")
        
        # Console handler (only if explicitly enabled)
        if console_output:
            console_handler = logging.StreamHandler(sys.stdout)
            console_handler.setFormatter(formatter)
            logger.addHandler(console_handler)
    
    return logger

def log_exception(logger, e, context=""):
    """
    Log an exception with traceback
    
    Args:
        logger (logging.Logger): Logger to use
        e (Exception): Exception to log
        context (str): Additional context about where/why the exception occurred
    """
    error_msg = f"{context}: {str(e)}" if context else str(e)
    tb = traceback.format_exc()
    logger.error(f"{error_msg}\n{tb}")
    
class LogCapture:
    """Context manager to capture logs for a specific operation"""
    
    def __init__(self, logger, operation_name):
        self.logger = logger
        self.operation_name = operation_name
        
    def __enter__(self):
        self.logger.info(f"Starting: {self.operation_name}")
        return self
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type:
            self.logger.error(f"Failed: {self.operation_name} - {exc_val}")
        else:
            self.logger.info(f"Completed: {self.operation_name}")
        return False  # Don't suppress exceptions
