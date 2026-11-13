# 상담원장 정리 스크립트
#
# 이 스크립트가 따르는 결정 기록: ../my-wiki/decisions/d-005-상담원장-정리-다섯-결정.md
#   d-005 (1) «종결»=«완료», «대기»=«보류»로 합친다
#   d-005 (2) 처리시간 음수는 지우지 않는다. 값은 그대로 두고 _표시 칸에 이유를 적는다
#   d-005 (3) 만족도 6~10점은 지우지 않는다. _표시 칸에 이유를 적고, 평균 만족도에서는 표시한 줄을 뺀다
#   d-005 (4) 칸 이름은 원본 그대로 둔다. _표시 칸만 맨 끝에 더한다
#   d-005 (5) 고객번호 앞뒤 공백을 없앤다
# 그 밖의 처리(테스트 접수 제거, 접수번호 중복 정리, 표기 통일, 7월 이후 전화 초→분 등)는
# 작성기준 시트(원장 파일의 «작성기준»)와 처음 정리할 때의 판단을 그대로 옮긴 것이다.
#
# 원본은 읽기만 한다. 결과는 정리본/ 에 쓴다.
# 실행: python -I -X utf8 정리/정리_상담원장.py   (cleaner 폴더 어디서든 가능)

import csv
from pathlib import Path

import numpy as np
import openpyxl
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent          # cleaner/
SRC = ROOT.parent / "messy" / "상담원장_2025.xlsx"
OUT = ROOT / "정리본"
MARK = "_표시"
MARK_NEG = "처리시간 음수: 틀린 값이지만 진짜 값을 몰라 그대로 둠"
MARK_SAT = "만족도 6~10점: NPS를 잘못 넣은 것으로 보이나 확인 못함. 평균 만족도에서 뺌"
R_TEST = "테스트 접수 — 상담원ID AG999"
R_OLD = "이전 상태 — 같은 접수번호에 최종수정일이 더 늦은 줄이 있음"
R_TIE = "중복 추출 — 같은 접수번호·같은 최종수정일의 줄이 또 있음(아래 줄을 남김)"

# ---------- 원본 읽기 (읽기 전용) ----------
wb = openpyxl.load_workbook(SRC, read_only=True)
rows = list(wb["원장"].iter_rows(values_only=True))
wb.close()
H = list(rows[0])
O = pd.DataFrame(rows[1:], columns=H)
O.insert(0, "원본행", range(2, len(O) + 2))
n_src = len(O)

# ---------- 줄 지우기 ----------
is_test = O["상담원ID"] == "AG999"
T = O[~is_test]
T = T.sort_values(["접수번호", "최종수정일", "원본행"])
keep_idx = T.drop_duplicates("접수번호", keep="last").index
removed = []                                           # (원본행 줄, 이유)
for _, r in O[is_test].iterrows():
    removed.append((r, R_TEST))
last_by_id = T.drop_duplicates("접수번호", keep="last").set_index("접수번호")
for _, r in T[~T.index.isin(keep_idx)].iterrows():
    k = last_by_id.loc[r["접수번호"]]
    removed.append((r, R_TIE if r["최종수정일"] == k["최종수정일"] else R_OLD))
removed.sort(key=lambda x: x[0]["원본행"])
n_test = sum(1 for _, why in removed if why == R_TEST)
n_old = sum(1 for _, why in removed if why == R_OLD)
n_tie = sum(1 for _, why in removed if why == R_TIE)

df = O.loc[keep_idx].sort_values("원본행").copy()
orig = df.copy()                                       # 바뀌기 전 값(세기용)

# ---------- 표기 통일 ----------
df["접수일"] = pd.to_datetime(df["접수일"].str.replace(r"[/.]", "-", regex=True)).dt.strftime("%Y-%m-%d")
df["접수채널"] = df["접수채널"].str.strip().replace({
    "유선": "전화", "전화상담": "전화", "TEL": "전화",
    "chatbot": "챗봇", "Chatbot": "챗봇", "챗 봇": "챗봇",
    "모바일앱": "앱", "app": "앱", "APP": "앱",
    "e-mail": "이메일", "E-mail": "이메일", "메일": "이메일"})
