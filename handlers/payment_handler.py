from services.stripe_service import StripeService
from utils.logger import setup_logger

class PaymentHandler:
    def __init__(self):
        self.logger = setup_logger("PaymentHandler")
        self.stripe_service = StripeService()

    def handle(self, customer_id, entities):
        """
        Handle payment method update requests
        
        Args:
            customer_id (str): Stripe customer ID
            entities (dict): Extracted entities from email
            
        Returns:
            tuple: (success, message)
                - success (bool): Whether the operation was successful
                - message (str): Detailed message about the operation
        """
        try:
            self.logger.info(f"Processing payment update for customer {customer_id}")
            
            # Validate customer ID
            if not customer_id:
                self.logger.error("Missing customer ID")
                return False, "Your account couldn't be identified. Please contact support."
            
            # In a real-world scenario, we wouldn't have card tokens directly
            # Instead, we'd generate a secure link for the customer
            # The placeholder logic below is just for simulation
            card_token = entities.get("card_token")
            if card_token:
                self.logger.info(f"Using provided card token: {card_token[:4]}...")
                success = self.stripe_service.update_payment_method(customer_id, card_token)
                if success:
                    self.logger.info(f"Successfully updated payment method for {customer_id}")
                    return True, "Your payment method has been updated successfully."
                else:
                    self.logger.error(f"Failed to update payment method for {customer_id}")
                    return False, "We couldn't update your payment method. Please use the secure link we'll provide."
            else:
                # In real scenarios, we'd generate a payment link instead
                payment_link = self.stripe_service.create_payment_link(customer_id)
                if payment_link:
                    self.logger.info(f"Generated payment link for {customer_id}")
                    return False, "We'll need to verify your payment details securely."
                else:
                    self.logger.error(f"Failed to generate payment link for {customer_id}")
                    return False, "We couldn't process your request. Our team will contact you shortly."
        
        except Exception as e:
            self.logger.error(f"Payment handling failed: {str(e)}", exc_info=True)
            return False, "An unexpected error occurred. Our team has been notified."

class BillingHandler:
    def __init__(self):
        self.logger = setup_logger("BillingHandler")
        self.stripe_service = StripeService()
    
    def handle(self, customer_id, entities):
        """
        Handle billing inquiries and related requests
        
        Args:
            customer_id (str): Stripe customer ID
            entities (dict): Extracted entities from email
            
        Returns:
            tuple: (success, message)
                - success (bool): Whether the operation was successful
                - message (str): Detailed message about the operation
        """
        try:
            self.logger.info(f"Processing billing inquiry for customer {customer_id}")
            
            # Validate customer ID
            if not customer_id:
                self.logger.error("Missing customer ID")
                return False, "Your account couldn't be identified. Please contact support."
            
            # Determine the type of billing inquiry
            inquiry_type = entities.get("inquiry_type")
            
            if inquiry_type == "invoice":
                invoice_id = entities.get("invoice_id")
                if invoice_id:
                    invoice = self.stripe_service.get_invoice(customer_id, invoice_id)
                    if invoice:
                        return True, f"Your invoice {invoice_id} for ${invoice.get('amount_due')/100} was issued on {invoice.get('created')}."
                    else:
                        return False, f"We couldn't find invoice {invoice_id} for your account."
                else:
                    # Return recent invoices
                    invoices = self.stripe_service.get_recent_invoices(customer_id)
                    if invoices:
                        invoice_list = "\n".join([f"- Invoice {inv.get('id')}: ${inv.get('amount_due')/100} ({inv.get('status')}) - {inv.get('created')}" for inv in invoices[:3]])
                        return True, f"Here are your recent invoices:\n{invoice_list}"
                    else:
                        return False, "We couldn't find any recent invoices for your account."
            
            elif inquiry_type == "payment_history":
                payments = self.stripe_service.get_payment_history(customer_id)
                if payments:
                    payment_list = "\n".join([f"- Payment of ${p.get('amount')/100} on {p.get('created')} ({p.get('status')})" for p in payments[:3]])
                    return True, f"Here are your recent payments:\n{payment_list}"
                else:
                    return False, "We couldn't find any recent payment records for your account."
            
            elif inquiry_type == "subscription":
                subscription_id = entities.get("subscription_id")
                if subscription_id:
                    subscription = self.stripe_service.get_subscription(customer_id, subscription_id)
                    if subscription:
                        return True, f"Your subscription {subscription_id} is currently {subscription.get('status')} and will renew on {subscription.get('current_period_end')}."
                    else:
                        return False, f"We couldn't find subscription {subscription_id} for your account."
                else:
                    subscriptions = self.stripe_service.get_active_subscriptions(customer_id)
                    if subscriptions:
                        sub_list = "\n".join([f"- Plan: {sub.get('plan_name')} (${sub.get('amount')/100}/{sub.get('interval')}) - Next billing: {sub.get('current_period_end')}" for sub in subscriptions])
                        return True, f"Here are your active subscriptions:\n{sub_list}"
                    else:
                        return False, "We couldn't find any active subscriptions for your account."
            
            else:
                return False, "We need more information about your billing inquiry. Please specify if you're asking about invoices, payments, or subscriptions."
                
        except Exception as e:
            self.logger.error(f"Billing inquiry handling failed: {str(e)}", exc_info=True)
            return False, "An unexpected error occurred with your billing inquiry. Our team has been notified."

