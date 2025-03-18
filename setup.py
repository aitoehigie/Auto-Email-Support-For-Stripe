from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name="hunchbank-auto-email-support",
    version="0.1.0",
    author="HunchBank Contributors",
    author_email="your.email@example.com",
    description="Automated email support system for banking and payment inquiries",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/yourusername/hunchbank_auto_email_support",
    packages=find_packages(),
    classifiers=[
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Topic :: Communications :: Email",
        "Topic :: Office/Business :: Financial",
    ],
    python_requires=">=3.8",
    install_requires=[
        "python-dotenv>=0.15.0",
        "python-dateutil>=2.8.1",
        "requests>=2.25.1",
        "stripe>=2.56.0",
        "email-validator>=1.1.2",
        "nltk>=3.6.2",
        "scikit-learn>=0.24.2",
        "prompt-toolkit>=3.0.18",
        "rich>=10.1.0",
        "tqdm>=4.61.0",
        "loguru>=0.5.3",
    ],
    entry_points={
        "console_scripts": [
            "hunchbank=main:main",
        ],
    },
)
