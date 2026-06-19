"""
E2E conversation tests — verifies RAG citations, multi-turn, GPS, wardrobe search.
"""
import requests
import json
import sys
import time

BASE = "http://localhost:5001/api/chat"
SESSION = "e2e-" + str(int(time.time()))
USER_ID = "10000005"
GPS = {"latitude": 34.2222, "longitude": 108.9450}
HEADERS = {"Content-Type": "application/json", "X-Session-ID": SESSION}


def safe_str(v):
    try:
        s = str(v)
        s.encode('gbk')
        return s[:200]
    except (UnicodeEncodeError, UnicodeDecodeError):
        return str(v).encode('ascii', errors='replace').decode('ascii')[:200]


def chat(message):
    body = {
        "user_id": USER_ID, "message": message, "session_id": SESSION,
        "latitude": GPS["latitude"], "longitude": GPS["longitude"],
    }
    start = time.time()
    r = requests.post(BASE, json=body, headers=HEADERS, timeout=180)
    elapsed = time.time() - start
    return r.json(), elapsed


def main():
    results = []

    # ===== Turn 1: RAG + GPS =====
    print("--- Turn 1: RAG + GPS ---")
    data, t = chat("帮我推荐一套参加户外婚礼的穿搭，我在西安")
    print(f"  Latency: {t:.1f}s")

    citations = data.get("citations", [])
    city = data.get("city", "")
    city_src = data.get("citySource", "")
    reply = data.get("reply", "")

    print(f"  Citations: {len(citations)}")
    for c in citations[:3]:
        print(f"    - {safe_str(c.get('title',''))}: {safe_str(c.get('content',''))[:60]}")

    print(f"  City: {safe_str(city)} (source: {city_src})")
    print(f"  Intent: {data.get('intent','')}")

    has_citations = len(citations) > 0
    has_reply = len(reply) > 100
    has_wedding = "婚礼" in reply or "户外" in reply
    has_city = bool(city)

    results.append(("RAG citations", has_citations))
    results.append(("Reply length", has_reply))
    results.append(("Wedding context", has_wedding))
    results.append(("City resolved", has_city))

    # ===== Turn 2: Multi-turn preference =====
    print("\n--- Turn 2: Multi-turn (bright preference) ---")
    data2, t2 = chat("太素了吧，有没有亮色一点的搭配？我喜欢鲜艳的风格")
    print(f"  Latency: {t2:.1f}s")
    reply2 = data2.get("reply", "")

    diff_from_t1 = reply != reply2
    has_bright = "鲜艳" in reply2 or "亮" in reply2 or "色彩" in reply2 or "明亮" in reply2

    results.append(("Different from T1", diff_from_t1))
    results.append(("Bright preference addressed", has_bright))
    print(f"  Diff reply: {diff_from_t1}, Bright ref: {has_bright}")

    # ===== Turn 3: Style continuity =====
    print("\n--- Turn 3: Style continuity ---")
    data3, t3 = chat("那鞋子换成休闲款吧")
    print(f"  Latency: {t3:.1f}s")
    reply3 = data3.get("reply", "")

    has_shoe = "鞋" in reply3
    has_casual = "休闲" in reply3

    results.append(("Shoe reference", has_shoe))
    results.append(("Casual style", has_casual))
    print(f"  Shoe ref: {has_shoe}, Casual: {has_casual}")

    # Summary
    print(f"\n{'='*50}")
    passed = sum(1 for _, ok in results if ok)
    total = len(results)
    for name, ok in results:
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}")
    print(f"  Result: {passed}/{total}")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
