import os
import json
import requests
from bs4 import BeautifulSoup
from google import genai
import re

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID = os.environ.get("CHAT_ID")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

HISTORY_FILE = "sent_links.json"

IEE_FOOTER = """----------------------------------
Công ty IEE – Tư vấn du học Toàn quốc
Địa chỉ: số 27 ngõ 23 Đỗ Quang, Yên Hoà, Hà Nội
Hotline: 0969.159.131
Đăng ký tư vấn Miễn phí: https://forms.gle/MuTGJFbU99rNVbyw6"""

def load_sent_links():
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                return set(json.load(f))
        except Exception:
            return set()
    return set()

def save_sent_links(sent_set):
    links_list = list(sent_set)[-400:]
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(links_list, f, ensure_ascii=False, indent=2)

TARGET_UNIVERSITIES = [
    {"name": "MIT", "url": "https://admissions.mit.edu/"},
    {"name": "Stanford", "url": "https://admission.stanford.edu/"},
    {"name": "Harvard", "url": "https://college.harvard.edu/admissions"},
    {"name": "Oxford", "url": "https://www.ox.ac.uk/admissions/undergraduate"},
    {"name": "Cambridge", "url": "https://www.undergraduate.study.cam.ac.uk/"},
    {"name": "Caltech", "url": "https://www.caltech.edu/admissions"},
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
    {"name": "TUM", "url": "https://www.tum.de/en/studies/application"}
]

def fetch_university_news():
    sent_links = load_sent_links()
    school_articles = {}
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
                    if len(title) > 25:
                        if link.startswith('/'):
                            base_domain = "/".join(school["url"].split("/")[:3])
                            link = base_domain + link
                        elif not link.startswith('http'):
                            continue
                        if link in sent_links:
                            continue
                        if school["name"] not in school_articles:
                            school_articles[school["name"]] = []
                        if title not in [art['title'] for art in school_articles[school["name"]]]:
                            school_articles[school["name"]].append({
                                "title": title,
                                "link": link
                            })
                            count += 1
                            if count >= 2:
                                break
        except Exception:
            continue
    return school_articles

def generate_post_content(school_name, articles_list):
    client = genai.Client(api_key=GEMINI_API_KEY)
    articles_text = ""
    for art in articles_list:
        articles_text += f"- Tiêu đề: {art['title']}\n  Link gốc: {art['link']}\n"

    # Đã cải tiến Prompt để AI tự sinh tiêu đề linh hoạt bám sát nội dung từng trường
    prompt = f"""
Dựa vào các thông tin mới từ trường đại học {school_name} dưới đây, hãy viết một bài đăng Facebook hoàn chỉnh, chi tiết và chuyên nghiệp bằng tiếng Việt để tư vấn du học.

Thông tin thô:
{articles_text}

Yêu cầu nội dung:
1. SÁNG TẠO TIÊU ĐỀ: Dòng đầu tiên phải là một tiêu đề thật thu hút, linh hoạt bám sát nội dung chính của bài (ví dụ: liên quan đến học bổng, ngành hot, hoặc sự kiện tuyển sinh cụ thể của trường {school_name}), viết bằng chữ IN HOA, không dùng tiêu đề chung chung.
2. Viết vắn tắt, chi tiết, làm nổi bật thông tin tuyển sinh, học bổng hoặc sự kiện quan trọng.
3. Văn phong thu hút học sinh và phụ huynh, rõ ràng, mạch lạc.
4. KHÔNG sử dụng bất kỳ thẻ HTML hay định dạng markdown (như **, *, <a>) nào trong văn bản thuần túy này.

Cấu trúc bài viết:
[TIÊU ĐỀ LINH HOẠT VỀ TRƯỜNG {school_name.upper()}]

[Nội dung chi tiết, tóm tắt rõ ràng các ý chính]
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
        "disable_web_page_preview": False
    }
    response = requests.post(url, json=payload)
    return response.json()

if __name__ == "__main__":
    if not TELEGRAM_TOKEN or not GEMINI_API_KEY or not CHAT_ID:
        print("Lỗi: Thiếu cấu hình Secrets!")
    else:
        schools_data = fetch_university_news()
        if schools_data:
            sent_set = load_sent_links()
            total_processed_schools = 0
            
            for school_name, articles in schools_data.items():
                print(f"Đang xử lý bài viết cho trường: {school_name}")
                try:
                    post_content = generate_post_content(school_name, articles)
                    
                    # Lấy link gốc đầu tiên làm link preview chính cho bài viết Facebook
                    primary_link = articles[0]['link'] if articles else TARGET_UNIVERSITIES[0]['url']
                    link_section = f"\n\nLink chi tiết & Đọc thêm:\n{primary_link}"

                    final_message = post_content + link_section + "\n\n" + IEE_FOOTER
                    
                    send_telegram_message(final_message)
                    
                    for art in articles:
                        sent_set.add(art['link'])
                    total_processed_schools += 1
                    
                except Exception as e:
                    print(f"Lỗi khi xử lý {school_name}: {e}")
            
            save_sent_links(sent_set)
            print(f"Hoàn tất! Đã đẩy {total_processed_schools} bài viết chi tiết về Telegram.")
        else:
            print("Không có thông tin tuyển sinh mới nào từ các trường.")