class SubscriptionHandler:
    def __init__(self):
        self.logger = setup_logger("SubscriptionHandler")
        self.stripe_service = StripeService()
    
    def handle(self, customer_id, entities):
        """
        Handle subscription-related requests (change plan, add seats, cancel)
        
        Args:
            customer_id (str): Stripe customer ID
            entities (dict): Extracted entities from email
            
        Returns:
            tuple: (success, message)
                - success (bool): Whether the operation was successful
                - message (str): Detailed message about the operation
        """
        try:
            self.logger.info(f"Processing subscription request for customer {customer_id}")
            
            # Validate customer ID
            if not customer_id:
                self.logger.error("Missing customer ID")
                return False, "Your account couldn't be identified. Please contact support."
            
            # Determine the type of subscription request
            request_type = entities.get("request_type")
            subscription_id = entities.get("subscription_id")
            
            # Get the subscription if ID is provided
            subscription = None
            if subscription_id:
                subscription = self.stripe_service.get_subscription(customer_id, subscription_id)
                if not subscription:
                    return False, f"We couldn't find subscription {subscription_id} for your account."
            else:
                # Try to get the active subscription if ID not provided
                subscriptions = self.stripe_service.get_active_subscriptions(customer_id)
                if subscriptions:
                    subscription = subscriptions[0]  # Use the first active subscription
                    subscription_id = subscription.get("id")
                else:
                    return False, "You don't have any active subscriptions. Please contact support for assistance."
            
            if request_type == "change_plan":
                new_plan = entities.get("new_plan")
                if not new_plan:
                    return False, "Please specify which plan you would like to switch to."
                
                success = self.stripe_service.change_subscription_plan(subscription_id, new_plan)
                if success:
                    return True, f"Your subscription has been updated to the {new_plan} plan. Changes will be reflected in your next billing cycle."
                else:
                    return False, f"We couldn't update your plan to {new_plan}. Please contact support for assistance."
            
            elif request_type == "add_seats":
                seat_count = entities.get("seat_count")
                if not seat_count:
                    return False, "Please specify how many seats you would like to add."
                
                try:
                    seat_count = int(seat_count)
                except ValueError:
                    return False, "The number of seats must be a valid number."
                
                success = self.stripe_service.update_subscription_quantity(subscription_id, seat_count)
                if success:
                    return True, f"Your subscription has been updated with {seat_count} additional seats. Changes will be reflected in your next invoice."
                else:
                    return False, "We couldn't update your seat count. Please contact support for assistance."
            
            elif request_type == "cancel":
                reason = entities.get("reason", "Not specified")
                
                # For cancellations, we may want human review for retention purposes
                if entities.get("immediate", "false").lower() == "true":
                    success = self.stripe_service.cancel_subscription(subscription_id, immediate=True)
                    message = "Your subscription has been canceled immediately."
                else:
                    success = self.stripe_service.cancel_subscription(subscription_id, immediate=False)
                    message = "Your subscription has been scheduled to cancel at the end of the current billing period."
                
                if success:
                    self.logger.info(f"Subscription {subscription_id} canceled. Reason: {reason}")
                    return True, message
                else:
                    return False, "We couldn't process your cancellation request. Please contact support."
            
            else:
                return False, "Please specify what you'd like to do with your subscription (change plan, add seats, or cancel)."
                
        except Exception as e:
            self.logger.error(f"Subscription handling failed: {str(e)}", exc_info=True)
            return False, "An unexpected error occurred with your subscription request. Our team has been notified."

