# -*- coding: utf-8 -*-
"""
네이버 플레이스 SEO 데이터 수집기 v2
────────────────────────────────────────────────────────────
전략:
  1) Playwright로 실제 브라우저 구동 (headless=False)
  2) 네트워크 응답 인터셉트 → Naver 내부 API JSON 직접 캡처
  3) DOM 파싱으로 보완 수집
  4) 결과를 JSON + SEO 리포트(TXT)로 저장

설치:
  pip install playwright
  playwright install chromium

실행:
  python naver_place_scraper.py
"""

import asyncio
import json
import re
from collections import Counter
from datetime import datetime
from pathlib import Path

from playwright.async_api import async_playwright, Response

# ──────────────────────────────────────────────────────────
# 수집 대상
# ──────────────────────────────────────────────────────────
PLACES = {
    "1위":    "13155391",
    "2위":    "1166532147",
    "3위":    "1219319598",
    "4위":    "1083518673",
    "5위":    "1056155482",
    "내 업체": "1100555051",
}

OUT_JSON   = "naver_place_result.json"
OUT_REPORT = "naver_seo_report.txt"
SHOT_DIR   = Path("screenshots")

# 네이버 내부 API URL 패턴 (인터셉트 대상)
API_PATTERNS = [
    "api.place.naver.com",
    "place.map.naver.com/place/v",
    "map.naver.com/p/api/place",
    "/graphql",
]


