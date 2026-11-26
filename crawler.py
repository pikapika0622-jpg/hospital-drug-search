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
    {"id": "cch", "name": "彰化基督教醫院", "mode": "auto", "url": "https://www.cch.org.tw/drug.aspx"},
    {"id": "vghtc", "name": "臺中榮民總醫院", "mode": "auto", "url": "https://www3.vghtc.gov.tw:8443/pharmacyHandbook/#/education/search"},
    {"id": "cmuh", "name": "中國醫藥大學附設醫院（含兒童醫院）", "mode": "auto", "url": "https://druginfo.cmuh.org.tw/DrugNetNew/BookInfo/DrugQuery.aspx"},
    {"id": "cgmh", "name": "長庚醫療體系（台北/林口/高雄）", "mode": "auto", "url": "https://www.cgmh.org.tw/tw/Services/Drug"},
    {"id": "chimei", "name": "奇美醫院（台南/永康）", "mode": "auto", "url": "https://www.chimei.org.tw/MedQuery/search"},
    {"id": "femh", "name": "亞東紀念醫院", "mode": "auto", "url": "https://www.e-pharm.info/safety/drug-information/femh-formulary"},
    {"id": "vghtpe", "name": "臺北榮民總醫院", "mode": "manual", "reason": "需圖形驗證碼", "url": "https://www7.vghtpe.gov.tw/home/index"},
    {"id": "nckuh", "name": "成大醫院", "mode": "manual", "reason": "需圖形驗證碼", "url": "https://web.hosp.ncku.edu.tw/pharmacy/"},
    {"id": "skh", "name": "新光醫院", "mode": "manual", "reason": "需圖形驗證碼", "url": "https://www.skh.org.tw/skh_regis/#/register/drug"},
    {"id": "tsgh", "name": "三軍總醫院", "mode": "manual", "reason": "Cloudflare 防護", "url": "https://wwwv.tsgh.ndmctsgh.edu.tw/unit/10026/25855"},
    {"id": "mmh", "name": "馬偕紀念醫院（台北/淡水）", "mode": "manual", "reason": "限台灣IP連線", "url": "https://mcloud.mmh.org.tw/DMZDrugFormB817/DrugQuery.html"},
    {"id": "tzuchi", "name": "花蓮慈濟醫院", "mode": "manual", "reason": "限台灣IP連線", "url": "https://hldrug.tzuchi.com.tw/tchw/IphqryChinese/DesktopModules/WesternMedicine/Pill_Search.aspx?Hospital=HL"},
    {"id": "kmuh", "name": "高雄醫學大學附設中和紀念醫院", "mode": "manual", "reason": "限台灣IP連線", "url": "https://www.kmuh.org.tw/web/kmuhdept/pill/"},
    {"id": "cgh", "name": "國泰綜合醫院", "mode": "manual", "reason": "限台灣IP連線", "url": "https://www.cgh.org.tw/ec99/rwd112/category.asp?category_id=15"},
    {"id": "hch", "name": "臺大醫院新竹分院", "mode": "manual", "reason": "限台灣IP連線", "url": "https://www.hch.gov.tw/"},
    {"id": "wanfang", "name": "萬芳醫院", "mode": "manual", "reason": "查詢入口確認中", "url": "https://www.wanfang.gov.tw/"},
    {"id": "shh", "name": "雙和醫院", "mode": "manual", "reason": "查詢入口確認中", "url": "https://shh.tmu.edu.tw/"},
]

def extract_brand_key(brand_en: str, fallback_zh: str = "") -> str:
    cleaned = (brand_en or "").strip()
    if cleaned and cleaned not in ["-", "--", "/"]:
        match = re.search(r"[A-Za-z][A-Za-z0-9\-]*", cleaned)
        if match:
            return match.group(0).capitalize()
    if fallback_zh:
        return re.sub(r"[\s（(].*$", "", fallback_zh)[:8]
    return "Unknown"

