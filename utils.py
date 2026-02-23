import re
import os
import hashlib
from urllib.parse import urlparse, parse_qs
import time
import subprocess
import platform
import yt_dlp
from yt_dlp.networking.impersonate import ImpersonateTarget

# บังคับเพิ่ม Path สำหรับ ffmpeg ในกรณีที่ระบบมองไม่เห็น
os.environ["PATH"] += os.pathsep + "/opt/homebrew/bin"
os.environ["PATH"] += os.pathsep + "/usr/local/bin"

def format_time(s):
    # รูปแบบ HH:MM:SS.mmm
    h = int(s // 3600)
    m = int((s % 3600) // 60)
    sec = s % 60
    return f"{h:02d}:{m:02d}:{sec:06.3f}"

def extract_video_id(url):
    """
    ดึง ID วิดีโอจาก URL ของ YouTube
    รองรับรูปแบบต่างๆ ดังนี้:
    - https://www.youtube.com/watch?v=VIDEO_ID
    - https://m.youtube.com/watch?v=VIDEO_ID
    - https://music.youtube.com/watch?v=VIDEO_ID
    - https://youtu.be/VIDEO_ID
    - https://www.youtube.com/embed/VIDEO_ID
    """
    if not url: return None
    parsed_url = urlparse(url)
    
    if parsed_url.hostname == 'youtu.be':
        return parsed_url.path[1:]
    
    if parsed_url.hostname in ('www.youtube.com', 'youtube.com', 'm.youtube.com', 'music.youtube.com'):
        if parsed_url.path == '/watch':
            query_params = parse_qs(parsed_url.query)
            return query_params.get('v', [None])[0]
        if parsed_url.path.startswith('/embed/'):
            return parsed_url.path.split('/')[2]
        if parsed_url.path.startswith('/v/'):
            return parsed_url.path.split('/')[2]
        if parsed_url.path.startswith('/live/'):
            return parsed_url.path.split('/')[2]
        if parsed_url.path.startswith('/shorts/'):
            return parsed_url.path.split('/')[2]
            
    return None

def format_transcript(transcript_list):
    """
    รวมรายการบทบรรยายเข้าเป็นสตริงเดียว
    """
    return " ".join([item['text'] for item in transcript_list])

def format_transcript_with_timestamps(transcript_list):
    """
    จัดรูปแบบรายการบทบรรยายเป็นรายการ Dictionary ที่ประกอบด้วยเวลาเริ่มต้น, ความยาว, เวลาสิ้นสุด และข้อความ
    คืนค่า: [{'start': float, 'duration': float, 'end': float, 'text': str}, ...]
    """
    formatted = []
    for item in transcript_list:
        start = float(item['start']) if isinstance(item, dict) else item.start
        duration = float(item['duration']) if isinstance(item, dict) else item.duration
        formatted.append({
            'start': start,
            'duration': duration,
            'end': start + duration,
            'text': item['text'] if isinstance(item, dict) else item.text
        })

    return formatted

def download_video_preview(url):
    """
    ดาวน์โหลดวิดีโอเพื่อใช้ในการแสดงตัวอย่าง (เช่น TikTok)
    คืนค่าเป็นเส้นทางของไฟล์ที่ดาวน์โหลด
    """
    import tempfile
    import os
    
    # สร้างชื่อไฟล์ตาม Hash ของ URL เพื่อให้สามารถแคชหรือนำกลับมาใช้ใหม่ได้
    import hashlib
    url_hash = hashlib.md5(url.encode()).hexdigest()
    temp_dir = tempfile.gettempdir()
    # รูปแบบไฟล์ผลลัพธ์: /tmp/preview_MD5.mp4
    output_template = os.path.join(temp_dir, f"preview_{url_hash}.%(ext)s")
    
    # ตรวจสอบว่ามีไฟล์อยู่แล้วหรือไม่ (ระบบแคชแบบง่าย)
    # ตรวจสอบนามสกุลไฟล์หรือรูปแบบที่ตรงกัน
    base_path = os.path.join(temp_dir, f"preview_{url_hash}")
    for ext in ['.mp4', '.mkv', '.webm']:
        if os.path.exists(base_path + ext):
            return base_path + ext

    # การตั้งค่าคุ้กกี้และความเสถียรสำหรับ TikTok
    base_ydl_opts = {
        'format': 'best[ext=mp4]/best', 
        'outtmpl': output_template,
        'quiet': True,
        'no_warnings': True,
        'overwrite': False, 
        'socket_timeout': 15, # เพิ่มเวลา Timeout สำหรับ TikTok
        'nocheckcertificate': True,
        'geo_bypass': True,
        'extractor_args': {
            'youtube': {
                'player_client': ['ios', 'android', 'web']
            }
        },
    }

    cookie_sources = []
    
    # 0. PROJECT COOKIES (ตู้เก็บคุกกี้ของผู้ใช้ - ความสำคัญสูงสุด)
    project_cookie_file = os.path.join(os.getcwd(), 'PROJECT_COOKIES.txt')
    if os.path.exists(project_cookie_file):
        cookie_sources.append({'cookiefile': project_cookie_file})
    
    if "tiktok.com" in url:
        cookie_file = os.path.join(os.getcwd(), 'tiktok_cookies.txt')
        if os.path.exists(cookie_file):
            cookie_sources.append({'cookiefile': cookie_file})
        
        if platform.system() == 'Darwin':
            cookie_sources.append({'cookiesfrombrowser': ['safari']})
        # Removed Chrome source to ensure system doesn't rely on it
        cookie_sources.append({}) # ลำดับสุดท้ายลองแบบไม่ใช้คุ้กกี้

    last_error = None
    for source in cookie_sources:
        ydl_opts = base_ydl_opts.copy()
        ydl_opts.update(source)
        
        if "tiktok.com" in url:
            ua = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Safari/605.1.15'
            ydl_opts['impersonate'] = ImpersonateTarget(client='safari', os='macos', os_version='15', version='18.0')
            ydl_opts['http_headers'] = {
                'User-Agent': ua,
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.9,th;q=0.8',
                'Referer': 'https://www.tiktok.com/',
            }

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])
            
            # ตรวจสอบไฟล์ที่ดาวน์โหลด
            for ext in ['.mp4', '.mkv', '.webm']:
                if os.path.exists(base_path + ext):
                    return base_path + ext
        except Exception as e:
            last_error = e
            continue
            
    # --- ระบบสำรอง (Stealth Fallback) สำหรับแสดงตัวอย่างวิดีโอ TikTok ---
    if "tiktok.com" in url and not os.path.exists(base_path + ".mp4"):
        print("⚠️ TikTok preview blocked locally, trying Stealth Fallback (TikWM)...")
        try:
            import requests
            clean_url = url.split('?')[0]
            tikwm_url = f"https://www.tikwm.com/api/?url={clean_url}"
            resp = requests.get(tikwm_url, timeout=15)
            if resp.status_code == 200:
                data = resp.json()
                if data.get('code') == 0:
                    video_url = data['data'].get('play')
                    if video_url:
                        print(f"✅ Found preview video via stealth: {video_url[:50]}...")
                        video_resp = requests.get(video_url, timeout=30)
                        if video_resp.status_code == 200:
                            target_path = base_path + ".mp4"
                            with open(target_path, "wb") as f:
                                f.write(video_resp.content)
                            return target_path
        except Exception as te:
            print(f"❌ Stealth preview fallback error: {te}")
            
    if last_error:
        print(f"Error downloading video preview: {last_error}")
    return None

