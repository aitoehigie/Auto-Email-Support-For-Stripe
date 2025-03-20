from services.email_service import EmailService
from services.nlp_service import NLPService
from services.response_service import ResponseService
from services.stripe_service import StripeService
from handlers.payment_handler import PaymentHandler, BillingHandler, SubscriptionHandler, RefundHandler, DisputeHandler
from cli.interface import PaymentUpdateCLI
from human_loop.review_system import ReviewSystem
from utils.logger import setup_logger, log_exception, LogCapture
from utils.database import get_db
from config.config import Config
import threading
import signal
import sys
import re
import time
import os
from datetime import datetime

class System:
    def __init__(self):
        self.logger = setup_logger("Main", os.path.join("logs", "hunchbank.log"), console_output=False)
        
        # Get database connection
        if Config.USE_DATABASE:
            self.db = get_db()
            self.logger.info("Database service initialized")
            
            # Load metrics from database if available
            try:
                metrics = self.db.get_latest_metrics()
                self.processed_count = [metrics["processed_count"]]  # Use latest from DB
                self.logger.info(f"Loaded processed count from database: {self.processed_count[0]}")
            except Exception as e:
                self.logger.error(f"Error loading metrics from database: {str(e)}")
                self.processed_count = [0]  # Default if DB fails
        else:
            self.processed_count = [0]  # Mutable to share between threads
        
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
        self.running = True
        signal.signal(signal.SIGINT, self.shutdown)
        signal.signal(signal.SIGTERM, self.shutdown)
        
        # Add system startup to activity log if database is enabled
        if Config.USE_DATABASE:
            self.db.add_activity("System started", "system", "Main")
        
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
        # Log email to database if using database
        if Config.USE_DATABASE:
            try:
                # Store initial email receipt in database
                self.db.log_email_processing(
                    email_id=email.get("uid", str(time.time())),
                    sender=email["from"],
                    subject=email.get("subject", ""),
                    received_at=datetime.now().isoformat(),
                    status="received"
                )
                
                # Add activity log entry
                self.db.add_activity(
                    f"Email received from {email['from']}", 
                    "email", 
                    "EmailProcessor"
                )
            except Exception as e:
                self.logger.error(f"Error logging email to database: {str(e)}")
        
        # Validate email format
        if not self._is_valid_email(email["from"]):
            self.logger.warning(f"Invalid email format: {email['from']}")
            response = self.response_service.generate_response(
                "unknown", False, "Invalid email address format", email["from"]
            )
            self.response_service.send_email(email["from"], response, email.get("message_id", None))
            
            # Update email status in database
            if Config.USE_DATABASE:
                try:
                    self.db.update_email_status(
                        email_id=email.get("uid", str(time.time())),
                        status="error",
                        intent="unknown"
                    )
                    
                    # Log error
                    self.db.log_error(
                        "invalid_email", 
                        f"Invalid email format: {email['from']}", 
                        "EmailProcessor"
                    )
                except Exception as e:
                    self.logger.error(f"Error updating email status in database: {str(e)}")
            
            return
        
        # Classify intent
        intent, entities, confidence = self.nlp_service.classify_intent(email["body"])
        self.logger.info(f"Intent: {intent}, Confidence: {confidence:.2f}, Entities: {entities}")
        
        # Update email in database with intent classification
        if Config.USE_DATABASE:
            try:
                self.db.update_email_status(
                    email_id=email.get("uid", str(time.time())),
                    status="classified",
                    intent=intent,
                    confidence=confidence
                )
                
                # Update intent stats
                today = datetime.now().strftime("%Y-%m-%d")
                self.db.update_intent_stats(
                    date=today,
                    intent=intent,
                    count=1,
                    auto_processed=0  # Will be updated if auto-processed
                )
            except Exception as e:
                self.logger.error(f"Error updating email classification in database: {str(e)}")
        
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
        
        # Update email in database if using database
        if Config.USE_DATABASE:
            try:
                self.db.update_email_status(
                    email_id=email.get("uid", str(time.time())),
                    status="processing"
                )
            except Exception as e:
                self.logger.error(f"Error updating email status in database: {str(e)}")
        
        # Look up customer
        customer_id = self.stripe_service.get_customer_by_email(email["from"])
        if not customer_id:
            self.logger.warning(f"No customer found for {email['from']}")
            response = self.response_service.generate_response(
                intent, False, "No account found for this email address", email["from"]
            )
            self.response_service.send_email(email["from"], response)
            
            # Update email status in database
            if Config.USE_DATABASE:
                try:
                    self.db.update_email_status(
                        email_id=email.get("uid", str(time.time())),
                        status="error",
                        processed_at=datetime.now().isoformat()
                    )
                    
                    # Log error
                    self.db.log_error(
                        "customer_not_found", 
                        f"No customer found for {email['from']}", 
                        "EmailProcessor"
                    )
                except Exception as e:
                    self.logger.error(f"Error updating email status in database: {str(e)}")
                    
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
                
                # Create activity message for both database and dashboard
                activity_msg = f"Email processed: {intent} from {email['from']}"
                
                # Add to database activity log if using database
                if Config.USE_DATABASE:
                    try:
                        # Log activity
                        self.db.add_activity(activity_msg, "email", "EmailProcessor")
                        
                        # Update email status
                        self.db.update_email_status(
                            email_id=email.get("uid", str(time.time())),
                            status="processed",
                            processed_at=datetime.now().isoformat(),
                            auto_processed=True
                        )
                        
                        # Update intent stats - increment auto-processed count
                        today = datetime.now().strftime("%Y-%m-%d")
                        self.db.update_intent_stats(
                            date=today,
                            intent=intent,
                            count=0,  # Already counted when classified
                            auto_processed=1
                        )
                        
                        # Update system metrics
                        if hasattr(self, 'db'):
                            # Count errors from error_log table
                            error_count = 0
                            try:
                                cursor = self.db._get_connection().cursor()
                                cursor.execute("SELECT COUNT(*) as count FROM error_log")
                                row = cursor.fetchone()
                                if row:
                                    error_count = row[0]
                            except Exception as e:
                                self.logger.error(f"Error counting errors: {str(e)}")
                            
                            # Set pending count
                            pending_count = len(self.review_system.pending_reviews) if hasattr(self.review_system, 'pending_reviews') else 0
                            
                            # Update metrics in database
                            self.db.update_metrics(
                                processed_count=self.processed_count[0],
                                auto_processed_count=self.processed_count[0] - pending_count,
                                error_count=error_count,
                                pending_reviews_count=pending_count
                            )
                    except Exception as e:
                        self.logger.error(f"Error updating database: {str(e)}")
                
                # Emit an activity log entry for dashboard
                if cli is not None and hasattr(cli, 'system_activity_log'):
                    # Use already created activity_msg 
                    cli.system_activity_log.insert(0, (
                        datetime.now(),
                        activity_msg
                    ))
                    # Keep only 20 most recent activities
                    cli.system_activity_log = cli.system_activity_log[:20]
                    # Update UI with multiple metrics
                    cli.post_message(cli.UpdateProcessed(self.processed_count[0]))
                    
                    # Also update database metrics for dashboard
                    if Config.USE_DATABASE and hasattr(self, 'db'):
                        # Force immediate metrics update in database
                        pending_count = len(self.review_system.pending_reviews) if hasattr(self.review_system, 'pending_reviews') else 0
                        error_log_count = 0
                        # Count errors from error_log table
                        try:
                            cursor = self.db._get_connection().cursor()
                            cursor.execute("SELECT COUNT(*) FROM error_log")
                            error_log_count = cursor.fetchone()[0]
                        except Exception as e:
                            self.logger.error(f"Error counting errors: {str(e)}")
                            
                        self.db.update_metrics(
                            processed_count=self.processed_count[0],
                            auto_processed_count=self.processed_count[0] - pending_count,
                            error_count=error_log_count,
                            pending_reviews_count=pending_count
                        )
                    
                self.logger.info(f"Email marked as read and processed successfully")
            else:
                self.logger.error(f"Failed to mark email as read")
                
                # Log error in database
                if Config.USE_DATABASE:
                    try:
                        self.db.log_error(
                            "mark_read_failed", 
                            f"Failed to mark email as read: {email.get('uid', '')}", 
                            "EmailProcessor"
                        )
                    except Exception as e:
                        self.logger.error(f"Error logging error to database: {str(e)}")
        else:
            self.logger.warning(f"Email not marked as read: success={success}, email_sent={email_sent}")
            
            # Update status in database
            if Config.USE_DATABASE:
                try:
                    status = "error" if not success else "sending_failed"
                    self.db.update_email_status(
                        email_id=email.get("uid", str(time.time())),
                        status=status,
                        processed_at=datetime.now().isoformat()
                    )
                    
                    # Log error
                    error_type = "handler_error" if not success else "sending_error"
                    self.db.log_error(
                        error_type, 
                        f"Email handling failed: {message}", 
                        "EmailProcessor",
                        f"Intent: {intent}, Success: {success}, Email sent: {email_sent}"
                    )
                except Exception as e:
                    self.logger.error(f"Error updating email status in database: {str(e)}")

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
        # Initialize CLI with proper system references
        cli = PaymentUpdateCLI(system.review_system, Config)
        # Set initial processed count value
        if hasattr(cli, 'processed_count'):
            cli.processed_count = system.processed_count[0]
        # Run the CLI (this will block until exit)
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