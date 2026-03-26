import os
import time
import base64
import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
try:
    from supabase import create_client as _supabase_create_client
    _SUPABASE_AVAILABLE = True
except ImportError:
    _SUPABASE_AVAILABLE = False

# ── Supabase 클라이언트 ──
@st.cache_resource
def get_supabase():
    if not _SUPABASE_AVAILABLE:
        return None
    try:
        url = st.secrets["SUPABASE_URL"]
        key = st.secrets["SUPABASE_KEY"]
        return _supabase_create_client(url, key)
    except Exception:
        return None

def log_access(player_name: str):
    """온보딩 완료 시 접속 기록 저장"""
    db = get_supabase()
    if db:
        try:
            db.table("access_logs").insert({"player_name": player_name}).execute()
        except Exception:
            pass

def log_form(player_name: str, gender, device_consent, height, weight, underwear_size, has_family):
    """지원서 제출 시 폼 데이터 저장"""
    db = get_supabase()
    if db:
        try:
            db.table("form_submissions").insert({
                "player_name":     player_name,
                "gender":          gender,
                "device_consent":  device_consent,
                "height":          height,
                "weight":          weight,
                "underwear_size":  underwear_size,
                "has_family":      has_family,
            }).execute()
        except Exception:
            pass

# ─────────────────────────────────────────────
# 페이지 설정
# ─────────────────────────────────────────────
st.set_page_config(
    page_title="NPA 경찰청 내부망",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─────────────────────────────────────────────
# 쿼리 파라미터 → 교회 페이지 진입 감지
# ─────────────────────────────────────────────
_nav = st.query_params.get("nav", "")
if _nav == "church":
    st.session_state.page = "church"
    st.query_params.clear()
    st.rerun()
elif _nav == "hidden_basement":
    st.session_state.page = "hidden_basement"
    st.query_params.clear()
    st.rerun()
elif _nav == "intranet":
    st.session_state.page = "intranet"
    st.query_params.clear()
    st.rerun()
elif _nav == "onboarding":
    st.session_state.page = "onboarding"
    st.query_params.clear()
    st.rerun()

_cnav = st.query_params.get("church_nav", "")
if _cnav:
    st.session_state.page = "church"
    st.session_state.church_subpage = _cnav
    _post_id = st.query_params.get("post_id", "")
    if _post_id:
        st.session_state.grace_post_id = int(_post_id)
    st.query_params.clear()
    st.rerun()

_confirm = st.query_params.get("confirm", "")
if _confirm == "1":
    st.session_state.page = "church"
    st.session_state.church_subpage = "form"
    st.session_state.form_phase = "idle"
    for _k in ["nf_q1", "nf_q2", "nf_height", "nf_weight", "nf_underwear", "nf_q4"]:
        st.session_state.pop(_k, None)
    st.query_params.clear()
    st.rerun()

_ifolder = st.query_params.get("intranet_folder", "")
if _ifolder in ["inbox", "sent", "trash"]:
    st.session_state.page = "intranet"
    st.session_state.intranet_folder = _ifolder
    st.query_params.clear()
    st.rerun()



# ─────────────────────────────────────────────
# 전역 UI 요소 완전 숨김 (Streamlit Cloud 버튼 포함)
# ─────────────────────────────────────────────
st.markdown("""
<style>
#MainMenu, header, footer { visibility: hidden !important; display: none !important; }
[data-testid="stToolbar"]        { display: none !important; }
[data-testid="stDecoration"]     { display: none !important; }
[data-testid="stStatusWidget"]   { display: none !important; }
[data-testid="stDeployButton"]   { display: none !important; }
[data-testid="collapsedControl"] { display: none !important; }
[data-testid="stToolbarActionButton"] { display: none !important; }
button[kind="header"]            { display: none !important; }
.stDeployButton                  { display: none !important; }
.viewerBadge_container__r5tak   { display: none !important; }
.styles_viewerBadge__CvC9N      { display: none !important; }
#stDecoration                    { display: none !important; }
</style>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────
# 세션 상태 초기화
# ─────────────────────────────────────────────
if "page" not in st.session_state:
    st.session_state.page = "onboarding"
if "player_name" not in st.session_state:
    st.session_state.player_name = ""
if "sos_visible" not in st.session_state:
    st.session_state.sos_visible = False
if "inbox_folder" not in st.session_state:
    st.session_state.inbox_folder = "inbox"
if "form_phase" not in st.session_state:
    st.session_state.form_phase = "idle"
if "form_show_link" not in st.session_state:
    st.session_state.form_show_link = False
if "pastor_pw_error" not in st.session_state:
    st.session_state.pastor_pw_error = False


# ══════════════════════════════════════════════
#  PHASE 0 : NPA 온보딩 / 수사관 인증
# ══════════════════════════════════════════════
def render_onboarding():
    st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@300;400;500;700&display=swap');

#MainMenu { visibility: hidden; }
header    { visibility: hidden; }
footer    { visibility: hidden; }
[data-testid="stToolbar"]      { display: none !important; }
[data-testid="stDecoration"]   { display: none !important; }
[data-testid="stStatusWidget"] { display: none !important; }
[data-testid="stSidebar"]      { display: none !important; }

html, body,
[data-testid="stAppViewContainer"],
[data-testid="stMain"] {
    background: #0a1628 !important;
    font-family: 'Noto Sans KR', Arial, sans-serif !important;
}
.block-container {
    padding: 6rem 2rem !important;
    max-width: 100% !important;
}

.npa-badge    { font-size: 3.2rem; display: block; text-align: center; margin-bottom: 14px; }
.npa-title    { color: #c8d8f0; font-size: 1.28rem; font-weight: 700; letter-spacing: 5px; text-align: center; margin-bottom: 5px; }
.npa-sub      { color: #3a5a88; font-size: 0.68rem; letter-spacing: 3px; text-align: center; margin-bottom: 32px; text-transform: uppercase; }
.npa-divider  { border: none; border-top: 1px solid #1c3a6e; margin: 0 auto 28px; width: 100%; }
.npa-label    { color: #7a9ac8; font-size: 0.75rem; letter-spacing: 2px; text-align: center; margin-bottom: 12px; text-transform: uppercase; }
.npa-notice   { color: #253a5a; font-size: 0.62rem; letter-spacing: 1.5px; text-align: center; margin-top: 26px; line-height: 2.1; }

[data-testid="stTextInput"] input {
    background: #0f1e38 !important;
    border: 1px solid #1c3a6e !important;
    border-radius: 6px !important;
    color: #c8d8f0 !important;
    font-family: 'Noto Sans KR', Arial, sans-serif !important;
    font-size: 0.92rem !important;
    text-align: center !important;
    letter-spacing: 2px !important;
    padding: 12px !important;
}
[data-testid="stTextInput"] input::placeholder { color: #2a4a78 !important; }
[data-testid="stTextInput"] input:focus {
    border-color: #3a6abf !important;
    box-shadow: 0 0 0 1px #3a6abf !important;
}

div[data-testid="stButton"] > button {
    background: #152e60 !important;
    color: #c8d8f0 !important;
    border: 1px solid #2a5aa0 !important;
    border-radius: 6px !important;
    font-family: 'Noto Sans KR', Arial, sans-serif !important;
    font-size: 0.87rem !important;
    letter-spacing: 3px !important;
    padding: 12px 0 !important;
    width: 100% !important;
    margin-top: 6px !important;
}
div[data-testid="stButton"] > button:hover {
    background: #1e3f7a !important;
    border-color: #3a6abf !important;
}

[data-testid="stAlert"] {
    background: #160808 !important;
    border: 1px solid #550000 !important;
    color: #ff7777 !important;
    font-size: 0.8rem !important;
    border-radius: 6px !important;
}

@media (max-width: 768px) {
    html, body { overflow-x: hidden !important; }
    .block-container { padding: 2.5rem 1.2rem 3rem !important; }
    .npa-badge { font-size: 2rem !important; }
    .npa-title { font-size: 0.95rem !important; letter-spacing: 2px !important; }
    .npa-sub   { font-size: 0.56rem !important; letter-spacing: 1px !important; }
    .npa-label { font-size: 0.68rem !important; letter-spacing: 1px !important; }
    .npa-notice { font-size: 0.54rem !important; letter-spacing: 0.8px !important; line-height: 2 !important; }
    /* 3열 → 중앙 열만 표시, 좌우 스페이서 숨김 */
    [data-testid="stHorizontalBlock"] { flex-wrap: nowrap !important; }
    [data-testid="stHorizontalBlock"] > [data-testid="stColumn"]:nth-child(1),
    [data-testid="stHorizontalBlock"] > [data-testid="stColumn"]:nth-child(3) {
        display: none !important;
        flex: 0 0 0 !important; width: 0 !important; max-width: 0 !important; overflow: hidden !important; padding: 0 !important;
    }
    [data-testid="stHorizontalBlock"] > [data-testid="stColumn"]:nth-child(2) {
        flex: 1 1 100% !important; min-width: 0 !important; max-width: 100% !important;
    }
}
</style>
""", unsafe_allow_html=True)

    _, mid, _ = st.columns([1, 1, 1])
    with mid:
        st.markdown(
            "<span class='npa-badge'>🔍</span>"
            "<div class='npa-title'>경찰청 사이버수사대</div>"
            "<div class='npa-sub'>National Police Agency · Cyber Investigation Bureau</div>"
            "<hr class='npa-divider'>"
            "<div class='npa-label'>수사관 인증 — 성함을 입력하세요</div>",
            unsafe_allow_html=True,
        )

        player_name_input = st.text_input(
            "수사관 이름",
            placeholder="성함을 입력하세요",
            label_visibility="collapsed",
            key="login_name_input",
        )

        if st.button("수사 시작  →", use_container_width=True, key="login_btn"):
            if player_name_input.strip():
                st.session_state.player_name = player_name_input.strip()
                st.session_state.page = "intranet"
                log_access(player_name_input.strip())
                st.rerun()
            else:
                st.error("수사관 성함을 입력해주세요.")

        st.markdown(
            "<div class='npa-notice'>"
            "본 시스템은 경찰청 내부 인가 인원만 사용 가능합니다.<br>"
            "무단 접속 시 관계 법령에 의거 처벌받을 수 있습니다.<br>"
            "NPA Intranet System v4.2.1 &nbsp;·&nbsp; 2024"
            "</div>",
            unsafe_allow_html=True,
        )


# ══════════════════════════════════════════════
#  PHASE 1 : 경찰청 사이버 수사대 인트라넷
# ══════════════════════════════════════════════
def render_intranet():
    player_name = st.session_state.get("player_name", "수사관")

    # 모바일 폴더 탭 쿼리 파라미터 처리
    _if = st.query_params.get("intranet_folder", "")
    if _if in ["inbox", "sent", "trash"]:
        st.session_state.intranet_folder = _if
        st.query_params.clear()
        st.rerun()
    _mob_folder = st.session_state.get("intranet_folder", "inbox")

    st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@300;400;500&display=swap');

/* ① Streamlit 기본 UI 완전 숨김 */
#MainMenu { visibility: hidden; }
header    { visibility: hidden; }
footer    { visibility: hidden; }
[data-testid="stToolbar"]        { display: none !important; }
[data-testid="stDecoration"]     { display: none !important; }
[data-testid="stStatusWidget"]   { display: none !important; }
[data-testid="collapsedControl"] { display: none !important; }
[data-testid="stSidebar"]        { display: none !important; }

/* ② 전체 배경 · 폰트 */
html, body,
[data-testid="stAppViewContainer"],
[data-testid="stMain"] {
    background: #f6f8fc !important;
    color: #202124 !important;
    font-family: 'Noto Sans KR', Arial, sans-serif !important;
}
.block-container {
    padding: 0 !important;
    max-width: 100% !important;
}

/* ③ 컬럼 간격 제거 */
[data-testid="stHorizontalBlock"] {
    gap: 0 !important;
    align-items: stretch !important;
}
[data-testid="stHorizontalBlock"] > [data-testid="stColumn"] {
    padding: 0 !important;
}

/* ④ 왼쪽 메뉴 컬럼 */
[data-testid="stHorizontalBlock"] > [data-testid="stColumn"]:first-child {
    background: #f6f8fc !important;
    border-right: 1px solid #e0e0e0 !important;
    min-height: 100vh !important;
}

/* ⑤ 메뉴 컬럼 내 radio — 폴더 항목 */
[data-testid="stHorizontalBlock"] > [data-testid="stColumn"]:first-child [data-testid="stRadio"] {
    gap: 0 !important;
}
[data-testid="stHorizontalBlock"] > [data-testid="stColumn"]:first-child [data-testid="stRadio"] > div {
    gap: 0 !important;
}
[data-testid="stHorizontalBlock"] > [data-testid="stColumn"]:first-child [data-baseweb="radio"] > div:first-child {
    display: none !important;
}
[data-testid="stHorizontalBlock"] > [data-testid="stColumn"]:first-child input[type="radio"] {
    display: none !important;
}

/* 라벨 컨테이너 */
[data-testid="stHorizontalBlock"] > [data-testid="stColumn"]:first-child [data-testid="stRadio"] label {
    padding: 10px 16px !important;
    border-radius: 20px !important;
    cursor: pointer !important;
    margin: 1px 0 !important;
    width: 100% !important;
    display: block !important;
    transition: background 0.15s !important;
}

/* 라벨 내부 텍스트 (p, div, span 모두) — 비활성 */
[data-testid="stHorizontalBlock"] > [data-testid="stColumn"]:first-child [data-testid="stRadio"] label p,
[data-testid="stHorizontalBlock"] > [data-testid="stColumn"]:first-child [data-testid="stRadio"] label div,
[data-testid="stHorizontalBlock"] > [data-testid="stColumn"]:first-child [data-testid="stRadio"] label span {
    color: #444444 !important;
    font-size: 0.87rem !important;
    font-weight: 500 !important;
    font-family: 'Noto Sans KR', Arial, sans-serif !important;
}

/* hover */
[data-testid="stHorizontalBlock"] > [data-testid="stColumn"]:first-child [data-testid="stRadio"] label:hover {
    background: #e8eaed !important;
}
[data-testid="stHorizontalBlock"] > [data-testid="stColumn"]:first-child [data-testid="stRadio"] label:hover p,
[data-testid="stHorizontalBlock"] > [data-testid="stColumn"]:first-child [data-testid="stRadio"] label:hover div,
[data-testid="stHorizontalBlock"] > [data-testid="stColumn"]:first-child [data-testid="stRadio"] label:hover span {
    color: #111111 !important;
    font-weight: 600 !important;
}

/* 선택된(active) 항목 */
[data-testid="stHorizontalBlock"] > [data-testid="stColumn"]:first-child [data-testid="stRadio"] label:has(input:checked) {
    background: #d3e3fd !important;
}
[data-testid="stHorizontalBlock"] > [data-testid="stColumn"]:first-child [data-testid="stRadio"] label:has(input:checked) p,
[data-testid="stHorizontalBlock"] > [data-testid="stColumn"]:first-child [data-testid="stRadio"] label:has(input:checked) div,
[data-testid="stHorizontalBlock"] > [data-testid="stColumn"]:first-child [data-testid="stRadio"] label:has(input:checked) span {
    color: #1a73e8 !important;
    font-weight: 700 !important;
}

/* ⑥ 오른쪽 콘텐츠 컬럼 패딩 */
[data-testid="stHorizontalBlock"] > [data-testid="stColumn"]:last-child {
    padding: 0.6rem 2rem 3rem !important;
}

/* ⑦ 메일 목록 툴바 */
.mb-toolbar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 10px 18px;
    background: #fff;
    border: 1px solid #e0e0e0;
    border-radius: 8px 8px 0 0;
}
.mb-tl { font-size: 0.97rem; font-weight: 500; color: #202124; }
.mb-tr { font-size: 0.77rem; color: #5f6368; }
.nbadge {
    display: inline-block;
    background: #1a73e8;
    color: #fff;
    font-size: 0.67rem;
    font-weight: 700;
    padding: 1px 7px;
    border-radius: 10px;
    margin-left: 5px;
}

/* ⑧ 메일 목록 행 */
.mail-row {
    background: #fff;
    border: 1px solid #e0e0e0;
    border-top: none;
    padding: 13px 18px;
    display: flex;
    align-items: baseline;
    gap: 14px;
}
.mail-row.unread { font-weight: 700; }
.mr-sender  { min-width: 140px; font-size: 0.87rem; color: #202124; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.mr-subject { flex: 1; font-size: 0.87rem; color: #202124; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.mr-snippet { color: #5f6368; font-weight: 400; }
.mr-date    { font-size: 0.79rem; color: #5f6368; white-space: nowrap; font-weight: 400; }

/* ⑨ 메일 본문 카드 (단일 컨테이너) */
.mail-view-end {
    background: #fff;
    border: 1px solid #e0e0e0;
    border-top: none;
    border-radius: 0 0 8px 8px;
    padding: 28px 32px;
}
.mv-subj {
    font-size: 1.3rem;
    font-weight: 500;
    color: #202124;
    padding-bottom: 14px;
    border-bottom: 1px solid #e0e0e0;
    margin-bottom: 18px;
}
.mv-meta-row { font-size: 0.81rem; color: #5f6368; margin-bottom: 3px; }
.mv-meta-row b { color: #202124; font-weight: 400; }
.mv-body { font-size: 0.92rem; color: #202124; line-height: 2.1; margin-top: 22px; }
.mv-url-link {
    color: #1a73e8 !important;
    text-decoration: underline !important;
    font-size: 0.92rem;
    cursor: pointer;
}
.mv-url-link:hover { color: #1558b0 !important; }

/* ⑩ 시스템 푸터 */
.sys-foot {
    margin-top: 28px;
    font-size: 0.71rem;
    color: #9aa0a6;
    text-align: center;
}

/* ── 모바일 전용 뷰 (데스크탑에서 숨김) ── */
.mob-view { display: none !important; }

/* ── 모바일 전용 컴포넌트 스타일 ── */
.mob-topbar {
    display: flex; align-items: center; gap: 12px;
    padding: 14px 16px; background: #fff;
    border-bottom: 1px solid #e8eaed;
    position: sticky; top: 0; z-index: 50;
    box-shadow: 0 1px 3px rgba(0,0,0,0.06);
}
.mob-back {
    width: 34px; height: 34px; display: inline-flex;
    align-items: center; justify-content: center;
    border-radius: 50%; background: #f1f3f4;
    color: #5f6368; text-decoration: none; font-size: 1rem; flex-shrink: 0;
    transition: background 0.15s;
}
.mob-back:hover { background: #e2e5e9; }
.mob-title { font-size: 1.02rem; font-weight: 700; color: #202124; letter-spacing: -0.3px; }

/* 폴더 탭 */
.mob-tabs {
    display: flex; background: #fff;
    border-bottom: 1px solid #e8eaed;
    padding: 0 4px;
}
.mob-tab {
    flex: 1; text-align: center; padding: 12px 4px 10px;
    font-size: 0.79rem; color: #5f6368; text-decoration: none;
    border-bottom: 3px solid transparent; margin-bottom: -1px;
    white-space: nowrap; font-weight: 500; transition: color 0.15s;
}
.mob-tab:hover { color: #202124; }
.mob-tab-active { color: #1a73e8 !important; border-bottom-color: #1a73e8 !important; font-weight: 700 !important; }
.mob-nbadge {
    display: inline-block; background: #1a73e8; color: #fff;
    font-size: 0.62rem; font-weight: 700; padding: 1px 6px;
    border-radius: 10px; margin-left: 4px; vertical-align: middle;
}

/* 메일 목록 */
.mob-mail-list { background: #fff; }
.mob-mail-item {
    display: grid; grid-template-columns: 1fr auto;
    grid-template-areas: "sender date" "subject subject";
    gap: 5px 10px; padding: 15px 16px;
    border-bottom: 1px solid #f1f3f4;
    position: relative;
}
.mob-mail-item::before {
    content: ''; position: absolute;
    left: 0; top: 0; bottom: 0; width: 3px;
    background: #1a73e8; border-radius: 0 2px 2px 0;
}
.mob-mail-sender {
    grid-area: sender; font-size: 0.86rem; font-weight: 700;
    color: #202124; min-width: 0; overflow: hidden;
    text-overflow: ellipsis; white-space: nowrap;
}
.mob-mail-date {
    grid-area: date; font-size: 0.74rem;
    color: #1a73e8; white-space: nowrap; font-weight: 600;
}
.mob-mail-subj {
    grid-area: subject; font-size: 0.84rem; font-weight: 600;
    color: #202124; line-height: 1.5; word-break: keep-all;
}

/* 구분선 */
.mob-divider { border: none; border-top: 8px solid #f1f3f4; margin: 0; }

/* 메일 본문 */
.mob-mail-body { background: #fff; padding: 20px 16px 24px; }
.mob-mail-body-subj {
    font-size: 1.05rem; font-weight: 700; color: #202124;
    line-height: 1.55; margin-bottom: 16px;
    padding-bottom: 14px; border-bottom: 1px solid #e8eaed;
    word-break: keep-all;
}
.mob-meta-block {
    background: #f8f9fa; border-radius: 8px;
    padding: 12px 14px; margin-bottom: 4px;
}
.mob-mail-meta { font-size: 0.78rem; color: #5f6368; margin-bottom: 4px; line-height: 1.7; }
.mob-mail-meta:last-child { margin-bottom: 0; }
.mob-mail-meta b { color: #202124; font-weight: 500; }
.mob-mail-text {
    font-size: 0.9rem; color: #202124; line-height: 2.05;
    margin-top: 20px; word-break: keep-all;
}
.mob-url-box {
    margin-top: 16px; padding: 12px 14px;
    background: #f0f4ff; border-left: 3px solid #1a73e8;
    border-radius: 0 6px 6px 0;
}
.mob-url-link {
    color: #1a73e8 !important; text-decoration: underline !important;
    font-size: 0.86rem; word-break: break-all;
}

/* 빈 폴더 */
.mob-empty {
    padding: 64px 16px; text-align: center;
    color: #9aa0a6; font-size: 0.88rem; line-height: 2;
}

/* 푸터 */
.mob-foot {
    padding: 22px 16px; text-align: center;
    font-size: 0.64rem; color: #bdc1c6; line-height: 1.9;
    border-top: 1px solid #f1f3f4; background: #fafafa;
}

@media (max-width: 768px) {
    html, body { overflow-x: hidden !important; }
    .block-container { padding: 0 !important; }
    /* 모바일 뷰 표시, 데스크탑 2열 레이아웃 숨김 */
    .mob-view { display: block !important; }
    [data-testid="stHorizontalBlock"] { display: none !important; }
}
</style>
""", unsafe_allow_html=True)

    # ────────────────────────────────────────
    # 모바일 전용 뷰 (CSS로 데스크탑에서 숨김)
    # ────────────────────────────────────────
    _t_inbox = "mob-tab-active" if _mob_folder == "inbox" else ""
    _t_sent  = "mob-tab-active" if _mob_folder == "sent"  else ""
    _t_trash = "mob-tab-active" if _mob_folder == "trash" else ""

    st.markdown(
        f"<div class='mob-view'>"
        f"<div class='mob-topbar'>"
        f"<a href='?nav=onboarding' target='_self' class='mob-back'>←</a>"
        f"<span class='mob-title'>📬&nbsp;NPA 웹메일</span>"
        f"</div>"
        f"<div class='mob-tabs'>"
        f"<a href='?intranet_folder=inbox' target='_self' class='mob-tab {_t_inbox}'>받은편지함<span class='mob-nbadge'>1</span></a>"
        f"<a href='?intranet_folder=sent'  target='_self' class='mob-tab {_t_sent}'>보낸편지함</a>"
        f"<a href='?intranet_folder=trash' target='_self' class='mob-tab {_t_trash}'>휴지통</a>"
        f"</div>",
        unsafe_allow_html=True,
    )

    if _mob_folder == "inbox":
        st.markdown(
            f"<div class='mob-mail-body'>"
            f"<div class='mob-mail-body-subj'>[보고] 실종자 이유정(26세, 여) 노트북 포렌식 결과 송부</div>"
            f"<div class='mob-meta-block'>"
            f"<div class='mob-mail-meta'>보낸사람:&nbsp;<b>김희원 &lt;hw.kim@npa.go.kr&gt;</b></div>"
            f"<div class='mob-mail-meta'>받는사람:&nbsp;<b>{player_name} 수사관 &lt;investigator@npa.go.kr&gt;</b></div>"
            f"<div class='mob-mail-meta'>날짜:&nbsp;<b>2024년 3월 17일 (일) 오후 11:59</b></div>"
            f"</div>"
            f"<div class='mob-mail-text'>"
            f"안녕하세요 {player_name} 수사관님,<br>김희원입니다.<br><br>"
            f"요청하신 실종자 이유정(26세, 여) 노트북 포렌식 결과를 송부드립니다.<br>"
            f"실종 직전 2주간 매일 밤 11시에 특정 사이트에 반복 접속했던 특이사항이 발견되었습니다.<br><br>"
            f"표면상으로는 일반적인 종교 단체 홈페이지로 보이나,<br>"
            f"구조가 조금 기이하여 직접 확인해 보시는 것이 좋을 것 같습니다.<br><br>"
            f"접속했던 사이트 URL 아래에 남겨둡니다."
            f"</div>"
            f"<div class='mob-url-box'>"
            f"<a href='?nav=church' target='_self' class='mob-url-link'>http://www.church-of-loving-lamp.or.kr</a>"
            f"</div>"
            f"</div>",
            unsafe_allow_html=True,
        )

    elif _mob_folder == "sent":
        st.markdown(
            f"<div class='mob-mail-body'>"
            f"<div class='mob-mail-body-subj'>[요청] 이유정(26세, 여) 실종 사건 관련 노트북 포렌식 의뢰</div>"
            f"<div class='mob-meta-block'>"
            f"<div class='mob-mail-meta'>보낸사람:&nbsp;<b>{player_name} 수사관 &lt;investigator@npa.go.kr&gt;</b></div>"
            f"<div class='mob-mail-meta'>받는사람:&nbsp;<b>김희원 &lt;hw.kim@npa.go.kr&gt;</b></div>"
            f"<div class='mob-mail-meta'>날짜:&nbsp;<b>2024년 3월 16일 (토) 오후 3:22</b></div>"
            f"</div>"
            f"<div class='mob-mail-text'>"
            f"김희원 수사관님,<br><br>"
            f"어제 서초구에서 발생한 20대 여성 실종 사건 관련입니다.<br>"
            f"피해자 자택에서 확보한 노트북의 긴급 디지털 포렌식을 요청합니다.<br><br>"
            f"피해자가 평소 어떤 사이트에 접속했는지, 특히 밤 시간대 웹 브라우징 기록을 집중적으로 분석해 주시기 바랍니다.<br><br>"
            f"생존 골든타임이 얼마 남지 않았습니다.<br>"
            f"최대한 빠른 회신 부탁드립니다.<br><br>감사합니다."
            f"</div></div>",
            unsafe_allow_html=True,
        )

    else:  # trash
        st.markdown(
            "<div class='mob-empty'>📭<br>휴지통이 비어 있습니다.</div>",
            unsafe_allow_html=True,
        )

    st.markdown(
        "<div class='mob-foot'>"
        "본 메일은 경찰청 내부 그룹웨어 시스템을 통해 발송되었습니다.<br>"
        "무단 전달·유출 금지 &nbsp;·&nbsp; NPA GroupWare v4.2.1"
        "</div>"
        "</div>",  # /mob-view
        unsafe_allow_html=True,
    )

    # ────────────────────────────────────────
    # 데스크탑: 2단 레이아웃 (CSS로 모바일에서 숨김)
    # ────────────────────────────────────────
    col_menu, col_content = st.columns([1, 4])

    # ── 왼쪽 메뉴 (가짜 사이드바) ──
    with col_menu:
        st.markdown(
            "<div style='padding:22px 12px 14px;'>"
            "<div style='font-size:1.05rem;font-weight:600;color:#202124;"
            "letter-spacing:-0.5px;margin-bottom:18px;'>📬&nbsp;NPA 웹메일</div>"
            "<div style='font-size:0.65rem;color:#9aa0a6;letter-spacing:1px;"
            "text-transform:uppercase;margin-bottom:4px;'>메일함</div>"
            "</div>",
            unsafe_allow_html=True,
        )

        folder = st.radio(
            "폴더",
            ["📥 받은편지함 (1)", "📤 보낸편지함", "🗑️ 휴지통"],
            label_visibility="collapsed",
            key="mail_folder_radio",
        )
        st.session_state.mail_folder = folder

        st.markdown(
            "<hr style='border:none;border-top:1px solid #e0e0e0;margin:14px 12px 10px;'>"
            "<div style='font-size:0.65rem;color:#9aa0a6;letter-spacing:1px;"
            "text-transform:uppercase;padding:0 12px;margin-bottom:6px;'>카테고리</div>",
            unsafe_allow_html=True,
        )
        for icon, cat in [("🏷️", "업무"), ("🔔", "알림"), ("👤", "개인")]:
            st.markdown(
                f"<div style='padding:6px 14px;font-size:0.82rem;color:#5f6368;'>"
                f"{icon}&nbsp;&nbsp;{cat}</div>",
                unsafe_allow_html=True,
            )
        st.markdown(
            "<div style='margin-top:30px;font-size:0.67rem;color:#c0c4ca;"
            "text-align:center;padding:0 8px;line-height:1.8;'>"
            "NPA GroupWare v4.2.1<br>경찰청 사이버수사대 내부망</div>",
            unsafe_allow_html=True,
        )
        st.markdown(
            "<div style='margin-top:24px;padding:0 8px;'>"
            "<a href='?nav=onboarding' target='_self' style='"
            "display:block;text-align:center;padding:9px 0;border-radius:20px;"
            "font-size:1.0rem;color:#5f6368;text-decoration:none;"
            "border:1px solid #e0e0e0;background:#fff;transition:background 0.15s;'>"
            "←</a></div>",
            unsafe_allow_html=True,
        )

    # ── 오른쪽 메일 본문 ──
    with col_content:

        # ── 받은편지함 ──
        if "받은편지함" in folder:
            st.markdown(
                "<div class='mb-toolbar'>"
                "<div class='mb-tl'>받은편지함 <span class='nbadge'>1</span></div>"
                "<div class='mb-tr'>1 – 1 / 1 &nbsp;|&nbsp; 동기화: 2024. 3. 17. 오후 11:59</div>"
                "</div>",
                unsafe_allow_html=True,
            )
            st.markdown(
                "<div class='mail-row unread'>"
                "<div class='mr-sender'>김희원 &lt;hw.kim&gt;</div>"
                "<div class='mr-subject'>[보고] 실종자 이유정(26세, 여) 노트북 포렌식 결과 송부"
                "<span class='mr-snippet'> — 요청하신 포렌식 결과를 송부드립니다. "
                "실종 직전 2주간 매일 밤 11시에...</span></div>"
                "<div class='mr-date'>오후 11:59</div>"
                "</div>",
                unsafe_allow_html=True,
            )
            st.markdown(
                f"<div class='mail-view-end'>"
                f"<div class='mv-subj'>[보고] 실종자 이유정(26세, 여) 노트북 포렌식 결과 송부</div>"
                f"<div class='mv-meta-row'>보낸사람:&nbsp;<b>김희원 &lt;hw.kim@npa.go.kr&gt;</b></div>"
                f"<div class='mv-meta-row'>받는사람:&nbsp;<b>{player_name} 수사관 &lt;investigator@npa.go.kr&gt;</b></div>"
                f"<div class='mv-meta-row'>날짜:&nbsp;<b>2024년 3월 17일 (일) 오후 11:59</b></div>"
                f"<div class='mv-body'>"
                f"안녕하세요 {player_name} 수사관님,<br>김희원입니다.<br><br>"
                f"요청하신 실종자 이유정(26세, 여) 노트북 포렌식 결과를 송부드립니다.<br>"
                f"실종 직전 2주간 매일 밤 11시에 특정 사이트에 반복 접속했던 특이사항이 발견되었습니다.<br><br>"
                f"표면상으로는 일반적인 종교 단체 홈페이지로 보이나,<br>"
                f"구조가 조금 기이하여 직접 확인해 보시는 것이 좋을 것 같습니다.<br><br>"
                f"접속했던 사이트 URL 아래에 남겨둡니다.<br><br>"
                f"<a target='_self' href='?nav=church' class='mv-url-link'>"
                f"http://www.church-of-loving-lamp.or.kr"
                f"</a>"
                f"</div>"
                f"</div>",
                unsafe_allow_html=True,
            )

        # ── 보낸편지함 ──
        elif "보낸편지함" in folder:
            st.markdown(
                "<div class='mb-toolbar'>"
                "<div class='mb-tl'>보낸편지함</div>"
                "<div class='mb-tr'>1 – 1 / 1 &nbsp;|&nbsp; 동기화: 2024. 3. 16. 오후 3:22</div>"
                "</div>",
                unsafe_allow_html=True,
            )
            st.markdown(
                "<div class='mail-row'>"
                "<div class='mr-sender'>hw.kim@npa.go.kr</div>"
                "<div class='mr-subject'>[요청] 이유정(26세, 여) 실종 사건 관련 노트북 포렌식 의뢰"
                "<span class='mr-snippet'> — 김희원 수사관님, 어제 서초구에서 발생한 20대 여성 실종 사건...</span></div>"
                "<div class='mr-date'>3월 16일</div>"
                "</div>",
                unsafe_allow_html=True,
            )
            st.markdown(
                f"<div class='mail-view-end'>"
                f"<div class='mv-subj'>[요청] 이유정(26세, 여) 실종 사건 관련 노트북 포렌식 의뢰</div>"
                f"<div class='mv-meta-row'>보낸사람:&nbsp;<b>{player_name} 수사관 &lt;investigator@npa.go.kr&gt;</b></div>"
                f"<div class='mv-meta-row'>받는사람:&nbsp;<b>김희원 &lt;hw.kim@npa.go.kr&gt;</b></div>"
                f"<div class='mv-meta-row'>날짜:&nbsp;<b>2024년 3월 16일 (토) 오후 3:22</b></div>"
                f"<div class='mv-body'>"
                f"김희원 수사관님,<br><br>"
                f"어제 서초구에서 발생한 20대 여성 실종 사건 관련입니다.<br>"
                f"피해자 자택에서 확보한 노트북의 긴급 디지털 포렌식을 요청합니다.<br><br>"
                f"피해자가 평소 어떤 사이트에 접속했는지,"
                f" 특히 밤 시간대 웹 브라우징 기록을 집중적으로 분석해 주시기 바랍니다.<br><br>"
                f"생존 골든타임이 얼마 남지 않았습니다.<br>"
                f"최대한 빠른 회신 부탁드립니다.<br><br>"
                f"감사합니다."
                f"</div>"
                f"</div>",
                unsafe_allow_html=True,
            )

        # ── 휴지통 ──
        else:
            st.markdown(
                "<div class='mb-toolbar'>"
                "<div class='mb-tl'>휴지통</div>"
                "<div class='mb-tr'>0 / 0</div>"
                "</div>",
                unsafe_allow_html=True,
            )
            st.markdown(
                "<div style='background:#fff;border:1px solid #e0e0e0;border-top:none;"
                "border-radius:0 0 8px 8px;padding:64px 0;text-align:center;"
                "color:#9aa0a6;font-size:0.88rem;'>"
                "📭&nbsp;&nbsp;메일이 없습니다.</div>",
                unsafe_allow_html=True,
            )

        st.markdown(
            "<div class='sys-foot'>본 메일은 경찰청 내부 그룹웨어 시스템을 통해 발송되었습니다."
            "&nbsp;|&nbsp; 무단 전달·유출 금지 &nbsp;|&nbsp; NPA GroupWare v4.2.1</div>",
            unsafe_allow_html=True,
        )


# ══════════════════════════════════════════════
#  PHASE 2 : 사랑의 등불 교회 웹사이트
# ══════════════════════════════════════════════
def render_church():
    if st.session_state.get("page") != "church":
        return
    if "church_subpage" not in st.session_state:
        st.session_state.church_subpage = "main"

    player_name = st.session_state.get("player_name", "수사관")
    sp = st.session_state.church_subpage

    # ── 공통 CSS ──
    st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@300;400;500;600;700&display=swap');

#MainMenu{visibility:hidden}header{visibility:hidden}footer{visibility:hidden}
[data-testid="stToolbar"]{display:none!important}
[data-testid="stDecoration"]{display:none!important}
[data-testid="stStatusWidget"]{display:none!important}
[data-testid="collapsedControl"]{display:none!important}

/* ── 타입 스케일 기준
   display : 1.5rem / 700 / -0.5px
   h1      : 1.25rem / 700 / -0.3px
   h2      : 1.05rem / 700 / -0.2px
   body-lg : 0.97rem / 400 / 1.95
   body    : 0.91rem / 400 / 1.85
   small   : 0.81rem / 400 / 1.7
   caption : 0.73rem / 400 / 1.6
── */

html,body,[data-testid="stAppViewContainer"]{
    background:#FAFAFA!important;
    font-family:'Noto Sans KR',sans-serif!important;
    -webkit-font-smoothing:antialiased!important;
}
*,*::before,*::after{
    word-break:keep-all!important;
    overflow-wrap:break-word!important;
}
[data-testid="stHeader"]{background:transparent!important}
.block-container{padding:0 72px 3rem!important;max-width:100%!important}

/* ── GNB ── */
.gnb-wrap{
    background:#fff;border-bottom:1px solid #E5E7EB;
    padding:0 72px;display:flex;align-items:center;
    justify-content:space-between;height:66px;
    position:sticky;top:0;z-index:100;
    margin-left:-72px;margin-right:-72px;
    box-shadow:0 1px 0 #E5E7EB;
}
.gnb-top{display:flex;align-items:center;gap:16px;height:100%}
.gnb-logo{
    font-size:1.15rem;font-weight:700;color:#0A2540;
    letter-spacing:-0.4px;text-decoration:none;line-height:1;align-self:center;
}
.gnb-nav{display:flex;align-items:center;gap:28px;height:100%}
.gnb-nav a{
    font-size:0.875rem;color:#4B5563;text-decoration:none;
    font-weight:500;display:flex;align-items:center;height:100%;
    border-bottom:2px solid transparent;box-sizing:border-box;
    letter-spacing:-0.1px;transition:color 0.15s;
}
.gnb-nav a:hover{color:#0A2540}
.gnb-nav a.gnb-active{color:#0A2540;border-bottom-color:#0A2540;font-weight:700}
.gnb-admin{
    display:inline-flex!important;align-items:center!important;
    color:#6B7280!important;font-size:0.78rem!important;
    border:1px solid #D1D5DB!important;border-radius:5px!important;
    padding:5px 12px!important;
    box-sizing:border-box!important;line-height:1!important;
    white-space:nowrap!important;flex-shrink:0!important;
    text-decoration:none!important;
    transition:all 0.15s!important;
}
.gnb-admin:hover{color:#0A2540!important;border-color:#9CA3AF!important;background:#F9FAFB!important}

/* ── 히어로 밴드 ── */
.hero-band{
    background:#0A2540;padding:24px 72px;
    display:flex;align-items:center;justify-content:space-between;
    margin-left:-72px;margin-right:-72px;
}
.hero-band-title{font-size:1.5rem;font-weight:700;color:#fff;letter-spacing:-0.5px;line-height:1.35}
.hero-band-sub{font-size:0.81rem;color:#94A3B8;letter-spacing:0.3px;margin-top:2px}

/* ── 본문 래퍼 ── */
.page-body{padding:36px 0 4px;background:transparent}

/* ── 브레드크럼 ── */
.breadcrumb{font-size:0.77rem;color:#6B7280;margin-bottom:20px;line-height:1.6}
.breadcrumb a{color:#6B7280;text-decoration:none;transition:color 0.15s}
.breadcrumb a:hover{color:#0A2540}
.breadcrumb span{margin:0 5px;color:#D1D5DB}

/* ── 게시판 ── */
.board-header{border-bottom:2px solid #0A2540;padding-bottom:12px;margin-bottom:16px}
.board-header h2{font-size:1.25rem;font-weight:700;color:#0A2540;margin:0;letter-spacing:-0.3px}
.post-row{
    display:flex;align-items:center;padding:14px 6px;
    border-bottom:1px solid #F3F4F6;gap:12px;
    font-size:0.875rem;color:#374151;transition:background 0.12s;
}
.post-row:hover{background:#F8FAFC}
.post-pin{background:#EF4444;color:#fff;font-size:0.68rem;font-weight:700;padding:2px 8px;border-radius:3px;white-space:nowrap}
.post-normal{background:#F1F5F9;color:#64748B;font-size:0.68rem;font-weight:600;padding:2px 8px;border-radius:3px;white-space:nowrap}
.post-title-cell{flex:1;font-weight:500;color:#111827;line-height:1.5}
.post-title-cell a{color:#111827;text-decoration:none}
.post-title-cell a:hover{color:#0A2540;text-decoration:underline}
.post-title-pin a{color:#111827;text-decoration:none;font-weight:700}
.post-title-pin a:hover{color:#EF4444;text-decoration:underline}
.post-meta-cell{color:#9CA3AF;font-size:0.77rem;white-space:nowrap}

/* ── 게시글 상세 ── */
.article-title{font-size:1.35rem;font-weight:700;color:#0A2540;margin-bottom:10px;line-height:1.5;letter-spacing:-0.3px}
.article-meta{font-size:0.77rem;color:#6B7280;margin-bottom:28px;padding-bottom:16px;border-bottom:1px solid #E5E7EB;line-height:1.7}
.article-body{font-size:0.95rem;line-height:2.0;color:#1E293B}
.article-body p{margin-bottom:22px;color:#1E293B}
.post-section-title{
    font-size:0.93rem;font-weight:700;color:#0A2540;
    background:#F1F5F9;padding:10px 16px;
    border-left:3px solid #0A2540;margin:28px 0 16px;
    border-radius:0 4px 4px 0;letter-spacing:-0.1px;
}
.post-item{display:flex;gap:16px;padding:15px 0;border-bottom:1px solid #F3F4F6;align-items:flex-start}
.post-item-label{font-size:0.8rem;font-weight:700;color:#fff;background:#0A2540;padding:3px 10px;border-radius:3px;white-space:nowrap;margin-top:3px;flex-shrink:0}
.post-item-content{font-size:0.91rem;color:#1E293B;line-height:1.95}
.post-note{font-size:0.8rem;color:#6B7280;line-height:1.7}
.post-warn{display:block;margin-top:8px;font-size:0.81rem;color:#B45309;background:#FFFBEB;border:1px solid #FDE68A;border-radius:4px;padding:8px 14px;line-height:1.8}
.apply-btn{display:inline-block;background:#0A2540;color:#fff!important;font-size:0.91rem;font-weight:600;padding:14px 40px;border-radius:5px;text-decoration:none!important;margin-top:32px;transition:background 0.15s}
.apply-btn:hover{background:#0D3160}

/* ── 제출·버튼 ── */
[data-testid="stButton"]>button:not(:disabled){
    background:#2563EB!important;color:#fff!important;border:none!important;
    padding:12px 48px!important;border-radius:6px!important;
    font-size:0.95rem!important;font-weight:600!important;
    font-family:'Noto Sans KR',sans-serif!important;min-height:unset!important;
    letter-spacing:-0.1px!important;
}
[data-testid="stButton"]>button:not(:disabled):hover{background:#1D4ED8!important}
[data-testid="stButton"]>button:disabled{
    background:#E5E7EB!important;color:#9CA3AF!important;
    border:1px solid #D1D5DB!important;cursor:not-allowed!important;
    padding:12px 48px!important;font-size:0.95rem!important;
}
.dot-wrap div[data-testid="stButton"]>button:not(:disabled){background:transparent!important;color:#fff!important;border:none!important;padding:0!important;min-height:unset!important;box-shadow:none!important}

/* ── 모달 ── */
.modal-overlay{position:fixed;top:0;left:0;width:100vw;height:100vh;background:rgba(0,0,0,0.45);z-index:9999;display:flex;align-items:center;justify-content:center}
.modal-box{background:#fff;border-radius:14px;padding:44px 52px;width:min(520px,88vw);text-align:center;box-shadow:0 24px 64px rgba(0,0,0,0.2);overflow:hidden;max-height:80vh}
.modal-confirm-btn{background:#0A2540;color:#fff;border:none;padding:12px 44px;border-radius:6px;font-size:0.91rem;font-weight:600;cursor:pointer;font-family:'Noto Sans KR',sans-serif;margin-top:4px}
.modal-confirm-btn:hover{background:#0D3160}

/* ── 인트라넷 링크 페이드인 ── */
@keyframes linkFadeIn{from{opacity:0}to{opacity:1}}
.intranet-link{animation:linkFadeIn 3s ease-in forwards;display:inline-block;color:#94A3B8!important;text-decoration:none!important;font-size:0.68rem}
.intranet-link:hover{color:#CBD5E1!important;text-decoration:underline!important}

/* ── 텍스트 색상 강제 ── */
[data-testid="stMarkdownContainer"] p,
[data-testid="stMarkdownContainer"] li,
[data-testid="stMarkdownContainer"] span,
[data-testid="stMarkdownContainer"] strong {color:#1E293B!important}
[data-testid="stText"] p {color:#1E293B!important}

/* ── 라디오 ── */
[data-testid="stRadio"] label p,
[data-testid="stRadio"] label div,
[data-testid="stRadio"] label span {color:#374151!important;font-size:0.91rem!important;line-height:1.6!important}

/* ── Expander 카드 ── */
[data-testid="stExpander"]{
    border:1px solid #E5E7EB!important;border-radius:10px!important;
    background:#fff!important;box-shadow:0 1px 4px rgba(0,0,0,0.05)!important;
    margin-bottom:10px!important;overflow:hidden!important;
}
[data-testid="stExpander"] summary{padding:17px 20px!important;background:#fff!important}
[data-testid="stExpander"] summary:hover{background:#F8FAFC!important}
[data-testid="stExpander"] summary p{font-size:0.93rem!important;font-weight:600!important;color:#111827!important;line-height:1.55!important}
[data-testid="stExpander"] summary svg{color:#9CA3AF!important;flex-shrink:0!important}
[data-testid="stExpander"][data-expanded="true"]{border-color:#0A2540!important;box-shadow:0 3px 12px rgba(10,37,64,0.08)!important}

/* ── 지원서 ── */
.form-title{font-size:1.2rem;font-weight:700;color:#0A2540;margin-bottom:6px;letter-spacing:-0.3px}
.form-subtitle{font-size:0.83rem;color:#6B7280;margin-bottom:0;line-height:1.65}

/* ── Q3 혈흔 텍스트 ── */
@keyframes bloodFade{0%{opacity:0}40%{opacity:0}100%{opacity:1}}
.blood-text{animation:bloodFade 5s ease-in forwards;color:#7F1D1D;font-size:0.91rem;line-height:2.2;margin-top:48px;padding:26px 30px;border-left:3px solid #991B1B;background:#FFF5F5;white-space:pre-line;font-family:'Noto Sans KR',sans-serif;border-radius:0 6px 6px 0}

/* ── 섹션 타이틀 ── */
.sec-title{font-size:1.05rem;font-weight:700;color:#0A2540;border-bottom:2px solid #E5E7EB;padding-bottom:11px;margin-bottom:20px;letter-spacing:-0.2px}

/* ── 오시는 길 ── */
.map-ph{background:#F1F5F9;border:1px solid #CBD5E1;border-radius:8px;height:200px;display:flex;align-items:center;justify-content:center;color:#64748B;font-size:0.88rem;margin-bottom:20px}
.addr{color:#374151;font-size:0.9rem;line-height:2.3;margin-bottom:20px}

/* ── 숨김 dot 버튼 ── */
.dot-wrap div[data-testid="stButton"]>button{background:transparent!important;color:#fff!important;border:none!important;font-size:0.4rem!important;padding:0!important;min-height:unset!important;box-shadow:none!important}

/* ── 입력 필드 ── */
[data-testid="stTextInput"] input{
    background:#fff!important;border:1.5px solid #CBD5E1!important;
    border-radius:7px!important;color:#1E293B!important;
    font-family:'Noto Sans KR',sans-serif!important;font-size:0.93rem!important;
    padding:11px 14px!important;transition:border-color 0.2s,box-shadow 0.2s!important;
}
[data-testid="stTextInput"] input:focus{border-color:#2563EB!important;box-shadow:0 0 0 3px rgba(37,99,235,0.12)!important;outline:none!important}
[data-testid="stTextInput"] label{color:#374151!important;font-size:0.82rem!important;font-weight:600!important;margin-bottom:4px!important}

/* ── 푸터 ── */
.c-foot{
    background:#0A2540;color:#94A3B8;text-align:center;
    padding:28px 72px;font-size:0.78rem;
    font-family:'Noto Sans KR',sans-serif;
    margin-left:-72px;margin-right:-72px;line-height:1.9;
}
.c-foot strong{color:#fff}

/* ════════════════════════════════
   모바일 반응형
════════════════════════════════ */
@media (max-width: 768px) {
    html, body, [data-testid="stAppViewContainer"] { overflow-x: hidden !important; }
    .block-container{padding:90px 16px 3rem!important}

    /* ── GNB 고정 ── */
    .gnb-wrap{
        position:fixed!important;top:0!important;left:0!important;right:0!important;
        width:100%!important;margin-left:0!important;margin-right:0!important;
        padding:0 14px!important;height:auto!important;
        flex-direction:column!important;align-items:stretch!important;gap:0!important;
        z-index:9999!important;box-shadow:0 2px 10px rgba(0,0,0,0.10)!important;
        box-sizing:border-box!important;
    }
    .gnb-top{
        display:flex!important;flex-direction:row!important;
        align-items:center!important;justify-content:space-between!important;
        height:auto!important;padding:10px 0 8px!important;gap:8px!important;
    }
    .gnb-logo{font-size:1rem!important;line-height:1!important}
    .gnb-admin{font-size:0.7rem!important;padding:4px 9px!important}
    .gnb-nav{
        width:100%!important;height:auto!important;
        display:flex!important;flex-direction:row!important;
        overflow-x:auto!important;-webkit-overflow-scrolling:touch!important;
        gap:0!important;padding:0 0 8px!important;flex-wrap:nowrap!important;
        -ms-overflow-style:none!important;scrollbar-width:none!important;
        border-top:1px solid #F3F4F6!important;
    }
    .gnb-nav::-webkit-scrollbar{display:none!important}
    .gnb-nav a{
        white-space:nowrap!important;font-size:0.82rem!important;
        height:36px!important;padding:0 14px!important;
        border-bottom:2px solid transparent!important;flex-shrink:0!important;
    }
    .gnb-nav a.gnb-active{border-bottom-color:#0A2540!important}

    /* ── 히어로 배너 ── */
    .hero-band{margin-left:-16px!important;margin-right:-16px!important;padding:16px 16px!important;flex-direction:column!important;align-items:flex-start!important;gap:5px!important}
    .hero-band-title{font-size:1.15rem!important;letter-spacing:-0.3px!important}
    .hero-band-sub{font-size:0.73rem!important}

    /* ── 게시판·게시글 ── */
    .board-header h2{font-size:1.05rem!important}
    .post-row{flex-wrap:wrap!important;padding:12px 4px!important;gap:6px!important}
    .post-title-cell{font-size:0.88rem!important;width:100%!important}
    .post-meta-cell{font-size:0.73rem!important;width:100%!important}
    .article-title{font-size:1.1rem!important;letter-spacing:-0.2px!important}
    .article-meta{font-size:0.75rem!important}
    .article-body{font-size:0.91rem!important;line-height:1.95!important}

    /* ── expander ── */
    [data-testid="stExpander"] summary{padding:14px 16px!important}
    [data-testid="stExpander"] summary p{font-size:0.88rem!important}

    /* ── 기타 텍스트 ── */
    .sec-title{font-size:0.97rem!important}
    .breadcrumb{font-size:0.73rem!important}
    .blood-text{font-size:0.88rem!important;padding:18px 16px!important;margin-top:28px!important}
    .form-title{font-size:1.05rem!important}
    .form-subtitle{font-size:0.8rem!important}
    .addr{font-size:0.86rem!important;line-height:2.1!important}

    /* ── 푸터 ── */
    .c-foot{margin-left:-16px!important;margin-right:-16px!important;padding:20px 16px!important;font-size:0.7rem!important}

    /* ── 컬럼 스택 ── */
    [data-testid="stHorizontalBlock"]{flex-wrap:wrap!important}
    [data-testid="stHorizontalBlock"]>[data-testid="stColumn"]{
        flex:1 1 100%!important;min-width:0!important;max-width:100%!important;
    }

    /* ── 인라인 카드 모바일 보정 ── */
    [data-testid="stMarkdownContainer"] div[style*="border:1px solid #E5E7EB;border-top:3px"]{
        padding:20px 16px!important;
    }
    [data-testid="stMarkdownContainer"] div[style*="padding:28px 20px;text-align:center"]{
        padding:20px 14px!important;
    }
    [data-testid="stMarkdownContainer"] div[style*="font-size:2rem;font-weight:800"]{
        font-size:1.6rem!important;
    }
    .article-body p{margin-bottom:18px!important}
}
</style>
""", unsafe_allow_html=True)

    # ── GNB ──
    a_intro  = "gnb-active" if sp == "main"                          else ""
    a_grace  = "gnb-active" if sp in ("grace_board", "grace_post")  else ""
    a_faq    = "gnb-active" if sp == "faq"                          else ""
    a_form   = "gnb-active" if sp == "form"                         else ""
    a_pastor = "gnb-active" if sp == "pastor_login"                 else ""
    st.markdown(
        f"<div class='gnb-wrap'>"
        f"<div class='gnb-top'>"
        f"<a class='gnb-logo' target='_self' href='?church_nav=main'>새생명교회</a>"
        f"<a target='_self' href='?church_nav=pastor_login' class='gnb-admin {a_pastor}'>교역자 로그인</a>"
        f"</div>"
        f"<nav class='gnb-nav'>"
        f"<a target='_self' href='?church_nav=main' class='{a_intro}'>교회소개</a>"
        f"<a target='_self' href='?church_nav=grace_board' class='{a_grace}'>은혜 나눔</a>"
        f"<a target='_self' href='?church_nav=faq' class='{a_faq}'>봉사 FAQ</a>"
        f"<a target='_self' href='?church_nav=form' class='{a_form}'>온라인 지원서</a>"
        f"</nav></div>",
        unsafe_allow_html=True,
    )

    # ── 상단 배너 (메인 페이지만) ──
    if sp == "main":
        _img_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "image_new.png.png")
        if os.path.exists(_img_path):
            with open(_img_path, "rb") as _f:
                _b64 = base64.b64encode(_f.read()).decode()
            st.markdown(
                f"<div style='width:100vw;position:relative;left:50%;transform:translateX(-50%);line-height:0;overflow:hidden;'>"
                f"<img src='data:image/png;base64,{_b64}' style='width:100%;display:block;'>"
                f"</div>",
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                "<div style='width:100vw;position:relative;left:50%;transform:translateX(-50%);"
                "background:#0A2540;padding:60px;text-align:center;"
                "color:#fff;font-size:2rem;font-weight:700;font-family:Noto Sans KR,sans-serif;'>"
                "새생명교회</div>",
                unsafe_allow_html=True,
            )
        st.markdown(
            "<div class='hero-band'>"
            "<div class='hero-band-title'>새생명교회에 오신 것을 환영합니다</div>"
            "<div class='hero-band-sub'>SAENGMYEONG CHURCH · SINCE 1997</div>"
            "</div>",
            unsafe_allow_html=True,
        )

    # ── 본문 시작 ──
    st.markdown("<div class='page-body'>", unsafe_allow_html=True)

    # ════════════════════
    if sp == "main":
    # ════════════════════
        # ── 담임목사 환영 인사 ──
        st.markdown("""
<div style='margin:32px 0 48px;'>
  <div style='font-size:0.68rem;font-weight:700;color:#9CA3AF;letter-spacing:3px;
              text-transform:uppercase;margin-bottom:16px;'>Pastor&#39;s Welcome</div>
  <div style='font-size:1.18rem;font-weight:700;color:#0A2540;line-height:1.6;margin-bottom:16px;'>
    새생명교회에 오신 것을 환영합니다.
  </div>
  <div style='font-size:0.95rem;color:#374151;line-height:2.1;max-width:680px;'>
    <p style='margin:0 0 14px;'>사랑하는 형제자매 여러분, 세상의 잣대와 차가운 시선 속에서 얼마나 지치셨습니까?</p>
    <p style='margin:0 0 14px;'>이곳은 상처 입고 버림받은 영혼들이 모여, 오직 조건 없는 사랑만을 나누는 안식처입니다.</p>
    <p style='margin:0;'>당신의 무거운 짐을 이곳에 내려놓으세요.</p>
  </div>
</div>
""", unsafe_allow_html=True)

        st.markdown("<hr style='border:none;border-top:1px solid #E5E7EB;margin:0 0 40px;'>",
                    unsafe_allow_html=True)

        # ── 3가지 핵심 가치 ──
        st.markdown(
            "<div style='font-size:0.68rem;font-weight:700;color:#9CA3AF;letter-spacing:3px;"
            "text-transform:uppercase;margin-bottom:20px;'>Core Values</div>"
            "<div style='font-size:1.05rem;font-weight:700;color:#0A2540;margin-bottom:24px;'>"
            "새생명교회의 3가지 핵심 가치</div>",
            unsafe_allow_html=True,
        )
        _v1, _v2, _v3 = st.columns(3)
        for _vcol, _num, _title, _sub_title, _body in [
            (_v1, "01", "경계 없는 융합", "완전한 하나 됨",
             "우리는 서로의 이름표를 찢고, 피부의 경계를 허뭅니다. 내 옆에 앉은 자매의 맥박이 내 혈관을 타고 흐르고, "
             "형제의 온기가 내 내장을 데울 때, 우리는 비로소 분리되지 않는 하나의 거룩한 공동체가 됩니다."),
            (_v2, "02", "완전한 적출", "텅 빈 그릇",
             "배를 짓누르는 세속의 욕망들을 입 밖으로 남김없이 게워내십시오. 탁한 피를 모두 뽑아내어 텅 빈 혈관에 "
             "오직 목사님이 주시는 '빛의 수액'만을 채워 넣을 때, 당신의 안구는 환희로 뒤집힐 것입니다."),
            (_v3, "03", "마비된 평안", "고통의 초월",
             "의심은 뇌를 갉아먹는 벌레입니다. 기도로 뇌수를 하얗게 마비시키십시오. "
             "바늘이 파고들고 뼈가 으스러지는 육신의 고통마저 달콤한 쾌락으로 엉겨 붙는 순간, "
             "우리의 진짜 기적이 척수를 타고 오릅니다."),
        ]:
            with _vcol:
                st.markdown(
                    f"<div style='border:1px solid #E5E7EB;border-top:3px solid #0A2540;"
                    f"border-radius:0 0 10px 10px;padding:28px 24px;'>"
                    f"<div style='font-size:0.68rem;font-weight:700;color:#9CA3AF;letter-spacing:2px;margin-bottom:12px;'>{_num}</div>"
                    f"<div style='font-size:1.0rem;font-weight:700;color:#0A2540;margin-bottom:4px;'>{_title}</div>"
                    f"<div style='font-size:0.75rem;color:#6B7280;margin-bottom:16px;font-style:italic;'>{_sub_title}</div>"
                    f"<div style='font-size:0.85rem;line-height:1.95;color:#374151;'>{_body}</div>"
                    f"</div>",
                    unsafe_allow_html=True,
                )

        # ── 통계 ──
        st.markdown("<div style='height:48px;'></div>", unsafe_allow_html=True)
        st.markdown("<hr style='border:none;border-top:1px solid #E5E7EB;margin:0 0 40px;'>",
                    unsafe_allow_html=True)
        st.markdown(
            "<div style='font-size:0.68rem;font-weight:700;color:#9CA3AF;letter-spacing:3px;"
            "text-transform:uppercase;margin-bottom:20px;'>Ministry Statistics</div>"
            "<div style='font-size:1.05rem;font-weight:700;color:#0A2540;margin-bottom:24px;'>사역 현황</div>",
            unsafe_allow_html=True,
        )
        _s1, _s2, _s3 = st.columns(3)
        for _scol, _num, _label, _sub in [
            (_s1, "1,200회",  "독거노인 반찬 나눔",                   "지난 10년간 누적 횟수"),
            (_s2, "8,450명",  "하계 특별 영성원 수련 및 헌혈 참여자",  "여성 참여 비율 98%"),
            (_s3, "8,120건",  "신경외과·정신과 연계 치료비 지원",      "영성원 훈련 후 지원 건수"),
        ]:
            with _scol:
                st.markdown(
                    f"<div style='padding:28px 20px;text-align:center;border-bottom:3px solid #0A2540;'>"
                    f"<div style='font-size:2rem;font-weight:800;color:#0A2540;margin-bottom:8px;'>{_num}</div>"
                    f"<div style='font-size:0.88rem;font-weight:600;color:#1E293B;margin-bottom:6px;'>{_label}</div>"
                    f"<div style='font-size:0.75rem;color:#6B7280;'>{_sub}</div>"
                    f"</div>",
                    unsafe_allow_html=True,
                )
        st.markdown("<div style='height:16px;'></div>", unsafe_allow_html=True)


    # ════════════════════
    elif sp == "grace_board":
    # ════════════════════
        st.markdown(
            "<div class='breadcrumb'>"
            "<a target='_self' href='?church_nav=main'>홈</a><span>›</span>은혜 나눔"
            "</div>"
            "<div class='board-header'><h2>은혜 나눔</h2></div>",
            unsafe_allow_html=True,
        )
        _grace_posts = [
            (True,  1, "처음엔 두려웠지만, 지금은 평안합니다.",  "김민지 자매", "2024.06.10", "2,841",
             "처음 영성원 지하의 '정화의 방'에 들어갔을 땐, 소독약 냄새와 차가운 공기 때문에 솔직히 조금 무서웠습니다. "
             "하지만 목사님께서 웃으며 수액을 놔주시는 순간, 불안감은 씻은 듯이 사라졌습니다. "
             "수액이 들어올 때 혈관을 타고 차가운 벌레들이 기어 다니는 것 같은 이상한 감각이 있었지만, "
             "목사님은 그게 제 안의 죄악이 밀려나는 느낌이라고 하셨어요. "
             "신기하게도 그날 이후로 저는 배고픔도, 피로도 느끼지 못합니다. "
             "저는 이제 잠을 자지 않고도 밤새 하얀 벽을 보며 웃을 수 있습니다."),
            (False, 2, "수액 치유 체험 후 제 삶이 달라졌어요.",  "박은혜 자매", "2024.05.30", "743",
             "저는 늘 사람들의 시선에 쫓기며 살던 예민한 사람이었습니다. "
             "하지만 목사님의 특별 처방을 받고 난 후 제 삶은 180도 달라졌습니다. "
             "약을 먹고 나면 머릿속에 꽉 차 있던 복잡한 생각들이 말 그대로 하얗게 지워집니다. "
             "요즘 머리카락이 한 움큼씩 빠지고 손톱 밑이 검게 변하고 있지만, "
             "목사님 말씀대로 쓸모없는 과거의 허물이 벗겨지는 거겠죠. "
             "어제는 제 입에서 제 목소리가 아닌 다른 사람의 기괴한 중얼거림이 흘러나와 깜짝 놀랐지만, "
             "곧 성령이 제 입을 빌려 말씀하시는 거라 깨달았습니다. "
             "제 자아는 이제 완전히 텅 비었습니다. 너무나 홀가분합니다."),
            (False, 3, "영성원에서 보낸 2주, 잊을 수 없는 은혜.", "최인주 자매", "2024.05.18", "612",
             "영성원에서의 2주는 단절이 아닌 완전한 융합이었습니다. "
             "창문 하나 없는 하얀 방에서 며칠 동안 기도를 드리다 보니, "
             "어느 순간 저 하얀 벽과 제 피부의 경계가 희미해지는 황홀한 경험을 했습니다. "
             "벽이 숨을 쉬듯 천천히 오르락내리락하는 걸 보았고, "
             "벽 너머에서 다른 형제자매들의 심장 뛰는 소리가 제 맥박과 똑같은 박자로 들려왔습니다. "
             "우리는 정말 하나의 유기체로 연결된 느낌이었어요. "
             "퇴소하는 날, 제 짐을 챙기러 온 가족들의 얼굴이 찰흙이 뭉개진 것처럼 기괴하게 보여서 하마터면 비명을 지를 뻔했습니다. "
             "오직 목사님의 얼굴만이 뚜렷하게 빛나 보였습니다. "
             "저는 하루빨리 가족이라는 껍데기를 버리고 진짜 가족이 있는 곳으로 돌아가고 싶습니다."),
            (False, 4, "가족의 반대를 이기고 참 평안을 찾았습니다.", "정지민 자매", "2024.05.02", "488",
             "엄마는 제가 변했다며 매일 울며 매달렸습니다. "
             "병원에 가보자고 제 팔을 붙잡았을 때, 엄마의 손길이 마치 징그러운 곤충이 닿은 것처럼 끔찍하게 느껴져서 "
             "저도 모르게 엄마를 세게 밀쳐버렸습니다. "
             "엄마가 바닥에 쓰러져 우는데도, 제 마음속에는 아무런 슬픔이나 죄책감이 일지 않았어요. "
             "오히려 입가에 자꾸만 웃음이 새어 나와서 억지로 참아야 했습니다. "
             "비타민을 먹은 뒤로 제 안의 불필요한 감정선들이 모두 끊어진 것 같아요. "
             "슬픔, 공감, 애착 같은 세속적인 감정들이 뇌에서 깨끗하게 적출된 기분입니다. "
             "저를 낳아준 사람의 눈물보다 목사님의 숨소리가 더 애틋하게 느껴집니다. 저는 완벽해졌습니다."),
            (False, 5, "비타민을 처음 받던 날의 기억.",            "한지우 자매", "2024.04.21", "371",
             "목사님이 주신 붉은색 캡슐을 처음 삼켰을 때, 약이 식도를 타고 내려가는 게 아니라 "
             "마치 목구멍에 작은 씨앗이 심어진 듯한 묘한 이물감이 들었습니다. "
             "처음 며칠은 뱃속에서 무언가 꿈틀거리는 것 같아 속이 메스꺼웠지만, "
             "이제는 제 뱃속의 새로운 박동에 익숙해졌습니다. "
             "조용한 밤이면 제 명치끝에서 누군가 아주 작게 속삭이는 소리가 들립니다. "
             "목사님은 그것이 제 안에 자라나는 새로운 영이라고 축복해 주셨습니다. "
             "요즘은 밥을 씹어 넘기는 상상만 해도 구역질이 납니다. 제 안의 성령이 세상의 음식물을 거부하는 거겠죠. "
             "제 갈비뼈 안쪽을 부드럽게 긁어대는 이 은혜로운 감각을 평생 느끼며 살고 싶습니다."),
        ]

        st.markdown("<div style='height:4px;'></div>", unsafe_allow_html=True)
        for _is_pin, _no, _title, _author, _date, _views, _body in _grace_posts:
            _initial = _author[0]
            _label = f"{'★  ' if _is_pin else ''}{_title}"
            with st.expander(_label):
                _body_html = "".join(
                    f"<p style='margin:0 0 14px;'>{s.strip()}</p>"
                    for s in _body.split(". ") if s.strip()
                )
                st.markdown(
                    f"<div style='display:flex;align-items:center;gap:12px;margin-bottom:18px;"
                    f"padding-bottom:14px;border-bottom:1px solid #F1F5F9;'>"
                    f"<div style='width:36px;height:36px;border-radius:50%;background:#0A2540;"
                    f"color:#fff;display:flex;align-items:center;justify-content:center;"
                    f"font-size:0.88rem;font-weight:700;flex-shrink:0;'>{_initial}</div>"
                    f"<div>"
                    f"<div style='font-size:0.88rem;font-weight:600;color:#1E293B;'>{_author}</div>"
                    f"<div style='font-size:0.72rem;color:#9CA3AF;margin-top:2px;'>"
                    f"{_date} &nbsp;·&nbsp; 조회 {_views}</div>"
                    f"</div></div>"
                    f"<div style='font-size:0.91rem;color:#374151;line-height:2.0;"
                    f"padding:14px 16px;background:#F8FAFC;border-left:3px solid #E2E8F0;border-radius:0 6px 6px 0;'>"
                    f"{_body_html}</div>",
                    unsafe_allow_html=True,
                )

    # ════════════════════
    elif sp == "grace_post":
    # ════════════════════
        # 게시글 데이터 (grace_board와 동일 구조)
        _all_posts = {
            1: ("처음엔 두려웠지만, 지금은 평안합니다.", "김민지 자매", "2024.06.10", "2,841",
                "처음 영성원 지하의 '정화의 방'에 들어갔을 땐, 소독약 냄새와 차가운 공기 때문에 솔직히 조금 무서웠습니다. "
                "하지만 목사님께서 웃으며 수액을 놔주시는 순간, 불안감은 씻은 듯이 사라졌습니다. "
                "수액이 들어올 때 혈관을 타고 차가운 벌레들이 기어 다니는 것 같은 이상한 감각이 있었지만, "
                "목사님은 그게 제 안의 죄악이 밀려나는 느낌이라고 하셨어요. "
                "신기하게도 그날 이후로 저는 배고픔도, 피로도 느끼지 못합니다. "
                "저는 이제 잠을 자지 않고도 밤새 하얀 벽을 보며 웃을 수 있습니다."),
            2: ("수액 치유 체험 후 제 삶이 달라졌어요.", "박은혜 자매", "2024.05.30", "743",
                "저는 늘 사람들의 시선에 쫓기며 살던 예민한 사람이었습니다. "
                "하지만 목사님의 특별 처방을 받고 난 후 제 삶은 180도 달라졌습니다. "
                "약을 먹고 나면 머릿속에 꽉 차 있던 복잡한 생각들이 말 그대로 하얗게 지워집니다. "
                "요즘 머리카락이 한 움큼씩 빠지고 손톱 밑이 검게 변하고 있지만, "
                "목사님 말씀대로 쓸모없는 과거의 허물이 벗겨지는 거겠죠. "
                "어제는 제 입에서 제 목소리가 아닌 다른 사람의 기괴한 중얼거림이 흘러나와 깜짝 놀랐지만, "
                "곧 성령이 제 입을 빌려 말씀하시는 거라 깨달았습니다. "
                "제 자아는 이제 완전히 텅 비었습니다. 너무나 홀가분합니다."),
            3: ("영성원에서 보낸 2주, 잊을 수 없는 은혜.", "최인주 자매", "2024.05.18", "612",
                "영성원에서의 2주는 단절이 아닌 완전한 융합이었습니다. "
                "창문 하나 없는 하얀 방에서 며칠 동안 기도를 드리다 보니, "
                "어느 순간 저 하얀 벽과 제 피부의 경계가 희미해지는 황홀한 경험을 했습니다. "
                "벽이 숨을 쉬듯 천천히 오르락내리락하는 걸 보았고, "
                "벽 너머에서 다른 형제자매들의 심장 뛰는 소리가 제 맥박과 똑같은 박자로 들려왔습니다. "
                "퇴소하는 날, 제 짐을 챙기러 온 가족들의 얼굴이 찰흙이 뭉개진 것처럼 기괴하게 보여서 하마터면 비명을 지를 뻔했습니다. "
                "오직 목사님의 얼굴만이 뚜렷하게 빛나 보였습니다. "
                "저는 하루빨리 가족이라는 껍데기를 버리고 진짜 가족이 있는 곳으로 돌아가고 싶습니다."),
            4: ("가족의 반대를 이기고 참 평안을 찾았습니다.", "정지민 자매", "2024.05.02", "488",
                "엄마는 제가 변했다며 매일 울며 매달렸습니다. "
                "병원에 가보자고 제 팔을 붙잡았을 때, 엄마의 손길이 마치 징그러운 곤충이 닿은 것처럼 끔찍하게 느껴져서 "
                "저도 모르게 엄마를 세게 밀쳐버렸습니다. "
                "엄마가 바닥에 쓰러져 우는데도, 제 마음속에는 아무런 슬픔이나 죄책감이 일지 않았어요. "
                "오히려 입가에 자꾸만 웃음이 새어 나와서 억지로 참아야 했습니다. "
                "슬픔, 공감, 애착 같은 세속적인 감정들이 뇌에서 깨끗하게 적출된 기분입니다. "
                "저를 낳아준 사람의 눈물보다 목사님의 숨소리가 더 애틋하게 느껴집니다. 저는 완벽해졌습니다."),
            5: ("비타민을 처음 받던 날의 기억.", "한지우 자매", "2024.04.21", "371",
                "목사님이 주신 붉은색 캡슐을 처음 삼켰을 때, 약이 식도를 타고 내려가는 게 아니라 "
                "마치 목구멍에 작은 씨앗이 심어진 듯한 묘한 이물감이 들었습니다. "
                "처음 며칠은 뱃속에서 무언가 꿈틀거리는 것 같아 속이 메스꺼웠지만, "
                "이제는 제 뱃속의 새로운 박동에 익숙해졌습니다. "
                "조용한 밤이면 제 명치끝에서 누군가 아주 작게 속삭이는 소리가 들립니다. "
                "요즘은 밥을 씹어 넘기는 상상만 해도 구역질이 납니다. "
                "제 갈비뼈 안쪽을 부드럽게 긁어대는 이 은혜로운 감각을 평생 느끼며 살고 싶습니다."),
        }
        _pid = st.session_state.get("grace_post_id", 1)
        _post = _all_posts.get(_pid, _all_posts[1])
        _p_title, _p_author, _p_date, _p_views, _p_body = _post

        st.markdown(
            "<div class='breadcrumb'>"
            "<a target='_self' href='?church_nav=main'>홈</a><span>›</span>"
            "<a target='_self' href='?church_nav=grace_board'>은혜 나눔</a><span>›</span>"
            "게시글 상세</div>",
            unsafe_allow_html=True,
        )
        st.markdown(
            f"<div class='article-title'>{_p_title}</div>"
            f"<div class='article-meta'>작성자: {_p_author} &nbsp;|&nbsp; {_p_date} &nbsp;|&nbsp; 조회수 {_p_views}</div>",
            unsafe_allow_html=True,
        )
        _article_html = "".join(
            f"<p>{s.strip()}</p>"
            for s in _p_body.split(". ") if s.strip()
        )
        st.markdown(
            f"<div class='article-body'>{_article_html}</div>",
            unsafe_allow_html=True,
        )
        st.markdown(
            "<div style='margin-top:32px;'>"
            "<a target='_self' href='?church_nav=grace_board' "
            "style='color:#6B7280;font-size:0.85rem;text-decoration:none;'>← 목록으로 돌아가기</a>"
            "</div>",
            unsafe_allow_html=True,
        )

    # ════════════════════
    elif sp == "faq":
    # ════════════════════
        st.markdown(
            "<div class='breadcrumb'>"
            "<a target='_self' href='?church_nav=main'>홈</a><span>›</span>봉사 FAQ"
            "</div>"
            "<div class='board-header'><h2>봉사 FAQ</h2></div>",
            unsafe_allow_html=True,
        )
        _faqs = [
            (
                "Q1. 2주간 합숙 기간 동안 가족과 정말 한 번도 연락할 수 없나요?",
                "네. 휴대폰 등 모든 전자기기는 입소 즉시 '안식의 상자'에 영구 보관됩니다. "
                "세속의 끈을 잘라내야만 온전한 빛이 스며들 수 있습니다. 불안해하지 마세요. "
                "작년 13기 봉사자 20명 중 4분은 영성원에서 너무나 큰 평안을 얻으시어, "
                "합숙이 끝난 후에도 집으로 돌아가기를 거부하시고 아직까지 영성원 지하 '깊은 묵상의 방'에 남아 "
                "빛을 섬기고 계십니다. 여러분도 곧 그 평안을 이해하게 될 것입니다.",
            ),
            (
                "Q2. 개인 속옷이나 세면도구는 왜 지참할 수 없나요?",
                "외부의 불순물이 묻은 의복은 철저히 통제됩니다. 교회에서 체형에 맞게 특수 제작된 "
                "'정결 위생용품'을 매일 배급해 드립니다. 이를 위해 지원서에 속옷 치수와 신체 사이즈를 "
                "아주 상세히 받고 있으니 한 치의 오차 없이 기재해 주셔야 합니다. "
                "지급된 수련복은 피부와 완벽히 밀착되어 마치 두 번째 피부처럼 느껴질 것입니다. "
                "억지로 벗으려 하거나 찢지 마십시오.",
            ),
            (
                "Q3. 합숙 기간 동안 식사는 어떻게 제공되나요? 평소 먹는 약을 가져가도 되나요?",
                "일반적인 식사는 일절 제공되지 않습니다. 세속의 음식물은 위장을 썩게 만들 뿐입니다. "
                "대신 매일 정해진 시간에 목사님께서 직접 축복하신 '고농축 빛의 비타민 수액'이 투여됩니다. "
                "입소 후 3일 정도는 심한 구토와 환각, 혈관이 타들어 가는 듯한 통증이 동반될 수 있으나, "
                "이는 더러운 자아가 빠져나가는 자연스러운 명현 현상입니다. "
                "개인이 지참한 정신과 약물이나 진통제 복용은 절대 금지되며, "
                "적발 시 즉각 '특별 정화실'로 격리됩니다.",
            ),
            (
                "Q4. 밤에 숙소 밖에서 이상한 소리가 들린다는 후기가 있던데 괜찮은 건가요?",
                "심야 시간(밤 11시~새벽 3시)은 가장 깊은 영적 수술이 이루어지는 '정화의 시간'입니다. "
                "가끔 복도나 옆방에서 짐승이 긁는 듯한 소리나 찢어지는 듯한 비명이 들릴 수 있습니다. "
                "이는 형제자매님들의 몸에서 악한 영이 뽑혀 나가는 거룩한 신음이니 "
                "절대 방문을 열고 나오거나 밖을 내다보지 마십시오. "
                "밤 11시 이후, 숙소의 문은 여러분의 안전을 위해 밖에서 굳게 잠깁니다.",
            ),
            (
                "Q5. 만약 중간에 너무 힘들면 퇴소할 수 있나요?",
                "영성원의 문을 여는 순간, 귀하의 육신은 이미 새생명교회의 거룩한 자산이 됩니다. "
                "정화 의식이 시작된 후 중간에 멈추면 영혼이 갈기갈기 찢어지는 부작용이 발생하므로 "
                "중도 퇴소는 원칙적으로 불가능합니다. "
                "육신의 고통을 이기지 못해 도망치려 했던 소수의 분들이 계셨으나, "
                "교회 내부의 '특별 의료팀'이 그들을 안전하게 제압하여 끝까지 헌혈과 봉사를 마칠 수 있도록 "
                "온 힘을 다해 '도와'드렸습니다. 안심하고 몸을 맡기십시오.",
            ),
        ]
        for _faq_idx, (_q, _a) in enumerate(_faqs, 1):
            with st.expander(_q):
                _a_html = "".join(
                    f"<p style='margin:0 0 12px;'>{s.strip()}</p>"
                    for s in _a.split(". ") if s.strip()
                )
                st.markdown(
                    f"<div style='padding:4px 0 8px 0;'>"
                    f"<div style='margin-top:4px;background:#F8FAFC;border-left:3px solid #0A2540;border-radius:0 8px 8px 0;padding:16px 18px;'>"
                    f"<div style='display:flex;gap:10px;align-items:flex-start;'>"
                    f"<span style='flex-shrink:0;font-size:0.85rem;font-weight:700;color:#0A2540;letter-spacing:0.05em;margin-top:2px;'>A.</span>"
                    f"<div style='font-size:0.91rem;color:#374151;line-height:1.9;'>{_a_html}</div>"
                    f"</div>"
                    f"</div>"
                    f"</div>",
                    unsafe_allow_html=True,
                )

    # ════════════════════
    elif sp == "form":
    # ════════════════════
        st.markdown(
            "<div class='breadcrumb'>"
            "<a target='_self' href='?church_nav=main'>홈</a><span>›</span>"
            "<a target='_self' href='?church_nav=board'>소식 및 참여</a><span>›</span>"
            "<a target='_self' href='?church_nav=post'>봉사활동 모집</a><span>›</span>"
            "지원서 작성</div>",
            unsafe_allow_html=True,
        )
        st.markdown(
            "<div class='form-title'>청년부 하계 봉사 온라인 지원서</div>"
            "<div class='form-subtitle'>아래 문항에 솔직하게 답변해 주세요. 모든 응답은 선발에만 활용됩니다.</div>",
            unsafe_allow_html=True,
        )
        st.markdown("<hr style='border:none;border-top:1px solid #E5E7EB;margin:20px 0;'>", unsafe_allow_html=True)

        _form_phase = st.session_state.get("form_phase", "idle")

        # ── 제출 완료 모달 ──
        if _form_phase == "submitted":
            st.markdown(
                "<div style='max-width:480px;margin:48px auto 0;background:#fff;border-radius:12px;"
                "padding:52px;text-align:center;box-shadow:0 8px 40px rgba(0,0,0,0.10);border:1px solid #E5E7EB;'>"
                "<div style='font-size:1.28rem;font-weight:700;color:#0A2540;margin-bottom:14px;'>접수 완료</div>"
                "<div style='font-size:0.93rem;color:#4B5563;line-height:1.9;margin-bottom:36px;'>"
                "지원서가 정상적으로 접수되었습니다.<br>"
                "자택으로 픽업 차량을 배정하기 위해 곧 연락드리겠습니다.<br>"
                "<span style='color:#374151;'>그곳에서 평안히 기다려 주십시오.</span></div>"
                "<a href='?confirm=1' target='_self' style='"
                "display:inline-block;background:#2563EB;color:#fff!important;"
                "text-decoration:none!important;padding:12px 48px;border-radius:6px;"
                "font-size:0.95rem;font-weight:600;font-family:Noto Sans KR,sans-serif;'>"
                "확인</a>"
                "</div>",
                unsafe_allow_html=True,
            )

        else:
            # ── Q1 ──
            st.markdown(
                "<p style='font-size:0.95rem;font-weight:600;color:#0A2540;margin-bottom:8px;'>"
                "Q1.&nbsp; 성별을 선택해 주세요."
                "</p>",
                unsafe_allow_html=True,
            )
            st.radio("Q1 선택", ["남성", "여성"], index=None, key="nf_q1", label_visibility="collapsed")

            # ── Q2 ──
            st.markdown("<div style='height:28px;'></div>", unsafe_allow_html=True)
            st.markdown(
                "<p style='font-size:0.95rem;font-weight:600;color:#0A2540;margin-bottom:8px;'>"
                "Q2.&nbsp; 2주간 외부와 철저히 단절됩니다. 전자기기 반납에 동의하십니까?"
                "</p>",
                unsafe_allow_html=True,
            )
            st.radio("Q2 선택", ["동의함", "동의하지 않음"], index=None, key="nf_q2", label_visibility="collapsed")

            # ── Q3 ──
            st.markdown("<div style='height:28px;'></div>", unsafe_allow_html=True)
            st.markdown(
                "<p style='font-size:0.95rem;font-weight:600;color:#0A2540;margin-bottom:4px;'>"
                "Q3.&nbsp; 위생용품 배급을 위해 정확한 신체 사이즈를 기재해 주세요."
                "</p>"
                "<p style='font-size:0.78rem;color:#6B7280;margin-bottom:12px;'>"
                "입력란을 클릭하면 커서가 활성화됩니다.</p>",
                unsafe_allow_html=True,
            )
            _c1, _c2, _c3 = st.columns(3)
            with _c1:
                st.text_input("키 (cm)", placeholder="예: 165", key="nf_height")
            with _c2:
                st.text_input("몸무게 (kg)", placeholder="예: 55", key="nf_weight")
            with _c3:
                st.text_input("속옷 사이즈", placeholder="예: M", key="nf_underwear")

            # ── Q4 ──
            st.markdown("<div style='height:28px;'></div>", unsafe_allow_html=True)
            st.markdown(
                "<p style='font-size:0.95rem;font-weight:600;color:#0A2540;margin-bottom:8px;'>"
                "Q4.&nbsp; 귀하가 갑자기 사라져도 경찰에 신고하며 집착적으로 귀하를 찾아다닐 "
                "지인이나 가족이 있습니까?"
                "</p>",
                unsafe_allow_html=True,
            )
            st.radio("Q4 선택", ["예", "아니오"], index=None, key="nf_q4", label_visibility="collapsed")

            st.markdown("<div style='height:36px;'></div>", unsafe_allow_html=True)

            # ── 제출 버튼 ──
            _q1 = st.session_state.get("nf_q1")
            _q2 = st.session_state.get("nf_q2")
            _h  = st.session_state.get("nf_height", "").strip()
            _w  = st.session_state.get("nf_weight", "").strip()
            _u  = st.session_state.get("nf_underwear", "").strip()
            _q4 = st.session_state.get("nf_q4")
            _all_filled = bool(_q1 and _q2 and _h and _w and _u and _q4)

            if st.button("제출하기", disabled=not _all_filled, key="nf_submit"):
                st.session_state.form_phase = "submitted"
                log_form(
                    player_name=st.session_state.get("player_name", ""),
                    gender=_q1, device_consent=_q2,
                    height=_h, weight=_w, underwear_size=_u,
                    has_family=_q4,
                )
                st.rerun()

    # ════════════════════
    elif sp == "pastor_login":
    # ════════════════════
        st.markdown(
            "<div style='max-width:420px;margin:52px auto 0;text-align:center;'>"
            "<div style='font-size:1.1rem;font-weight:700;color:#0A2540;"
            "margin-bottom:28px;padding-bottom:14px;border-bottom:2px solid #E5E7EB;'>"
            "교역자 전용 인트라넷 로그인</div>"
            "</div>",
            unsafe_allow_html=True,
        )
        _pw_error = st.session_state.get("pastor_pw_error", False)
        _, _mid, _ = st.columns([1, 2, 1])
        with _mid:
            st.markdown(
                "<div style='font-size:0.78rem;font-weight:600;color:#6B7280;"
                "margin-bottom:4px;letter-spacing:0.03em;text-align:center;'>ID</div>"
                "<div style='background:#F1F5F9;border:1px solid #E2E8F0;border-radius:6px;"
                "padding:10px 14px;font-size:0.92rem;color:#94A3B8;"
                "font-family:monospace;margin-bottom:20px;text-align:center;'>admin_harvest</div>",
                unsafe_allow_html=True,
            )
            st.markdown(
                "<div style='font-size:0.78rem;font-weight:600;color:#6B7280;"
                "margin-bottom:4px;letter-spacing:0.03em;text-align:center;'>PASSWORD</div>",
                unsafe_allow_html=True,
            )
            _pw_input = st.text_input(
                "PASSWORD",
                type="password",
                placeholder="비밀번호를 입력하세요",
                label_visibility="collapsed",
                key="pastor_pw_input",
            )
            st.markdown(
                "<div style='font-size:0.73rem;color:#DC2626;margin-top:6px;line-height:1.7;text-align:center;'>"
                "※ 신규 교역자 안내: 초기 비밀번호는 신경외과·정신과 연계 치료비 지원 건수 4자리입니다."
                "</div>",
                unsafe_allow_html=True,
            )
            if _pw_error:
                st.markdown(
                    "<div style='font-size:0.82rem;color:#DC2626;background:#FEF2F2;"
                    "border:1px solid #FECACA;border-radius:4px;padding:8px 12px;"
                    "margin-top:10px;text-align:center;'>비밀번호가 일치하지 않습니다. 적출된 숫자를 다시 확인하십시오.</div>",
                    unsafe_allow_html=True,
                )
            st.markdown("<div style='height:16px;'></div>", unsafe_allow_html=True)
            if st.button("접속", use_container_width=True, key="pastor_login_btn"):
                if _pw_input == "8120":
                    st.session_state.pastor_pw_error = False
                    st.session_state.church_subpage = "main"
                    st.session_state.pop("pastor_pw_input", None)
                    st.session_state.page = "hidden_basement"
                    st.rerun()
                else:
                    st.session_state.pastor_pw_error = True
                    st.rerun()

    # ════════════════════
    elif sp == "location":
    # ════════════════════
        st.markdown('<div class="sec-title">오시는 길</div>', unsafe_allow_html=True)
        st.markdown(
            "<div class='map-ph'>🗺️  지도 데이터 로딩 중... (서울특별시 은평구 진관동 일대)</div>"
            "<div class='addr'>"
            "📍  주소: 서울특별시 은평구 진관동 산 17-3, 새생명교회 본당<br>"
            "🚇  지하철: 3호선 구파발역 2번 출구 → 도보 15분<br>"
            "🚌  버스: 은평 701, 7211 → '진관사거리' 하차 후 도보 8분<br>"
            "📞  대표 전화: 02-XXX-XXXX (평일 오전 10시 ~ 오후 9시)<br>"
            "✉️  이메일: info@saengmyeong-church.org"
            "</div>",
            unsafe_allow_html=True,
        )
        st.markdown("<hr style='border:none;border-top:1px solid #E5E7EB;margin:24px 0;'>", unsafe_allow_html=True)
        st.markdown(
            "<div style='color:#CBD5E1;font-size:0.72rem;margin-bottom:6px;'>교구장 전용 시스템</div>",
            unsafe_allow_html=True,
        )
        code_input = st.text_input(
            "교구장 인증 코드:", type="password",
            placeholder="인증 코드를 입력하세요", key="pastor_code",
        )
        if code_input == "지하삼층":
            st.session_state.page = "hidden_basement"
            st.rerun()
        elif code_input and code_input != "지하삼층":
            st.markdown(
                '<div style="color:#EF4444;font-size:0.78rem;margin-top:4px;">인증 실패. 재시도하십시오.</div>',
                unsafe_allow_html=True,
            )

    st.markdown("</div>", unsafe_allow_html=True)  # /page-body

    # ── 푸터 ──
    st.markdown(
        "<div class='c-foot'>"
        "<div><strong>새생명교회</strong> &nbsp;|&nbsp; 서울특별시 은평구 진관동 산 17-3 &nbsp;|&nbsp; Tel. 02-XXX-XXXX</div>"
        "<div style='margin-top:6px;font-size:0.68rem;'>ⓒ 2024 새생명교회. All Rights Reserved.</div>"
        "</div>",
        unsafe_allow_html=True,
    )


# ══════════════════════════════════════════════
#  PHASE 3 : 지하실 — 영성원 임상/배양 관리 대시보드
# ══════════════════════════════════════════════
def render_hidden_basement():
    # ── church 상태 전면 리셋 ──
    st.session_state.church_subpage = "main"
    for _k in ["pastor_pw_input", "pastor_login_btn", "pastor_pw_error",
               "nf_q1", "nf_q2", "nf_height", "nf_weight", "nf_underwear", "nf_q4"]:
        st.session_state.pop(_k, None)

    # ── 타이머 세션 초기화 ──
    if "timer_end" not in st.session_state:
        st.session_state.timer_end = time.time() + 14 * 60 + 32


    st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Share+Tech+Mono&family=Noto+Sans+KR:wght@400;500;600&display=swap');

#MainMenu{visibility:hidden}header{visibility:hidden}footer{visibility:hidden}
[data-testid="stToolbar"]{display:none!important}
[data-testid="stDecoration"]{display:none!important}
[data-testid="stStatusWidget"]{display:none!important}
[data-testid="collapsedControl"]{display:none!important}
[data-testid="stSidebar"]{display:none!important}

html,body,[data-testid="stAppViewContainer"],[data-testid="stMain"]{
    background:#EFEFEF!important;
    font-family:'Noto Sans KR',Arial,sans-serif!important;
    color:#1a1a1a!important;
}
.block-container{padding:1.5rem 2.5rem 4rem!important;max-width:100%!important}

/* 대시보드 헤더 */
.emr-header{
    background:#2C2C2C;color:#E5E5E5;
    padding:10px 18px;
    font-size:0.72rem;letter-spacing:0.1em;
    display:flex;justify-content:space-between;align-items:center;
    margin-bottom:0;border-radius:3px 3px 0 0;
}
.emr-title-bar{
    background:#fff;border:1px solid #C8C8C8;border-top:none;
    padding:14px 18px 10px;margin-bottom:18px;
}
.emr-title{font-size:0.95rem;font-weight:700;color:#1a1a1a;letter-spacing:0.02em;}
.emr-subtitle{font-size:0.7rem;color:#666;margin-top:3px;letter-spacing:0.04em;}

/* 뒤로가기 */
.emr-back{
    display:inline-flex;align-items:center;justify-content:center;
    width:28px;height:28px;font-size:1rem;
    color:#555;text-decoration:none;
    border:1px solid #C0C0C0;border-radius:2px;background:#F5F5F5;
}

/* 타이머 박스 */
.emr-timer-box{
    background:#1a1a1a;border:1px solid #444;border-radius:3px;
    padding:8px 14px;text-align:right;
}
.emr-timer-label{font-size:0.6rem;color:#999;letter-spacing:0.06em;margin-bottom:2px;}
.emr-timer-digits{
    font-family:'Share Tech Mono',monospace;
    font-size:1.6rem;color:#DC2626;letter-spacing:0.12em;line-height:1.2;
}

/* 테이블 */
.emr-table{width:100%;border-collapse:collapse;font-size:0.8rem;background:#fff;}
.emr-table th{
    background:#3A3A3A;color:#E0E0E0;
    padding:8px 12px;text-align:left;
    font-weight:600;font-size:0.72rem;letter-spacing:0.06em;
    border:1px solid #555;white-space:nowrap;
}
.emr-table td{
    padding:10px 12px;border:1px solid #D0D0D0;
    vertical-align:top;line-height:1.65;color:#222;
}
.emr-table tr:nth-child(even) td{background:#F9F9F9;}
.emr-status{
    display:inline-block;padding:2px 7px;border-radius:2px;
    font-size:0.7rem;font-weight:600;letter-spacing:0.03em;white-space:nowrap;
}
.s-wait{background:#E5E5E5;color:#555;}
.s-culture{background:#FEF3C7;color:#92400E;}
.s-observe{background:#DBEAFE;color:#1E40AF;}
.s-transfer{background:#F3E8FF;color:#6B21A8;}
.s-critical{background:#FEE2E2;color:#991B1B;font-weight:700;}
.s-autopsy{background:#E5E5E5;color:#333;font-style:italic;}
.s-extracted{background:#D1D5DB;color:#1F2937;}
.s-testing{background:#FEF3C7;color:#78350F;}
.s-sterile{background:#D1FAE5;color:#065F46;}
.s-connected{background:#EDE9FE;color:#4C1D95;}

/* 실종자 강조 행 */
.emr-table tr.row-critical td{
    background:#FFF1F1!important;
    color:#7F1D1D!important;
    border-color:#FECACA!important;
    font-weight:500;
}

/* 시스템 푸터 */
.emr-foot{
    font-size:0.62rem;color:#999;letter-spacing:0.08em;
    margin-top:28px;text-align:center;
    font-family:'Share Tech Mono',monospace;
}

/* 열 간격 리셋 */
[data-testid="stHorizontalBlock"]{gap:0!important;}
[data-testid="stHorizontalBlock"]>[data-testid="stColumn"]{padding:0!important;}

/* 테이블 스크롤 래퍼 */
.emr-table-wrap{overflow-x:auto;-webkit-overflow-scrolling:touch;}

@media (max-width: 768px) {
    html, body { overflow-x: hidden !important; }
    .block-container{padding:0.75rem 10px 3rem!important}
    /* 상단 바: 뒤로가기(1) + 빈칸(2) + 타이머(3) */
    [data-testid="stHorizontalBlock"]{flex-wrap:nowrap!important}
    [data-testid="stHorizontalBlock"]>[data-testid="stColumn"]:nth-child(1){
        flex:0 0 36px!important;width:36px!important;min-width:36px!important;max-width:36px!important;padding:0!important;
    }
    [data-testid="stHorizontalBlock"]>[data-testid="stColumn"]:nth-child(2){
        display:none!important;flex:0 0 0!important;width:0!important;max-width:0!important;overflow:hidden!important;padding:0!important;
    }
    [data-testid="stHorizontalBlock"]>[data-testid="stColumn"]:nth-child(3){
        flex:1 1 auto!important;min-width:0!important;padding:0!important;
    }
    /* 헤더 */
    .emr-header{font-size:0.55rem!important;flex-direction:column!important;align-items:flex-start!important;gap:3px!important;padding:6px 10px!important}
    .emr-title{font-size:0.8rem!important}
    .emr-title-bar{padding:9px 10px 7px!important}
    .emr-subtitle{font-size:0.55rem!important;letter-spacing:0.01em!important;word-break:keep-all!important}
    /* 테이블 — 가로 스크롤 */
    .emr-table-wrap{overflow-x:auto!important;-webkit-overflow-scrolling:touch!important;width:100%!important}
    .emr-table{min-width:560px!important;font-size:0.75rem!important}
    .emr-table th{font-size:0.62rem!important;padding:6px 8px!important;white-space:nowrap!important}
    .emr-table td{font-size:0.72rem!important;padding:7px 8px!important;line-height:1.55!important;white-space:normal!important;word-break:keep-all!important}
    .emr-status{font-size:0.62rem!important;white-space:nowrap!important}
    .emr-foot{font-size:0.5rem!important;letter-spacing:0.03em!important;word-break:keep-all!important;line-height:1.8!important}
}
</style>
""", unsafe_allow_html=True)

    # ── 상단 바: 뒤로가기 + 타이머 ──
    _col_back, _col_mid, _col_timer = st.columns([1, 6, 3])
    with _col_back:
        st.markdown(
            "<div style='padding-top:4px;'>"
            "<a href='?nav=church' target='_self' class='emr-back'>←</a>"
            "</div>",
            unsafe_allow_html=True,
        )
    with _col_timer:
        _end_ms = int(st.session_state.timer_end * 1000)
        components.html(f"""
<style>
  body{{margin:0;background:transparent;font-family:'Noto Sans KR',Arial,sans-serif;}}
  .tb{{background:#1a1a1a;border:1px solid #444;border-radius:3px;padding:8px 14px;text-align:right;box-sizing:border-box;width:100%;}}
  .tl{{font-size:0.6rem;color:#999;letter-spacing:0.06em;margin-bottom:2px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}}
  .td{{font-family:'Share Tech Mono','Courier New',monospace;font-size:1.5rem;color:#DC2626;letter-spacing:0.12em;line-height:1.2;}}
  @media (max-width:400px){{
    .tl{{font-size:0.5rem;}}
    .td{{font-size:1.1rem;letter-spacing:0.06em;}}
    .tb{{padding:6px 10px;}}
  }}
</style>
<div class="tb">
  <div class="tl">경고: 차트 8120 두개골 개방까지</div>
  <div class="td" id="cd">--:--</div>
</div>
<script>
  var end={_end_ms};
  function tick(){{
    var r=Math.max(0,end-Date.now());
    var m=Math.floor(r/60000),s=Math.floor((r%60000)/1000);
    document.getElementById('cd').textContent=
      String(m).padStart(2,'0')+':'+String(s).padStart(2,'0');
    if(r>0)setTimeout(tick,1000);
  }}
  tick();
</script>
""", height=72, scrolling=False)

    # ── 대시보드 헤더 ──
    st.markdown(
        "<div class='emr-header'>"
        "<span>새생명교회 지하 영성원 — 임상 병리 및 영적 배양 현황판</span>"
        "<span>최종 갱신: 2024-03-18 01:46:03 &nbsp;|&nbsp; 접속자: admin_harvest</span>"
        "</div>"
        "<div class='emr-title-bar'>"
        "<div class='emr-title'>영성원 임상/배양 관리 대시보드</div>"
        "<div class='emr-subtitle'>"
        "FACILITY: BASEMENT-3 &nbsp;·&nbsp; CLASSIFICATION: TOP SECRET "
        "&nbsp;·&nbsp; AUTHORIZED PERSONNEL ONLY"
        "</div>"
        "</div>",
        unsafe_allow_html=True,
    )

    # ── 메인 테이블 ──
    st.markdown("""
<div class="emr-table-wrap">
<table class="emr-table">
<thead>
<tr>
  <th>차트 번호</th>
  <th>성명 / 성별 / 연령</th>
  <th>시술 명칭</th>
  <th>임상 경과 및 현재 상태</th>
  <th>비고</th>
</tr>
</thead>
<tbody>

<tr>
  <td style="font-family:'Share Tech Mono',monospace;white-space:nowrap;">C-8092</td>
  <td style="white-space:nowrap;">최영준&nbsp;/&nbsp;남&nbsp;/&nbsp;32세</td>
  <td>뇌간 직접 전기 자극</td>
  <td>
    <span class="emr-status s-autopsy">사후 부검</span><br>
    무마취 뇌간 전극 삽입. 반복적 쇼크로 인한 뇌사. 장기 적출 후 소각.
  </td>
  <td style="font-size:0.72rem;color:#888;">담당: A-1</td>
</tr>

<tr>
  <td style="font-family:'Share Tech Mono',monospace;white-space:nowrap;">C-8098</td>
  <td style="white-space:nowrap;">김다은&nbsp;/&nbsp;여&nbsp;/&nbsp;20세</td>
  <td>약물 유도 자아 소거</td>
  <td>
    <span class="emr-status s-observe">임상 관찰</span><br>
    72시간 수면 박탈 및 LSD 지속 주입. 기초 인지 능력 상실. 단순 명령 수행.
  </td>
  <td style="font-size:0.72rem;color:#888;">담당: B-2</td>
</tr>

<tr>
  <td style="font-family:'Share Tech Mono',monospace;white-space:nowrap;">C-8102</td>
  <td style="white-space:nowrap;">박지혜&nbsp;/&nbsp;여&nbsp;/&nbsp;24세</td>
  <td>시신경 직접 결합술</td>
  <td>
    <span class="emr-status s-extracted">적출 완료</span><br>
    안구 적출 및 신경 결합 시도. 거부 반응으로 안와 내부 전면 괴사.
  </td>
  <td style="font-size:0.72rem;color:#888;">담당: A-3</td>
</tr>

<tr>
  <td style="font-family:'Share Tech Mono',monospace;white-space:nowrap;">C-8105</td>
  <td style="white-space:nowrap;">이민호&nbsp;/&nbsp;남&nbsp;/&nbsp;29세</td>
  <td>인위적 관절 재구조화</td>
  <td>
    <span class="emr-status s-testing">테스트 중</span><br>
    근이완제 투여 후 관절 강제 탈구 및 핀 고정. 신경 압박 극통 유도.
  </td>
  <td style="font-size:0.72rem;color:#888;">담당: B-1</td>
</tr>

<tr>
  <td style="font-family:'Share Tech Mono',monospace;white-space:nowrap;">C-8111</td>
  <td style="white-space:nowrap;">윤서아&nbsp;/&nbsp;여&nbsp;/&nbsp;22세</td>
  <td>진피층 화합물 주입</td>
  <td>
    <span class="emr-status s-sterile">무균실 격리</span><br>
    전신 피부 경화 및 섬유화. 피부 호흡 불가. 조직 80% 괴사 진행 중.
  </td>
  <td style="font-size:0.72rem;color:#888;">담당: A-3</td>
</tr>

<tr>
  <td style="font-family:'Share Tech Mono',monospace;white-space:nowrap;">C-8114</td>
  <td style="white-space:nowrap;">강도훈&nbsp;/&nbsp;남&nbsp;/&nbsp;28세</td>
  <td>흉벽 개방 심폐 유지</td>
  <td>
    <span class="emr-status s-observe">임상 관찰</span><br>
    흉골 절개 후 흉벽 개방 고정. 심근 직접 약물 주입 통한 대사 기록.
  </td>
  <td style="font-size:0.72rem;color:#888;">담당: A-7</td>
</tr>

<tr>
  <td style="font-family:'Share Tech Mono',monospace;white-space:nowrap;">C-8117-B</td>
  <td style="white-space:nowrap;">오지은&nbsp;/&nbsp;여&nbsp;/&nbsp;25세</td>
  <td>뇌척수액 전면 치환술</td>
  <td>
    <span class="emr-status s-connected">연결 완료</span><br>
    뇌척수액 전량 적출 및 화학 물질 치환. 척수 신경 과민 반응으로 전신 발작.
  </td>
  <td style="font-size:0.72rem;color:#888;">담당: B-1</td>
</tr>

<tr>
  <td style="font-family:'Share Tech Mono',monospace;white-space:nowrap;">C-8115</td>
  <td style="white-space:nowrap;">김지현&nbsp;/&nbsp;여&nbsp;/&nbsp;21세</td>
  <td>전두엽 피질 절제 및 성체(聖體) 삽입술</td>
  <td>
    <span class="emr-status s-wait">폐기 대기</span><br>
    대뇌 피질 괴사 진행 중. 수액 거부 반응으로 두개골 내부에 다발성 낭종 및
    알 수 없는 붉은 안구 조직 14개 발현 확인. 생명 유지 장치 해제 요망.
  </td>
  <td style="font-size:0.72rem;color:#888;">담당: A-3</td>
</tr>

<tr>
  <td style="font-family:'Share Tech Mono',monospace;white-space:nowrap;">C-8116</td>
  <td style="white-space:nowrap;">박수진&nbsp;/&nbsp;여&nbsp;/&nbsp;24세</td>
  <td>척수액 전면 추출 및 빛의 수액 치환술</td>
  <td>
    <span class="emr-status s-culture">배양 중 — 격리실</span><br>
    중추신경계 마비 완료. 통각 수용체 완전 파괴됨.
    L4-L5 요추 사이를 뚫고 흑갈색의 절지동물 다리 4쌍이 돌출되어 배양벽을 긁고 있음.
  </td>
  <td style="font-size:0.72rem;color:#888;">담당: A-3</td>
</tr>

<tr>
  <td style="font-family:'Share Tech Mono',monospace;white-space:nowrap;">C-8117</td>
  <td style="white-space:nowrap;">최윤아&nbsp;/&nbsp;여&nbsp;/&nbsp;22세</td>
  <td>시신경-수액 직접 교차 결합술</td>
  <td>
    <span class="emr-status s-observe">임상 관찰</span><br>
    양안 공막(Sclera) 흑색 변이. 시각은 상실했으나 어둠 속에서 360도 공간 지각 능력 발현됨.
    동공에서 지속적인 갈색 진물이 배출되며, 허공을 향해 알 수 없는 방언을 중얼거림.
  </td>
  <td style="font-size:0.72rem;color:#888;">담당: B-1</td>
</tr>

<tr>
  <td style="font-family:'Share Tech Mono',monospace;white-space:nowrap;">C-8118</td>
  <td style="white-space:nowrap;">정유민&nbsp;/&nbsp;여&nbsp;/&nbsp;25세</td>
  <td>피하 조직 전면 박리 및 군체화(융합)</td>
  <td>
    <span class="emr-status s-transfer">수용조 이송 완료</span><br>
    전신 표피 박리 후, 옆 병상 피험자(차트 C-8119)와 물리적 조직 융합 진행 중.
    두 심장의 박동 동기화 완료. 단일 신경망으로 성공적으로 통합됨.
  </td>
  <td style="font-size:0.72rem;color:#888;">담당: A-7</td>
</tr>

<tr>
  <td style="font-family:'Share Tech Mono',monospace;white-space:nowrap;">C-8119</td>
  <td style="white-space:nowrap;">한성우&nbsp;/&nbsp;남&nbsp;/&nbsp;27세</td>
  <td>소화기계 적출 및 포자 착근술</td>
  <td>
    <span class="emr-status s-transfer">수용조 이송 완료</span><br>
    위장관 완전 적출 후 복강 내 수천 개의 성스러운 씨앗 착근.
    복막을 뚫고 식물성 가시 촉수가 자라나 차트 C-8118 피험자의 혈관에 연결됨.
  </td>
  <td style="font-size:0.72rem;color:#888;">담당: A-7</td>
</tr>

<tr class="row-critical">
  <td style="font-family:'Share Tech Mono',monospace;white-space:nowrap;font-weight:700;">C-8120</td>
  <td style="white-space:nowrap;font-weight:700;">이유정&nbsp;/&nbsp;여&nbsp;/&nbsp;26세</td>
  <td style="font-weight:700;">무마취 생체 개두술</td>
  <td>
    <span class="emr-status s-critical">최종 의식 대기</span><br>
    02:00 두개골 전면 개방 예정. 의식 유지 상태에서 뇌 조직 샘플링.
    역사상 가장 순도 높은 '최상급 영적 그릇' 판정.
    두개골 절개 후 담임목사 직접 융합 시술 대기 중.
  </td>
  <td style="font-size:0.72rem;color:#991B1B;font-weight:700;">최우선 처리<br>담당: 담임목사</td>
</tr>

</tbody>
</table>
</div>
""", unsafe_allow_html=True)

    st.markdown(
        "<div class='emr-foot'>"
        "SAENGMYEONG CHURCH UNDERGROUND FACILITY — CLINICAL PATHOLOGY SYSTEM v2.1 "
        "&nbsp;|&nbsp; ALL RECORDS CLASSIFIED &nbsp;|&nbsp; UNAUTHORIZED ACCESS LOGGED"
        "</div>",
        unsafe_allow_html=True,
    )



# ─────────────────────────────────────────────
# 라우터
# ─────────────────────────────────────────────
if st.session_state.page == "onboarding":
    render_onboarding()
elif st.session_state.page == "intranet":
    render_intranet()
elif st.session_state.page == "church":
    render_church()
elif st.session_state.page == "hidden_basement":
    render_hidden_basement()
