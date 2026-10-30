import os
import json
import requests
from bs4 import BeautifulSoup
from google import genai
import re
from telegraph import Telegraph

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID = os.environ.get("CHAT_ID")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

# --- Khởi tạo Telegraph tự động ---
telegraph = Telegraph()
try:
    telegraph.create_account(short_name='IEE_UniBot')
except Exception:
    pass

HISTORY_FILE = "sent_links.json"

# Chuẩn hóa nhận diện thương hiệu IEE (Logo chuẩn & Slogan)
IEE_FOOTER = """----------------------------------
<b>🏢 CÔNG TY TƯ VẤN DU HỌC IEE</b>
🎨 <i>Thức tỉnh tiềm năng – Chắp cánh ước mơ du học</i>[cite: 8]
📍 Địa chỉ: Số 27 ngõ 23 Đỗ Quang, Yên Hoà, Cầu Giấy, Hà Nội
 hotline: 0969.159.131
🚀 Đăng ký tư vấn 1-1 Miễn phí: <a href="https://forms.gle/MuTGJFbU99rNVbyw6">https://forms.gle/MuTGJFbU99rNVbyw6</a>"""

def load_sent_links():
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                return set(json.load(f))
        except Exception:
            return set()
    return set()

def save_sent_links(sent_set):
    links_list = list(sent_set)[-500:]
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(links_list, f, ensure_ascii=False, indent=2)

# Danh sách đầy đủ 50 trường đại học hàng đầu thế giới
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
    {"name": "TUM", "url": "https://www.tum.de/en/studies/application"},
    {"name": "ETH Zurich", "url": "https://ethz.ch/en/studies/bachelor/application.html"},
    {"name": "EPFL", "url": "https://www.epfl.ch/education/bachelor/en/admission-immatriculation/"},
    {"name": "Duke University", "url": "https://admissions.duke.edu/"},
    {"name": "Brown University", "url": "https://admission.brown.edu/"},
    {"name": "Carnegie Mellon", "url": "https://www.admission.cs.cmu.edu/"},
    {"name": "NYU", "url": "https://www.nyu.edu/admissions/undergraduate-admissions.html"},
    {"name": "KAUST", "url": "https://admissions.kaust.edu.sa/"}
]

def fetch_university_news():
    print(f"Đang quét thông tin từ {len(TARGET_UNIVERSITIES)} trường đại học hàng đầu...")
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
        articles_text += f"- Tiêu đề bài viết gốc: {art['title']}\n  Link: {art['link']}\n"

    prompt = f"""
Dựa vào các thông tin mới từ trường đại học {school_name} dưới đây, hãy viết một bài đăng hoàn chỉnh, chuyên nghiệp bằng tiếng Việt để tư vấn du học.

Thông tin thô:
{articles_text}

Yêu cầu nội dung:
1. Đặt tiêu đề bài viết thật nổi bật, đi thẳng vào trọng tâm nội dung chuyên môn (ví dụ về học bổng, chính sách xét tuyển, nghiên cứu khoa học đột phá, hoặc đời sống sinh viên), TUYỆT ĐỐI KHÔNG dùng cụm từ chung chung như "CẬP NHẬT TUYỂN SINH:".
2. Tóm tắt chi tiết, sắc sảo, làm nổi bật giá trị cốt lõi giúp học sinh định hướng hồ sơ du học.
3. Định dạng chuẩn HTML an toàn cho Telegram (dùng các thẻ như <b>, <i>, <a>, tuyệt đối không dùng dấu **).

Cấu trúc trả về:
🎓 <b>[TIÊU ĐỀ ĐẶC TRƯNG, ĐÁNH TRÚNG TRỌNG TÂM CỦA {school_name.upper()}]</b> 🎓

[Nội dung chi tiết tóm tắt các ý chính]
"""

    response = client.models.generate_content(
        model='gemini-2.5-flash',
        contents=prompt,
    )
    return response.text.strip()

def create_telegraph_page(school_name, content_html, articles_list):
    try:
        full_html = content_html.replace('\n', '<br>')
        full_html += "<br><br><h3>Các liên kết tham khảo chi tiết:</h3><ul>"
        for art in articles_list:
            full_html += f"<li><a href='{art['link']}'>{art['title']}</a></li>"
        full_html += "</ul>"

        title = f"{school_name}: {articles_list[0]['title'] if articles_list else 'Thông tin mới'}"
        response = telegraph.create_page(
            title=title,
            html_content=full_html,
            author_name="IEE Admissions Bot"
        )
        return f"https://telegra.ph{response['url']}"
    except Exception as e:
        print(f"Lỗi khi tạo Telegraph page cho {school_name}: {e}")
        return None

def send_telegram_photo_message(photo_path, caption_message):
    """Gửi ảnh logo/banner từ thư mục gốc kèm nội dung bài viết lên Telegram"""
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto"
    
    if os.path.exists(photo_path):
        with open(photo_path, 'rb') as photo_file:
            payload = {
                "chat_id": CHAT_ID,
                "caption": caption_message,
                "parse_mode": "HTML"
            }
            files = {"photo": photo_file}
            response = requests.post(url, data=payload, files=files)
            return response.json()
    else:
        # Fallback gửi tin nhắn văn bản nếu không tìm thấy ảnh
        url_text = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        payload = {
            "chat_id": CHAT_ID,
            "text": caption_message,
            "parse_mode": "HTML"
        }
        return requests.post(url_text, json=payload).json()

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
                    formatted_post = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', post_content)
                    
                    telegraph_url = create_telegraph_page(school_name, formatted_post, articles)
                    
                    link_section = ""
                    if telegraph_url:
                        link_section = f"\n\n🔗 <b>Đọc bài viết đầy đủ & Link gốc:</b>\n👉 <a href='{telegraph_url}'>Xem tại đây</a>"

                    video_section = f"\n\n🎬 <b>Video ngắn tổng hợp nội dung {school_name}:</b>\n<i>(Đang render video tự động đính kèm thương hiệu IEE...)</i>"

                    final_message = formatted_post + link_section + video_section + "\n\n" + IEE_FOOTER
                    
                    # Sử dụng file ảnh logo đã upload lên thư mục gốc
                    logo_filename = "tu_van_du_hoc_logo.jpg"
                    send_telegram_photo_message(logo_filename, final_message)
                    
                    for art in articles:
                        sent_set.add(art['link'])
                    total_processed_schools += 1
                    
                except Exception as e:
                    print(f"Lỗi khi xử lý {school_name}: {e}")
            
            save_sent_links(sent_set)
            print(f"Hoàn tất! Đã quét và đẩy tin từ {total_processed_schools} trường top đầu về Telegram kèm ảnh logo.")
        else:
            print("Không có thông tin tuyển sinh mới nào từ các trường.")