async def crawl_ntuh(context, keyword: str):
    items = []
    page = await context.new_page()
    try:
        await page.goto("https://www.ntuh.gov.tw/phr/Fpage.action?muid=2077&fid=1939", wait_until="domcontentloaded", timeout=20000)
        await page.wait_for_timeout(2000)
        target_frame = None
        for f in page.frames:
            if await f.locator("#DrugInfoQueryBox_txbDrugName").count() > 0:
                target_frame = f
                break
        if target_frame:
            await target_frame.fill("#DrugInfoQueryBox_txbDrugName", keyword)
            await target_frame.locator("#DrugInfoQueryBox_txbDrugName").press("Enter")
            await page.wait_for_timeout(3000)
            soup = BeautifulSoup(await target_frame.content(), "html.parser")
            for tr in soup.find_all("tr"):
                if tr.find("tr"):
                    continue
                cells = [c.get_text(" ", strip=True) for c in tr.find_all(["td", "th"], recursive=False) if c.get_text(strip=True)]
                if len(cells) >= 3 and keyword.lower() in cells[0].lower() and "學名" not in cells[0]:
                    items.append({
                        "hospital_id": "ntuh",
                        "hospital_name": "台大醫院",
                        "brand_key": extract_brand_key(cells[2], cells[1]),
                        "brand_en": cells[2],
                        "brand_zh": cells[1],
                        "generic_spec": cells[0],
                        "note": "正常收載",
                        "search_url": "https://www.ntuh.gov.tw/phr/Fpage.action?muid=2077&fid=1939"
                    })
    except Exception as e:
        print("NTUH error:", e)
    finally:
        await page.close()
    return items

async def crawl_tptzuchi(context, keyword: str):
    items = []
    page = await context.new_page()
    try:
        await page.goto("https://tp-his.tzuchi-healthcare.org.tw/DrugPharm/ComPharmacopoeia/AllInOne/Med_Search_AllInOne.aspx", wait_until="domcontentloaded", timeout=20000)
        await page.fill("#tbxMedquery", keyword)
        await page.locator("#btnWordQry").click()
        await page.wait_for_timeout(3000)
        soup = BeautifulSoup(await page.content(), "html.parser")
        for tr in soup.find_all("tr"):
            if tr.find("tr"):
                continue
            cells = [c.get_text(" ", strip=True) for c in tr.find_all(["td", "th"], recursive=False)]
            if len(cells) >= 10 and keyword.lower() in cells[3].lower():
                items.append({
                    "hospital_id": "tptzuchi",
                    "hospital_name": "台北慈濟醫院",
                    "brand_key": extract_brand_key(cells[2], cells[4]),
                    "brand_en": cells[2],
                    "brand_zh": cells[4],
                    "generic_spec": cells[3],
                    "note": f"門:{cells[7]} / 急:{cells[8]} / 住:{cells[9]}",
                    "search_url": "https://tp-his.tzuchi-healthcare.org.tw/DrugPharm/ComPharmacopoeia/AllInOne/Med_Search_AllInOne.aspx"
                })
    except Exception as e:
        print("TPTZUCHI error:", e)
    finally:
        await page.close()
    return items

async def crawl_edah(context, keyword: str):
    items = []
    page = await context.new_page()
    try:
        await page.goto("https://dept.edah.org.tw/ph/asp/search.asp?TAB=1&orgby=ED", wait_until="domcontentloaded", timeout=20000)
        await page.fill("input[name='MedAliseDesc']", keyword)
        form = page.locator("form").filter(has=page.locator("input[name='MedAliseDesc']"))
        await form.locator("input[type='submit'], input[type='button'], input[type='image'], button").first.click()
        await page.wait_for_timeout(2500)
        soup = BeautifulSoup(await page.content(), "html.parser")
        for tr in soup.find_all("tr"):
            if tr.find("tr"):
                continue
            cells = [c.get_text(" ", strip=True) for c in tr.find_all(["td", "th"], recursive=False) if c.get_text(strip=True)]
            if len(cells) >= 5 and keyword.lower() in cells[0].lower() and "學名" not in cells[0]:
                items.append({
                    "hospital_id": "edah",
                    "hospital_name": "義大醫院",
                    "brand_key": extract_brand_key(cells[2], cells[3]),
                    "brand_en": f"{cells[2]} ({cells[4]})",
                    "brand_zh": cells[3],
                    "generic_spec": f"{cells[0]} {cells[4]}",
                    "note": "正常收載",
                    "search_url": "https://dept.edah.org.tw/ph/asp/search.asp?TAB=1&orgby=ED"
                })
    except Exception as e:
        print("EDAH error:", e)
    finally:
        await page.close()
    return items

