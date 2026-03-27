# -*- coding: utf-8 -*-
"""
네이버 플레이스 리뷰 수집 + 키워드 분석기
────────────────────────────────────────────────────────────────
전략:
  1) 네트워크 인터셉트 → Naver 리뷰 API JSON 직접 캡처 (1차)
  2) DOM 스크롤 수집 → 화면에 렌더링된 리뷰 텍스트 수집 (2차)
  3) 수집된 리뷰 전체 키워드 빈도 분석
  4) 업체별 / 전체 비교 리포트 생성

설치:
  pip install playwright
  playwright install chromium

실행 (직접):
  python naver_review_scraper.py

실행 (웹앱에서 config 파일 전달):
  python naver_review_scraper.py path/to/scraper_config.json
"""

import asyncio
import json
import re
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

from playwright.async_api import async_playwright, Response

# ──────────────────────────────────────────────────────────────
# 외부 config 파일 지원 (웹앱에서 sys.argv[1]로 경로 전달)
# ──────────────────────────────────────────────────────────────
_EXT_CONFIG = {}
if len(sys.argv) > 1:
    try:
        _cfg_path = Path(sys.argv[1])
        _EXT_CONFIG = json.loads(_cfg_path.read_text(encoding="utf-8"))
        print(f"[CONFIG] 외부 설정 로드: {_cfg_path}")
    except Exception as _e:
        print(f"[CONFIG] 설정 파일 로드 실패: {_e}")

# ──────────────────────────────────────────────────────────────
# 수집 대상 업체 (외부 config 없으면 기본값 사용)
# ──────────────────────────────────────────────────────────────
PLACES = _EXT_CONFIG.get("places", {
    "1위":    {"id": "13155391",    "name": "맥스XX 피트니스 건대점"},
    "2위":    {"id": "1166532147",  "name": "에이블짐 건대구의역점"},
    "3위":    {"id": "1219319598",  "name": "스XX 구의역점"},
    "4위":    {"id": "1083518673",  "name": "포스보이스XX 건대스포아트"},
    "5위":    {"id": "1056155482",  "name": "피트니스파이 우먼 건대점"},
    "내 업체": {"id": "1100555051",  "name": "짐박스피트니스 건대구의점"},
})

MAX_REVIEWS_PER_PLACE = int(_EXT_CONFIG.get("max_reviews", 100))
SCROLL_PAUSE = 1.5            # 스크롤 간 대기(초)

# 출력 경로 (외부 config에 output_dir이 있으면 해당 폴더에 저장)
_OUT_DIR = Path(_EXT_CONFIG["output_dir"]) if "output_dir" in _EXT_CONFIG else Path(".")
OUT_JSON   = str(_OUT_DIR / "reviews.json")
OUT_REPORT = str(_OUT_DIR / "review_report.txt")
SHOT_DIR   = _OUT_DIR / "screenshots"

# ──────────────────────────────────────────────────────────────
# 한국어 불용어
# ──────────────────────────────────────────────────────────────
STOPWORDS = {
    # 조사·접속사
    "있습니다","합니다","입니다","드립니다","있어요","해요","해드립니다",
    "이고","이며","그리고","그런데","하지만","그래서","이라","에서",
    "으로","위해","하여","하는","하고","하면","하다","한다","되어",
    "때문","정말","너무","매우","아주","조금","좀더","진짜","완전",
    "했어요","했습니다","해서","해요","인데","이에","데요","고요",
    # 일반 동사·형용사
    "좋아요","좋습니다","좋은","좋고","같아요","같습니다","없어요",
    "있고","없고","나왔어요","됩니다","됐어요","받았어요","생각해요",
    "느껴","느낌","같은","이번","처음","다음","저도","저는","제가",
    # 숫자·기타
    "하나","둘","셋","넷","다섯","한번","두번","몇번","번째",
    "여기","거기","이곳","저곳","이런","저런","그런","어떤",
    "갔어요","갔다","왔어요","왔다","봤어요","봤다","했다",
}

