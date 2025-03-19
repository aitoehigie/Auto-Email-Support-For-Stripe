# HunchBank Auto Email Support Troubleshooting Guide

This guide provides troubleshooting tips and sample log entries to help diagnose and resolve common issues with the HunchBank Auto Email Support system.

## Log Analysis

The application logs are your primary source of information when diagnosing issues. Below are examples of common log patterns and what they indicate.

### Log Location

All logs are stored in the `logs/` directory, with the main application log at `logs/hunchbank.log`.

### Sample Log Entries

#### Successful Email Processing Flow

```
2025-03-19 10:00:01 - Main - INFO - Connecting to email server...
2025-03-19 10:00:02 - Main - INFO - Fetching emails...
2025-03-19 10:00:03 - Main - INFO - Processing email from customer@example.com
2025-03-19 10:00:04 - Main - INFO - Intent: billing_inquiry, Confidence: 0.95, Entities: {"account_id": "acct_123456"}
2025-03-19 10:00:05 - Main - INFO - Handling billing_inquiry for customer@example.com
2025-03-19 10:00:06 - Main - INFO - Email marked as read and processed successfully
```

This indicates successful processing of an email with a billing inquiry.

#### Email Connection Issues

```
2025-03-19 10:02:01 - Main - ERROR - SMTP SSL error (attempt 1): Connection refused
2025-03-19 10:02:10 - Main - ERROR - SMTP SSL error (attempt 2): Connection refused
2025-03-19 10:02:30 - Main - ERROR - SMTP SSL error (attempt 3): Connection refused
2025-03-19 10:03:01 - EmailService - ERROR - Failed to connect after 3 attempts
```

This indicates connection problems with the email server. Check your internet connection and email server settings in the `.env` file.

#### Human Review Flow

```
2025-03-19 10:05:01 - Main - INFO - Processing email from user5@example.com
2025-03-19 10:05:02 - Main - INFO - Intent: unknown, Confidence: 0.25, Entities: {}
2025-03-19 10:05:03 - Main - INFO - Sending to human review: intent=unknown, confidence=0.25
2025-03-19 10:05:04 - ReviewSystem - INFO - Added review rev_1715936703_0 to queue - Intent: unknown, Risk: medium
```

This shows an email being routed to human review due to low confidence.

#### API Errors

```
2025-03-19 10:04:01 - Main - ERROR - API error: Rate limit exceeded
2025-03-19 10:04:02 - StripeService - ERROR - Failed to process payment update: Rate limit exceeded
```

This indicates issues with external API services. Check your API keys and usage limits.

## Common Issues and Solutions

### Email Connection Problems

**Symptoms in logs:**
```
SMTP SSL error (attempt 1): Connection refused
```

**Solutions:**
1. Verify EMAIL_USER and EMAIL_PASS in .env file
2. For Gmail, ensure you've enabled "Less secure app access" or created an App Password
3. Check your internet connection
4. Try alternative SMTP settings (TLS on port 587)

### Missing Logs Directory

**Symptoms:**
- Application crashes with file not found errors related to logs
- Logs not being created

**Solutions:**
1. Run one of the installation scripts which will create the logs directory
2. Manually create the logs directory: `mkdir -p logs`
3. Ensure the application has write permissions to this directory

### Dashboard Not Updating in Real-time

**Symptoms in logs:**
- No errors, but dashboard metrics stay at 0 or don't change

**Solutions:**
1. Check logs for processing activities
2. Ensure log files are being written to with proper permissions
3. The dashboard should read log data to update metrics

### Low Intent Classification Confidence

**Symptoms in logs:**
```
Intent: unknown, Confidence: 0.25
```

**Solutions:**
1. Train your NLP model with more examples
2. Check the format of incoming emails
3. Adjust the CONFIDENCE_THRESHOLD in config

## Testing Your Installation

Run the test email script to verify your email configuration:
```
python test_email.py
```

Expected log output:
```
INFO - Test - Testing email configuration
INFO - Test - Connected to SMTP server
INFO - Test - Test email sent successfully
```

## Still Having Issues?

1. Share your logs (after removing sensitive information)
2. Describe the exact steps that triggered the issue
3. Include your system information (OS, Python version)
4. File an issue in the GitHub repository with the above information