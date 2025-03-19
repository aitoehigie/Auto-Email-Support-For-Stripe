from services.email_service import EmailService
from services.nlp_service import NLPService
from services.response_service import ResponseService
from services.stripe_service import StripeService
from handlers.payment_handler import PaymentHandler, BillingHandler, SubscriptionHandler, RefundHandler, DisputeHandler
from cli.interface import PaymentUpdateCLI
from human_loop.review_system import ReviewSystem
from utils.logger import setup_logger, log_exception, LogCapture
from config.config import Config
import threading
import signal
import sys
import re
import time
import os

class System:
    def __init__(self):
        self.logger = setup_logger("Main", os.path.join("logs", "hunchbank.log"), console_output=False)
        self.email_service = EmailService()
        self.nlp_service = NLPService()
        self.stripe_service = StripeService()
        
        # Initialize all handlers
        self.payment_handler = PaymentHandler()
        self.billing_handler = BillingHandler()
        self.subscription_handler = SubscriptionHandler()
        self.refund_handler = RefundHandler()
        self.dispute_handler = DisputeHandler()
        
        self.response_service = ResponseService()
        self.review_system = ReviewSystem()
        self.processed_count = [0]  # Mutable to share between threads
        self.running = True
        signal.signal(signal.SIGINT, self.shutdown)
        signal.signal(signal.SIGTERM, self.shutdown)
        
        # Basic validation
        self._validate_configuration()

    def _validate_configuration(self):
        """Validate essential configuration before starting"""
        missing = []
        if not Config.EMAIL_USER or not Config.EMAIL_PASS:
            missing.append("Email credentials")
        if not Config.STRIPE_API_KEY:
            missing.append("Stripe API key")
        if not Config.NLP_API_KEY:
            missing.append("NLP API key")
            
        if missing:
            self.logger.error(f"Missing required configuration: {', '.join(missing)}")
            self.logger.error("Please check your .env file")
            print(f"ERROR: Missing required configuration: {', '.join(missing)}")
            print("Please check your .env file and try again")

    def shutdown(self, signum, frame):
        """Gracefully shut down the system"""
        self.logger.info(f"Shutting down system (signal: {signum})...")
        self.running = False
        
        # Give threads a chance to exit gracefully
        time.sleep(2)
        sys.exit(0)

    def process_emails(self):
        """Main email processing loop"""
        with LogCapture(self.logger, "Email processing service"):
            connect_retry_count = 0
            while self.running:
                try:
                    # Connect to email server
                    self.logger.info("Connecting to email server...")
                    try:
                        self.email_service.connect()
                        connect_retry_count = 0  # Reset on successful connection
                    except Exception as e:
                        connect_retry_count += 1
                        if connect_retry_count > 5:
                            self.logger.error(f"Failed to connect after 5 attempts, sleeping for 5 minutes")
                            time.sleep(300)  # Sleep for 5 minutes after repeated failures
                            continue
                        else:
                            self.logger.error(f"Connection failed (attempt {connect_retry_count}): {str(e)}")
                            time.sleep(30)  # Short sleep before retry
                            continue
                    
                    # Fetch and process emails
                    self.logger.info("Fetching emails...")
                    emails = self.email_service.fetch_emails()
                    
                    if not emails:
                        self.logger.info("No new emails to process")
                        time.sleep(Config.EMAIL_CHECK_INTERVAL)
                        continue
                        
                    emails_processed = 0
                    for email in emails:
                        if not self.running:
                            self.logger.info("Shutting down email processing loop...")
                            break
                            
                        with LogCapture(self.logger, f"Email from {email['from']} (UID: {email['uid']})"):
                            try:
                                self._process_single_email(email)
                                emails_processed += 1
                            except Exception as e:
                                log_exception(self.logger, e, f"Failed to process email {email['uid']}")
                                
                    self.logger.info(f"Processed {emails_processed} emails in this cycle")
                    
                except Exception as e:
                    log_exception(self.logger, e, "System error in email processing loop")
                    
                if self.running:
                    self.logger.info(f"Sleeping for {Config.EMAIL_CHECK_INTERVAL} seconds before next cycle...")
                    time.sleep(Config.EMAIL_CHECK_INTERVAL)

    def _process_single_email(self, email):
        """Process a single email"""
        # Validate email format
        if not self._is_valid_email(email["from"]):
            self.logger.warning(f"Invalid email format: {email['from']}")
            response = self.response_service.generate_response(
                "unknown", False, "Invalid email address format", email["from"]
            )
            self.response_service.send_email(email["from"], response, email.get("message_id", None))
            return
        
        # Classify intent
        intent, entities, confidence = self.nlp_service.classify_intent(email["body"])
        self.logger.info(f"Intent: {intent}, Confidence: {confidence:.2f}, Entities: {entities}")
        
        # Handle based on intent and confidence threshold
        if confidence > Config.CONFIDENCE_THRESHOLD:
            # Map intents to handlers
            intent_handler_map = {
                "update_payment_method": self.payment_handler,
                "billing_inquiry": self.billing_handler,
                "subscription_change": self.subscription_handler,
                "refund_request": self.refund_handler,
                "payment_dispute": self.dispute_handler
            }
            
            # Process high-risk intents differently
            high_risk_intents = ["subscription_cancel", "refund_request", "payment_dispute"]
            
            if intent in high_risk_intents:
                if intent == "refund_request" and confidence > 0.95:
                    # For very high confidence refund requests, try automated processing
                    # The handler will still apply fraud checks and may route to human review
                    self._handle_request(email, intent, entities, self.refund_handler)
                else:
                    # Route other high-risk intents to human review
                    self._send_to_human_review(email, intent, entities, confidence)
            elif intent in intent_handler_map:
                # Process standard intents with the appropriate handler
                self._handle_request(email, intent, entities, intent_handler_map[intent])
            else:
                # Unknown intent types go to human review
                self._send_to_human_review(email, intent, entities, confidence)
        else:
            # Low confidence intents always go to human review
            self._send_to_human_review(email, intent, entities, confidence)

    def _is_valid_email(self, email):
        """Validate email format"""
        if not email:
            return False
        email_pattern = re.compile(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$")
        return bool(email_pattern.match(email))

    def _handle_request(self, email, intent, entities, handler):
        """Handle a request using the appropriate handler"""
        self.logger.info(f"Handling {intent} for {email['from']}")
        
        # Look up customer
        customer_id = self.stripe_service.get_customer_by_email(email["from"])
        if not customer_id:
            self.logger.warning(f"No customer found for {email['from']}")
            response = self.response_service.generate_response(
                intent, False, "No account found for this email address", email["from"]
            )
            self.response_service.send_email(email["from"], response)
            return
        
        # Process the request with the appropriate handler
        success, message = handler.handle(customer_id, entities)
        self.logger.info(f"{intent} handling result: success={success}, message={message}")
        
        # Send response to customer
        response = self.response_service.generate_response(intent, success, message, email["from"])
        email_sent = self.response_service.send_email(email["from"], response, email.get("message_id", None))
        
        # Mark as read if successfully handled
        if success and email_sent:
            if self.email_service.mark_as_read(email["uid"]):
                self.processed_count[0] += 1
                # Emit an activity log entry for dashboard
                if cli is not None and hasattr(cli, 'system_activity_log'):
                    import datetime
                    cli.system_activity_log.insert(0, (
                        datetime.datetime.now(),
                        f"Email processed: {intent} from {email['from']}"
                    ))
                    # Keep only 20 most recent activities
                    cli.system_activity_log = cli.system_activity_log[:20]
                    # Update UI
                    cli.post_message(cli.UpdateProcessed(self.processed_count[0]))
                self.logger.info(f"Email marked as read and processed successfully")
            else:
                self.logger.error(f"Failed to mark email as read")
        else:
            self.logger.warning(f"Email not marked as read: success={success}, email_sent={email_sent}")

    def _send_to_human_review(self, email, intent, entities, confidence):
        """Send email to human review queue"""
        self.logger.info(f"Sending to human review: intent={intent}, confidence={confidence:.2f}")
        self.review_system.add_for_review(email, intent, entities, confidence)
        
        # Optionally send an acknowledgment to the customer
        if confidence < 0.3:  # Very low confidence
            response = self.response_service.generate_response(
                "unknown", True, "We've received your message and our team will review it shortly", email["from"]
            )
            self.response_service.send_email(email["from"], response, email.get("message_id", None))

# Global CLI reference for cross-thread updates
cli = None

def main():
    """Entry point for the application"""
    try:
        # Create system
        system = System()
        
        # Start email processing thread
        email_thread = threading.Thread(target=system.process_emails, name="EmailProcessor")
        email_thread.daemon = True
        email_thread.start()
        
        # Run CLI (this will block until exit)
        global cli
        cli = PaymentUpdateCLI(system.review_system, Config)
        cli.run(system.processed_count[0])
        
    except KeyboardInterrupt:
        print("\nShutting down gracefully...")
        sys.exit(0)
    except Exception as e:
        logger = setup_logger("Startup", console_output=False)
        log_exception(logger, e, "Fatal error during startup")
        print(f"ERROR: {str(e)}")
        print("See logs for details")
        sys.exit(1)

if __name__ == "__main__":
    main()