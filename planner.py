import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
from collections import defaultdict
from supabase import create_client, Client
import extra_streamlit_components as stx  # ✨ 쿠키 관리를 위한 라이브러리 추가

# 1. 페이지 설정
st.set_page_config(page_title="스마트 진도표", layout="wide")

# ✨ 쿠키 매니저 실행 (브라우저 쿠키를 읽고 쓰는 역할)
cookie_manager = stx.CookieManager()


# --- [Supabase 연결] ---
@st.cache_resource
def init_connection():
    url = st.secrets["supabase"]["url"]
    key = st.secrets["supabase"]["key"]
    return create_client(url, key)


supabase = init_connection()


# --- [DB 연동 함수들] ---
def load_all_user_data(user_id):
    res_settings = supabase.table("user_settings").select("*").eq("id", user_id).execute()
    if res_settings.data:
        data = res_settings.data[0]
        loaded_df = pd.DataFrame(data['timetable'])
        loaded_df.index = loaded_df.index.astype(int)
        cols = ["월", "화", "수", "목", "금"]
        for c in cols:
            if c not in loaded_df.columns:
                loaded_df[c] = ""
        st.session_state.timetable = loaded_df[cols]
        st.session_state.start_date = datetime.strptime(data['start_date'], "%Y-%m-%d").date()
        st.session_state.end_date = datetime.strptime(data['end_date'], "%Y-%m-%d").date()

    res_plans = supabase.table("lesson_plans").select("*").eq("user_id", user_id).execute()
    if res_plans.data:
        for row in res_plans.data:
            st.session_state.lesson_plans_dict[row['grade']] = pd.DataFrame(row['plan_data'])

    res_data = supabase.table("user_data").select("*").eq("user_id", user_id).execute()
    if res_data.data:
        d = res_data.data[0]
        st.session_state.custom_overrides = d.get('overrides', {})
        st.session_state.events = pd.DataFrame(d.get('events', []))
        st.session_state.cancels = pd.DataFrame(d.get('cancels', []))


def save_settings():
    user_id = st.session_state.user.id
    payload = {
        "id": user_id,
        "timetable": st.session_state.timetable.to_dict(),
        "start_date": st.session_state.start_date.strftime("%Y-%m-%d"),
        "end_date": st.session_state.end_date.strftime("%Y-%m-%d")
    }
    supabase.table("user_settings").upsert(payload).execute()


def save_lesson_plan(grade):
    user_id = st.session_state.user.id
    payload = {
        "user_id": user_id,
        "grade": grade,
        "plan_data": st.session_state.lesson_plans_dict[grade].to_dict()
    }
    supabase.table("lesson_plans").upsert(payload, on_conflict="user_id,grade").execute()


def save_custom_data():
    user_id = st.session_state.user.id
    payload = {
        "user_id": user_id,
        "overrides": st.session_state.custom_overrides,
        "events": st.session_state.events.to_dict(),
        "cancels": st.session_state.cancels.to_dict()
    }
    supabase.table("user_data").upsert(payload).execute()