def get_video_info(url):
    """
    ดึงข้อมูล Metadata ของวิดีโอ (ชื่อ, ความยาว, ผู้ดูแล ฯลฯ) โดยใช้ yt-dlp
    รองรับ YouTube, TikTok, Facebook, Instagram, X, Vimeo, Dailymotion, Twitch ฯลฯ
    """
    

    # การตั้งค่าพื้นฐาน (Base options)
    base_ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'skip_download': True,
        'ignoreerrors': True,
        'nocheckcertificate': True,
        'geo_bypass': True,
        'extractor_args': {
            'youtube': {
                'player_client': ['ios', 'android', 'web']
            }
        },
    }

    # แหล่งที่มาของคุ้กกี้ที่อาจใช้สำหรับ TikTok
    cookie_sources = []
    
    # 0. PROJECT COOKIES (ตู้เก็บคุกกี้ของผู้ใช้ - ความสำคัญสูงสุด)
    project_cookie_file = os.path.join(os.getcwd(), 'PROJECT_COOKIES.txt')
    if os.path.exists(project_cookie_file):
        cookie_sources.append({'cookiefile': project_cookie_file})
        
    if "tiktok.com" in url:
        cookie_file = os.path.join(os.getcwd(), 'tiktok_cookies.txt')
        if os.path.exists(cookie_file):
            cookie_sources.append({'cookiefile': cookie_file})
        
        # Add browsers
        if platform.system() == 'Darwin':
            cookie_sources.append({'cookiesfrombrowser': ['safari']})
        # Chrome source removed per user request
        
    # เพิ่มแหล่งสำรอง: ไม่ใช้คุ้กกี้
    cookie_sources.append({}) 

    # --- ระบบสำรอง (Fallback): ใช้ curl_cffi สำหรับ Metadata ของ TikTok ---
    if "tiktok.com" in url:
        try:
            from curl_cffi import requests
            headers = {
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Safari/605.1.15",
            }
            # เลียนแบบเบราว์เซอร์ทั่วไปเพื่อเลี่ยงระบบป้องกัน
            r = requests.get(url, headers=headers, impersonate="safari12_1", timeout=15)
            if r.status_code == 200:
                import re
                # ลองดึงคำอธิบายจาก Meta OG ก่อน (มักจะมีข้อความบรรยายวิดีโอ)
                desc_match = re.search(r'<meta property="og:description" content="(.*?)"', r.text)
                if desc_match:
                    title = desc_match.group(1)
                else:
                    title_match = re.search(r'<title>(.*?)</title>', r.text)
                    title = title_match.group(1) if title_match else "TikTok Video"
                
                # ลบข้อความส่วนเกินจากชื่อเรื่อง (Remove junk)
                title = re.sub(r' \| TikTok$', '', title).strip()
                title = re.sub(r'^TikTok - ', '', title).strip()
                if not title or title == "Make Your Day": title = "TikTok Video"
                
                # พยายามหา ID วิดีโอ
                video_id = url.split('/')[-1].split('?')[0]
                
                return {
                    'id': video_id,
                    'title': title,
                    'uploader': "TikTok User",
                    'duration': None,
                    'platform': 'TikTok',
                    'webpage_url': url,
                    'thumbnail': None,
                    'url': None
                }
        except Exception as e:
            print(f"curl_cffi fallback failed: {e}")
    else:
        # สำหรับ URL ที่ไม่ใช่ TikTok
        cookie_sources = [{}]

    last_error = None
    safari_permission_error = False
    
    for source in cookie_sources:
        ydl_opts = base_ydl_opts.copy()
        ydl_opts.update(source)
        
        if "tiktok.com" in url:
            # พยายามใช้ Safari เพื่อจำลองเบราว์เซอร์ให้ดีขึ้นเพื่อเลี่ยงการบล็อก
            ua = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Safari/605.1.15'
            ydl_opts['impersonate'] = ImpersonateTarget(client='safari', os='macos', os_version='15', version='18.0')
            ydl_opts['http_headers'] = {
                'User-Agent': ua,
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.9,th;q=0.8',
            }
            
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                if info:
                    return {
                        'id': info.get('id'),
                        'title': info.get('title'),
                        'uploader': info.get('uploader'),
                        'duration': info.get('duration'),
                        'platform': info.get('extractor_key'),
                        'webpage_url': info.get('webpage_url'),
                        'thumbnail': info.get('thumbnail'),
                        'url': info.get('url')
                    }
        except Exception as e:
            err_str = str(e)
            if 'Operation not permitted' in err_str and 'Safari' in err_str:
                safari_permission_error = True
            last_error = e
            continue
            
    if safari_permission_error:
        raise Exception("SAFARI_PERMISSION_DENIED: กรุณาอนุญาตให้แอปเข้าถึงข้อมูล Safari ในการตั้งค่าความเป็นส่วนตัวของเครื่อง")
            
    if last_error:
        print(f"Error fetching video info: {last_error}")
    return None

