import os
import json
import requests
from bs4 import BeautifulSoup
from google import genai
import re

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID = os.environ.get("CHAT_ID")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

# File lưu vết các link đã gửi để tránh gửi lặp lại
HISTORY_FILE = "sent_links.json"

def load_sent_links():
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                return set(json.load(f))
        except Exception:
            return set()
    return set()

def save_sent_links(sent_set):
    # Giữ lại tối đa 200 link gần nhất để file không quá lớn
    links_list = list(sent_set)[-200:]
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(links_list, f, ensure_ascii=False, indent=2)

# Danh sách chuẩn 50 trường đại học hàng đầu thế giới
TARGET_UNIVERSITIES = [
    {"name": "MIT", "url": "https://admissions.mit.edu/"},
    {"name": "Stanford", "url": "https://admission.stanford.edu/"},
    {"name": "Harvard", "url": "https://college.harvard.edu/admissions"},
    {"name": "Oxford", "url": "https://www.ox.ac.uk/admissions/undergraduate"},
    {"name": "Cambridge", "url": "https://www.undergraduate.study.cam.ac.uk/"},
    {"name": "Caltech", "url": "https://www.caltech.edu/admissions"},
    {"name": "ETH Zurich", "url": "https://ethz.ch/en/studies/bachelor/application.html"},
    {"name": "NUS", "url": "https://www.nus.edu.sg/oam/"},
    {"name": "NTU", "url": "https://www.ntu.edu.sg/admissions"},
    {"name": "UCL", "url": "https://www.ucl.ac.uk/prospective-students/"},
    {"name": "Imperial College London", "url": "https://www.imperial.ac.uk/study/"},
    {"name": "University of Chicago", "url": "https://collegeadmissions.uchicago.edu/"},
    {"name": "UPenn", "url": "https://admissions.upenn.edu/"},
    {"name": "Princeton", "url": "https://admission.princeton.edu/"},
    {"name": "Yale", "url": "https://admissions.yale.edu/"},
    {"name": "Cornell", "url": "https://admissions.cornell.edu/"},
    {"name": "Columbia", "url": "https://undergrad.admissions.columbia.edu/"},
    {"name": "UC Berkeley", "url": "https://admissions.berkeley.edu/"},
    {"name": "UCLA", "url": "https://admission.ucla.edu/"},
    {"name": "University of Melbourne", "url": "https://study.unimelb.edu.au/"},
    {"name": "UNSW Sydney", "url": "https://www.unsw.edu.au/study"},
    {"name": "University of Sydney", "url": "https://www.sydney.edu.au/study.html"},
    {"name": "ANU", "url": "https://www.anu.edu.au/study"},
    {"name": "Monash University", "url": "https://www.monash.edu/study"},
    {"name": "University of Queensland", "url": "https://study.uq.edu.au/"},
    {"name": "University of Tokyo", "url": "https://www.u-tokyo.ac.jp/en/admissions/index.html"},
    {"name": "Seoul National University", "url": "https://en.snu.ac.kr/admission/index.html"},
    {"name": "Peking University", "url": "https://english.pku.edu.cn/admissions/index.html"},
    {"name": "Tsinghua University", "url": "https://www.tsinghua.edu.cn/en/Admissions1.htm"},
    {"name": "University of Toronto", "url": "https://future.utoronto.ca/"},
    {"name": "McGill University", "url": "https://www.mcgill.ca/study/"},
    {"name": "UBC", "url": "https://you.ubc.ca/"},
    {"name": "EPFL", "url": "https://www.epfl.ch/education/bachelor/en/welcome-bachelor-students/"},
    {"name": "King's College London", "url": "https://www.kcl.ac.uk/study"},
    {"name": "LSE", "url": "https://www.lse.ac.uk/study"},
    {"name": "University of Edinburgh", "url": "https://www.ed.ac.uk/studying"},
    {"name": "University of Manchester", "url": "https://www.manchester.ac.uk/study/"},
    {"name": "Johns Hopkins", "url": "https://apply.jhu.edu/"},
    {"name": "Northwestern", "url": "https://admissions.northwestern.edu/"},
    {"name": "UMich", "url": "https://admissions.umich.edu/"},
    {"name": "HKU", "url": "https://hku.hk/admissions/"},
    {"name": "CUHK", "url": "https://www.cuhk.edu.hk/english/admissions/index.html"},
    {"name": "HKUST", "url": "https://join.ust.hk/"},
    {"name": "TU Delft", "url": "https://www.tudelft.nl/en/education/admission-and-application"},
    {"name": "University of Amsterdam", "url": "https://www.uva.nl/en/education/bachelors/bachelors.html"},
    {"name": "TUM", "url": "https://www.tum.de/en/studies/application"},
    {"name": "University of Sydney", "url": "https://www.sydney.edu.au/"},
    {"name": "Fudan University", "url": "https://iso.fudan.edu.cn/isoenglish/main.htm"},
    {"name": "Shanghai Jiao Tong", "url": "https://en.sjtu.edu.cn/study/admission/"},
    {"name": "Zhejiang University", "url": "http://iczu.zju.edu.cn/english/redir.php?catalog_id=111"}
]