# --- [로그인/회원가입 UI] ---
if 'user' not in st.session_state:
    st.title("🔒 스마트 진도표 시스템")

    # ✨ 1. 쿠키에서 토큰을 찾아 자동 로그인 시도
    access_token = cookie_manager.get(cookie="sb_access_token")
    refresh_token = cookie_manager.get(cookie="sb_refresh_token")

    if access_token and refresh_token:
        try:
            # 토큰이 유효하다면 세션을 복구하여 자동 로그인 통과
            response = supabase.auth.set_session(access_token, refresh_token)
            st.session_state.user = response.user

            if 'timetable' not in st.session_state:
                st.session_state.timetable = pd.DataFrame("", index=range(1, 10), columns=["월", "화", "수", "목", "금"])
                st.session_state.lesson_plans_dict = {
                    g: pd.DataFrame({"차시": range(1, 101), "진도 내용": [f"{g} {i}차시 내용" for i in range(1, 101)]}) for g
                    in ["1학년", "2학년", "3학년"]}
                st.session_state.events = pd.DataFrame(columns=["날짜", "행사명"])
                st.session_state.cancels = pd.DataFrame(columns=["날짜", "교시", "사유"])
                st.session_state.custom_overrides = {}
                st.session_state.start_date = datetime(2026, 3, 2).date()
                st.session_state.end_date = datetime(2026, 7, 17).date()

            load_all_user_data(st.session_state.user.id)
            st.rerun()
        except Exception:
            # 토큰이 만료되었거나 오류가 나면 조용히 무시 (다시 로그인 창 표시)
            pass

    # ✨ 2. 로그인 화면 (쿠키에 토큰이 없거나 실패했을 때만 보임)
    tab1, tab2 = st.tabs(["로그인", "회원가입"])
    with tab1:
        log_email = st.text_input("이메일", key="log_email")
        log_pw = st.text_input("비밀번호", type="password", key="log_pw")
        # 자동 로그인 선택 체크박스
        auto_login = st.checkbox("자동 로그인 유지 (30일)", value=True)

        if st.button("로그인", type="primary", use_container_width=True):
            try:
                response = supabase.auth.sign_in_with_password({"email": log_email, "password": log_pw})
                st.session_state.user = response.user

                # ✨ 로그인 성공 시: 자동 로그인이 체크되어 있다면 쿠키에 토큰 발급
                if auto_login:
                    expire_date = datetime.now() + timedelta(days=30)
                    cookie_manager.set("sb_access_token", response.session.access_token, expires_at=expire_date)
                    cookie_manager.set("sb_refresh_token", response.session.refresh_token, expires_at=expire_date)

                if 'timetable' not in st.session_state:
                    st.session_state.timetable = pd.DataFrame("", index=range(1, 10), columns=["월", "화", "수", "목", "금"])
                    st.session_state.lesson_plans_dict = {
                        g: pd.DataFrame({"차시": range(1, 101), "진도 내용": [f"{g} {i}차시 내용" for i in range(1, 101)]}) for g
                        in ["1학년", "2학년", "3학년"]}
                    st.session_state.events = pd.DataFrame(columns=["날짜", "행사명"])
                    st.session_state.cancels = pd.DataFrame(columns=["날짜", "교시", "사유"])
                    st.session_state.custom_overrides = {}
                    st.session_state.start_date = datetime(2026, 3, 2).date()
                    st.session_state.end_date = datetime(2026, 7, 17).date()
                load_all_user_data(st.session_state.user.id)
                st.rerun()
            except Exception as e:
                st.error(f"로그인 실패: {e}")

    with tab2:
        reg_email = st.text_input("가입용 이메일", key="reg_email")
        reg_pw = st.text_input("비밀번호(6자 이상)", type="password", key="reg_pw")
        if st.button("회원가입", use_container_width=True):
            try:
                supabase.auth.sign_up({"email": reg_email, "password": reg_pw})
                st.success("가입 완료! 로그인해 주세요.")
            except Exception as e:
                st.error(f"가입 실패 원인: {e}")
    st.stop()

# --- [메인 화면 UI] ---

# 🚨 [종합 안전장치] 메모리에 데이터가 날아가 있으면 무조건 기본 뼈대를 만들어줌
if 'start_date' not in st.session_state:
    st.session_state.start_date = datetime(2026, 3, 2).date()
    st.session_state.end_date = datetime(2026, 7, 17).date()
if 'timetable' not in st.session_state:
    st.session_state.timetable = pd.DataFrame("", index=range(1, 10), columns=["월", "화", "수", "목", "금"])
if 'lesson_plans_dict' not in st.session_state:
    st.session_state.lesson_plans_dict = {
        g: pd.DataFrame({"차시": range(1, 101), "진도 내용": [f"{g} {i}차시 내용" for i in range(1, 101)]}) for g
        in ["1학년", "2학년", "3학년"]}
if 'events' not in st.session_state:
    st.session_state.events = pd.DataFrame(columns=["날짜", "행사명"])
