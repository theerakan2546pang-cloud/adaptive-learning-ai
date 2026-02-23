import streamlit as st
import os
import tempfile
import re
from history_manager import HistoryManager
from main import process_video
from concurrent.futures import ThreadPoolExecutor, as_completed
from utils import (
    extract_meaningful_search_query, 
    parse_timestamp_to_seconds, 
    get_url_with_timestamp, 
    format_time, 
    search_videos,
    extract_video_id,
    get_video_info,
    download_video_preview
)

# ตั้งค่าหน้าเว็บ
st.set_page_config(
    page_title="ระบบถอดเสียงวิดีโอด้วย AI",
    page_icon="🎥",
    layout="centered",
)

# CSS เพิ่มเติมเพื่อจัดเนื้อหาให้พรีเมียม (Monica Style)
st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;600&display=swap');
    
    html, body, [data-testid="stAppViewContainer"] {
        font-family: 'Outfit', sans-serif;
    }

    .main .block-container {
        max-width: 900px;
        padding-top: 2rem;
        padding-bottom: 5rem;
    }
    
    /* Background Gradient */
    .stApp {
        background: linear-gradient(135deg, #fceabb 0%, #f8b500 50%, #f78978 100%);
        background-attachment: fixed;
    }

    /* Glassmorphism Containers */
    div[data-testid="stVerticalBlockBorderWrapper"] {
        background: rgba(255, 255, 255, 0.9) !important;
        backdrop-filter: blur(10px);
        border: 1px solid rgba(255, 255, 255, 0.2);
        border-radius: 1.2rem !important;
        box-shadow: 0 8px 32px 0 rgba(31, 38, 135, 0.1);
        padding: 1.5rem !important;
        margin-bottom: 1.5rem;
    }
    
    /* Text Colors */
    h1, h2, h3, h4, p, label, .stMarkdown {
        color: #1f2937 !important;
    }

    /* Modern Buttons */
    .stButton > button {
        border-radius: 0.8rem !important;
        border: none !important;
        background: white !important;
        color: #1f2937 !important;
        font-weight: 600 !important;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1) !important;
        transition: all 0.2s ease !important;
    }
    
    .stButton > button:hover {
        transform: translateY(-2px);
        box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.1) !important;
        background: #f9fafb !important;
    }


    /* Custom Highlight */
    .topic-highlight {
        background: #fef3c7;
        padding: 10px 15px;
        border-radius: 0.8rem;
        border-left: 6px solid #f59e0b;
        margin-bottom: 12px;
        color: #92400e !important;
    }

    /* Tabs Styling */
    .stTabs [data-baseweb="tab-list"] {
        gap: 10px;
        background-color: rgba(255, 255, 255, 0.3);
        padding: 5px;
        border-radius: 1rem;
    }

    .stTabs [data-baseweb="tab"] {
        background-color: transparent;
        border-radius: 0.8rem;
        padding: 10px 20px;
        color: #4b5563;
    }

    .stTabs [aria-selected="true"] {
        background-color: white !important;
        color: #1f2937 !important;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1) !important;
    }
    </style>
