import os
import requests
from bs4 import BeautifulSoup
from google import genai
import re

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID = os.environ.get("CHAT_ID")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

# Danh sách trang tin tức / tuyển sinh mục tiêu (Ví dụ mẫu các trường top đầu)
TARGET_UNIVERSITIES = [
    {"name": "MIT Admissions", "url": "https://admissions.mit.edu/"},
    {"name": "Stanford Admission", "url": "https://admission.stanford.edu/"},
    {"name": "Harvard Undergraduate", "url": "https://college.harvard.edu/admissions"},
    {"name": "Oxford Admissions", "url": "https://www.ox.ac.uk/admissions/undergraduate"},
    {"name": "Cambridge Admission", "url": "https://www.undergraduate.study.cam.ac.uk/"},
    {"name": "NUS Admissions", "url": "https://www.nus.edu.sg/oam/"},
    {"name": "NTU Admissions", "url": "https://www.ntu.edu.sg/admissions"},
    {"name": "Melbourne Study", "url": "https://study.unimelb.edu.au/"}
]

def fetch_university_news():
    """Cào tiêu đề và link từ các trang tuyển sinh/tin tức đại học"""
    print("Đang quét thông tin từ các trường đại học...")
    all_articles = []
    seen_titles = set()
    
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    
    for school in TARGET_UNIVERSITIES:
        try:
            response = requests.get(school["url"], headers=headers, timeout=10)
            if response.status_code == 200:
                soup = BeautifulSoup(response.text, 'html.parser')
                
                # Tìm các thẻ chứa tiêu đề và link bài viết (tùy cấu trúc web từng trường có thể tinh chỉnh selector)
                count = 0
                for a_tag in soup.find_all('a', href=True):
                    title = a_tag.get_text().strip()
                    link = a_tag['href']
                    
                    # Lọc sơ bộ tiêu đề có độ dài hợp lý và tránh trùng lặp
                    if len(title) > 30 and title not in seen_titles:
                        # Chuẩn hóa link tuyệt đối nếu link là tương đối (relative)
                        if link.startswith('/'):
                            # Cần ghép với domain gốc nếu cần, ở đây giả lập đơn giản
                            base_domain = "/".join(school["url"].split("/")[:3])
                            link = base_domain + link
                        elif not link.startswith('http'):
                            continue
                            
                        seen_titles.add(title)
                        all_articles.append({
                            "source": school["name"],
                            "title": title,
                            "link": link
                        })
                        count += 1
                        if count >= 2: # Lấy tối đa 2 bài mỗi trường
                            break
        except Exception as e:
            print(f"Lỗi khi cào {school['name']}: {e}")
            
    return all_articles

def analyze_admissions_with_gemini(articles_list):
    """Sử dụng Gemini để lọc tin tuyển sinh/học bổng quan trọng"""
    client = genai.Client(api_key=GEMINI_API_KEY)
    
    news_text = ""
    for idx, art in enumerate(articles_list):
        news_text += f"[{idx+1}] {art['source']}: {art['title']} ({art['link']})\n"

    prompt = f"""
Nhiệm vụ của bạn là rà soát các tiêu đề và nội dung bài viết từ trang tuyển sinh của các trường đại học lớn. Hãy tìm và chọn ra các thông tin mới nhất, quan trọng nhất liên quan đến:
1. Hạn chót nộp hồ sơ (Application Deadlines).
2. Thay đổi tiêu chí xét tuyển, điểm chuẩn, chứng chỉ yêu cầu (SAT, IELTS, TOEFL...).
3. Học bổng mới, hỗ trợ tài chính (Financial Aid / Scholarships) cho sinh viên quốc tế.

Danh sách nguồn:
{news_text}

Nếu có thông tin phù hợp, hãy tổng hợp theo chuẩn HTML sau (không dùng markdown **):
🎓 <b>BẢN TIN TUYỂN SINH & HỌC BỔNG QUỐC TẾ</b> 🎓

───────────────
<b>[Tên trường] [Tiêu đề tin ngắn gọn]</b>
- Nội dung: [Tóm tắt chi tiết 1-2 câu]
- Lưu ý/Deadline: [Mốc thời gian hoặc điều kiện cần nhớ]
- Link: <a href="link_gốc">Xem chi tiết</a>

Nếu tuyệt đối không có thông tin nào liên quan đến tuyển sinh/học bổng trong danh sách trên, hãy trả về ngắn gọn: "Hiện tại chưa có cập nhật mới về tuyển sinh từ các nguồn đã quét."
"""
    
    response = client.models.generate_content(
        model='gemini-3.6-flash', # Hoặc model flash phù hợp
        contents=prompt,
    )
    raw_text = response.text
    return re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', raw_text)

def send_telegram_message(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": message,
        "parse_mode": "HTML"
    }
    response = requests.post(url, json=payload)
    return response.json()

if __name__ == "__main__":
    if not TELEGRAM_TOKEN or not GEMINI_API_KEY or not CHAT_ID:
        print("Lỗi: Thiếu cấu hình Secrets!")
    else:
        articles = fetch_university_news()
        if articles:
            print(f"Đã lấy được {len(articles)} bài. Đang gọi AI xử lý...")
            final_analysis = analyze_admissions_with_gemini(articles)
            result = send_telegram_message(final_analysis)
            print("Đã gửi bản tin tuyển sinh thành công!", result)
        else:
            print("Không thu thập được dữ liệu.")