if 'cancels' not in st.session_state:
    st.session_state.cancels = pd.DataFrame(columns=["날짜", "교시", "사유"])
if 'custom_overrides' not in st.session_state:
    st.session_state.custom_overrides = {}

col_logo, col_user = st.columns([8, 2])
with col_logo: st.title("📅 교사용 학년별 스마트 진도 관리")
with col_user:
    st.write(f"👤 **{st.session_state.user.email.split('@')[0]}** 님")
    # 🚨 [추가할 코드] 현재 로그인된 test 님의 진짜 고유번호를 화면에 출력
    st.code(st.session_state.user.id)
    if st.button("로그아웃"):
        # ✨ 로그아웃 처리 시 발급했던 쿠키(증명서)도 완벽하게 폐기
        supabase.auth.sign_out()
        cookie_manager.delete("sb_access_token")
        cookie_manager.delete("sb_refresh_token")
        del st.session_state.user
        st.rerun()

st.divider()

# --- [CSS 스타일 수정: 너비 일치 및 색상 복구] ---
st.markdown("""
<style>
    /* 수정/편집 모드일 때 보여지는 카드 스타일 */
    .slot-card { padding: 10px; border-radius: 4px; margin-bottom: 5px; min-height: 90px; line-height: 1.4; border: 1px solid #ddd; width: 100%; }
    .grade1 { background-color: #fef0d9; border-top: 4px solid #fdcc8a; }
    .grade2 { background-color: #e5f5e0; border-top: 4px solid #a1d99b; }
    .grade3 { background-color: #eff3ff; border-top: 4px solid #9ecae1; }
    .overridden { border-left: 3px solid #ff1493 !important; }
    .empty-slot { min-height: 120px; }

    /* 버튼(진도 카드) 공통 스타일 (너비 100% 맞춤) */
    div.element-container:has(span.edit-anchor) + div.element-container button {
        width: 100% !important;
        height: auto !important;
        min-height: 90px !important;
        display: block !important;
        padding: 10px !important;
        border-radius: 4px !important;
        border: 1px solid #ddd !important;
        box-shadow: 1px 1px 3px rgba(0,0,0,0.05) !important;
        color: #333 !important;
        text-align: left !important;
        margin-bottom: 4px !important;
        transition: transform 0.1s ease-in-out !important;
    }
    div.element-container:has(span.edit-anchor) + div.element-container button:hover { transform: scale(1.02); border-color: #999 !important; }
    div.element-container:has(span.edit-anchor) + div.element-container button p { margin: 0 !important; text-align: left !important; font-size: 0.9em !important; }

    /* 학년별 버튼 배경색 복구 (필수!) */
    div.element-container:has(span.grade-1) + div.element-container button { background-color: #fef0d9 !important; border-top: 4px solid #fdcc8a !important; }
    div.element-container:has(span.grade-2) + div.element-container button { background-color: #e5f5e0 !important; border-top: 4px solid #a1d99b !important; }
    div.element-container:has(span.grade-3) + div.element-container button { background-color: #eff3ff !important; border-top: 4px solid #9ecae1 !important; }
    div.element-container:has(span.overridden-true) + div.element-container button { border-left: 3px solid #ff1493 !important; }

    /* 메모 입력창들이 포함된 컬럼간 간격 최소화 */
    [data-testid="column"] {
        gap: 0.5rem !important;
    }
</style>
""", unsafe_allow_html=True)

col_left, col_right = st.columns([7, 3])