def get_video_title(url):
    """
    ดึงชื่อเรื่องของวิดีโอ โดยพยายามใช้ yt-dlp ก่อน และหากล้มเหลวจะใช้ requests/bs4 สำรอง
    """
    info = get_video_info(url)
    if info and info.get('title'):
        return info['title']
        
    # ระบบสำรองสำหรับบางกรณี หรือเมื่อ yt-dlp ล้มเหลวแต่ยังสามารถเข้าถึงหน้าเว็บปกติได้
    import requests
    from bs4 import BeautifulSoup
    
    try:
        response = requests.get(url)
        soup = BeautifulSoup(response.text, 'html.parser')
        title = soup.find('title')
        if title:
            return title.string.replace(" - YouTube", "")
        return None
    except Exception as e:
        print(f"Error fetching title: {e}")
        return None

def download_audio(url, output_filename="temp_audio"):
    """
    Downloads audio from a video URL using yt-dlp.
    Attempts to use cookies from various sources if available.
    """
    import os
    
    # ล้างไฟล์เก่าทิ้งก่อน (Clean up previous files)
    possible_extensions = ['m4a', 'mp3', 'webm', 'mp4', 'aac', 'wav']
    for ext in possible_extensions:
        path = f"{output_filename}.{ext}"
        if os.path.exists(path):
            try: os.remove(path)
            except: pass
                
    if os.path.exists(output_filename):
        try: os.remove(output_filename)
        except: pass
        
    base_ydl_opts = {
        'format': 'bestaudio/best', 
        'outtmpl': output_filename, 
        'quiet': False,
        'no_warnings': False,
        'ignoreerrors': False, 
        'nocheckcertificate': True,
        'geo_bypass': True,
        'nopart': True,
        'extractor_args': {
            'youtube': {
                'player_client': ['ios', 'android', 'web']
            }
        },
        'socket_timeout': 60,
        'retries': 5,
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'wav',
            'preferredquality': '192',
        }],
        'postprocessor_args': [
            '-ac', '1',  # Mono
            '-ar', '16000' # 16kHz (Gemini Native Resolution) for zero-latency sync
        ],
    }
    
    cookie_sources = []
    
    # 0. PROJECT COOKIES (ตู้เก็บคุกกี้ของผู้ใช้ - ความสำคัญสูงสุด)
    project_cookie_file = os.path.join(os.getcwd(), 'PROJECT_COOKIES.txt')
    if os.path.exists(project_cookie_file):
        cookie_sources.append({'cookiefile': project_cookie_file})
        
    # พยายามใช้ไฟล์คุ้กกี้ที่มีอยู่ในโฟลเดอร์โครงการก่อน
    cookie_file = os.path.join(os.getcwd(), 'youtube_cookies.txt') if "youtube.com" in url or "youtu.be" in url else os.path.join(os.getcwd(), 'tiktok_cookies.txt')
    if os.path.exists(cookie_file):
        cookie_sources.append({'cookiefile': cookie_file})
    
    # หากไม่มีไฟล์คุ้กกี้ ให้ลองดึงจากเบราว์เซอร์ที่ติดตั้งในเครื่อง
    if platform.system() == 'Darwin':
        cookie_sources.append({'cookiesfrombrowser': ['safari']})
    # Chrome and Firefox removed to prioritize Safari-native experience
    cookie_sources.append({'cookiesfrombrowser': ['firefox']})
    
    # Rotating Fallbacks (Automatic Retry System)
    # หากการโหลดปกติล้มเหลว ระบบจะ "ลองใหม่" โดยปลอมตัวเป็นเบราว์เซอร์อื่นอัตโนมัติ
    
    # 1. Safari on macOS (Native Apple - Priority for Mac users)
    cookie_sources.append({'rotation_target': ImpersonateTarget(client='safari', os='macos', os_version='15', version='18.0')})
    
    # 2. Safari (Earlier macOS version)
    cookie_sources.append({'rotation_target': ImpersonateTarget(client='safari', os='macos', os_version='14', version='17.0')})
    
    # 3. Simple Safari (Broadly supported)
    cookie_sources.append({'rotation_target': 'safari'})

    last_error = None
    safari_permission_error = False
    
    for source in cookie_sources:
        ydl_opts = base_ydl_opts.copy()
        ydl_opts.update(source)
        
        source_name = source.get('cookiesfrombrowser', 'no-cookies')
        if source.get('cookiefile'):
            source_name = f"file:{os.path.basename(source.get('cookiefile'))}"

        if "tiktok.com" in url or "youtube.com" in url or "youtu.be" in url:
            # Use robust settings as get_video_info
            
            # Use Impersonate by default to avoid 403 (for browser cookies or no cookies)
            # BUT disable it if using a specific cookie FILE (fingerprint mismatch risk)
            should_impersonate = True
            if source.get('cookiefile'):
                should_impersonate = False
                
            if should_impersonate:
                try:
                    if source.get('rotation_target'):
                        # Use the specific target for this rotation
                        ydl_opts['impersonate'] = source['rotation_target']
                    else:
                        # Default for browser cookies: Match Safari on Mac
                        ydl_opts['impersonate'] = ImpersonateTarget(client='safari', os='macos', os_version='15', version='18.0')
                except:
                    pass 
            
            ua = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Safari/605.1.15'
            ydl_opts['http_headers'] = {
                'User-Agent': ua,
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.9,th;q=0.8',
                'Referer': 'https://www.google.com/',
            }
            
        try:
            print(f"   🚀 Download attempt using: {source_name}")
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])
            
            # ค้นหาไฟล์ที่ดาวน์โหลดสำเร็จ
            for ext in possible_extensions:
                path = f"{output_filename}.{ext}"
                if os.path.exists(path):
                    print(f"   ✅ Download successful: {path}")
                    return path
            if os.path.exists(output_filename):
                print(f"   ✅ Download successful (no ext): {output_filename}")
                return output_filename
        except Exception as e:
            # Clean ANSI colors and use repr(e) if empty
            import re
            raw_err = str(e) if str(e) else repr(e)
            ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
            err_str = ansi_escape.sub('', raw_err)
            
            print(f"   ⚠️  Download attempt failed ({source_name}): {err_str[:200]}...")
            if 'Operation not permitted' in err_str and 'Safari' in err_str:
                safari_permission_error = True
            
            # ลำดับความสำคัญของ Error:
            # 1. Actionable (Sign in, Blocked, Unavailable)
            # 2. Network/Timeout
            # 3. Cookie not found (ความสำคัญต่ำสุด)
            
            is_serious_error = any(msg in err_str for msg in ["Sign in", "blocked", "Unavailable", "403", "Forbidden"])
            is_cookie_not_found = "could not find" in err_str.lower() or "database" in err_str.lower()
            
            if not last_error:
                last_error = e
            elif is_serious_error and not any(msg in (str(last_error) if str(last_error) else repr(last_error)) for msg in ["Sign in", "blocked", "Unavailable"]):
                last_error = e
            elif not is_cookie_not_found and "could not find" in (str(last_error) if str(last_error) else repr(last_error)).lower():
                 last_error = e
            continue
    
    if last_error:
        # เก็บข้อความ Error ล่าสุดที่คัดกรองเลาย (ANSI Stripped)
        raw_msg = str(last_error) if str(last_error) else repr(last_error)
        import re
        ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
        error_msg = ansi_escape.sub('', raw_msg)
        
        with open(f"{output_filename}.error", "w", encoding="utf-8") as f:
            f.write(f"[{time.strftime('%H:%M:%S')}] {error_msg}")
            # ตรวจสอบสาเหตุยอดนิยม
            if "Video unavailable" in error_msg:
                f.write("\n💡 วิดีโอนี้อาจจะถูกลบ หรือตั้งเป็นส่วนตัว")
            elif "Sign in to confirm your age" in error_msg:
                f.write("\n💡 วิดีโอนี้จำกัดอายุ กรุณาตรวจสอบว่าได้ลงชื่อเข้าใช้ใน Safari แล้ว")
            elif "blocked" in error_msg.lower() or "403" in error_msg:
                f.write("\n💡 ถูกบล็อกการเข้าถึง (Access Blocked) กรุณาลองใหม่ภายหลัง")
            elif "could not find" in error_msg.lower() and "cookies" in error_msg.lower():
                f.write("\n💡 ระบบไม่สามารถดึงข้อมูลจาก Safari ได้")
    
    if last_error and "tiktok.com" in url:
        print("⚠️ TikTok ถูกบล็อกในเครื่อง กำลังใช้ระบบสำรองเสียง (TikWM)...")
        try:
            import requests
            clean_url = url.split('?')[0]
            tikwm_url = f"https://www.tikwm.com/api/?url={clean_url}"
            resp = requests.get(tikwm_url, timeout=15)
            if resp.status_code == 200:
                data = resp.json()
                if data.get('code') == 0:
                    audio_url = data['data'].get('music')
                    if audio_url:
                        print(f"✅ Found audio via stealth: {audio_url[:50]}...")
                        audio_resp = requests.get(audio_url, timeout=30)
                        if audio_resp.status_code == 200:
                            path = f"{output_filename}.mp3"
                            with open(path, "wb") as f:
                                f.write(audio_resp.content)
                            return path
            else:
                print(f"❌ Stealth audio fallback failed: {data.get('msg')}")
        except Exception as te:
            print(f"❌ Stealth audio fallback error: {te}")

    if safari_permission_error:
        raise Exception("SAFARI_PERMISSION_DENIED: กรุณาอนุญาตให้แอปเข้าถึงข้อมูล Safari")
            
    return None


