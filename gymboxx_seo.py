# -*- coding: utf-8 -*-
"""
짐박스 네이버 플레이스 SEO 분석 플랫폼 (통합 단일 파일)
────────────────────────────────────────────────────────
실행 (웹 서버):  python gymboxx_seo.py
접속:            http://localhost:5000

실행 (스크레이퍼 단독): python gymboxx_seo.py path/to/scraper_config.json

설치:
  pip install flask playwright requests
  playwright install chromium
"""

import asyncio
import json
import os
import re
import subprocess
import sys
import threading
from collections import Counter
from datetime import datetime
from pathlib import Path

from flask import Flask, render_template, request, jsonify, redirect, url_for
from playwright.async_api import async_playwright, Response

try:
    import requests as req_lib
except ImportError:
    req_lib = None

# ══════════════════════════════════════════════════════════════════
# 공통 상수
# ══════════════════════════════════════════════════════════════════

STOPWORDS = {
    "있습니다","합니다","입니다","드립니다","있어요","해요","있어서","해드립니다",
    "이고","이며","그리고","그런데","하지만","그래서","이라","에서","으로","위해",
    "하여","하는","하고","하면","하다","한다","되어","때문","정말","너무","매우",
    "아주","조금","좀더","진짜","완전","했어요","했습니다","해서","인데","이에",
    "데요","고요","좋아요","좋습니다","좋은","좋고","같아요","같습니다","없어요",
    "있고","없고","됩니다","됐어요","받았어요","생각해요","느껴","느낌","같은",
    "이번","처음","다음","저도","저는","제가","하나","여기","거기","이곳","저곳",
    "이런","저런","그런","어떤","갔어요","왔어요","봤어요","했다","나왔어요",
    "둘","셋","넷","다섯","한번","두번","몇번","번째",
    "갔다","왔다","봤다",
}

TOPIC_MAP = {
    "트레이너·PT":  ["트레이너","pt","피티","코치","선생님","담당자","실장","관리"],
    "기구·장비":    ["기구","머신","덤벨","바벨","케이블","유산소","러닝머신","싸이클"],
    "공간·시설":    ["넓","공간","층고","뷰","창문","채광","환기","청결","깔끔","냄새"],
    "가격·가성비":  ["가격","비용","할인","이벤트","가성비","합리","저렴","회원권"],
    "위치·교통":    ["역","출구","주차","도보","교통","위치","찾기","거리"],
    "혼잡도":       ["붐비","혼잡","대기","줄","여유","여유롭","한적","복잡"],
    "운영시간":     ["24시간","새벽","야간","아침","저녁","주말","영업"],
    "PT 효과":      ["다이어트","감량","근육","체형","교정","재활","효과","변화","결과"],
    "분위기":       ["분위기","힐링","여성","프리미엄","고급","감성","인테리어"],
    "샤워·탈의실":  ["샤워","탈의","락커","화장실","청결","세면","수건"],
}

POSITIVE_SIGNALS = [
    "친절","깔끔","넓","쾌적","만족","좋","최고","추천","훌륭","완벽",
    "전문","체계","효과","변화","결과","성과","뷰","힐링","편안","여유",
    "합리","가성비","청결","위생","배려","세심","꼼꼼","섬세",
]
NEGATIVE_SIGNALS = [
    "불친절","좁","복잡","불만","아쉬","최악","별로","실망","비싸",
    "붐비","줄","대기","노후","낡","냄새","불결","불편","어둡",
]

# ══════════════════════════════════════════════════════════════════
# ██  SCRAPER 모듈
# ══════════════════════════════════════════════════════════════════

# ── 외부 config 파일 지원 ──────────────────────────────────────────
_EXT_CONFIG: dict = {}
if len(sys.argv) > 1:
    try:
        _cfg_path = Path(sys.argv[1])
        if _cfg_path.exists():
            _EXT_CONFIG = json.loads(_cfg_path.read_text(encoding="utf-8"))
            print(f"[CONFIG] 외부 설정 로드: {_cfg_path}")
    except Exception as _e:
        print(f"[CONFIG] 설정 파일 로드 실패: {_e}")

PLACES = _EXT_CONFIG.get("places", {
    "1위":     {"id": "13155391",   "name": "맥스피트니스 건대점"},
    "내 업체": {"id": "1100555051", "name": "짐박스피트니스 건대구의점"},
})

MAX_REVIEWS_PER_PLACE = int(_EXT_CONFIG.get("max_reviews", 100))
SCROLL_PAUSE = 1.5

_OUT_DIR   = Path(_EXT_CONFIG["output_dir"]) if "output_dir" in _EXT_CONFIG else Path(".")
OUT_JSON   = str(_OUT_DIR / "reviews.json")
OUT_REPORT = str(_OUT_DIR / "review_report.txt")
SHOT_DIR   = _OUT_DIR / "screenshots"

# ── 날짜 필드명 목록 ──────────────────────────────────────────────
_DATE_FIELDS = (
    "created", "visitDate", "createdAt", "createdDate", "reviewDate",
    "registerDate", "registDate", "date", "updateDate", "updatedAt",
)

# ── JS: 스크롤 컨테이너 탐색 ──────────────────────────────────────
SCROLL_JS = """
(amount) => {
    const selectors = [
        '.place_section_scroll',
        '[class*="ReviewList"]',
        '[class*="review_list"]',
        '[class*="reviewList"]',
        '.pui__ygLbC',
        '.pui__xAHSj',
        '[data-nclicks-area-code]',
        'ul[class*="list"]',
        '.place_section',
    ];
    for (const sel of selectors) {
        const el = document.querySelector(sel);
        if (el && el.scrollHeight > el.clientHeight + 100) {
            el.scrollBy(0, amount);
            return 'container:' + sel;
        }
    }
    const all = Array.from(document.querySelectorAll('*'));
    const scrollable = all.find(el => {
        const style = window.getComputedStyle(el);
        const overflow = style.overflow + style.overflowY;
        return (overflow.includes('scroll') || overflow.includes('auto'))
            && el.scrollHeight > el.clientHeight + 100;
    });
    if (scrollable) {
        scrollable.scrollBy(0, amount);
        return 'dynamic:' + (scrollable.className || scrollable.tagName);
    }
    // 마지막 수단: document 스크롤
    document.documentElement.scrollBy(0, amount);
    window.scrollBy(0, amount);
    return 'window';
}
"""

