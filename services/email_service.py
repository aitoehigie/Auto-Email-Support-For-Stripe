from imapclient import IMAPClient
from email.parser import BytesParser
from email.policy import default
from email.header import decode_header
import re
from config.config import Config
from utils.logger import setup_logger
import time

class EmailService:
    def __init__(self):
        self.logger = setup_logger("EmailService", console_output=False)
        self.server = None
        self.connected = False
        self.max_retries = Config.MAX_RETRIES
        self.retry_delay = Config.RETRY_DELAY
        self.batch_size = Config.EMAIL_BATCH_SIZE

    def connect(self):
        """Connect to the email server with retry logic"""
        if self.connected and self.server:
            try:
                # Check if connection is still alive
                self.server.noop()
                return True
            except Exception:
                self.logger.info("Connection lost, reconnecting...")
                self.disconnect()
        
        for attempt in range(self.max_retries):
            try:
                self.server = IMAPClient(Config.EMAIL_SERVER, ssl=True)
                self.server.login(Config.EMAIL_USER, Config.EMAIL_PASS)
                self.server.select_folder("INBOX")
                self.connected = True
                self.logger.info("Connected to email server and selected INBOX")
                return True
            except Exception as e:
                self.logger.error(f"Email connection attempt {attempt+1} failed: {str(e)}")
                if attempt + 1 == self.max_retries:
                    self.logger.error("All connection attempts failed")
                    raise ConnectionError("Could not connect to email server") from e
                time.sleep(self.retry_delay)

    def fetch_emails(self):
        """Fetch unread emails with error handling and reconnection logic"""
        if not self.connected:
            self.connect()
            
        try:
            self.logger.info("Searching for unread emails...")
            messages = self.server.search(["UNSEEN"])
            self.logger.info(f"Found {len(messages)} unread emails")
            
            if not messages:
                return []
            
            # Process in batches to avoid overload
            emails = []
            for i in range(0, len(messages), self.batch_size):
                batch = messages[i:i + self.batch_size]
                self.logger.info(f"Fetching batch {i // self.batch_size + 1}: {len(batch)} emails")
                try:
                    fetched = self.server.fetch(batch, ["RFC822", "FLAGS"])
                    for uid, message_data in fetched.items():
                        try:
                            raw_email = message_data[b"RFC822"]
                            email = BytesParser(policy=default).parsebytes(raw_email)
                            
                            # Properly decode the "from" field
                            from_address = self._decode_email_field(email["from"])
                            subject = self._decode_email_field(email["subject"] or "")
                            
                            # Extract email address from "From" field
                            email_regex = r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+"
                            from_matches = re.findall(email_regex, from_address)
                            from_email = from_matches[0] if from_matches else from_address
                            
                            # Get email body
                            body = ""
                            if email.is_multipart():
                                for part in email.walk():
                                    content_type = part.get_content_type()
                                    content_disposition = str(part.get("Content-Disposition"))
                                    
                                    if content_type == "text/plain" and "attachment" not in content_disposition:
                                        try:
                                            body = part.get_content()
                                            break
                                        except Exception as e:
                                            self.logger.error(f"Failed to get plain text content: {e}")
                            else:
                                try:
                                    body = email.get_body(preferencelist=("plain",)).get_content()
                                except Exception as e:
                                    self.logger.error(f"Failed to get email body: {e}")
                                    body = ""
                            
                            # Extract message-id for proper email threading
                            message_id = email.get('Message-ID', '')
                            
                            emails.append({
                                "uid": uid,
                                "from": from_email,
                                "subject": subject,
                                "body": body,
                                "message_id": message_id
                            })
                            
                        except Exception as e:
                            self.logger.error(f"Failed to process email UID {uid}: {str(e)}")
                            
                except Exception as e:
                    self.logger.error(f"Failed to fetch batch: {str(e)}")
                    # Try to reconnect before next batch
                    self.connect()
                    
            return emails
                
        except Exception as e:
            self.logger.error(f"Email fetch failed: {str(e)}", exc_info=True)
            self.connected = False
            return []

    def _decode_email_field(self, field):
        """Properly decode email header fields"""
        if field is None:
            return ""
            
        decoded_parts = []
        try:
            for part, encoding in decode_header(str(field)):
                if isinstance(part, bytes):
                    try:
                        if encoding:
                            decoded_parts.append(part.decode(encoding))
                        else:
                            decoded_parts.append(part.decode('utf-8', errors='replace'))
                    except Exception:
                        decoded_parts.append(part.decode('utf-8', errors='replace'))
                else:
                    decoded_parts.append(str(part))
            return ''.join(decoded_parts)
        except Exception as e:
            self.logger.error(f"Failed to decode email field: {str(e)}")
            return str(field)

    def mark_as_read(self, uid):
        """Mark an email as read with retry logic"""
        for attempt in range(self.max_retries):
            try:
                self.server.add_flags([uid], ["\\Seen"])
                self.logger.info(f"Marked email {uid} as read")
                return True
            except Exception as e:
                self.logger.error(f"Failed to mark email {uid} as read (attempt {attempt+1}): {str(e)}")
                if attempt + 1 == self.max_retries:
                    return False
                # Try to reconnect before retrying
                self.connect()
                time.sleep(self.retry_delay)
                
        return False
            
    def disconnect(self):
        """Safely disconnect from the email server"""
        if self.server:
            try:
                self.server.logout()
                self.logger.info("Disconnected from email server")
            except Exception as e:
                self.logger.error(f"Email disconnect failed: {str(e)}")
            finally:
                self.server = None
                self.connected = False