async def crawl_csh(context, keyword: str):
    items = []
    page = await context.new_page()
    try:
        await page.goto("https://www.csh.org.tw/DrugQuery/NewDrugQuery.aspx", wait_until="domcontentloaded", timeout=20000)
        await page.wait_for_timeout(1500)
        await page.fill("#tbQuery", keyword)
        clicked = False
        for sel in [
            "#tbQuery ~ input[type='submit']",
            "#tbQuery ~ input[type='image']",
            "#tbQuery ~ button",
            "input[value*='查詢']",
            "button:has-text('查詢')",
            "input[id*='btn' i]"
        ]:
            loc = page.locator(sel).first
            if await loc.count() > 0 and await loc.is_visible():
                await loc.click()
                clicked = True
                break
        if not clicked:
            await page.locator("#tbQuery").press("Enter")
        await page.wait_for_timeout(3500)
        soup = BeautifulSoup(await page.content(), "html.parser")
        for tr in soup.find_all("tr"):
            if tr.find("tr"):
                continue
            raw_cells = [c.get_text(" ", strip=True) for c in tr.find_all(["td", "th"], recursive=False)]
            non_empty = [c for c in raw_cells if c]
            if len(non_empty) >= 3 and keyword.lower() in " ".join(non_empty).lower() and "學名" not in non_empty[0]:
                kw_idx = next((i for i, v in enumerate(non_empty) if keyword.lower() in v.lower()), -1)
                if kw_idx >= 2:
                    brand_en = non_empty[kw_idx - 2]
                    brand_zh = non_empty[kw_idx - 1]
                    generic_spec = non_empty[kw_idx]
                else:
                    brand_en = non_empty[0]
                    brand_zh = non_empty[1]
                    generic_spec = non_empty[2]
                items.append({
                    "hospital_id": "csh",
                    "hospital_name": "中山醫學大學附設醫院",
                    "brand_key": extract_brand_key(brand_en, brand_zh),
                    "brand_en": brand_en,
                    "brand_zh": brand_zh,
                    "generic_spec": generic_spec,
                    "note": "正常收載",
                    "search_url": "https://www.csh.org.tw/DrugQuery/NewDrugQuery.aspx"
                })
    except Exception as e:
        print("CSH error:", e)
    finally:
        await page.close()
    return items

async def crawl_vghks(context, keyword: str):
    items = []
    page = await context.new_page()
    try:
        page.on("dialog", lambda d: asyncio.create_task(d.dismiss()))
        encoded_kw = urllib.parse.quote(keyword)
        target_url = f"https://www2.vghks.gov.tw/DIWEB/dIDrug.do?method=showAllDrugs&source=DIQR&portal=false&hid=1A0&drugName={encoded_kw}"
        await page.goto(target_url, wait_until="domcontentloaded", timeout=20000)
        await page.wait_for_timeout(2500)
        soup = BeautifulSoup(await page.content(), "html.parser")
        for tr in soup.find_all("tr"):
            if tr.find("tr"):
                continue
            raw_cells = [c.get_text(" ", strip=True) for c in tr.find_all(["td", "th"], recursive=False)]
            if len(raw_cells) >= 4 and keyword.lower() in " ".join(raw_cells).lower() and "學名" not in raw_cells[0]:
                brand_en = raw_cells[1] if raw_cells[1] and raw_cells[1] not in ["-", "--"] else ""
                nhi_code = raw_cells[2] if len(raw_cells) > 2 else ""
                brand_zh = raw_cells[3] if len(raw_cells) > 3 else ""
                display_en = brand_en if brand_en else f"{brand_zh} ({nhi_code})"
                items.append({
                    "hospital_id": "vghks",
                    "hospital_name": "高雄榮民總醫院",
                    "brand_key": extract_brand_key(brand_en, brand_zh),
                    "brand_en": display_en,
                    "brand_zh": brand_zh,
                    "generic_spec": keyword,
                    "note": f"健保碼:{nhi_code}" if nhi_code else "正常收載",
                    "search_url": "https://www2.vghks.gov.tw/DIWEB/DIQuerySql.jsp"
                })
    except Exception as e:
        print("VGHKS error:", e)
    finally:
        await page.close()
    return items

