"""
Utility module to test SMTP connectivity and troubleshoot email issues
"""
import sys
import smtplib
import ssl
import socket
import time
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from config.config import Config
from utils.logger import setup_logger

# Enable console logging for this utility
logger = setup_logger("EmailTest", console_output=True)

def test_smtp_connection():
    """
    Test SMTP server connection with both SSL and TLS methods
    """
    logger.info(f"Testing SMTP connection to {Config.SMTP_SERVER}...")
    
    # Test socket connectivity first
    logger.info(f"Testing basic socket connectivity to {Config.SMTP_SERVER}:{Config.SMTP_PORT}...")
    try:
        sock = socket.create_connection((Config.SMTP_SERVER, Config.SMTP_PORT), timeout=10)
        sock.close()
        logger.info("✅ Socket connection successful")
    except Exception as e:
        logger.error(f"❌ Socket connection failed: {e}")
        logger.info("This suggests network/firewall issues or incorrect server/port")
    
    # Test SSL connection (port 465)
    try:
        context = ssl.create_default_context()
        with smtplib.SMTP_SSL(Config.SMTP_SERVER, 465, timeout=10, context=context) as server:
            logger.info("✅ SSL connection successful")
            
            # Try authentication
            try:
                server.login(Config.EMAIL_USER, Config.EMAIL_PASS)
                logger.info("✅ Authentication successful via SSL")
            except Exception as e:
                logger.error(f"❌ Authentication failed via SSL: {e}")
    except Exception as e:
        logger.error(f"❌ SSL connection failed: {e}")
    
    # Test TLS connection (port 587)
    try:
        with smtplib.SMTP(Config.SMTP_SERVER, 587, timeout=10) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            logger.info("✅ TLS connection successful")
            
            # Try authentication
            try:
                server.login(Config.EMAIL_USER, Config.EMAIL_PASS)
                logger.info("✅ Authentication successful via TLS")
            except Exception as e:
                logger.error(f"❌ Authentication failed via TLS: {e}")
    except Exception as e:
        logger.error(f"❌ TLS connection failed: {e}")

def send_test_email(recipient):
    """
    Send a test email to verify full email delivery
    """
    logger.info(f"Sending test email to {recipient} from {Config.EMAIL_USER}")
    
    msg = MIMEMultipart()
    msg["Subject"] = "HunchBank Test Email"
    msg["From"] = Config.EMAIL_USER
    msg["To"] = recipient
    msg["Date"] = time.strftime("%a, %d %b %Y %H:%M:%S +0000", time.gmtime())
    msg["Message-ID"] = f"<{time.time()}.{id(msg)}@hunchbank.example.com>"
    
    body = """
    This is a test email from HunchBank Auto Email Support.
    
    If you received this email, email delivery is working correctly.
    
    Time: {}
    """.format(time.strftime("%Y-%m-%d %H:%M:%S"))
    
    msg.attach(MIMEText(body, "plain"))
    
    # Try SSL first (recommended for Gmail)
    if Config.USE_SMTP_SSL:
        try:
            with smtplib.SMTP_SSL(Config.SMTP_SERVER, Config.SMTP_PORT, timeout=Config.SMTP_TIMEOUT) as server:
                server.ehlo()
                server.login(Config.EMAIL_USER, Config.EMAIL_PASS)
                server.send_message(msg)
                logger.info("✅ Test email sent successfully via SSL")
                return True
        except Exception as e:
            logger.error(f"❌ Failed to send via SSL: {e}")
    
    # Try TLS as fallback
    try:
        with smtplib.SMTP(Config.SMTP_SERVER, 587, timeout=Config.SMTP_TIMEOUT) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(Config.EMAIL_USER, Config.EMAIL_PASS)
            server.send_message(msg)
            logger.info("✅ Test email sent successfully via TLS")
            return True
    except Exception as e:
        logger.error(f"❌ Failed to send via TLS: {e}")
    
    return False

def test_fallback_smtp():
    """Test connectivity to fallback SMTP server"""
    if not Config.FALLBACK_SMTP_SERVER:
        logger.info("No fallback SMTP server configured")
        return
        
    logger.info(f"Testing fallback SMTP server {Config.FALLBACK_SMTP_SERVER}...")
    
    # Test socket connectivity first
    try:
        sock = socket.create_connection(
            (Config.FALLBACK_SMTP_SERVER, Config.FALLBACK_SMTP_PORT), 
            timeout=10
        )
        sock.close()
        logger.info("✅ Fallback socket connection successful")
    except Exception as e:
        logger.error(f"❌ Fallback socket connection failed: {e}")
    
    # Try actual SMTP connection
    try:
        with smtplib.SMTP(
            Config.FALLBACK_SMTP_SERVER, 
            Config.FALLBACK_SMTP_PORT, 
            timeout=10
        ) as server:
            server.ehlo()
            if Config.FALLBACK_SMTP_USE_TLS:
                server.starttls()
                server.ehlo()
            
            fallback_user = Config.FALLBACK_SMTP_USER or Config.EMAIL_USER
            fallback_pass = Config.FALLBACK_SMTP_PASS or Config.EMAIL_PASS
            
            try:
                server.login(fallback_user, fallback_pass)
                logger.info("✅ Fallback authentication successful")
            except Exception as e:
                logger.error(f"❌ Fallback authentication failed: {e}")
    except Exception as e:
        logger.error(f"❌ Fallback connection failed: {e}")

def display_config():
    """Display current email configuration"""
    logger.info("===== EMAIL CONFIGURATION =====")
    logger.info(f"Primary SMTP: {Config.SMTP_SERVER}:{Config.SMTP_PORT}")
    logger.info(f"Use SSL: {Config.USE_SMTP_SSL}, Use TLS: {Config.SMTP_USE_TLS}")
    logger.info(f"Email User: {Config.EMAIL_USER}")
    logger.info(f"Fallback SMTP: {Config.FALLBACK_SMTP_SERVER}:{Config.FALLBACK_SMTP_PORT}")
    logger.info(f"SMTP Timeout: {Config.SMTP_TIMEOUT} seconds")
    logger.info(f"Max Retries: {Config.MAX_RETRIES}")
    logger.info("===========================")

if __name__ == "__main__":
    display_config()
    test_smtp_connection()
    test_fallback_smtp()
    
    if len(sys.argv) > 1:
        recipient = sys.argv[1]
        send_test_email(recipient)
    else:
        logger.info("To send a test email, provide recipient email as argument:")
        logger.info("python -m utils.email_test your.email@example.com")