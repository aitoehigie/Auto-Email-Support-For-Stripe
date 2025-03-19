# HunchBank Auto Email Support

A robust system for automatically handling customer support emails for banking and payment-related inquiries. The system uses natural language processing to classify email intents, process requests through appropriate service handlers, and provide timely responses to customers.

## Features

- **Automated Email Processing**: Connects to email servers, fetches unread messages, and processes them based on intent
- **Natural Language Understanding**: Classifies customer intents like payment updates, billing inquiries, and refund requests
- **Stripe Integration**: Interfaces with Stripe API to handle payment-related requests
- **Human Review System**: Routes low-confidence or high-risk requests to human operators
- **Robust Email Handling**: Dual-method approach with SSL/TLS fallback and retry mechanisms
- **Command Line Interface**: Monitor and manage system operations

## Use Cases

- Handling payment method updates
- Processing billing inquiries
- Managing subscription changes
- Routing refund requests and payment disputes
- Responding to general customer inquiries

## Getting Started

### Prerequisites

- Python 3.8 or higher
- Gmail account (or other email provider)
- Stripe account with API access
- NLP service API key

### Installation

1. Clone the repository
   ```bash
   git clone https://github.com/yourusername/hunchbank_auto_email_support.git
   cd hunchbank_auto_email_support
   ```

2. Install dependencies
   ```bash
   pip install -r requirements.txt
   ```

3. Create a `.env` file with required credentials
   ```
   EMAIL_USER=your.email@gmail.com
   EMAIL_PASS=your-password-or-app-password
   STRIPE_API_KEY=sk_test_your_stripe_key
   NLP_API_KEY=your-nlp-service-key
   ```

### Email Configuration

For Gmail accounts:
- **With 2FA enabled**: Generate an App Password at https://myaccount.google.com/apppasswords
- **Without 2FA**: Enable "Less secure app access" at https://myaccount.google.com/lesssecureapps

Use the test script to verify your email configuration:
```bash
python test_email.py
```

## Usage

### Running the System

```bash
python main.py
```

This starts the main application with:
- Email processing in the background
- Command-line interface for monitoring and management

### Troubleshooting

If you encounter any issues, refer to the [Troubleshooting Guide](TROUBLESHOOTING.md) which includes:
- Sample log entries for common scenarios
- Solutions for typical problems
- Log directory information

### System Components

- **Email Service**: Handles email fetching and sending
- **NLP Service**: Classifies email intents and extracts entities
- **Stripe Service**: Interfaces with Stripe API
- **Response Service**: Generates and sends appropriate responses
- **Handlers**: Process specific types of requests (payments, billing, etc.)
- **Review System**: Manages human review queue for complex cases

## Architecture

The system uses a modular architecture with the following components:

- **Services**: Core functionality providers (email, NLP, payments)
- **Handlers**: Business logic for different request types
- **CLI**: User interface for system monitoring and management
- **Human Loop**: Review system for manual intervention
- **Utils**: Shared utilities like logging and configuration

## Logging System

The application maintains extensive logs to help with monitoring and troubleshooting:

### Log Directory Structure

- `logs/` - Main directory for all log files (created automatically on first run)
  - `hunchbank.log` - Primary application log with all system events
  - `{additional log files}` - Service-specific logs may be created as needed

### Log Format

Log entries follow this standard format:
```
YYYY-MM-DD HH:MM:SS - ComponentName - LEVEL - Message
```

Example:
```
2025-03-19 10:00:01 - Main - INFO - Connecting to email server...
2025-03-19 10:00:05 - Main - INFO - Handling billing_inquiry for customer@example.com
2025-03-19 10:02:01 - Main - ERROR - SMTP SSL error (attempt 1): Connection refused
```

### Common Log Entries

- Email processing events (fetching, processing, sending)
- Intent classification results
- Error events with detailed context
- System startup and shutdown events
- Review system activities

Logs are automatically rotated to prevent excessive disk usage (max 10MB per file, keeping 5 backups).

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add some amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Acknowledgments

- Thanks to all the open-source libraries this project depends on
- Inspired by the need for efficient customer support automation in fintech