# ── JS: 홈 탭 외부 기능 연동 추출 ────────────────────────────────
METADATA_JS = """
() => {
    const result = {
        has_n_booking: false,
        has_talktalk:  false,
        has_coupon:    false,
        coupon_name:   null,
    };
    const els = Array.from(document.querySelectorAll('a, button, [role="button"]'));
    for (const el of els) {
        const text = (el.textContent || '').trim().replace(/\\s+/g, ' ');
        const href = el.getAttribute('href') || '';
        if (!result.has_n_booking && (
            text.includes('예약') || href.includes('booking.naver.com') || href.includes('/booking')
        )) {
            result.has_n_booking = true;
        }
        if (!result.has_talktalk && (
            text.includes('톡톡') || href.includes('talk.naver.com')
        )) {
            result.has_talktalk = true;
        }
        if (!result.has_coupon && text.includes('쿠폰') && text.length < 200) {
            result.has_coupon = true;
            result.coupon_name = text.slice(0, 100);
        }
    }
    return result;
}
"""


def extract_reviews_from_api(payload) -> list:
    reviews = []

    def search(obj):
        if isinstance(obj, list):
            for item in obj:
                search(item)
        elif isinstance(obj, dict):
            for key in ("reviews", "visitorReviews", "items", "list", "data"):
                if key in obj and isinstance(obj[key], list):
                    for r in obj[key]:
                        if isinstance(r, dict):
                            text = (
                                r.get("body") or r.get("text") or
                                r.get("content") or r.get("description") or
                                r.get("review") or ""
                            )
                            if text and len(text) > 5:
                                date_val = ""
                                for df in _DATE_FIELDS:
                                    v = r.get(df)
                                    if v:
                                        date_val = str(v)
                                        break
                                rating = r.get("starScore") or r.get("rating")
                                reviews.append({
                                    "text":   text,
                                    "rating": "" if rating is None else str(rating),
                                    "date":   date_val,
                                })
            for v in obj.values():
                search(v)

    search(payload)
    return reviews


def categorize_coupon(coupon_name):
    if not coupon_name:
        return None
    if re.search(r'무료|체험|1회|OT', coupon_name):
        return "Experience"
    if re.search(r'증정|서비스|음료', coupon_name):
        return "Freebie"
    if re.search(r'%|할인|원', coupon_name):
        return "Discount"
    return "Conditional"


async def extract_place_metadata(frame) -> dict:
    default = {"has_n_booking": False, "has_talktalk": False,
                "has_coupon": False, "coupon_name": None}
    if frame is None:
        return default
    try:
        return await frame.evaluate(METADATA_JS)
    except Exception as e:
        print(f"  ⚠  메타데이터 추출 실패: {e}")
        return default


async def find_entry_frame(page, timeout_sec: int = 20):
    PROBE_SELS = [
        "a.fvwqf",
        "a._tab-menu[data-index='3']",
        "li.pui__X35jYm",
        "a[role='tab']",
    ]
    for attempt in range(timeout_sec):
        frames = page.frames
        sub_frames = [f for f in frames
                      if f != page.main_frame and f.url not in ("about:blank", "")]
        for f in sub_frames:
            for sel in PROBE_SELS:
                try:
                    if await f.query_selector(sel):
                        print(f"  🖼  frame 발견 ({sel}): {f.url[:70]}")
                        return f
                except Exception:
                    pass
        for sel in PROBE_SELS:
            try:
                if await page.main_frame.query_selector(sel):
                    print(f"  🖼  main frame 발견 ({sel})")
                    return page.main_frame
            except Exception:
                pass
        if attempt % 5 == 0:
            urls = [f.url[:70] for f in frames if f.url not in ("about:blank", "")]
            print(f"  🔍 [{attempt}s] frames({len(frames)}개): {urls}")
        await page.wait_for_timeout(1000)
    print("  ❌ frame을 찾지 못했습니다.")
    return None


async def dismiss_popups(page) -> None:
    for sel in [
        "button.panorama_config_popup_btn_close",
        "button[class*='popup_btn_close']",
        "button[class*='close']",
        ".popup_close",
    ]:
        try:
            btn = await page.query_selector(sel)
            if btn and await btn.is_visible():
                await btn.click()
                await page.wait_for_timeout(800)
        except Exception:
            pass


async def navigate_to_review_tab(frame, page) -> bool:
    if "place.map.naver.com" not in frame.url and "place" not in frame.url:
        return False
    for sel in [
        "a._tab-menu[data-index='3']",
        "a[role='tab'][data-index='3']",
        "a.tpj9w[data-index='3']",
        "a:has(> span.I2hj8)",
        "a[href*='/review'][role='tab']",
    ]:
        try:
            el = await frame.query_selector(sel)
            if el and await el.is_visible():
                text = (await el.inner_text()).strip()
                if "리뷰" not in text and "review" not in (await el.get_attribute("href") or ""):
                    continue
                await el.click()
                await page.wait_for_timeout(2500)
                return True
        except Exception:
            pass
    return False


