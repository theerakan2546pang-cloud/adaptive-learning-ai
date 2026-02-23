import yt_dlp
from yt_dlp.networking.impersonate import ImpersonateTarget

url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
ydl_opts_api = {
    'quiet': True,
    'skip_download': True,
    # Use ImpersonateTarget object explicitly
    'impersonate': ImpersonateTarget(client='chrome', os='macos', os_version='14', version='131'),
}

print("Testing yt-dlp with ImpersonateTarget(client='chrome', os='macos', os_version='14', version='131')...")
try:
    with yt_dlp.YoutubeDL(ydl_opts_api) as ydl:
        ydl.extract_info(url, download=False)
    print("SUCCESS: ImpersonateTarget object worked!")
except Exception as e:
    print(f"FAILED with ImpersonateTarget object: {repr(e)}")
