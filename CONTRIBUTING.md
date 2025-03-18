# Contributing to HunchBank Auto Email Support

Thank you for considering contributing to the HunchBank Auto Email Support project! This document provides guidelines and instructions for contributing.

## Code of Conduct

Please be respectful and considerate of others when contributing to this project. We aim to foster an inclusive and positive community.

## How Can I Contribute?

### Reporting Bugs

Bugs are tracked as GitHub issues. When you create an issue, please include:

- A clear and descriptive title
- Steps to reproduce the problem
- Expected and actual behavior
- Any relevant screenshots
- Environment details (OS, Python version, etc.)

### Suggesting Enhancements

Enhancement suggestions are also tracked as GitHub issues. When suggesting an enhancement, please include:

- A clear and descriptive title
- A detailed explanation of the proposed feature
- Any potential implementation ideas
- Why this enhancement would be useful

### Pull Requests

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Make your changes
4. Ensure your code follows the project's style guidelines
5. Add tests for your changes if applicable
6. Commit your changes (`git commit -m 'Add some amazing feature'`)
7. Push to the branch (`git push origin feature/amazing-feature`)
8. Open a Pull Request

## Development Environment Setup

1. Clone your fork of the repository
   ```bash
   git clone https://github.com/yourusername/hunchbank_auto_email_support.git
   cd hunchbank_auto_email_support
   ```

2. Create a virtual environment and activate it
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. Install dependencies
   ```bash
   pip install -r requirements.txt
   pip install -r requirements-dev.txt  # Development dependencies
   ```

4. Create a `.env` file with test credentials
   ```
   EMAIL_USER=test@example.com
   EMAIL_PASS=test-password
   STRIPE_API_KEY=sk_test_your_test_key
   NLP_API_KEY=your-test-nlp-key
   ```

## Coding Style Guidelines

- Follow PEP 8 guidelines for Python code
- Use type hints for function parameters and return values
- Write descriptive docstrings for classes and functions
- Use meaningful variable and function names
- Group imports in this order: standard library, third-party, local
- Use appropriate error handling with specific exceptions

## Testing

- Write unit tests for new functionality
- Ensure all tests pass before submitting a pull request
- Run tests with pytest
  ```bash
  pytest
  ```

## Documentation

- Update documentation when changing functionality
- Include docstrings for all functions, methods, and classes
- Update the README.md if necessary

## Commit Messages

- Use the present tense ("Add feature" not "Added feature")
- Use the imperative mood ("Move cursor to..." not "Moves cursor to...")
- Limit the first line to 72 characters or less
- Reference issues and pull requests after the first line

## Questions?

If you have any questions or need help, feel free to create an issue with your question or reach out to the maintainers.

Thank you for contributing to HunchBank Auto Email Support!
