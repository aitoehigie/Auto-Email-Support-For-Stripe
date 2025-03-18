from utils.logger import setup_logger
import os
import json
import time
import threading
import queue
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import requests
from datetime import datetime, timedelta
from config.config import Config

class ReviewSystem:
    """
    Manages human review workflow for low-confidence or high-risk operations
    """
    def __init__(self):
        self.logger = setup_logger("ReviewSystem")
        self.pending_reviews = []
        self.processed_reviews = []
        self.review_history = []
        
        # Create notification queue and start worker
        self.notification_queue = queue.Queue()
        self.worker_thread = threading.Thread(target=self._notification_worker, daemon=True)
        self.worker_thread.start()
        
        # Load configuration
        self.notification_channels = self._load_notification_channels()
        self.risk_thresholds = self._load_risk_thresholds()
        
        self.logger.info("Review system initialized")
        
    def _load_notification_channels(self):
        """Load notification channel configuration"""
        channels = {
            "email": {
                "enabled": os.getenv("NOTIFICATION_EMAIL_ENABLED", "true").lower() == "true",
                "recipients": os.getenv("NOTIFICATION_EMAIL_RECIPIENTS", "support@hunchbank.example.com").split(","),
                "urgent_recipients": os.getenv("NOTIFICATION_EMAIL_URGENT", "urgent@hunchbank.example.com").split(","),
            },
            "slack": {
                "enabled": os.getenv("NOTIFICATION_SLACK_ENABLED", "false").lower() == "true",
                "webhook_url": os.getenv("NOTIFICATION_SLACK_WEBHOOK", ""),
                "channel": os.getenv("NOTIFICATION_SLACK_CHANNEL", "#support-queue"),
                "urgent_channel": os.getenv("NOTIFICATION_SLACK_URGENT", "#support-urgent"),
            }
        }
        return channels
        
    def _load_risk_thresholds(self):
        """Load risk assessment thresholds"""
        return {
            "confidence": {
                "low": float(os.getenv("RISK_THRESHOLD_CONFIDENCE_LOW", "0.3")),
                "medium": float(os.getenv("RISK_THRESHOLD_CONFIDENCE_MEDIUM", "0.6")),
                "high": float(os.getenv("RISK_THRESHOLD_CONFIDENCE_HIGH", "0.8")),
            },
            "amount": {
                "low": float(os.getenv("RISK_THRESHOLD_AMOUNT_LOW", "50.0")),
                "medium": float(os.getenv("RISK_THRESHOLD_AMOUNT_MEDIUM", "500.0")),
                "high": float(os.getenv("RISK_THRESHOLD_AMOUNT_HIGH", "1000.0")),
            },
            "high_risk_intents": os.getenv(
                "HIGH_RISK_INTENTS", 
                "refund_request,payment_dispute,subscription_cancel"
            ).split(",")
        }
    
    def add_for_review(self, email, intent, entities, confidence):
        """
        Add an email to the review queue
        
        Args:
            email (dict): Email data
            intent (str): Classified intent
            entities (dict): Extracted entities
            confidence (float): Confidence score
        """
        review_id = f"rev_{int(time.time())}_{len(self.pending_reviews) + len(self.processed_reviews)}"
        
        review = {
            "id": review_id,
            "email": email,
            "intent": intent,
            "entities": entities,
            "confidence": confidence,
            "created_at": datetime.now().isoformat(),
            "status": "pending",
            "risk_level": self._assess_risk_level(intent, entities, confidence)
        }
        
        self.pending_reviews.append(review)
        self.logger.info(f"Added review {review_id} to queue - Intent: {intent}, Risk: {review['risk_level']}")
        
        # Send notification based on risk level
        self._queue_notification(review)
        
        # In production, also persist to database
        self._persist_review(review)
        
        return review_id
    
    def _assess_risk_level(self, intent, entities, confidence):
        """
        Assess risk level based on intent, entities, and confidence
        
        Args:
            intent (str): Classified intent
            entities (dict): Extracted entities
            confidence (float): Confidence score
            
        Returns:
            str: Risk level ('low', 'medium', 'high')
        """
        # High risk intents are always at least medium risk
        if intent in self.risk_thresholds["high_risk_intents"]:
            risk_level = "medium"
        # Low confidence is at least medium risk
        elif confidence < self.risk_thresholds["confidence"]["medium"]:
            risk_level = "medium"
        else:
            risk_level = "low"
        
        # Check for high-value transactions
        amount = None
        if "amount" in entities:
            try:
                amount = float(entities["amount"])
            except (ValueError, TypeError):
                pass
        
        # Upgrade risk level based on amount
        if amount:
            if amount > self.risk_thresholds["amount"]["high"]:
                risk_level = "high"
            elif amount > self.risk_thresholds["amount"]["medium"] and risk_level != "high":
                risk_level = "medium"
                
        # Always consider disputes high risk
        if intent == "payment_dispute":
            risk_level = "high"
            
        # Special case: refunds of high value
        if intent == "refund_request" and amount and amount > self.risk_thresholds["amount"]["medium"]:
            risk_level = "high"
            
        return risk_level
    
    def _queue_notification(self, review):
        """
        Queue notification for async delivery
        
        Args:
            review (dict): Review data
        """
        self.notification_queue.put(review)
    
    def _notification_worker(self):
        """
        Background worker that processes the notification queue
        """
        while True:
            try:
                review = self.notification_queue.get(timeout=1)
                self._send_notifications(review)
                self.notification_queue.task_done()
            except queue.Empty:
                # No items in queue, sleep briefly
                time.sleep(0.1)
            except Exception as e:
                self.logger.error(f"Error in notification worker: {str(e)}")
                # Sleep to avoid tight loop in case of persistent error
                time.sleep(1)
    
    def _send_notifications(self, review):
        """
        Send notifications through configured channels
        
        Args:
            review (dict): Review data
        """
        # Determine if this is an urgent notification
        is_urgent = review["risk_level"] == "high"
        
        # Email notification
        if self.notification_channels["email"]["enabled"]:
            recipients = (
                self.notification_channels["email"]["urgent_recipients"] 
                if is_urgent 
                else self.notification_channels["email"]["recipients"]
            )
            
            self._send_email_notification(review, recipients)
            
        # Slack notification
        if self.notification_channels["slack"]["enabled"]:
            channel = (
                self.notification_channels["slack"]["urgent_channel"] 
                if is_urgent 
                else self.notification_channels["slack"]["channel"]
            )
            
            self._send_slack_notification(review, channel)
    
    def _send_email_notification(self, review, recipients):
        """
        Send email notification about review
        
        Args:
            review (dict): Review data
            recipients (list): List of email recipients
        """
        try:
            # Create email
            msg = MIMEMultipart()
            
            # Determine subject prefix based on risk level
            risk_prefix = ""
            if review["risk_level"] == "high":
                risk_prefix = "[URGENT] "
            elif review["risk_level"] == "medium":
                risk_prefix = "[ATTENTION] "
                
            # Set subject
            msg["Subject"] = f"{risk_prefix}Review Required: {review['intent']} ({review['id']})"
            msg["From"] = Config.EMAIL_USER
            msg["To"] = ", ".join(recipients)
            
            # Create email body with review details
            body = f"""
            <h2>Review Required: {review['intent']}</h2>
            <p><strong>ID:</strong> {review['id']}</p>
            <p><strong>Risk Level:</strong> {review['risk_level'].upper()}</p>
            <p><strong>Created At:</strong> {review['created_at']}</p>
            <p><strong>From:</strong> {review['email']['from']}</p>
            <p><strong>Subject:</strong> {review['email']['subject']}</p>
            <p><strong>Confidence:</strong> {review['confidence']:.2f}</p>
            
            <h3>Email Body:</h3>
            <pre>{review['email']['body']}</pre>
            
            <h3>Entities:</h3>
            <pre>{json.dumps(review['entities'], indent=2)}</pre>
            
            <p>Please review and address this request as soon as possible.</p>
            <p>You can review this in the HunchBank support system.</p>
            """
            
            # Add HTML part
            html_part = MIMEText(body, "html")
            msg.attach(html_part)
            
            # Add plain text alternative
            text_body = body.replace("<h2>", "").replace("</h2>", "\n\n")
            text_body = text_body.replace("<h3>", "").replace("</h3>", "\n\n")
            text_body = text_body.replace("<p>", "").replace("</p>", "\n")
            text_body = text_body.replace("<pre>", "").replace("</pre>", "")
            text_body = text_body.replace("<strong>", "").replace("</strong>", "")
            
            text_part = MIMEText(text_body, "plain")
            msg.attach(text_part)
            
            # Send email
            with smtplib.SMTP(Config.SMTP_SERVER, Config.SMTP_PORT) as server:
                if Config.SMTP_USE_TLS:
                    server.starttls()
                server.login(Config.EMAIL_USER, Config.EMAIL_PASS)
                server.send_message(msg)
                
            self.logger.info(f"Sent email notification for review {review['id']} to {len(recipients)} recipients")
            
        except Exception as e:
            self.logger.error(f"Failed to send email notification: {str(e)}")
    
    def _send_slack_notification(self, review, channel):
        """
        Send Slack notification about review
        
        Args:
            review (dict): Review data
            channel (str): Slack channel
        """
        try:
            webhook_url = self.notification_channels["slack"]["webhook_url"]
            if not webhook_url:
                self.logger.warning("Slack webhook URL not configured, skipping notification")
                return
                
            # Determine emoji based on risk level
            risk_emoji = "🟢"  # Default low risk
            if review["risk_level"] == "high":
                risk_emoji = "🔴"
            elif review["risk_level"] == "medium":
                risk_emoji = "🟠"
                
            # Create message
            message = {
                "channel": channel,
                "username": "HunchBank Support Bot",
                "icon_emoji": ":bank:",
                "text": f"{risk_emoji} *New review required: {review['intent']}*",
                "blocks": [
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": f"{risk_emoji} *New review required: {review['intent']}*"
                        }
                    },
                    {
                        "type": "divider"
                    },
                    {
                        "type": "section",
                        "fields": [
                            {
                                "type": "mrkdwn",
                                "text": f"*ID:*\n{review['id']}"
                            },
                            {
                                "type": "mrkdwn",
                                "text": f"*Risk Level:*\n{review['risk_level'].upper()}"
                            },
                            {
                                "type": "mrkdwn",
                                "text": f"*From:*\n{review['email']['from']}"
                            },
                            {
                                "type": "mrkdwn",
                                "text": f"*Confidence:*\n{review['confidence']:.2f}"
                            }
                        ]
                    },
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": f"*Subject:*\n{review['email']['subject']}"
                        }
                    },
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": f"*Email Body:*\n```{review['email']['body'][:300]}{'...' if len(review['email']['body']) > 300 else ''}```"
                        }
                    },
                    {
                        "type": "actions",
                        "elements": [
                            {
                                "type": "button",
                                "text": {
                                    "type": "plain_text",
                                    "text": "View Details"
                                },
                                "url": f"https://hunchbank.example.com/review/{review['id']}"
                            }
                        ]
                    }
                ]
            }
            
            # Send to Slack
            response = requests.post(webhook_url, json=message, timeout=5)
            if response.status_code != 200:
                self.logger.error(f"Slack API error: {response.status_code} - {response.text}")
            else:
                self.logger.info(f"Sent Slack notification for review {review['id']} to {channel}")
            
        except Exception as e:
            self.logger.error(f"Failed to send Slack notification: {str(e)}")
    
    def _persist_review(self, review):
        """
        Persist review to storage (in production, this would use a database)
        
        Args:
            review (dict): Review data
        """
        # In production, this would store to a database
        self.logger.info(f"Would persist review {review['id']} to database")
        
        # Example production database implementation:
        # 
        # import sqlite3
        # 
        # conn = sqlite3.connect('hunchbank.db')
        # cursor = conn.cursor()
        # 
        # cursor.execute('''
        #     INSERT INTO reviews (
        #         id, customer_email, intent, confidence, risk_level, 
        #         email_subject, email_body, entities, status, created_at
        #     ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        # ''', (
        #     review['id'],
        #     review['email']['from'],
        #     review['intent'],
        #     review['confidence'],
        #     review['risk_level'],
        #     review['email']['subject'],
        #     review['email']['body'],
        #     json.dumps(review['entities']),
        #     review['status'],
        #     review['created_at']
        # ))
        # conn.commit()
        # conn.close()
        
    def get_pending_reviews(self):
        """
        Get list of pending reviews
        
        Returns:
            list: List of pending review objects
        """
        return self.pending_reviews
    
    def get_review_by_id(self, review_id):
        """
        Get review by ID
        
        Args:
            review_id (str): Review ID
            
        Returns:
            dict: Review data or None if not found
        """
        # Check pending reviews
        for review in self.pending_reviews:
            if review.get("id") == review_id:
                return review
                
        # Check processed reviews
        for review in self.processed_reviews:
            if review.get("id") == review_id:
                return review
                
        return None
    
    def accept_review(self, review):
        """
        Mark a review as accepted
        
        Args:
            review (dict): Review object
            
        Returns:
            tuple: (intent, entities)
        """
        try:
            # Find and remove the review from pending list
            self.pending_reviews.remove(review)
            
            # Update status
            review["status"] = "accepted"
            review["processed_at"] = datetime.now().isoformat()
            
            # Add to processed list
            self.processed_reviews.append(review)
            
            # Add to history
            self.review_history.append({
                "review_id": review.get("id", "unknown"),
                "action": "accepted",
                "timestamp": datetime.now().isoformat()
            })
            
            # Persist update
            self._persist_review_update(review)
            
            self.logger.info(f"Review {review.get('id', 'unknown')} accepted")
            return review["intent"], review["entities"]
            
        except Exception as e:
            self.logger.error(f"Error accepting review: {str(e)}")
            return review["intent"], review["entities"]  # Return original values
    
    def reject_review(self, review):
        """
        Mark a review as rejected
        
        Args:
            review (dict): Review object
        """
        try:
            # Find and remove from pending list
            self.pending_reviews.remove(review)
            
            # Update status
            review["status"] = "rejected"
            review["processed_at"] = datetime.now().isoformat()
            
            # Add to history
            self.review_history.append({
                "review_id": review.get("id", "unknown"),
                "action": "rejected",
                "timestamp": datetime.now().isoformat()
            })
            
            # Persist update
            self._persist_review_update(review)
            
            self.logger.info(f"Review {review.get('id', 'unknown')} rejected")
            
        except Exception as e:
            self.logger.error(f"Error rejecting review: {str(e)}")
    
    def modify_review(self, review, new_intent):
        """
        Modify a review's intent
        
        Args:
            review (dict): Review object
            new_intent (str): New intent classification
            
        Returns:
            tuple: (new_intent, entities)
        """
        try:
            # Find and remove from pending list
            self.pending_reviews.remove(review)
            
            # Store old intent for logging
            old_intent = review["intent"]
            
            # Update intent and status
            review["intent"] = new_intent
            review["status"] = "modified"
            review["modified_at"] = datetime.now().isoformat()
            
            # Add to processed list
            self.processed_reviews.append(review)
            
            # Add to history
            self.review_history.append({
                "review_id": review.get("id", "unknown"),
                "action": "modified",
                "details": f"Intent changed from {old_intent} to {new_intent}",
                "timestamp": datetime.now().isoformat()
            })
            
            # Persist update
            self._persist_review_update(review)
            
            self.logger.info(f"Review {review.get('id', 'unknown')} modified: intent {old_intent} -> {new_intent}")
            return new_intent, review["entities"]
            
        except Exception as e:
            self.logger.error(f"Error modifying review: {str(e)}")
            return new_intent, review["entities"]  # Return the requested values
    
    def _persist_review_update(self, review):
        """
        Persist review update to storage
        
        Args:
            review (dict): Updated review data
        """
        # In production, this would update database
        self.logger.info(f"Would update review {review.get('id', 'unknown')} in database: status={review.get('status')}")
        
        # Example production database implementation:
        # conn = sqlite3.connect('hunchbank.db')
        # cursor = conn.cursor()
        # 
        # cursor.execute('''
        #     UPDATE reviews 
        #     SET status = ?, intent = ?, modified_at = ?, processed_at = ?
        #     WHERE id = ?
        # ''', (
        #     review.get('status'),
        #     review.get('intent'),
        #     review.get('modified_at'),
        #     review.get('processed_at'),
        #     review.get('id')
        # ))
        # conn.commit()
        # conn.close()
        
    def get_stats(self):
        """
        Get review system statistics
        
        Returns:
            dict: Statistics about reviews
        """
        now = datetime.now()
        today_start = datetime(now.year, now.month, now.day, 0, 0, 0)
        
        # Count by status
        pending_count = len(self.pending_reviews)
        accepted_count = sum(1 for r in self.processed_reviews if r.get("status") == "accepted")
        rejected_count = sum(1 for r in self.processed_reviews if r.get("status") == "rejected")
        
        # Count by risk level (for those that have risk level)
        high_risk_count = sum(1 for r in self.pending_reviews if r.get("risk_level") == "high")
        medium_risk_count = sum(1 for r in self.pending_reviews if r.get("risk_level") == "medium")
        low_risk_count = sum(1 for r in self.pending_reviews if r.get("risk_level") == "low")
        
        # Count today's reviews
        today_count = 0
        for r in self.pending_reviews + self.processed_reviews:
            if "created_at" in r:
                try:
                    if datetime.fromisoformat(r["created_at"]) >= today_start:
                        today_count += 1
                except (ValueError, TypeError):
                    pass
        
        # Count by intent
        intent_counts = {}
        for r in self.pending_reviews + self.processed_reviews:
            intent = r["intent"]
            if intent not in intent_counts:
                intent_counts[intent] = 0
            intent_counts[intent] += 1
        
        return {
            "total_pending": pending_count,
            "total_processed": len(self.processed_reviews),
            "accepted": accepted_count,
            "rejected": rejected_count,
            "high_risk": high_risk_count,
            "medium_risk": medium_risk_count,
            "low_risk": low_risk_count,
            "today_count": today_count,
            "intent_distribution": intent_counts
        }