async def extract_visible_reviews(frame) -> list:
    collected = []
    for item_sel in [
        "li.pui__X35jYm",
        "li[class*='reviewer']",
        "li[class*='review_item']",
        "div[class*='ReviewItem']",
        "div[class*='review_item']",
        "ul[class*='list'] > li",
        ".pui__vn15t2",
        "li.place_visitor_review",
    ]:
        try:
            items = await frame.query_selector_all(item_sel)
            if not items:
                continue
            for item in items:
                review = {"text": "", "rating": "", "date": ""}
                for ts in ["p.pui__xhnDpg","span.pui__xhnDpg","div.pui__vn15t2",
                           "[class*='review_text']","[class*='reviewText']",
                           "[class*='body']","p","span.text"]:
                    try:
                        tel = await item.query_selector(ts)
                        if tel:
                            t = (await tel.inner_text()).strip()
                            if len(t) >= 10:
                                review["text"] = t
                                break
                    except Exception:
                        pass
                if not review["text"]:
                    full = (await item.inner_text()).strip()
                    if len(full) >= 15 and re.search(r"[가-힣]{3,}", full):
                        review["text"] = full[:500]
                if not review["text"]:
                    continue
                for rs in ["[class*='score']","[class*='rating']","em.num","span.num"]:
                    try:
                        rel = await item.query_selector(rs)
                        if rel:
                            review["rating"] = (await rel.inner_text()).strip()
                            break
                    except Exception:
                        pass
                for ds in ["time","[class*='date']","span.date","span[class*='time']"]:
                    try:
                        del_el = await item.query_selector(ds)
                        if del_el:
                            review["date"] = (await del_el.inner_text()).strip()
                            break
                    except Exception:
                        pass
                collected.append(review)
            if collected:
                break
        except Exception:
            continue
    return collected


