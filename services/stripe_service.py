import stripe
from config.config import Config
from utils.logger import setup_logger
import time
import os
import json
from datetime import datetime

class StripeService:
    def __init__(self):
        self.logger = setup_logger("StripeService")
        stripe.api_key = Config.STRIPE_API_KEY
        self.stripe = stripe
        self.max_retries = Config.MAX_RETRIES
        self.retry_delay = Config.RETRY_DELAY

    def get_customer_by_email(self, email):
        """
        Look up a Stripe customer by email address
        
        Args:
            email (str): Customer email address
            
        Returns:
            str: Customer ID if found, None otherwise
        """
        if not email:
            self.logger.error("Empty email provided for customer lookup")
            return None
            
        # Normalize email address (lowercase)
        email = email.lower().strip()
        
        for attempt in range(self.max_retries):
            try:
                customers = self.stripe.Customer.list(email=email, limit=1)
                if customers and customers.data:
                    customer_id = customers.data[0].id
                    self.logger.info(f"Found customer {customer_id} for email {email}")
                    return customer_id
                self.logger.warning(f"No customer found for email {email}")
                return None
            except stripe.error.RateLimitError as e:
                self.logger.error(f"Rate limit hit: {str(e)}")
                if attempt + 1 == self.max_retries:
                    return None
                time.sleep(self.retry_delay * (attempt + 1))  # Exponential backoff
            except stripe.error.InvalidRequestError as e:
                self.logger.error(f"Invalid request to Stripe API: {str(e)}")
                return None
            except stripe.error.AuthenticationError as e:
                self.logger.error(f"Authentication with Stripe failed: {str(e)}")
                return None
            except stripe.error.APIConnectionError as e:
                self.logger.error(f"Network error connecting to Stripe: {str(e)}")
                if attempt + 1 == self.max_retries:
                    return None
                time.sleep(self.retry_delay * (attempt + 1))  # Exponential backoff
            except stripe.error.StripeError as e:
                self.logger.error(f"Stripe customer lookup failed: {str(e)}")
                return None
            except Exception as e:
                self.logger.error(f"Unexpected error in customer lookup: {str(e)}")
                return None

    def update_payment_method(self, customer_id, new_card_token):
        """
        Update a customer's default payment method
        
        Args:
            customer_id (str): Stripe customer ID
            new_card_token (str): Token for the new payment method
            
        Returns:
            bool: True if successful, False otherwise
        """
        if not customer_id:
            self.logger.error("Empty customer_id provided for payment method update")
            return False
            
        if not new_card_token:
            self.logger.error("Empty card token provided for payment method update")
            return False
            
        for attempt in range(self.max_retries):
            try:
                # First verify that the customer exists
                customer = self.stripe.Customer.retrieve(customer_id)
                if not customer or customer.get('deleted', False):
                    self.logger.error(f"Customer {customer_id} not found or deleted")
                    return False
                
                # Create and attach payment method
                payment_method = self.stripe.PaymentMethod.attach(
                    new_card_token,
                    customer=customer_id
                )
                
                # Set as default payment method
                self.stripe.Customer.modify(
                    customer_id,
                    invoice_settings={"default_payment_method": payment_method.id}
                )
                
                self.logger.info(f"Payment method {payment_method.id} set as default for customer {customer_id}")
                return True
                
            except stripe.error.CardError as e:
                # Card was declined
                self.logger.error(f"Card declined: {e.error.message}")
                return False
                
            except stripe.error.RateLimitError as e:
                self.logger.error(f"Rate limit hit: {str(e)}")
                if attempt + 1 == self.max_retries:
                    return False
                time.sleep(self.retry_delay * (attempt + 1))  # Exponential backoff
                
            except stripe.error.InvalidRequestError as e:
                if "No such payment_method" in str(e):
                    self.logger.error(f"Invalid payment method token: {new_card_token}")
                elif "No such customer" in str(e):
                    self.logger.error(f"Invalid customer ID: {customer_id}")
                else:
                    self.logger.error(f"Invalid request to Stripe API: {str(e)}")
                return False
                
            except stripe.error.AuthenticationError as e:
                self.logger.error(f"Authentication with Stripe failed: {str(e)}")
                return False
                
            except stripe.error.APIConnectionError as e:
                self.logger.error(f"Network error connecting to Stripe: {str(e)}")
                if attempt + 1 == self.max_retries:
                    return False
                time.sleep(self.retry_delay * (attempt + 1))  # Exponential backoff
                
            except stripe.error.StripeError as e:
                self.logger.error(f"Stripe error: {str(e)}")
                return False
                
            except Exception as e:
                self.logger.error(f"Unexpected error updating payment method: {str(e)}")
                return False
                
        return False  # If we've exhausted all retries
        
    def create_payment_link(self, customer_id, return_path="/account/payment-updated", base_url=None):
        """
        Create a secure payment update link for a customer
        
        Args:
            customer_id (str): Stripe customer ID
            return_path (str): Path to redirect after payment update
            base_url (str, optional): Base URL for the return URL. If None, uses environment config
            
        Returns:
            str: URL for customer to update payment details, or None if failed
        """
        try:
            if not base_url:
                # Get from environment with fallback
                base_url = os.getenv("APP_BASE_URL", "https://hunchbank.example.com")
            
            # Ensure no trailing slash in base_url and leading slash in return_path
            base_url = base_url.rstrip("/")
            if not return_path.startswith("/"):
                return_path = f"/{return_path}"
                
            # Add security token to return URL to prevent CSRF
            security_token = self._generate_security_token(customer_id)
            return_url = f"{base_url}{return_path}?token={security_token}"
                
            # Create configuration for the portal
            configuration = {
                "business_profile": {
                    "headline": "Update your payment method securely",
                },
                "features": {
                    "payment_method_update": {
                        "enabled": True
                    },
                    # Disable other features for security
                    "subscription_cancel": {
                        "enabled": False
                    },
                    "subscription_update": {
                        "enabled": False
                    }
                }
            }
            
            # Check if configuration already exists, otherwise create it
            try:
                # Try to reuse existing configuration
                configs = self.stripe.billing_portal.Configuration.list(limit=1)
                if configs and configs.data:
                    config_id = configs.data[0].id
                else:
                    # Create a new configuration
                    config = self.stripe.billing_portal.Configuration.create(
                        business_profile={
                            "headline": "HunchBank Payment Management",
                            "privacy_policy_url": f"{base_url}/privacy-policy",
                            "terms_of_service_url": f"{base_url}/terms"
                        },
                        features={
                            "payment_method_update": {"enabled": True},
                            "subscription_cancel": {"enabled": False},
                            "subscription_update": {"enabled": False}
                        }
                    )
                    config_id = config.id
                    self.logger.info(f"Created new customer portal configuration: {config_id}")
            except stripe.error.StripeError as e:
                # Fallback to default configuration
                self.logger.warning(f"Could not create configuration, using default: {e}")
                config_id = None
                
            # Create session parameters
            session_params = {
                "customer": customer_id,
                "return_url": return_url,
            }
            
            # Add configuration if available
            if config_id:
                session_params["configuration"] = config_id
                
            # Create the session
            session = self.stripe.billing_portal.Session.create(**session_params)
            
            # Log session creation with redacted URL for security
            url_parts = session.url.split("?")
            base_url = url_parts[0]
            self.logger.info(f"Created secure payment portal session for {customer_id}: {base_url}...")
            
            # Store session info in a secure database/cache for verification
            self._store_session_info(customer_id, session.id, security_token)
            
            return session.url
            
        except stripe.error.StripeError as e:
            self.logger.error(f"Failed to create payment link: {str(e)}")
            return None
        except Exception as e:
            self.logger.error(f"Unexpected error creating payment link: {str(e)}")
            return None
            
    def _generate_security_token(self, customer_id):
        """
        Generate a secure token for return URL verification
        
        Args:
            customer_id (str): Stripe customer ID
            
        Returns:
            str: Secure token
        """
        # In production, use a proper crypto library and secret key
        import hashlib
        import time
        import os
        
        # Get secret key from environment with fallback
        secret_key = os.getenv("SECURITY_TOKEN_SECRET", "hunchbank-dev-secret-key")
        
        # Create timestamp and combine with customer_id and secret
        timestamp = str(int(time.time()))
        data = f"{customer_id}:{timestamp}:{secret_key}"
        
        # Create hash
        hash_obj = hashlib.sha256(data.encode())
        token = hash_obj.hexdigest()
        
        # Return token with timestamp for verification
        return f"{timestamp}.{token[:32]}"
        
    def _store_session_info(self, customer_id, session_id, security_token):
        """
        Store session information for verification on return
        In production, this would use a database or secure cache
        
        Args:
            customer_id (str): Stripe customer ID
            session_id (str): Stripe session ID
            security_token (str): Generated security token
        """
        # In a real system, this would store in a database or Redis cache
        # For now, log it (in production this would be a security risk)
        self.logger.info(f"Session info for verification - Customer: {customer_id}, Token: {security_token[:8]}...")
        
        # Simulate storage in a database
        # In production code, use proper database or cache:
        #
        # Example with Redis:
        # import redis
        # r = redis.Redis(host='localhost', port=6379, db=0)
        # r.setex(f"payment_session:{security_token}", 3600, json.dumps({
        #     "customer_id": customer_id,
        #     "session_id": session_id,
        #     "created_at": time.time()
        # }))
        #
        # Example with database:
        # database.execute(
        #     "INSERT INTO payment_sessions (customer_id, session_id, token, created_at) "
        #     "VALUES (%s, %s, %s, NOW())",
        #     (customer_id, session_id, security_token)
        # )
        pass
    
    def get_invoice(self, customer_id, invoice_id):
        """
        Get a specific invoice for a customer
        
        Args:
            customer_id (str): Stripe customer ID
            invoice_id (str): Stripe invoice ID
            
        Returns:
            dict: Invoice details or None if not found
        """
        try:
            invoice = self.stripe.Invoice.retrieve(invoice_id)
            # Verify that the invoice belongs to the customer
            if invoice.customer != customer_id:
                self.logger.warning(f"Invoice {invoice_id} does not belong to customer {customer_id}")
                return None
                
            return {
                "id": invoice.id,
                "amount_due": invoice.amount_due,
                "status": invoice.status,
                "created": datetime.fromtimestamp(invoice.created).strftime("%Y-%m-%d"),
                "hosted_invoice_url": invoice.hosted_invoice_url
            }
        except stripe.error.StripeError as e:
            self.logger.error(f"Failed to retrieve invoice {invoice_id}: {str(e)}")
            return None
    
    def get_recent_invoices(self, customer_id, limit=5):
        """
        Get recent invoices for a customer
        
        Args:
            customer_id (str): Stripe customer ID
            limit (int): Maximum number of invoices to return
            
        Returns:
            list: List of invoice details or empty list if none found
        """
        try:
            invoices = self.stripe.Invoice.list(customer=customer_id, limit=limit)
            
            if not invoices or not invoices.data:
                return []
                
            result = []
            for invoice in invoices.data:
                result.append({
                    "id": invoice.id,
                    "amount_due": invoice.amount_due,
                    "status": invoice.status,
                    "created": datetime.fromtimestamp(invoice.created).strftime("%Y-%m-%d"),
                    "hosted_invoice_url": invoice.hosted_invoice_url
                })
            return result
        except stripe.error.StripeError as e:
            self.logger.error(f"Failed to retrieve invoices for customer {customer_id}: {str(e)}")
            return []
    
    def get_payment_history(self, customer_id, limit=5):
        """
        Get payment history for a customer
        
        Args:
            customer_id (str): Stripe customer ID
            limit (int): Maximum number of payments to return
            
        Returns:
            list: List of payment details or empty list if none found
        """
        try:
            payments = self.stripe.PaymentIntent.list(customer=customer_id, limit=limit)
            
            if not payments or not payments.data:
                return []
                
            result = []
            for payment in payments.data:
                result.append({
                    "id": payment.id,
                    "amount": payment.amount,
                    "status": payment.status,
                    "created": datetime.fromtimestamp(payment.created).strftime("%Y-%m-%d"),
                    "payment_method": payment.payment_method
                })
            return result
        except stripe.error.StripeError as e:
            self.logger.error(f"Failed to retrieve payment history for customer {customer_id}: {str(e)}")
            return []
    
    def get_subscription(self, customer_id, subscription_id):
        """
        Get details for a specific subscription
        
        Args:
            customer_id (str): Stripe customer ID
            subscription_id (str): Stripe subscription ID
            
        Returns:
            dict: Subscription details or None if not found
        """
        try:
            subscription = self.stripe.Subscription.retrieve(subscription_id)
            
            # Verify that the subscription belongs to the customer
            if subscription.customer != customer_id:
                self.logger.warning(f"Subscription {subscription_id} does not belong to customer {customer_id}")
                return None
                
            # Get plan information
            plan_name = "Unknown Plan"
            amount = 0
            interval = "month"
            
            if subscription.items and subscription.items.data:
                item = subscription.items.data[0]
                if item.plan:
                    plan_name = item.plan.nickname or f"Plan {item.plan.id}"
                    amount = item.plan.amount
                    interval = item.plan.interval
            
            return {
                "id": subscription.id,
                "status": subscription.status,
                "current_period_end": datetime.fromtimestamp(subscription.current_period_end).strftime("%Y-%m-%d"),
                "current_period_start": datetime.fromtimestamp(subscription.current_period_start).strftime("%Y-%m-%d"),
                "plan_name": plan_name,
                "amount": amount,
                "interval": interval,
                "cancel_at_period_end": subscription.cancel_at_period_end
            }
        except stripe.error.StripeError as e:
            self.logger.error(f"Failed to retrieve subscription {subscription_id}: {str(e)}")
            return None
    
    def get_active_subscriptions(self, customer_id):
        """
        Get all active subscriptions for a customer
        
        Args:
            customer_id (str): Stripe customer ID
            
        Returns:
            list: List of subscription details or empty list if none found
        """
        try:
            subscriptions = self.stripe.Subscription.list(
                customer=customer_id,
                status="active",
                expand=["data.default_payment_method"]
            )
            
            if not subscriptions or not subscriptions.data:
                return []
                
            result = []
            for subscription in subscriptions.data:
                # Get plan information
                plan_name = "Unknown Plan"
                amount = 0
                interval = "month"
                
                if subscription.items and subscription.items.data:
                    item = subscription.items.data[0]
                    if item.plan:
                        plan_name = item.plan.nickname or f"Plan {item.plan.id}"
                        amount = item.plan.amount
                        interval = item.plan.interval
                
                result.append({
                    "id": subscription.id,
                    "status": subscription.status,
                    "current_period_end": datetime.fromtimestamp(subscription.current_period_end).strftime("%Y-%m-%d"),
                    "current_period_start": datetime.fromtimestamp(subscription.current_period_start).strftime("%Y-%m-%d"),
                    "plan_name": plan_name,
                    "amount": amount,
                    "interval": interval,
                    "cancel_at_period_end": subscription.cancel_at_period_end
                })
            return result
        except stripe.error.StripeError as e:
            self.logger.error(f"Failed to retrieve subscriptions for customer {customer_id}: {str(e)}")
            return []
    
    def change_subscription_plan(self, subscription_id, new_plan_id):
        """
        Change a subscription's plan
        
        Args:
            subscription_id (str): Stripe subscription ID
            new_plan_id (str): New plan ID to switch to
            
        Returns:
            bool: True if successful, False otherwise
        """
        for attempt in range(self.max_retries):
            try:
                # Get the subscription to find the subscription item ID
                subscription = self.stripe.Subscription.retrieve(subscription_id)
                
                if not subscription or not subscription.items or not subscription.items.data:
                    self.logger.error(f"Invalid subscription {subscription_id} or no items found")
                    return False
                
                # We need the subscription item ID to update the plan
                subscription_item_id = subscription.items.data[0].id
                
                # Update the subscription item with the new plan
                self.stripe.SubscriptionItem.modify(
                    subscription_item_id,
                    price=new_plan_id,
                    proration_behavior="create_prorations"
                )
                
                self.logger.info(f"Changed subscription {subscription_id} to plan {new_plan_id}")
                return True
                
            except stripe.error.RateLimitError as e:
                self.logger.error(f"Rate limit hit: {str(e)}")
                if attempt + 1 == self.max_retries:
                    return False
                time.sleep(self.retry_delay * (attempt + 1))
                
            except stripe.error.InvalidRequestError as e:
                self.logger.error(f"Invalid request to Stripe API: {str(e)}")
                return False
                
            except stripe.error.StripeError as e:
                self.logger.error(f"Stripe error changing subscription plan: {str(e)}")
                return False
                
            except Exception as e:
                self.logger.error(f"Unexpected error changing subscription plan: {str(e)}")
                return False
                
        return False  # If we've exhausted all retries
    
    def update_subscription_quantity(self, subscription_id, quantity):
        """
        Update the quantity of a subscription (e.g., number of seats)
        
        Args:
            subscription_id (str): Stripe subscription ID
            quantity (int): New quantity value
            
        Returns:
            bool: True if successful, False otherwise
        """
        for attempt in range(self.max_retries):
            try:
                # Get the subscription to find the subscription item ID
                subscription = self.stripe.Subscription.retrieve(subscription_id)
                
                if not subscription or not subscription.items or not subscription.items.data:
                    self.logger.error(f"Invalid subscription {subscription_id} or no items found")
                    return False
                
                # We need the subscription item ID to update the quantity
                subscription_item_id = subscription.items.data[0].id
                
                # Get current quantity
                current_quantity = subscription.items.data[0].quantity or 1
                
                # Calculate new quantity (adding to current)
                new_quantity = current_quantity + quantity
                
                # Update the subscription item with the new quantity
                self.stripe.SubscriptionItem.modify(
                    subscription_item_id,
                    quantity=new_quantity,
                    proration_behavior="create_prorations"
                )
                
                self.logger.info(f"Updated subscription {subscription_id} quantity from {current_quantity} to {new_quantity}")
                return True
                
            except stripe.error.RateLimitError as e:
                self.logger.error(f"Rate limit hit: {str(e)}")
                if attempt + 1 == self.max_retries:
                    return False
                time.sleep(self.retry_delay * (attempt + 1))
                
            except stripe.error.InvalidRequestError as e:
                self.logger.error(f"Invalid request to Stripe API: {str(e)}")
                return False
                
            except stripe.error.StripeError as e:
                self.logger.error(f"Stripe error updating subscription quantity: {str(e)}")
                return False
                
            except Exception as e:
                self.logger.error(f"Unexpected error updating subscription quantity: {str(e)}")
                return False
                
        return False  # If we've exhausted all retries
    
    def cancel_subscription(self, subscription_id, immediate=False):
        """
        Cancel a subscription either immediately or at period end
        
        Args:
            subscription_id (str): Stripe subscription ID
            immediate (bool): If True, cancel immediately; if False, cancel at period end
            
        Returns:
            bool: True if successful, False otherwise
        """
        for attempt in range(self.max_retries):
            try:
                if immediate:
                    # Cancel immediately
                    self.stripe.Subscription.delete(subscription_id)
                    self.logger.info(f"Canceled subscription {subscription_id} immediately")
                else:
                    # Cancel at period end
                    self.stripe.Subscription.modify(
                        subscription_id,
                        cancel_at_period_end=True
                    )
                    self.logger.info(f"Scheduled subscription {subscription_id} to cancel at period end")
                
                return True
                
            except stripe.error.RateLimitError as e:
                self.logger.error(f"Rate limit hit: {str(e)}")
                if attempt + 1 == self.max_retries:
                    return False
                time.sleep(self.retry_delay * (attempt + 1))
                
            except stripe.error.InvalidRequestError as e:
                self.logger.error(f"Invalid request to Stripe API: {str(e)}")
                return False
                
            except stripe.error.StripeError as e:
                self.logger.error(f"Stripe error canceling subscription: {str(e)}")
                return False
                
            except Exception as e:
                self.logger.error(f"Unexpected error canceling subscription: {str(e)}")
                return False
                
        return False  # If we've exhausted all retries
    
    def get_recent_charges(self, customer_id, limit=5):
        """
        Get recent charges for a customer
        
        Args:
            customer_id (str): Stripe customer ID
            limit (int): Maximum number of charges to return
            
        Returns:
            list: List of charge details or empty list if none found
        """
        try:
            charges = self.stripe.Charge.list(customer=customer_id, limit=limit)
            
            if not charges or not charges.data:
                return []
                
            result = []
            for charge in charges.data:
                result.append({
                    "id": charge.id,
                    "amount": charge.amount,
                    "status": charge.status,
                    "created": datetime.fromtimestamp(charge.created).strftime("%Y-%m-%d"),
                    "payment_method": charge.payment_method
                })
            return result
        except stripe.error.StripeError as e:
            self.logger.error(f"Failed to retrieve charges for customer {customer_id}: {str(e)}")
            return []
    
    def create_refund(self, charge_id, amount=None, reason=None):
        """
        Create a refund for a charge
        
        Args:
            charge_id (str): Stripe charge ID to refund
            amount (int, optional): Amount to refund in cents, or None for full refund
            reason (str, optional): Reason for the refund
            
        Returns:
            bool: True if successful, False otherwise
        """
        for attempt in range(self.max_retries):
            try:
                refund_params = {"charge": charge_id}
                
                if amount:
                    refund_params["amount"] = amount
                    
                if reason:
                    refund_params["reason"] = "requested_by_customer"  # Stripe only accepts specific values
                    refund_params["metadata"] = {"detailed_reason": reason}
                
                refund = self.stripe.Refund.create(**refund_params)
                
                if refund and refund.status in ["succeeded", "pending"]:
                    self.logger.info(f"Created refund for charge {charge_id}: {refund.id}")
                    return True
                else:
                    self.logger.error(f"Refund creation failed with status: {refund.status}")
                    return False
                
            except stripe.error.RateLimitError as e:
                self.logger.error(f"Rate limit hit: {str(e)}")
                if attempt + 1 == self.max_retries:
                    return False
                time.sleep(self.retry_delay * (attempt + 1))
                
            except stripe.error.InvalidRequestError as e:
                self.logger.error(f"Invalid request to Stripe API: {str(e)}")
                return False
                
            except stripe.error.StripeError as e:
                self.logger.error(f"Stripe error creating refund: {str(e)}")
                return False
                
            except Exception as e:
                self.logger.error(f"Unexpected error creating refund: {str(e)}")
                return False
                
        return False  # If we've exhausted all retries
    
    def get_dispute(self, dispute_id):
        """
        Get details of a specific dispute
        
        Args:
            dispute_id (str): Stripe dispute ID
            
        Returns:
            dict: Dispute details or None if not found
        """
        try:
            dispute = self.stripe.Dispute.retrieve(dispute_id)
            
            return {
                "id": dispute.id,
                "charge": dispute.charge,
                "amount": dispute.amount,
                "status": dispute.status,
                "reason": dispute.reason,
                "created": datetime.fromtimestamp(dispute.created).strftime("%Y-%m-%d")
            }
        except stripe.error.StripeError as e:
            self.logger.error(f"Failed to retrieve dispute {dispute_id}: {str(e)}")
            return None
    
    def get_charge_details(self, charge_id):
        """
        Get detailed information about a charge
        
        Args:
            charge_id (str): Stripe charge ID
            
        Returns:
            dict: Charge details or None if not found
        """
        for attempt in range(self.max_retries):
            try:
                charge = self.stripe.Charge.retrieve(
                    charge_id,
                    expand=["customer", "payment_method", "payment_method_details", "refunds"]
                )
                
                # Return the full charge object as a dict
                charge_dict = dict(charge)
                
                # Log charge retrieval with sensitive data redacted
                redacted_log = f"Retrieved charge {charge_id}: amount={charge.amount}, status={charge.status}"
                self.logger.info(redacted_log)
                
                return charge_dict
                
            except stripe.error.RateLimitError as e:
                self.logger.error(f"Rate limit hit: {str(e)}")
                if attempt + 1 == self.max_retries:
                    return None
                time.sleep(self.retry_delay * (attempt + 1))
                
            except stripe.error.InvalidRequestError as e:
                self.logger.error(f"Invalid charge ID {charge_id}: {str(e)}")
                return None
                
            except stripe.error.AuthenticationError as e:
                self.logger.error(f"Authentication error retrieving charge: {str(e)}")
                return None
                
            except stripe.error.APIConnectionError as e:
                self.logger.error(f"Network error connecting to Stripe: {str(e)}")
                if attempt + 1 == self.max_retries:
                    return None
                time.sleep(self.retry_delay * (attempt + 1))
                
            except stripe.error.StripeError as e:
                self.logger.error(f"Stripe error retrieving charge {charge_id}: {str(e)}")
                return None
                
            except Exception as e:
                self.logger.error(f"Unexpected error retrieving charge {charge_id}: {str(e)}")
                return None
                
        return None  # If we've exhausted all retries
        
    def get_customer_refunds(self, customer_id, limit=10):
        """
        Get a customer's recent refunds
        
        Args:
            customer_id (str): Stripe customer ID
            limit (int): Maximum number of refunds to retrieve
            
        Returns:
            list: List of refund objects or empty list if none found
        """
        try:
            # First get all charges for this customer
            charges = self.stripe.Charge.list(customer=customer_id, limit=100)
            
            # Extract the charge IDs
            charge_ids = [charge.id for charge in charges.data]
            
            if not charge_ids:
                return []
                
            # Get refunds for these charges
            all_refunds = []
            for charge_id in charge_ids:
                refunds = self.stripe.Refund.list(charge=charge_id)
                all_refunds.extend(refunds.data)
                
                # Stop once we have enough refunds
                if len(all_refunds) >= limit:
                    break
            
            # Convert to dictionaries and sort by creation date (newest first)
            refund_dicts = [dict(refund) for refund in all_refunds]
            refund_dicts.sort(key=lambda x: x.get("created", 0), reverse=True)
            
            # Return only the requested number
            return refund_dicts[:limit]
            
        except stripe.error.StripeError as e:
            self.logger.error(f"Failed to retrieve refunds for customer {customer_id}: {str(e)}")
            return []
        except Exception as e:
            self.logger.error(f"Unexpected error retrieving refunds: {str(e)}")
            return []
