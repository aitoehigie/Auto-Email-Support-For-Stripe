import os
import sys
from dotenv import load_dotenv
from utils.logger import setup_logger

# Create logger before config is fully loaded
logger = setup_logger("Config")

# Load environment variables from .env file
if not load_dotenv():
    logger.warning("No .env file found or could not be loaded. Using environment variables.")

class Config:
    # Email configuration
    EMAIL_SERVER = os.getenv("EMAIL_SERVER", "imap.gmail.com")
    EMAIL_USER = os.getenv("EMAIL_USER")
    EMAIL_PASS = os.getenv("EMAIL_PASS")
    
    # SMTP configuration - supports both SSL and TLS approaches
    # Our implementation will try SSL on port 465 first,
    # then fall back to TLS on port 587 if needed
    SMTP_SERVER = os.getenv("SMTP_SERVER", "smtp.gmail.com")
    SMTP_PORT = int(os.getenv("SMTP_PORT", 465))  # Default to SSL port
    SMTP_USE_TLS = os.getenv("SMTP_USE_TLS", "false").lower() == "true"  # Default: don't use TLS with SSL
    SMTP_TIMEOUT = int(os.getenv("SMTP_TIMEOUT", 60))  # Longer timeout for more reliable connections
    
    # SSL config (port 465) - primary method
    USE_SMTP_SSL = os.getenv("USE_SMTP_SSL", "true").lower() == "true"  # Default to SSL
    
    # Fallback SMTP configs - default to same as primary as a safety measure
    FALLBACK_SMTP_SERVER = os.getenv("FALLBACK_SMTP_SERVER", SMTP_SERVER) 
    FALLBACK_SMTP_PORT = int(os.getenv("FALLBACK_SMTP_PORT", SMTP_PORT))
    FALLBACK_SMTP_USE_TLS = os.getenv("FALLBACK_SMTP_USE_TLS", "true" if SMTP_USE_TLS else "false").lower() == "true"
    # Use same credentials unless specifically overridden
    FALLBACK_SMTP_USER = os.getenv("FALLBACK_SMTP_USER", EMAIL_USER)
    FALLBACK_SMTP_PASS = os.getenv("FALLBACK_SMTP_PASS", EMAIL_PASS)
    
    # API keys
    STRIPE_API_KEY = os.getenv("STRIPE_API_KEY")
    NLP_API_KEY = os.getenv("NLP_API_KEY")
    
    # Application settings
    CONFIDENCE_THRESHOLD = float(os.getenv("CONFIDENCE_THRESHOLD", 0.9))
    EMAIL_CHECK_INTERVAL = int(os.getenv("EMAIL_CHECK_INTERVAL", 60))  # seconds
    EMAIL_BATCH_SIZE = int(os.getenv("EMAIL_BATCH_SIZE", 100))
    MAX_RETRIES = int(os.getenv("MAX_RETRIES", 3))
    RETRY_DELAY = int(os.getenv("RETRY_DELAY", 2))  # seconds
    
    # Database settings
    USE_DATABASE = os.getenv("USE_DATABASE", "true").lower() == "true"
    DATABASE_PATH = os.getenv("DATABASE_PATH", None)  # None uses default path
    DATABASE_METRICS_INTERVAL = int(os.getenv("DATABASE_METRICS_INTERVAL", 60))  # seconds
    DATABASE_RETAIN_DAYS = int(os.getenv("DATABASE_RETAIN_DAYS", 90))  # days to keep data

# Validate required configuration
required_configs = [
    ("EMAIL_USER", Config.EMAIL_USER),
    ("EMAIL_PASS", Config.EMAIL_PASS),
    ("STRIPE_API_KEY", Config.STRIPE_API_KEY),
    ("NLP_API_KEY", Config.NLP_API_KEY)
]

missing_configs = [name for name, value in required_configs if not value]
if missing_configs:
    logger.error(f"Missing required environment variables: {', '.join(missing_configs)}")
    logger.error("Please set these in your .env file or environment variables")
    # Don't exit if running tests
    if not any('pytest' in arg for arg in sys.argv):
        sys.exit(1)