def search_videos(query, max_results=3, platforms=['youtube']):
    """
    ค้นหาวิดีโอที่เกี่ยวข้องจากหลายแพลตฟอร์ม
    YouTube: ใช้ ytsearch ของ yt-dlp
    TikTok: ใช้การดึงข้อมูลจากเว็บเพื่อหาเป้าหมายหรือวิดีโอที่กำลังเป็นกระแส
    คืนค่าเป็นรายการ Dictionary: [{'title': str, 'url': str, 'duration': str, 'platform': str}, ...]
    """
    import subprocess
    import json
    import re
    
    all_videos = []
    
    for platform in platforms:
        if platform.lower() == 'youtube':
            print(f"   🔍 Searching YouTube for: {query}")
            search_prefix = f"ytsearch{max_results}"
            
            try:
                # ใช้ yt-dlp เพื่อค้นหาและแสดงผลเป็น JSON
                command = [
                    "./venv/bin/yt-dlp",
                    f"{search_prefix}:{query}",
                    "--dump-json",
                    "--no-playlist",
                    "--quiet",
                    "--skip-download"
                ]
                
                # รันคำสั่ง (Run command)
                result = subprocess.run(command, capture_output=True, text=True, timeout=30)
                
                if result.returncode == 0:
                    # yt-dlp จะแสดงผลลัพธ์เป็นออบเจกต์ JSON หนึ่งรายการต่อหนึ่งบรรทัดสำหรับการค้นหา
                    for line in result.stdout.strip().split('\n'):
                        if line:
                            try:
                                data = json.loads(line)
                                all_videos.append({
                                    'title': data.get('title'),
                                    'url': data.get('webpage_url'),
                                    'thumbnail': data.get('thumbnail'),
                                    'duration': data.get('duration_string'),
                                    'views': data.get('view_count'),
                                    'platform': 'Youtube'
                                })
                            except json.JSONDecodeError:
                                continue
                else:
                    if result.stderr:
                        print(f"   ⚠️  YouTube search failed")
                    
            except subprocess.TimeoutExpired:
                print(f"   ⚠️  YouTube search timeout")
            except Exception as e:
                print(f"   ⚠️  Error searching YouTube: {e}")
                
        elif platform.lower() == 'tiktok':
            # การค้นหาของ TikTok ยังไม่เปิดใช้งานในขณะนี้
            # Would require TikTok API or web scraping
            print(f"   ℹ️  TikTok search not implemented yet")
            pass
    
    return all_videos