with col_right:
    st.subheader("⚙️ 설정 및 저장")
    if st.button("💾 전체 설정 DB 저장", type="primary", use_container_width=True):
        save_settings()
        for g in ["1학년", "2학년", "3학년"]: save_lesson_plan(g)
        save_custom_data()
        st.success("데이터베이스에 저장되었습니다!")

    with st.expander("📅 학기 및 시간표", expanded=False):
        c1, c2 = st.columns(2)
        st.session_state.start_date = c1.date_input("시작일", st.session_state.start_date)
        st.session_state.end_date = c2.date_input("종료일", st.session_state.end_date)
        st.session_state.timetable = st.data_editor(st.session_state.timetable, use_container_width=True)

    with st.expander("📚 학년별 진도 계획", expanded=True):
        tabs = st.tabs(["1학년", "2학년", "3학년"])
        for i, g in enumerate(["1학년", "2학년", "3학년"]):
            with tabs[i]:
                st.session_state.lesson_plans_dict[g] = st.data_editor(st.session_state.lesson_plans_dict[g],
                                                                       num_rows="dynamic", use_container_width=True,
                                                                       key=f"p_{g}")

    with st.expander("🚨 일정 변경 (행사/결강)", expanded=True):
        st.write("**[전일 행사]**")
        st.session_state.events = st.data_editor(st.session_state.events, num_rows="dynamic", use_container_width=True,
                                                 key="ev")
        st.write("**[특정 교시 결강]**")
        st.session_state.cancels = st.data_editor(st.session_state.cancels, num_rows="dynamic",
                                                  use_container_width=True, key="ca")


def get_class_start_indices(start_dt, target_dt, timetable, events, cancels):
    class_indices = defaultdict(int)
    curr = start_dt
    while curr < target_dt:
        if curr.weekday() < 5:
            curr_str = curr.strftime("%Y-%m-%d")
            day_name = ["월", "화", "수", "목", "금"][curr.weekday()]
            if curr_str not in [str(d) for d in events["날짜"].values]:
                for p in range(1, 10):
                    class_info = str(timetable.loc[p, day_name]).strip()
                    if class_info:
                        is_cancelled = not cancels[
                            (cancels["날짜"].astype(str) == curr_str) & (cancels["교시"].astype(str) == str(p))].empty
                        if not is_cancelled:
                            class_indices[class_info] += 1
        curr += timedelta(days=1)
    return class_indices


