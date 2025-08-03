import psycopg2
import psycopg2.extras
import json
import os
from datetime import datetime
from typing import Optional, List, Dict, Any
from urllib.parse import urlparse

class DatabaseManager:
    def __init__(self, db_url: str = None):
        """Initialize with DATABASE_URL from Railway or connection string"""
        self.db_url = db_url or os.environ.get('DATABASE_URL')
        if not self.db_url:
            raise ValueError("DATABASE_URL environment variable is required for Railway deployment")
        
        # Parse DATABASE_URL
        self.db_config = self._parse_db_url(self.db_url)
        self.init_database()

    def _parse_db_url(self, db_url: str) -> dict:
        """Parse DATABASE_URL into connection parameters"""
        parsed = urlparse(db_url)
        return {
            'host': parsed.hostname,
            'port': parsed.port or 5432,
            'database': parsed.path[1:],  # Remove leading slash
            'user': parsed.username,
            'password': parsed.password,
        }

    def _get_connection(self):
        """Get database connection"""
        return psycopg2.connect(**self.db_config)

    def init_database(self):
        """Initialize the database with required tables for skincare questionnaire"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            # Users table to track questionnaire progress
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    user_id BIGINT PRIMARY KEY,
                    username TEXT,
                    first_name TEXT,
                    last_name TEXT,
                    current_question_index INTEGER DEFAULT 0,
                    waiting_for_followup BOOLEAN DEFAULT FALSE,
                    followup_question_index INTEGER NULL,
                    questionnaire_completed BOOLEAN DEFAULT FALSE,
                    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    completed_at TIMESTAMP NULL
                )
            ''')
            
            # Enhanced answers table for skincare data
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS answers (
                    id SERIAL PRIMARY KEY,
                    user_id BIGINT,
                    question_index INTEGER,
                    question_text TEXT,
                    answer_text TEXT,
                    answer_type TEXT DEFAULT 'text',
                    file_id TEXT NULL,
                    followup_text TEXT NULL,
                    answered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users (user_id)
                )
            ''')
            
            # Photos table for better photo management
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS photos (
                    id SERIAL PRIMARY KEY,
                    user_id BIGINT,
                    question_index INTEGER,
                    file_id TEXT,
                    file_unique_id TEXT,
                    file_size INTEGER,
                    photo_description TEXT,
                    uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users (user_id)
                )
            ''')
            
            # User sessions for complex state management
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS user_sessions (
                    user_id BIGINT PRIMARY KEY,
                    session_data TEXT,
                    last_activity TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users (user_id)
                )
            ''')

            cursor.execute('''
                CREATE TABLE IF NOT EXISTS user_messages (
                    user_id BIGINT,
                    message_id INTEGER, 
                    message_type TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users (user_id)
                )
            ''')
            
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            cursor.close()
            conn.close()

    def get_user(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Get user information and progress"""
        conn = self._get_connection()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        try:
            cursor.execute('''
                SELECT * FROM users WHERE user_id = %s
            ''', (user_id,))
            
            user = cursor.fetchone()
            return dict(user) if user else None
        finally:
            cursor.close()
            conn.close()

    def create_or_update_user(self, user_id: int, username: str = None, 
                            first_name: str = None, last_name: str = None) -> None:
        """Create new user or update existing user info"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            # PostgreSQL UPSERT using ON CONFLICT
            cursor.execute('''
                INSERT INTO users (user_id, username, first_name, last_name, current_question_index, 
                                 waiting_for_followup, followup_question_index, questionnaire_completed)
                VALUES (%s, %s, %s, %s, 0, FALSE, NULL, FALSE)
                ON CONFLICT (user_id) DO UPDATE SET
                    username = EXCLUDED.username,
                    first_name = EXCLUDED.first_name,
                    last_name = EXCLUDED.last_name
            ''', (user_id, username, first_name, last_name))
            
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            cursor.close()
            conn.close()

    def save_answer(self, user_id: int, question_index: int, 
                   question_text: str, answer_text: str, answer_type: str = 'text',
                   file_id: str = None, followup_text: str = None) -> None:
        """Save user's answer to a question"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            # Save the answer
            cursor.execute('''
                INSERT INTO answers (user_id, question_index, question_text, answer_text, 
                                   answer_type, file_id, followup_text)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            ''', (user_id, question_index, question_text, answer_text, answer_type, file_id, followup_text))
            
            # Update user's current question index only if not waiting for followup
            cursor.execute('''
                UPDATE users 
                SET current_question_index = %s 
                WHERE user_id = %s AND waiting_for_followup = FALSE
            ''', (question_index + 1, user_id))
            
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            cursor.close()
            conn.close()

    def save_photo(self, user_id: int, question_index: int, question_text: str,
                  file_id: str, file_unique_id: str = None, file_size: int = None,
                  photo_description: str = None) -> None:
        """Save photo upload"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            # Save to photos table
            cursor.execute('''
                INSERT INTO photos (user_id, question_index, file_id, file_unique_id, 
                                  file_size, photo_description)
                VALUES (%s, %s, %s, %s, %s, %s)
            ''', (user_id, question_index, file_id, file_unique_id, file_size, photo_description))
            
            # Save to answers table
            cursor.execute('''
                INSERT INTO answers (user_id, question_index, question_text, answer_text, 
                                   answer_type, file_id)
                VALUES (%s, %s, %s, %s, 'photo', %s)
            ''', (user_id, question_index, question_text, "Fotografie nahrána", file_id))
            
            # Update user's progress
            cursor.execute('''
                UPDATE users 
                SET current_question_index = %s 
                WHERE user_id = %s
            ''', (question_index + 1, user_id))
            
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            cursor.close()
            conn.close()

    def set_waiting_for_followup(self, user_id: int, question_index: int) -> None:
        """Set user as waiting for followup answer"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute('''
                UPDATE users 
                SET waiting_for_followup = TRUE, followup_question_index = %s
                WHERE user_id = %s
            ''', (question_index, user_id))
            
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            cursor.close()
            conn.close()

    def save_followup_answer(self, user_id: int, question_index: int, followup_text: str) -> None:
        """Save followup answer and clear waiting state"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            # First, find the most recent answer ID for this user and question
            cursor.execute('''
                SELECT id FROM answers 
                WHERE user_id = %s AND question_index = %s
                ORDER BY answered_at DESC
                LIMIT 1
            ''', (user_id, question_index))
            
            result = cursor.fetchone()
            if result:
                answer_id = result[0]
                
                # Update the specific answer with followup text
                cursor.execute('''
                    UPDATE answers 
                    SET followup_text = %s
                    WHERE id = %s
                ''', (followup_text, answer_id))
            
            # Clear waiting state and advance to next question
            cursor.execute('''
                UPDATE users 
                SET waiting_for_followup = FALSE, 
                    followup_question_index = NULL
                WHERE user_id = %s
            ''', (user_id,))
            
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            cursor.close()
            conn.close()

    def clear_followup_state(self, user_id: int, question_index: int) -> None:
        """Clear followup waiting state without additional text"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute('''
                UPDATE users 
                SET waiting_for_followup = FALSE, 
                    followup_question_index = NULL
                WHERE user_id = %s
            ''', (user_id,))
            
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            cursor.close()
            conn.close()

    def mark_questionnaire_completed(self, user_id: int) -> None:
        """Mark questionnaire as completed for user"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute('''
                UPDATE users 
                SET questionnaire_completed = TRUE, 
                    completed_at = CURRENT_TIMESTAMP,
                    waiting_for_followup = FALSE,
                    followup_question_index = NULL
                WHERE user_id = %s
            ''', (user_id,))
            
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            cursor.close()
            conn.close()

    def get_user_answers(self, user_id: int) -> List[Dict[str, Any]]:
        """Get all answers for a specific user including photos"""
        conn = self._get_connection()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        try:
            cursor.execute('''
                SELECT * FROM answers 
                WHERE user_id = %s 
                ORDER BY question_index, answered_at
            ''', (user_id,))
            
            answers = cursor.fetchall()
            return [dict(answer) for answer in answers]
        finally:
            cursor.close()
            conn.close()

    def get_user_photos(self, user_id: int) -> List[Dict[str, Any]]:
        """Get all photos for a specific user"""
        conn = self._get_connection()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        try:
            cursor.execute('''
                SELECT * FROM photos 
                WHERE user_id = %s 
                ORDER BY question_index, uploaded_at
            ''', (user_id,))
            
            photos = cursor.fetchall()
            return [dict(photo) for photo in photos]
        finally:
            cursor.close()
            conn.close()

    def reset_user_progress(self, user_id: int) -> None:
        """Reset user's questionnaire progress"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            # Delete existing answers and photos
            cursor.execute('DELETE FROM answers WHERE user_id = %s', (user_id,))
            cursor.execute('DELETE FROM photos WHERE user_id = %s', (user_id,))
            
            # Reset user progress
            cursor.execute('''
                UPDATE users 
                SET current_question_index = 0, 
                    waiting_for_followup = FALSE,
                    followup_question_index = NULL,
                    questionnaire_completed = FALSE, 
                    completed_at = NULL
                WHERE user_id = %s
            ''', (user_id,))
            
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            cursor.close()
            conn.close()

    def get_statistics(self) -> Dict[str, Any]:
        """Get comprehensive statistics about the skincare questionnaire"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            # Total users
            cursor.execute('SELECT COUNT(*) FROM users')
            total_users = cursor.fetchone()[0]
            
            # Completed questionnaires
            cursor.execute('SELECT COUNT(*) FROM users WHERE questionnaire_completed = TRUE')
            completed_users = cursor.fetchone()[0]
            
            # Active users (started but not completed)
            cursor.execute('SELECT COUNT(*) FROM users WHERE questionnaire_completed = FALSE AND current_question_index > 0')
            active_users = cursor.fetchone()[0]
            
            # Photo uploads count (excluding skipped)
            cursor.execute('SELECT COUNT(*) FROM photos')
            total_photos = cursor.fetchone()[0]
            
            # Skipped photos count
            cursor.execute('''
                SELECT COUNT(*) FROM answers 
                WHERE answer_type = 'photo' AND answer_text = 'None'
            ''')
            skipped_photos = cursor.fetchone()[0]
            
            # Skipped follow-ups count
            cursor.execute('''
                SELECT COUNT(*) FROM answers 
                WHERE followup_text = 'None'
            ''')
            skipped_followups = cursor.fetchone()[0]
            
            # Skipped text answers count
            cursor.execute('''
                SELECT COUNT(*) FROM answers 
                WHERE answer_type = 'text' AND answer_text = 'None'
            ''')
            skipped_text = cursor.fetchone()[0]
            
            # Average age (from scale question, excluding None values)
            cursor.execute('''
                SELECT AVG(answer_text::INTEGER) 
                FROM answers 
                WHERE question_index = 0 
                AND answer_text != 'None' 
                AND answer_text != '' 
                AND answer_text ~ '^[0-9]+$'
                AND LENGTH(answer_text) <= 3
            ''')
            avg_age_result = cursor.fetchone()[0]
            avg_age = float(avg_age_result) if avg_age_result else 0
            
            # Smokers count (excluding None/skipped answers)
            cursor.execute('''
                SELECT COUNT(*) 
                FROM answers 
                WHERE question_index = 1 AND answer_text = 'Ano'
            ''')
            smokers_count = cursor.fetchone()[0]
            
            return {
                'total_users': total_users,
                'completed_users': completed_users,
                'active_users': active_users,
                'completion_rate': completed_users / total_users if total_users > 0 else 0,
                'total_photos': total_photos,
                'skipped_photos': skipped_photos,
                'skipped_followups': skipped_followups,
                'skipped_text': skipped_text,
                'average_age': round(avg_age, 1),
                'smokers_count': smokers_count
            }
        finally:
            cursor.close()
            conn.close()

    def export_consultation_data(self, user_id: int) -> Dict[str, Any]:
        """Export complete consultation data for a user"""
        conn = self._get_connection()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        try:
            # Get user info
            cursor.execute('SELECT * FROM users WHERE user_id = %s', (user_id,))
            user_info = dict(cursor.fetchone() or {})
            
            # Get all answers
            cursor.execute('''
                SELECT question_index, question_text, answer_text, answer_type, 
                       file_id, followup_text, answered_at
                FROM answers 
                WHERE user_id = %s 
                ORDER BY question_index, answered_at
            ''', (user_id,))
            answers = [dict(row) for row in cursor.fetchall()]
            
            # Get photos
            cursor.execute('''
                SELECT question_index, file_id, file_unique_id, file_size, uploaded_at
                FROM photos 
                WHERE user_id = %s 
                ORDER BY question_index, uploaded_at
            ''', (user_id,))
            photos = [dict(row) for row in cursor.fetchall()]
            
            return {
                'user_info': user_info,
                'answers': answers,
                'photos': photos,
                'export_timestamp': datetime.now().isoformat()
            }
        finally:
            cursor.close()
            conn.close()
    
    # USER MESSAGES TRACKING
    def save_user_message(self, user_id: int, message_id: int, message_type: str = 'question'):
        """Save message ID for later invalidation"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute('''
                INSERT INTO user_messages (user_id, message_id, message_type)
                VALUES (%s, %s, %s)
                ON CONFLICT (user_id) DO UPDATE SET
                    message_id = EXCLUDED.message_id,
                    message_type = EXCLUDED.message_type,
                    created_at = CURRENT_TIMESTAMP
            ''', (user_id, message_id, message_type))
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            cursor.close()
            conn.close()

    def get_user_last_message(self, user_id: int, message_type: str = 'question'):
        """Get last message ID for user"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute('''
                SELECT message_id FROM user_messages 
                WHERE user_id = %s AND message_type = %s
                ORDER BY created_at DESC LIMIT 1
            ''', (user_id, message_type))
            result = cursor.fetchone()
            return result[0] if result else None
        finally:
            cursor.close()
            conn.close()

    def clear_user_messages(self, user_id: int, message_type: str = 'question'):
        """Clear stored message IDs"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute('''
                DELETE FROM user_messages WHERE user_id = %s AND message_type = %s
            ''', (user_id, message_type))
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            cursor.close()
            conn.close()