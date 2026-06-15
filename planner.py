import copy
import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
from collections import defaultdict
from supabase import create_client

# 1. 페이지 설정
st.set_page_config(page_title="스마트 진도표", layout="wide")


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
        if 'start_date' in data and data['start_date']:
            st.session_state.start_date = datetime.strptime(data['start_date'], "%Y-%m-%d").date()
        if 'end_date' in data and data['end_date']:
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
        st.session_state.status_data = d.get('status_data', {})
        st.session_state.memo_data = d.get('memo_data', {})
def create_backup():
    st.session_state.backup = {
        "custom_overrides": copy.deepcopy(st.session_state.custom_overrides),
        "cancels": st.session_state.cancels.copy(deep=True),
        "status_data": copy.deepcopy(st.session_state.status_data),
        "memo_data": copy.deepcopy(st.session_state.memo_data)
    }
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
        "cancels": st.session_state.cancels.to_dict(),
        "status_data": st.session_state.status_data,
        "memo_data": st.session_state.memo_data
    }
    try:
        supabase.table("user_data").upsert(payload, on_conflict="user_id").execute()
    except Exception as e:
        st.error(f"🚨 DB 저장 실패: {e}")


# --- [로그인/회원가입 UI] ---
if 'user' not in st.session_state:
    st.title("🔒 스마트 진도표 시스템")
    tab1, tab2 = st.tabs(["로그인", "회원가입"])
    with tab1:
        log_email = st.text_input("이메일", key="log_email")
        log_pw = st.text_input("비밀번호", type="password", key="log_pw")
        if st.button("로그인", type="primary", use_container_width=True):
            try:
                response = supabase.auth.sign_in_with_password({"email": log_email, "password": log_pw})
                st.session_state.user = response.user

                # 로그인 직후 빈 데이터 뼈대 생성
                st.session_state.timetable = pd.DataFrame("", index=range(1, 10), columns=["월", "화", "수", "목", "금"])
                st.session_state.lesson_plans_dict = {
                    g: pd.DataFrame({"차시": range(1, 101), "진도 내용": [f"{g} {i}차시 내용" for i in range(1, 101)]}) for g
                    in ["1학년", "2학년", "3학년"]}
                st.session_state.events = pd.DataFrame(columns=["날짜", "행사명"])
                st.session_state.cancels = pd.DataFrame(columns=["날짜", "교시", "사유"])
                st.session_state.custom_overrides = {}
                st.session_state.start_date = datetime(2026, 3, 2).date()
                st.session_state.end_date = datetime(2026, 7, 17).date()

                # 생성된 뼈대 위에 DB 데이터 덮어쓰기 시도
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

# 🚨 [안전장치] 혹시 모를 에러 방지를 위해 기본 뼈대 유지 여부 확인
if 'start_date' not in st.session_state: st.session_state.start_date = datetime(2026, 3, 2).date()
if 'end_date' not in st.session_state: st.session_state.end_date = datetime(2026, 7, 17).date()
if 'timetable' not in st.session_state: st.session_state.timetable = pd.DataFrame("", index=range(1, 10),
                                                                                  columns=["월", "화", "수", "목", "금"])
if 'lesson_plans_dict' not in st.session_state: st.session_state.lesson_plans_dict = {
    g: pd.DataFrame({"차시": range(1, 101), "진도 내용": [f"{g} {i}차시 내용" for i in range(1, 101)]}) for g in
    ["1학년", "2학년", "3학년"]}
if 'events' not in st.session_state: st.session_state.events = pd.DataFrame(columns=["날짜", "행사명"])
if 'cancels' not in st.session_state: st.session_state.cancels = pd.DataFrame(columns=["날짜", "교시", "사유"])
if 'custom_overrides' not in st.session_state: st.session_state.custom_overrides = {}
if 'status_data' not in st.session_state: st.session_state.status_data = {}
if 'memo_data' not in st.session_state: st.session_state.memo_data = {}

# 👇 위젯 상태 변경 시 실행될 콜백 함수 (UI 렌더링 전 상단에 배치)
def update_status(k):
    st.session_state.status_data[k] = st.session_state[f"s_{k}"]

def update_memo(k):
    st.session_state.memo_data[k] = st.session_state[f"m_{k}"]

# --- [메인 화면 UI] ---
col_logo, col_user = st.columns([8, 2])
with col_logo: st.title("📅 교사용 학년별 스마트 진도 관리")
with col_user:
    st.write(f"👤 **{st.session_state.user.email.split('@')[0]}** 님")
    if st.button("로그아웃"):
        supabase.auth.sign_out()
        del st.session_state.user
        st.rerun()

st.divider()