async def scrape_reviews(page, rank: str, info: dict) -> dict:
    place_id = info["id"]
    name     = info["name"]
    url_home   = f"https://map.naver.com/p/entry/place/{place_id}"
    url_review = f"https://map.naver.com/p/entry/place/{place_id}?placePath=%2Freview"

    print(f"\n[{rank}] {name}")

    result = {
        "rank": rank, "place_id": place_id, "name": name,
        "reviews": [], "total_collected": 0, "source": "none",
        "has_n_booking": False, "has_talktalk": False,
        "has_coupon": False, "coupon_name": None, "coupon_type": None,
    }

    api_reviews = []

    async def on_response(resp: Response):
        try:
            rurl = resp.url
            if any(p in rurl for p in [
                "api.place.naver.com", "place.map.naver.com/place/v",
                "/graphql", "review", "visitor",
            ]):
                ct = resp.headers.get("content-type", "")
                if "json" in ct:
                    body = await resp.json()
                    found = extract_reviews_from_api(body)
                    if found:
                        api_reviews.extend(found)
                        print(f"  📡 API {len(found)}건 캡처 (누적 {len(api_reviews)}건)")
        except Exception:
            pass

    page.on("response", on_response)

    try:
        # Step 0: 홈 탭 → 외부 기능 연동 메타데이터
        print(f"  🏠 홈 탭: {url_home}")
        await page.goto(url_home, wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(3000)
        await dismiss_popups(page)

        home_frame = None
        for _ in range(8):
            for f in page.frames:
                if f != page.main_frame and f.url not in ("about:blank", ""):
                    home_frame = f
                    break
            if home_frame:
                break
            await page.wait_for_timeout(1000)
        if home_frame is None:
            home_frame = page.main_frame

        meta = await extract_place_metadata(home_frame)
        result.update({
            "has_n_booking": meta["has_n_booking"],
            "has_talktalk":  meta["has_talktalk"],
            "has_coupon":    meta["has_coupon"],
            "coupon_name":   meta["coupon_name"],
            "coupon_type":   categorize_coupon(meta["coupon_name"]),
        })
        print(f"  📋 N예약:{meta['has_n_booking']}  톡톡:{meta['has_talktalk']}  쿠폰:{meta['has_coupon']}")

        # Step 1: 리뷰 탭
        print(f"  📝 리뷰 탭: {url_review}")
        await page.goto(url_review, wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(4000)
        await dismiss_popups(page)

        frame = await find_entry_frame(page)
        if frame is None:
            result["error"] = "iframe 탐색 실패"
            return result
        print(f"  🖼  iframe: {frame.url[:80]}")
        await page.wait_for_timeout(3000)

        # 스크롤 수집
        seen: set = set()
        dom_reviews = []
        no_new_streak = 0

        print(f"  🔄 스크롤 수집 시작 (목표: {MAX_REVIEWS_PER_PLACE}건)")
        for scroll_n in range(200):
            visible = await extract_visible_reviews(frame)
            new_count = 0
            for rv in visible:
                key = rv["text"][:80]
                if key not in seen:
                    seen.add(key)
                    dom_reviews.append(rv)
                    new_count += 1

            if scroll_n % 10 == 0:
                print(f"  [{scroll_n:3d}회] 수집: {len(dom_reviews)}건")

            more_clicked = False
            for btn_sel in ["a.fvwqf","button.fvwqf","a[class*='more']","button[class*='more']",
                            "a.place_more_btn",".pui__DP0WBr"]:
                try:
                    btns = await frame.query_selector_all(btn_sel)
                    for btn in btns:
                        if not await btn.is_visible():
                            continue
                        if "더보기" not in (await btn.inner_text()).strip():
                            continue
                        await btn.click()
                        await page.wait_for_timeout(2000)
                        more_clicked = True
                        break
                    if more_clicked:
                        break
                except Exception:
                    pass

            scroll_target = await frame.evaluate(SCROLL_JS, 1500)
            if scroll_n == 0:
                print(f"  📍 스크롤 타겟: {scroll_target}")

            await page.wait_for_timeout(int(SCROLL_PAUSE * 1000))

            if new_count == 0 and not more_clicked:
                no_new_streak += 1
                if no_new_streak >= 8:
                    print(f"  ⏹  8회 연속 새 리뷰 없음 → 종료")
                    break
            else:
                no_new_streak = 0

            if len(dom_reviews) >= MAX_REVIEWS_PER_PLACE:
                print(f"  ✅ 목표 도달: {len(dom_reviews)}건")
                break

        print(f"  📄 DOM 수집 완료: {len(dom_reviews)}건")

        if len(api_reviews) > len(dom_reviews):
            result["reviews"] = api_reviews[:MAX_REVIEWS_PER_PLACE]
            result["source"]  = f"api({len(api_reviews)}건)"
        elif dom_reviews:
            result["reviews"] = dom_reviews[:MAX_REVIEWS_PER_PLACE]
            result["source"]  = f"dom({len(dom_reviews)}건)"
        else:
            result["source"] = "none"

        result["total_collected"] = len(result["reviews"])

        SHOT_DIR.mkdir(exist_ok=True)
        await page.screenshot(path=str(SHOT_DIR / f"{rank}_reviews.png"))
        print(f"  📸 스크린샷 저장  ✅ 최종: {result['total_collected']}건")

    except Exception as e:
        print(f"  ❌ 오류: {e}")
        result["error"] = str(e)
    finally:
        page.remove_listener("response", on_response)

    return result


def analyze_keywords(reviews: list) -> dict:
    all_text = " ".join(r["text"] for r in reviews)
    words = re.findall(r"[가-힣]{2,6}", all_text)
    word_freq = Counter(w for w in words if w not in STOPWORDS)
    tokens = [w for w in words if w not in STOPWORDS]
    bigrams = [f"{tokens[i]} {tokens[i+1]}" for i in range(len(tokens)-1)]
    topic_counts = {t: sum(all_text.count(k) for k in kws) for t, kws in TOPIC_MAP.items()}
    pos_cnt = sum(all_text.count(k) for k in POSITIVE_SIGNALS)
    neg_cnt = sum(all_text.count(k) for k in NEGATIVE_SIGNALS)
    ratings = [r["rating"] for r in reviews if r.get("rating")]
    rating_dist: dict = {}
    for rr in ratings:
        try:
            key = str(float(str(rr)))
            rating_dist[key] = rating_dist.get(key, 0) + 1
        except Exception:
            pass
    return {
        "word_freq":    word_freq.most_common(50),
        "bigram_freq":  Counter(bigrams).most_common(30),
        "topic_counts": topic_counts,
        "pos_cnt":      pos_cnt,
        "neg_cnt":      neg_cnt,
        "rating_dist":  rating_dist,
    }


def generate_review_report(all_results: list) -> str:
    W = 65
    buf = []

    def sep(title=""):
        buf.append("\n" + "─" * W)
        if title:
            buf.append(f" {title}")
            buf.append("─" * W)

    buf.append("=" * W)
    buf.append("  네이버 플레이스 리뷰 키워드 분석 리포트")
    buf.append(f"  생성: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    buf.append("=" * W)

    sep("[ 수집 현황 ]")
    total = 0
    for r in all_results:
        n = r["total_collected"]
        total += n
        buf.append(f"  {r['rank']:6s} | {r['name']:22s} | {n:>4}건 | 소스: {r.get('source','?')}")
    buf.append(f"\n  전체 수집 리뷰: {total}건")

    sep("[ 1 ] 업체별 리뷰 키워드 Top 20")
    analyses: dict = {}
    for r in all_results:
        if not r["reviews"]:
            buf.append(f"\n  [{r['rank']}] {r['name']}: 리뷰 없음")
            continue
        ana = analyze_keywords(r["reviews"])
        analyses[r["rank"]] = ana
        buf.append(f"\n  ┌ [{r['rank']}] {r['name']} ({r['total_collected']}건)")
        rows = [f"{w}({c})" for w, c in ana["word_freq"][:20]]
        buf.append("  │ 상위 키워드:")
        for i in range(0, len(rows), 5):
            buf.append("  │   " + "  ".join(rows[i:i+5]))
        sorted_topics = sorted(ana["topic_counts"].items(), key=lambda x: -x[1])
        buf.append("  │ 토픽별 언급:")
        for topic, cnt in sorted_topics:
            if cnt > 0:
                buf.append(f"  │   {topic:12s}: {cnt:>4}회 {'█' * min(cnt // 3, 15)}")
        buf.append("  └" + "─" * (W - 4))

    sep("[ 2 ] 전체 합산 키워드 Top 30")
    all_flat = [r for res in all_results for r in res["reviews"]]
    if all_flat:
        total_ana = analyze_keywords(all_flat)
        rows = [f"{w}({c})" for w, c in total_ana["word_freq"][:30]]
        buf.append("\n  ▶ Top 30 키워드:")
        for i in range(0, len(rows), 5):
            buf.append("    " + "  ".join(rows[i:i+5]))

    buf.append("\n" + "=" * W)
    return "\n".join(buf)


async def scraper_main():
    print("=" * 55)
    print("  네이버 플레이스 리뷰 수집기")
    print("=" * 55)

    all_results = []
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=False, slow_mo=80,
            args=["--lang=ko-KR", "--no-sandbox"],
        )
        context = await browser.new_context(
            locale="ko-KR", timezone_id="Asia/Seoul",
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/122.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1400, "height": 900},
        )
        page = await context.new_page()

        for rank, info in PLACES.items():
            result = await scrape_reviews(page, rank, info)
            all_results.append(result)
            await asyncio.sleep(3)

        await browser.close()

    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2)
    print(f"\n✅ JSON 저장: {OUT_JSON}")

    report = generate_review_report(all_results)
    with open(OUT_REPORT, "w", encoding="utf-8") as f:
        f.write(report)
    print(f"✅ 리포트 저장: {OUT_REPORT}")