async def crawl_cch(context, keyword: str):
    items = []
    page = await context.new_page()
    try:
        await page.goto("https://www.cch.org.tw/drug.aspx", wait_until="domcontentloaded", timeout=20000)
        await page.wait_for_timeout(1500)
        await page.fill("#Keyword_txt", keyword)
        await page.click("#QueryBtn1")
        await page.wait_for_timeout(3000)
        soup = BeautifulSoup(await page.content(), "html.parser")

        detail_targets = []
        seen_urls = set()
        for tr in soup.find_all("tr"):
            row_txt = tr.get_text(" ", strip=True)
            a_tag = tr.find("a", href=re.compile(r"drug_2\.aspx", re.I))
            if a_tag and keyword.lower() in row_txt.lower():
                full_url = urllib.parse.urljoin("https://www.cch.org.tw/", a_tag["href"])
                if full_url not in seen_urls:
                    seen_urls.add(full_url)
                    tds = [c.get_text(" ", strip=True) for c in tr.find_all("td")]
                    detail_targets.append((full_url, tds))

        for detail_url, fallback_tds in detail_targets[:15]:
            generic_spec = fallback_tds[0] if len(fallback_tds) > 0 else keyword
            brand_zh = fallback_tds[1] if len(fallback_tds) > 1 else ""
            brand_en = ""
            manufactory = ""
            try:
                resp = await context.request.get(detail_url, timeout=15000)
                d_soup = BeautifulSoup(await resp.text(), "html.parser")
                d_rows = d_soup.find_all("tr")
                for idx, dtr in enumerate(d_rows):
                    dcells = [re.sub(r"\s+", " ", c.get_text(" ", strip=True)).strip() for c in dtr.find_all(["td", "th"])]
                    if len(dcells) >= 3 and "商品名" in dcells[1] and idx + 1 < len(d_rows):
                        vcells = [re.sub(r"\s+", " ", c.get_text(" ", strip=True)).strip() for c in d_rows[idx + 1].find_all(["td", "th"])]
                        if len(vcells) >= 3:
                            generic_spec = vcells[0] or generic_spec
                            brand_en = vcells[1]
                            brand_zh = vcells[2] or brand_zh
                    elif len(dcells) >= 2 and "廠牌" in dcells[0]:
                        manufactory = dcells[1]
            except Exception as de:
                print("CCH detail error:", de)

            items.append({
                "hospital_id": "cch",
                "hospital_name": "彰化基督教醫院",
                "brand_key": extract_brand_key(brand_en, brand_zh),
                "brand_en": brand_en if brand_en else brand_zh,
                "brand_zh": brand_zh,
                "generic_spec": generic_spec,
                "note": manufactory if manufactory else "正常收載",
                "search_url": detail_url
            })
    except Exception as e:
        print("CCH error:", e)
    finally:
        await page.close()
    return items

async def crawl_vghtc(context, keyword: str):
    items = []
    try:
        encoded_kw = urllib.parse.quote(keyword)
        api_url = f"https://www3.vghtc.gov.tw:8443/pharmacyHandbook/API/handbookSearchEducation.jsp?keyword={encoded_kw}"
        resp = await context.request.get(api_url, timeout=15000)
        raw_txt = (await resp.text()).strip()
        payload = json.loads(raw_txt)
        for row in payload.get("DATA", []):
            brand_en = (row.get("UDNMFTDGNM") or row.get("UDDMDPNAME") or "").strip()
            brand_zh = (row.get("UDDRGNMKJ") or "").strip()
            generic_spec = (row.get("UDNMATDGNM") or keyword).strip()
            drg_code = (row.get("UDNDRGCODE") or "").strip()
            if keyword.lower() in f"{generic_spec} {brand_en} {brand_zh}".lower():
                items.append({
                    "hospital_id": "vghtc",
                    "hospital_name": "臺中榮民總醫院",
                    "brand_key": extract_brand_key(brand_en, brand_zh),
                    "brand_en": brand_en if brand_en else brand_zh,
                    "brand_zh": brand_zh,
                    "generic_spec": generic_spec,
                    "note": f"院內碼:{drg_code}" if drg_code else "正常收載",
                    "search_url": "https://www3.vghtc.gov.tw:8443/pharmacyHandbook/#/education/search"
                })
    except Exception as e:
        print("VGHTC error:", e)
    return items

