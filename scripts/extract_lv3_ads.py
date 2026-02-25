#!/usr/bin/env python3
"""Extract LV3 Anzeigen (ads) from PDF pages using Gemini Vision API."""
import base64, json, os, subprocess, sys, time, urllib.request

GEMINI_KEY = os.environ["GEMINI_API_KEY"]
PDF = "telc-b1-pruefungsbuch.pdf"
OUT = "data/lv3_ads.json"

# Exam name → ads page number (page AFTER the LV3 questions page)
EXAM_ADS_PAGES = {
    "PETRA": 6, "EVA1": 19, "SOPHIE": 34, "NADIA2": 47,
    "NICOLE": 60, "ANDREAS": 73, "ANNIKA3": 87, "IRIS1": 100,
    "CAROLINA": 126, "VERA": 139, "JENNIFER": 152, "ANDREAS2": 163,
    "THOMAS": 174, "TAMARA": 187, "JAN": 200, "VIKTOR": 213,
}

PROMPT = """This is a page from a German telc B1 exam (Leseverstehen Teil 3) containing Anzeigen (classified ads) labeled a) through l).

Extract ALL ads with their exact German text. Return ONLY a JSON array like:
[
  {"letter": "a", "text": "exact German text of ad a..."},
  {"letter": "b", "text": "exact German text of ad b..."},
  ...
]

Rules:
- Extract ALL ads (usually a through l, 10-12 ads)
- Keep the EXACT German text, including phone numbers, addresses, prices
- Do NOT translate or modify the text
- Include line breaks as spaces
- Return ONLY valid JSON, no markdown fences"""


def extract_ads_from_page(page_num: int) -> list:
    """Convert PDF page to image and send to Gemini Vision."""
    # Convert page to JPEG
    tmp = f"/tmp/lv3_page_{page_num}.jpg"
    subprocess.run(
        ["pdftoppm", "-jpeg", "-f", str(page_num), "-l", str(page_num),
         "-r", "250", PDF, f"/tmp/lv3_page_{page_num}"],
        capture_output=True
    )
    # pdftoppm adds page suffix
    import glob
    files = glob.glob(f"/tmp/lv3_page_{page_num}*.jpg")
    if not files:
        print(f"  ERROR: No image generated for page {page_num}")
        return []
    img_path = files[0]

    with open(img_path, "rb") as f:
        img_b64 = base64.b64encode(f.read()).decode()

    body = json.dumps({
        "contents": [{"parts": [
            {"inlineData": {"mimeType": "image/jpeg", "data": img_b64}},
            {"text": PROMPT}
        ]}],
        "generationConfig": {"temperature": 0.1}
    }).encode()

    req = urllib.request.Request(
        f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={GEMINI_KEY}",
        data=body,
        headers={"Content-Type": "application/json"}
    )

    for attempt in range(3):
        try:
            resp = urllib.request.urlopen(req, timeout=90)
            result = json.loads(resp.read())
            text = result["candidates"][0]["content"]["parts"][0]["text"]
            # Parse JSON from response
            text = text.strip()
            if text.startswith("```"):
                text = text.split("\n", 1)[1].rsplit("```", 1)[0]
            ads = json.loads(text)
            return ads
        except Exception as e:
            print(f"  Attempt {attempt+1} failed: {e}")
            if attempt < 2:
                time.sleep(3 * (attempt + 1))
    return []


def main():
    all_ads = {}
    for exam, page in sorted(EXAM_ADS_PAGES.items(), key=lambda x: x[1]):
        print(f"Extracting {exam} (page {page})...", flush=True)
        ads = extract_ads_from_page(page)
        print(f"  → {len(ads)} ads extracted", flush=True)
        all_ads[exam] = ads
        time.sleep(1)  # Rate limit

    with open(OUT, "w") as f:
        json.dump(all_ads, f, ensure_ascii=False, indent=2)
    print(f"\nSaved to {OUT}")

    # Summary
    total = sum(len(v) for v in all_ads.values())
    missing = [k for k, v in all_ads.items() if len(v) < 10]
    print(f"Total ads: {total} across {len(all_ads)} exams")
    if missing:
        print(f"WARNING: Exams with <10 ads: {missing}")


if __name__ == "__main__":
    main()