# ══════════════════════════════════════════════════════════════════
# ██  FLASK 웹앱 모듈
# ══════════════════════════════════════════════════════════════════

app = Flask(__name__)
BRANCHES_DIR = Path("branches")
BRANCHES_DIR.mkdir(exist_ok=True)

KW_TO_SENTENCE = [
    ("트레이너",  "트레이너가 친절하고 전문적이에요"),
    ("선생님",   "선생님이 꼼꼼하게 케어해 줘요"),
    ("코치",     "코치진이 전문적이에요"),
    ("pt",       "PT 프로그램이 효과적이에요"),
    ("피티",     "PT 수업이 만족스러워요"),
    ("기구",     "운동 기구가 다양해요"),
    ("머신",     "머신 종류가 많아요"),
    ("덤벨",     "덤벨 구성이 잘 돼 있어요"),
    ("러닝",     "유산소 기구가 충분해요"),
    ("넓",       "공간이 넓어 쾌적해요"),
    ("깨끗",     "시설이 깨끗해요"),
    ("청결",     "청결하게 관리돼요"),
    ("냄새",     "냄새가 없어요"),
    ("가성비",   "가성비가 좋아요"),
    ("가격",     "가격이 합리적이에요"),
    ("저렴",     "저렴하게 이용할 수 있어요"),
    ("일일권",   "일일권 이용이 편해요"),
    ("역",       "역에서 가까워요"),
    ("주차",     "주차하기 편해요"),
    ("친절",     "직원이 친절해요"),
    ("분위기",   "분위기가 좋아요"),
    ("인테리어", "인테리어가 깔끔해요"),
    ("샤워",     "샤워 시설이 쾌적해요"),
    ("락커",     "락커룸이 편해요"),
    ("붐비",     "혼잡하지 않아요"),
    ("한적",     "한적하게 운동할 수 있어요"),
    ("다양",     "다양한 기구를 이용할 수 있어요"),
    ("24시",     "24시간 이용 가능해요"),
    ("새벽",     "새벽 시간대에도 이용해요"),
    ("효과",     "운동 효과가 좋아요"),
    ("감량",     "다이어트 효과가 있어요"),
    ("체형",     "체형 교정에 도움이 돼요"),
]


def extract_place_id(url: str) -> str:
    try:
        if req_lib and "naver.me" in url:
            r = req_lib.get(url, allow_redirects=True, timeout=10,
                            headers={"User-Agent": "Mozilla/5.0"})
            url = r.url
        m = re.search(r'/place/(\d+)', url)
        return m.group(1) if m else ""
    except Exception:
        return ""


def safe_folder_name(name: str) -> str:
    return re.sub(r'[<>:"/\\|?*\s]', '_', name).strip('_')


def get_branches():
    result = []
    if not BRANCHES_DIR.exists():
        return result
    for folder in sorted(BRANCHES_DIR.iterdir(), key=lambda x: x.stat().st_mtime, reverse=True):
        if not folder.is_dir():
            continue
        cfg = folder / "config.json"
        if not cfg.exists():
            continue
        try:
            config = json.loads(cfg.read_text(encoding="utf-8"))
        except Exception:
            continue

        review_count = 0
        if (folder / "reviews.json").exists():
            try:
                data = json.loads((folder / "reviews.json").read_text(encoding="utf-8"))
                review_count = sum(r.get("total_collected", 0) for r in data)
            except Exception:
                pass

        status = "none"
        if (folder / "progress.json").exists():
            try:
                status = json.loads((folder / "progress.json").read_text(encoding="utf-8")).get("status", "none")
            except Exception:
                pass

        result.append({
            "folder":           folder.name,
            "name":             config.get("branch_name", folder.name),
            "created":          config.get("created", ""),
            "has_data":         review_count > 0,
            "review_count":     review_count,
            "competitor_count": len(config.get("competitors", [])),
            "status":           status,
        })
    return result


def analyze_reviews(reviews: list) -> dict:
    all_text = " ".join(r.get("text", "") for r in reviews)
    words = re.findall(r"[가-힣]{2,6}", all_text)
    word_freq = Counter(w for w in words if w not in STOPWORDS)
    tokens = [w for w in words if w not in STOPWORDS]
    bigrams = [f"{tokens[i]} {tokens[i+1]}" for i in range(len(tokens) - 1)]
    topic_counts = {
        t: sum(all_text.count(k) for k in kws)
        for t, kws in TOPIC_MAP.items()
    }
    return {
        "word_freq":    word_freq.most_common(20),
        "bigram_freq":  Counter(bigrams).most_common(10),
        "topic_counts": topic_counts,
        "top_topics":   [t for t, _ in sorted(topic_counts.items(), key=lambda x: -x[1]) if topic_counts[t] > 0],
    }


def compute_match(intro: str, top_words: list) -> dict:
    matched, unmatched = [], []
    for kw, cnt in top_words:
        (matched if kw in intro else unmatched).append({"kw": kw, "cnt": cnt})
    total = len(top_words)
    rate = round(len(matched) / total * 100) if total else 0
    return {"matched": matched, "unmatched": unmatched, "rate": rate, "total": total}


def compute_multi_source_match(top_words: list, intro: str, posts: str, menu: str) -> dict:
    result_any, result_unmatched = [], []
    intro_count = posts_count = menu_count = 0
    for kw, cnt in top_words:
        in_intro = kw in intro
        in_posts = kw in posts
        in_menu  = kw in menu
        in_any   = in_intro or in_posts or in_menu
        item = {"kw": kw, "cnt": cnt, "intro": in_intro, "posts": in_posts, "menu": in_menu}
        if in_intro: intro_count += 1
        if in_posts: posts_count += 1
        if in_menu:  menu_count  += 1
        if in_any:   result_any.append(item)
        else:        result_unmatched.append(item)
    total = len(top_words)
    return {
        "total":         total,
        "intro_rate":    round(intro_count / total * 100) if total else 0,
        "posts_rate":    round(posts_count / total * 100) if total else 0,
        "menu_rate":     round(menu_count  / total * 100) if total else 0,
        "combined_rate": round(len(result_any) / total * 100) if total else 0,
        "matched_any":   result_any,
        "unmatched":     result_unmatched,
    }