async def crawl_cmuh(context, keyword: str):
    items = []
    page = await context.new_page()
    try:
        await page.goto("https://druginfo.cmuh.org.tw/DrugNetNew/BookInfo/DrugQuery.aspx", wait_until="domcontentloaded", timeout=20000)
        await page.wait_for_timeout(1500)
        await page.fill("#txtkeyword", keyword)
        await page.click("#Button1")
        await page.wait_for_timeout(3000)
        soup = BeautifulSoup(await page.content(), "html.parser")
        for tr in soup.find_all("tr"):
            if tr.find("tr"):
                continue
            cells = [re.sub(r"\s+", " ", c.get_text(" ", strip=True)).strip() for c in tr.find_all(["td", "th"], recursive=False)]
            if len(cells) >= 4 and keyword.lower() in " ".join(cells).lower() and "醫令代碼" not in cells[0]:
                items.append({
                    "hospital_id": "cmuh",
                    "hospital_name": "中國醫藥大學附設醫院（含兒童醫院）",
                    "brand_key": extract_brand_key(cells[2], cells[1]),
                    "brand_en": cells[2] if cells[2] else cells[1],
                    "brand_zh": cells[1],
                    "generic_spec": cells[3],
                    "note": f"醫令碼:{cells[0]}" if cells[0] else "正常收載",
                    "search_url": "https://druginfo.cmuh.org.tw/DrugNetNew/BookInfo/DrugQuery.aspx"
                })
    except Exception as e:
        print("CMUH error:", e)
    finally:
        await page.close()
    return items

async def crawl_cgmh(context, keyword: str):
    items = []
    page = await context.new_page()
    try:
        encoded_kw = urllib.parse.quote(keyword)
        url = f"https://www.cgmh.org.tw/tw/Services/DrugSearch?keyword={encoded_kw}"
        await page.goto(url, wait_until="domcontentloaded", timeout=20000)
        await page.wait_for_timeout(2500)
        soup = BeautifulSoup(await page.content(), "html.parser")
        seen = set()
        for tr in soup.find_all("tr"):
            cells = [re.sub(r"\s+", " ", c.get_text(" ", strip=True)).strip() for c in tr.find_all(["td", "th"])]
            if not cells or "商品名：" not in cells[0] or keyword.lower() not in cells[0].lower():
                continue
            txt = cells[0]
            code_m = re.match(r"^([A-Z0-9]+)\s+商品名：", txt)
            code = code_m.group(1) if code_m else ""
            trade_m = re.search(r"商品名：(.+?)\s+學名：", txt)
            trade_full = trade_m.group(1).strip() if trade_m else ""
            gen_m = re.search(r"學名：(.+?)(?:\s+副作用：|\s+適應症：|\s+異動日期：|$)", txt)
            generic_spec = gen_m.group(1).strip() if gen_m else keyword

            zh_m = re.search(r"[\u4e00-\u9fff]", trade_full)
            if zh_m:
                brand_en = trade_full[:zh_m.start()].strip()
                brand_zh = trade_full[zh_m.start():].strip()
            else:
                brand_en = trade_full
                brand_zh = ""

            dedup_key = (code, brand_en, generic_spec)
            if dedup_key in seen:
                continue
            seen.add(dedup_key)

            items.append({
                "hospital_id": "cgmh",
                "hospital_name": "長庚醫療體系（台北/林口/高雄）",
                "brand_key": extract_brand_key(brand_en, brand_zh),
                "brand_en": brand_en if brand_en else brand_zh,
                "brand_zh": brand_zh,
                "generic_spec": generic_spec,
                "note": f"院內碼:{code}" if code else "正常收載",
                "search_url": url
            })
    except Exception as e:
        print("CGMH error:", e)
    finally:
        await page.close()
    return items