# ──────────────────────────────────────────────────────────
# 헬퍼
# ──────────────────────────────────────────────────────────
def clean(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


async def safe_text(ctx, *selectors) -> str:
    for sel in selectors:
        try:
            el = await ctx.query_selector(sel)
            if el:
                t = clean(await el.inner_text())
                if t:
                    return t
        except Exception:
            pass
    return ""


async def safe_texts(ctx, *selectors) -> list[str]:
    for sel in selectors:
        try:
            els = await ctx.query_selector_all(sel)
            result = []
            for el in els:
                t = clean(await el.inner_text())
                if t:
                    result.append(t)
            if result:
                return result
        except Exception:
            pass
    return []


# ──────────────────────────────────────────────────────────
# API 응답에서 데이터 추출
# ──────────────────────────────────────────────────────────
def parse_api_response(payload: dict, place_id: str) -> dict:
    """네이버 내부 API JSON에서 필요한 필드 추출 (구조가 다양하므로 재귀 탐색)"""
    result = {}

    def find(obj, *keys):
        """중첩 dict/list에서 key 탐색"""
        if isinstance(obj, dict):
            for k, v in obj.items():
                if k in keys:
                    return v
                found = find(v, *keys)
                if found is not None:
                    return found
        elif isinstance(obj, list):
            for item in obj:
                found = find(item, *keys)
                if found is not None:
                    return found
        return None

    # 업체명
    for key in ("name", "placeName", "title"):
        v = find(payload, key)
        if v and isinstance(v, str) and len(v) < 50:
            result["name"] = v
            break

    # 카테고리
    for key in ("category", "categoryName", "categoryPath"):
        v = find(payload, key)
        if v and isinstance(v, str):
            result["category"] = v
            break

    # 소개글
    for key in ("description", "intro", "introduce", "summary", "content"):
        v = find(payload, key)
        if v and isinstance(v, str) and len(v) > 15:
            result["description"] = v
            break

    # 별점
    for key in ("starScore", "avgRating", "rating", "score"):
        v = find(payload, key)
        if v is not None:
            result["rating"] = str(v)
            break

    # 리뷰 수
    for key in ("reviewCount", "visitorReviewCount", "totalReviewCount"):
        v = find(payload, key)
        if v is not None:
            result["review_count"] = str(v)
            break

    # 방문자 리뷰
    for key in ("visitorReviewCount", "blogReviewCount"):
        v = find(payload, key)
        if v is not None:
            result.setdefault("visitor_review_count", str(v))
            break

    # 키워드
    for key in ("keywords", "tags", "businessKeywords"):
        v = find(payload, key)
        if isinstance(v, list) and v:
            result["keywords"] = [str(x) if not isinstance(x, dict) else x.get("keyword", "") for x in v]
            break

    # 영업시간
    for key in ("businessHours", "openingHours", "businessHour"):
        v = find(payload, key)
        if v:
            result["business_hours"] = str(v)[:300]
            break

    # 이벤트
    for key in ("coupon", "event", "benefit", "promotions"):
        v = find(payload, key)
        if v:
            result["has_event"] = True
            result["event_text"] = str(v)[:200]
            break

    return result


# ──────────────────────────────────────────────────────────
# 단일 업체 수집
# ──────────────────────────────────────────────────────────
async def scrape_place(page, rank: str, place_id: str) -> dict:
    url = f"https://map.naver.com/p/entry/place/{place_id}?placePath=%2Fhome"
    print(f"\n[{rank}] ▶ {url}")

    data = {
        "rank": rank,
        "place_id": place_id,
        "url": url,
        "name": "", "category": "", "description": "",
        "rating": "", "review_count": "", "visitor_review_count": "",
        "keywords": [], "business_hours": "",
        "has_event": False, "event_text": "",
        "menu_items": [], "raw_text": "", "source": "dom",
    }

    # ── 네트워크 인터셉트 ──────────────────────────────────
    captured: list[dict] = []

    async def on_response(response: Response):
        try:
            rurl = response.url
            if any(p in rurl for p in API_PATTERNS):
                ct = response.headers.get("content-type", "")
                if "json" in ct:
                    body = await response.json()
                    captured.append({"url": rurl, "body": body})
                    print(f"   📡 API 캡처: {rurl[:80]}")
        except Exception:
            pass

    page.on("response", on_response)

    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        # 동적 컨텐츠 로딩 대기
        await page.wait_for_timeout(5000)

        # ── 1차: API 응답에서 데이터 파싱 ─────────────────
        for cap in captured:
            parsed = parse_api_response(cap["body"], place_id)
            for k, v in parsed.items():
                if v and not data.get(k):
                    data[k] = v
            if data.get("name") and data.get("description"):
                data["source"] = "api"
                print(f"   ✅ API 파싱 성공")
                break

        # ── 2차: iframe DOM 파싱 ───────────────────────────
        # entryIframe 찾기 (최대 10초 대기)
        frame = None
        for attempt in range(10):
            for f in page.frames:
                fu = f.url
                if place_id in fu or "place.map.naver.com" in fu:
                    frame = f
                    break
            if frame:
                print(f"   🖼  iframe 발견: {frame.url[:80]}")
                break
            await page.wait_for_timeout(1000)

        ctx = frame if frame else page.main_frame

        # 업체명
        if not data["name"]:
            data["name"] = await safe_text(
                ctx,
                "span.GHAhO", "h2.GHAhO", ".place_name",
                "h1", "strong.place_name", ".Fc1rA", ".bJMxI",
                "h2[class*='name']", "h1[class*='name']",
            )

        # 카테고리
        if not data["category"]:
            data["category"] = await safe_text(
                ctx,
                "span.lnJFt", ".category", "a.lnJFt",
                "span.KCMnt", "span[class*='category']",
            )

        # 소개글 — 여러 섹션 순서대로 시도
        if not data["description"]:
            for sel in [
                "div.T8RFa", "div.zD5Nm", "div.owAeM", "div.xHaT3",
                ".place_intro", ".intro_text", "p.intro",
                "div[class*='intro']", "section[class*='intro'] p",
                "div.pSavy", "div.gMZSN",
            ]:
                try:
                    el = await ctx.query_selector(sel)
                    if el:
                        t = clean(await el.inner_text())
                        if len(t) > 20:
                            data["description"] = t
                            break
                except Exception:
                    pass

        # 별점
        if not data["rating"]:
            for sel in [
                "span.PXMot em", ".score_num", ".rating_star em",
                "em.num", "span[class*='score']", "strong[class*='score']",
            ]:
                t = await safe_text(ctx, sel)
                if t and re.search(r"\d+\.?\d*", t):
                    data["rating"] = t
                    break

        # 리뷰 수
        if not data["review_count"]:
            review_candidates = await safe_texts(
                ctx,
                "a.PXMot", "span.PXMot", ".review_count",
                "a[class*='review']", "span[class*='review']",
            )
            for t in review_candidates:
                nums = re.findall(r"[\d,]+", t)
                if nums:
                    if "방문자" in t or "visitor" in t.lower():
                        data["visitor_review_count"] = nums[0]
                    else:
                        data["review_count"] = nums[0]

        # 키워드 태그
        if not data["keywords"]:
            kws = await safe_texts(
                ctx,
                "span.zPfVt", ".keyword_tag", "a.keyword",
                "li.keyword", ".tag_item", "span.tag",
                "a[class*='keyword']", "div[class*='keyword'] span",
            )
            data["keywords"] = [k for k in kws if len(k) < 20][:15]

        # 영업시간
        if not data["business_hours"]:
            data["business_hours"] = await safe_text(
                ctx,
                ".U7pYf", ".O8qbU", ".place_business_hours",
                "div[class*='BusinessHour']", "div[class*='hours']",
            )

        # 이벤트/쿠폰
        if not data["has_event"]:
            event_els = await ctx.query_selector_all(
                ".event_area, .coupon, .xEvnm, .YsRHH, [class*='event'], [class*='coupon']"
            )
            if event_els:
                data["has_event"] = True
                texts = []
                for el in event_els[:3]:
                    t = clean(await el.inner_text())
                    if t:
                        texts.append(t)
                data["event_text"] = " | ".join(texts)

        # 메뉴
        menus = await safe_texts(
            ctx,
            ".menu_item", ".dish_item", "li.MXkFe",
            ".place_menu li", ".list_menu li", "[class*='menu'] li",
        )
        data["menu_items"] = menus[:10]

        # raw_text (백업)
        try:
            body_el = await ctx.query_selector("body")
            if body_el:
                raw = clean(await body_el.inner_text())
                raw = re.sub(r" {2,}", " ", raw)
                data["raw_text"] = raw[:6000]
        except Exception:
            pass

        # ── 스크린샷 ──────────────────────────────────────
        SHOT_DIR.mkdir(exist_ok=True)
        await page.screenshot(
            path=str(SHOT_DIR / f"{rank}.png"),
            full_page=False,
        )
        print(f"   📸 스크린샷 저장: screenshots/{rank}.png")
        print(f"   ✅ 수집 결과: 이름={data['name'] or '?'} | "
              f"리뷰={data['review_count'] or '?'} | "
              f"소개글={len(data['description'])}자 | "
              f"키워드={len(data['keywords'])}개")

    except Exception as e:
        print(f"   ❌ 오류: {e}")
        data["error"] = str(e)
    finally:
        page.remove_listener("response", on_response)

    return data


# ──────────────────────────────────────────────────────────
# SEO 리포트 생성
# ──────────────────────────────────────────────────────────
def generate_seo_report(results: list[dict]) -> str:
    top5 = [r for r in results if r["rank"] != "내 업체"]
    mine = next((r for r in results if r["rank"] == "내 업체"), {})

    buf = []
    W = 62

    def section(title):
        buf.append("\n" + "─" * W)
        buf.append(f" {title}")
        buf.append("─" * W)

    buf.append("=" * W)
    buf.append("  네이버 플레이스 SEO 분석 리포트")
    buf.append(f"  생성: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    buf.append("=" * W)

    # ── 0. 수집 현황 ──────────────────────────────────────
    section("[ 수집 데이터 현황 ]")
    for r in results:
        flag = "★" if r["rank"] == "내 업체" else " "
        buf.append(
            f"  {flag}{r['rank']:6s} | {r.get('name','(미수집)'):18s} | "
            f"별점 {r.get('rating','?'):4s} | "
            f"리뷰 {r.get('review_count','?'):>5s} | "
            f"소개글 {len(r.get('description',''))}자 | "
            f"이벤트 {'O' if r.get('has_event') else 'X'}"
        )

    # ── 수집 품질 경고 ────────────────────────────────────
    empty_count = sum(1 for r in results if not r.get("name") and not r.get("description"))
    if empty_count > 0:
        buf.append(f"\n  ⚠  {empty_count}개 업체 데이터 미수집")
        buf.append("  → screenshots/ 폴더 확인 후 누락 항목은 직접 보완 권장")

    # ── 1. 키워드 밀도 분석 ───────────────────────────────
    section("[ 1 ] 키워드 밀도 분석 — 상위 5개 공통 핵심 키워드")

    # 소개글 + raw_text 합산 (상위 5개)
    combined_desc = " ".join(
        r.get("description", "") + " " + r.get("raw_text", "")[:500]
        for r in top5
    )
    words = re.findall(r"[가-힣]{2,6}", combined_desc)

    STOPWORDS = {
        "있습니다","합니다","입니다","드립니다","있어요","해요","해드립니다",
        "으로","에서","위해","하여","하는","하고","이며","이고","그리고",
        "저희","제공","운영","가능","시간","문의","주세요","바랍니다",
        "이용","방문","예약","서비스","고객","업체","가게","매장",
        "안내","통해","대한","경우","모든","관련","기준","사항",
    }
    word_freq = Counter(w for w in words if w not in STOPWORDS)
    top_words = word_freq.most_common(20)

    # 등록 키워드 태그 빈도
    all_tags: list[str] = []
    for r in top5:
        all_tags.extend(r.get("keywords", []))
    tag_freq = Counter(all_tags)
    top_tags = tag_freq.most_common(10)

    buf.append("\n  ▶ 소개글 고빈도 단어 Top 20 (UI 제거 후):")
    if top_words:
        rows = [f"{w}({c})" for w, c in top_words]
        # 4개씩 줄 바꿈
        for i in range(0, len(rows), 5):
            buf.append("    " + "  ".join(rows[i:i+5]))
    else:
        buf.append("    (소개글 데이터 부족 — 스크린샷 직접 확인)")

    buf.append("\n  ▶ 등록 키워드 태그 (상위 업체 공통):")
    if top_tags:
        buf.append("    " + "  ".join(f"{t}({c})" for t, c in top_tags))
    else:
        buf.append("    (키워드 태그 미수집)")

    # 업체별 키워드 현황
    buf.append("\n  ▶ 업체별 등록 키워드:")
    for r in results:
        kws = r.get("keywords", [])
        buf.append(f"    {r['rank']:6s}: {', '.join(kws[:8]) or '(없음)'}")

    # ── 2. 차별점 분석 ────────────────────────────────────
    section("[ 2 ] 차별점 분석 — 내 업체 소개글 부족 요소")

    my_desc = mine.get("description", "")
    avg_len = (
        sum(len(r.get("description", "")) for r in top5) // max(len(top5), 1)
    )

    buf.append(f"\n  ▶ 내 업체 소개글 ({len(my_desc)}자):")
    buf.append(f"    {my_desc[:300] or '(소개글 미수집)'}")

    buf.append(f"\n  ▶ 글자 수 비교:")
    buf.append(f"    상위 5개 평균: {avg_len}자")
    buf.append(f"    내 업체:       {len(my_desc)}자  "
               f"{'← 부족 (보강 필요)' if len(my_desc) < avg_len * 0.8 else '← 양호'}")

    top_kw_set = {w for w, _ in top_words[:12]}
    my_words = set(re.findall(r"[가-힣]{2,6}", my_desc))
    missing_kw = top_kw_set - my_words - STOPWORDS

    buf.append(f"\n  ▶ 상위 업체 핵심 키워드 중 내 소개글에 없는 것:")
    buf.append(f"    {', '.join(sorted(missing_kw)) or '(분석 데이터 부족)'}")

    # 소개글 항목별 상세 비교
    buf.append("\n  ▶ 상위 업체 소개글 요약 (참고용):")
    for r in top5:
        desc = r.get("description", "")
        if desc:
            buf.append(f"    [{r['rank']}] {desc[:100]}{'...' if len(desc) > 100 else ''}")
        else:
            buf.append(f"    [{r['rank']}] (미수집)")

    # 감성 소구 체크
    EMOTIONAL = {
        "편안함·분위기": ["편안", "아늑", "분위기", "감성", "힐링", "포근", "여유"],
        "신선·품질":     ["신선", "국내산", "산지직송", "당일", "엄선", "품질", "정성"],
        "전문성":        ["전문", "자격", "경력", "숙련", "장인", "전문가", "실력"],
        "청결·위생":     ["청결", "위생", "소독", "깨끗", "청소", "위생적"],
        "주차·접근성":   ["주차", "역", "도보", "무료주차", "접근", "인근", "위치"],
        "가격·혜택":     ["합리", "가성비", "할인", "특가", "무료", "저렴", "혜택"],
        "예약·편의":     ["예약", "당일", "주문", "편리", "간편", "카카오", "네이버예약"],
    }
    buf.append("\n  ▶ 감성 소구 포인트 체크:")
    buf.append(f"    {'항목':18s} {'상위업체':8s} {'내 업체':10s} 조치")
    buf.append("    " + "-" * 44)
    for label, kws in EMOTIONAL.items():
        top_has = any(k in combined_desc for k in kws)
        my_has  = any(k in my_desc for k in kws)
        action = "✓ OK" if my_has else ("⚠ 추가 권장" if top_has else "—")
        buf.append(f"    {label:18s} {'있음' if top_has else '없음':8s} {'있음' if my_has else '없음':10s} {action}")

    # ── 3. 활성화 지수 ────────────────────────────────────
    section("[ 3 ] 활성화 지수 비교 — 즉시 실행 우선순위")

    buf.append("\n  ▶ 리뷰 수 비교:")
    for r in results:
        cnt = r.get("review_count") or "?"
        try:
            bar = int(cnt.replace(",", "")) // 50
            bar_str = "█" * min(bar, 20)
        except Exception:
            bar_str = "?"
        flag = " ★" if r["rank"] == "내 업체" else ""
        buf.append(f"    {r['rank']:6s} | {r.get('name','?'):16s} | {cnt:>6} | {bar_str}{flag}")

    event_count = sum(1 for r in top5 if r.get("has_event"))
    buf.append(f"\n  ▶ 이벤트/쿠폰: 상위 5개 중 {event_count}개 업체 운영")
    buf.append(f"    내 업체: {'✅ 운영 중' if mine.get('has_event') else '❌ 없음 → 즉시 등록 권장'}")

    # 우선순위 계산
    priorities: list[str] = []
    if not mine.get("has_event"):
        priorities.append("🥇 1순위: 이벤트/쿠폰 등록 (저장·클릭률 직결)")
    if len(my_desc) < max(avg_len * 0.7, 100):
        priorities.append(f"🥈 2순위: 소개글 보강 ({len(my_desc)}자 → {max(avg_len, 200)}자 목표)")
    if missing_kw:
        priorities.append(f"🥉 3순위: 핵심 키워드 삽입 ({', '.join(list(missing_kw)[:5])})")
    priorities.append("4순위: 리뷰 유도 (영수증리뷰 QR / 현장 안내문)")
    priorities.append("5순위: 사진 최적화 (대표사진 교체, 10장+ 등록)")
    priorities.append("6순위: 네이버 예약 연동 (미연동 시 상위 노출 불리)")

    buf.append("\n  ▶ 즉시 실행 우선순위:")
    for p in priorities:
        buf.append(f"    {p}")

    # ── 4. 최적화 제안 ────────────────────────────────────
    section("[ 4 ] 최적화 제안 — 소개글·키워드 수정 초안")

    category = (mine.get("category")
                or (top5[0].get("category") if top5 else "")
                or "업체")
    buf.append(f"\n  ▶ 업종(추정): {category}")

    # 소개글 초안
    draft_kw = [w for w, _ in top_words[:6]]
    miss_list = list(missing_kw)[:4]

    # 현재 소개글 기반 + 키워드 삽입 가이드
    base_intro = my_desc[:80] if my_desc else f"안녕하세요, {mine.get('name', '저희 업체')}입니다."

    buf.append("\n  ┌─────────────────────────────────────────────────────┐")
    buf.append("  │           ★ 소개글 수정 초안 (직접 다듬어 사용)     │")
    buf.append("  └─────────────────────────────────────────────────────┘")
    buf.append("")
    buf.append(f"  {base_intro}")
    buf.append("")
    buf.append(f"  저희는 {category} 전문 업체로,")
    if draft_kw:
        buf.append(f"  {' · '.join(draft_kw[:3])} 을(를) 중심으로 최상의 서비스를 제공합니다.")
    buf.append("")
    buf.append("  [감성 소구 문구 예시 — 업종에 맞게 1~2개 선택]")
    buf.append("  · 편안하고 아늑한 공간에서 특별한 시간을 경험해보세요.")
    buf.append("  · 엄선된 재료와 숙련된 전문가의 손길로 만들어드립니다.")
    buf.append("  · 청결하고 위생적인 환경에서 편안하게 이용하실 수 있습니다.")
    buf.append("  · 합리적인 가격으로 높은 품질의 서비스를 만나보세요.")
    buf.append("")
    if miss_list:
        buf.append(f"  [추가 삽입 권장 키워드]: {' / '.join(miss_list)}")
    buf.append("")
    buf.append("  방문 전 네이버 예약으로 간편하게 일정을 잡아보세요.")
    buf.append("  지금 저장하고 특별한 혜택을 놓치지 마세요! 💡")
    buf.append("")
    buf.append(f"  ▸ 목표 글자 수: {max(avg_len, 200)}자 이상 (현재 {len(my_desc)}자)")

    # 추천 키워드 태그
    buf.append("\n  ▶ 추천 등록 키워드 태그 (10개 이내 선택):")
    rec_kw = list({w for w, _ in top_words[:8]} | {t for t, _ in top_tags[:5]})
    buf.append("    " + " / ".join(rec_kw[:10]))

    # ── 전체 요약 ─────────────────────────────────────────
    section("[ 요약 ] 핵심 액션 체크리스트")
    checklist = [
        "[ ] 소개글 최소 200자 이상으로 보강",
        "[ ] 핵심 키워드 자연스럽게 소개글에 삽입",
        "[ ] 이벤트/쿠폰 1개 이상 등록",
        "[ ] 대표 사진 고화질로 교체 (음식·공간·스태프)",
        "[ ] 내부·메뉴 사진 10장 이상 업로드",
        "[ ] 네이버 예약 연동",
        "[ ] 리뷰 유도 QR코드 현장 부착",
        "[ ] 키워드 태그 업종 맞춤 10개 등록",
    ]
    for item in checklist:
        buf.append(f"  {item}")

    buf.append("\n" + "=" * W)
    buf.append("  ※ 실제 업체 특성에 맞게 소개글 초안을 수정 후 등록하세요.")
    buf.append("  ※ screenshots/ 폴더에서 각 업체 화면을 직접 확인하세요.")
    buf.append("=" * W)

    return "\n".join(buf)


# ──────────────────────────────────────────────────────────
# 메인
# ──────────────────────────────────────────────────────────
async def main():
    print("=" * 50)
    print("  네이버 플레이스 SEO 수집기 v2")
    print("=" * 50)

    results: list[dict] = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=False,
            slow_mo=100,
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

        for rank, place_id in PLACES.items():
            result = await scrape_place(page, rank, place_id)
            results.append(result)
            await asyncio.sleep(3)

        await browser.close()

    # JSON 저장
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"\n✅ JSON 저장: {OUT_JSON}")

    # 리포트 저장
    report = generate_seo_report(results)
    with open(OUT_REPORT, "w", encoding="utf-8") as f:
        f.write(report)
    print(f"✅ 리포트 저장: {OUT_REPORT}")

    # 콘솔 출력
    print("\n" + report)


if __name__ == "__main__":
    asyncio.run(main())