st.markdown("""
<style>
    .slot-card { padding: 10px; border-radius: 4px; margin-bottom: 5px; min-height: 90px; line-height: 1.4; border: 1px solid #ddd; width: 100%; }
    .grade1 { background-color: #fef0d9; border-top: 4px solid #fdcc8a; }
    .grade2 { background-color: #e5f5e0; border-top: 4px solid #a1d99b; }
    .grade3 { background-color: #eff3ff; border-top: 4px solid #9ecae1; }
    .overridden { border-left: 3px solid #ff1493 !important; }
    .empty-slot { min-height: 120px; }

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

    div.element-container:has(span.grade-1) + div.element-container button { background-color: #fef0d9 !important; border-top: 4px solid #fdcc8a !important; }
    div.element-container:has(span.grade-2) + div.element-container button { background-color: #e5f5e0 !important; border-top: 4px solid #a1d99b !important; }
    div.element-container:has(span.grade-3) + div.element-container button { background-color: #eff3ff !important; border-top: 4px solid #9ecae1 !important; }
    div.element-container:has(span.overridden-true) + div.element-container button { border-left: 3px solid #ff1493 !important; div.element-container:has(span.disabled-slot) + div.element-container button { 
        background-color: #f8f9fa !important;
        border: 1px solid #e9ecef !important;
        border-top: none !important;
        color: #adb5bd !important;
        box-shadow: none !important;}

    [data-testid="column"] { gap: 0.5rem !important; }
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

    # ---------------------------------------------------------
    # 👇 여기서부터 화면에 시간표를 그려주는 메인 반복문 시작
    # ---------------------------------------------------------
    for period in range(1, 10):
        # 1. 빈 줄(교시)인지 체크: 기본 시간표에 있거나, '이동'해온 데이터가 있으면 그 줄을 표시
        has_class_in_row = False
        for i, d in enumerate(days):
            if str(st.session_state.timetable.loc[period, d]).strip() != "":
                has_class_in_row = True
                break
            # 이동된 수업이 있는지 체크
            check_key = f"{current_week_dates[i]}_{period}"
            val = st.session_state.custom_overrides.get(check_key, "")
            if isinstance(val, str) and val.startswith("[") and "] " in val:
                has_class_in_row = True
                break

        if not has_class_in_row: continue

        r_cols = st.columns([0.6, 2, 2, 2, 2, 2])
        r_cols[0].markdown(f"<div style='text-align:center; font-weight:bold; margin-top: 35px;'>{period}</div>",
                           unsafe_allow_html=True)

        for i, day in enumerate(days):
            curr_date = current_week_dates[i]
            override_key = f"{curr_date}_{period}"

            # 기본 반 정보
            base_class_info = str(st.session_state.timetable.loc[period, day]).strip()
            class_info = base_class_info

            # 2. 다른 곳에서 여기로 이동된 수업인지 판별 (비밀 태그 [반이름] 확인)
            override_val = st.session_state.custom_overrides.get(override_key, "")
            is_moved_class = isinstance(override_val, str) and override_val.startswith("[") and "] " in override_val

            if is_moved_class:
                end_idx = override_val.index("] ")
                class_info = override_val[1:end_idx]  # 빈칸이어도 반 이름 강제 인식 (예: 204)

            with r_cols[i + 1]:
                if curr_date in [str(d) for d in st.session_state.events["날짜"].values]:
                    if period == 1:
                        ev_name = \
                        st.session_state.events[st.session_state.events["날짜"].astype(str) == curr_date]["행사명"].values[0]
                        st.markdown(
                            f"<div style='color:red; font-weight:bold; text-align:center; margin-top:30px;'>🚩 {ev_name}</div>",
                            unsafe_allow_html=True)
                    continue

                if class_info:
                    cancel_match = st.session_state.cancels[
                        (st.session_state.cancels["날짜"].astype(str) == curr_date) &
                        (st.session_state.cancels["교시"].astype(str) == str(period))
                        ]
                    is_editing = st.session_state.get(f"edit_{override_key}", False)
                    grade_num = class_info[0] if class_info[0] in ['1', '2', '3'] else '1'

                    # 3. 휴강/이동으로 인해 원래 자리가 취소된 경우 (회색 버튼)
                    if not cancel_match.empty and not is_moved_class:
                        display_content = f"⚠️ {cancel_match.iloc[-1]['사유']}"
                        st.markdown("<span class='edit-anchor disabled-slot'></span>", unsafe_allow_html=True)
                        st.button(f"**{class_info}반**\n\n{display_content}", key=f"btn_{override_key}", disabled=True,
                                  use_container_width=True)
                    else:
                        # 정상 렌더링
                        default_content = weekly_content_map.get((curr_date, period), "진도 계획 없음")
                        display_content = st.session_state.custom_overrides.get(override_key, default_content)

                        if is_moved_class:
                            display_content = display_content.replace(f"[{class_info}] ", "", 1)

                        if is_editing:
                            st.markdown(
                                f"<div class='slot-card grade{grade_num} {'overridden' if override_key in st.session_state.custom_overrides else ''}'><div style='font-weight:bold;'>{class_info}반</div></div>",
                                unsafe_allow_html=True)

                            new_val = st.text_input("수정", value=display_content, key=f"in_{override_key}",
                                                    label_visibility="collapsed")

                            st.markdown("<div style='font-size:0.85em; color:#555; margin-top:5px;'>🔄 이동할 위치 (날짜/교시)</div>",
                                        unsafe_allow_html=True)
                            move_col1, move_col2 = st.columns([1.5, 1])
                            curr_date_obj = datetime.strptime(curr_date, "%Y-%m-%d").date()
                            new_date = move_col1.date_input("이동 날짜", value=curr_date_obj, key=f"d_{override_key}",
                                                            label_visibility="collapsed")
                            new_period = move_col2.selectbox("이동 교시", options=list(range(1, 10)), index=period - 1,
                                                             key=f"p_{override_key}", label_visibility="collapsed")

                            if st.session_state.get(f"confirm_overwrite_{override_key}", False):
                                st.warning("⚠️ 이동하려는 위치에 이미 일정이 있습니다. 덮어쓰시겠습니까?")
                                cw1, cw2 = st.columns(2)
                                if cw1.button("네, 덮어씁니다", key=f"yes_{override_key}", type="primary"):
                                    st.session_state[f"confirm_overwrite_{override_key}"] = False
                                    st.session_state[f"force_save_{override_key}"] = True
                                    st.rerun()
                                if cw2.button("아니오", key=f"no_{override_key}"):
                                    st.session_state[f"confirm_overwrite_{override_key}"] = False
                                    st.rerun()
                            else:
                                c1, c2, c3 = st.columns([1, 1, 1.4])

                                if c1.button("저장", key=f"sv_{override_key}",
                                             use_container_width=True) or st.session_state.get(f"force_save_{override_key}",
                                                                                               False):
                                    new_date_str = new_date.strftime("%Y-%m-%d")
                                    new_override_key = f"{new_date_str}_{new_period}"

                                    is_conflict = False
                                    if new_override_key != override_key and not st.session_state.get(
                                            f"force_save_{override_key}", False):
                                        if new_date.weekday() < 5:
                                            target_day_name = days[new_date.weekday()]
                                            target_base = str(
                                                st.session_state.timetable.loc[new_period, target_day_name]).strip()
                                            if target_base != "" or new_override_key in st.session_state.custom_overrides:
                                                is_conflict = True

                                    if is_conflict:
                                        st.session_state[f"confirm_overwrite_{override_key}"] = True
                                        st.rerun()
                                    else:
                                        if 'create_backup' in globals(): create_backup()
                                        st.session_state[f"force_save_{override_key}"] = False

                                        if new_override_key != override_key:
                                            new_cancel = pd.DataFrame([{"날짜": curr_date, "교시": str(period),
                                                                        "사유": f"🔄 {new_date_str[-5:]} {new_period}교시로 이동"}])
                                            st.session_state.cancels = pd.concat([st.session_state.cancels, new_cancel],
                                                                                 ignore_index=True)

                                            st.session_state.custom_overrides[
                                                new_override_key] = f"[{class_info}] {new_val}"
                                            st.session_state.custom_overrides.pop(override_key, None)
                                            if override_key in st.session_state.status_data: st.session_state.status_data[
                                                new_override_key] = st.session_state.status_data.pop(override_key)
                                            if override_key in st.session_state.memo_data: st.session_state.memo_data[
                                                new_override_key] = st.session_state.memo_data.pop(override_key)
                                        else:
                                            if is_moved_class:
                                                st.session_state.custom_overrides[
                                                    override_key] = f"[{class_info}] {new_val}"
                                            else:
                                                st.session_state.custom_overrides[override_key] = new_val

                                        st.session_state[f"edit_{override_key}"] = False
                                        save_custom_data()
                                        st.rerun()

                                if c2.button("취소", key=f"cc_{override_key}", use_container_width=True):
                                    st.session_state[f"edit_{override_key}"] = False
                                    st.rerun()

                                if c3.button("🗑️ 삭제/휴강", key=f"rs_{override_key}", use_container_width=True):
                                    if 'create_backup' in globals(): create_backup()
                                    new_cancel = pd.DataFrame([{"날짜": curr_date, "교시": str(period), "사유": "❌ 일정 삭제됨"}])
                                    st.session_state.cancels = pd.concat([st.session_state.cancels, new_cancel],
                                                                         ignore_index=True)

                                    st.session_state.custom_overrides.pop(override_key, None)
                                    st.session_state.status_data.pop(override_key, None)
                                    st.session_state.memo_data.pop(override_key, None)

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

                    m_c1, m_c2 = st.columns([1.5, 2])
                    curr_status = st.session_state.status_data.get(override_key, "O")
                    curr_memo = st.session_state.memo_data.get(override_key, "")
                    status_options = ["O", "△", "X"]
                    st_idx = status_options.index(curr_status) if curr_status in status_options else 0

                    m_c1.selectbox("st", status_options, index=st_idx, key=f"s_{override_key}",
                                   label_visibility="collapsed", on_change=update_status, args=(override_key,))
                    m_c2.text_input("m", value=curr_memo, key=f"m_{override_key}", placeholder="메모",
                                    label_visibility="collapsed", on_change=update_memo, args=(override_key,))
                else:
                    st.markdown("<div class='empty-slot'></div>", unsafe_allow_html=True)