df["지역"] = df["지역"].replace({"경기도": "경기", "서울시": "서울", "서울특별시": "서울"})
df["상담원팀"] = df["상담원팀"].str.replace(" ", "", regex=False)
# d-005 (1): 종결=완료, 대기=보류
df["처리상태"] = df["처리상태"].str.strip().replace(
    {"처리완료": "완료", "종결": "완료", "처리중": "진행중", "대기": "보류"})
df["재문의"] = df["재문의"].replace(
    {"n": "N", "아니오": "N", "FALSE": "N", "y": "Y", "예": "Y", "TRUE": "Y"})
df["월정액"] = df["월정액"].map(
    lambda v: v if v is None or isinstance(v, int) else int(v.replace(",", "").replace("원", "")))
# d-005 (5): 고객번호 앞뒤 공백
df["고객번호"] = df["고객번호"].str.strip()

# ---------- 만족도 (0·-·미응답은 빈칸, «N점»은 N, 6~10은 값 그대로 두고 표시) ----------
def sat(v):
    if v is None:
        return np.nan
    if isinstance(v, str):
        if v in ("-", "미응답"):
            return np.nan
        v = int(v.replace("점", ""))
    if v == 0:
        return np.nan
    return float(v)

df["만족도"] = df["만족도"].map(sat)
sat_hi = df["만족도"] > 5                                # d-005 (3): 6~10점
assert df.loc[sat_hi, "만족도"].between(6, 10).all()

# ---------- 상담시간: 값이 180을 넘는 줄은 초 단위 → 분 ----------
sec = df["상담시간"] > 180
before_sec = df.loc[sec, "상담시간"].copy()
df["상담시간"] = np.where(sec, df["상담시간"] / 60, df["상담시간"]).round(2)

# ---------- d-005 (2): 처리시간 음수는 그대로, 표시만 ----------
neg = df["처리시간"] < 0

# ---------- d-005 (3)(4): _표시 칸 ----------
mark = pd.Series("", index=df.index)
mark[neg] = MARK_NEG
mark[sat_hi] = np.where(neg[sat_hi], MARK_NEG + "; " + MARK_SAT, MARK_SAT)
df[MARK] = mark

out = df.drop(columns="원본행")
assert list(out.columns) == H + [MARK]                  # 칸 이름: 원본 24칸 그대로 + _표시
OUT.mkdir(exist_ok=True)
out.to_csv(OUT / "상담원장_정리.csv", index=False, encoding="utf-8-sig")

with open(OUT / "지운줄.csv", "w", encoding="utf-8-sig", newline="") as f:
    w = csv.writer(f)
    w.writerow(["원본행"] + H + ["지운이유"])
    for r, why in removed:
        raw = rows[int(r["원본행"]) - 1]                # rows[0]은 머리글. 원본 칸 값을 표를 거치지 않고 그대로
        assert raw[H.index("접수번호")] == r["접수번호"]
        w.writerow([r["원본행"]] + ["" if v is None else v for v in raw] + [why])

# ---------- 다섯 숫자와 고객 수 (정리본 값으로) ----------
rq = out["재문의"].dropna()
sat_ok = out.loc[out[MARK].str.contains("만족도 6~10점") == False, "만족도"].dropna()
five = {
    "상담 건수": len(out),
    "평균 상담시간(분)": out["상담시간"].mean(),
    "재문의율(%)": (rq == "Y").mean() * 100,
    "평균 만족도": sat_ok.mean(),
    "완료율(%)": (out["처리상태"] == "완료").mean() * 100,
}
n_cust = out["고객번호"].nunique()

# ---------- 변경요약.md ----------
o = orig
def cnt(mask):
    return int(mask.sum())