async def crawl_chimei(context, keyword: str):
    items = []
    page = await context.new_page()
    try:
        await page.goto("https://www.chimei.org.tw/MedQuery/search", wait_until="domcontentloaded", timeout=20000)
        await page.wait_for_timeout(1500)
        await page.fill("#keyword", keyword)
        await page.locator("button[type='submit']").first.click()
        await page.wait_for_timeout(2500)

        med_links = page.locator(".med-link")
        count = await med_links.count()
        for i in range(min(count, 15)):
            await med_links.nth(i).click()
            await page.wait_for_timeout(1500)
            body_txt = await page.evaluate("() => document.body.innerText")
            lines = [ln.strip() for ln in body_txt.splitlines() if ln.strip()]
            info = {}
            for idx, ln in enumerate(lines):
                if ln in ["藥品代碼", "商品名", "學名", "中文名", "健保代碼", "品牌/代理商"] and idx + 1 < len(lines):
                    info[ln] = lines[idx + 1]
            brand_en = info.get("商品名", "")
            brand_zh = info.get("中文名", "")
            generic_spec = info.get("學名", keyword)
            vendor = info.get("品牌/代理商", "").rstrip("/").strip()
            if brand_en or brand_zh:
                items.append({
                    "hospital_id": "chimei",
                    "hospital_name": "奇美醫院（台南/永康）",
                    "brand_key": extract_brand_key(brand_en, brand_zh),
                    "brand_en": brand_en if brand_en else brand_zh,
                    "brand_zh": brand_zh,
                    "generic_spec": generic_spec,
                    "note": vendor if vendor else "正常收載",
                    "search_url": "https://www.chimei.org.tw/MedQuery/search"
                })
    except Exception as e:
        print("CHIMEI error:", e)
    finally:
        await page.close()
    return items

async def crawl_femh(context, keyword: str):
    items = []
    page = await context.new_page()
    try:
        await page.goto("https://www.e-pharm.info/safety/drug-information/femh-formulary", wait_until="domcontentloaded", timeout=20000)
        await page.wait_for_timeout(1500)
        await page.locator("input[name='elements[e5571ded-b1aa-402a-a883-19546b579bcb]']").fill(keyword)
        await page.locator("button[type='submit']:visible").first.click()
        await page.wait_for_timeout(2500)
        soup = BeautifulSoup(await page.content(), "html.parser")
        for teaser in soup.select(".teaser-item"):
            title_el = teaser.select_one("h2.pos-title")
            a_el = teaser.select_one("a[href*='/femh-formulary/item/']")
            brand_zh = title_el.get_text(strip=True) if title_el else ""
            brand_en = (a_el.get("title") or "").strip() if a_el else ""
            item_url = urllib.parse.urljoin("https://www.e-pharm.info", a_el["href"]) if a_el else "https://www.e-pharm.info/safety/drug-information/femh-formulary"
            if brand_zh or brand_en:
                items.append({
                    "hospital_id": "femh",
                    "hospital_name": "亞東紀念醫院",
                    "brand_key": extract_brand_key(brand_en, brand_zh),
                    "brand_en": brand_en if brand_en else brand_zh,
                    "brand_zh": brand_zh,
                    "generic_spec": keyword,
                    "note": "正常收載",
                    "search_url": item_url
                })
    except Exception as e:
        print("FEMH error:", e)
    finally:
        await page.close()
    return items

async def crawl_all(keyword: str):
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

        results = await asyncio.gather(
            crawl_ntuh(context, keyword),
            crawl_tptzuchi(context, keyword),
            crawl_edah(context, keyword),
            crawl_csh(context, keyword),
            crawl_vghks(context, keyword),
            crawl_cch(context, keyword),
            crawl_vghtc(context, keyword),
            crawl_cmuh(context, keyword),
            crawl_cgmh(context, keyword),
            crawl_chimei(context, keyword),
            crawl_femh(context, keyword),
        )
        records = [item for sublist in results for item in sublist]
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
    print(f"抓取完成，共 {len(result['records'])} 筆紀錄")

    if args.webhook:
        resp = requests.post(
            args.webhook,
            data=json.dumps(result, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            timeout=30
        )
        print("Webhook回傳狀態:", resp.status_code, resp.text[:150])
