#!/usr/bin/env python3
"""
Test script for the updated email service with improved fallback
"""
from services.response_service import ResponseService
from config.config import Config

def test_improved_email_service():
    """Test the fixed email service with SSL and TLS fallback"""
    print("\n===== TESTING IMPROVED EMAIL SERVICE =====")
    
    # Create response service
    service = ResponseService()
    
    # Test sending to self
    recipient = Config.EMAIL_USER
    print(f"Testing email to: {recipient}")
    
    # Create a test response
    test_response = {
        "subject": "HunchBank Email Service Test",
        "body": "This is a test email to verify the improved email service with SSL/TLS fallback.\n\n" +
                "If you receive this email, the service is working correctly."
    }
    
    # Send the email with our improved service
    print("Sending email using dual-mode system (SSL first, TLS fallback)...")
    result = service.send_email(recipient, test_response)
    
    if result:
        print("✅ SUCCESS: Email sent successfully!")
        print("The email system is now using a robust fallback approach:")
        print("1. First tries SSL on port 465 (most reliable for Gmail)")
        print("2. Falls back to TLS on port 587 if SSL fails")
        print("This ensures maximum compatibility across different email providers and network conditions.")
    else:
        print("❌ ERROR: Email sending failed with both methods.")
        print("Please check your email credentials and internet connection.")
    
    return result

def test_ssl_explicitly():
    """Explicitly test just the SSL method"""
    print("\n===== TESTING SSL CONNECTION ONLY =====")
    service = ResponseService()
    
    # Create a test message
    test_response = {
        "subject": "HunchBank SSL Test",
        "body": "This test confirms the SSL connection on port 465 is working."
    }
    
    # Try the SSL method directly
    result = service._try_ssl_connection(
        service.create_message(Config.EMAIL_USER, test_response),
        Config.EMAIL_USER
    )
    
    if result:
        print("✅ SSL on port 465: SUCCESS")
    else:
        print("❌ SSL on port 465: FAILED")
    
    return result

def test_tls_explicitly():
    """Explicitly test just the TLS method"""
    print("\n===== TESTING TLS CONNECTION ONLY =====")
    service = ResponseService()
    
    # Create a test message
    test_response = {
        "subject": "HunchBank TLS Test",
        "body": "This test confirms the TLS connection on port 587 is working."
    }
    
    # Try the TLS method directly
    result = service._try_tls_connection(
        service.create_message(Config.EMAIL_USER, test_response),
        Config.EMAIL_USER
    )
    
    if result:
        print("✅ TLS on port 587: SUCCESS")
    else:
        print("❌ TLS on port 587: FAILED")
    
    return result

if __name__ == "__main__":
    print(f"Using email: {Config.EMAIL_USER}")
    
    # Add helper method to create message to ResponseService
    def create_message(self, recipient, response):
        """Helper to create a message from a response dict"""
        if isinstance(response, str):
            try:
                parts = response.split("\n\n", 1)
                subject = parts[0].replace("Subject: ", "")
                body = parts[1] if len(parts) > 1 else ""
            except Exception:
                subject = "Your Request Has Been Received"
                body = response
        else:
            subject = response.get("subject", "Your Request Has Been Received")
            body = response.get("body", "We've received your request.")

        msg = MIMEMultipart()
        msg["Subject"] = subject
        msg["From"] = self.email_user
        msg["To"] = recipient
        msg["Date"] = time.strftime("%a, %d %b %Y %H:%M:%S +0000", time.gmtime())
        msg["Message-ID"] = f"<{time.time()}.{id(msg)}@hunchbank.example.com>"
        text_part = MIMEText(body, "plain")
        msg.attach(text_part)
        return msg
        
    # Add the helper method to the ResponseService class
    import types
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart
    import time
    ResponseService.create_message = types.MethodType(create_message, ResponseService())
    
    # Run the combined test
    test_improved_email_service()
    
    # Run individual tests if desired
    # test_ssl_explicitly()
    # test_tls_explicitly()