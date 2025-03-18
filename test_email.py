#!/usr/bin/env python3
"""
Test script for SMTP email configuration
"""
import smtplib
import ssl
import time
import sys
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from config.config import Config
from datetime import datetime

def test_gmail_ports():
    """Test multiple SMTP configurations for Gmail compatibility"""
    print("\n===== TESTING GMAIL SMTP CONFIGURATIONS =====")
    
    # Create test message
    msg = MIMEMultipart()
    msg["Subject"] = "HunchBank Email Test"
    msg["From"] = Config.EMAIL_USER
    msg["To"] = Config.EMAIL_USER  # Send to self
    msg["Date"] = time.strftime("%a, %d %b %Y %H:%M:%S +0000", time.gmtime())
    msg["Message-ID"] = f"<{time.time()}.{id(msg)}@hunchbank.test.local>"
    msg.attach(MIMEText(f"This is a test email sent at {datetime.now()}", "plain"))
    
    # Test configurations
    configs = [
        {"port": 587, "use_ssl": False, "use_tls": True, "desc": "TLS on port 587 (standard)"},
        {"port": 465, "use_ssl": True, "use_tls": False, "desc": "SSL on port 465 (legacy)"},
        {"port": 25, "use_ssl": False, "use_tls": True, "desc": "TLS on port 25 (alternate)"},
    ]
    
    successes = 0
    
    # Try each configuration
    for config in configs:
        print(f"\nTesting: {config['desc']}")
        print(f"Server: {Config.SMTP_SERVER}:{config['port']}")
        print(f"SSL: {config['use_ssl']}, TLS: {config['use_tls']}")
        
        try:
            if config["use_ssl"]:
                # Use SSL
                print("Connecting with SSL...")
                with smtplib.SMTP_SSL(
                    Config.SMTP_SERVER, 
                    config["port"],
                    timeout=10
                ) as server:
                    print("Connected. Sending EHLO...")
                    server.ehlo()
                    print("Authenticating...")
                    server.login(Config.EMAIL_USER, Config.EMAIL_PASS)
                    print("Sending message...")
                    server.send_message(msg)
                    print("✅ SUCCESS: Message sent via SSL")
                    successes += 1
            else:
                # Use standard SMTP with optional TLS
                print("Connecting with standard SMTP...")
                with smtplib.SMTP(
                    Config.SMTP_SERVER,
                    config["port"],
                    timeout=10
                ) as server:
                    server.set_debuglevel(1)  # Enable debugging
                    print("Connected. Sending EHLO...")
                    server.ehlo()
                    
                    if config["use_tls"]:
                        print("Starting TLS...")
                        server.starttls()
                        print("TLS started. Sending EHLO again...")
                        server.ehlo()
                    
                    print("Authenticating...")
                    server.login(Config.EMAIL_USER, Config.EMAIL_PASS)
                    print("Sending message...")
                    server.send_message(msg)
                    print("✅ SUCCESS: Message sent via SMTP+TLS")
                    successes += 1
                    
        except ssl.SSLError as e:
            print(f"❌ SSL ERROR: {str(e)}")
            print("This usually means you're trying to use SSL on a port that doesn't support it")
            
        except smtplib.SMTPAuthenticationError as e:
            print(f"❌ AUTHENTICATION ERROR: {str(e)}")
            print("This usually means invalid username/password or")
            print("you need to enable 'Less secure app access' or create an App Password for Gmail")
            
        except Exception as e:
            print(f"❌ ERROR: {str(e)}")
            
        print("-" * 50)
    
    print(f"\nResults: {successes} of {len(configs)} configurations succeeded")
    if successes == 0:
        print("\nTROUBLESHOOTING FOR GMAIL:")
        print("1. Check that your Gmail credentials are correct")
        print("2. If using your regular password, enable 'Less secure app access' at:")
        print("   https://myaccount.google.com/lesssecureapps")
        print("3. If you have 2-factor authentication, create an App Password at:")
        print("   https://myaccount.google.com/apppasswords")
        print("4. Check if your account has been temporarily locked due to suspicious activity")
        print("5. Try logging in through a browser to see if there are any security prompts")
        
    return successes > 0
    
if __name__ == "__main__":
    print(f"Email User: {Config.EMAIL_USER}")
    test_gmail_ports()