oc = lambda c: o[c]
st_o = oc("처리상태")
ex = before_sec.sort_values().iloc[[0, len(before_sec) // 2, -1]]
exrows = [(o.loc[i, "접수번호"], o.loc[i, "접수일"], int(before_sec[i]), float(df.loc[i, "상담시간"])) for i in ex.index]
q = lambda s: f"{s:,}"

L = []
L.append("# 상담원장 정리 변경 요약\n")
L.append("- 스크립트: `정리/정리_상담원장.py` · 결정 기록: `../my-wiki/decisions/d-005-상담원장-정리-다섯-결정.md`")
L.append(f"- 원본: `../messy/상담원장_2025.xlsx` 시트 «원장» ({q(n_src)}줄 · {len(H)}칸). 원본은 읽기만 했다.")
L.append(f"- 결과: `정리본/상담원장_정리.csv` ({q(len(out))}줄 · {len(out.columns)}칸), `정리본/지운줄.csv` ({q(len(removed))}줄)")
L.append("- 아래 줄 수는 모두 원본 값에서 센 것이다. 정리본에 남은 {0}줄 가운데 몇 줄이 바뀌었는지를 적었다.\n".format(q(len(out))))

L.append("## 1. 줄 수\n")
L.append("| 단계 | 줄 수 |\n|---|---|")
L.append(f"| 원본 | {q(n_src)} |")
L.append(f"| 테스트 접수(AG999) 지움 | −{q(n_test)} |")
L.append(f"| 이전 상태(같은 접수번호에 최종수정일이 더 늦은 줄) 지움 | −{q(n_old)} |")
L.append(f"| 중복 추출(같은 접수번호·같은 최종수정일, 아래 줄을 남김) 지움 | −{q(n_tie)} |")
L.append(f"| 정리본 | {q(len(out))} |")
L.append(f"\n빼기: {q(n_src)} − {q(n_test + n_old + n_tie)} = {q(n_src - n_test - n_old - n_tie)} (정리본 {q(len(out))}줄과 {'같다' if n_src - n_test - n_old - n_tie == len(out) else '다르다'}). 지운 줄 전부와 이유는 `지운줄.csv`.\n")

L.append("## 2. 값을 바꾼 것 (정리본에 남은 줄 기준)\n")
L.append("| 칸 | 무엇을 | 줄 수 | 결정 |\n|---|---|---|---|")
L.append(f"| 상담시간 | 값이 180을 넘는 줄을 **초에서 분으로** (÷60, 소수 둘째 자리) | {q(int(sec.sum()))} | 기준 변경 |")
L.append(f"| 처리상태 | «종결» → «완료» | {q(cnt(st_o.str.strip() == '종결'))} | d-005 (1) |")
L.append(f"| 처리상태 | «대기» → «보류» | {q(cnt(st_o.str.strip() == '대기'))} | d-005 (1) |")
L.append(f"| 처리상태 | «처리완료» → «완료» | {q(cnt(st_o.str.strip() == '처리완료'))} | 처음 정리할 때의 판단 |")
L.append(f"| 처리상태 | «처리중» → «진행중» | {q(cnt(st_o.str.strip() == '처리중'))} | 처음 정리할 때의 판단 |")
L.append(f"| 처리상태 | «완료 »의 뒤 공백 제거 | {q(cnt(st_o == '완료 '))} | 처음 정리할 때의 판단 |")
L.append(f"| 고객번호 | 앞뒤 공백 제거 | {q(cnt(oc('고객번호') != df['고객번호']))} | d-005 (5) |")
L.append(f"| 접수일 | `/` `.` 표기를 `2025-03-14` 꼴로 | {q(cnt(oc('접수일') != df['접수일']))} | 처음 정리할 때의 판단 |")
L.append(f"| 접수채널 | 17가지 표기를 전화·챗봇·앱·이메일로 | {q(cnt(oc('접수채널') != df['접수채널']))} | 처음 정리할 때의 판단 |")
L.append(f"| 지역 | «경기도»·«서울시»·«서울특별시» → «경기»·«서울» | {q(cnt(oc('지역') != df['지역']))} | 처음 정리할 때의 판단 |")
L.append(f"| 상담원팀 | «요금 팀» 같은 안쪽 공백 제거 | {q(cnt(oc('상담원팀') != df['상담원팀']))} | 처음 정리할 때의 판단 |")
L.append(f"| 재문의 | y·예·TRUE·n·아니오·FALSE → Y·N (빈칸은 그대로) | {q(cnt(oc('재문의').notna() & (oc('재문의') != df['재문의'])))} | 작성기준 + 처음 정리할 때의 판단 |")
L.append(f"| 월정액 | «33,000원» → 33000 | {q(cnt(oc('월정액').map(lambda v: isinstance(v, str))))} | 처음 정리할 때의 판단 |")
L.append(f"| 만족도 | «0» → 빈칸 | {q(cnt(oc('만족도') == 0))} | 작성기준 |")
L.append(f"| 만족도 | «-» → 빈칸 | {q(cnt(oc('만족도') == '-'))} | 작성기준 |")
L.append(f"| 만족도 | «미응답» → 빈칸 | {q(cnt(oc('만족도') == '미응답'))} | 작성기준 |")
L.append(f"| 만족도 | «5점» 꼴 → 숫자 | {q(cnt(oc('만족도').map(lambda v: isinstance(v, str) and v.endswith('점'))))} | 처음 정리할 때의 판단 |")
L.append("")

L.append("## 3. 지우지 않고 표시만 한 것 (`_표시` 칸)\n")
L.append("| 무엇 | 줄 수 | 값 | 결정 |\n|---|---|---|---|")
L.append(f"| 처리시간 음수 | {q(int(neg.sum()))} | 그대로 둠 | d-005 (2) |")
L.append(f"| 만족도 6~10점 | {q(int(sat_hi.sum()))} | 그대로 둠. 평균 만족도에서만 뺌 | d-005 (3) |")
L.append(f"\n`_표시` 칸에 값이 적힌 줄: {q(int((out[MARK] != '').sum()))}줄 (정리본 {q(len(out))}줄 모두에 칸이 있고, 나머지는 빈칸). 칸 이름 24개는 원본 그대로이고 `_표시`만 맨 끝에 더했다 (d-005 (4)).\n")

L.append("## 4. 상담시간 칸: 초에서 분으로\n")
L.append("**상담시간 값이 180을 넘는 줄 "
         f"{q(int(sec.sum()))}줄을 초 단위로 보고 60으로 나눠 분으로 바꿨다.**\n")
L.append(f"- 바꾸기 전(초): {int(before_sec.min())} ~ {int(before_sec.max())}, 바꾼 뒤(분): {df.loc[sec, '상담시간'].min()} ~ {df.loc[sec, '상담시간'].max()}")
L.append("- 예: " + " · ".join(f"{a}({b}) {c}초 → {d}분" for a, b, c, d in exrows))
L.append("- 나머지 줄(180 이하)은 분 단위로 보고 그대로 두었다.\n")

L.append("## 5. 다섯 숫자와 고객 수 (정리본 기준)\n")
L.append("| 지표 | 값 |\n|---|---|")
L.append(f"| 상담 건수 | {q(five['상담 건수'])}건 |")
L.append(f"| 평균 상담시간 | {five['평균 상담시간(분)']:.2f}분 |")
L.append(f"| 재문의율 | {five['재문의율(%)']:.2f}% (Y {q(int((rq == 'Y').sum()))}건 ÷ 3월 이후 {q(len(rq))}건) |")
L.append(f"| 평균 만족도 | {five['평균 만족도']:.3f}점 (`_표시`로 뺀 줄을 제외한 {q(len(sat_ok))}건) |")
L.append(f"| 완료율 | {five['완료율(%)']:.2f}% ({q(int((out['처리상태'] == '완료').sum()))}건 ÷ {q(len(out))}건) |")
L.append(f"| 고객 수 | {q(n_cust)}명 (고객번호 종류) |")
(OUT / "변경요약.md").write_text("\n".join(L) + "\n", encoding="utf-8")

print("원본", n_src, "→ 정리본", len(out), "| 지운 줄", len(removed))
for k, v in five.items():
    print(k, round(v, 3))
print("고객 수", n_cust)