# ──────────────────────────────────────────────────────────────
# 헬스장 업종 긍정·부정 시그널
# ──────────────────────────────────────────────────────────────
POSITIVE_SIGNALS = [
    "친절","깔끔","넓","쾌적","만족","좋","최고","추천","훌륭","완벽",
    "전문","체계","효과","변화","결과","성과","뷰","힐링","편안","여유",
    "합리","가성비","청결","위생","배려","세심","꼼꼼","섬세",
]
NEGATIVE_SIGNALS = [
    "불친절","좁","복잡","불만","아쉬","최악","별로","실망","비싸",
    "붐비","줄","대기","노후","낡","냄새","불결","불편","어둡",
]

# ──────────────────────────────────────────────────────────────
# 헬스장 관심 토픽 카테고리
# ──────────────────────────────────────────────────────────────
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


# ──────────────────────────────────────────────────────────────
# API 응답에서 리뷰 배열 추출
# ──────────────────────────────────────────────────────────────
_DATE_FIELDS = (
    "created", "visitDate", "createdAt", "createdDate", "reviewDate",
    "registerDate", "registDate", "date", "updateDate", "updatedAt",
)

def extract_reviews_from_api(payload) -> list[dict]:
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


# ──────────────────────────────────────────────────────────────
# 쿠폰 유형 분류
# ──────────────────────────────────────────────────────────────
def categorize_coupon(coupon_name: str | None) -> str | None:
    """쿠폰 이름을 4가지 유형으로 분류"""
    if not coupon_name:
        return None
    if re.search(r'무료|체험|1회|OT', coupon_name):
        return "Experience"
    if re.search(r'증정|서비스|음료', coupon_name):
        return "Freebie"
    if re.search(r'%|할인|원', coupon_name):
        return "Discount"
    return "Conditional"


# ──────────────────────────────────────────────────────────────
# 홈 탭 메타데이터 추출
# ──────────────────────────────────────────────────────────────
async def extract_place_metadata(frame) -> dict:
    """홈 탭 frame에서 N예약·톡톡·쿠폰 버튼 유무 추출"""
    default = {
        "has_n_booking": False,
        "has_talktalk":  False,
        "has_coupon":    False,
        "coupon_name":   None,
    }
    if frame is None:
        return default
    try:
        meta = await frame.evaluate(METADATA_JS)
        return meta
    except Exception as e:
        print(f"  ⚠  메타데이터 추출 실패: {e}")
        return default


# ──────────────────────────────────────────────────────────────
# iframe 탐색 헬퍼
# ──────────────────────────────────────────────────────────────
async def find_entry_frame(page, timeout_sec: int = 20):
    """리뷰 콘텐츠가 실제로 있는 frame을 반환 (URL 기반 아닌 콘텐츠 기반 탐색).

    네이버 플레이스 패널은 map.naver.com 하위 iframe으로 로드되며
    도메인이 동일해 URL로는 구분이 어렵기 때문에
    실제 요소 존재 여부로 판별.
    """
    # 탐색 우선순위: 리뷰 관련 요소가 있는 frame
    PROBE_SELS = [
        "a.fvwqf",                  # 펼쳐서 더보기 버튼 (리뷰 탭 전용)
        "a._tab-menu[data-index='3']",  # 리뷰 탭 메뉴
        "li.pui__X35jYm",           # 리뷰 아이템
        "a[role='tab']",            # 탭 메뉴 일반
    ]

    for attempt in range(timeout_sec):
        frames = page.frames

        # main frame(page.main_frame) 제외한 sub-frame 우선 탐색
        sub_frames = [f for f in frames
                      if f != page.main_frame and f.url not in ("about:blank", "")]

        for f in sub_frames:
            for sel in PROBE_SELS:
                try:
                    el = await f.query_selector(sel)
                    if el:
                        print(f"  🖼  frame 발견 (셀렉터: {sel}): {f.url[:70]}")
                        return f
                except Exception:
                    pass

        # sub-frame에서 못 찾으면 main frame도 시도
        for sel in PROBE_SELS:
            try:
                el = await page.main_frame.query_selector(sel)
                if el:
                    print(f"  🖼  main frame에서 콘텐츠 발견 (셀렉터: {sel})")
                    return page.main_frame
            except Exception:
                pass

        if attempt % 5 == 0:
            urls = [f.url[:70] for f in frames if f.url not in ("about:blank", "")]
            print(f"  🔍 [{attempt}s] frames({len(frames)}개): {urls}")

        await page.wait_for_timeout(1000)

    print("  ❌ 리뷰 콘텐츠를 가진 frame을 찾지 못했습니다.")
    return None


