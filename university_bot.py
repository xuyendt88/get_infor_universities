import os
import json
import logging
import requests
from bs4 import BeautifulSoup
from google import genai
import re
from datetime import datetime, timedelta
from telegraph import Telegraph
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# --- Cấu hình Logging ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[logging.StreamHandler()]
)

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID = os.environ.get("CHAT_ID")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

# --- Khởi tạo Telegraph tự động ---
telegraph = Telegraph()
try:
    telegraph.create_account(short_name='IEE_UniBot')
except Exception as e:
    logging.warning(f"Không thể khởi tạo tài khoản Telegraph (có thể đã tồn tại): {e}")

HISTORY_FILE = "sent_links.json"
RETENTION_DAYS = 45  # Giữ lịch sử link trong vòng 45 ngày

IEE_FOOTER = """----------------------------------
<b>Công ty IEE – Tư vấn du học Toàn quốc</b>
Địa chỉ: số 27 ngõ 23 Đỗ Quang, Yên Hoà, Hà Nội
Hotline: 0969.159.131
Đăng ký tư vấn Miễn phí: <a href="https://forms.gle/MuTGJFbU99rNVbyw6">https://forms.gle/MuTGJFbU99rNVbyw6</a>"""

def send_telegram_error(error_message):
    """Gửi cảnh báo lỗi trực tiếp về Telegram"""
    if not TELEGRAM_TOKEN or not CHAT_ID:
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": f"⚠️ <b>BOT CẢNH BÁO LỖI</b>\n<pre>{error_message}</pre>",
        "parse_mode": "HTML"
    }
    try:
        requests.post(url, json=payload, timeout=5)
    except Exception:
        pass

def load_sent_links():
    """Tải lịch sử link và tự động xóa các link cũ hơn RETENTION_DAYS ngày"""
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                now = datetime.now()
                filtered = {}
                
                # Tương thích ngược: Nếu file cũ là dạng list
                if isinstance(data, list):
                    now_str = now.isoformat()
                    return {link: now_str for link in data}
                
                # Định dạng mới: dict {link: timestamp_str}
                elif isinstance(data, dict):
                    for link, ts_str in data.items():
                        try:
                            ts = datetime.fromisoformat(ts_str)
                            if now - ts <= timedelta(days=RETENTION_DAYS):
                                filtered[link] = ts_str
                        except Exception:
                            # Nếu parse thời gian lỗi, bỏ qua link cũ này
                            continue
                    return filtered
        except Exception as e:
            logging.error(f"Lỗi khi đọc file lịch sử sent_links.json: {e}")
            return {}
    return {}

def save_sent_links(sent_dict):
    """Lưu lịch sử dưới dạng từ điển kèm thời gian"""
    try:
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(sent_dict, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logging.error(f"Lỗi khi ghi file lịch sử sent_links.json: {e}")

def create_robust_session():
    """Tạo requests session với cơ chế Retry tự động và Header chuẩn"""
    session = requests.Session()
    retries = Retry(
        total=3,
        backoff_factor=2,
        status_forcelist=[500, 502, 503, 504],
        raise_on_status=False
    )
    adapter = HTTPAdapter(max_retries=retries)
    session.mount('https://', adapter)
    session.mount('http://', adapter)
    
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9,vi;q=0.8",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8"
    })
    return session

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
    logging.info("Bắt đầu quét thông tin tuyển sinh từ các trường đại học...")
    sent_dict = load_sent_links()
    sent_links_set = set(sent_dict.keys())
    school_articles = {}
    
    session = create_robust_session()
    
    for school in TARGET_UNIVERSITIES:
        school_name = school["name"]
        school_url = school["url"]
        try:
            response = session.get(school_url, timeout=12)
            if response.status_code == 200:
                soup = BeautifulSoup(response.text, 'html.parser')
                count = 0
                for a_tag in soup.find_all('a', href=True):
                    title = a_tag.get_text().strip()
                    link = a_tag['href']
                    
                    if len(title) > 25:
                        if link.startswith('/'):
                            base_domain = "/".join(school_url.split("/")[:3])
                            link = base_domain + link
                        elif not link.startswith('http'):
                            continue
                            
                        if link in sent_links_set:
                            continue
                            
                        if school_name not in school_articles:
                            school_articles[school_name] = []
                        
                        if title not in [art['title'] for art in school_articles[school_name]]:
                            school_articles[school_name].append({
                                "title": title,
                                "link": link
                            })
                            count += 1
                            if count >= 2:
                                break
            else:
                logging.warning(f"Trường {school_name} phản hồi mã lỗi HTTP: {response.status_code}")
        except Exception as e:
            err_msg = f"Lỗi kết nối khi quét trường {school_name} ({school_url}): {str(e)}"
            logging.error(err_msg)
            # Không gửi thông báo lỗi nhỏ lẻ từng trường để tránh spam Telegram, 
            # nhưng log lại đầy đủ trên GitHub Actions.
            continue
            
    return school_articles, sent_dict

