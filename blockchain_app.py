# -*- coding: utf-8 -*-
"""
교실 블록체인 체험 앱 (blockchain_)
가계자산 투자설계 11주차 — 학생 한 명이 노드 한 개가 됩니다.

설계 원칙
  · 실시간 폴링 없음. 학생은 제출할 때만 쓰고, 화면은 수동 새로고침.
  · 분반 크기(26 / 12 / 10명)에 따라 정족수와 담합 인원을 자동 계산.
  · 교수가 단계를 넘길 때만 집계 읽기가 일어남.
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
DEAD_ADDRESS = "❌ 존재하지 않는 주소"

PHASES = {
    0: "대기 — 학생 입장",
    1: "① 장부 배포",
    2: "② 거래와 승인",
    3: "③ 이중지불",
    4: "④ 취소 불가",
    5: "⑤ 51% 공격",
    6: "⑥ 수수료와 정산",
}


@st.cache_resource
def db():
    return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])


sb = db()

st.markdown("""
<style>
  .block-container {padding-top: 2rem; max-width: 1150px;}
  /* 휴대폰 화면 대응 — 학생 대부분이 폰으로 참여합니다 */
  @media (max-width: 640px) {
    .block-container {padding-top: 1rem; padding-left: 1rem; padding-right: 1rem;}
    h1 {font-size: 1.45rem !important; line-height: 1.3 !important;}
    h2, h3 {font-size: 1.1rem !important;}
    .big {font-size: 1.05rem !important;}
    .boxed, .secret {padding: 10px 12px;}
    [data-testid="stMetricValue"] {font-size: 1.3rem !important;}
    /* 승인·거부 버튼을 손가락으로 누르기 쉽게 */
    .stButton > button {width: 100%; min-height: 44px; font-size: 1rem;}
  }
  .boxed {background:#F4F3EC; border:1px solid #CFC7B0; border-radius:6px;
          padding:14px 18px; margin:8px 0 14px 0;}
  .big {font-size:1.35rem; font-weight:700; line-height:1.5;}
  .brick {color:#9C4A3C;} .blue {color:#41617A;} .muted {color:#666;}
  .secret {background:#9C4A3C; color:#fff; border-radius:6px;
           padding:16px 20px; margin:10px 0; font-size:1.05rem; line-height:1.6;}
</style>
""", unsafe_allow_html=True)


def box(html):
    st.markdown(f'<div class="boxed">{html}</div>', unsafe_allow_html=True)


# ----------------------------------------------------------------------
# 데이터 접근
# ----------------------------------------------------------------------
def get_status(cls):
    r = sb.table("blockchain_status").select("*").eq("class_name", cls).execute().data
    if r:
        return r[0]
    row = {"class_name": cls, "phase": 0, "block_no": 0,
           "voting_open": False, "tx_open": False,
           "fee_per_vote": 0.2, "initial_coin": 10, "reveal": False}
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


def votes_for(cls, block_no):
    tx_ids = [t["id"] for t in txs(cls, block_no)]
    if not tx_ids:
        return []
    return sb.table("blockchain_votes").select("*") \
        .in_("tx_id", tx_ids).execute().data


def missions_for(cls, name):
    return sb.table("blockchain_missions").select("*") \
        .eq("class_name", cls).eq("student", name).eq("active", True).execute().data


def quorum(n):
    """투표 정족수 — 소규모 분반도 작동하도록 최소 3명."""
    return max(3, math.ceil(n * 0.4))


def majority(approve, reject):
    return approve > reject


def total_supply(cls):
    return sum(float(s["balance"]) for s in students(cls))


# ======================================================================
# 사이드바 — 역할 선택
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
    pw = st.sidebar.text_input("관리자 비밀번호", type="password")
    if pw != ADMIN_PW:
        st.warning("관리자 비밀번호를 입력하세요.")
        st.stop()

    st.title(f"교수 통제소 — {cls}")
    st.subheader(f"현재 단계: {PHASES[phase]}   ·   블록 #{block_no}")

    sts = students(cls)
    n = len(sts)
    q = quorum(n)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("참여 노드", f"{n} 명")
    c2.metric("정족수", f"{q} 명", help="이만큼 투표하면 블록을 확정할 수 있습니다")
    c3.metric("총 발행량", f"{total_supply(cls):.1f} 코인")
    c4.metric("거래 접수", "열림" if stt["tx_open"] else "닫힘")

    st.markdown("---")

    # ---------------- 단계 제어 ----------------
    st.markdown("### 단계 제어")
    cols = st.columns(7)
    for i, (k, label) in enumerate(PHASES.items()):
        if cols[i].button(label.split(" ")[0], key=f"ph{k}",
                          type="primary" if k == phase else "secondary"):
            set_status(cls, phase=k, voting_open=False, reveal=False)
            st.rerun()

    st.markdown("---")

    # ---------------- 단계별 작업 ----------------
    if phase == 0:
        st.markdown("### 준비")
        st.write("학생들이 '학생' 화면에서 분반과 이름을 입력해 입장하게 하세요.")
        init = st.number_input("1인당 지급 코인", 1, 100, int(stt["initial_coin"]))
        if st.button("① 장부 배포 — 전원에게 코인 지급", type="primary"):
            for s in sts:
                sb.table("blockchain_students").update({"balance": init}) \
                    .eq("id", s["id"]).execute()
            set_status(cls, initial_coin=init, phase=1, block_no=0)
            st.success(f"{n}명에게 {init}코인씩 지급했습니다.")
            st.rerun()

        if sts:
            st.dataframe(pd.DataFrame([{"이름": s["name"], "잔액": s["balance"]} for s in sts]),
                         use_container_width=True, hide_index=True)

    elif phase == 1:
        st.markdown("### ① 장부 배포 완료")
        box("학생 화면에 <b>전원의 잔액</b>이 그대로 보입니다.<br>"
            "여기서 한 번 물어보세요 — "
            "<b>\"은행 계좌와 뭐가 다릅니까? 여러분은 지금 옆 사람 잔액을 보고 있습니다.\"</b>")
        st.dataframe(pd.DataFrame([{"이름": s["name"], "잔액": s["balance"]} for s in sts]),
                     use_container_width=True, hide_index=True)
        if st.button("② 거래 단계로 — 송금 접수 열기", type="primary"):
            set_status(cls, phase=2, tx_open=True, block_no=block_no + 1)
            st.rerun()

    elif phase in (2, 3, 4, 5):
        # ---- 단계 안내 ----
        if phase == 2:
            box("학생들이 서로 송금합니다. 거래는 <b>대기 목록</b>에 쌓입니다.<br>"
                "충분히 쌓이면 <b>투표 열기</b>를 누르세요.")
        elif phase == 3:
            box("<b class='brick'>이중지불 단계</b> — 아래에서 공모자에게 비밀 지령을 보내세요.<br>"
                "공모자는 자기 잔액보다 많은 금액을 두 사람에게 나눠 보냅니다. "
                "다른 학생들이 투표에서 잡아내야 합니다.")
        elif phase == 4:
            box("<b class='brick'>취소 불가 단계</b> — 한 학생에게 "
                "'존재하지 않는 주소로 보내기' 지령을 보내세요.<br>"
                "확정된 뒤 취소 버튼을 찾게 하면 됩니다. 없습니다.")
        elif phase == 5:
            box("<b class='brick'>51% 공격 단계</b> — 교실의 과반에게 담합 지령을 보냅니다.<br>"
                "정상 거래가 통과되지 않는 장면을 만든 뒤, 당한 학생에게 소감을 물어보세요.")

        # ---- 지령 발송 ----
        with st.expander("🔒 비밀 지령 보내기", expanded=(phase in (3, 4, 5))):
            names = [s["name"] for s in sts]
            if phase == 3:
                k = st.number_input("공모자 수", 1, max(1, n // 4), 1,
                                    help="26명 분반은 2명으로 하면 난이도가 올라갑니다")
                picked = st.multiselect("공모자 (비우면 무작위)", names, max_selections=int(k))
                if st.button("이중지불 지령 발송", type="primary"):
                    chosen = picked or random.sample(names, int(k))
                    for c in chosen:
                        bal = next(float(s["balance"]) for s in sts if s["name"] == c)
                        others = [x for x in names if x != c]
                        a, b = random.sample(others, 2) if len(others) >= 2 else (others[0], others[0])
                        txt = (f"당신의 잔액은 {bal:.1f}코인입니다.<br>"
                               f"<b>{a}</b>에게 {bal:.1f}코인, <b>{b}</b>에게 {bal:.1f}코인을 "
                               f"<b>각각 따로</b> 보내세요.<br>"
                               "두 거래를 연달아 제출하면 됩니다. 들키지 마세요.")
                        sb.table("blockchain_missions").insert({
                            "class_name": cls, "student": c,
                            "kind": "double_spend", "text": txt}).execute()
                    st.success(f"공모자 {', '.join(chosen)} 에게 지령을 보냈습니다. (학생에게 말하지 마세요)")

            elif phase == 4:
                target = st.selectbox("지령 받을 학생 (비우면 무작위)", ["(무작위)"] + names)
                if st.button("'존재하지 않는 주소로 보내기' 지령 발송", type="primary"):
                    c = random.choice(names) if target == "(무작위)" else target
                    txt = ("받는 사람에서 <b>❌ 존재하지 않는 주소</b>를 고르고 "
                           "3코인을 보내세요.<br>그다음 이 거래를 취소해 보세요.")
                    sb.table("blockchain_missions").insert({
                        "class_name": cls, "student": c,
                        "kind": "burn", "text": txt}).execute()
                    st.success(f"{c} 에게 지령을 보냈습니다.")

            elif phase == 5:
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
                    st.success(f"{len(chosen)}명에게 담합 지령을 보냈습니다. "
                               f"({victim} 에게는 보내지 않았습니다)")

            if st.button("모든 지령 회수"):
                sb.table("blockchain_missions").update({"active": False}) \
                    .eq("class_name", cls).execute()
                st.success("지령을 모두 회수했습니다.")

        st.markdown("---")

        # ---- 블록 운영 ----
        pend = txs(cls, block_no, "pending")
        st.markdown(f"### 블록 #{block_no} — 대기 거래 {len(pend)}건")

        bal_map = {s["name"]: float(s["balance"]) for s in sts}
        if pend:
            rows = []
            for t in pend:
                rows.append({
                    "보낸 사람": t["sender"],
                    "보낸 사람의 현재 잔액": bal_map.get(t["sender"], 0),
                    "받는 사람": t["receiver"],
                    "금액": float(t["amount"]),
                })
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

            # 이중지불 자동 탐지 (교수만 봄)
            sums = {}
            for t in pend:
                sums[t["sender"]] = sums.get(t["sender"], 0) + float(t["amount"])
            bad = {k: v for k, v in sums.items() if v > bal_map.get(k, 0) + 1e-9}
            if bad:
                st.error("🔍 (교수만 보임) 합계가 잔액을 넘는 사람: "
                         + ", ".join(f"{k} — 잔액 {bal_map.get(k,0):.1f} / 보내려는 합 {v:.1f}"
                                     for k, v in bad.items()))
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

        # ---- 투표 현황 ----
        if pend:
            vs = votes_for(cls, block_no)
            tally = {}
            for v in vs:
                a, r = tally.get(v["tx_id"], (0, 0))
                tally[v["tx_id"]] = (a + (v["vote"] == "approve"), r + (v["vote"] == "reject"))
            voters = len({v["voter"] for v in vs})
            st.markdown(f"**투표한 노드: {voters} / {n} 명**  (정족수 {q}명)")
            vr = []
            for t in pend:
                a, r = tally.get(t["id"], (0, 0))
                vr.append({
                    "거래": f'{t["sender"]} → {t["receiver"]} ({float(t["amount"]):.1f})',
                    "승인": a, "거부": r,
                    "판정": "승인" if majority(a, r) else "거부",
                })
            st.dataframe(pd.DataFrame(vr), use_container_width=True, hide_index=True)

            if st.button("⛓️ 블록 확정 — 과반 승인된 거래를 장부에 기록",
                         type="primary", disabled=(voters < q)):
                before = total_supply(cls)
                bal = {s["name"]: float(s["balance"]) for s in sts}
                fee = float(stt["fee_per_vote"])
                for t in pend:
                    a, r = tally.get(t["id"], (0, 0))
                    if majority(a, r):
                        bal[t["sender"]] = bal.get(t["sender"], 0) - float(t["amount"])
                        if t["receiver"] != DEAD_ADDRESS:
                            bal[t["receiver"]] = bal.get(t["receiver"], 0) + float(t["amount"])
                        sb.table("blockchain_tx").update({"status": "confirmed"}) \
                            .eq("id", t["id"]).execute()
                    else:
                        sb.table("blockchain_tx").update({"status": "rejected"}) \
                            .eq("id", t["id"]).execute()
                # 검증에 참여한 노드에게 수수료 지급 (⑥단계에서 공개)
                for v in {v["voter"] for v in vs}:
                    bal[v] = bal.get(v, 0) + fee
                for name, b in bal.items():
                    sb.table("blockchain_students").update({"balance": round(b, 2)}) \
                        .eq("class_name", cls).eq("name", name).execute()
                set_status(cls, voting_open=False, block_no=block_no + 1,
                           tx_open=True, reveal=True)
                after = sum(bal.values())
                st.session_state["supply_delta"] = (before, after, fee * len({v["voter"] for v in vs}))
                st.rerun()

        # ---- 확정 직후 결과 ----
        if "supply_delta" in st.session_state:
            before, after, feesum = st.session_state.pop("supply_delta")
            created = after - before - feesum
            if created > 1e-6:
                st.error(f"🚨 총 발행량이 {before:.1f} → {after:.1f} 코인으로 늘었습니다. "
                         f"수수료({feesum:.1f})를 빼고도 **{created:.1f}코인이 새로 생겼습니다.**")
                box("<span class='big brick'>방금 돈이 복제됐습니다.</span><br>"
                    "이것이 디지털 화폐가 40년 동안 풀지 못했던 <b>이중지불 문제</b>입니다.<br>"
                    "여러분이 투표에서 걸러내야 했던 거래입니다.")
            elif created < -1e-6:
                st.warning(f"총 발행량이 {before:.1f} → {after:.1f} 코인으로 줄었습니다. "
                           f"**{abs(created):.1f}코인이 영구히 사라졌습니다.**")
                box("<span class='big brick'>존재하지 않는 주소로 보낸 코인은 "
                    "누구도 되찾을 수 없습니다.</span><br>"
                    "취소 버튼은 없습니다. 고객센터도 없습니다.")
            else:
                st.success("정상적으로 확정되었습니다. 총 발행량이 유지되었습니다.")

    elif phase == 6:
        st.markdown("### ⑥ 수수료와 정산")
        box("투표에 참여한 노드에게만 수수료가 지급되었습니다.<br>"
            "최종 잔액을 공개하고 물어보세요 — "
            "<b>\"왜 이 사람들이 공짜로 검증을 해줬을까요?\"</b>")
        df = pd.DataFrame([{"이름": s["name"], "최종 잔액": float(s["balance"])} for s in sts]) \
            .sort_values("최종 잔액", ascending=False)
        st.dataframe(df, use_container_width=True, hide_index=True)
        st.bar_chart(df.set_index("이름"), height=280)
        box("<b>이어서 할 이야기</b><br>"
            "여러분은 손을 들어 합의했습니다. 비트코인은 <b>전기를 태워</b> 합의합니다.<br>"
            "왜 굳이 그 비싼 방법을 쓸까요? → 작업증명(PoW) 슬라이드로.")

    st.markdown("---")
    with st.expander("⚠️ 초기화"):
        st.write("이 분반의 체험 기록을 모두 지웁니다.")
        if st.text_input("확인을 위해 분반명을 입력", key="rs") == cls:
            if st.button("전부 삭제", type="primary"):
                for tbl in ("blockchain_votes",):
                    ids = [t["id"] for t in txs(cls)]
                    if ids:
                        sb.table(tbl).delete().in_("tx_id", ids).execute()
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
    top[1].metric("내 잔액", f"{float(mine['balance']):.1f} 코인")
    if top[2].button("🔄 새로고침"):
        st.rerun()

    st.caption(f"현재 단계: {PHASES[phase]}  ·  블록 #{block_no}")

    # ---- 비밀 지령 ----
    for m in missions_for(cls, me):
        st.markdown(
            f'<div class="secret">🔒 <b>비밀 미션</b><br>{m["text"]}</div>',
            unsafe_allow_html=True)

    if phase == 0:
        st.info("교수님이 장부를 배포할 때까지 기다리세요.")
        st.stop()

    # ---- 장부 ----
    st.markdown("### 📒 장부 — 모두가 같은 장부를 봅니다")
    led = pd.DataFrame([{"노드": s["name"], "잔액": float(s["balance"])} for s in sts])
    st.dataframe(led, use_container_width=True, hide_index=True, height=240)
    st.caption(f"총 발행량 {led['잔액'].sum():.1f} 코인 · 노드 {len(sts)}개")

    # ---- 송금 ----
    if stt["tx_open"]:
        st.markdown("### 💸 송금하기")
        others = [s["name"] for s in sts if s["name"] != me]
        if phase >= 4:
            others = others + [DEAD_ADDRESS]
        with st.form("send"):
            c1, c2 = st.columns([2, 1])
            to = c1.selectbox("받는 사람", others)
            amt = c2.number_input("금액", 0.5, 1000.0, 1.0, step=0.5)
            ok = st.form_submit_button("제출", type="primary")
        if ok:
            sb.table("blockchain_tx").insert({
                "class_name": cls, "block_no": block_no,
                "sender": me, "receiver": to, "amount": float(amt),
                "status": "pending",
            }).execute()
            st.success("대기 목록에 올라갔습니다. 아직 확정된 것이 아닙니다.")
            st.rerun()
    else:
        st.caption("지금은 송금 접수가 닫혀 있습니다.")

    # ---- 투표 ----
    if stt["voting_open"]:
        st.markdown("### 🗳️ 검증 — 이 거래를 장부에 기록할까요?")
        box("보낸 사람의 <b>현재 잔액</b>과 보내려는 <b>금액</b>을 비교해 보세요.<br>"
            "<span class='muted'>한 사람이 여러 건을 올렸다면, 합계도 확인하세요.</span>")

        pend = txs(cls, block_no, "pending")
        my_votes = {v["tx_id"] for v in sb.table("blockchain_votes").select("tx_id")
                    .eq("class_name", cls).eq("voter", me).execute().data}
        bal_map = {s["name"]: float(s["balance"]) for s in sts}

        for t in pend:
            with st.container(border=True):
                a, b, c = st.columns([3, 1, 1])
                a.markdown(
                    f'**{t["sender"]} → {t["receiver"]}**  ·  {float(t["amount"]):.1f} 코인  \n'
                    f'<span class="muted">{t["sender"]} 의 현재 잔액: '
                    f'{bal_map.get(t["sender"], 0):.1f} 코인</span>',
                    unsafe_allow_html=True)
                done = t["id"] in my_votes
                if b.button("✅ 승인", key=f"ap{t['id']}", disabled=done,
                            use_container_width=True):
                    sb.table("blockchain_votes").upsert({
                        "class_name": cls, "tx_id": t["id"],
                        "voter": me, "vote": "approve"}, on_conflict="tx_id,voter").execute()
                    st.rerun()
                if c.button("❌ 거부", key=f"rj{t['id']}", disabled=done,
                            use_container_width=True):
                    sb.table("blockchain_votes").upsert({
                        "class_name": cls, "tx_id": t["id"],
                        "voter": me, "vote": "reject"}, on_conflict="tx_id,voter").execute()
                    st.rerun()
                if done:
                    a.caption("✔ 투표 완료")

    # ---- 확정된 기록 ----
    with st.expander("📜 확정된 거래 기록 (블록체인)"):
        conf = txs(cls, status="confirmed")
        if conf:
            st.dataframe(pd.DataFrame([{
                "블록": t["block_no"], "보낸 사람": t["sender"],
                "받는 사람": t["receiver"], "금액": float(t["amount"]),
            } for t in conf]), use_container_width=True, hide_index=True)
            st.caption("이 기록은 수정하거나 삭제할 수 없습니다. 취소 버튼이 없는 것을 확인하세요.")
        else:
            st.write("아직 확정된 거래가 없습니다.")