# ──────────────────────────────────────────────────────────────
# iframe 내부 스크롤 컨테이너를 찾아 스크롤
# (핵심 수정: window가 아닌 실제 스크롤 div를 타겟)
# ──────────────────────────────────────────────────────────────
SCROLL_JS = """
(amount) => {
    // 네이버 플레이스 리뷰 탭의 실제 스크롤 컨테이너 후보 순서대로 탐색
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
    // 스크롤 가능한 요소를 동적으로 탐색
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

# ──────────────────────────────────────────────────────────────
# 홈 탭 외부 기능 연동 추출 JS
# ──────────────────────────────────────────────────────────────
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


# ──────────────────────────────────────────────────────────────
# 리뷰 탭으로 이동
# ──────────────────────────────────────────────────────────────
async def dismiss_popups(page) -> None:
    """메인 페이지에 뜨는 팝업(거리뷰 설정 등)을 닫음"""
    popup_close_sels = [
        "button.panorama_config_popup_btn_close",   # 거리뷰 설정 팝업 (실제 확인값)
        "button[class*='popup_btn_close']",
        "button[class*='close']",
        ".popup_close",
    ]
    for sel in popup_close_sels:
        try:
            btn = await page.query_selector(sel)
            if btn and await btn.is_visible():
                await btn.click()
                await page.wait_for_timeout(800)
                print(f"  🔕 팝업 닫기: {sel}")
        except Exception:
            pass


async def navigate_to_review_tab(frame, page) -> bool:
    """iframe 내에서 '리뷰' 탭을 클릭해 리뷰 목록 화면으로 전환.

    실제 확인된 HTML:
      <a href="/place/{id}/review?..." role="tab"
         class="tpj9w _tab-menu" data-index="3">
        <span class="I2hj8">리뷰</span>
      </a>
    """
    # ── 먼저 iframe이 실제로 place 페이지인지 확인 ──────────────
    if "place.map.naver.com" not in frame.url and "place" not in frame.url:
        print(f"  ⚠  frame이 place iframe이 아님: {frame.url[:60]}")
        return False

    # ── 정밀 셀렉터 (실제 HTML 기반, 넓은 패턴 제거) ────────────
    tab_selectors = [
        "a._tab-menu[data-index='3']",      # class + data-index (가장 정확)
        "a[role='tab'][data-index='3']",    # role + data-index
        "a.tpj9w[data-index='3']",         # tpj9w class + data-index
        "a:has(> span.I2hj8)",             # span.I2hj8 직계 자식을 가진 a
        # ↓ 아래부터는 범위가 넓어 iframe 검증 후에만 사용
        "a[href*='/review'][role='tab']",  # href /review + role=tab (슬래시 포함)
    ]

    for sel in tab_selectors:
        try:
            el = await frame.query_selector(sel)
            if el and await el.is_visible():
                # 클릭 전 요소 텍스트 확인 (리뷰 탭이 맞는지 검증)
                text = (await el.inner_text()).strip()
                if "리뷰" not in text and "review" not in (await el.get_attribute("href") or ""):
                    continue
                await el.click()
                await page.wait_for_timeout(2500)
                print(f"  🗂  리뷰 탭 클릭 성공: {sel}  (텍스트: '{text}')")
                return True
        except Exception:
            pass
    return False


# ──────────────────────────────────────────────────────────────
# 현재 화면에서 리뷰 아이템 추출
# ──────────────────────────────────────────────────────────────
async def extract_visible_reviews(frame) -> list[dict]:
    """iframe에서 현재 렌더링된 리뷰 텍스트·별점·날짜 수집"""
    collected: list[dict] = []

    # 리뷰 아이템 컨테이너 후보 (리뷰 탭 전용 셀렉터 포함)
    item_selectors = [
        "li.pui__X35jYm",          # 네이버 방문자 리뷰 아이템
        "li[class*='reviewer']",
        "li[class*='review_item']",
        "div[class*='ReviewItem']",
        "div[class*='review_item']",
        "ul[class*='list'] > li",
        ".pui__vn15t2",
        "li.place_visitor_review",
    ]

    for item_sel in item_selectors:
        try:
            items = await frame.query_selector_all(item_sel)
            if not items:
                continue

            for item in items:
                review: dict = {"text": "", "rating": "", "date": ""}

                # 리뷰 텍스트 — 아이템 내부에서 추출
                text_sels = [
                    "p.pui__xhnDpg",
                    "span.pui__xhnDpg",
                    "div.pui__vn15t2",
                    "[class*='review_text']",
                    "[class*='reviewText']",
                    "[class*='body']",
                    "p", "span.text",
                ]
                for ts in text_sels:
                    try:
                        tel = await item.query_selector(ts)
                        if tel:
                            t = (await tel.inner_text()).strip()
                            if len(t) >= 10:
                                review["text"] = t
                                break
                    except Exception:
                        pass

                # 텍스트가 없으면 아이템 전체 텍스트 시도
                if not review["text"]:
                    full = (await item.inner_text()).strip()
                    # 짧은 UI 레이블 제거 (날짜, 별점 숫자만 있는 경우)
                    if len(full) >= 15 and re.search(r"[가-힣]{3,}", full):
                        review["text"] = full[:500]

                if not review["text"]:
                    continue

                # 별점
                for rs in ["[class*='score']","[class*='rating']","em.num","span.num"]:
                    try:
                        rel = await item.query_selector(rs)
                        if rel:
                            review["rating"] = (await rel.inner_text()).strip()
                            break
                    except Exception:
                        pass

                # 날짜 — <time aria-hidden="true">2.24.화</time> 형식 우선
                for ds in ["time", "[class*='date']", "span.date", "span[class*='time']"]:
                    try:
                        del_el = await item.query_selector(ds)
                        if del_el:
                            review["date"] = (await del_el.inner_text()).strip()
                            break
                    except Exception:
                        pass

                collected.append(review)

            if collected:
                break  # 유효한 셀렉터 찾으면 종료

        except Exception:
            continue

    return collected


# ──────────────────────────────────────────────────────────────
# 단일 업체 리뷰 수집 (수정된 버전)
# ──────────────────────────────────────────────────────────────
async def scrape_reviews(page, rank: str, info: dict) -> dict:
    place_id = info["id"]
    name     = info["name"]

    url_home   = f"https://map.naver.com/p/entry/place/{place_id}"
    url_review = f"https://map.naver.com/p/entry/place/{place_id}?placePath=%2Freview"

    print(f"\n[{rank}] {name}")

    result = {
        "rank": rank, "place_id": place_id, "name": name,
        "reviews": [], "total_collected": 0, "source": "none",
        # 외부 기능 연동 메타데이터
        "has_n_booking": False,
        "has_talktalk":  False,
        "has_coupon":    False,
        "coupon_name":   None,
        "coupon_type":   None,
    }

    # ── 네트워크 인터셉트 (API 리뷰 JSON 캡처) ─────────────────
    api_reviews: list[dict] = []

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
                        print(f"  📡 API 리뷰 {len(found)}건 캡처 ({len(api_reviews)}건 누적)")
        except Exception:
            pass

    page.on("response", on_response)

    try:
        # ── Step 0: 홈 탭 진입 → 외부 기능 연동 메타데이터 추출 ─
        print(f"  🏠 홈 탭 진입: {url_home}")
        await page.goto(url_home, wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(3000)
        await dismiss_popups(page)

        # 홈 탭 iframe 탐색 (최대 8초, 빠른 버전)
        home_frame = None
        for _ in range(8):
            frames = page.frames
            for f in frames:
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
        coupon_info = f" ({meta['coupon_name']})" if meta["coupon_name"] else ""
        print(
            f"  📋 N예약:{meta['has_n_booking']}  "
            f"톡톡:{meta['has_talktalk']}  "
            f"쿠폰:{meta['has_coupon']}{coupon_info}"
        )

        # ── Step 1: 리뷰 탭 URL로 직접 진입 ────────────────────
        print(f"  📝 리뷰 탭 진입: {url_review}")
        await page.goto(url_review, wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(4000)

        # ── Step 2: 팝업 닫기 (거리뷰 설정 등) ──────────────────
        await dismiss_popups(page)

        # ── Step 3: entryIframe 찾기 ─────────────────────────────
        frame = await find_entry_frame(page)
        if frame is None:
            result["error"] = "iframe 탐색 실패"
            return result
        print(f"  🖼  iframe: {frame.url[:80]}")

        # 리뷰 목록 초기 로딩 대기
        await page.wait_for_timeout(3000)

        # ── Step 5: 스크롤 + 리뷰 수집 루프 ─────────────────────
        seen: set[str] = set()
        dom_reviews: list[dict] = []
        no_new_streak = 0
        scroll_amount = 1500

        print(f"  🔄 리뷰 스크롤 수집 시작 (목표: {MAX_REVIEWS_PER_PLACE}건)")

        for scroll_n in range(200):  # 최대 200회 (리뷰 ~300건 커버)

            # 현재 화면 리뷰 추출
            visible = await extract_visible_reviews(frame)
            new_count = 0
            for rv in visible:
                key = rv["text"][:80]   # 앞 80자로 중복 판단
                if key not in seen:
                    seen.add(key)
                    dom_reviews.append(rv)
                    new_count += 1

            # 진행 상황 출력 (10회마다)
            if scroll_n % 10 == 0:
                print(f"  [{scroll_n:3d}회 스크롤] 수집: {len(dom_reviews)}건")

            # 더보기 버튼 클릭 (있을 경우)
            # 확인된 HTML: <a class="fvwqf"><span class="TeItc">펼쳐서 더보기</span></a>
            more_clicked = False
            for btn_sel in [
                "a.fvwqf",                   # 확인된 실제 셀렉터
                "button.fvwqf",
                "a[class*='more']", "button[class*='more']",
                "a.place_more_btn", ".pui__DP0WBr",
            ]:
                try:
                    btns = await frame.query_selector_all(btn_sel)
                    for btn in btns:
                        if not await btn.is_visible():
                            continue
                        btn_text = (await btn.inner_text()).strip()
                        # "펼쳐서 더보기" 또는 일반 "더보기" 버튼만 클릭
                        if "더보기" not in btn_text:
                            continue
                        await btn.click()
                        await page.wait_for_timeout(2000)
                        more_clicked = True
                        break
                    if more_clicked:
                        break
                except Exception:
                    pass

            # iframe 내부 스크롤 컨테이너를 타겟해서 스크롤
            # (핵심: frame.evaluate 로 iframe 내부 JS 실행)
            scroll_target = await frame.evaluate(SCROLL_JS, scroll_amount)
            if scroll_n == 0:
                print(f"  📍 스크롤 타겟: {scroll_target}")

            await page.wait_for_timeout(int(SCROLL_PAUSE * 1000))

            # 새 리뷰가 없으면 streak 증가
            if new_count == 0 and not more_clicked:
                no_new_streak += 1
                if no_new_streak >= 8:
                    print(f"  ⏹  8회 연속 새 리뷰 없음 → 수집 종료")
                    break
            else:
                no_new_streak = 0

            # 최대 수집 수 도달
            if len(dom_reviews) >= MAX_REVIEWS_PER_PLACE:
                print(f"  ✅ 목표 수집 수 도달: {len(dom_reviews)}건")
                break

        print(f"  📄 DOM 수집 완료: {len(dom_reviews)}건")

        # ── Step 5: 결과 병합 (API > DOM 우선순위) ───────────────
        if len(api_reviews) > len(dom_reviews):
            result["reviews"] = api_reviews[:MAX_REVIEWS_PER_PLACE]
            result["source"]  = f"api({len(api_reviews)}건)"
            print(f"  ✅ API 소스 채택: {len(api_reviews)}건")
        elif dom_reviews:
            result["reviews"] = dom_reviews[:MAX_REVIEWS_PER_PLACE]
            result["source"]  = f"dom({len(dom_reviews)}건)"
        else:
            result["source"] = "none"

        result["total_collected"] = len(result["reviews"])

        # ── 스크린샷 ─────────────────────────────────────────────
        SHOT_DIR.mkdir(exist_ok=True)
        await page.screenshot(path=str(SHOT_DIR / f"{rank}_reviews.png"))
        print(f"  📸 스크린샷 저장")
        print(f"  ✅ 최종: {result['total_collected']}건 (소스: {result['source']})")

    except Exception as e:
        print(f"  ❌ 오류: {e}")
        result["error"] = str(e)
    finally:
        page.remove_listener("response", on_response)

    return result


# ──────────────────────────────────────────────────────────────
# 키워드 분석
# ──────────────────────────────────────────────────────────────
def analyze_keywords(reviews: list[dict]) -> dict:
    all_text = " ".join(r["text"] for r in reviews)

    # 1) 단어 빈도
    words = re.findall(r"[가-힣]{2,6}", all_text)
    word_freq = Counter(w for w in words if w not in STOPWORDS)

    # 2) 2-gram 빈도
    tokens = [w for w in words if w not in STOPWORDS]
    bigrams = [f"{tokens[i]} {tokens[i+1]}" for i in range(len(tokens)-1)]
    bigram_freq = Counter(bigrams)

    # 3) 토픽별 빈도
    topic_counts: dict[str, int] = {}
    for topic, kws in TOPIC_MAP.items():
        cnt = sum(all_text.count(k) for k in kws)
        topic_counts[topic] = cnt

    # 4) 긍/부정 비율
    pos_cnt = sum(all_text.count(k) for k in POSITIVE_SIGNALS)
    neg_cnt = sum(all_text.count(k) for k in NEGATIVE_SIGNALS)

    # 5) 별점 분포
    ratings = [r["rating"] for r in reviews if r.get("rating")]
    rating_dist: dict[str, int] = {}
    for rr in ratings:
        try:
            key = str(float(str(rr)))
            rating_dist[key] = rating_dist.get(key, 0) + 1
        except Exception:
            pass

    return {
        "word_freq":    word_freq.most_common(50),
        "bigram_freq":  bigram_freq.most_common(30),
        "topic_counts": topic_counts,
        "pos_cnt":      pos_cnt,
        "neg_cnt":      neg_cnt,
        "rating_dist":  rating_dist,
    }


# ──────────────────────────────────────────────────────────────
# 리뷰 분석 리포트 생성
# ──────────────────────────────────────────────────────────────
def generate_review_report(all_results: list[dict]) -> str:
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

    # ── 0. 수집 현황 ──────────────────────────────────────────
    sep("[ 수집 현황 ]")
    total = 0
    for r in all_results:
        n = r["total_collected"]
        total += n
        buf.append(
            f"  {r['rank']:6s} | {r['name']:22s} | "
            f"{n:>4}건 수집 | 소스: {r.get('source','?')}"
        )
    buf.append(f"\n  전체 수집 리뷰: {total}건")

    # ── 1. 업체별 키워드 분석 ─────────────────────────────────
    sep("[ 1 ] 업체별 리뷰 키워드 Top 20")

    analyses: dict[str, dict] = {}
    for r in all_results:
        if not r["reviews"]:
            buf.append(f"\n  [{r['rank']}] {r['name']}: 리뷰 없음")
            continue
        ana = analyze_keywords(r["reviews"])
        analyses[r["rank"]] = ana

        buf.append(f"\n  ┌ [{r['rank']}] {r['name']} ({r['total_collected']}건)")

        # 상위 키워드
        top_words = ana["word_freq"][:20]
        rows = [f"{w}({c})" for w, c in top_words]
        buf.append("  │ 상위 키워드:")
        for i in range(0, len(rows), 5):
            buf.append("  │   " + "  ".join(rows[i:i+5]))

        # 2-gram
        top2 = ana["bigram_freq"][:10]
        if top2:
            buf.append("  │ 2단어 연속 표현:")
            buf.append("  │   " + "  ".join(f"[{b}]({c})" for b, c in top2[:6]))

        # 토픽
        buf.append("  │ 토픽별 언급 수:")
        sorted_topics = sorted(ana["topic_counts"].items(), key=lambda x: -x[1])
        for topic, cnt in sorted_topics:
            if cnt > 0:
                bar = "█" * min(cnt // 3, 15)
                buf.append(f"  │   {topic:12s}: {cnt:>4}회 {bar}")

        # 감성
        pos = ana["pos_cnt"]
        neg = ana["neg_cnt"]
        total_senti = pos + neg if (pos + neg) > 0 else 1
        buf.append(
            f"  │ 감성 비율:  긍정 {pos}({pos*100//total_senti}%)  "
            f"부정 {neg}({neg*100//total_senti}%)"
        )
        buf.append("  └" + "─" * (W - 4))

    # ── 2. 전체 합산 키워드 Top 30 ────────────────────────────
    sep("[ 2 ] 전체 업체 합산 고빈도 키워드 Top 30")

    all_reviews_flat = [r for res in all_results for r in res["reviews"]]
    if all_reviews_flat:
        total_ana = analyze_keywords(all_reviews_flat)

        buf.append("\n  ▶ 고객이 가장 많이 언급하는 단어 Top 30:")
        rows = [f"{w}({c})" for w, c in total_ana["word_freq"][:30]]
        for i in range(0, len(rows), 5):
            buf.append("    " + "  ".join(rows[i:i+5]))

        buf.append("\n  ▶ 자주 나오는 2단어 조합 Top 15:")
        rows2 = [f"[{b}]({c})" for b, c in total_ana["bigram_freq"][:15]]
        for i in range(0, len(rows2), 3):
            buf.append("    " + "  ".join(rows2[i:i+3]))

    # ── 3. 토픽 비교 히트맵 ──────────────────────────────────
    sep("[ 3 ] 토픽별 언급 빈도 비교 (상위 5 vs 내 업체)")

    if analyses:
        top_ranks   = [k for k in analyses if k != "내 업체"]
        mine_rank   = "내 업체"
        topics      = list(TOPIC_MAP.keys())

        # 헤더
        header = f"  {'토픽':14s}"
        for rank in top_ranks:
            header += f" {rank:6s}"
        header += f"  {'내업체':6s}"
        buf.append("\n" + header)
        buf.append("  " + "─" * (len(header) - 2))

        for topic in topics:
            row = f"  {topic:14s}"
            for rank in top_ranks:
                cnt = analyses.get(rank, {}).get("topic_counts", {}).get(topic, 0)
                cell = f"{cnt:>4}" if cnt > 0 else "   -"
                row += f"  {cell:4s}"
            mine_cnt = analyses.get(mine_rank, {}).get("topic_counts", {}).get(topic, 0)
            flag = " ⚠" if mine_cnt == 0 else ""
            row += f"  {mine_cnt:>4}{flag}"
            buf.append(row)

    # ── 4. 내 업체 리뷰 vs 상위 업체 리뷰 차이 분석 ──────────
    sep("[ 4 ] 내 업체 리뷰 GAP 분석")

    if analyses and "내 업체" in analyses:
        mine_ana  = analyses["내 업체"]
        mine_kws  = {w for w, _ in mine_ana["word_freq"][:20]}

        # 상위 업체들의 공통 키워드 (3개 이상 업체 등장)
        top_word_cnt: Counter = Counter()
        for rank in top_ranks:
            for w, _ in analyses.get(rank, {}).get("word_freq", [])[:20]:
                top_word_cnt[w] += 1
        common_top = {w for w, c in top_word_cnt.items() if c >= 2}

        missing = common_top - mine_kws - STOPWORDS
        buf.append("\n  ▶ 상위 업체 리뷰에 자주 등장하지만 내 업체 리뷰에 없는 키워드:")
        if missing:
            buf.append(f"    → {', '.join(sorted(missing))}")
            buf.append("    위 키워드들은 고객이 상위 업체에서 경험하고 언급하는 요소입니다.")
            buf.append("    해당 요소들을 실제 서비스/소개글에 반영하면 효과적입니다.")
        else:
            buf.append("    (데이터 충분하지 않음 — 스크린샷 직접 확인 권장)")

        # 내 업체에만 있는 강점 키워드
        mine_only = mine_kws - common_top - STOPWORDS
        if mine_only:
            buf.append(f"\n  ▶ 내 업체 리뷰에만 등장하는 차별 키워드 (강점 후보):")
            buf.append(f"    → {', '.join(sorted(mine_only))}")
            buf.append("    이 키워드들을 소개글과 키워드 태그에 적극 활용하세요.")

        # 감성 비교
        buf.append("\n  ▶ 긍/부정 감성 비교:")
        buf.append(f"    {'순위':8s} {'긍정':>6s}  {'부정':>6s}  {'긍정률':>6s}")
        buf.append("    " + "─" * 32)
        for rank in list(top_ranks) + ["내 업체"]:
            if rank not in analyses:
                continue
            p = analyses[rank]["pos_cnt"]
            n = analyses[rank]["neg_cnt"]
            t = p + n if p + n > 0 else 1
            flag = " ★" if rank == "내 업체" else ""
            buf.append(f"    {rank:8s}  {p:>6}   {n:>6}   {p*100//t:>5}%{flag}")

    # ── 5. SEO 활용 인사이트 ─────────────────────────────────
    sep("[ 5 ] 리뷰 기반 SEO 활용 인사이트")

    buf.append("""
  ① 소개글 키워드 최적화
     고빈도 리뷰 키워드를 소개글에 자연스럽게 삽입
     → 고객이 실제 쓰는 단어 = 검색어와 일치 = 노출 확률 상승

  ② 리뷰 유도 문구 개선
     자주 언급되는 긍정 토픽(ex. 트레이너, 기구, 청결)을
     현장 QR/안내 문구에 반영해 리뷰 작성 방향 유도

  ③ 키워드 태그 업데이트
     리뷰 Top 키워드 중 현재 태그에 없는 단어 추가 등록

  ④ 부정 리뷰 토픽 관리
     혼잡도·가격·시설 노후 언급이 많다면 해당 항목 실제 개선 후
     소개글에 "대규모 리모델링 완료" 등 반영

  ⑤ 2-gram 표현 활용
     "친절한 트레이너", "넓은 공간" 등 2단어 조합을
     이벤트 문구·사진 캡션에 그대로 사용 (자연어 최적화)
""")

    buf.append("=" * W)
    buf.append("  ※ 리뷰 원본: naver_reviews.json 참조")
    buf.append("  ※ 스크린샷: screenshots_review/ 폴더")
    buf.append("=" * W)

    return "\n".join(buf)


# ──────────────────────────────────────────────────────────────
# 메인
# ──────────────────────────────────────────────────────────────
async def main():
    print("=" * 55)
    print("  네이버 플레이스 리뷰 수집 + 키워드 분석기")
    print("=" * 55)

    all_results: list[dict] = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=False,
            slow_mo=80,
            args=["--lang=ko-KR", "--no-sandbox"],
        )
        context = await browser.new_context(
            locale="ko-KR",
            timezone_id="Asia/Seoul",
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

    # ── JSON 저장 ──────────────────────────────────────────────
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2)
    print(f"\n✅ 리뷰 JSON 저장: {OUT_JSON}")

    # ── 리포트 저장 ────────────────────────────────────────────
    report = generate_review_report(all_results)
    with open(OUT_REPORT, "w", encoding="utf-8") as f:
        f.write(report)
    print(f"✅ 분석 리포트 저장: {OUT_REPORT}")
    print("\n" + report)


if __name__ == "__main__":
    asyncio.run(main())
