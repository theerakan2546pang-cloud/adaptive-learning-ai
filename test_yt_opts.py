import yt_dlp
import os

url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
# Test with string instead of list
ydl_opts = {
    'quiet': True,
    'skip_download': True,
    'cookiesfrombrowser': 'safari', # String instead of ['safari']
}

print("Testing yt-dlp library call with cookiesfrombrowser='safari'...")
try:
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)
        print(f"SUCCESS: Extracted title: {info.get('title')}")
except Exception as e:
    print(f"FAILED with cookiesfrombrowser='safari': {repr(e)}")

# Test with list to see if it causes AssertionError in download
ydl_opts_list = {
    'format': 'bestaudio/best',
    'outtmpl': 'test_download_opts',
    'quiet': False,
    'cookiesfrombrowser': ['safari'],
    'postprocessors': [{
        'key': 'FFmpegExtractAudio',
        'preferredcodec': 'mp3',
        'preferredquality': '128',
    }],
}
print("\nTesting yt-dlp library call with config including post-processors...")
try:
    with yt_dlp.YoutubeDL(ydl_opts_list) as ydl:
        ydl.download([url])
    print("SUCCESS: Download completed.")
except Exception as e:
    print(f"FAILED: {repr(e)}")
    import traceback
    traceback.print_exc()
