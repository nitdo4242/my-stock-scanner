import json
import os
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from bs4 import BeautifulSoup
import time
import gspread
from google.oauth2.service_account import Credentials

# --- 1, 2단계는 이전과 동일합니다 ---

def save_for_dashboard(data):
    print("\n" + "🖥️"*15)
    print("  3단계: HTML 대시보드용 데이터 생성 중...  ")
    print("🖥️"*15)
    
    dashboard_list = []
    for item in data:
        raw_price = item[1] # 예: "21억 8000만"
        price_val = 0
        
        try:
            # [정밀 세척 로직]
            clean_text = raw_price.replace(',', '').strip() # 쉼표 제거
            
            # 1. '억' 단위 처리
            if '억' in clean_text:
                parts = clean_text.split('억')
                # '억' 앞부분 (예: "21" -> 210000000)
                if parts[0].strip():
                    price_val += int(parts[0].strip()) * 100000000
                
                # '억' 뒷부분 (예: " 8000만" -> 80000000)
                remainder = parts[1].replace('만', '').strip()
                if remainder:
                    price_val += int(remainder) * 10000
            
            # 2. '만' 단위만 있는 경우 처리 (예: "8000만")
            elif '만' in clean_text:
                million_part = clean_text.replace('만', '').strip()
                if million_part:
                    price_val += int(million_part) * 10000  # ✅ 10000 곱하기 추가
                    
            print(f"📊 변환 결과: {raw_price} -> {price_val:,}원 ({price_val//10000}만원)")

        except Exception as e:
            print(f"⚠️ 가격 변환 중 오류 (데이터 무시): {raw_price} -> {e}")
            continue

        dashboard_list.append({
            "name": item[0],
            "price_text": raw_price,
            "price_val": price_val,
            "price_man": price_val // 10000  # 만원 단위로도 저장
        })
    
    # 파일 저장
    with open('data.js', 'w', encoding='utf-8') as f:
        f.write(f"const crawledData = {json.dumps(dashboard_list, ensure_ascii=False)};")
    print(f"✅ 'data.js' 생성 완료! (총 {len(dashboard_list)}건)")

# --- 메인 실행부 ---
if __name__ == "__main__":
    # 반포자이(1001428) 또는 다른 아파트 번호로 테스트
    result = get_kb_data('1001428')
    
    if result:
        upload_to_google_sheet(result)
        save_for_dashboard(result)
        print("\n🎉 모든 업데이트가 끝났습니다. 이제 대시보드 파일을 열어보세요!")
