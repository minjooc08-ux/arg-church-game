# -*- coding: utf-8 -*-
"""
짐박스 네이버 플레이스 SEO 분석 플랫폼
────────────────────────────────────
실행: python seo_app.py
접속: http://localhost:5000
"""

from flask import Flask, render_template, request, jsonify, redirect, url_for
import json, os, re, subprocess, sys, threading
from pathlib import Path
from datetime import datetime
from collections import Counter

try:
    import requests as req_lib
except ImportError:
    req_lib = None

app = Flask(__name__)
BRANCHES_DIR = Path("branches")
BRANCHES_DIR.mkdir(exist_ok=True)

# ── 불용어 / 토픽맵 ────────────────────────────────────────────
STOPWORDS = {
    "있습니다","합니다","입니다","드립니다","있어요","해요","있어서","해드립니다",
    "이고","이며","그리고","그런데","하지만","그래서","이라","에서","으로","위해",
    "하여","하는","하고","하면","하다","한다","되어","때문","정말","너무","매우",
    "아주","조금","좀더","진짜","완전","했어요","했습니다","해서","인데","이에",
    "데요","고요","좋아요","좋습니다","좋은","좋고","같아요","같습니다","없어요",
    "있고","없고","됩니다","됐어요","받았어요","생각해요","느껴","느낌","같은",
    "이번","처음","다음","저도","저는","제가","하나","여기","거기","이곳","저곳",
    "이런","저런","그런","어떤","갔어요","왔어요","봤어요","했다","나왔어요",
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

# ── 유틸 ───────────────────────────────────────────────────────
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
            "folder": folder.name,
            "name": config.get("branch_name", folder.name),
            "created": config.get("created", ""),
            "has_data": review_count > 0,
            "review_count": review_count,
            "competitor_count": len(config.get("competitors", [])),
            "status": status,
        })
    return result

# ── 분석 엔진 ──────────────────────────────────────────────────
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
        "word_freq": word_freq.most_common(20),
        "bigram_freq": Counter(bigrams).most_common(10),
        "topic_counts": topic_counts,
    }

def compute_match(intro: str, top_words: list) -> dict:
    matched, unmatched = [], []
    for kw, cnt in top_words:
        (matched if kw in intro else unmatched).append({"kw": kw, "cnt": cnt})
    total = len(top_words)
    rate = round(len(matched) / total * 100) if total else 0
    return {"matched": matched, "unmatched": unmatched, "rate": rate, "total": total}


def compute_multi_source_match(top_words: list, intro: str, posts: str, menu: str) -> dict:
    """소개글·소식글·메뉴 각 소스별 + 통합 키워드 일치율 계산"""
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
    """
    가설: 의미론적 일치율(소식글+메뉴+소개글 ↔ 리뷰)이 높을수록 SEO 순위가 높다.
    Pearson r (rank_num vs combined_rate) — r < 0 일수록 가설 지지
    """
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

    # 내 업체 (순위 없음 — 별도 표시)
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
    # rank_num 낮을수록 좋음 → rate 높을수록 rank_num 낮아야 함 → r < 0 이면 가설 지지
    supported = r_val < -0.3
    verdict   = "✅ 가설을 지지합니다" if supported else (
                "⚠️ 가설을 부분적으로 지지합니다" if r_val < 0 else
                "❌ 가설과 반대 경향이 나타납니다")

    return {
        "status":    "ok",
        "r":         r_val,
        "abs_r":     abs_r,
        "strength":  strength,
        "supported": supported,
        "verdict":   verdict,
        "n":         len(ranked),
        "ranked":    ranked,
        "my":        my_item,
    }

def parse_naver_date(date_str: str):
    """네이버 날짜 문자열 → datetime 변환
    처리 형식:
      - '3일 전', '2주 전', '1개월 전'  (상대)
      - '2.24.화', '12.3.목'            (월.일.요일, 연도 없음)
      - '2025.03.24', '2025-03-24'      (절대)
    """
    if not date_str:
        return None
    from datetime import timedelta
    now = datetime.now()
    try:
        # 상대 표현
        m = re.search(r'(\d+)일\s*전', date_str)
        if m:
            return now - timedelta(days=int(m.group(1)))
        m = re.search(r'(\d+)주\s*전', date_str)
        if m:
            return now - timedelta(weeks=int(m.group(1)))
        m = re.search(r'(\d+)개월\s*전', date_str)
        if m:
            return now - timedelta(days=int(m.group(1)) * 30)
        # 절대 연도 포함: 2025.03.24 / 2025-03 등
        m = re.search(r'(\d{4})[.\-년]\s*(\d{1,2})(?:[.\-월]\s*(\d{1,2}))?', date_str)
        if m:
            year  = int(m.group(1))
            month = int(m.group(2))
            day   = int(m.group(3)) if m.group(3) else 1
            return datetime(year, month, day)
        # 연도 없는 월.일.요일 형식: "2.24.화", "12.3.목"
        m = re.match(r'^(\d{1,2})\.(\d{1,2})\.', date_str.strip())
        if m:
            month = int(m.group(1))
            day   = int(m.group(2))
            year  = now.year
            candidate = datetime(year, month, day)
            # 미래 날짜면 작년으로
            if candidate > now:
                candidate = datetime(year - 1, month, day)
            return candidate
    except Exception:
        pass
    return None

