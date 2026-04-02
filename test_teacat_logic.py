import httpx
from pathlib import Path
import json

def test_chaturbate_ajax(username):
    url = f"https://chaturbate.com/get_edge_hls_url_ajax/"
    headers = {
        "X-Requested-With": "XMLHttpRequest",
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Referer": f"https://chaturbate.com/{username}/",
        "Content-Type": "application/x-www-form-urlencoded",
    }
    
    # 建立一個臨時的 CookieDict
    cookies = {}
    cookie_path = Path("streamer_cookies.txt")
    if cookie_path.exists():
        with open(cookie_path, "r") as f:
            for line in f:
                if line.startswith("#") or not line.strip():
                    continue
                parts = line.strip().split("\t")
                if len(parts) >= 7:
                    # domain, flag, path, secure, expires, name, value
                    cookies[parts[5]] = parts[6]
    
    data = {
        "room_slug": username,
        "bandwidth": "high",
    }
    
    print(f"[*] Sending AJAX request to {url} for {username}...")
    
    with httpx.Client(headers=headers, cookies=cookies, timeout=10.0) as client:
        try:
            response = client.post(url, data=data)
            print(f"[*] Response Status: {response.status_code}")
            
            if response.status_code == 200:
                result = response.json()
                print(f"[+] Success! Result: {json.dumps(result, indent=2)}")
                if result.get("url"):
                    print(f"\n[!!!] FOUND M3U8 URL: {result['url']}")
                else:
                    print(f"[!] No URL found in JSON response. (Is the streamer actually live?)")
            else:
                print(f"[-] Request failed: {response.text}")
                
        except Exception as e:
            print(f"[!] Error: {str(e)}")

if __name__ == "__main__":
    test_chaturbate_ajax("katkittykate")