def extract_search_query_from_ai_result(ai_result, video_title=""):
    """
    ดึงข้อความค้นหาที่มีความหมายจากผลลัพธ์การวิเคราะห์ของ AI
    แยกวิเคราะห์ส่วน [SUMMARY] และ [TOPICS] เพื่อค้นหาหัวข้อหลัก
    เน้นส่วน [TOPICS] เพื่อให้ได้คำค้นหาที่สะอาดและเป็นชื่อหัวข้อทั่วไปมากขึ้น
    """
    if not ai_result:
        return video_title[:50] if video_title else None
    
    # พยายามดึงจากส่วน [TOPICS] ก่อน (มักจะสะอาดและทั่วไปมากกว่า)
    topics_match = re.search(r'\[TOPICS\](.*?)(?:\[|$)', ai_result, re.DOTALL | re.IGNORECASE)
    if topics_match:
        topics_text = topics_match.group(1).strip()
        # ดึงบรรทัดหรือหัวข้อแรก
        lines = [line.strip() for line in topics_text.split('\n') if line.strip()]
        if lines:
            first_topic = lines[0]
            # ดึงเฉพาะชื่อหัวข้อ (ก่อนเครื่องหมายโคลอนหรือแดช)
            topic = re.split(r'[:\-]', first_topic)[0].strip()
            # ลบจุดนำหัวข้อ ตัวเลข (Remove bullet points, numbers)
            topic = re.sub(r'^[\-\*\d\.\)]+\s*', '', topic)
            if len(topic) > 5:
                return topic[:60]
    
    # ระบบสำรอง: พยายามดึงวลีสำคัญจากส่วน [SUMMARY]
    summary_match = re.search(r'\[SUMMARY\](.*?)(?:\[|$)', ai_result, re.DOTALL | re.IGNORECASE)
    if summary_match:
        summary_text = summary_match.group(1).strip()
        
        # ค้นหารูปแบบภาษาไทยทั่วไปที่ระบุถึงหัวข้อหลัก
        topic_patterns = [
            r'(?:เกี่ยวกับ|พูดถึง|เรื่อง|เนื้อหา)\s*([^\n\.]{10,40})',
            r'(?:คดี|กรณี|ประเด็น)\s*([^\n\.]{10,40})',
        ]
        
        for pattern in topic_patterns:
            match = re.search(pattern, summary_text)
            if match:
                topic = match.group(1).strip()
                # ล้างข้อมูล - ลบตัวเชื่อมที่อยู่ท้ายข้อความ
                topic = re.sub(r'\s*(ที่|ซึ่ง|โดย|และ|ว่า).*$', '', topic)
                if len(topic) > 10:
                    return topic[:50]
        
        # ทางเลือกสุดท้าย: ใช้ประโยคสั้นๆ ประโยคแรก
        sentences = summary_text.split('.')
        for sent in sentences[:2]:
            sent = sent.strip()
            if 15 < len(sent) < 50:
                return sent
    
    # Fallback: use video title
    return video_title[:50] if video_title else None

