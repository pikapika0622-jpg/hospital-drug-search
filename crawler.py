import os
import re
import json
import argparse
import asyncio
import urllib.parse
import requests
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

REAL_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"

HOSPITAL_CATALOG = [
    {"id": "ntuh", "name": "台大醫院", "mode": "auto", "url": "https://www.ntuh.gov.tw/phr/Fpage.action?muid=2077&fid=1939"},
    {"id": "tptzuchi", "name": "台北慈濟醫院", "mode": "auto", "url": "https://tp-his.tzuchi-healthcare.org.tw/DrugPharm/ComPharmacopoeia/AllInOne/Med_Search_AllInOne.aspx"},
    {"id": "edah", "name": "義大醫院", "mode": "auto", "url": "https://dept.edah.org.tw/ph/asp/search.asp?TAB=1&orgby=ED"},
    {"id": "csh", "name": "中山醫學大學附設醫院", "mode": "auto", "url": "https://www.csh.org.tw/DrugQuery/NewDrugQuery.aspx"},
    {"id": "vghks", "name": "高雄榮民總醫院", "mode": "auto", "url": "https://www2.vghks.gov.tw/DIWEB/DIQuerySql.jsp"},
    {"id": "vghtpe", "name": "臺北榮民總醫院", "mode": "manual", "reason": "需圖形驗證碼", "url": "https://www7.vghtpe.gov.tw/home/index"},
    {"id": "nckuh", "name": "成大醫院", "mode": "manual", "reason": "需圖形驗證碼", "url": "https://web.hosp.ncku.edu.tw/pharmacy/"},
    {"id": "tsgh", "name": "三軍總醫院", "mode": "manual", "reason": "Cloudflare 防護", "url": "https://wwwv.tsgh.ndmctsgh.edu.tw/unit/10026/25855"},
    {"id": "mmh", "name": "馬偕紀念醫院", "mode": "manual", "reason": "限台灣IP連線", "url": "https://mcloud.mmh.org.tw/DMZDrugFormB817/DrugQuery.html"},
    {"id": "tzuchi", "name": "花蓮慈濟醫院", "mode": "manual", "reason": "限台灣IP連線", "url": "https://hldrug.tzuchi.com.tw/tchw/IphqryChinese/DesktopModules/WesternMedicine/Pill_Search.aspx?Hospital=HL"},
    {"id": "kmuh", "name": "高雄醫學大學附設中和紀念醫院", "mode": "manual", "reason": "限台灣IP連線", "url": "https://www.kmuh.org.tw/web/kmuhdept/pill/"},
    {"id": "cgh", "name": "國泰醫院", "mode": "manual", "reason": "限台灣IP連線", "url": "https://www.cgh.org.tw/ec99/rwd112/category.asp?category_id=15"},
    {"id": "femh", "name": "亞東紀念醫院", "mode": "manual", "reason": "藥理分類目錄頁", "url": "https://www.e-pharm.info/safety/drug-information/femh-formulary"},
    {"id": "vghtc", "name": "臺中榮民總醫院", "mode": "manual", "reason": "需從院網進入", "url": "https://www.vghtc.gov.tw/UnitPage/UnitContentView?WebMenuID=35069f8d-2ef4-4f8a-8648-f0ef5fca7fd7&UnitDefaultTemplate=1"},
    {"id": "skh", "name": "新光醫院", "mode": "manual", "reason": "需從院網進入", "url": "https://www.skh.org.tw/"},
    {"id": "cgmh", "name": "林口長庚紀念醫院", "mode": "manual", "reason": "舊連結待更新", "url": "https://www.cgmh.org.tw/"},
    {"id": "chimei", "name": "奇美醫院", "mode": "manual", "reason": "舊連結待更新", "url": "https://www.chimei.org.tw/"},
    {"id": "cch", "name": "彰化基督教醫院", "mode": "manual", "reason": "舊連結待更新", "url": "https://www.cch.org.tw/"},
    {"id": "cmuh", "name": "中國醫藥大學附設醫院", "mode": "manual", "reason": "舊連結待更新", "url": "https://www.cmuh.cmu.edu.tw/"},
]

