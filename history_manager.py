import sqlite3
import json
from datetime import datetime
import os


class HistoryManager:
    def __init__(self, db_file="history.db"):
        self.db_file = db_file
        self.init_db()
    
    def init_db(self):
        """สร้างตาราง History และ Users หากยังไม่มีในระบบ"""
        try:
            with sqlite3.connect(self.db_file) as conn:
                cursor = conn.cursor()
                
                # History Table
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS history (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        title TEXT,
                        url TEXT,
                        result_text TEXT,
                        recommendations TEXT,
                        timestamp TEXT
                    )
                """)
                

                
                conn.commit()

                # การปรับเปลี่ยนฐานข้อมูล: เพิ่มคอลัมน์ recommendations หากยังไม่มี (สำหรับฐานข้อมูลเก่า)
                try:
                    cursor.execute("ALTER TABLE history ADD COLUMN recommendations TEXT")
                    conn.commit()
                except sqlite3.OperationalError:
                     # คอลัมน์น่าจะมีอยู่แล้ว
                     pass
        except Exception as e:
            print(f"Database initialization error: {e}")



    def load_history(self):
        """ดึงข้อมูลประวัติจากฐานข้อมูล SQLite"""
        try:
            with sqlite3.connect(self.db_file) as conn:
                conn.row_factory = sqlite3.Row  # Access columns by name
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM history ORDER BY timestamp DESC LIMIT 50")
                rows = cursor.fetchall()
                
                history = []
                for row in rows:
                    item = dict(row)
                    # recommendations is stored as JSON string, need to decode
                    if item.get('recommendations'):
                        try:
                            item['recommendations'] = json.loads(item['recommendations'])
                        except:
                            item['recommendations'] = []
                    history.append(item)
                return history
        except Exception as e:
            print(f"Error loading history: {e}")
            return []

    def get_today_usage_count(self):
        """นับจำนวนรายการที่ประมวลผลในวันนี้ (Counts entries processed today)"""
        try:
            today_date = datetime.now().strftime("%Y-%m-%d")
            with sqlite3.connect(self.db_file) as conn:
                cursor = conn.cursor()
                # ค้นหา timestamp ที่เริ่มต้นด้วยวันที่ของวันนี้
                cursor.execute("SELECT COUNT(*) FROM history WHERE timestamp LIKE ?", (f"{today_date}%",))
                count = cursor.fetchone()[0]
                return count
        except Exception as e:
            print(f"Error getting today's usage count: {e}")
            return 0

    def save_to_history(self, entry):
        """
        บันทึกข้อมูลใหม่ลงในฐานข้อมูล SQLite
        ในออบเจกต์ entry ควรมีคีย์: title, url, result_text, recommendations
        """
        try:
            # Prepare data
            title = entry.get('title', 'Unknown')
            url = entry.get('url', '')
            result_text = entry.get('result_text', '')
            # แปลง list/dict เป็นสตริง JSON เพื่อจัดเก็บ (JSON string for storage)
            recommendations = json.dumps(entry.get('recommendations', []), ensure_ascii=False)
            timestamp = datetime.now().isoformat()
            
            with sqlite3.connect(self.db_file) as conn:
                cursor = conn.cursor()
                # ตรวจสอบ URL ซ้ำเพื่อหลีกเลี่ยงข้อมูลขยะ (เลือกอัปเดตเวลาแทนการสร้างใหม่)
                cursor.execute("SELECT id FROM history WHERE url = ?", (url,))
                existing = cursor.fetchone()
                
                if existing:
                    # Update existing entry
                    cursor.execute("""
                        UPDATE history 
                        SET title=?, result_text=?, recommendations=?, timestamp=?
                        WHERE url=?
                    """, (title, result_text, recommendations, timestamp, url))
                else:
                    # Insert new entry
                    cursor.execute("""
                        INSERT INTO history (title, url, result_text, recommendations, timestamp)
                        VALUES (?, ?, ?, ?, ?)
                    """, (title, url, result_text, recommendations, timestamp))
                
                conn.commit()
            return True
            
        except Exception as e:
            print(f"Error saving history: {e}")
            return False
            
    def clear_history(self):
        """ลบข้อมูลประวัติทั้งหมด (Deletes all records)"""
        try:
            with sqlite3.connect(self.db_file) as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM history")
                conn.commit()
            return True
        except Exception as e:
            return False