class RefundHandler:
    def __init__(self):
        self.logger = setup_logger("RefundHandler")
        self.stripe_service = StripeService()
    
    def handle(self, customer_id, entities):
        """
        Handle refund requests
        
        Args:
            customer_id (str): Stripe customer ID
            entities (dict): Extracted entities from email
            
        Returns:
            tuple: (success, message)
                - success (bool): Whether the operation was successful
                - message (str): Detailed message about the operation
        """
        try:
            self.logger.info(f"Processing refund request for customer {customer_id}")
            
            # Validate customer ID
            if not customer_id:
                self.logger.error("Missing customer ID")
                return False, "Your account couldn't be identified. Please contact support."
            
            # For refunds, we typically need a charge ID or payment intent ID
            charge_id = entities.get("charge_id") or entities.get("payment_intent")
            
            if not charge_id:
                # Try to get recent charges to see if we can help identify the payment
                charges = self.stripe_service.get_recent_charges(customer_id)
                if charges:
                    charge_list = "\n".join([f"- Charge {c.get('id')}: ${c.get('amount')/100} on {c.get('created')}" for c in charges[:3]])
                    return False, f"Please specify which charge you would like refunded. Here are your recent charges:\n{charge_list}"
                else:
                    return False, "We couldn't find any recent charges for your account. Please provide more details about the payment you'd like refunded."
            
            # Refund reason is important for record-keeping
            reason = entities.get("reason", "Customer request")
            
            # Get the amount for the refund
            amount = entities.get("amount")
            refund_amount_cents = None
            if amount:
                try:
                    refund_amount_cents = int(float(amount) * 100)  # Convert to cents
                except ValueError:
                    return False, "The refund amount provided is not valid. Please provide a valid amount."
            
            # Get detailed charge information for fraud prevention
            charge_details = self.stripe_service.get_charge_details(charge_id)
            if not charge_details:
                return False, "We couldn't retrieve details for this charge. Our team will review your request."
                
            # Run through fraud prevention checks
            fraud_score, risk_factors = self._check_refund_risk(
                customer_id, 
                charge_id, 
                refund_amount_cents, 
                charge_details,
                reason
            )
            
            # Auto-approve low-risk refunds under threshold
            auto_approve_threshold = 0.3  # 0-1 scale, lower means less risk
            auto_approve_amount_threshold = 2000  # $20 in cents
            
            if fraud_score <= auto_approve_threshold and (refund_amount_cents is None or refund_amount_cents <= auto_approve_amount_threshold):
                # Safe to auto-approve
                refund_amount_str = f"${refund_amount_cents/100:.2f}" if refund_amount_cents else "full amount"
                success = self.stripe_service.create_refund(charge_id, refund_amount_cents, reason)
                
                if success:
                    self.logger.info(f"Auto-approved refund for charge {charge_id}: {refund_amount_str}, fraud score: {fraud_score:.2f}")
                    return True, f"We've processed your refund of {refund_amount_str}. It may take 5-10 business days to appear on your statement."
                else:
                    self.logger.warning(f"Failed to process auto-approved refund for charge {charge_id}")
                    return False, "We couldn't process your refund automatically. Our team will review your request and contact you."
            else:
                # Log reasons for sending to manual review
                risk_reason = "high amount" if refund_amount_cents and refund_amount_cents > auto_approve_amount_threshold else "high risk score"
                self.logger.info(f"Sending refund to review: {risk_reason}, score: {fraud_score:.2f}, amount: {refund_amount_cents}, factors: {risk_factors}")
                
                # Store risk assessment for human reviewers
                entities["risk_assessment"] = {
                    "fraud_score": fraud_score,
                    "risk_factors": risk_factors,
                    "charge_details": {
                        "amount": charge_details.get("amount"),
                        "date": charge_details.get("created", "Unknown"),
                        "payment_method": charge_details.get("payment_method_details", {}).get("type", "Unknown"),
                        "status": charge_details.get("status")
                    }
                }
                
                return False, "Your refund request has been submitted for review. Our team will process it within 1-2 business days."
                
        except Exception as e:
            self.logger.error(f"Refund handling failed: {str(e)}", exc_info=True)
            return False, "An unexpected error occurred with your refund request. Our team has been notified and will contact you."
    
    def _check_refund_risk(self, customer_id, charge_id, refund_amount_cents, charge_details, reason):
        """
        Perform fraud prevention checks for refund requests
        
        Args:
            customer_id (str): Stripe customer ID
            charge_id (str): Stripe charge ID
            refund_amount_cents (int): Refund amount in cents, or None for full refund
            charge_details (dict): Charge details from Stripe
            reason (str): Refund reason provided by customer
            
        Returns:
            tuple: (fraud_score, risk_factors)
                - fraud_score (float): 0-1 risk score (higher = more risky)
                - risk_factors (list): List of identified risk factors
        """
        risk_factors = []
        fraud_score = 0.0
        
        # Get customer history 
        payment_history = self.stripe_service.get_payment_history(customer_id)
        previous_refunds = self.stripe_service.get_customer_refunds(customer_id)
        
        # Check charge age (newer charges are higher risk)
        charge_age_days = None
        if "created" in charge_details:
            try:
                from datetime import datetime, timezone
                created_timestamp = charge_details["created"]
                charge_time = datetime.fromtimestamp(created_timestamp, tz=timezone.utc)
                now = datetime.now(timezone.utc)
                charge_age_days = (now - charge_time).days
                
                if charge_age_days < 1:
                    risk_factors.append("very_recent_charge")
                    fraud_score += 0.3
                elif charge_age_days < 3:
                    risk_factors.append("recent_charge")
                    fraud_score += 0.15
                elif charge_age_days > 60:
                    risk_factors.append("old_charge")
                    fraud_score += 0.1
            except (KeyError, ValueError, TypeError) as e:
                self.logger.warning(f"Error calculating charge age: {str(e)}")
        
        # Check charge amount vs refund amount
        charge_amount = charge_details.get("amount", 0)
        if refund_amount_cents is not None and charge_amount > 0:
            refund_percentage = refund_amount_cents / charge_amount
            if refund_percentage < 0.2:
                # Small partial refunds are lower risk
                pass
            elif refund_percentage > 0.9 and refund_percentage < 1.0:
                # Unusual to request almost-full but not full refund
                risk_factors.append("near_full_refund")
                fraud_score += 0.15
        
        # Check refund reason
        if not reason or reason == "Customer request":
            risk_factors.append("generic_reason")
            fraud_score += 0.1
            
        # Check customer refund history
        if previous_refunds:
            recent_refund_count = sum(1 for r in previous_refunds if r.get("created", 0) > (datetime.now().timestamp() - 60*86400))
            if recent_refund_count > 3:
                risk_factors.append("multiple_recent_refunds")
                fraud_score += 0.3
            elif recent_refund_count > 1:
                risk_factors.append("has_recent_refunds")
                fraud_score += 0.1
                
            # Calculate refund ratio
            if len(payment_history) > 0:
                refund_ratio = len(previous_refunds) / len(payment_history)
                if refund_ratio > 0.5:
                    risk_factors.append("high_refund_ratio")
                    fraud_score += 0.25
                elif refund_ratio > 0.3:
                    risk_factors.append("elevated_refund_ratio")
                    fraud_score += 0.1
        
        # Check payment method risk
        payment_method = charge_details.get("payment_method_details", {}).get("type", "unknown")
        if payment_method == "card":
            card_details = charge_details.get("payment_method_details", {}).get("card", {})
            
            # Higher risk factors for certain card scenarios
            if card_details.get("checks", {}).get("cvc_check") == "fail":
                risk_factors.append("cvc_check_failed")
                fraud_score += 0.3
                
            if card_details.get("checks", {}).get("address_line1_check") == "fail":
                risk_factors.append("address_check_failed")
                fraud_score += 0.2
        
        # Cap the score at 1.0
        fraud_score = min(fraud_score, 1.0)
        
        return fraud_score, risk_factors

