import yt_dlp
from yt_dlp.networking.impersonate import ImpersonateTarget
import traceback

# User provided problematic video
url = "https://www.youtube.com/watch?v=pNoPMnL2T4k" 

targets = [
    ("Chrome/Mac", ImpersonateTarget(client='chrome', os='macos', os_version='15', version='133')),
    ("Chrome/Win", ImpersonateTarget(client='chrome', os='windows', os_version='10', version='131')),
    ("Safari/Mac", ImpersonateTarget(client='safari', os='macos', os_version='15', version='18.0')),
]

print(f"--- DIAGNOSING 403 BLOCKS FOR: {url} ---")

for name, target in targets:
    print(f"\n🧪 Testing Target: {name}")
    opts = {
        'quiet': True,
        'impersonate': target,
        'skip_download': True, # Just extract info to trigger HTTP check
    }
    
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
            print(f"   ✅ SUCCESS! Title: {info.get('title')}")
            break # Stop if one works
    except Exception as e:
        err = str(e)
        if "403" in err:
            print(f"   ❌ BLOCKED (403 Forbidden)")
        elif "Sign in" in err:
            print(f"   ⚠️  SIGN IN REQUIRED (Age/Premium)")
        else:
            print(f"   ⚠️  FAILED: {err[:100]}...")

print("\n--- DIAGNOSTIC COMPLETE ---")