def _pearson(x: list, y: list) -> float:
    n = len(x)
    if n < 2:
        return 0.0
    mx, my = sum(x) / n, sum(y) / n
    num = sum((x[i] - mx) * (y[i] - my) for i in range(n))
    dx  = sum((v - mx) ** 2 for v in x) ** 0.5
    dy  = sum((v - my) ** 2 for v in y) ** 0.5
    return round(num / (dx * dy), 3) if dx * dy else 0.0


def compute_hypothesis_validation(data: list) -> dict:
    ranked = []
    for p in data:
        m = re.match(r'^(\d+)위$', p.get("rank", ""))
        if not m:
            continue
        mm = p.get("multi_match")
        if not mm:
            continue
        ranked.append({
            "rank":          int(m.group(1)),
            "name":          p["name"],
            "combined_rate": mm["combined_rate"],
            "intro_rate":    mm["intro_rate"],
            "posts_rate":    mm["posts_rate"],
            "menu_rate":     mm["menu_rate"],
        })
    my_item = next(
        ({"name": p["name"],
          "combined_rate": p["multi_match"]["combined_rate"],
          "intro_rate":    p["multi_match"]["intro_rate"],
          "posts_rate":    p["multi_match"]["posts_rate"],
          "menu_rate":     p["multi_match"]["menu_rate"],
         } for p in data if p.get("rank") == "내 업체" and p.get("multi_match")),
        None
    )
    if len(ranked) < 2:
        return {"status": "insufficient_data", "ranked": ranked, "my": my_item}

    ranks = [r["rank"] for r in ranked]
    rates = [r["combined_rate"] for r in ranked]
    r_val = _pearson(ranks, rates)
    abs_r    = abs(r_val)
    strength = "강한" if abs_r >= 0.7 else ("중간 수준의" if abs_r >= 0.4 else "약한")
    supported = r_val < -0.3
    verdict   = "✅ 가설을 지지합니다" if supported else (
                "⚠️ 가설을 부분적으로 지지합니다" if r_val < 0 else
                "❌ 가설과 반대 경향이 나타납니다")
    return {
        "status": "ok", "r": r_val, "abs_r": abs_r,
        "strength": strength, "supported": supported,
        "verdict": verdict, "n": len(ranked),
        "ranked": ranked, "my": my_item,
    }


def parse_naver_date(date_str: str):
    if not date_str:
        return None
    from datetime import timedelta
    now = datetime.now()
    try:
        m = re.search(r'(\d+)일\s*전', date_str)
        if m:
            return now - timedelta(days=int(m.group(1)))
        m = re.search(r'(\d+)주\s*전', date_str)
        if m:
            return now - timedelta(weeks=int(m.group(1)))
        m = re.search(r'(\d+)개월\s*전', date_str)
        if m:
            return now - timedelta(days=int(m.group(1)) * 30)
        m = re.search(r'(\d{4})[.\-년]\s*(\d{1,2})(?:[.\-월]\s*(\d{1,2}))?', date_str)
        if m:
            year  = int(m.group(1))
            month = int(m.group(2))
            day   = int(m.group(3)) if m.group(3) else 1
            return datetime(year, month, day)
        m = re.match(r'^(\d{1,2})\.(\d{1,2})\.', date_str.strip())
        if m:
            month = int(m.group(1))
            day   = int(m.group(2))
            year  = now.year
            candidate = datetime(year, month, day)
            if candidate > now:
                candidate = datetime(year - 1, month, day)
            return candidate
    except Exception:
        pass
    return None


def compute_review_quality(reviews: list) -> dict:
    if not reviews:
        return None
    lengths = [len(r.get("text", "")) for r in reviews]
    avg_len = round(sum(lengths) / len(lengths))
    rich_count = sum(1 for l in lengths if l >= 50)
    rich_pct = round(rich_count / len(lengths) * 100)
    now = datetime.now()
    dated_dates = []
    for r in reviews:
        d = parse_naver_date(r.get("date", ""))
        if d:
            dated_dates.append(d)
    dated_count = len(dated_dates)
    if dated_count >= 2:
        oldest = min(dated_dates)
        span_days = max((now - oldest).days, 1)
        monthly_rate = round(dated_count / (span_days / 30), 1)
    else:
        monthly_rate = None
    recent_count = sum(1 for d in dated_dates if (now - d).days <= 90)
    recent_pct = round(recent_count / dated_count * 100) if dated_count > 0 else None
    ratings = []
    for r in reviews:
        raw = str(r.get("rating", "")).replace("점", "").strip()
        try:
            v = float(raw)
            if 1 <= v <= 5:
                ratings.append(v)
        except Exception:
            pass
    avg_rating = round(sum(ratings) / len(ratings), 1) if ratings else None
    return {
        "avg_len": avg_len, "rich_count": rich_count, "rich_pct": rich_pct,
        "recent_count": recent_count, "recent_pct": recent_pct,
        "monthly_rate": monthly_rate, "dated_count": dated_count,
        "avg_rating": avg_rating, "total": len(reviews),
    }


def compute_length_std(reviews: list):
    lengths = [len(r.get("text", "")) for r in reviews if r.get("text")]
    if len(lengths) < 2:
        return None
    n = len(lengths)
    mean = sum(lengths) / n
    variance = sum((x - mean) ** 2 for x in lengths) / (n - 1)
    return round(variance ** 0.5, 1)