def compute_review_quality(reviews: list) -> dict:
    """리뷰 품질·최신성 지표 계산"""
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
    # 월평균 리뷰 수: 수집된 리뷰의 날짜 범위(가장 오래된~오늘)로 속도 계산
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
        "avg_len": avg_len,
        "rich_count": rich_count,
        "rich_pct": rich_pct,
        "recent_count": recent_count,
        "recent_pct": recent_pct,
        "monthly_rate": monthly_rate,
        "dated_count": dated_count,
        "avg_rating": avg_rating,
        "total": len(reviews),
    }

# ── 키워드 → 자연어 문장 변환 ───────────────────────────────────
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

def make_keyword_sentences(word_freq: list) -> list:
    """TOP 키워드를 자연어 문장 카드로 변환 (최대 8개)"""
    sentences = []
    seen_sentences = set()
    for kw, cnt in word_freq:
        kw_lower = kw.lower()
        matched = None
        for key, sentence in KW_TO_SENTENCE:
            if key in kw_lower and sentence not in seen_sentences:
                matched = {"sentence": sentence, "kw": kw, "count": cnt}
                seen_sentences.add(sentence)
                break
        if matched:
            sentences.append(matched)
        if len(sentences) >= 8:
            break
    return sentences


def compute_length_std(reviews: list) -> float | None:
    """리뷰 글자 수 표준편차 — 높을수록 자연스러운 유저 리뷰 패턴"""
    lengths = [len(r.get("text", "")) for r in reviews if r.get("text")]
    if len(lengths) < 2:
        return None
    n = len(lengths)
    mean = sum(lengths) / n
    variance = sum((x - mean) ** 2 for x in lengths) / (n - 1)
    return round(variance ** 0.5, 1)


def compute_vocab_diversity(reviews: list) -> float | None:
    """어휘 다양성 지수(TTR) — 고유 단어 수 / 전체 단어 수, 높을수록 자연스러운 리뷰"""
    all_text = " ".join(r.get("text", "") for r in reviews)
    words = re.findall(r"[가-힣]{2,6}", all_text)
    tokens = [w for w in words if w not in STOPWORDS]
    if len(tokens) < 10:
        return None
    return round(len(set(tokens)) / len(tokens), 3)


def compute_new_info_count(reviews: list, intro: str) -> int | None:
    """소개글에 없는 새로운 명사 수(Top 20 기준) — 높을수록 유저가 자발적으로 생성한 정보"""
    if not reviews:
        return None
    all_text = " ".join(r.get("text", "") for r in reviews)
    words = re.findall(r"[가-힣]{2,6}", all_text)
    word_freq = Counter(w for w in words if w not in STOPWORDS)
    top_20 = [w for w, _ in word_freq.most_common(20)]
    return sum(1 for w in top_20 if w not in intro)


def generate_quality_insight(data: list) -> str:
    """리뷰 품질 테이블 하단 자동 코멘트 생성"""
    if not data:
        return ""
    places = [p for p in data if p.get("quality")]
    if len(places) < 2:
        return ""

    insights = []
    # 월평균 리뷰 속도 비교
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
    # 양보다 질 패턴 탐지
    for p in places:
        q = p["quality"]
        mr = q.get("monthly_rate") or 0
        rich = q.get("rich_pct", 0)
        avg_l = q.get("avg_len", 0)
        if mr < 20 and rich >= 75 and avg_l >= 120:
            insights.append(
                f"<strong>{p['name']}</strong>은 월 {mr}건으로 리뷰 발행 속도는 느리지만 "
                f"평균 리뷰 길이 {avg_l}자, 정보형 비중 {rich}%로 "
                f"진정성 있는 후기가 집중된 업체입니다."
            )
    return " ".join(insights)