""", unsafe_allow_html=True)

@st.cache_resource
def get_history_mgr_v2(db_path):
    return HistoryManager(db_path)

db_path = os.path.join(os.getcwd(), "history.db")
history_mgr = get_history_mgr_v2(db_path)

@st.cache_data(ttl=3600, show_spinner=False)
def get_cached_video_info(url):
    """ฟังก์ชันแคชสำหรับ get_video_info เพื่อลดการเรียกเครือข่ายซ้ำ"""
    return get_video_info(url)

# กำหนดค่าเริ่มต้นให้กับ Session State
SESSION_DEFAULTS = {
    'all_results': [],
    'batch_processing': False,
    'preview_start_time': 0,
    'start_times': {},
    'active_preview_url': None,
    'should_autoplay': False,
    'seek_toggle': 0,
    'results_by_url': {},
    'processing_url': None,
    'paste_urls': "",
    'uploader_key': 0,
    'is_processing': False
}

for key, default_value in SESSION_DEFAULTS.items():
    if key not in st.session_state:
        st.session_state[key] = default_value

def reset_state():
    """ฟังก์ชันสำหรับล้างค่าทั้งหมดของ Session State อย่างปลอดภัย"""
    # ล้างค่าที่เฉพาะเจาะจงของแอปเป็นค่าเริ่มต้น
    for key, default_value in SESSION_DEFAULTS.items():
        if key == 'uploader_key':
            st.session_state[key] += 1  # เพิ่มค่าเพื่อบังคับให้ Widget เริ่มใหม่ (Reset Upload)
        else:
            st.session_state[key] = default_value
    
    # ล้างคีย์ที่สร้างขึ้นแบบไดนามิก (เช่น คีย์ rec_ ที่เกิดจากการค้นหา)
    for key in list(st.session_state.keys()):
        if key.startswith("rec_") or key.startswith("preview_path_"):
            del st.session_state[key]
    
    # ล้างพารามิเตอร์ URL หากทำได้
    try:
        st.query_params.clear()
    except Exception:
        pass
    
    # บังคับรีรันเพื่อให้หน้าจอกลับสู่สถานะเริ่มต้นทันที
    st.rerun()

# --- ระบบแสดงผลเบื้องต้น ---
# กำหนดค่าตัวแปรการโต้ตอบพื้นฐาน
urls_text = ""
process_urls = False
uploaded_file = None
process_file = False

# --- ระบบจำกัดการใช้รายวัน (Daily Usage Limit) ---
DAILY_LIMIT = 20
usage_count = history_mgr.get_today_usage_count()
remaining_uses = max(0, DAILY_LIMIT - usage_count)
is_limit_reached = usage_count >= DAILY_LIMIT

# --- เมนูข้าง (Sidebar) ---
with st.sidebar:
    st.header("⚙️ System Status")
    
    # แสดงโควตาการใช้งานรายวัน
    st.markdown(f"### 📊 โควตารายวัน ({usage_count}/{DAILY_LIMIT})")
    if is_limit_reached:
        st.error("🚫 วันนี้คุณใช้งานครบ 20 ครั้งแล้ว")
        st.caption("กรุณากลับมาใช้งานใหม่ในวันพรุ่งนี้ เพื่อช่วยประหยัดโควตา API ครับ")
    else:
        progress_val = min(1.0, usage_count / DAILY_LIMIT)
        st.progress(progress_val)
        st.info(f"เหลือสิทธิ์อีก **{remaining_uses}** ครั้งสำหรับวันนี้")

    st.divider()
    
    # ตัวบ่งชี้สถานะแบบง่าย
    if st.session_state.is_processing:
        st.status("⏳ กำลังประมวลผล...")
    else:
        st.success("✅ ระบบหลักพร้อมทำงาน")
    
    st.divider()
    
    # --- ส่วนตรวจสอบและจัดการระบบ (Diagnostics & Tools) ---
    with st.expander("🛠 ตรวจสอบระบบ (Diagnostics)"):
        from main import GEMINI_API_KEYS
        
        # 1. API Status
        if GEMINI_API_KEYS:
            st.success(f"✅ **Gemini AI**: พร้อมใช้งาน ({len(GEMINI_API_KEYS)} keys)")
        else:
            st.error("❌ **Gemini AI**: ไม่พบ API Key")
            
        st.caption("ระบบเสียง: **Gemini-Native Audio** (No Whisper)")
            
        st.divider()
        
        # 2. Cookie Vault (ตู้เซฟคุกกี้) - สำหรับแก้ปัญหา 403/Block
        st.markdown("#### 🍪 Cookie Vault (แก้ปัญหาโดนบล็อก)")
        st.caption("หากวิดีโอถูกบล็อก (403 Forbidden / Sign in required) ให้อัปโหลดไฟล์ `cookies.txt` ที่นี่")
        
        uploaded_cookie = st.file_uploader("อัปโหลด cookies.txt", type=['txt'], key="cookie_uploader")
        if uploaded_cookie:
            # ตรวจสอบว่าเป็นคุกกี้ของอะไร
            content = uploaded_cookie.getvalue().decode("utf-8")
            save_path = "cookies.txt" # Default
            
            if ".tiktok.com" in content:
                save_path = "tiktok_cookies.txt"
                st.info("ตรวจพบ: **TikTok Cookies**")
            elif ".youtube.com" in content or "youtube" in content:
                save_path = "youtube_cookies.txt"
                st.info("ตรวจพบ: **YouTube Cookies**")
            else:
                save_path = "PROJECT_COOKIES.txt"
                st.info("ตรวจพบ: **Generic Cookies**")
                
            # บันทึกไฟล์
            with open(save_path, "wb") as f:
                f.write(uploaded_cookie.getvalue())
            st.success(f"✅ บันทึกไฟล์ {save_path} สำเร็จ! (ลองกดประมวลผลใหม่ได้เลย)")
        
    
    if st.button("New Process (ล้างข้อมูล)", type="secondary", icon="🔄", use_container_width=True):
        reset_state()

# จัดการการคลิกที่รูปภาพตัวอย่าง (Clickable Thumbnail) ผ่าน Query Params
if "play_url" in st.query_params:
    target_play_url = st.query_params["play_url"]
    st.session_state.active_preview_url = target_play_url
    st.session_state.preview_start_time = 0
    st.session_state.seek_toggle += 1
    st.session_state.should_autoplay = True
    # ล้างพารามิเตอร์ URL เพื่อป้องกันการรันวนซ้ำเมื่อรีเฟรชเบราว์เซอร์
    try:
        st.query_params.clear()
    except: pass
    st.rerun()

# กำหนดค่าตัวแปรการโต้ตอบเบื้องต้นเพื่อให้เรียกใช้งานได้เสมอ
urls_text = ""
process_urls = False
uploaded_file = None
process_file = False

# ส่วนหัวข้อหลักและช่องกรอกข้อมูล
st.title("ระบบถอดเสียงวิดีโอด้วย AI")
st.write("รองรับ YouTube, TikTok, หรือไฟล์วิดีโอ")

# ส่วนรับข้อมูล (Input Section)
with st.container():
    tab1, tab2 = st.tabs(["🔗 วางลิงก์ (Paste Links)", "📁 อัปโหลดไฟล์ (Upload File)"])
    
    with tab1:
        with st.form("url_input_form"):
            urls_text = st.text_area(
                "วางลิงก์วิดีโอที่นี่ (แยกด้วยการขึ้นบรรทัดใหม่):", 
                placeholder="https://www.youtube.com/watch?v=...\nhttps://www.tiktok.com/@user/video/...",
                key="paste_urls"
            )
            process_urls = st.form_submit_button(
                "เริ่มประมวลผลลิงก์", 
                type="primary", 
                disabled=is_limit_reached,
                use_container_width=True
            )
        


    
    
    with tab2:
        with st.form("file_input_form"):
            uploaded_file = st.file_uploader(
                "อัปโหลดวิดีโอหรือเสียง", 
                type=["mp4", "mp3", "m4a", "wav", "mov", "avi"], 
                label_visibility="collapsed",
                key=f"uploader_{st.session_state.uploader_key}"
            )
            process_file = st.form_submit_button(
                "เริ่มประมวลผลไฟล์", 
                type="primary", 
                disabled=is_limit_reached,
                use_container_width=True
            )



# --- ส่วนเริ่มการประมวลผล (Processing) ---
# เมื่อผู้ใช้คลิกปุ่ม "Process Links" หรือ "Process File"
if process_urls or process_file:
    items_to_process = []
    
    if process_file and uploaded_file:
        uploaded_temp_path = os.path.join(tempfile.gettempdir(), f"upload_{uploaded_file.name}")
        with open(uploaded_temp_path, "wb") as f:
            f.write(uploaded_file.getbuffer())
        items_to_process.append((uploaded_temp_path, uploaded_file.name, True))
        st.session_state.active_preview_url = uploaded_temp_path
    
    if process_urls and urls_text.strip():
        raw_urls = [u.strip() for u in urls_text.split('\n') if u.strip()]
        for url in raw_urls:
            items_to_process.append((url, url, False))
    
    if items_to_process:
        # ใช้ระบบ ThreadPoolExecutor เพื่อประมวลผลวิดีโอหลายตัวพร้อมกัน (Parallel)
        total = len(items_to_process)
        
        with ThreadPoolExecutor(max_workers=min(len(items_to_process), 5)) as executor:
            future_to_item = {}
            for target_url, display_name, is_uploaded in items_to_process:
                # ใช้ระบบ Pipeline อัตโนมัติ (Audio -> Gemini Analysis) - เปิดการแยกเสียงพูด (Diarization) เป็นค่าเริ่มต้น
                future = executor.submit(process_video, target_url, diarize_mode=True)
                future_to_item[future] = (target_url, display_name, is_uploaded)
            
            for future in as_completed(future_to_item):
                target_url, display_name, is_uploaded = future_to_item[future]
                result_key = f"res_{target_url}"
                try:
                    # รับผลลัพธ์จากการประมวลผล
                    results = future.result()
                    if results:
                        # เก็บผลลัพธ์ลงใน session_state เพื่อแสดงผลบนหน้าจอ
                        st.session_state.results_by_url[result_key] = results
                        if not results.get('error'):
                            # บันทึกประวัติลงในฐานข้อมูล
                            entry = {
                                'title': results['video_title'],
                                'url': target_url if not is_uploaded else f"Uploaded: {display_name}",
                                'result_text': results['ai_analysis'] if results['is_audio_processed'] else results['ai_summary'],
                                'platform': results.get('platform')
                            }
                            history_mgr.save_to_history(entry)
                except Exception as e:
                    st.session_state.results_by_url[result_key] = {'error': str(e)}
        
        st.success(f"✅ ประมวลผลเสร็จสิ้นทั้งหมด {total} รายการ!")
        st.rerun()

# ================= ระบบแสดงตัวอย่างวิดีโอ (Instant Preview) =================
if urls_text.strip() or st.session_state.active_preview_url:
    # ตัดสินใจว่าจะใช้วิดีโอตัวไหนแสดงใน Preview
    preview_url = st.session_state.get('active_preview_url')
    
    # หากยังไม่ได้ระบุตัวอย่าง ให้เลือก URL แรกจากช่องกรอกข้อความเป็นค่าเริ่มต้น
    if not preview_url and urls_text.strip():
        urls = [u.strip() for u in urls_text.split('\n') if u.strip()]
        if urls:
            preview_url = urls[0]
            st.session_state.active_preview_url = preview_url
    
    if preview_url:
        st.markdown("### 📺 ตัวอย่างวิดีโอ")
        p_start = float(st.session_state.preview_start_time)
        
        # ตรวจสอบว่าเป็นพาธไฟล์ในเครื่องหรือไม่ (ไฟล์ที่อัปโหลด)
        is_local_file = os.path.exists(preview_url)
        
        # ตรวจสอบแพลตฟอร์ม (Platform)
        is_youtube = "youtube.com" in preview_url or "youtu.be" in preview_url
        is_tiktok = "tiktok.com" in preview_url
        is_facebook = "facebook.com" in preview_url or "fb.watch" in preview_url
        
        if is_local_file:
            # ไฟล์ที่อัปโหลด - ใช้ st.video พร้อมกำหนดเวลาเริ่มต้น
            st.markdown("**📁 ไฟล์ที่อัปโหลด (Uploaded File)**")
            
            # ใช้เทคนิคการซ้อน Layer 3 ชั้นและคีย์แบบไดนามิกเพื่อบังคับให้เบราว์เซอร์รีเฟรชเมื่อเวลาเปลี่ยน
            preview_container = st.empty()
            with preview_container:
                mod_toggle = st.session_state.seek_toggle % 3
                
                if mod_toggle == 0:
                    st.video(preview_url, start_time=p_start, autoplay=st.session_state.should_autoplay)
                elif mod_toggle == 1:
                    with st.container():
                        st.video(preview_url, start_time=p_start, autoplay=st.session_state.should_autoplay)
                else:
                    col_p = st.columns([1])[0]
                    with col_p:
                        st.video(preview_url, start_time=p_start, autoplay=st.session_state.should_autoplay)
            
            if p_start > 0:
                st.caption(f"⏩ กำลังเลื่อนไปยัง {format_time(p_start)}")
                
        elif is_tiktok or is_facebook:
            platform_label = "TikTok" if is_tiktok else "Facebook"
            st.markdown(f"**{platform_label} Video**")
            
            # Check if we already have a successful preview path in session state or cache
            import hashlib
            url_hash = hashlib.md5(preview_url.encode()).hexdigest()
            preview_key = f"preview_path_{url_hash}"
            local_preview_path = st.session_state.get(preview_key)
            
            # If not loaded, check if it exists in cache (temp) or download it automatically
            if not local_preview_path:
                temp_dir = tempfile.gettempdir()
                cached_path = os.path.join(temp_dir, f"preview_{url_hash}.mp4")
                if os.path.exists(cached_path):
                    local_preview_path = cached_path
                    st.session_state[preview_key] = local_preview_path
                else:
                    # ดาวน์โหลดในเบื้องหลังโดยอัตโนมัติ (จะแสดง Spinner ของ Streamlit)
                    with st.status(f"📥 กำลังโหลดตัวอย่าง {platform_label} เพื่อรองรับการเลื่อนเวลา...", expanded=False):
                        st.write("กำลังดึงข้อมูลวิดีโอ...")
                        local_preview_path = download_video_preview(preview_url)
                        if local_preview_path:
                            st.session_state[preview_key] = local_preview_path
                            # No st.rerun() here - let it continue to the next block while in the same script run

            if local_preview_path and os.path.exists(local_preview_path):
                # ใช้ตัวเล่นวิดีโอมาตรฐานกับไฟล์ในเครื่องเพื่อให้เลื่อนเวลาได้แม่นยำ (Seeking works perfectly!)
                preview_container = st.empty()
                with preview_container:
                    mod_toggle = st.session_state.get('seek_toggle', 0) % 3
                    
                    if mod_toggle == 0:
                        st.video(local_preview_path, start_time=p_start, autoplay=st.session_state.should_autoplay)
                    elif mod_toggle == 1:
                        with st.container():
                            st.video(local_preview_path, start_time=p_start, autoplay=st.session_state.should_autoplay)
                    else:
                        col_p = st.columns([1])[0]
                        with col_p:
                            st.video(local_preview_path, start_time=p_start, autoplay=st.session_state.should_autoplay)
                
                if p_start > 0:
                    st.caption(f"⏩ กำลังเลื่อนไปยัง {format_time(p_start)}")
            else:
                # ทางเลือกสุดท้าย: ใช้การฝังวิดีโอ (Embed) หากดาวน์โหลดล้มเหลว (สำหรับ TikTok)
                if is_tiktok:
                    import re
                    video_id_match = re.search(r'/video/(\d+)', preview_url)
                    if video_id_match:
                        video_id = video_id_match.group(1)
                        embed_url = f"https://www.tiktok.com/embed/v2/{video_id}"
                        st.components.v1.iframe(embed_url, height=700)
                        if p_start > 0:
                            st.warning("⚠️ TikTok Embed ไม่รองรับการกระโดดไปยัง timestamp (Download failed)")
                    else:
                        st.info(f"🔗 [เปิดดู TikTok]({preview_url})")
                else:
                    st.info(f"🔗 [เปิดดูวิดีโอ]({preview_url})")
                
        elif is_youtube:
            # การแสดงตัวอย่าง YouTube (ใช้โค้ดดั้งเดิม)
            preview_container = st.empty()
            with preview_container:
                # พารามิเตอร์ซิงค์สำหรับ YouTube เพื่อบังคับให้เบราว์เซอร์รีเฟรช
                sep = "&" if "?" in preview_url else "?"
                sync_url = f"{preview_url}{sep}v_sync={st.session_state.seek_toggle}"

                # เทคนิคการซ้อน Layer 3 ชั้นเพื่อบังคับให้ Streamlit เห็นว่าเป็นคอมโพเนนต์ใหม่
                mod_toggle = st.session_state.seek_toggle % 3
                if mod_toggle == 0:
                    st.video(sync_url, start_time=p_start, autoplay=st.session_state.should_autoplay)
                elif mod_toggle == 1:
                    with st.container():
                        st.video(sync_url, start_time=p_start, autoplay=st.session_state.should_autoplay)
                else:
                    col_p = st.columns([1])[0]
                    with col_p:
                        st.video(sync_url, start_time=p_start, autoplay=st.session_state.should_autoplay)
            
            if p_start > 0:
                st.caption(f"⏩ เริ่มต้นที่ {format_time(p_start)}")
        else:
            # แพลตฟอร์มอื่นๆ (Facebook, Instagram ฯลฯ)
            # ลองใช้ st.video() พร้อมระบุเวลาเริ่มต้น
            try:
                preview_container = st.empty()
                with preview_container:
                    mod_toggle = st.session_state.seek_toggle % 3
                    if mod_toggle == 0:
                        st.video(preview_url, start_time=p_start, autoplay=st.session_state.should_autoplay)
                    elif mod_toggle == 1:
                        with st.container():
                            st.video(preview_url, start_time=p_start, autoplay=st.session_state.should_autoplay)
                    else:
                        col_p = st.columns([1])[0]
                        with col_p:
                            st.video(preview_url, start_time=p_start, autoplay=st.session_state.should_autoplay)
                
                if p_start > 0:
                    st.caption(f"⏩ เริ่มต้นที่ {format_time(p_start)}")
            except:
                # กรณีสำรอง: แสดงลิงก์วิดีโอ
                st.info(f"🔗 [คลิกเพื่อดูวิดีโอ]({preview_url})")
                st.caption("แพลตฟอร์มนี้ไม่สามารถแสดง preview ได้โดยตรง กรุณากดลิงก์ด้านบน")


if st.session_state.results_by_url:
    st.divider()
    st.markdown("## 🎬 ผลการวิเคราะห์วิดีโอ")

# ฟังก์ชันเสริม: แสดงส่วนข้อมูลวิดีโอรายตัว (Individual Video Fragment)
def video_fragment(target_url, idx, is_uploaded=False, uploaded_name=None):
    # สถานะข้อมูลเฉพาะของ URL นี้
    result_key = f"res_{target_url}"
    
    # ส่วนแสดงผลลัพธ์ (Results Container)
    if result_key not in st.session_state.results_by_url:
        st.info(f"⏳ กำลังรอประมวลผล: {uploaded_name if is_uploaded else target_url[:50]+'...'}")
        return

    res = st.session_state.results_by_url[result_key]
    
    # กรณีเกิดข้อผิดพลาด (ERROR CASE)
    if res.get('error'):
        with st.container(border=True):
            err = res['error']
            if 'API_QUOTA_EXCEEDED' in err:
                st.error(f"❌ **API Quota เต็ม (โควตาหมดชั่วคราว)**")
                st.warning(f"รายละเอียด: {err.split(':', 1)[1] if ':' in err else err}")
            elif "tiktok" in str(target_url).lower() or "tiktok" in str(err).lower():
                st.error(f"❌ **TikTok Error**: {err}")
                st.info("💡 **คำแนะนำสำหรับ TikTok**:\n1. ตรวจสอบว่ามีไฟล์ `tiktok_cookies.txt` หรือยัง\n2. ลองเปลี่ยน IP (ใช้ VPN หรือ Hotspot)\n3. TikTok บล็อกการเข้าถึงบ่อยเป็นปกติครับ")
            else:
                st.error(f"❌ **Error**: {err}")
            
            if st.button("🔄 ล้างและลองใหม่", key=f"retry_{idx}"):
                del st.session_state.results_by_url[result_key]
                st.rerun()
        return

    # ส่วนติดต่อผู้ใช้ (UI) สำหรับวิดีโอนี้
    with st.container(border=True):
        st.markdown(f"### ✅ {res.get('video_title', 'ผลลัพธ์')}")
        
        # ข้อมูลพื้นฐานวิดีโอ (Duration, Transcript Stats)
        col_meta1, col_meta2, col_meta3 = st.columns(3)
        with col_meta1:
            duration = res.get('duration_fmt', '00:00:00')
            st.metric("⏱️ ความยาว", duration)
        with col_meta2:
            full_text = res.get('full_text', '')
            word_count = len(full_text.split()) if full_text else 0
            st.metric("📝 จำนวนคำ", f"{word_count:,}")
        with col_meta3:
            speaker_count = res.get('speaker_count', 0)
            if speaker_count > 0:
                st.metric("🎤 ผู้พูด", f"{speaker_count} คน")
            else:
                st.metric("🎤 ผู้พูด", "ไม่ระบุ")
        
        # แสดงแหล่งที่มาของการถอดเสียงเพื่อความโปร่งใส
        source = res.get('transcription_source', 'Unknown')
        st.caption(f"🔍 แหล่งข้อมูลการถอดเสียง: **{source}**")

    # Summary (Always visible at the top)
    with st.container(border=True):
        st.markdown("#### 📝 สรุปเนื้อหาสำคัญ")
        st.write(res.get('ai_summary', "ไม่มีข้อมูลสรุป"))

    # หัวข้อสำคัญ (แบบย่อตามคำขอ: เวลา + ชื่อหัวข้อ + วิดีโอแนะนำเท่านั้น)
    if res.get('ai_topics'):
        st.markdown("#### 📌 Topics")
        for t_idx, topic in enumerate(res.get('ai_topics', [])):
            ts_match = re.search(r'\[(\d{1,2}:\d{2}(?::\d{2})?(?:\.\d+)?)\]', topic)
            ts_str = ts_match.group(1) if ts_match else None
            topic_clean = topic.replace(f"[{ts_str}]", "") if ts_str else topic
            topic_clean = re.sub(r'^[\-\*\d\.\s]+', '', topic_clean).strip()
            
            # แยกชื่อหัวข้อและรายละเอียด (Split Title/Description)
            parts = topic_clean.split(":", 1)
            t_title = parts[0].strip()
            t_desc = parts[1].strip() if len(parts) > 1 else ""
            
            if not t_title: continue

            with st.container(border=True):
                col_t1, col_t2 = st.columns([0.25, 0.75])
                with col_t1:
                    if ts_str:
                        # Normalize to HH:MM:SS
                        sec_val = parse_timestamp_to_seconds(ts_str)
                        if sec_val is not None:
                            ts_display = format_time(sec_val)
                        else:
                            ts_display = ts_str

                        if st.button(f"🕒\n{ts_display}", key=f"ts_{idx}_{t_idx}_{ts_str}", use_container_width=True):
                            seconds = parse_timestamp_to_seconds(ts_str)
                            # Direct-Sync: ลบการถอยหลัง 2 วินาทีออก เพื่อความแม่นยำระดับเฟรมตามผู้ใช้ต้องการ
                            st.session_state.preview_start_time = float(seconds)
                            st.session_state.active_preview_url = target_url
                            st.session_state.seek_toggle += 1
                            st.session_state.should_autoplay = True
                            st.rerun()
                    else: st.write("📌")
                
                with col_t2:
                    st.markdown(f"**{t_title}**")
                    if t_desc:
                        st.write(t_desc)
                    
                    # ตรรกะการแสดงวิดีโอที่เกี่ยวข้องด้วย st.expander
                    rec_key = f"rec_{idx}_{t_idx}"
                    pushed_vids = res.get('related_recommendations', {}).get(topic)
                    display_list = st.session_state.get(rec_key, pushed_vids)

                    with st.expander("🔗 วิดีโอที่เกี่ยวข้อง", expanded=False):
                        if not display_list:
                            if st.button("🔍 ค้นหาวิดีโอที่เกี่ยวข้อง", key=f"btn_{rec_key}"):
                                with st.spinner("Searching..."):
                                    search_term = extract_meaningful_search_query(t_title)
                                    if search_term:
                                        display_list = search_videos(search_term, max_results=3)
                                        st.session_state[rec_key] = display_list
                                        st.rerun()
                        
                        if display_list:
                            # แสดงวิดีโอแนะนำในกรอบที่มีเส้นขอบภายในหัวข้อ
                            with st.container(border=True):
                                cols = st.columns(len(display_list))
                                for c_idx, v in enumerate(display_list):
                                    with cols[c_idx]:
                                        if v.get('thumbnail'):
                                            # ใช้ Markdown HTML เพื่อทำให้รูปภาพสามารถคลิกได้
                                            thumbnail_html = f'''
                                                <a href="/?play_url={v["url"]}" target="_self" style="text-decoration: none;">
                                                    <img src="{v["thumbnail"]}" style="width: 100%; border-radius: 8px; cursor: pointer; transition: transform 0.2s;" 
                                                         onmouseover="this.style.transform='scale(1.05)'" 
                                                         onmouseout="this.style.transform='scale(1.0)'">
                                                </a>
                                            '''
                                            st.markdown(thumbnail_html, unsafe_allow_html=True)
                                        else: st.write("📺")
                                        
                                        d_title = f"▶️ {v['title'][:40]}..." if len(v['title']) > 40 else f"▶️ {v['title']}"
                                        if st.button(d_title, key=f"play_{rec_key}_{c_idx}", use_container_width=True):
                                            st.session_state.active_preview_url = v['url']
                                            st.session_state.preview_start_time = 0
                                            st.session_state.seek_toggle += 1
                                            st.session_state.should_autoplay = True
                                            st.rerun()

    # บทบรรยาย (Transcript)
    with st.expander("📜 ดูบทบรรยายฉบับเต็ม (View Full Transcript)", expanded=False):
        full_text = res.get('full_text', "")
        
        # ตรวจสอบว่าบทบรรยายว่างหรือสั้นเกินไปหรือไม่
        if not full_text or len(full_text.strip()) < 50:
            st.warning("⚠️ ไม่พบ Transcript หรือข้อมูลสั้นเกินไป")
            st.info("""
            **สาเหตุที่เป็นไปได้:**
            - 🔇 ไฟล์ไม่มีเสียงพูด (เป็นเพลง หรือเสียงพื้นหลังเท่านั้น)
            - 🎤 เสียงไม่ชัดพอให้ AI ถอดเสียงได้
            - ⏱️ ไฟล์ยาวเกินไป ทำให้ AI ประมวลผลไม่ทัน
            - 🤖 AI ไม่สามารถถอดเสียงได้ (ลองอัปโหลดใหม่)
            
            **วิธีแก้:**
            - ตรวจสอบว่าไฟล์มีเสียงพูดจริงหรือไม่
            - ลองเพิ่มระดับเสียง (volume) ของไฟล์
            - แบ่งคลิปยาวๆ เป็นส่วนสั้นๆ (ไม่เกิน 1 ชั่วโมง)
            - ลองอัปโหลดใหม่อีกครั้ง
            """)
            
            # แสดงข้อความดิบหากมีข้อมูล (สำหรับการตรวจสอบหาข้อผิดพลาด)
            if full_text and len(full_text.strip()) > 0:
                with st.expander("🔍 ดูข้อมูลดิบ (Debug)", expanded=False):
                    st.text(full_text[:500])
        else:
            # Split and bold metadata for better readability
            # ระบุว่าเวลาใดเป็นจุดเริ่มต้นของหัวข้อ (แปลงเป็นวินาทีเพื่อการเปรียบเทียบที่แม่นยำ)
            topic_seconds_set = set()
            for topic_str in res.get('ai_topics', []):
                ts_match = re.search(r'\[(\d{1,2}:\d{2}(?::\d{2})?(?:\.\d+)?)\]', topic_str)
                if ts_match:
                    try:
                        sec = parse_timestamp_to_seconds(ts_match.group(1))
                        topic_seconds_set.add(sec)
                    except: pass

            lines = [l.strip() for l in full_text.split('\n') if l.strip()]
            for line in lines:
                match = re.match(r'^(\[([\d:\.]+)\](?:\s*(?:TO|To|to)\s*\[[\d:\.]+\])?\s*[^:]+:)(.*)', line, re.IGNORECASE)
                if match:
                    meta, ts_time, content = match.groups()
                    
                    # ตรวจสอบว่าบรรทัดนี้เป็นจุดเริ่มต้นของหัวข้อหรือไม่ (Fuzzy match 0.5 วินาที เพื่อรองรับความคลาดเคลื่อนระดับมิลลิวินาที)
                    is_topic_start = False
                    try:
                        line_sec = parse_timestamp_to_seconds(ts_time)
                        if line_sec is not None and any(abs(line_sec - t_sec) < 0.5 for t_sec in topic_seconds_set):
                            is_topic_start = True
                    except: pass
                    
                    if is_topic_start:
                        # PASTEL HIGHLIGHT STYLE (Vivid for visibility)
                        highlight_style = "background-color: #ffd54f; padding: 4px 8px; border-radius: 6px; border-left: 5px solid #ff6f00; color: black; margin-bottom: 4px;"
                        st.markdown(f'<div style="{highlight_style}"><span style="font-weight:bold;">{meta}</span> {content}</div>', unsafe_allow_html=True)
                    else:
                        st.write(line)
                else:
                    st.write(line)



# ขั้นตอนการทำงานหลักของแอป (Main App Flow)
# เตรียมรายการ URL หรือไฟล์
urls_to_show = []
if urls_text.strip():
    urls_to_show = [u.strip() for u in urls_text.split('\n') if u.strip()]

# ส่วนแสดงผลหลัก (Display Area)
if uploaded_file or urls_to_show or st.session_state.results_by_url:
    st.divider()
    
    # แสดงรายการที่กำลังประมวลผลอยู่ (หากมี)
    if uploaded_file:
        uploaded_temp_path = os.path.join(tempfile.gettempdir(), f"upload_{uploaded_file.name}")
        st.markdown("### 📁 ไฟล์วิดีโอ (File)")
        video_fragment(uploaded_temp_path, 0, is_uploaded=True, uploaded_name=uploaded_file.name)
        st.divider()

    if urls_to_show:
        st.markdown("### 🔗 รายการลิงก์ (Links)")
        for i, url in enumerate(urls_to_show):
            video_fragment(url, i + (1 if uploaded_file else 0))

# ส่วนท้ายหน้าเพจ (Footer)
st.divider()

if st.session_state.results_by_url:
    # CSS เพิ่มเติมสำหรับปุ่มที่มองเห็นได้แต่ไม่เด่นเกินไป
    st.markdown("""
        <style>
        div.stButton > button:first-child[kind="secondary"] {
            border: 1px solid #d1d5db;
            color: #4b5563;
        }
        div.stButton > button:first-child[kind="secondary"]:hover {
            border-color: #3b82f6;
            color: #3b82f6;
            background-color: #eff6ff;
        }
        </style>
    """, unsafe_allow_html=True)
    
    st.button("เริ่มการทำงานใหม่ (New Process)", type="secondary", use_container_width=True, on_click=reset_state)

st.caption("Adaptive Learning Assistant")

# ล้างสถานะการเล่นอัตโนมัติหลังจากโหลดข้อมูลหน้าครบถ้วนแล้ว
st.session_state.should_autoplay = False