def extract_meaningful_search_query(topic_string):
    """
    ดึงข้อความค้นหาที่มีความหมายจากสตริงหัวข้อของ AI
    ตัวอย่าง:
    - "[00:01:23] การรับสารภาพ: เกี่ยวกับ..." -> "การรับสารภาพ"
    - "การรับสารภาพของนายกิตติ: เกี่ยวกับ..." -> "การรับสารภาพของนายกิตติ"
    - "Python Programming: Learn basics" -> "Python Programming"
    """
    if not topic_string:
        return None
    
    # ลบเวลา (Timestamp) ออกหากมีอยู่ [HH:MM:SS] หรือ [MM:SS]
    topic_string = re.sub(r'^\[\d{1,2}:\d{2}(?::\d{2})?\]\s*', '', topic_string)
    
    # ลบคำนำหน้าทั่วไป (จุดนำหัวข้อ, ตัวเลข, เครื่องหมายแดช)
    topic_string = re.sub(r'^[\-\*\d\.\)]+\s*', '', topic_string)
    
    # แยกด้วยเครื่องหมายโคลอนและเอาส่วนแรก (หัวข้อหลักก่อนคำอธิบาย)
    # รวมถึงจัดการเครื่องหมายแดชหากไม่มีเครื่องหมายโคลอน
    main_topic = re.split(r'[:\-]', topic_string)[0].strip()
    
    # จำกัดความยาว (ยาวเกินไปจะทำให้ผลการค้นหาไม่ดี)
    if len(main_topic) > 60:
        # พยายามตัดตามขอบเขตของคำ
        main_topic = main_topic[:60].rsplit(' ', 1)[0]
    
    return main_topic if main_topic else topic_string[:50]

