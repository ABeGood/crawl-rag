import sqlite3
import json
from datetime import datetime
from typing import Optional, List, Dict, Any

class DatabaseManager:
    def __init__(self, db_path: str = "skincare_questionnaire.db"):
        self.db_path = db_path
        self.init_database()

    def init_database(self):
        """Initialize the database with required tables for skincare questionnaire"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Users table to track questionnaire progress
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
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
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                question_index INTEGER,
                question_text TEXT,
                answer_text TEXT,
                answer_type TEXT DEFAULT 'text',  -- 'text', 'photo', 'followup'
                file_id TEXT NULL,  -- Telegram file_id for photos
                followup_text TEXT NULL,  -- Additional text for YES_NO questions
                answered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (user_id)
            )
        ''')
        
        # Photos table for better photo management
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS photos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
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
                user_id INTEGER PRIMARY KEY,
                session_data TEXT,  -- JSON string for complex state
                last_activity TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (user_id)
            )
        ''')
        
        conn.commit()
        conn.close()

    def get_user(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Get user information and progress"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT * FROM users WHERE user_id = ?
        ''', (user_id,))
        
        user = cursor.fetchone()
        conn.close()
        
        return dict(user) if user else None

    def create_or_update_user(self, user_id: int, username: str = None, 
                            first_name: str = None, last_name: str = None) -> None:
        """Create new user or update existing user info"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT OR REPLACE INTO users 
            (user_id, username, first_name, last_name, current_question_index, 
             waiting_for_followup, followup_question_index, questionnaire_completed)
            VALUES (?, ?, ?, ?, 
                COALESCE((SELECT current_question_index FROM users WHERE user_id = ?), 0),
                COALESCE((SELECT waiting_for_followup FROM users WHERE user_id = ?), FALSE),
                COALESCE((SELECT followup_question_index FROM users WHERE user_id = ?), NULL),
                COALESCE((SELECT questionnaire_completed FROM users WHERE user_id = ?), FALSE))
        ''', (user_id, username, first_name, last_name, user_id, user_id, user_id, user_id))
        
        conn.commit()
        conn.close()

    def save_answer(self, user_id: int, question_index: int, 
                   question_text: str, answer_text: str, answer_type: str = 'text',
                   file_id: str = None, followup_text: str = None) -> None:
        """Save user's answer to a question"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Save the answer
        cursor.execute('''
            INSERT INTO answers (user_id, question_index, question_text, answer_text, 
                               answer_type, file_id, followup_text)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (user_id, question_index, question_text, answer_text, answer_type, file_id, followup_text))
        
        # Update user's current question index only if not waiting for followup
        cursor.execute('''
            UPDATE users 
            SET current_question_index = ? 
            WHERE user_id = ? AND waiting_for_followup = FALSE
        ''', (question_index + 1, user_id))
        
        conn.commit()
        conn.close()

    def save_photo(self, user_id: int, question_index: int, question_text: str,
                  file_id: str, file_unique_id: str = None, file_size: int = None,
                  photo_description: str = None) -> None:
        """Save photo upload"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Save to photos table
        cursor.execute('''
            INSERT INTO photos (user_id, question_index, file_id, file_unique_id, 
                              file_size, photo_description)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (user_id, question_index, file_id, file_unique_id, file_size, photo_description))
        
        # Save to answers table
        cursor.execute('''
            INSERT INTO answers (user_id, question_index, question_text, answer_text, 
                               answer_type, file_id)
            VALUES (?, ?, ?, ?, 'photo', ?)
        ''', (user_id, question_index, question_text, "Fotografie nahrána", file_id))
        
        # Update user's progress
        cursor.execute('''
            UPDATE users 
            SET current_question_index = ? 
            WHERE user_id = ?
        ''', (question_index + 1, user_id))
        
        conn.commit()
        conn.close()

    def set_waiting_for_followup(self, user_id: int, question_index: int) -> None:
        """Set user as waiting for followup answer"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            UPDATE users 
            SET waiting_for_followup = TRUE, followup_question_index = ?
            WHERE user_id = ?
        ''', (question_index, user_id))
        
        conn.commit()
        conn.close()

    def save_followup_answer(self, user_id: int, question_index: int, followup_text: str) -> None:
        """Save followup answer and clear waiting state"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Update the existing answer with followup text
        cursor.execute('''
            UPDATE answers 
            SET followup_text = ?
            WHERE user_id = ? AND question_index = ?
            ORDER BY answered_at DESC
            LIMIT 1
        ''', (followup_text, user_id, question_index))
        
        # Clear waiting state and advance to next question
        cursor.execute('''
            UPDATE users 
            SET waiting_for_followup = FALSE, 
                followup_question_index = NULL,
                current_question_index = ?
            WHERE user_id = ?
        ''', (question_index + 1, user_id))
        
        conn.commit()
        conn.close()

    def clear_followup_state(self, user_id: int, question_index: int) -> None:
        """Clear followup waiting state without additional text"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            UPDATE users 
            SET waiting_for_followup = FALSE, 
                followup_question_index = NULL,
                current_question_index = ?
            WHERE user_id = ?
        ''', (question_index + 1, user_id))
        
        conn.commit()
        conn.close()

    def mark_questionnaire_completed(self, user_id: int) -> None:
        """Mark questionnaire as completed for user"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            UPDATE users 
            SET questionnaire_completed = TRUE, 
                completed_at = CURRENT_TIMESTAMP,
                waiting_for_followup = FALSE,
                followup_question_index = NULL
            WHERE user_id = ?
        ''', (user_id,))
        
        conn.commit()
        conn.close()

    def get_user_answers(self, user_id: int) -> List[Dict[str, Any]]:
        """Get all answers for a specific user including photos"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT * FROM answers 
            WHERE user_id = ? 
            ORDER BY question_index, answered_at
        ''', (user_id,))
        
        answers = cursor.fetchall()
        conn.close()
        
        return [dict(answer) for answer in answers]

    def get_user_photos(self, user_id: int) -> List[Dict[str, Any]]:
        """Get all photos for a specific user"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT * FROM photos 
            WHERE user_id = ? 
            ORDER BY question_index, uploaded_at
        ''', (user_id,))
        
        photos = cursor.fetchall()
        conn.close()
        
        return [dict(photo) for photo in photos]

    def reset_user_progress(self, user_id: int) -> None:
        """Reset user's questionnaire progress"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Delete existing answers and photos
        cursor.execute('DELETE FROM answers WHERE user_id = ?', (user_id,))
        cursor.execute('DELETE FROM photos WHERE user_id = ?', (user_id,))
        
        # Reset user progress
        cursor.execute('''
            UPDATE users 
            SET current_question_index = 0, 
                waiting_for_followup = FALSE,
                followup_question_index = NULL,
                questionnaire_completed = FALSE, 
                completed_at = NULL
            WHERE user_id = ?
        ''', (user_id,))
        
        conn.commit()
        conn.close()

    def get_statistics(self) -> Dict[str, Any]:
        """Get comprehensive statistics about the skincare questionnaire"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Total users
        cursor.execute('SELECT COUNT(*) FROM users')
        total_users = cursor.fetchone()[0]
        
        # Completed questionnaires
        cursor.execute('SELECT COUNT(*) FROM users WHERE questionnaire_completed = TRUE')
        completed_users = cursor.fetchone()[0]
        
        # Active users (started but not completed)
        cursor.execute('SELECT COUNT(*) FROM users WHERE questionnaire_completed = FALSE AND current_question_index > 0')
        active_users = cursor.fetchone()[0]
        
        # Photo uploads count
        cursor.execute('SELECT COUNT(*) FROM photos')
        total_photos = cursor.fetchone()[0]
        
        # Average age (from scale question)
        cursor.execute('''
            SELECT AVG(CAST(answer_text AS INTEGER)) 
            FROM answers 
            WHERE question_index = 0 AND answer_text REGEXP '^[0-9]+$'
        ''')
        avg_age_result = cursor.fetchone()[0]
        avg_age = avg_age_result if avg_age_result else 0
        
        # Smokers count
        cursor.execute('''
            SELECT COUNT(*) 
            FROM answers 
            WHERE question_index = 1 AND answer_text = 'Ano'
        ''')
        smokers_count = cursor.fetchone()[0]
        
        conn.close()
        
        return {
            'total_users': total_users,
            'completed_users': completed_users,
            'active_users': active_users,
            'completion_rate': completed_users / total_users if total_users > 0 else 0,
            'total_photos': total_photos,
            'average_age': round(avg_age, 1),
            'smokers_count': smokers_count
        }

    def export_consultation_data(self, user_id: int) -> Dict[str, Any]:
        """Export complete consultation data for a user"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # Get user info
        cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
        user_info = dict(cursor.fetchone() or {})
        
        # Get all answers
        cursor.execute('''
            SELECT question_index, question_text, answer_text, answer_type, 
                   file_id, followup_text, answered_at
            FROM answers 
            WHERE user_id = ? 
            ORDER BY question_index, answered_at
        ''', (user_id,))
        answers = [dict(row) for row in cursor.fetchall()]
        
        # Get photos
        cursor.execute('''
            SELECT question_index, file_id, file_unique_id, file_size, uploaded_at
            FROM photos 
            WHERE user_id = ? 
            ORDER BY question_index, uploaded_at
        ''', (user_id,))
        photos = [dict(row) for row in cursor.fetchall()]
        
        conn.close()
        
        return {
            'user_info': user_info,
            'answers': answers,
            'photos': photos,
            'export_timestamp': datetime.now().isoformat()
        }