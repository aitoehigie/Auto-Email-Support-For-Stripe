import os
import sqlite3
import time
import threading
from datetime import datetime
import json
from utils.logger import setup_logger

# Thread local storage for database connections
_thread_local = threading.local()

class DatabaseService:
    """
    Service that handles database operations across the application.
    Uses SQLite as the backend database engine.
    Implements connection pooling per thread and automatic retries.
    """
    
    def __init__(self, db_path=None):
        """
        Initialize the database service.
        
        Args:
            db_path (str, optional): Path to the database file. Defaults to 'database/hunchbank.db'.
        """
        self.logger = setup_logger("DatabaseService")
        
        if db_path is None:
            # Use default path in the database directory
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            self.db_path = os.path.join(base_dir, "database", "hunchbank.db")
        else:
            self.db_path = db_path
            
        # Create database directory if it doesn't exist
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        
        # Initialize the database
        self._init_db()
        self.logger.info(f"Database initialized at {self.db_path}")
        
    def _get_connection(self):
        """
        Get a database connection for the current thread.
        
        Returns:
            sqlite3.Connection: A database connection.
        """
        if not hasattr(_thread_local, 'connection') or _thread_local.connection is None:
            # Create a new connection for this thread
            _thread_local.connection = sqlite3.connect(
                self.db_path,
                detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES
            )
            # Enable foreign keys
            _thread_local.connection.execute("PRAGMA foreign_keys = ON")
            # Use Row factory for named column access
            _thread_local.connection.row_factory = sqlite3.Row
            
        return _thread_local.connection
    
    def _init_db(self):
        """
        Initialize the database schema if it doesn't exist.
        """
        # Create database tables with appropriate schema
        self.logger.info("Initializing database schema")
        connection = self._get_connection()
        cursor = connection.cursor()
        
        # Create tables
        cursor.executescript('''
        -- Activity log table (for dashboard)
        CREATE TABLE IF NOT EXISTS system_activity (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            activity TEXT NOT NULL,
            type TEXT NOT NULL,
            source TEXT
        );
        
        -- Email processing table
        CREATE TABLE IF NOT EXISTS email_processing (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email_id TEXT UNIQUE,
            sender TEXT NOT NULL,
            subject TEXT,
            received_at TEXT NOT NULL,
            processed_at TEXT,
            intent TEXT,
            confidence REAL,
            status TEXT NOT NULL,
            auto_processed BOOLEAN NOT NULL DEFAULT 0
        );
        
        -- Review table
        CREATE TABLE IF NOT EXISTS reviews (
            id TEXT PRIMARY KEY,
            email_id TEXT,
            customer_email TEXT NOT NULL,
            intent TEXT,
            confidence REAL,
            risk_level TEXT NOT NULL,
            email_subject TEXT,
            email_body TEXT,
            entities TEXT,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL,
            processed_at TEXT,
            modified_at TEXT,
            FOREIGN KEY (email_id) REFERENCES email_processing(email_id)
        );
        
        -- System metrics table
        CREATE TABLE IF NOT EXISTS system_metrics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            processed_count INTEGER NOT NULL DEFAULT 0,
            auto_processed_count INTEGER NOT NULL DEFAULT 0,
            error_count INTEGER NOT NULL DEFAULT 0,
            pending_reviews_count INTEGER NOT NULL DEFAULT 0
        );
        
        -- Error log table
        CREATE TABLE IF NOT EXISTS error_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            error_type TEXT NOT NULL,
            error_message TEXT NOT NULL,
            source TEXT,
            details TEXT
        );
        
        -- Intent statistics
        CREATE TABLE IF NOT EXISTS intent_stats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            intent TEXT NOT NULL,
            count INTEGER NOT NULL DEFAULT 0,
            auto_processed INTEGER NOT NULL DEFAULT 0,
            human_reviewed INTEGER NOT NULL DEFAULT 0,
            UNIQUE(date, intent)
        );
        ''')
        
        # Create indexes for performance
        cursor.executescript('''
        -- Indexes for fast querying
        CREATE INDEX IF NOT EXISTS idx_system_activity_timestamp ON system_activity(timestamp);
        CREATE INDEX IF NOT EXISTS idx_email_processing_status ON email_processing(status);
        CREATE INDEX IF NOT EXISTS idx_email_processing_intent ON email_processing(intent);
        CREATE INDEX IF NOT EXISTS idx_reviews_status ON reviews(status);
        CREATE INDEX IF NOT EXISTS idx_reviews_risk_level ON reviews(risk_level);
        CREATE INDEX IF NOT EXISTS idx_error_log_error_type ON error_log(error_type);
        CREATE INDEX IF NOT EXISTS idx_intent_stats_date ON intent_stats(date);
        ''')
        
        connection.commit()
        
        # Check if we need to initialize metrics
        cursor.execute("SELECT COUNT(*) FROM system_metrics")
        count = cursor.fetchone()[0]
        if count == 0:
            self.logger.info("Initializing system metrics with default values")
            # Initialize with default values
            timestamp = datetime.now().isoformat()
            
            # Count actual processed emails if possible
            processed_count = 0
            try:
                cursor.execute("SELECT COUNT(*) FROM email_processing WHERE status='processed'")
                row = cursor.fetchone()
                if row:
                    processed_count = row[0]
            except Exception as e:
                self.logger.error(f"Error counting processed emails: {e}")
            
            # Count auto-processed emails
            auto_processed = 0
            try:
                cursor.execute("SELECT COUNT(*) FROM email_processing WHERE auto_processed=1")
                row = cursor.fetchone()
                if row:
                    auto_processed = row[0]
            except Exception as e:
                self.logger.error(f"Error counting auto-processed emails: {e}")
            
            # Count errors
            error_count = 0
            try:
                cursor.execute("SELECT COUNT(*) FROM error_log")
                row = cursor.fetchone()
                if row:
                    error_count = row[0]
            except Exception as e:
                self.logger.error(f"Error counting errors: {e}")
            
            # Count pending reviews
            pending_reviews = 0
            try:
                cursor.execute("SELECT COUNT(*) FROM reviews WHERE status='pending'")
                row = cursor.fetchone()
                if row:
                    pending_reviews = row[0]
            except Exception as e:
                self.logger.error(f"Error counting pending reviews: {e}")
            
            # Insert initial metrics record
            cursor.execute(
                "INSERT INTO system_metrics (timestamp, processed_count, auto_processed_count, error_count, pending_reviews_count) VALUES (?, ?, ?, ?, ?)",
                (timestamp, processed_count, auto_processed, error_count, pending_reviews)
            )
            connection.commit()
            self.logger.info(f"Initialized system metrics: processed={processed_count}, auto={auto_processed}, errors={error_count}, pending={pending_reviews}")
            
        cursor.close()
        
    def close(self):
        """
        Close the database connection for the current thread.
        """
        if hasattr(_thread_local, 'connection') and _thread_local.connection is not None:
            _thread_local.connection.close()
            _thread_local.connection = None
    
    def execute_with_retry(self, query, params=None, max_retries=3, retry_delay=1):
        """
        Execute a database query with automatic retries for transient errors.
        
        Args:
            query (str): SQL query to execute
            params (tuple, optional): Parameters for the query. Defaults to None.
            max_retries (int, optional): Maximum number of retry attempts. Defaults to 3.
            retry_delay (int, optional): Delay between retries in seconds. Defaults to 1.
            
        Returns:
            cursor: SQLite cursor after execution
        """
        for attempt in range(max_retries):
            try:
                connection = self._get_connection()
                cursor = connection.cursor()
                if params:
                    cursor.execute(query, params)
                else:
                    cursor.execute(query)
                return cursor
            except sqlite3.OperationalError as e:
                if "database is locked" in str(e) and attempt < max_retries - 1:
                    self.logger.warning(f"Database locked, retrying ({attempt+1}/{max_retries})...")
                    time.sleep(retry_delay * (2 ** attempt))  # Exponential backoff
                else:
                    self.logger.error(f"Database error: {str(e)}")
                    raise
            except Exception as e:
                self.logger.error(f"Error executing query: {str(e)}")
                raise
    
    def add_activity(self, activity, activity_type="info", source=None):
        """
        Add an activity entry to the system activity log.
        
        Args:
            activity (str): Activity description
            activity_type (str, optional): Type of activity. Defaults to "info".
            source (str, optional): Source of the activity. Defaults to None.
            
        Returns:
            int: ID of the inserted activity
        """
        timestamp = datetime.now().isoformat()
        
        cursor = self.execute_with_retry(
            "INSERT INTO system_activity (timestamp, activity, type, source) VALUES (?, ?, ?, ?)",
            (timestamp, activity, activity_type, source)
        )
        
        self._get_connection().commit()
        return cursor.lastrowid
    
    def get_activities(self, limit=20):
        """
        Get recent activities from the system activity log.
        
        Args:
            limit (int, optional): Maximum number of activities to return. Defaults to 20.
            
        Returns:
            list: List of activity dictionaries
        """
        cursor = self.execute_with_retry(
            "SELECT * FROM system_activity ORDER BY timestamp DESC LIMIT ?",
            (limit,)
        )
        
        results = cursor.fetchall()
        activities = []
        
        for row in results:
            activity = dict(row)
            try:
                # Convert ISO timestamp to datetime object
                activity['timestamp'] = datetime.fromisoformat(activity['timestamp'])
            except (ValueError, TypeError):
                # Keep as string if conversion fails
                pass
            activities.append(activity)
            
        return activities
    
    def log_email_processing(self, email_id, sender, subject, received_at, intent=None, 
                            confidence=None, status="received", auto_processed=False):
        """
        Log an email processing event.
        
        Args:
            email_id (str): Unique ID for the email
            sender (str): Sender email address
            subject (str): Email subject
            received_at (str): ISO timestamp of when the email was received
            intent (str, optional): Classified intent. Defaults to None.
            confidence (float, optional): Confidence score. Defaults to None.
            status (str, optional): Processing status. Defaults to "received".
            auto_processed (bool, optional): Whether the email was auto-processed. Defaults to False.
            
        Returns:
            int: ID of the inserted record
        """
        cursor = self.execute_with_retry(
            """INSERT INTO email_processing 
               (email_id, sender, subject, received_at, intent, confidence, status, auto_processed)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(email_id) DO UPDATE SET
               intent=excluded.intent, confidence=excluded.confidence, 
               status=excluded.status, auto_processed=excluded.auto_processed""",
            (email_id, sender, subject, received_at, intent, confidence, status, auto_processed)
        )
        
        self._get_connection().commit()
        return cursor.lastrowid
    
    def update_email_status(self, email_id, status, processed_at=None, intent=None, confidence=None, auto_processed=None):
        """
        Update the status of an email in the database.
        
        Args:
            email_id (str): Unique ID for the email
            status (str): New status
            processed_at (str, optional): ISO timestamp of when processing completed. Defaults to None.
            intent (str, optional): Updated intent. Defaults to None.
            confidence (float, optional): Updated confidence score. Defaults to None.
            auto_processed (bool, optional): Whether the email was auto-processed. Defaults to None.
            
        Returns:
            bool: True if update successful, False otherwise
        """
        # Use current time if processed_at not provided
        if processed_at is None and status in ["processed", "error", "reviewed"]:
            processed_at = datetime.now().isoformat()
            
        # Build the query dynamically based on provided parameters
        query_parts = ["UPDATE email_processing SET status = ?"]
        params = [status]
        
        if processed_at is not None:
            query_parts.append("processed_at = ?")
            params.append(processed_at)
            
        if intent is not None:
            query_parts.append("intent = ?")
            params.append(intent)
            
        if confidence is not None:
            query_parts.append("confidence = ?")
            params.append(confidence)
            
        if auto_processed is not None:
            query_parts.append("auto_processed = ?")
            params.append(auto_processed)
            
        query_parts.append("WHERE email_id = ?")
        params.append(email_id)
        
        query = " ".join(query_parts)
        
        cursor = self.execute_with_retry(query, tuple(params))
        rows_affected = cursor.rowcount
        
        self._get_connection().commit()
        return rows_affected > 0
    
    def get_email_stats(self, days=7):
        """
        Get email processing statistics for the specified number of days.
        
        Args:
            days (int, optional): Number of days to retrieve stats for. Defaults to 7.
            
        Returns:
            dict: Statistics by day and status
        """
        cursor = self.execute_with_retry(
            """SELECT 
                 DATE(received_at) as date,
                 status,
                 COUNT(*) as count,
                 SUM(CASE WHEN auto_processed = 1 THEN 1 ELSE 0 END) as auto_count
               FROM email_processing
               WHERE received_at >= DATE('now', ?) 
               GROUP BY DATE(received_at), status
               ORDER BY DATE(received_at) DESC""",
            (f"-{days} days",)
        )
        
        results = cursor.fetchall()
        stats = {}
        
        for row in results:
            date = row["date"]
            if date not in stats:
                stats[date] = {
                    "total": 0,
                    "processed": 0,
                    "pending": 0,
                    "error": 0,
                    "auto_processed": 0
                }
                
            stats[date]["total"] += row["count"]
            if row["status"] == "processed":
                stats[date]["processed"] += row["count"]
            elif row["status"] in ["received", "pending"]:
                stats[date]["pending"] += row["count"]
            elif row["status"] == "error":
                stats[date]["error"] += row["count"]
                
            stats[date]["auto_processed"] += row["auto_count"]
            
        return stats
    
    def add_review(self, review_id, email_id, customer_email, intent, confidence, 
                  risk_level, email_subject, email_body, entities, status, created_at):
        """
        Add a review to the database.
        
        Args:
            review_id (str): Unique review ID
            email_id (str): ID of the corresponding email
            customer_email (str): Customer's email address
            intent (str): Classified intent
            confidence (float): Confidence score
            risk_level (str): Risk level assessment
            email_subject (str): Email subject
            email_body (str): Email body content
            entities (dict): Extracted entities as dictionary
            status (str): Review status
            created_at (str): ISO timestamp of when the review was created
            
        Returns:
            bool: True if review added successfully
        """
        # Convert entities dictionary to JSON string
        entities_json = json.dumps(entities) if entities else None
        
        cursor = self.execute_with_retry(
            """INSERT INTO reviews
               (id, email_id, customer_email, intent, confidence, risk_level,
                email_subject, email_body, entities, status, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (review_id, email_id, customer_email, intent, confidence, risk_level,
             email_subject, email_body, entities_json, status, created_at)
        )
        
        self._get_connection().commit()
        return cursor.rowcount > 0
    
    def update_review(self, review_id, status, processed_at=None, modified_at=None, new_intent=None):
        """
        Update a review in the database.
        
        Args:
            review_id (str): Unique review ID
            status (str): New status
            processed_at (str, optional): ISO timestamp of when processing completed. Defaults to None.
            modified_at (str, optional): ISO timestamp of when the review was modified. Defaults to None.
            new_intent (str, optional): Updated intent. Defaults to None.
            
        Returns:
            bool: True if update successful
        """
        # Build the query dynamically based on provided parameters
        query_parts = ["UPDATE reviews SET status = ?"]
        params = [status]
        
        if processed_at is not None:
            query_parts.append("processed_at = ?")
            params.append(processed_at)
            
        if modified_at is not None:
            query_parts.append("modified_at = ?")
            params.append(modified_at)
            
        if new_intent is not None:
            query_parts.append("intent = ?")
            params.append(new_intent)
            
        query_parts.append("WHERE id = ?")
        params.append(review_id)
        
        query = " ".join(query_parts)
        
        cursor = self.execute_with_retry(query, tuple(params))
        rows_affected = cursor.rowcount
        
        self._get_connection().commit()
        return rows_affected > 0
    
    def get_pending_reviews(self):
        """
        Get all pending reviews from the database.
        
        Returns:
            list: List of pending review dictionaries
        """
        cursor = self.execute_with_retry(
            "SELECT * FROM reviews WHERE status = 'pending' ORDER BY created_at DESC"
        )
        
        results = cursor.fetchall()
        reviews = []
        
        for row in results:
            review = dict(row)
            # Convert stored JSON string back to dictionary
            if review['entities']:
                review['entities'] = json.loads(review['entities'])
            else:
                review['entities'] = {}
                
            # Reconstruct the email dict to match existing code structure
            review['email'] = {
                'from': review['customer_email'],
                'subject': review['email_subject'],
                'body': review['email_body'],
                'id': review['email_id']
            }
            
            reviews.append(review)
            
        return reviews
    
    def get_review_by_id(self, review_id):
        """
        Get a review by its ID.
        
        Args:
            review_id (str): Unique review ID
            
        Returns:
            dict: Review data or None if not found
        """
        cursor = self.execute_with_retry(
            "SELECT * FROM reviews WHERE id = ?",
            (review_id,)
        )
        
        row = cursor.fetchone()
        if not row:
            return None
            
        review = dict(row)
        # Convert stored JSON string back to dictionary
        if review['entities']:
            review['entities'] = json.loads(review['entities'])
        else:
            review['entities'] = {}
            
        # Reconstruct the email dict to match existing code structure
        review['email'] = {
            'from': review['customer_email'],
            'subject': review['email_subject'],
            'body': review['email_body'],
            'id': review['email_id']
        }
        
        return review
    
    def get_review_stats(self):
        """
        Get statistics about reviews.
        
        Returns:
            dict: Statistics about reviews
        """
        # Count by status
        cursor = self.execute_with_retry(
            """SELECT 
                 status, 
                 COUNT(*) as count 
               FROM reviews 
               GROUP BY status"""
        )
        
        status_counts = {}
        for row in cursor.fetchall():
            status_counts[row['status']] = row['count']
            
        # Count by risk level
        cursor = self.execute_with_retry(
            """SELECT 
                 risk_level, 
                 COUNT(*) as count 
               FROM reviews 
               GROUP BY risk_level"""
        )
        
        risk_counts = {}
        for row in cursor.fetchall():
            risk_counts[row['risk_level']] = row['count']
            
        # Count by intent (for intent distribution)
        cursor = self.execute_with_retry(
            """SELECT 
                 intent, 
                 COUNT(*) as count 
               FROM reviews 
               GROUP BY intent"""
        )
        
        intent_counts = {}
        for row in cursor.fetchall():
            intent_counts[row['intent']] = row['count']
            
        # Count today's reviews
        cursor = self.execute_with_retry(
            "SELECT COUNT(*) as count FROM reviews WHERE created_at >= DATE('now')"
        )
        
        today_count = cursor.fetchone()['count']
        
        return {
            "total_pending": status_counts.get("pending", 0),
            "total_processed": sum(count for status, count in status_counts.items() if status != "pending"),
            "accepted": status_counts.get("accepted", 0),
            "rejected": status_counts.get("rejected", 0),
            "high_risk": risk_counts.get("high", 0),
            "medium_risk": risk_counts.get("medium", 0),
            "low_risk": risk_counts.get("low", 0),
            "today_count": today_count,
            "intent_distribution": intent_counts
        }
    
    def update_metrics(self, processed_count, auto_processed_count, error_count, pending_reviews_count):
        """
        Update system metrics in the database.
        
        Args:
            processed_count (int): Count of processed emails
            auto_processed_count (int): Count of auto-processed emails
            error_count (int): Count of errors
            pending_reviews_count (int): Count of pending reviews
            
        Returns:
            int: ID of the inserted record
        """
        timestamp = datetime.now().isoformat()
        
        cursor = self.execute_with_retry(
            """INSERT INTO system_metrics 
               (timestamp, processed_count, auto_processed_count, error_count, pending_reviews_count)
               VALUES (?, ?, ?, ?, ?)""",
            (timestamp, processed_count, auto_processed_count, error_count, pending_reviews_count)
        )
        
        self._get_connection().commit()
        
        # After updating metrics, try to update the CLI dashboard directly
        # Don't use try/except since that might mask database commit errors
        try:
            # Import cli reference from main to trigger dashboard update
            from main import cli
            if cli is not None:
                print(f"Database updated metrics. Notifying CLI: processed={processed_count}, auto={auto_processed_count}")
                
                # Try direct update of stats cards first (most reliable)
                try:
                    # Update processed count property
                    cli.processed_count = processed_count
                    cli.auto_processed = auto_processed_count
                    cli.error_count = error_count
                    
                    # Direct UI update - find and update the dashboard cards
                    processed_card = cli.query_one("#processed-card", Container)
                    auto_card = cli.query_one("#auto-card", Container)
                    pending_card = cli.query_one("#pending-card", Container)
                    
                    # Update each card's value label directly
                    if processed_card:
                        value_label = processed_card.query("Label.stats-value")
                        if value_label and len(value_label) > 0:
                            value_label[0].update(str(processed_count))
                            print(f"Database directly updated processed card to {processed_count}")
                            
                    if auto_card:
                        value_label = auto_card.query("Label.stats-value")
                        if value_label and len(value_label) > 0:
                            value_label[0].update(str(auto_processed_count))
                            
                    if pending_card:
                        value_label = pending_card.query("Label.stats-value")
                        if value_label and len(value_label) > 0:
                            value_label[0].update(str(pending_reviews_count))
                except Exception as e:
                    print(f"Error during direct UI update: {str(e)}")
                
                # Update all UI components comprehensively
                try:
                    # First update dashboard completely
                    if hasattr(cli, 'update_dashboard'):
                        # Use a separate thread to avoid blocking
                        import threading
                        threading.Thread(target=lambda: cli.call_later(cli.update_dashboard), daemon=True).start()
                    
                    # Then update analytics components
                    if hasattr(cli, 'refresh_analytics_safely'):
                        threading.Thread(target=lambda: cli.call_later(cli.refresh_analytics_safely), daemon=True).start()
                    
                    # Also update specific analytics tables
                    if hasattr(cli, 'update_intent_stats'):
                        threading.Thread(target=lambda: cli.call_later(cli.update_intent_stats), daemon=True).start()
                    
                    if hasattr(cli, 'update_error_stats'):
                        threading.Thread(target=lambda: cli.call_later(cli.update_error_stats), daemon=True).start()
                    
                    # Also use the action_refresh method as backup
                    if hasattr(cli, 'action_refresh'):
                        threading.Thread(target=lambda: cli.call_later(cli.action_refresh), daemon=True).start()
                except Exception as refresh_e:
                    print(f"Error scheduling UI updates: {refresh_e}")
                    
                # If all else fails, force the dashboard to check for changes on next poll
                if hasattr(cli, 'last_db_update_time'):
                    cli.last_db_update_time = 0  # Reset to force check
                if hasattr(cli, 'last_analytics_refresh'):
                    cli.last_analytics_refresh = 0  # Reset to force analytics check
        except ImportError:
            # CLI not available, which is fine
            pass
        except Exception as e:
            # Log but don't re-raise so database operation completes
            print(f"Warning: Error attempting to refresh CLI dashboard: {str(e)}")
            
        return cursor.lastrowid
    
    def get_latest_metrics(self):
        """
        Get the latest system metrics.
        
        Returns:
            dict: Latest metrics or default values if none found
        """
        cursor = self.execute_with_retry(
            "SELECT * FROM system_metrics ORDER BY timestamp DESC LIMIT 1"
        )
        
        row = cursor.fetchone()
        if not row:
            # No metrics found - let's create initial metrics
            timestamp = datetime.now().isoformat()
            
            # Count actual processed emails if possible
            processed_count = 0
            try:
                cursor = self.execute_with_retry("SELECT COUNT(*) FROM email_processing WHERE status='processed'")
                row = cursor.fetchone()
                if row:
                    processed_count = row[0]
            except Exception as e:
                self.logger.error(f"Error counting processed emails: {e}")
            
            # Count auto-processed emails
            auto_processed = 0
            try:
                cursor = self.execute_with_retry("SELECT COUNT(*) FROM email_processing WHERE auto_processed=1")
                row = cursor.fetchone()
                if row:
                    auto_processed = row[0]
            except Exception as e:
                self.logger.error(f"Error counting auto-processed emails: {e}")
            
            # Count errors
            error_count = 0
            try:
                cursor = self.execute_with_retry("SELECT COUNT(*) FROM error_log")
                row = cursor.fetchone()
                if row:
                    error_count = row[0]
            except Exception as e:
                self.logger.error(f"Error counting errors: {e}")
            
            # Count pending reviews
            pending_reviews = 0
            try:
                cursor = self.execute_with_retry("SELECT COUNT(*) FROM reviews WHERE status='pending'")
                row = cursor.fetchone()
                if row:
                    pending_reviews = row[0]
            except Exception as e:
                self.logger.error(f"Error counting pending reviews: {e}")
            
            # Insert initial metrics record
            cursor = self.execute_with_retry(
                "INSERT INTO system_metrics (timestamp, processed_count, auto_processed_count, error_count, pending_reviews_count) VALUES (?, ?, ?, ?, ?)",
                (timestamp, processed_count, auto_processed, error_count, pending_reviews)
            )
            self._get_connection().commit()
            self.logger.info(f"Created first-time metrics: processed={processed_count}, auto={auto_processed}, errors={error_count}, pending={pending_reviews}")
            
            # Now fetch the newly created record
            cursor = self.execute_with_retry(
                "SELECT * FROM system_metrics ORDER BY timestamp DESC LIMIT 1"
            )
            row = cursor.fetchone()
            
            # If still no row (though unlikely), return defaults
            if not row:
                return {
                    "processed_count": processed_count,
                    "auto_processed_count": auto_processed,
                    "error_count": error_count,
                    "pending_reviews_count": pending_reviews,
                    "timestamp": timestamp
                }
            
        return dict(row)
    
    def log_error(self, error_type, error_message, source=None, details=None):
        """
        Log an error in the database.
        
        Args:
            error_type (str): Type of error
            error_message (str): Error message
            source (str, optional): Source of the error. Defaults to None.
            details (str, optional): Additional error details. Defaults to None.
            
        Returns:
            int: ID of the inserted record
        """
        timestamp = datetime.now().isoformat()
        
        cursor = self.execute_with_retry(
            """INSERT INTO error_log 
               (timestamp, error_type, error_message, source, details)
               VALUES (?, ?, ?, ?, ?)""",
            (timestamp, error_type, error_message, source, details)
        )
        
        self._get_connection().commit()
        return cursor.lastrowid
    
    def get_error_stats(self, days=7):
        """
        Get error statistics for the specified number of days.
        
        Args:
            days (int, optional): Number of days to retrieve stats for. Defaults to 7.
            
        Returns:
            dict: Statistics by error type
        """
        cursor = self.execute_with_retry(
            """SELECT 
                 error_type, 
                 COUNT(*) as count,
                 MAX(timestamp) as last_occurrence
               FROM error_log
               WHERE timestamp >= DATETIME('now', ?)
               GROUP BY error_type
               ORDER BY count DESC""",
            (f"-{days} days",)
        )
        
        results = cursor.fetchall()
        stats = {}
        
        for row in results:
            error_type = row["error_type"]
            stats[error_type] = {
                "count": row["count"],
                "last_occurrence": row["last_occurrence"],
                # Determine trend by counting in last day vs previous days
                "trend": self._calculate_error_trend(error_type, days)
            }
            
        return stats
    
    def _calculate_error_trend(self, error_type, days):
        """
        Calculate the trend for an error type.
        
        Args:
            error_type (str): Type of error
            days (int): Number of days to analyze
            
        Returns:
            str: Trend ("increasing", "decreasing", or "stable")
        """
        # Count errors in the most recent day
        cursor = self.execute_with_retry(
            """SELECT COUNT(*) as count
               FROM error_log
               WHERE error_type = ?
               AND timestamp >= DATETIME('now', '-1 day')""",
            (error_type,)
        )
        
        recent_count = cursor.fetchone()["count"]
        
        # Count errors in the previous period
        cursor = self.execute_with_retry(
            """SELECT COUNT(*) as count
               FROM error_log
               WHERE error_type = ?
               AND timestamp >= DATETIME('now', ?)
               AND timestamp < DATETIME('now', '-1 day')""",
            (error_type, f"-{days} days")
        )
        
        previous_count = cursor.fetchone()["count"]
        
        # Calculate daily average for previous period (excluding most recent day)
        daily_avg_previous = previous_count / max(1, days - 1)
        
        # Determine trend
        if recent_count > daily_avg_previous * 1.5:
            return "increasing"
        elif recent_count < daily_avg_previous * 0.5:
            return "decreasing"
        else:
            return "stable"
    
    def update_intent_stats(self, date, intent, count=1, auto_processed=0, human_reviewed=0):
        """
        Update intent statistics for a given date.
        
        Args:
            date (str): Date in YYYY-MM-DD format
            intent (str): Intent type
            count (int, optional): Number to add to count. Defaults to 1.
            auto_processed (int, optional): Number to add to auto_processed. Defaults to 0.
            human_reviewed (int, optional): Number to add to human_reviewed. Defaults to 0.
            
        Returns:
            bool: True if update successful
        """
        cursor = self.execute_with_retry(
            """INSERT INTO intent_stats 
               (date, intent, count, auto_processed, human_reviewed)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(date, intent) DO UPDATE SET
               count = count + excluded.count,
               auto_processed = auto_processed + excluded.auto_processed,
               human_reviewed = human_reviewed + excluded.human_reviewed""",
            (date, intent, count, auto_processed, human_reviewed)
        )
        
        self._get_connection().commit()
        return cursor.rowcount > 0
    
    def get_intent_stats(self, days=7):
        """
        Get intent statistics for the specified number of days.
        
        Args:
            days (int, optional): Number of days to retrieve stats for. Defaults to 7.
            
        Returns:
            dict: Statistics by intent type
        """
        cursor = self.execute_with_retry(
            """SELECT 
                 intent, 
                 SUM(count) as total_count,
                 SUM(auto_processed) as auto_count,
                 SUM(human_reviewed) as human_count
               FROM intent_stats
               WHERE date >= DATE('now', ?)
               GROUP BY intent
               ORDER BY total_count DESC""",
            (f"-{days} days",)
        )
        
        results = cursor.fetchall()
        stats = {}
        
        for row in results:
            intent = row["intent"]
            stats[intent] = {
                "count": row["total_count"],
                "auto": row["auto_count"],
                "human": row["human_count"]
            }
            
        return stats

# Initialize the database service as a singleton
db = DatabaseService()

def ensure_metrics_exist():
    """
    Ensure that at least one metrics record exists in the database.
    This is called during startup to prevent empty dashboard.
    """
    global db
    if not db:
        db = DatabaseService()
    
    # Check if any metrics exist
    cursor = db.execute_with_retry("SELECT COUNT(*) FROM system_metrics")
    count = cursor.fetchone()[0]
    
    if count == 0:
        # Initialize with default values using the existing method
        metrics = db.get_latest_metrics()
        print(f"Initialized default metrics: {metrics}")
    
    return db

def get_db():
    """
    Get the database service instance.
    
    Returns:
        DatabaseService: The database service instance
    """
    global db
    if not db:
        db = DatabaseService()
    return db