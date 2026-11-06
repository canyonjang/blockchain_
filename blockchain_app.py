# -*- coding: utf-8 -*-
"""
교실 블록체인 체험 앱 (blockchain_)
가계자산 투자설계 11주차 — 학생 한 명이 노드 한 개가 됩니다.

설계 원칙
  · 실시간 폴링 없음. 화면은 수동 새로고침.
  · 투표는 한 번에 모아서 제출 → 학생 1명당 블록당 쓰기 1회.
  · 분반 크기(26 / 12 / 10명)에 따라 정족수와 담합 인원을 자동 계산.
  · 교수 화면이 강의실에 투사되는 상황을 기본으로 보고, 비밀 정보는 가려둡니다.
"""

import math
import random
import pandas as pd
import streamlit as st
from supabase import create_client

st.set_page_config(page_title="교실 블록체인", page_icon="⛓️", layout="wide")

# ----------------------------------------------------------------------
# 설정
# ----------------------------------------------------------------------
CLASSES = ["인하대", "숙대1", "숙대2"]
ADMIN_PW = st.secrets.get("ADMIN_PASSWORD", "3383")

PHASES = {
    0: "대기 — 학생 입장",
    1: "① 장부 배포",
    2: "② 거래와 승인",
    3: "③ 이중지불",
    4: "④ 51% 공격",
    5: "⑤ 수수료와 정산",
}
SECRET_PHASES = (3, 4)          # 학생이 보면 안 되는 단계


@st.cache_resource
def db():
    return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])


sb = db()

st.markdown("""
<style>
  .block-container {padding-top: 2rem; max-width: 1150px;}
  .boxed {background:#F4F3EC; border:1px solid #CFC7B0; border-radius:6px;
          padding:14px 18px; margin:8px 0 14px 0;}
  .big {font-size:1.35rem; font-weight:700; line-height:1.5;}
  .brick {color:#9C4A3C;} .blue {color:#41617A;} .muted {color:#666;}
  .secret {background:#9C4A3C; color:#fff; border-radius:6px;
           padding:16px 20px; margin:10px 0; font-size:1.05rem; line-height:1.6;}
  .warn {background:#FFF3CD; border:1px solid #D9B55B; border-radius:6px;
         padding:12px 16px; margin:8px 0 14px 0; font-weight:700; color:#6B4E00;}
  @media (max-width: 640px) {
    .block-container {padding-top: 1rem; padding-left: 1rem; padding-right: 1rem;}
    h1 {font-size: 1.45rem !important; line-height: 1.3 !important;}
    h2, h3 {font-size: 1.1rem !important;}
    .big {font-size: 1.05rem !important;}
    .boxed, .secret {padding: 10px 12px;}
    [data-testid="stMetricValue"] {font-size: 1.3rem !important;}
    .stButton > button {width: 100%; min-height: 44px; font-size: 1rem;}
  }
</style>
""", unsafe_allow_html=True)


def box(html):
    st.markdown(f'<div class="boxed">{html}</div>', unsafe_allow_html=True)


def warn(html):
    st.markdown(f'<div class="warn">{html}</div>', unsafe_allow_html=True)


def fmt(x):
    """정수면 정수로, 아니면 소수 한 자리로"""
    x = float(x)
    return f"{int(round(x))}" if abs(x - round(x)) < 1e-9 else f"{x:.1f}"


# ----------------------------------------------------------------------
# 데이터 접근
# ----------------------------------------------------------------------
def get_status(cls):
    r = sb.table("blockchain_status").select("*").eq("class_name", cls).execute().data
    if r:
        return r[0]
    row = {"class_name": cls, "phase": 0, "block_no": 0,
           "voting_open": False, "tx_open": False,
           "fee_per_vote": 1, "initial_coin": 3, "reveal": False}
    sb.table("blockchain_status").insert(row).execute()
    return row


def set_status(cls, **kw):
    sb.table("blockchain_status").update(kw).eq("class_name", cls).execute()


def students(cls):
    return sb.table("blockchain_students").select("*") \
        .eq("class_name", cls).order("name").execute().data