def load_branch_data(folder: Path, config: dict):
    reviews_path = folder / "reviews.json"
    if not reviews_path.exists():
        return None

    raw = json.loads(reviews_path.read_text(encoding="utf-8"))

    # 업체별 소개글/소식글/메뉴/블로그수 조회
    my_place = config.get("my_place", {})
    def _build_maps():
        intro_m, posts_m, menu_m, blog_m = {}, {}, {}, {}
        intro_m["내 업체"] = my_place.get("intro", "")
        posts_m["내 업체"] = my_place.get("posts", "")
        menu_m["내 업체"]  = my_place.get("menu", "")
        blog_m["내 업체"]  = my_place.get("blog_count", 0)
        for i, c in enumerate(config.get("competitors", []), 1):
            key = f"{i}위"
            intro_m[key] = c.get("intro", "")
            posts_m[key] = c.get("posts", "")
            menu_m[key]  = c.get("menu", "")
            blog_m[key]  = c.get("blog_count", 0)
        return intro_m, posts_m, menu_m, blog_m
    intro_map, posts_map, menu_map, blog_map = _build_maps()

    result = []
    for place in raw:
        rank = place.get("rank", "")
        reviews = place.get("reviews", [])
        ana = analyze_reviews(reviews) if reviews else None

        intro  = intro_map.get(rank, "")
        posts  = posts_map.get(rank, "")
        menu   = menu_map.get(rank, "")
        match  = compute_match(intro, ana["word_freq"]) if (ana and intro) else None
        multi_match = compute_multi_source_match(
            ana["word_freq"], intro, posts, menu
        ) if ana else None
        quality      = compute_review_quality(reviews) if reviews else None
        sentences    = make_keyword_sentences(ana["word_freq"]) if ana else []
        length_std   = compute_length_std(reviews) if reviews else None
        vocab_div    = compute_vocab_diversity(reviews) if reviews else None
        new_info_cnt = compute_new_info_count(reviews, intro) if reviews else None

        result.append({
            "rank":        rank,
            "name":        place.get("name", ""),
            "total":       place.get("total_collected", 0),
            "source":      place.get("source", ""),
            "analysis":    ana,
            "match":       match,
            "multi_match": multi_match,
            "quality":     quality,
            "blog_count":    blog_map.get(rank, 0),
            "sentences":     sentences,
            "length_std":    length_std,
            "vocab_div":     vocab_div,
            "new_info_count": new_info_cnt,
            "meta": {
                "has_n_booking": place.get("has_n_booking", False),
                "has_talktalk":  place.get("has_talktalk", False),
                "has_coupon":    place.get("has_coupon", False),
                "coupon_name":   place.get("coupon_name"),
                "coupon_type":   place.get("coupon_type"),
            },
        })
    return result

# ── Flask 라우트 ───────────────────────────────────────────────
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
    # 중복 체크
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
        "created": datetime.now().strftime("%Y-%m-%d %H:%M"),
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
    data = load_branch_data(folder, config)

    progress = {"status": "none"}
    if (folder / "progress.json").exists():
        try:
            progress = json.loads((folder / "progress.json").read_text(encoding="utf-8"))
        except Exception:
            pass

    # 경쟁사 평균 일치율 계산 (비교 지표용)
    comp_stats = None
    if data:
        my = next((d for d in data if d["rank"] == "내 업체"), None)
        comps = [d for d in data if d["rank"] != "내 업체" and d.get("match")]
        if my and comps:
            comp_avg = round(sum(c["match"]["rate"] for c in comps) / len(comps))
            comp_stats = {
                "my_rate": my["match"]["rate"] if my.get("match") else None,
                "comp_avg": comp_avg,
                "diff": (my["match"]["rate"] if my.get("match") else 0) - comp_avg,
            }

    quality_insight  = generate_quality_insight(data) if data else ""
    hypothesis_data  = compute_hypothesis_validation(data) if data else None

    return render_template("branch.html",
        config=config, folder_name=folder_name,
        data=data, progress=progress,
        topic_keys=list(TOPIC_MAP.keys()),
        comp_stats=comp_stats,
        quality_insight=quality_insight,
        hypothesis=hypothesis_data,
    )

@app.route("/api/run/<folder_name>", methods=["POST"])
def run_analysis(folder_name):
    folder = BRANCHES_DIR / folder_name
    if not (folder / "config.json").exists():
        return jsonify({"error": "지점 없음"}), 404

    config = json.loads((folder / "config.json").read_text(encoding="utf-8"))

    # 스크레이퍼용 설정 파일 생성
    places = {}
    for i, c in enumerate(config.get("competitors", []), 1):
        places[f"{i}위"] = {"id": c["id"], "name": c["name"]}
    places["내 업체"] = {"id": config["my_place"]["id"], "name": config["branch_name"]}

    scraper_cfg = {
        "places": places,
        "output_dir": str(folder.resolve()),
        "max_reviews": config.get("max_reviews", 300),
    }
    cfg_path = folder / "scraper_config.json"
    cfg_path.write_text(json.dumps(scraper_cfg, ensure_ascii=False, indent=2), encoding="utf-8")

    # 진행 상황 초기화
    (folder / "progress.json").write_text(
        json.dumps({"status": "running", "started": datetime.now().isoformat()}, ensure_ascii=False),
        encoding="utf-8"
    )

    scraper_path = Path(__file__).parent / "naver_review_scraper.py"

    def run():
        log_path = folder / "scraper.log"
        try:
            with open(log_path, "w", encoding="utf-8") as log_f:
                env = os.environ.copy()
                env["PYTHONIOENCODING"] = "utf-8"
                proc = subprocess.Popen(
                    [sys.executable, "-X", "utf8", str(scraper_path), str(cfg_path)],
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

if __name__ == "__main__":
    print("\n" + "=" * 50)
    print("  짐박스 SEO 분석 플랫폼")
    print("  http://localhost:5000 에서 접속하세요")
    print("  종료: Ctrl+C")
    print("=" * 50 + "\n")
    app.run(debug=False, port=5000, use_reloader=False)
