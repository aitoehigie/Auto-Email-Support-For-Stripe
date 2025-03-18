import smtplib
import ssl
import time
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from config.config import Config
from utils.logger import setup_logger
from services.stripe_service import StripeService

class ResponseService:
    def __init__(self):
        self.logger = setup_logger("ResponseService", console_output=False)
        
        # Primary email config
        self.email_user = Config.EMAIL_USER
        self.email_pass = Config.EMAIL_PASS
        self.smtp_server = Config.SMTP_SERVER
        self.smtp_port = Config.SMTP_PORT
        self.use_tls = Config.SMTP_USE_TLS
        self.use_ssl = Config.USE_SMTP_SSL
        
        # Fallback config
        self.fallback_smtp_server = Config.FALLBACK_SMTP_SERVER
        self.fallback_smtp_port = Config.FALLBACK_SMTP_PORT
        self.fallback_use_tls = Config.FALLBACK_SMTP_USE_TLS
        self.fallback_smtp_user = Config.FALLBACK_SMTP_USER or self.email_user
        self.fallback_smtp_pass = Config.FALLBACK_SMTP_PASS or self.email_pass
        
        # Retry settings
        self.max_retries = Config.MAX_RETRIES
        self.retry_delay = Config.RETRY_DELAY
        
        self.stripe_service = StripeService()
        
        # Debug startup config
        self.logger.info(f"Email configured: server={self.smtp_server}:{self.smtp_port}, SSL={self.use_ssl}, TLS={self.use_tls}")

    def generate_response(self, intent, success, message, customer_email):
        """
        Generate an email response based on intent and outcome
        
        Args:
            intent (str): The customer's intent (e.g., "update_payment_method")
            success (bool): Whether the operation was successful
            message (str): Detailed message about the operation
            customer_email (str): Customer's email address
            
        Returns:
            dict: Email template with subject and body
        """
        templates = {
            "update_payment_method": {
                "success": {
                    "subject": "Payment Method Updated",
                    "body": """Dear Customer,

Your payment method has been successfully updated. The changes will be applied to all future transactions.

If you have any questions or didn't authorize this change, please contact us immediately.

Best regards,
HunchBank Support Team"""
                },
                "failure": {
                    "subject": "Issue Updating Payment Method",
                    "body": """Dear Customer,

We encountered an issue updating your payment method: {message}

{payment_link_text}

If you need further assistance, please reply to this email with additional details.

Best regards,
HunchBank Support Team"""
                }
            },
            "billing_inquiry": {
                "success": {
                    "subject": "Your Billing Inquiry",
                    "body": """Dear Customer,

Thank you for your inquiry about your billing. {message}

If you have any further questions, please don't hesitate to contact us.

Best regards,
HunchBank Support Team"""
                },
                "failure": {
                    "subject": "Regarding Your Billing Inquiry",
                    "body": """Dear Customer,

We're looking into your billing inquiry, but we need a bit more information: {message}

Please reply to this email with the additional details so we can assist you further.

Best regards,
HunchBank Support Team"""
                }
            },
            "subscription_change": {
                "success": {
                    "subject": "Subscription Change Confirmation",
                    "body": """Dear Customer,

Your subscription has been successfully updated. {message}

You will see these changes reflected in your account immediately and on your next invoice.

Best regards,
HunchBank Support Team"""
                },
                "failure": {
                    "subject": "Issue Updating Your Subscription",
                    "body": """Dear Customer,

We encountered an issue updating your subscription: {message}

Please contact our support team if you need further assistance.

Best regards,
HunchBank Support Team"""
                }
            },
            "subscription_cancel": {
                "success": {
                    "subject": "Subscription Cancellation Confirmation",
                    "body": """Dear Customer,

Your cancellation request has been processed. {message}

We're sorry to see you go. If you change your mind or have any questions about your cancellation, please don't hesitate to contact us.

Best regards,
HunchBank Support Team"""
                },
                "failure": {
                    "subject": "Issue Cancelling Your Subscription",
                    "body": """Dear Customer,

We encountered an issue processing your cancellation request: {message}

Please contact our support team for immediate assistance with your cancellation.

Best regards,
HunchBank Support Team"""
                }
            },
            "refund_request": {
                "success": {
                    "subject": "Refund Request Processed",
                    "body": """Dear Customer,

Your refund request has been processed. {message}

Please note that it may take 5-10 business days for the refund to appear on your statement, depending on your bank.

Best regards,
HunchBank Support Team"""
                },
                "failure": {
                    "subject": "Refund Request Received",
                    "body": """Dear Customer,

We've received your refund request. {message}

Our team will review your request and get back to you within 1-2 business days.

Best regards,
HunchBank Support Team"""
                }
            },
            "payment_dispute": {
                "success": {
                    "subject": "Payment Dispute Update",
                    "body": """Dear Customer,

Regarding your payment dispute: {message}

If you have any questions or need to provide additional information, please reply to this email.

Best regards,
HunchBank Support Team"""
                },
                "failure": {
                    "subject": "Payment Dispute Received",
                    "body": """Dear Customer,

We've received your dispute request. {message}

Our team will investigate this matter and contact you within 1-2 business days.

Best regards,
HunchBank Support Team"""
                }
            },
            "unknown": {
                "success": {
                    "subject": "Your Request Has Been Received",
                    "body": """Dear Customer,

Thank you for contacting HunchBank support. We've received your message and will get back to you shortly.

Best regards,
HunchBank Support Team"""
                },
                "failure": {
                    "subject": "We Need More Information",
                    "body": """Dear Customer,

Thank you for contacting HunchBank support. We need a bit more information to properly assist you.

Please provide additional details about your request so we can help you more effectively.

Best regards,
HunchBank Support Team"""
                }
            }
        }
        
        try:
            # Get the appropriate template
            template_dict = templates.get(intent, templates.get("unknown", {}))
            status = "success" if success else "failure"
            template = template_dict.get(status, templates["unknown"][status])
            
            # For payment method failures, check if we can generate a secure link
            payment_link_text = ""
            if intent == "update_payment_method" and not success:
                customer_id = self.stripe_service.get_customer_by_email(customer_email)
                if customer_id:
                    payment_link = self.stripe_service.create_payment_link(customer_id)
                    if payment_link:
                        payment_link_text = f"For security, please use this secure link to update your payment method: {payment_link}"
                    else:
                        payment_link_text = "Our team will send you a secure link separately to update your payment method."
                else:
                    payment_link_text = "Please contact customer support directly for assistance with your payment method."
            
            # Format the body with any placeholder values
            body = template["body"].format(message=message, payment_link_text=payment_link_text)
            subject = template["subject"]
            
            self.logger.info(f"Generated '{subject}' response for {intent}")
            return {"subject": subject, "body": body}
            
        except Exception as e:
            self.logger.error(f"Response generation failed: {str(e)}")
            return {
                "subject": "Your Request Has Been Received",
                "body": "We've received your request and will get back to you as soon as possible."
            }

    def send_email(self, customer_email, response):
        """
        Send email to customer with retry logic and multiple provider fallbacks
        
        Args:
            customer_email (str): Recipient email address
            response (dict or str): Response containing subject and body, or legacy format string
            
        Returns:
            bool: True if email was sent successfully, False otherwise
        """
        # Support both new (dict) and old (string) response formats
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

        # Create message once to reuse
        msg = MIMEMultipart()
        msg["Subject"] = subject
        msg["From"] = self.email_user
        msg["To"] = customer_email
        msg["Date"] = time.strftime("%a, %d %b %Y %H:%M:%S +0000", time.gmtime())
        
        # Add message ID for better deliverability
        msg["Message-ID"] = f"<{time.time()}.{id(msg)}@hunchbank.example.com>"
        
        # Attach text body
        text_part = MIMEText(body, "plain")
        msg.attach(text_part)
        
        # Try primary server first
        primary_success = self._try_send_with_primary(msg, customer_email)
        if primary_success:
            return True
            
        # Try fallback on failure
        fallback_success = self._try_send_with_fallback(msg, customer_email)
        if fallback_success:
            return True
            
        # If all attempts fail, log final error
        self.logger.error(f"All email attempts failed for {customer_email}")
        return False
        
    def _try_send_with_primary(self, msg, customer_email):
        """Try sending with primary SMTP server using SSL on port 465 (confirmed working with Gmail)"""
        self.logger.info(f"Attempting to send email to {customer_email} via primary server")
        
        # First, try SSL on port 465 (most reliable for Gmail)
        if self._try_ssl_connection(msg, customer_email):
            return True
            
        # If SSL fails, return false and let fallback try a different approach
        return False
    
    def _try_ssl_connection(self, msg, customer_email):
        """Helper method to try sending via SSL on port 465"""
        # Use SSL on port 465 which usually works best for Gmail
        port = 465
        
        for attempt in range(self.max_retries):
            try:
                self.logger.info(f"Using SMTP+SSL connection to {self.smtp_server}:{port}")
                with smtplib.SMTP_SSL(
                    self.smtp_server, 
                    port, 
                    timeout=Config.SMTP_TIMEOUT
                ) as server:
                    server.ehlo()
                    server.login(self.email_user, self.email_pass)
                    server.send_message(msg)
                    self.logger.info(f"Email sent successfully to {msg['To']} via SSL")
                    return True
                    
            except (smtplib.SMTPServerDisconnected, smtplib.SMTPConnectError, 
                    smtplib.SMTPSenderRefused, ConnectionError, TimeoutError) as e:
                # Connectivity/availability errors - retry with backoff
                self.logger.error(f"SMTP SSL error (attempt {attempt+1}): {str(e)}")
                if attempt + 1 < self.max_retries:
                    delay = self.retry_delay * (2 ** attempt)  # Exponential backoff
                    self.logger.info(f"Retrying in {delay} seconds...")
                    time.sleep(delay)
                
            except smtplib.SMTPAuthenticationError as e:
                # Auth errors - don't retry with same credentials
                self.logger.error(f"SMTP authentication failed: {str(e)}")
                return False
                
            except smtplib.SMTPRecipientsRefused as e:
                # Invalid recipient - won't be fixed by retrying
                self.logger.error(f"SMTP refused recipient {msg['To']}: {str(e)}")
                return False
                
            except Exception as e:
                # Unknown errors - retry with caution
                self.logger.error(f"Unexpected error sending email (attempt {attempt+1}): {str(e)}")
                if attempt + 1 < self.max_retries:
                    delay = self.retry_delay * (2 ** attempt)
                    self.logger.info(f"Retrying in {delay} seconds...")
                    time.sleep(delay)
        
        # If we get here, all attempts failed
        return False
        
    def _try_send_with_fallback(self, msg, customer_email):
        """Try sending with a different method as fallback"""
        self.logger.info(f"Attempting alternative method for sending email to {customer_email}")
        
        # Create a copy of the message for the fallback attempt
        fallback_msg = MIMEMultipart()
        for header in msg.keys():
            fallback_msg[header] = msg[header]
            
        # Copy the payload
        for part in msg.get_payload():
            fallback_msg.attach(part)
            
        # Add additional headers that might help with delivery
        fallback_msg["X-Mailer"] = "HunchBank Auto Email Support"
        fallback_msg["X-Priority"] = "3"  # Normal priority
        
        # Try TLS on port 587 (also works for Gmail)
        if self._try_tls_connection(fallback_msg, customer_email):
            return True
        
        # If all methods have failed, log and return false
        self.logger.error("All email sending methods failed")
        return False
        
    def _try_tls_connection(self, msg, customer_email):
        """Helper method to try sending via TLS on port 587"""
        port = 587
        
        for attempt in range(self.max_retries):
            try:
                self.logger.info(f"Using SMTP+TLS connection to {self.smtp_server}:{port}")
                with smtplib.SMTP(
                    self.smtp_server, 
                    port, 
                    timeout=Config.SMTP_TIMEOUT
                ) as server:
                    server.ehlo()
                    server.starttls()
                    server.ehlo()  # Must call ehlo again after starttls
                    server.login(self.email_user, self.email_pass)
                    server.send_message(msg)
                    self.logger.info(f"Email sent successfully to {msg['To']} via TLS")
                    return True
                    
            except (smtplib.SMTPServerDisconnected, smtplib.SMTPConnectError, 
                    smtplib.SMTPSenderRefused, ConnectionError, TimeoutError) as e:
                # Connectivity/availability errors - retry with backoff
                self.logger.error(f"SMTP TLS error (attempt {attempt+1}): {str(e)}")
                if attempt + 1 < self.max_retries:
                    delay = self.retry_delay * (2 ** attempt)  # Exponential backoff
                    self.logger.info(f"Retrying in {delay} seconds...")
                    time.sleep(delay)
                    
            except smtplib.SMTPAuthenticationError as e:
                # Auth errors - don't retry with same credentials
                self.logger.error(f"SMTP authentication failed: {str(e)}")
                return False
                
            except Exception as e:
                self.logger.error(f"Unexpected error with TLS connection: {str(e)}")
                if attempt + 1 < self.max_retries:
                    delay = self.retry_delay * (2 ** attempt)
                    self.logger.info(f"Retrying in {delay} seconds...")
                    time.sleep(delay)
                    
        # If we get here, all TLS attempts failed
        return False