def generate_post_content(school_name, articles_list):
    client = genai.Client(api_key=GEMINI_API_KEY)
    
    articles_text = ""
    for art in articles_list:
        articles_text += f"- Tiêu đề: {art['title']}\n  Link gốc: {art['link']}\n"

    prompt = f"""
Dựa vào các thông tin mới từ trường đại học {school_name} dưới đây, hãy viết một bài đăng Facebook hoàn chỉnh, chi tiết và chuyên nghiệp bằng tiếng Việt để tư vấn du học.

Thông tin thô:
{articles_text}

Yêu cầu nội dung:
1. Viết vắn tắt, chi tiết, làm nổi bật thông tin tuyển sinh, học bổng hoặc sự kiện quan trọng của trường {school_name}.
2. Văn phong thu hút học sinh và phụ huynh, rõ ràng, mạch lạc.
3. Định dạng chuẩn HTML an toàn cho Telegram (dùng các thẻ như <b>, <i>, <a>, tuyệt đối không dùng dấu **).

Cấu trúc bài viết:
🎓 <b>CẬP NHẬT TUYỂN SINH: {school_name.upper()}</b> 🎓

[Nội dung chi tiết, tóm tắt rõ ràng các ý chính]
"""

    response = client.models.generate_content(
        model='gemini-2.5-flash', # Cập nhật model chuẩn nếu cần
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

        title = f"Cập nhật Tuyển sinh: {school_name}"
        response = telegraph.create_page(
            title=title,
            html_content=full_html,
            author_name="IEE Admissions Bot"
        )
        return f"https://telegra.ph{response['url']}"
    except Exception as e:
        logging.error(f"Lỗi khi tạo Telegraph page cho {school_name}: {e}")
        return None

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
        critical_err = "Lỗi nghiêm trọng: Thiếu cấu hình Secrets (TELEGRAM_TOKEN, CHAT_ID hoặc GEMINI_API_KEY)!"
        logging.error(critical_err)
        send_telegram_error(critical_err)
    else:
        try:
            schools_data, sent_dict = fetch_university_news()
            if schools_data:
                total_processed_schools = 0
                now_str = datetime.now().isoformat()
                
                for school_name, articles in schools_data.items():
                    logging.info(f"Đang xử lý bài viết cho trường: {school_name}")
                    try:
                        post_content = generate_post_content(school_name, articles)
                        formatted_post = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', post_content)
                        
                        telegraph_url = create_telegraph_page(school_name, formatted_post, articles)
                        
                        link_section = ""
                        if telegraph_url:
                            link_section = f"\n\n🔗 <b>Đọc bài viết đầy đủ & Link gốc:</b>\n👉 <a href='{telegraph_url}'>Xem tại đây</a>"

                        final_message = formatted_post + link_section + "\n\n" + IEE_FOOTER
                        
                        res = send_telegram_message(final_message)
                        if not res.get("ok"):
                            logging.error(f"Telegram API từ chối tin nhắn cho trường {school_name}: {res}")
                        
                        for art in articles:
                            sent_dict[art['link']] = now_str
                        total_processed_schools += 1
                        
                    except Exception as e:
                        logging.error(f"Lỗi khi xử lý nội dung trường {school_name}: {e}")
                
                save_sent_links(sent_dict)
                logging.info(f"Hoàn tất! Đã đẩy thành công {total_processed_schools} bài viết về Telegram.")
            else:
                logging.info("Không có thông tin tuyển sinh mới nào từ các trường.")
        except Exception as main_ex:
            err_msg = f"Bot gặp lỗi toàn cục trong quá trình chạy: {str(main_ex)}"
            logging.error(err_msg)
            send_telegram_error(err_msg)