def extract_brand_key(brand_en: str) -> str:
    match = re.search(r"[A-Za-z][A-Za-z0-9\-]*", brand_en or "")
    return match.group(0).capitalize() if match else "Unknown"

async def crawl_all(keyword: str):
    records = []
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-blink-features=AutomationControlled"]
        )
        context = await browser.new_context(
            user_agent=REAL_UA,
            viewport={"width": 1280, "height": 800},
            ignore_https_errors=True
        )

        # 1. 台大醫院
        try:
            page = await context.new_page()
            await page.goto("https://www.ntuh.gov.tw/phr/Fpage.action?muid=2077&fid=1939", wait_until="networkidle", timeout=30000)
            target_frame = None
            for f in page.frames:
                if await f.locator("#DrugInfoQueryBox_txbDrugName").count() > 0:
                    target_frame = f
                    break
            if target_frame:
                await target_frame.fill("#DrugInfoQueryBox_txbDrugName", keyword)
                await target_frame.locator("#DrugInfoQueryBox_txbDrugName").press("Enter")
                await page.wait_for_timeout(3500)
                soup = BeautifulSoup(await target_frame.content(), "html.parser")
                for tr in soup.find_all("tr"):
                    if tr.find("tr"):
                        continue
                    cells = [c.get_text(" ", strip=True) for c in tr.find_all(["td", "th"], recursive=False) if c.get_text(strip=True)]
                    if len(cells) >= 3 and keyword.lower() in cells[0].lower() and "學名" not in cells[0]:
                        records.append({
                            "hospital_id": "ntuh",
                            "hospital_name": "台大醫院",
                            "brand_key": extract_brand_key(cells[2]),
                            "brand_en": cells[2],
                            "brand_zh": cells[1],
                            "generic_spec": cells[0],
                            "note": "正常收載",
                            "search_url": "https://www.ntuh.gov.tw/phr/Fpage.action?muid=2077&fid=1939"
                        })
            await page.close()
        except Exception as e:
            print("NTUH error:", e)

        # 2. 台北慈濟醫院
        try:
            page = await context.new_page()
            await page.goto("https://tp-his.tzuchi-healthcare.org.tw/DrugPharm/ComPharmacopoeia/AllInOne/Med_Search_AllInOne.aspx", timeout=30000)
            await page.fill("#tbxMedquery", keyword)
            await page.locator("#btnWordQry").click()
            await page.wait_for_load_state("networkidle")
            await page.wait_for_timeout(2000)
            soup = BeautifulSoup(await page.content(), "html.parser")
            for tr in soup.find_all("tr"):
                if tr.find("tr"):
                    continue
                cells = [c.get_text(" ", strip=True) for c in tr.find_all(["td", "th"], recursive=False)]
                if len(cells) >= 10 and keyword.lower() in cells[3].lower():
                    records.append({
                        "hospital_id": "tptzuchi",
                        "hospital_name": "台北慈濟醫院",
                        "brand_key": extract_brand_key(cells[2]),
                        "brand_en": cells[2],
                        "brand_zh": cells[4],
                        "generic_spec": cells[3],
                        "note": f"門:{cells[7]} / 急:{cells[8]} / 住:{cells[9]}",
                        "search_url": "https://tp-his.tzuchi-healthcare.org.tw/DrugPharm/ComPharmacopoeia/AllInOne/Med_Search_AllInOne.aspx"
                    })
            await page.close()
        except Exception as e:
            print("TPTZUCHI error:", e)

        # 3. 義大醫院
        try:
            page = await context.new_page()
            await page.goto("https://dept.edah.org.tw/ph/asp/search.asp?TAB=1&orgby=ED", timeout=30000)
            await page.fill("input[name='MedAliseDesc']", keyword)
            form = page.locator("form").filter(has=page.locator("input[name='MedAliseDesc']"))
            await form.locator("input[type='submit'], input[type='button'], input[type='image'], button").first.click()
            await page.wait_for_load_state("networkidle")
            await page.wait_for_timeout(2000)
            soup = BeautifulSoup(await page.content(), "html.parser")
            for tr in soup.find_all("tr"):
                if tr.find("tr"):
                    continue
                cells = [c.get_text(" ", strip=True) for c in tr.find_all(["td", "th"], recursive=False) if c.get_text(strip=True)]
                if len(cells) >= 5 and keyword.lower() in cells[0].lower() and "學名" not in cells[0]:
                    records.append({
                        "hospital_id": "edah",
                        "hospital_name": "義大醫院",
                        "brand_key": extract_brand_key(cells[2]),
                        "brand_en": f"{cells[2]} ({cells[4]})",
                        "brand_zh": cells[3],
                        "generic_spec": f"{cells[0]} {cells[4]}",
                        "note": "正常收載",
                        "search_url": "https://dept.edah.org.tw/ph/asp/search.asp?TAB=1&orgby=ED"
                    })
            await page.close()
        except Exception as e:
            print("EDAH error:", e)

        # 4. 中山附醫
        try:
            page = await context.new_page()
            await page.goto("https://www.csh.org.tw/DrugQuery/NewDrugQuery.aspx", wait_until="networkidle", timeout=30000)
            await page.fill("#tbQuery", keyword)
            btn = page.locator("#tbQuery").locator("xpath=following::*[self::button or (self::input and (@type='submit' or @type='button'))][1]")
            if await btn.count() > 0:
                await btn.click()
            else:
                await page.locator("#tbQuery").press("Enter")
            await page.wait_for_timeout(3500)
            soup = BeautifulSoup(await page.content(), "html.parser")
            for tr in soup.find_all("tr"):
                if tr.find("tr"):
                    continue
                cells = [c.get_text(" ", strip=True) for c in tr.find_all(["td", "th"], recursive=False) if c.get_text(strip=True)]
                if len(cells) >= 4 and keyword.lower() in " ".join(cells).lower() and "學名" not in cells[0]:
                    records.append({
                        "hospital_id": "csh",
                        "hospital_name": "中山醫學大學附設醫院",
                        "brand_key": extract_brand_key(cells[1]),
                        "brand_en": cells[1],
                        "brand_zh": cells[2],
                        "generic_spec": cells[3],
                        "note": "正常收載",
                        "search_url": "https://www.csh.org.tw/DrugQuery/NewDrugQuery.aspx"
                    })
            await page.close()
        except Exception as e:
            print("CSH error:", e)

        # 5. 高雄榮總
        try:
            page = await context.new_page()
            page.on("dialog", lambda d: asyncio.create_task(d.dismiss()))
            await page.goto("https://www2.vghks.gov.tw/DIWEB/DIQuerySql.jsp", timeout=30000)
            encoded_kw = urllib.parse.quote(keyword)
            target_url = f"https://www2.vghks.gov.tw/DIWEB/dIDrug.do?method=showAllDrugs&source=DIQR&portal=false&hid=1A0&drugName={encoded_kw}"
            await page.goto(target_url, timeout=30000)
            await page.wait_for_timeout(2500)
            soup = BeautifulSoup(await page.content(), "html.parser")
            for tr in soup.find_all("tr"):
                if tr.find("tr"):
                    continue
                cells = [c.get_text(" ", strip=True) for c in tr.find_all(["td", "th"], recursive=False) if c.get_text(strip=True)]
                if len(cells) >= 3 and keyword.lower() in " ".join(cells).lower() and "學名" not in cells[0]:
                    records.append({
                        "hospital_id": "vghks",
                        "hospital_name": "高雄榮民總醫院",
                        "brand_key": extract_brand_key(cells[1]),
                        "brand_en": cells[1],
                        "brand_zh": cells[2] if len(cells) > 2 else "",
                        "generic_spec": cells[3] if len(cells) > 3 else keyword,
                        "note": "正常收載",
                        "search_url": "https://www2.vghks.gov.tw/DIWEB/DIQuerySql.jsp"
                    })
            await page.close()
        except Exception as e:
            print("VGHKS error:", e)

        await browser.close()

    return {
        "keyword": keyword,
        "records": records,
        "hospitals": HOSPITAL_CATALOG
    }

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--keyword", required=True)
    parser.add_argument("--webhook", default="")
    args = parser.parse_args()

    result = asyncio.run(crawl_all(args.keyword.strip()))
    with open("drug_result.json", "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    if args.webhook:
        resp = requests.post(args.webhook, json=result, timeout=30)
        print("Webhook回傳狀態:", resp.status_code, resp.text[:100])
