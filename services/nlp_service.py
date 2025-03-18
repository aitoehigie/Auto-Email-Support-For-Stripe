import requests
import json
from config.config import Config
from utils.logger import setup_logger
import time

class NLPService:
    def __init__(self):
        self.logger = setup_logger("NLPService")
        self.api_key = Config.NLP_API_KEY
        self.endpoint = "https://api.anthropic.com/v1/messages"  # Updated Anthropic endpoint
        self.max_retries = Config.MAX_RETRIES
        self.retry_delay = Config.RETRY_DELAY

    def classify_intent(self, email_body):
        """
        Analyze email content to determine the customer's intent and extract entities.
        
        Args:
            email_body (str): The body text of the customer email
            
        Returns:
            tuple: (intent, entities, confidence)
                - intent (str): The classified intent (e.g., "update_payment_method")
                - entities (dict): Extracted entities from the email
                - confidence (float): Confidence score (0.0-1.0)
        """
        for attempt in range(self.max_retries):
            try:
                headers = {
                    "x-api-key": self.api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json"
                }
                
                # Add system prompt to guide the model
                system_prompt = """
                You are an intent classification system for a bank's customer support.
                
                Analyze the customer email and determine the primary intent.
                
                Common intents include:
                - update_payment_method: Customer wants to update their payment method/card
                - billing_inquiry: Customer has questions about charges or billing
                - subscription_change: Customer wants to change their subscription plan or add seats
                - subscription_cancel: Customer wants to cancel their subscription
                - refund_request: Customer is requesting a refund
                - payment_dispute: Customer is disputing a charge
                - technical_issue: Customer is experiencing a technical problem
                - account_access: Customer has login or access issues
                - general_question: General inquiries about services or features
                - unknown: Intent cannot be determined
                
                Extract relevant entities based on the intent:
                
                For update_payment_method:
                - card_token: If they mention a specific card
                
                For billing_inquiry:
                - inquiry_type: "invoice", "payment_history", or "subscription"
                - invoice_id: If they reference a specific invoice
                - subscription_id: If they reference a specific subscription
                
                For subscription_change:
                - request_type: "change_plan", "add_seats"
                - subscription_id: If they reference a specific subscription
                - new_plan: The plan they want to switch to
                - seat_count: Number of seats they want to add
                
                For subscription_cancel:
                - subscription_id: If they reference a specific subscription
                - reason: Why they want to cancel
                - immediate: "true" if they want immediate cancellation, "false" for end of period
                
                For refund_request:
                - charge_id: ID of the charge to refund
                - payment_intent: Alternative to charge_id
                - amount: Amount to refund (if partial)
                - reason: Why they want a refund
                
                For payment_dispute:
                - dispute_id: ID of an existing dispute
                - charge_id: ID of the charge being disputed
                - reason: Why they're disputing the charge
                - timestamp: When the disputed charge occurred
                
                For all intents, also extract:
                - payment_date: Any dates mentioned for payments
                - account_type: Account types mentioned (checking, savings, etc.)
                
                Return ONLY a JSON object in this format:
                {
                    "intent": "intent_name",
                    "entities": {
                        "entity_name": "value"
                    },
                    "confidence": 0.95
                }
                
                Assign a confidence score between 0.0 and 1.0 based on how certain you are of the classification.
                """
                
                payload = {
                    "model": "claude-3-sonnet-20240229",
                    "system": system_prompt,
                    "messages": [{
                        "role": "user",
                        "content": f"Here is the customer email:\n\n{email_body}"
                    }],
                    "max_tokens": 300,
                    "temperature": 0.2
                }
                
                response = requests.post(self.endpoint, json=payload, headers=headers, timeout=15)
                response.raise_for_status()
                result = response.json()
                
                # Extract the content from the response
                content = result.get("content", [{}])[0].get("text", "{}")
                
                # Parse the JSON response
                try:
                    parsed_result = json.loads(content)
                    intent = parsed_result.get("intent", "unknown")
                    entities = parsed_result.get("entities", {})
                    confidence = parsed_result.get("confidence", 0.0)
                    
                    self.logger.info(f"Intent classified: {intent} (confidence: {confidence})")
                    return intent, entities, float(confidence)
                except json.JSONDecodeError as e:
                    self.logger.error(f"Failed to parse NLP response: {e}")
                    self.logger.debug(f"Raw response content: {content}")
                    if attempt + 1 == self.max_retries:
                        return "unknown", {}, 0.0
                    time.sleep(self.retry_delay)
                    
            except requests.RequestException as e:
                self.logger.error(f"NLP attempt {attempt + 1} failed: {str(e)}")
                if attempt + 1 == self.max_retries:
                    return "unknown", {}, 0.0
                time.sleep(self.retry_delay)
            
        # If we've exhausted all retries
        return "unknown", {}, 0.0
