import os
import json
import requests
from bs4 import BeautifulSoup
from google import genai
import re
from telegraph import Telegraph, upload

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID = os.environ.get("CHAT_ID")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

# --- Khởi tạo Telegraph Client ---
# Bạn có thể tạo một account mới bằng code, nhưng cách đơn giản nhất là tạo 1 lần
# bằng tay tại https://edit.telegra.ph/ và lấy short_name (author_url) điền vào đây
# để đảm bảo các bài viết được gom chung một tác giả.
TELEGRAPH_AUTHOR_URL = "https://edit.telegra.ph/University-Admissions-Bot" # Thay bằng URL tác giả của bạn
telegraph = Telegraph(access_token=None) # Nếu muốn bảo mật hơn, bạn có thể dùng access_token thay vì author_url

HISTORY_FILE = "sent_links.json"
IEE_FOOTER = """----------------------------------
<b>Công ty IEE – Tư vấn du học Toàn quốc</b>
Địa chỉ: số 27 ngõ 23 Đỗ Quang, Yên Hoà, Hà Nội
Hotline: 0969.159.131
Đăng ký tư vấn Miễn phí: <a href="https://forms.gle/MuTGJFbU99rNVbyw6">https://forms.gle/MuTGJFbU99rNVbyw6</a>"""

# --- Các hàm hỗ trợ chống trùng lặp ---
def load_sent_links():
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                return set(json.load(f))
        except Exception:
            return set()
    return set()

def save_sent_links(sent_set):
    links_list = list(sent_set)[-400:] # Tăng lịch sử lưu trữ
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(links_list, f, ensure_ascii=False, indent=2)

# --- Danh sách 50 trường (Giữ nguyên như cũ) ---
TARGET_UNIVERSITIES = [
    {"name": "MIT", "url": "https://admissions.mit.edu/"},
    {"name": "Stanford", "url": "https://admission.stanford.edu/"},
    # ... (Bổ sung đủ 50 trường vào đây)
]

def fetch_university_news():
    print("Đang quét thông tin tuyển sinh từ các trường đại học...")
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
                            if count >= 2: # Lấy tối đa 2 bài mới nhất mỗi trường
                                break
        except Exception:
            continue
            
    return school_articles

def generate_post_content_for_telegraph(school_name, articles_list):
    """
    Yêu cầu AI viết nội dung chi tiết, trình bày đẹp bằng HTML để đẩy lên Telegraph
    """
    client = genai.Client(api_key=GEMINI_API_KEY)
    
    articles_text = ""
    for art in articles_list:
        articles_text += f"- Tiêu đề: {art['title']}\n  Link gốc: {art['link']}\n"

    prompt = f"""
Viết một bài đăng blog chi tiết, chuyên nghiệp bằng tiếng Việt cho tư vấn du học, dựa trên các thông tin mới nhất từ trường đại học {school_name} dưới đây.

Nội dung thô cần tổng hợp:
{articles_text}

Yêu cầu định dạng HTML (chỉ dùng thẻ <p>, <strong>, <a>):
1. Một tiêu đề bài viết hấp dẫn.
2. Nội dung chi tiết, phân tích các ý chính, tóm tắt rõ ràng (không dùng dấu **).
3. Đặt liên kết gốc vào các từ khóa phù hợp bằng thẻ <a href="link_gốc">...</a>.
4. Kết thúc bài viết bằng câu kêu gọi hành động (Call-to-Action) chuyên nghiệp.
"""

    response = client.models.generate_content(
        model='gemini-3.6-flash',
        contents=prompt,
    )
    # Lọc thẻ h1 không cần thiết từ output Gemini nếu có
    return re.sub(r'<h1>.*?</h1>', '', response.text.strip(), flags=re.DOTALL)

def create_telegraph_page(school_name, content_html):
    """
    Tạo một trang trên Telegra.ph và trả về URL
    """
    try:
        # Tạo account mới lần đầu nếu chưa có token
        if not os.environ.get("TELEGRAPH_ACCESS_TOKEN"):
             # Bạn cần tạo bằng tay một lần tại https://edit.telegra.ph/
             # và set TELEGRAPH_ACCESS_TOKEN vào GitHub Secrets
             print("Lỗi: Thiếu TELEGRAPH_ACCESS_TOKEN trong Secrets!")
             return None
        
        telegraph.access_token = os.environ.get("TELEGRAPH_ACCESS_TOKEN")
        
        title = f"Cập nhật Tuyển sinh & Học bổng: {school_name}"
        response = telegraph.create_page(
            title=title,
            html_content=content_html,
            author_name="University Admissions Bot",
            author_url=TELEGRAPH_AUTHOR_URL
        )
        return response['url']
    except Exception as e:
        print(f"Lỗi khi tạo Telegraph page cho {school_name}: {e}")
        return None

def send_telegram_message(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": False # Cho phép hiển thị preview (ảnh, tiêu đề)
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
                    # 1. Yêu cầu AI viết nội dung chi tiết, đẹp mắt cho Telegraph
                    content_html = generate_post_content_for_telegraph(school_name, articles)
                    
                    # 2. Tạo trang Telegra.ph và lấy URL
                    telegraph_url = create_telegraph_page(school_name, content_html)
                    
                    if telegraph_url:
                        # 3. Soạn tin nhắn Telegram chỉ chứa link Telegraph và footer IEE
                        final_message = (
                            f"🎓 <b>CẬP NHẬT TUYỂN SINH & ĐẠI HỌC QUỐC TẾ</b> 🎓\n\n"
                            f"Đã có thông tin mới nhất từ <b>{school_name.upper()}</b>. Bấm vào link bên dưới để xem chi tiết:\n\n"
                            f"👉 <a href='{telegraph_url}'>Xem thông tin chi tiết tại đây</a>\n\n"
                            f"{IEE_FOOTER}"
                        )
                        
                        # Gửi tin nhắn
                        send_telegram_message(final_message)
                        
                        # 4. Đánh dấu các link gốc đã gửi để chống trùng lặp
                        for art in articles:
                            sent_set.add(art['link'])
                        total_processed_schools += 1
                    
                except Exception as e:
                    print(f"Lỗi khi xử lý {school_name}: {e}")
            
            save_sent_links(sent_set)
            print(f"Hoàn tất! Đã tạo {total_processed_schools} trang Telegraph và gửi về Telegram.")
        else:
            print("Không có thông tin tuyển sinh mới nào từ các trường.")