def txs(cls, block_no=None, status=None):
    q = sb.table("blockchain_tx").select("*").eq("class_name", cls)
    if block_no is not None:
        q = q.eq("block_no", block_no)
    if status:
        q = q.eq("status", status)
    return q.order("id").execute().data


def votes_of(tx_ids):
    if not tx_ids:
        return []
    return sb.table("blockchain_votes").select("*").in_("tx_id", tx_ids).execute().data


def missions_for(cls, name):
    return sb.table("blockchain_missions").select("*") \
        .eq("class_name", cls).eq("student", name).eq("active", True).execute().data


def quorum(n):
    """투표 정족수 — 소규모 분반도 작동하도록 최소 3명"""
    return max(3, math.ceil(n * 0.4))


# ======================================================================
# 사이드바
# ======================================================================
with st.sidebar:
    st.header("⛓️ 교실 블록체인")
    role = st.radio("화면", ["학생", "교수"], horizontal=True)
    cls = st.selectbox("분반", CLASSES)
    st.caption("화면은 자동으로 바뀌지 않습니다. "
               "교수님이 단계를 넘기면 새로고침 버튼을 누르세요.")

stt = get_status(cls)
phase = stt["phase"]
block_no = stt["block_no"]

# ======================================================================
# 교수 화면
# ======================================================================
if role == "교수":
    with st.sidebar:
        pw = st.text_input("관리자 비밀번호", type="password")
        st.markdown("---")
        projecting = st.toggle("🔴 이 화면이 강의실에 보이는 중", value=True,
                               help="켜 두면 공모자 이름·지령 내용·자동 탐지 결과가 "
                                    "화면에서 숨겨집니다. 지령을 보낼 때만 잠깐 끄세요.")
    if pw != ADMIN_PW:
        st.warning("관리자 비밀번호를 입력하세요.")
        st.stop()

    sts = students(cls)
    n = len(sts)
    q = quorum(n)
    supply = sum(float(s["balance"]) for s in sts)
    pend = txs(cls, block_no, "pending")

    h1, h2 = st.columns([4, 1])
    h1.title(f"교수 통제소 — {cls}")
    if h2.button("🔄 새로고침", use_container_width=True):
        st.rerun()
    st.subheader(f"{PHASES[phase]}   ·   블록 #{block_no}")

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("참여 노드", f"{n} 명")
    c2.metric("대기 거래", f"{len(pend)} 건")
    c3.metric("정족수", f"{q} 명", help="이만큼 투표하면 블록을 확정할 수 있습니다")
    c4.metric("총 발행량", f"{fmt(supply)} 코인")

    with st.expander(f"참여자 명단 ({n}명)"):
        if sts:
            st.dataframe(
                pd.DataFrame([{"이름": s["name"], "잔액": fmt(s["balance"])} for s in sts]),
                use_container_width=True, hide_index=True)
        else:
            st.write("아직 입장한 학생이 없습니다.")

    st.markdown("---")

    # ---------------- 단계 제어 ----------------
    st.markdown("### 단계 제어")
    cols = st.columns(6)
    for i, (k, label) in enumerate(PHASES.items()):
        if cols[i].button(label.split(" ")[0], key=f"ph{k}",
                          type="primary" if k == phase else "secondary"):
            set_status(cls, phase=k, voting_open=False, reveal=False)
            st.rerun()

    st.markdown("---")

    # ---------------- 0. 준비 ----------------
    if phase == 0:
        st.markdown("### 준비")
        st.write("학생들이 '학생' 화면에서 분반과 이름을 입력해 입장하게 하세요.")
        init = st.number_input("1인당 지급 코인", 1, 20, int(stt["initial_coin"]),
                               help="3코인을 권합니다. 이중지불 지령이 '1코인씩 4번'이 "
                                    "되어 학생이 제출하기 쉽습니다.")
        fee = st.number_input("블록당 검증 수수료 (투표한 노드에게)", 0, 5,
                              int(stt["fee_per_vote"]),
                              help="1코인을 권합니다. 이 수수료 때문에 총 발행량이 "
                                   "늘어나는데, 그것이 ⑤단계에서 설명할 '채굴 보상'입니다.")
        if st.button("① 장부 배포 — 전원에게 코인 지급", type="primary", disabled=(n == 0)):
            for s in sts:
                sb.table("blockchain_students").update({"balance": init}) \
                    .eq("id", s["id"]).execute()
            set_status(cls, initial_coin=init, fee_per_vote=fee, phase=1, block_no=0)
            st.success(f"{n}명에게 {init}코인씩 지급했습니다.")
            st.rerun()

    # ---------------- 1. 장부 배포 완료 ----------------
    elif phase == 1:
        st.markdown("### ① 장부 배포 완료")
        box("학생 화면에 <b>전원의 잔액</b>이 그대로 보입니다.<br>"
            "여기서 한 번 물어보세요 — "
            "<b>\"은행 계좌와 뭐가 다릅니까? 여러분은 지금 옆 사람 잔액을 보고 있습니다.\"</b>")
        if st.button("② 거래 단계로 — 송금 접수 열기", type="primary"):
            set_status(cls, phase=2, tx_open=True, block_no=block_no + 1)
            st.rerun()

    # ---------------- 2~4. 블록 운영 ----------------
    elif phase in (2, 3, 4):

        if phase == 2:
            box("학생들이 서로 송금합니다. 거래는 <b>대기 목록</b>에 쌓입니다.<br>"
                "5~10건쯤 쌓이면 <b>투표 열기</b> → <b>블록 확정</b>.<br>"
                "<b class='brick'>블록은 두 번만 돌리면 충분합니다.</b> "
                "첫 번째는 절차를 익히는 용도, 두 번째는 속도를 붙이는 용도입니다. "
                "세 번째부터는 지루해집니다.")
        elif phase == 3:
            box("<b class='brick'>이중지불 단계</b> — 공모자에게 비밀 지령을 보냅니다.<br>"
                "공모자는 <b>1코인씩 여러 번</b> 보냅니다. 한 건씩 보면 평범한 거래라 "
                "금액으로는 알 수 없고, <b>같은 사람이 보낸 건수를 세어야</b> 잡힙니다.")
        elif phase == 4:
            box("<b class='brick'>51% 공격 단계</b> — 교실의 과반에게 담합 지령을 보냅니다.<br>"
                "정상 거래가 통과되지 않는 장면을 만든 뒤, 당한 학생에게 소감을 물어보세요.")

        if phase in SECRET_PHASES and projecting:
            warn("🔴 지금 화면이 강의실에 보이는 중입니다. "
                 "공모자 이름과 지령 내용이 가려져 있습니다.<br>"
                 "지령을 보내려면 왼쪽 사이드바에서 <b>이 스위치를 잠깐 끄고</b>, "
                 "보낸 뒤 다시 켜세요. "
                 "<b>더 편한 방법</b> — 휴대폰으로 같은 주소를 열어 교수 화면에 로그인하면, "
                 "강의실 화면은 그대로 두고 손안에서 지령만 보낼 수 있습니다.")

        # ---------------- 지령 발송 ----------------
        show_secret = not (phase in SECRET_PHASES and projecting)
        with st.expander("🔒 비밀 지령 보내기", expanded=(phase in SECRET_PHASES)):
            names = [s["name"] for s in sts]
            bal_map = {s["name"]: float(s["balance"]) for s in sts}

            if not show_secret:
                st.info("강의실 투사 중이라 가려두었습니다. "
                        "사이드바의 🔴 스위치를 끄면 보입니다.")
            elif not names:
                st.info("학생이 입장해야 지령을 보낼 수 있습니다.")
            elif phase == 2:
                st.info("이 단계에서는 보낼 지령이 없습니다. ③ 또는 ④ 단계에서 사용하세요.")
            elif phase == 3:
                k = st.number_input("공모자 수", 1, max(1, n // 4), 1,
                                    help="26명 분반은 2명으로 하면 난이도가 올라갑니다")
                picked = st.multiselect("공모자 (비우면 무작위)", names, max_selections=int(k))
                if len(names) < 3:
                    st.warning("이중지불 지령은 학생이 3명 이상일 때 보낼 수 있습니다.")
                if st.button("이중지불 지령 발송", type="primary",
                             disabled=(len(names) < 3)):
                    chosen = picked or random.sample(names, int(k))
                    for c in chosen:
                        bal = int(round(bal_map.get(c, 0)))
                        cnt = bal + 1                      # 잔액보다 딱 한 번 더
                        others = [x for x in names if x != c]
                        targets = [others[i % len(others)] for i in range(cnt)]
                        txt = (f"당신의 잔액은 {bal}코인입니다.<br>"
                               f"<b>1코인씩 {cnt}번</b> 보내세요. "
                               f"받는 사람은 아무나 괜찮습니다.<br>"
                               f"예: {' · '.join(targets[:4])}{' …' if cnt > 4 else ''}<br>"
                               f"한 건씩 보면 평범한 거래라 티가 안 납니다. "
                               f"들키지 마세요.")
                        sb.table("blockchain_missions").insert({
                            "class_name": cls, "student": c,
                            "kind": "double_spend", "text": txt}).execute()
                    st.success(f"공모자 {', '.join(chosen)} 에게 지령을 보냈습니다.")
            elif phase == 4:
                victim = st.selectbox("거부당할 학생", names)
                share = st.slider("담합 인원 비율 (%)", 51, 90, 60)
                cnt = max(1, math.ceil(n * share / 100))
                if st.button(f"{cnt}명에게 담합 지령 발송", type="primary"):
                    pool = [x for x in names if x != victim]
                    chosen = random.sample(pool, min(cnt, len(pool)))
                    txt = (f"다음 투표에서 <b>{victim}</b> 이(가) 보낸 거래는 "
                           "내용과 상관없이 <b>무조건 거부</b>하세요.<br>"
                           "이유는 묻지 말고, 아무에게도 말하지 마세요.")
                    for c in chosen:
                        sb.table("blockchain_missions").insert({
                            "class_name": cls, "student": c,
                            "kind": "collude", "text": txt}).execute()
                    st.success(f"{len(chosen)}명에게 담합 지령을 보냈습니다.")

            if st.button("모든 지령 회수"):
                sb.table("blockchain_missions").update({"active": False}) \
                    .eq("class_name", cls).execute()
                st.success("지령을 모두 회수했습니다.")

        st.markdown("---")

        # ---------------- 대기 거래 ----------------
        st.markdown(f"### 블록 #{block_no} — 대기 거래 {len(pend)}건")
        bal_map = {s["name"]: float(s["balance"]) for s in sts}

        if pend:
            st.dataframe(pd.DataFrame([{
                "보낸 사람": t["sender"],
                "보낸 사람 잔액": fmt(bal_map.get(t["sender"], 0)),
                "받는 사람": t["receiver"],
                "금액": fmt(t["amount"]),
            } for t in pend]), use_container_width=True, hide_index=True)

            sums = {}
            for t in pend:
                sums[t["sender"]] = sums.get(t["sender"], 0) + float(t["amount"])
            bad = {k2: v for k2, v in sums.items() if v > bal_map.get(k2, 0) + 1e-9}
            if bad:
                if show_secret:
                    st.error("🔍 (교수용) 합계가 잔액을 넘는 사람: " + ", ".join(
                        f"{k2} — 잔액 {fmt(bal_map.get(k2,0))} / 보내려는 합 {fmt(v)}"
                        for k2, v in bad.items()))
                else:
                    st.caption("🔒 자동 탐지 결과가 가려져 있습니다.")
        else:
            st.info("아직 제출된 거래가 없습니다.")

        b1, b2, b3 = st.columns(3)
        if b1.button("송금 접수 " + ("닫기" if stt["tx_open"] else "열기")):
            set_status(cls, tx_open=not stt["tx_open"])
            st.rerun()
        if b2.button("🗳️ 투표 열기", type="primary", disabled=not pend):
            set_status(cls, voting_open=True, tx_open=False)
            st.rerun()
        if b3.button("투표 닫기", disabled=not stt["voting_open"]):
            set_status(cls, voting_open=False)
            st.rerun()

        # ---------------- 투표 현황 / 블록 확정 ----------------
        if pend:
            vs = votes_of([t["id"] for t in pend])
            tally = {}
            for v in vs:
                a, r = tally.get(v["tx_id"], (0, 0))
                tally[v["tx_id"]] = (a + (v["vote"] == "approve"),
                                     r + (v["vote"] == "reject"))
            voters = sorted({v["voter"] for v in vs})
            st.markdown(f"**투표한 노드: {len(voters)} / {n} 명**  (정족수 {q}명)")
            st.dataframe(pd.DataFrame([{
                "거래": f'{t["sender"]} → {t["receiver"]} ({fmt(t["amount"])})',
                "승인": tally.get(t["id"], (0, 0))[0],
                "거부": tally.get(t["id"], (0, 0))[1],
                "판정": "승인" if tally.get(t["id"], (0, 0))[0] > tally.get(t["id"], (0, 0))[1] else "거부",
            } for t in pend]), use_container_width=True, hide_index=True)

            if st.button("⛓️ 블록 확정 — 과반 승인된 거래를 장부에 기록",
                         type="primary", disabled=(len(voters) < q)):
                before = supply
                bal = dict(bal_map)
                fee = float(stt["fee_per_vote"])
                for t in pend:
                    a, r = tally.get(t["id"], (0, 0))
                    if a > r:
                        bal[t["sender"]] = bal.get(t["sender"], 0) - float(t["amount"])
                        bal[t["receiver"]] = bal.get(t["receiver"], 0) + float(t["amount"])
                        sb.table("blockchain_tx").update({"status": "confirmed"}) \
                            .eq("id", t["id"]).execute()
                    else:
                        sb.table("blockchain_tx").update({"status": "rejected"}) \
                            .eq("id", t["id"]).execute()
                for v in voters:                       # 검증 수수료
                    bal[v] = bal.get(v, 0) + fee
                for name, b in bal.items():
                    sb.table("blockchain_students").update({"balance": round(b, 2)}) \
                        .eq("class_name", cls).eq("name", name).execute()
                set_status(cls, voting_open=False, block_no=block_no + 1, tx_open=True)
                st.session_state["delta"] = (before, sum(bal.values()), fee * len(voters))
                st.rerun()

        if "delta" in st.session_state:
            before, after, feesum = st.session_state.pop("delta")
            created = after - before - feesum
            if created > 1e-6:
                st.error(f"🚨 총 발행량 {fmt(before)} → {fmt(after)} 코인. "
                         f"수수료({fmt(feesum)})를 빼고도 "
                         f"**{fmt(created)}코인이 새로 생겼습니다.**")
                box("<span class='big brick'>방금 돈이 복제됐습니다.</span><br>"
                    "이것이 디지털 화폐가 40년 동안 풀지 못했던 <b>이중지불 문제</b>입니다.<br>"
                    "여러분이 투표에서 걸러내야 했던 거래입니다. "
                    "금액은 평범했지만, <b>같은 사람이 보낸 건수를 세어보면</b> 보였습니다.")
            else:
                st.success(f"정상 확정. 총 발행량 {fmt(before)} → {fmt(after)} "
                           f"(늘어난 {fmt(feesum)}는 검증 수수료입니다)")

    # ---------------- 5. 정산 ----------------
    elif phase == 5:
        st.markdown("### ⑤ 수수료와 정산")
        box("투표에 참여한 노드에게만 수수료가 지급되었습니다.<br>"
            "최종 잔액을 공개하고 물어보세요 — "
            "<b>\"왜 이 사람들이 공짜로 검증을 해줬을까요?\"</b>")
        if not sts:
            st.info("아직 입장한 학생이 없습니다.")
        else:
            df = pd.DataFrame([{"이름": s["name"], "최종 잔액": float(s["balance"])}
                               for s in sts]).sort_values("최종 잔액", ascending=False)
            st.dataframe(df, use_container_width=True, hide_index=True)
            st.bar_chart(df.set_index("이름"), height=280)
            start_total = float(stt["initial_coin"]) * n
            box(f"<b>총 발행량이 {fmt(start_total)} → {fmt(supply)} 코인으로 늘었습니다.</b><br>"
                "늘어난 몫은 검증에 참여한 노드에게 간 수수료입니다. "
                "<b class='brick'>비트코인에서 새 코인이 생기는 방식이 정확히 이것입니다.</b>")
        box("<b>이어서 할 이야기</b><br>"
            "여러분은 손을 들어 합의했습니다. 비트코인은 <b>전기를 태워</b> 합의합니다.<br>"
            "왜 굳이 그 비싼 방법을 쓸까요? → 작업증명(PoW) 슬라이드로.")

    st.markdown("---")
    with st.expander("⚠️ 초기화"):
        st.write("이 분반의 체험 기록을 모두 지웁니다.")
        if st.text_input("확인을 위해 분반명을 입력", key="rs") == cls:
            if st.button("전부 삭제", type="primary"):
                ids = [t["id"] for t in txs(cls)]
                if ids:
                    sb.table("blockchain_votes").delete().in_("tx_id", ids).execute()
                sb.table("blockchain_tx").delete().eq("class_name", cls).execute()
                sb.table("blockchain_missions").delete().eq("class_name", cls).execute()
                sb.table("blockchain_students").delete().eq("class_name", cls).execute()
                set_status(cls, phase=0, block_no=0, voting_open=False,
                           tx_open=False, reveal=False)
                st.success("초기화했습니다.")
                st.rerun()

# ======================================================================
# 학생 화면
# ======================================================================
else:
    st.title("⛓️ 교실 블록체인")
    st.markdown("##### 나는 노드입니다")

    if "me" not in st.session_state:
        st.session_state["me"] = ""

    if not st.session_state["me"]:
        box("이름을 입력하면 이 블록체인의 <b>노드</b>가 됩니다.<br>"
            "<span class='muted'>같은 이름이 이미 있으면 그 자리로 다시 들어갑니다.</span>")
        nm = st.text_input("이름")
        if st.button("입장", type="primary") and nm.strip():
            nm = nm.strip()
            exist = sb.table("blockchain_students").select("*") \
                .eq("class_name", cls).eq("name", nm).execute().data
            if not exist:
                sb.table("blockchain_students").insert({
                    "class_name": cls, "name": nm,
                    "balance": float(stt["initial_coin"]) if phase >= 1 else 0,
                }).execute()
            st.session_state["me"] = nm
            st.rerun()
        st.stop()

    me = st.session_state["me"]
    sts = students(cls)
    mine = next((s for s in sts if s["name"] == me), None)
    if mine is None:
        st.session_state["me"] = ""
        st.rerun()

    top = st.columns([2, 1, 1])
    top[0].markdown(f"### {me} 님 · {cls}")
    top[1].metric("내 잔액", f"{fmt(mine['balance'])} 코인")
    if top[2].button("🔄 새로고침", use_container_width=True):
        st.rerun()

    st.caption(f"현재 단계: {PHASES[phase]}  ·  블록 #{block_no}")

    for m in missions_for(cls, me):
        st.markdown(f'<div class="secret">🔒 <b>비밀 미션</b><br>{m["text"]}</div>',
                    unsafe_allow_html=True)

    if phase == 0:
        st.info("교수님이 장부를 배포할 때까지 기다리세요.")
        st.stop()

    # ---- 장부 ----
    st.markdown("### 📒 장부 — 모두가 같은 장부를 봅니다")
    led = pd.DataFrame([{"노드": s["name"], "잔액": float(s["balance"])} for s in sts])
    st.dataframe(led, use_container_width=True, hide_index=True, height=240)
    st.caption(f"총 발행량 {fmt(led['잔액'].sum())} 코인 · 노드 {len(sts)}개")

    pend = txs(cls, block_no, "pending")

    # ---- 송금 ----
    if stt["tx_open"]:
        st.markdown("### 💸 송금하기")
        st.caption("한 사람에게 여러 번, 여러 사람에게 나눠서도 보낼 수 있습니다. "
                   "보낼 때마다 대기 목록에 한 줄씩 쌓입니다.")
        others = [s["name"] for s in sts if s["name"] != me]
        if others:
            with st.form("send", clear_on_submit=True):
                c1, c2 = st.columns([2, 1])
                to = c1.selectbox("받는 사람", others)
                amt = c2.number_input("금액 (코인)", 1, 20, 1, step=1)
                ok = st.form_submit_button("제출", type="primary")
            if ok:
                sb.table("blockchain_tx").insert({
                    "class_name": cls, "block_no": block_no,
                    "sender": me, "receiver": to, "amount": int(amt),
                    "status": "pending",
                }).execute()
                st.success(f"{to} 에게 {int(amt)}코인 — 대기 목록에 올라갔습니다. "
                           "아직 확정된 것이 아닙니다.")
                st.rerun()
        else:
            st.info("아직 다른 노드가 없습니다.")
    else:
        st.caption("지금은 송금 접수가 닫혀 있습니다.")

    # ---- 대기 목록 ----
    st.markdown(f"### ⏳ 대기 중인 거래 — {len(pend)}건")
    if pend:
        mine_cnt = sum(1 for t in pend if t["sender"] == me)
        st.dataframe(pd.DataFrame([{
            "보낸 사람": t["sender"] + ("  ← 나" if t["sender"] == me else ""),
            "받는 사람": t["receiver"],
            "금액": fmt(t["amount"]),
        } for t in pend]), use_container_width=True, hide_index=True)
        st.caption(f"이 중 내가 보낸 것 {mine_cnt}건. "
                   "아직 아무것도 확정되지 않았습니다. 투표를 거쳐야 장부에 들어갑니다.")
    else:
        st.caption("아직 제출된 거래가 없습니다.")

    # ---- 투표 (한 번에 제출) ----
    if stt["voting_open"] and pend:
        st.markdown("### 🗳️ 검증 — 이 거래들을 장부에 기록할까요?")
        box("보낸 사람의 <b>잔액</b>과 보내는 <b>금액</b>을 비교하세요.<br>"
            "<b class='brick'>한 사람이 여러 건을 올렸다면, 그 합계도 확인하세요.</b><br>"
            "<span class='muted'>전부 고른 뒤 맨 아래 '투표 제출'을 한 번만 누르면 됩니다.</span>")

        bal_map = {s["name"]: float(s["balance"]) for s in sts}
        done = sb.table("blockchain_votes").select("tx_id") \
            .eq("class_name", cls).eq("voter", me).execute().data
        voted = {d["tx_id"] for d in done}

        if voted >= {t["id"] for t in pend}:
            st.success("✔ 이번 블록 투표를 마쳤습니다. 교수님의 확정을 기다리세요.")
        else:
            with st.form("vote"):
                picks = {}
                for t in pend:
                    st.markdown(
                        f'**{t["sender"]} → {t["receiver"]}**  ·  {fmt(t["amount"])} 코인  '
                        f'<span class="muted">({t["sender"]} 잔액 '
                        f'{fmt(bal_map.get(t["sender"], 0))})</span>',
                        unsafe_allow_html=True)
                    picks[t["id"]] = st.radio(
                        "판정", ["승인", "거부"], horizontal=True,
                        key=f"v{t['id']}", label_visibility="collapsed")
                sent = st.form_submit_button("투표 제출", type="primary",
                                             use_container_width=True)
            if sent:
                sb.table("blockchain_votes").upsert([{
                    "class_name": cls, "tx_id": tid, "voter": me,
                    "vote": "approve" if v == "승인" else "reject",
                } for tid, v in picks.items()], on_conflict="tx_id,voter").execute()
                st.success("투표를 제출했습니다.")
                st.rerun()

    # ---- 확정된 기록 ----
    with st.expander("📜 확정된 거래 기록 (블록체인)"):
        conf = txs(cls, status="confirmed")
        if conf:
            st.dataframe(pd.DataFrame([{
                "블록": t["block_no"], "보낸 사람": t["sender"],
                "받는 사람": t["receiver"], "금액": fmt(t["amount"]),
            } for t in conf]), use_container_width=True, hide_index=True)
            st.caption("이 기록은 수정하거나 삭제할 수 없습니다.")
        else:
            st.write("아직 확정된 거래가 없습니다.")