def compute_vocab_diversity(reviews: list):
    all_text = " ".join(r.get("text", "") for r in reviews)
    words = re.findall(r"[가-힣]{2,6}", all_text)
    tokens = [w for w in words if w not in STOPWORDS]
    if len(tokens) < 10:
        return None
    return round(len(set(tokens)) / len(tokens), 3)


def compute_new_info_count(reviews: list, intro: str):
    if not reviews:
        return None
    all_text = " ".join(r.get("text", "") for r in reviews)
    words = re.findall(r"[가-힣]{2,6}", all_text)
    word_freq = Counter(w for w in words if w not in STOPWORDS)
    top_20 = [w for w, _ in word_freq.most_common(20)]
    return sum(1 for w in top_20 if w not in intro)


def make_keyword_sentences(word_freq: list) -> list:
    sentences = []
    seen_sentences = set()
    for kw, cnt in word_freq:
        kw_lower = kw.lower()
        for key, sentence in KW_TO_SENTENCE:
            if key in kw_lower and sentence not in seen_sentences:
                sentences.append({"sentence": sentence, "kw": kw, "count": cnt})
                seen_sentences.add(sentence)
                break
        if len(sentences) >= 8:
            break
    return sentences


def generate_quality_insight(data: list) -> str:
    if not data:
        return ""
    places = [p for p in data if p.get("quality")]
    if len(places) < 2:
        return ""
    insights = []
    monthly = [(p, p["quality"]["monthly_rate"]) for p in places if p["quality"].get("monthly_rate")]
    if len(monthly) >= 2:
        monthly.sort(key=lambda x: -x[1])
        fastest = monthly[0]
        slowest = monthly[-1]
        insights.append(
            f"리뷰 속도가 가장 빠른 업체는 <strong>{fastest[0]['name']}</strong>(월 {fastest[1]}건)이며, "
            f"<strong>{slowest[0]['name']}</strong>(월 {slowest[1]}건)과 비교해 "
            f"{round(fastest[1]/max(slowest[1],0.1), 1)}배 차이가 납니다."
        )
    for p in places:
        q = p["quality"]
        mr = q.get("monthly_rate") or 0
        rich = q.get("rich_pct", 0)
        avg_l = q.get("avg_len", 0)
        if mr < 20 and rich >= 75 and avg_l >= 120:
            insights.append(
                f"<strong>{p['name']}</strong>은 월 {mr}건으로 속도는 느리지만 "
                f"평균 길이 {avg_l}자, 정보형 비중 {rich}%로 진정성 있는 후기가 집중된 업체입니다."
            )
    return " ".join(insights)


def load_branch_data(folder: Path, config: dict):
    reviews_path = folder / "reviews.json"
    if not reviews_path.exists():
        return None

    raw = json.loads(reviews_path.read_text(encoding="utf-8"))

    my_place = config.get("my_place", {})
    intro_map, posts_map, menu_map, blog_map = {}, {}, {}, {}
    intro_map["내 업체"] = my_place.get("intro", "")
    posts_map["내 업체"] = my_place.get("posts", "")
    menu_map["내 업체"]  = my_place.get("menu", "")
    blog_map["내 업체"]  = my_place.get("blog_count", 0)
    for i, c in enumerate(config.get("competitors", []), 1):
        key = f"{i}위"
        intro_map[key] = c.get("intro", "")
        posts_map[key] = c.get("posts", "")
        menu_map[key]  = c.get("menu", "")
        blog_map[key]  = c.get("blog_count", 0)

    result = []
    for place in raw:
        rank    = place.get("rank", "")
        reviews = place.get("reviews", [])
        ana     = analyze_reviews(reviews) if reviews else None
        intro   = intro_map.get(rank, "")
        posts   = posts_map.get(rank, "")
        menu    = menu_map.get(rank, "")

        result.append({
            "rank":          rank,
            "name":          place.get("name", ""),
            "total":         place.get("total_collected", 0),
            "source":        place.get("source", ""),
            "analysis":      ana,
            "match":         compute_match(intro, ana["word_freq"]) if (ana and intro) else None,
            "multi_match":   compute_multi_source_match(ana["word_freq"], intro, posts, menu) if ana else None,
            "quality":       compute_review_quality(reviews) if reviews else None,
            "blog_count":    blog_map.get(rank, 0),
            "sentences":     make_keyword_sentences(ana["word_freq"]) if ana else [],
            "length_std":    compute_length_std(reviews) if reviews else None,
            "vocab_div":     compute_vocab_diversity(reviews) if reviews else None,
            "new_info_count": compute_new_info_count(reviews, intro) if reviews else None,
            "meta": {
                "has_n_booking": place.get("has_n_booking", False),
                "has_talktalk":  place.get("has_talktalk", False),
                "has_coupon":    place.get("has_coupon", False),
                "coupon_name":   place.get("coupon_name"),
                "coupon_type":   place.get("coupon_type"),
            },
        })
    return result


# ── Flask 라우트 ───────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html", branches=get_branches())

@app.route("/new")
def new_branch():
    return render_template("setup.html")

@app.route("/api/extract-id", methods=["POST"])
def api_extract_id():
    url = request.json.get("url", "")
    pid = extract_place_id(url)
    return jsonify({"place_id": pid, "ok": bool(pid)})

@app.route("/api/suggest-folder", methods=["POST"])
def api_suggest_folder():
    name = request.json.get("name", "")
    suggestion = safe_folder_name(name)
    if (BRANCHES_DIR / suggestion).exists():
        suggestion = f"{suggestion}_{datetime.now().strftime('%m%d')}"
    return jsonify({"folder": suggestion})

