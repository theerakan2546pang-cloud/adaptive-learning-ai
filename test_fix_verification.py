import sys
import os

# Add current directory to path
sys.path.append(os.getcwd())

from utils import download_video_preview

# Use a sample TikTok URL
url = "https://www.tiktok.com/@khaby.lame/video/7403482596954213665"

print(f"Testing download_video_preview for: {url}")
try:
    # We don't necessarily need it to succeed in downloading (which might fail due to network/IP),
    # we just need to verify that it doesn't throw NameError: ImpersonateTarget
    path = download_video_preview(url)
    print(f"Result path: {path}")
    print("SUCCESS: No NameError occurred.")
except NameError as e:
    print(f"FAILED: NameError still occurs: {e}")
    sys.exit(1)
except Exception as e:
    # Other exceptions are fine for this test as they aren't the NameError we're fixing
    print(f"INFO: Caught other exception (expected if download fails): {e}")
    print("SUCCESS: No NameError occurred.")