class DisputeHandler:
    def __init__(self):
        self.logger = setup_logger("DisputeHandler")
        self.stripe_service = StripeService()
    
    def handle(self, customer_id, entities):
        """
        Handle payment dispute inquiries
        
        Args:
            customer_id (str): Stripe customer ID
            entities (dict): Extracted entities from email
            
        Returns:
            tuple: (success, message)
                - success (bool): Whether the operation was successful
                - message (str): Detailed message about the operation
        """
        try:
            self.logger.info(f"Processing dispute inquiry for customer {customer_id}")
            
            # Validate customer ID
            if not customer_id:
                self.logger.error("Missing customer ID")
                return False, "Your account couldn't be identified. Please contact support."
            
            # Dispute handling needs significant human intervention
            # This handler mostly gathers info and creates a structured record
            
            dispute_id = entities.get("dispute_id")
            charge_id = entities.get("charge_id")
            reason = entities.get("reason", "Not specified")
            
            # Record detailed info about the dispute
            details = {
                "customer_id": customer_id,
                "dispute_id": dispute_id,
                "charge_id": charge_id,
                "reason": reason,
                "status": "pending_review",
                "created": entities.get("timestamp")
            }
            
            # In a real system, we'd save this to a database and notify the disputes team
            self.logger.info(f"Dispute details: {details}")
            
            # Check if there's an existing dispute in Stripe
            if dispute_id:
                dispute = self.stripe_service.get_dispute(dispute_id)
                if dispute:
                    status = dispute.get("status")
                    return True, f"Your dispute (ID: {dispute_id}) is currently marked as '{status}'. Our team is working to resolve this issue."
            
            # Always route disputes to human review
            return False, "We've received your dispute inquiry. Our team will investigate and contact you within 1-2 business days."
            
        except Exception as e:
            self.logger.error(f"Dispute handling failed: {str(e)}", exc_info=True)
            return False, "An unexpected error occurred with your dispute inquiry. Our team has been notified and will contact you shortly."