@app.route("/api/setup", methods=["POST"])
def api_setup():
    data = request.json
    folder_name = safe_folder_name(data.get("folder_name", "branch"))
    folder = BRANCHES_DIR / folder_name
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "screenshots").mkdir(exist_ok=True)

    config = {
        "branch_name": data["branch_name"],
        "folder_name": folder_name,
        "created":     datetime.now().strftime("%Y-%m-%d %H:%M"),
        "max_reviews": int(data.get("max_reviews", 300)),
        "my_place": {
            "id":         data["my_place_id"],
            "name":       data["branch_name"],
            "intro":      data.get("intro", ""),
            "posts":      data.get("my_posts", ""),
            "menu":       data.get("my_menu", ""),
            "keywords":   [k.strip() for k in data.get("keywords", "").split(",") if k.strip()],
            "blog_count": int(data.get("my_blog_count", 0)),
        },
        "competitors": data.get("competitors", []),
    }
    (folder / "config.json").write_text(
        json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return jsonify({"ok": True, "folder": folder_name})

@app.route("/branch/<folder_name>")
def branch(folder_name):
    folder = BRANCHES_DIR / folder_name
    if not (folder / "config.json").exists():
        return redirect(url_for("index"))

    config = json.loads((folder / "config.json").read_text(encoding="utf-8"))
    data   = load_branch_data(folder, config)

    progress = {"status": "none"}
    if (folder / "progress.json").exists():
        try:
            progress = json.loads((folder / "progress.json").read_text(encoding="utf-8"))
        except Exception:
            pass

    comp_stats = None
    if data:
        my    = next((d for d in data if d["rank"] == "내 업체"), None)
        comps = [d for d in data if d["rank"] != "내 업체" and d.get("match")]
        if my and comps:
            comp_avg = round(sum(c["match"]["rate"] for c in comps) / len(comps))
            comp_stats = {
                "my_rate":  my["match"]["rate"] if my.get("match") else None,
                "comp_avg": comp_avg,
                "diff":     (my["match"]["rate"] if my.get("match") else 0) - comp_avg,
            }

    return render_template("branch.html",
        config=config, folder_name=folder_name,
        data=data, progress=progress,
        topic_keys=list(TOPIC_MAP.keys()),
        comp_stats=comp_stats,
        quality_insight=generate_quality_insight(data) if data else "",
        hypothesis=compute_hypothesis_validation(data) if data else None,
    )

@app.route("/api/run/<folder_name>", methods=["POST"])
def run_analysis(folder_name):
    folder = BRANCHES_DIR / folder_name
    if not (folder / "config.json").exists():
        return jsonify({"error": "지점 없음"}), 404

    config = json.loads((folder / "config.json").read_text(encoding="utf-8"))

    places = {}
    for i, c in enumerate(config.get("competitors", []), 1):
        places[f"{i}위"] = {"id": c["id"], "name": c["name"]}
    places["내 업체"] = {"id": config["my_place"]["id"], "name": config["branch_name"]}

    scraper_cfg = {
        "places":     places,
        "output_dir": str(folder.resolve()),
        "max_reviews": config.get("max_reviews", 300),
    }
    cfg_path = folder / "scraper_config.json"
    cfg_path.write_text(json.dumps(scraper_cfg, ensure_ascii=False, indent=2), encoding="utf-8")

    (folder / "progress.json").write_text(
        json.dumps({"status": "running", "started": datetime.now().isoformat()}, ensure_ascii=False),
        encoding="utf-8"
    )

    # 이 파일 자체를 스크레이퍼 모드로 subprocess 실행
    this_file = Path(__file__).resolve()

    def run():
        log_path = folder / "scraper.log"
        try:
            with open(log_path, "w", encoding="utf-8") as log_f:
                env = os.environ.copy()
                env["PYTHONIOENCODING"] = "utf-8"
                proc = subprocess.Popen(
                    [sys.executable, "-X", "utf8", str(this_file), str(cfg_path)],
                    stdout=log_f, stderr=subprocess.STDOUT,
                    encoding="utf-8", text=True, env=env,
                )
                proc.wait(timeout=7200)
            status = "done" if proc.returncode == 0 else "error"
        except Exception as e:
            status = "error"
            log_path.write_text(str(e), encoding="utf-8")

        (folder / "progress.json").write_text(
            json.dumps({"status": status, "finished": datetime.now().isoformat()}, ensure_ascii=False),
            encoding="utf-8"
        )

    threading.Thread(target=run, daemon=True).start()
    return jsonify({"ok": True})

@app.route("/api/progress/<folder_name>")
def get_progress(folder_name):
    folder = BRANCHES_DIR / folder_name
    result = {"status": "none", "log": ""}

    if (folder / "progress.json").exists():
        try:
            result = json.loads((folder / "progress.json").read_text(encoding="utf-8"))
        except Exception:
            pass

    log_path = folder / "scraper.log"
    if log_path.exists():
        try:
            lines = log_path.read_text(encoding="utf-8").split("\n")
            result["log"] = "\n".join(lines[-40:])
        except Exception:
            pass

    return jsonify(result)

@app.route("/api/delete/<folder_name>", methods=["DELETE"])
def delete_branch(folder_name):
    import shutil
    folder = BRANCHES_DIR / folder_name
    if folder.exists():
        shutil.rmtree(folder)
    return jsonify({"ok": True})


# ══════════════════════════════════════════════════════════════════
# ██  진입점 — argv[1]이 있으면 스크레이퍼, 없으면 웹 서버
# ══════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    if len(sys.argv) > 1 and Path(sys.argv[1]).exists():
        # ── 스크레이퍼 모드 (웹앱에서 subprocess로 호출될 때)
        asyncio.run(scraper_main())
    else:
        # ── 웹 서버 모드
        print("\n" + "=" * 50)
        print("  짐박스 SEO 분석 플랫폼")
        print("  http://localhost:5000 에서 접속하세요")
        print("  종료: Ctrl+C")
        print("=" * 50 + "\n")
        app.run(debug=False, port=5000, use_reloader=False)