with col_left:
    def get_all_weeks(start, end):
        weeks = []
        curr = start - timedelta(days=start.weekday())
        week_num = 1
        while curr <= end:
            week_end = curr + timedelta(days=4)
            weeks.append(
                {"label": f"{week_num}주차 ({curr.strftime('%m/%d')}~{week_end.strftime('%m/%d')})", "start": curr})
            curr += timedelta(days=7)
            week_num += 1
        return weeks


    all_weeks = get_all_weeks(st.session_state.start_date, st.session_state.end_date)
    selected_week_data = st.selectbox("주차 선택", all_weeks, format_func=lambda x: x['label'])

    current_class_indices = get_class_start_indices(st.session_state.start_date, selected_week_data['start'],
                                                    st.session_state.timetable, st.session_state.events,
                                                    st.session_state.cancels)

    week_start = selected_week_data['start']
    current_week_dates = [(week_start + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(5)]
    days = ["월", "화", "수", "목", "금"]

    weekly_content_map = {}
    for i, day in enumerate(days):
        curr_date = current_week_dates[i]
        if curr_date in [str(d) for d in st.session_state.events["날짜"].values]: continue
        for p in range(1, 10):
            class_info = str(st.session_state.timetable.loc[p, day]).strip()
            if class_info:
                cancel_match = st.session_state.cancels[(st.session_state.cancels["날짜"].astype(str) == curr_date) & (
                        st.session_state.cancels["교시"].astype(str) == str(p))]
                if cancel_match.empty:
                    grade_key = f"{class_info[0]}학년" if class_info[0] in ['1', '2', '3'] else "1학년"
                    plans = st.session_state.lesson_plans_dict[grade_key]["진도 내용"].tolist()
                    idx = current_class_indices[class_info]
                    weekly_content_map[(curr_date, p)] = plans[idx] if idx < len(plans) else "진도 계획 없음"
                    current_class_indices[class_info] += 1

    h_cols = st.columns([0.6, 2, 2, 2, 2, 2])
    for i, day in enumerate(days):
        date_str = datetime.strptime(current_week_dates[i], "%Y-%m-%d").strftime("%m/%d")
        h_cols[i + 1].markdown(f"<div style='text-align:center; font-weight:bold;'>{day} ({date_str})</div>",
                               unsafe_allow_html=True)
    st.divider()

    for period in range(1, 10):
        if not any(str(st.session_state.timetable.loc[period, d]).strip() != "" for d in days): continue
        r_cols = st.columns([0.6, 2, 2, 2, 2, 2])
        r_cols[0].markdown(f"<div style='text-align:center; font-weight:bold; margin-top: 35px;'>{period}</div>",
                           unsafe_allow_html=True)

        for i, day in enumerate(days):
            curr_date = current_week_dates[i]
            class_info = str(st.session_state.timetable.loc[period, day]).strip()
            with r_cols[i + 1]:
                if curr_date in [str(d) for d in st.session_state.events["날짜"].values]:
                    if period == 1:
                        ev_name = \
                            st.session_state.events[st.session_state.events["날짜"].astype(str) == curr_date][
                                "행사명"].values[0]
                        st.markdown(
                            f"<div style='color:red; font-weight:bold; text-align:center; margin-top:30px;'>🚩 {ev_name}</div>",
                            unsafe_allow_html=True)
                    continue

                if class_info:
                    cancel_match = st.session_state.cancels[
                        (st.session_state.cancels["날짜"].astype(str) == curr_date) & (
                                st.session_state.cancels["교시"].astype(str) == str(period))]
                    override_key = f"{curr_date}_{period}"
                    is_editing = st.session_state.get(f"edit_{override_key}", False)
                    grade_num = class_info[0] if class_info[0] in ['1', '2', '3'] else '1'

                    if not cancel_match.empty:
                        display_content = f"⚠️ {cancel_match.iloc[0]['사유']}"
                        st.markdown(f"<span class='edit-anchor grade-{grade_num}'></span>", unsafe_allow_html=True)
                        st.button(f"**{class_info}반**\n\n{display_content}", key=f"btn_{override_key}", disabled=True,
                                  use_container_width=True)
                    else:
                        default_content = weekly_content_map.get((curr_date, period), "진도 계획 없음")
                        display_content = st.session_state.custom_overrides.get(override_key, default_content)

                        if is_editing:
                            st.markdown(
                                f"<div class='slot-card grade{grade_num} {'overridden' if override_key in st.session_state.custom_overrides else ''}'><div style='font-weight:bold;'>{class_info}반</div></div>",
                                unsafe_allow_html=True)
                            new_val = st.text_input("수정", value=display_content, key=f"in_{override_key}",
                                                    label_visibility="collapsed")
                            c1, c2, c3 = st.columns(3)
                            if c1.button("저장", key=f"sv_{override_key}", use_container_width=True):
                                st.session_state.custom_overrides[override_key] = new_val
                                st.session_state[f"edit_{override_key}"] = False
                                save_custom_data()
                                st.rerun()
                            if c2.button("취소", key=f"cc_{override_key}", use_container_width=True):
                                st.session_state[f"edit_{override_key}"] = False
                                st.rerun()
                            if c3.button("복구", key=f"rs_{override_key}", use_container_width=True):
                                st.session_state.custom_overrides.pop(override_key, None)
                                save_custom_data()
                                st.session_state[f"edit_{override_key}"] = False
                                st.rerun()
                        else:
                            st.markdown(
                                f"<span class='edit-anchor grade-{grade_num} {'overridden-true' if override_key in st.session_state.custom_overrides else ''}'></span>",
                                unsafe_allow_html=True)
                            if st.button(f"**{class_info}반**\n\n{display_content} ✏️", key=f"btn_{override_key}",
                                         use_container_width=True):
                                st.session_state[f"edit_{override_key}"] = True
                                st.rerun()

                    # 메모 및 상태 선택 영역
                    m_c1, m_c2 = st.columns([1, 2.5])
                    m_c1.selectbox("st", ["O", "△", "X"], key=f"s_{override_key}", label_visibility="collapsed")
                    m_c2.text_input("m", key=f"m_{override_key}", placeholder="메모", label_visibility="collapsed")
                else:
                    st.markdown("<div class='empty-slot'></div>", unsafe_allow_html=True)