def parse_timestamp_to_seconds(timestamp_str):
    """
    แปลง [HH:MM:SS] หรือ [MM:SS] หรือ HH:MM:SS หรือ MM:SS เป็นจำนวนวินาทีทั้งหมด
    คืนค่าเป็น None หากไม่พบรูปแบบที่ถูกต้อง
    """
    if not timestamp_str:
        return None
        
    # ค้นหาสิ่งที่ดูเหมือนเป็นเวลา (Timestamp) - รองรับมิลลิวินาทีที่เป็น .
    match = re.search(r'(\d{1,2}):(\d{2})(?::(\d{2}))?(?:\.(\d+))?', timestamp_str)
    if not match:
        return None
        
    # ดึงส่วนประกอบต่างๆ (Extract parts)
    groups = match.groups()
    
    total_seconds = 0.0
    if groups[2] is not None: # HH:MM:SS
        total_seconds = float(groups[0]) * 3600 + float(groups[1]) * 60 + float(groups[2])
    else: # MM:SS
        total_seconds = float(groups[0]) * 60 + float(groups[1])
        
    # เติมมิลลิวินาที (ถ้ามี)
    if groups[3]:
        ms = float(f"0.{groups[3]}")
        total_seconds += ms
        
    return total_seconds

def get_url_with_timestamp(url, seconds, autoplay=False):
    """
    เพิ่มพารามิเตอร์เวลา (Timestamp) ลงใน URL เพื่อให้สามารถเลื่อนเวลาได้อย่างแม่นยำ
    YouTube: &t=Xs
    """
    if not url or seconds is None:
        return url
        
    if 'youtube.com' in url or 'youtu.be' in url:
        video_id = extract_video_id(url)
        if video_id:
            # ใช้รูปแบบ Embed URL พร้อม start=X และตัวป้องกันการแคชแบบสุ่มเพื่อให้บังคับรีเฟรช
            # time.time() ให้ ID ที่ไม่ซ้ำกันในทุกวินาทีเพื่อเลี่ยงการแคชคอมโพเนนต์
            sync_id = int(time.time() * 10) % 100000 
            timed_url = f"https://www.youtube.com/embed/{video_id}?start={int(seconds)}&sync={sync_id}"
            if autoplay:
                timed_url += "&autoplay=1&mute=1"
            return timed_url
        
    return url

# เพื่อรักษาระบบการรองรับย้อนหลัง (Keep backward compatibility)
def search_youtube(query, max_results=3):
    """
    ค้นหาวิดีโอจาก YouTube (เพื่อการรองรับย้อนหลัง)
    """
    return search_videos(query, max_results, platforms=['youtube'])
