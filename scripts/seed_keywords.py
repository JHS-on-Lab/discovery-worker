"""
키워드 300개 초기 데이터 적재 스크립트.

실행:
  python scripts/seed_keywords.py           # 실제 DB 적재
  python scripts/seed_keywords.py --dry-run # 적재 없이 목록만 출력
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import text
from app.repository.db import db_context

# ---------------------------------------------------------------------------
# 키워드 정의  (keyword, portal_type, display_name, priority, interval_seconds)
# ---------------------------------------------------------------------------

_KEYWORDS: list[tuple[str, str, str | None, int, int]] = [

    # ── NAVER_NEWS (100개) ──────────────────────────────────────────────────
    ("삼성전자",        "NAVER_NEWS", None, 0, 86400),
    ("SK하이닉스",      "NAVER_NEWS", None, 0, 86400),
    ("LG에너지솔루션",  "NAVER_NEWS", None, 0, 86400),
    ("현대차",          "NAVER_NEWS", None, 0, 86400),
    ("기아",            "NAVER_NEWS", None, 0, 86400),
    ("네이버",          "NAVER_NEWS", None, 0, 86400),
    ("카카오",          "NAVER_NEWS", None, 0, 86400),
    ("셀트리온",        "NAVER_NEWS", None, 0, 86400),
    ("포스코홀딩스",    "NAVER_NEWS", None, 0, 86400),
    ("LG화학",          "NAVER_NEWS", None, 0, 86400),
    ("현대모비스",      "NAVER_NEWS", None, 0, 86400),
    ("삼성SDI",         "NAVER_NEWS", None, 0, 86400),
    ("KB금융",          "NAVER_NEWS", None, 0, 86400),
    ("신한지주",        "NAVER_NEWS", None, 0, 86400),
    ("하나금융지주",    "NAVER_NEWS", None, 0, 86400),
    ("우리금융지주",    "NAVER_NEWS", None, 0, 86400),
    ("삼성물산",        "NAVER_NEWS", None, 0, 86400),
    ("SK텔레콤",        "NAVER_NEWS", None, 0, 86400),
    ("KT",              "NAVER_NEWS", None, 0, 86400),
    ("LG전자",          "NAVER_NEWS", None, 0, 86400),
    ("두산에너빌리티",  "NAVER_NEWS", None, 0, 86400),
    ("한국전력",        "NAVER_NEWS", None, 0, 86400),
    ("삼성바이오로직스","NAVER_NEWS", None, 0, 86400),
    ("에코프로비엠",    "NAVER_NEWS", None, 0, 86400),
    ("에코프로",        "NAVER_NEWS", None, 0, 86400),
    ("고려아연",        "NAVER_NEWS", None, 0, 86400),
    ("현대건설",        "NAVER_NEWS", None, 0, 86400),
    ("GS건설",          "NAVER_NEWS", None, 0, 86400),
    ("대우건설",        "NAVER_NEWS", None, 0, 86400),
    ("롯데케미칼",      "NAVER_NEWS", None, 0, 86400),
    ("금리",            "NAVER_NEWS", None, 0, 86400),
    ("기준금리",        "NAVER_NEWS", None, 0, 86400),
    ("환율",            "NAVER_NEWS", None, 0, 86400),
    ("코스피",          "NAVER_NEWS", None, 0, 86400),
    ("코스닥",          "NAVER_NEWS", None, 0, 86400),
    ("물가",            "NAVER_NEWS", None, 0, 86400),
    ("인플레이션",      "NAVER_NEWS", None, 0, 86400),
    ("반도체",          "NAVER_NEWS", None, 0, 86400),
    ("배터리",          "NAVER_NEWS", None, 0, 86400),
    ("전기차",          "NAVER_NEWS", None, 0, 86400),
    ("AI반도체",        "NAVER_NEWS", None, 0, 86400),
    ("HBM",             "NAVER_NEWS", None, 0, 86400),
    ("챗GPT",           "NAVER_NEWS", None, 0, 86400),
    ("인공지능",        "NAVER_NEWS", None, 0, 86400),
    ("자율주행",        "NAVER_NEWS", None, 0, 86400),
    ("로봇",            "NAVER_NEWS", None, 0, 86400),
    ("부동산",          "NAVER_NEWS", None, 0, 86400),
    ("아파트",          "NAVER_NEWS", None, 0, 86400),
    ("분양",            "NAVER_NEWS", None, 0, 86400),
    ("재건축",          "NAVER_NEWS", None, 0, 86400),
    ("수출",            "NAVER_NEWS", None, 0, 86400),
    ("무역수지",        "NAVER_NEWS", None, 0, 86400),
    ("GDP",             "NAVER_NEWS", None, 0, 86400),
    ("실업률",          "NAVER_NEWS", None, 0, 86400),
    ("한국은행",        "NAVER_NEWS", None, 0, 86400),
    ("미국연준",        "NAVER_NEWS", None, 0, 86400),
    ("Fed",             "NAVER_NEWS", None, 0, 86400),
    ("엔비디아",        "NAVER_NEWS", None, 0, 86400),
    ("애플",            "NAVER_NEWS", None, 0, 86400),
    ("테슬라",          "NAVER_NEWS", None, 0, 86400),
    ("마이크로소프트",  "NAVER_NEWS", None, 0, 86400),
    ("구글",            "NAVER_NEWS", None, 0, 86400),
    ("아마존",          "NAVER_NEWS", None, 0, 86400),
    ("메타",            "NAVER_NEWS", None, 0, 86400),
    ("중국경제",        "NAVER_NEWS", None, 0, 86400),
    ("미중갈등",        "NAVER_NEWS", None, 0, 86400),
    ("관세",            "NAVER_NEWS", None, 0, 86400),
    ("반도체규제",      "NAVER_NEWS", None, 0, 86400),
    ("2차전지",         "NAVER_NEWS", None, 0, 86400),
    ("리튬",            "NAVER_NEWS", None, 0, 86400),
    ("니켈",            "NAVER_NEWS", None, 0, 86400),
    ("원자재",          "NAVER_NEWS", None, 0, 86400),
    ("유가",            "NAVER_NEWS", None, 0, 86400),
    ("원유",            "NAVER_NEWS", None, 0, 86400),
    ("천연가스",        "NAVER_NEWS", None, 0, 86400),
    ("에너지",          "NAVER_NEWS", None, 0, 86400),
    ("태양광",          "NAVER_NEWS", None, 0, 86400),
    ("풍력",            "NAVER_NEWS", None, 0, 86400),
    ("원전",            "NAVER_NEWS", None, 0, 86400),
    ("SMR",             "NAVER_NEWS", None, 0, 86400),
    ("바이오",          "NAVER_NEWS", None, 0, 86400),
    ("제약",            "NAVER_NEWS", None, 0, 86400),
    ("임상시험",        "NAVER_NEWS", None, 0, 86400),
    ("식품",            "NAVER_NEWS", None, 0, 86400),
    ("유통",            "NAVER_NEWS", None, 0, 86400),
    ("쿠팡",            "NAVER_NEWS", None, 0, 86400),
    ("이커머스",        "NAVER_NEWS", None, 0, 86400),
    ("항공",            "NAVER_NEWS", None, 0, 86400),
    ("대한항공",        "NAVER_NEWS", None, 0, 86400),
    ("아시아나",        "NAVER_NEWS", None, 0, 86400),
    ("조선",            "NAVER_NEWS", None, 0, 86400),
    ("HD현대중공업",    "NAVER_NEWS", None, 0, 86400),
    ("한화",            "NAVER_NEWS", None, 0, 86400),
    ("방산",            "NAVER_NEWS", None, 0, 86400),
    ("K방산",           "NAVER_NEWS", None, 0, 86400),
    ("게임",            "NAVER_NEWS", None, 0, 86400),
    ("엔씨소프트",      "NAVER_NEWS", None, 0, 86400),
    ("크래프톤",        "NAVER_NEWS", None, 0, 86400),
    ("한미반도체",      "NAVER_NEWS", None, 0, 86400),

    # ── DAUM_NEWS (100개) ───────────────────────────────────────────────────
    ("삼성전자",        "DAUM_NEWS",  None, 0, 86400),
    ("SK하이닉스",      "DAUM_NEWS",  None, 0, 86400),
    ("현대차",          "DAUM_NEWS",  None, 0, 86400),
    ("기아",            "DAUM_NEWS",  None, 0, 86400),
    ("네이버",          "DAUM_NEWS",  None, 0, 86400),
    ("카카오",          "DAUM_NEWS",  None, 0, 86400),
    ("LG에너지솔루션",  "DAUM_NEWS",  None, 0, 86400),
    ("셀트리온",        "DAUM_NEWS",  None, 0, 86400),
    ("포스코홀딩스",    "DAUM_NEWS",  None, 0, 86400),
    ("LG화학",          "DAUM_NEWS",  None, 0, 86400),
    ("금리",            "DAUM_NEWS",  None, 0, 86400),
    ("기준금리",        "DAUM_NEWS",  None, 0, 86400),
    ("환율",            "DAUM_NEWS",  None, 0, 86400),
    ("코스피",          "DAUM_NEWS",  None, 0, 86400),
    ("코스닥",          "DAUM_NEWS",  None, 0, 86400),
    ("반도체",          "DAUM_NEWS",  None, 0, 86400),
    ("AI반도체",        "DAUM_NEWS",  None, 0, 86400),
    ("HBM",             "DAUM_NEWS",  None, 0, 86400),
    ("배터리",          "DAUM_NEWS",  None, 0, 86400),
    ("전기차",          "DAUM_NEWS",  None, 0, 86400),
    ("2차전지",         "DAUM_NEWS",  None, 0, 86400),
    ("에코프로비엠",    "DAUM_NEWS",  None, 0, 86400),
    ("에코프로",        "DAUM_NEWS",  None, 0, 86400),
    ("엔비디아",        "DAUM_NEWS",  None, 0, 86400),
    ("테슬라",          "DAUM_NEWS",  None, 0, 86400),
    ("애플",            "DAUM_NEWS",  None, 0, 86400),
    ("챗GPT",           "DAUM_NEWS",  None, 0, 86400),
    ("인공지능",        "DAUM_NEWS",  None, 0, 86400),
    ("자율주행",        "DAUM_NEWS",  None, 0, 86400),
    ("로봇",            "DAUM_NEWS",  None, 0, 86400),
    ("부동산",          "DAUM_NEWS",  None, 0, 86400),
    ("아파트",          "DAUM_NEWS",  None, 0, 86400),
    ("재건축",          "DAUM_NEWS",  None, 0, 86400),
    ("분양",            "DAUM_NEWS",  None, 0, 86400),
    ("물가",            "DAUM_NEWS",  None, 0, 86400),
    ("인플레이션",      "DAUM_NEWS",  None, 0, 86400),
    ("유가",            "DAUM_NEWS",  None, 0, 86400),
    ("원자재",          "DAUM_NEWS",  None, 0, 86400),
    ("에너지",          "DAUM_NEWS",  None, 0, 86400),
    ("원전",            "DAUM_NEWS",  None, 0, 86400),
    ("SMR",             "DAUM_NEWS",  None, 0, 86400),
    ("태양광",          "DAUM_NEWS",  None, 0, 86400),
    ("수출",            "DAUM_NEWS",  None, 0, 86400),
    ("무역수지",        "DAUM_NEWS",  None, 0, 86400),
    ("관세",            "DAUM_NEWS",  None, 0, 86400),
    ("미중갈등",        "DAUM_NEWS",  None, 0, 86400),
    ("중국경제",        "DAUM_NEWS",  None, 0, 86400),
    ("미국연준",        "DAUM_NEWS",  None, 0, 86400),
    ("한국은행",        "DAUM_NEWS",  None, 0, 86400),
    ("KB금융",          "DAUM_NEWS",  None, 0, 86400),
    ("신한지주",        "DAUM_NEWS",  None, 0, 86400),
    ("삼성SDI",         "DAUM_NEWS",  None, 0, 86400),
    ("삼성바이오로직스","DAUM_NEWS",  None, 0, 86400),
    ("LG전자",          "DAUM_NEWS",  None, 0, 86400),
    ("SK텔레콤",        "DAUM_NEWS",  None, 0, 86400),
    ("KT",              "DAUM_NEWS",  None, 0, 86400),
    ("두산에너빌리티",  "DAUM_NEWS",  None, 0, 86400),
    ("한국전력",        "DAUM_NEWS",  None, 0, 86400),
    ("고려아연",        "DAUM_NEWS",  None, 0, 86400),
    ("방산",            "DAUM_NEWS",  None, 0, 86400),
    ("K방산",           "DAUM_NEWS",  None, 0, 86400),
    ("한화",            "DAUM_NEWS",  None, 0, 86400),
    ("HD현대중공업",    "DAUM_NEWS",  None, 0, 86400),
    ("조선",            "DAUM_NEWS",  None, 0, 86400),
    ("바이오",          "DAUM_NEWS",  None, 0, 86400),
    ("제약",            "DAUM_NEWS",  None, 0, 86400),
    ("쿠팡",            "DAUM_NEWS",  None, 0, 86400),
    ("이커머스",        "DAUM_NEWS",  None, 0, 86400),
    ("대한항공",        "DAUM_NEWS",  None, 0, 86400),
    ("현대건설",        "DAUM_NEWS",  None, 0, 86400),
    ("GS건설",          "DAUM_NEWS",  None, 0, 86400),
    ("롯데케미칼",      "DAUM_NEWS",  None, 0, 86400),
    ("리튬",            "DAUM_NEWS",  None, 0, 86400),
    ("천연가스",        "DAUM_NEWS",  None, 0, 86400),
    ("GDP",             "DAUM_NEWS",  None, 0, 86400),
    ("실업률",          "DAUM_NEWS",  None, 0, 86400),
    ("게임",            "DAUM_NEWS",  None, 0, 86400),
    ("엔씨소프트",      "DAUM_NEWS",  None, 0, 86400),
    ("크래프톤",        "DAUM_NEWS",  None, 0, 86400),
    ("현대모비스",      "DAUM_NEWS",  None, 0, 86400),
    ("삼성물산",        "DAUM_NEWS",  None, 0, 86400),
    ("하나금융지주",    "DAUM_NEWS",  None, 0, 86400),
    ("우리금융지주",    "DAUM_NEWS",  None, 0, 86400),
    ("구글",            "DAUM_NEWS",  None, 0, 86400),
    ("마이크로소프트",  "DAUM_NEWS",  None, 0, 86400),
    ("아마존",          "DAUM_NEWS",  None, 0, 86400),
    ("메타",            "DAUM_NEWS",  None, 0, 86400),
    ("원유",            "DAUM_NEWS",  None, 0, 86400),
    ("풍력",            "DAUM_NEWS",  None, 0, 86400),
    ("임상시험",        "DAUM_NEWS",  None, 0, 86400),
    ("식품",            "DAUM_NEWS",  None, 0, 86400),
    ("유통",            "DAUM_NEWS",  None, 0, 86400),
    ("항공",            "DAUM_NEWS",  None, 0, 86400),
    ("아시아나",        "DAUM_NEWS",  None, 0, 86400),
    ("니켈",            "DAUM_NEWS",  None, 0, 86400),
    ("반도체규제",      "DAUM_NEWS",  None, 0, 86400),
    ("Fed",             "DAUM_NEWS",  None, 0, 86400),
    ("한미반도체",      "DAUM_NEWS",  None, 0, 86400),
    ("삼성전기",        "DAUM_NEWS",  None, 0, 86400),

    # ── NAVER_STOCK (100개 — KOSPI/KOSDAQ 주요 종목) ────────────────────────
    ("005930", "NAVER_STOCK", "삼성전자", 0, 86400),
    ("000660", "NAVER_STOCK", "SK하이닉스", 0, 86400),
    ("373220", "NAVER_STOCK", "LG에너지솔루션", 0, 86400),
    ("005380", "NAVER_STOCK", "현대차", 0, 86400),
    ("000270", "NAVER_STOCK", "기아", 0, 86400),
    ("035420", "NAVER_STOCK", "NAVER", 0, 86400),
    ("035720", "NAVER_STOCK", "카카오", 0, 86400),
    ("068270", "NAVER_STOCK", "셀트리온", 0, 86400),
    ("005490", "NAVER_STOCK", "POSCO홀딩스", 0, 86400),
    ("051910", "NAVER_STOCK", "LG화학", 0, 86400),
    ("006400", "NAVER_STOCK", "삼성SDI", 0, 86400),
    ("207940", "NAVER_STOCK", "삼성바이오로직스", 0, 86400),
    ("105560", "NAVER_STOCK", "KB금융", 0, 86400),
    ("055550", "NAVER_STOCK", "신한지주", 0, 86400),
    ("086790", "NAVER_STOCK", "하나금융지주", 0, 86400),
    ("316140", "NAVER_STOCK", "우리금융지주", 0, 86400),
    ("028260", "NAVER_STOCK", "삼성물산", 0, 86400),
    ("017670", "NAVER_STOCK", "SK텔레콤", 0, 86400),
    ("030200", "NAVER_STOCK", "KT", 0, 86400),
    ("066570", "NAVER_STOCK", "LG전자", 0, 86400),
    ("012330", "NAVER_STOCK", "현대모비스", 0, 86400),
    ("034020", "NAVER_STOCK", "두산에너빌리티", 0, 86400),
    ("015760", "NAVER_STOCK", "한국전력", 0, 86400),
    ("247540", "NAVER_STOCK", "에코프로비엠", 0, 86400),
    ("086520", "NAVER_STOCK", "에코프로", 0, 86400),
    ("010130", "NAVER_STOCK", "고려아연", 0, 86400),
    ("000720", "NAVER_STOCK", "현대건설", 0, 86400),
    ("006360", "NAVER_STOCK", "GS건설", 0, 86400),
    ("047040", "NAVER_STOCK", "대우건설", 0, 86400),
    ("011170", "NAVER_STOCK", "롯데케미칼", 0, 86400),
    ("010950", "NAVER_STOCK", "S-Oil", 0, 86400),
    ("096770", "NAVER_STOCK", "SK이노베이션", 0, 86400),
    ("267250", "NAVER_STOCK", "HD현대중공업", 0, 86400),
    ("009540", "NAVER_STOCK", "HD한국조선해양", 0, 86400),
    ("042660", "NAVER_STOCK", "한화오션", 0, 86400),
    ("012450", "NAVER_STOCK", "한화에어로스페이스", 0, 86400),
    ("272210", "NAVER_STOCK", "한화시스템", 0, 86400),
    ("003490", "NAVER_STOCK", "대한항공", 0, 86400),
    ("020560", "NAVER_STOCK", "아시아나항공", 0, 86400),
    ("000120", "NAVER_STOCK", "CJ대한통운", 0, 86400),
    ("011200", "NAVER_STOCK", "HMM", 0, 86400),
    ("036460", "NAVER_STOCK", "한국가스공사", 0, 86400),
    ("033780", "NAVER_STOCK", "KT&G", 0, 86400),
    ("000810", "NAVER_STOCK", "삼성화재", 0, 86400),
    ("032830", "NAVER_STOCK", "삼성생명", 0, 86400),
    ("088350", "NAVER_STOCK", "한화생명", 0, 86400),
    ("000100", "NAVER_STOCK", "유한양행", 0, 86400),
    ("128940", "NAVER_STOCK", "한미약품", 0, 86400),
    ("326030", "NAVER_STOCK", "SK바이오팜", 0, 86400),
    ("145020", "NAVER_STOCK", "휴젤", 0, 86400),
    ("091990", "NAVER_STOCK", "셀트리온헬스케어", 0, 86400),
    ("251270", "NAVER_STOCK", "넷마블", 0, 86400),
    ("036570", "NAVER_STOCK", "엔씨소프트", 0, 86400),
    ("259960", "NAVER_STOCK", "크래프톤", 0, 86400),
    ("293490", "NAVER_STOCK", "카카오게임즈", 0, 86400),
    ("352820", "NAVER_STOCK", "하이브", 0, 86400),
    ("041510", "NAVER_STOCK", "에스엠", 0, 86400),
    ("035900", "NAVER_STOCK", "JYP Ent.", 0, 86400),
    ("122870", "NAVER_STOCK", "와이지엔터테인먼트", 0, 86400),
    ("196170", "NAVER_STOCK", "알테오젠", 0, 86400),
    ("323410", "NAVER_STOCK", "카카오뱅크", 0, 86400),
    ("377300", "NAVER_STOCK", "카카오페이", 0, 86400),
    ("271560", "NAVER_STOCK", "오리온", 0, 86400),
    ("097950", "NAVER_STOCK", "CJ제일제당", 0, 86400),
    ("000080", "NAVER_STOCK", "하이트진로", 0, 86400),
    ("005300", "NAVER_STOCK", "롯데칠성", 0, 86400),
    ("139480", "NAVER_STOCK", "이마트", 0, 86400),
    ("023530", "NAVER_STOCK", "롯데쇼핑", 0, 86400),
    ("069960", "NAVER_STOCK", "현대백화점", 0, 86400),
    ("282330", "NAVER_STOCK", "BGF리테일", 0, 86400),
    ("004170", "NAVER_STOCK", "신세계", 0, 86400),
    ("034730", "NAVER_STOCK", "SK", 0, 86400),
    ("003550", "NAVER_STOCK", "LG", 0, 86400),
    ("042700", "NAVER_STOCK", "한미반도체", 0, 86400),
    ("357780", "NAVER_STOCK", "솔브레인", 0, 86400),
    ("009150", "NAVER_STOCK", "삼성전기", 0, 86400),
    ("000240", "NAVER_STOCK", "한국타이어앤테크놀로지", 0, 86400),
    ("010140", "NAVER_STOCK", "삼성중공업", 0, 86400),
    ("047050", "NAVER_STOCK", "포스코인터내셔널", 0, 86400),
    ("071050", "NAVER_STOCK", "한국금융지주", 0, 86400),
    ("018260", "NAVER_STOCK", "삼성에스디에스", 0, 86400),
    ("079550", "NAVER_STOCK", "LIG넥스원", 0, 86400),
    ("047810", "NAVER_STOCK", "한국항공우주", 0, 86400),
    ("006280", "NAVER_STOCK", "녹십자", 0, 86400),
    ("000100", "NAVER_STOCK", "유한양행", 0, 86400),
    ("024110", "NAVER_STOCK", "기업은행", 0, 86400),
    ("138930", "NAVER_STOCK", "BNK금융지주", 0, 86400),
    ("000990", "NAVER_STOCK", "DB하이텍", 0, 86400),
    ("078935", "NAVER_STOCK", "GS", 0, 86400),
    ("030000", "NAVER_STOCK", "제일기획", 0, 86400),
    ("000670", "NAVER_STOCK", "영풍", 0, 86400),
    ("091810", "NAVER_STOCK", "티씨케이", 0, 86400),
    ("015230", "NAVER_STOCK", "대한재보험", 0, 86400),
    ("088980", "NAVER_STOCK", "맥쿼리인프라", 0, 86400),
    ("175330", "NAVER_STOCK", "JB금융지주", 0, 86400),
    ("192400", "NAVER_STOCK", "쿠쿠홀딩스", 0, 86400),
    ("180640", "NAVER_STOCK", "한진칼", 0, 86400),
    ("003670", "NAVER_STOCK", "포스코퓨처엠", 0, 86400),
    ("006110", "NAVER_STOCK", "삼아알미늄", 0, 86400),
    ("298040", "NAVER_STOCK", "효성중공업", 0, 86400),
    ("000150", "NAVER_STOCK", "두산", 0, 86400),
]

# ---------------------------------------------------------------------------
# 실행
# ---------------------------------------------------------------------------

def main() -> None:
    p = argparse.ArgumentParser(description="키워드 300개 초기 데이터 적재")
    p.add_argument("--dry-run", action="store_true", help="DB에 쓰지 않고 목록만 출력")
    args = p.parse_args()

    total = len(_KEYWORDS)
    portals: dict[str, int] = {}
    for _, portal, *_ in _KEYWORDS:
        portals[portal] = portals.get(portal, 0) + 1

    print(f"총 {total}개 키워드 적재 예정")
    for portal, cnt in sorted(portals.items()):
        print(f"  {portal}: {cnt}개")
    print()

    if args.dry_run:
        print("[dry-run] 실제 DB 적재 없음")
        for kw, portal, display, priority, interval in _KEYWORDS:
            label = f" ({display})" if display else ""
            print(f"  {portal:<14} {kw}{label}")
        return

    inserted = skipped = 0
    with db_context() as engine:
        with engine.begin() as conn:
            for kw, portal, display_name, priority, interval in _KEYWORDS:
                result = conn.execute(
                    text("""
                        INSERT INTO t_keyword
                            (keyword, portal_type, display_name, enabled, priority, interval_seconds)
                        VALUES
                            (:kw, :portal, :display_name, 1, :priority, :interval)
                        ON DUPLICATE KEY UPDATE
                            id = id
                    """),
                    {
                        "kw":           kw,
                        "portal":       portal.upper(),
                        "display_name": display_name,
                        "priority":     priority,
                        "interval":     interval,
                    },
                )
                if result.rowcount == 1:
                    inserted += 1
                else:
                    skipped += 1

    print(f"완료 — 신규: {inserted}개 / 중복 스킵: {skipped}개")


if __name__ == "__main__":
    main()