def fetch_university_news():
    print("Đang quét thông tin tuyển sinh từ 50 trường đại học...")
    sent_links = load_sent_links()
    all_articles = []
    seen_titles = set()
    
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    
    for school in TARGET_UNIVERSITIES:
        try:
            response = requests.get(school["url"], headers=headers, timeout=8)
            if response.status_code == 200:
                soup = BeautifulSoup(response.text, 'html.parser')
                count = 0
                for a_tag in soup.find_all('a', href=True):
                    title = a_tag.get_text().strip()
                    link = a_tag['href']
                    
                    if len(title) > 25 and title not in seen_titles:
                        if link.startswith('/'):
                            base_domain = "/".join(school["url"].split("/")[:3])
                            link = base_domain + link
                        elif not link.startswith('http'):
                            continue
                            
                        # Bỏ qua nếu link này đã gửi trước đó
                        if link in sent_links:
                            continue
                            
                        seen_titles.add(title)
                        all_articles.append({
                            "source": school["name"],
                            "title": title,
                            "link": link
                        })
                        count += 1
                        if count >= 2: # Lấy tối đa 2 bài mới mỗi trường
                            break
        except Exception as e:
            # Bỏ qua lỗi kết nối riêng lẻ của từng trường để bot không bị dừng giữa chừng
            continue
            
    return all_articles[:15] # Giới hạn tối đa 15 bài mới nhất gửi cho AI

def analyze_admissions_with_gemini(articles_list):
    client = genai.Client(api_key=GEMINI_API_KEY)
    
    news_text = ""
    for idx, art in enumerate(articles_list):
        news_text += f"[{idx+1}] {art['source']}: {art['title']} ({art['link']})\n"

    prompt = f"""
Nhiệm vụ của bạn là rà soát các thông báo từ trang tuyển sinh đại học. Hãy chọn lọc các thông tin quan trọng nhất liên quan đến:
1. Hạn chót nộp hồ sơ (Application Deadlines).
2. Thay đổi tiêu chí xét tuyển, điểm chuẩn, chứng chỉ (SAT, IELTS...).
3. Học bổng mới hoặc hỗ trợ tài chính cho sinh viên quốc tế.

Danh sách:
{news_text}

Nếu có thông tin phù hợp, hãy tổng hợp theo chuẩn HTML sau (không dùng markdown **):
🎓 <b>BẢN TIN TUYỂN SINH & HỌC BỔNG QUỐC TẾ</b> 🎓

───────────────
<b>[Tên trường] [Tiêu đề tin ngắn gọn]</b>
- Nội dung: [Tóm tắt chi tiết 1-2 câu]
- Lưu ý/Deadline: [Mốc thời gian hoặc điều kiện cần nhớ]
- Link: <a href="link_gốc">Xem chi tiết</a>

Nếu tuyệt đối không có thông tin tuyển sinh/học bổng nào đáng chú ý, hãy trả về đúng một dòng: "NO_NEWS"
"""
    
    response = client.models.generate_content(
        model='gemini-3.6-flash',
        contents=prompt,
    )
    return response.text.strip()

def send_telegram_message(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": True
    }
    response = requests.post(url, json=payload)
    return response.json()

if __name__ == "__main__":
    if not TELEGRAM_TOKEN or not GEMINI_API_KEY or not CHAT_ID:
        print("Lỗi: Thiếu cấu hình Secrets!")
    else:
        articles = fetch_university_news()
        if articles:
            print(f"Đã lọc được {len(articles)} bài viết mới. Đang gọi AI xử lý...")
            analysis_result = analyze_admissions_with_gemini(articles)
            
            if "NO_NEWS" not in analysis_result:
                formatted_msg = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', analysis_result)
                send_telegram_message(formatted_msg)
                
                # Lưu lại các link đã gửi để không bị lặp lại lần sau
                sent_set = load_sent_links()
                for art in articles:
                    sent_set.add(art['link'])
                save_sent_links(sent_set)
                print("Đã gửi bản tin tuyển sinh và cập nhật lịch sử thành công!")
            else:
                print("Không có thông tin tuyển sinh mới cần gửi.")
        else:
            print("Không thu thập được bài viết mới nào.")
