import imaplib
import email
from email.header import decode_header
import torch
from transformers import BertTokenizer, BertForSequenceClassification
import time
import os
import pandas as pd

# ==========================
# 1. Cấu hình
# ==========================
EMAIL_USER = "decalseri@gmail.com"
EMAIL_PASS = "mwma nfep tybx dbwl"  # App Password Gmail
IMAP_SERVER = "imap.gmail.com"
MODEL_DIR = os.getenv("MODEL_DIR", "/app/saved_model_updated")  # Đường dẫn trong container
CHECK_INTERVAL = int(os.getenv("CHECK_INTERVAL", 30))  # Mặc định 30s
LOG_FILE = "email_scan_log.csv"

# Thiết bị
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
print(f"[INFO] Đang dùng thiết bị: {device}")

# ==========================
# 2. Load model
# ==========================
print("[INFO] Đang tải mô hình...")
tokenizer = BertTokenizer.from_pretrained(MODEL_DIR)
model = BertForSequenceClassification.from_pretrained(MODEL_DIR).to(device)
model.eval()
print("[INFO] Mô hình sẵn sàng!")

# ==========================
# 3. Lưu log
# ==========================
if not os.path.exists(LOG_FILE):
    pd.DataFrame(columns=["time", "subject", "result"]).to_csv(LOG_FILE, index=False)

def save_log(subject, result):
    df = pd.DataFrame([[time.strftime("%Y-%m-%d %H:%M:%S"), subject, result]], columns=["time", "subject", "result"])
    df.to_csv(LOG_FILE, mode="a", header=False, index=False)

# ==========================
# 4. Hàm đọc email
# ==========================
processed_ids = set()

def fetch_emails(limit=10):
    try:
        mail = imaplib.IMAP4_SSL(IMAP_SERVER)
        mail.login(EMAIL_USER, EMAIL_PASS)
        mail.select("inbox")

        status, messages = mail.search(None, "ALL")  # Lấy tất cả email
        if status != "OK":
            return []

        email_ids = messages[0].split()[-limit:]  # Lấy N email mới nhất
        emails = []

        for e_id in email_ids:
            if e_id in processed_ids:
                continue
            processed_ids.add(e_id)

            _, msg_data = mail.fetch(e_id, "(RFC822)")
            for response_part in msg_data:
                if isinstance(response_part, tuple):
                    msg = email.message_from_bytes(response_part[1])
                    subject, encoding = decode_header(msg["Subject"])[0]
                    if isinstance(subject, bytes):
                        subject = subject.decode(encoding if encoding else "utf-8")

                    body = ""
                    if msg.is_multipart():
                        for part in msg.walk():
                            if part.get_content_type() == "text/plain":
                                try:
                                    body = part.get_payload(decode=True).decode()
                                except:
                                    body = ""
                                break
                    else:
                        try:
                            body = msg.get_payload(decode=True).decode()
                        except:
                            body = ""

                    emails.append((subject, body))

        mail.logout()
        return emails

    except Exception as e:
        print(f"[ERROR] Gmail lỗi: {e}")
        return []

# ==========================
# 5. Kiểm tra phishing
# ==========================
def is_phishing(subject, body):
    text = (subject + " " + body)[:500]  # Giới hạn 500 ký tự
    inputs = tokenizer(text, return_tensors="pt", truncation=True, padding=True).to(device)
    with torch.no_grad():
        outputs = model(**inputs)
    pred = torch.argmax(outputs.logits, dim=1).item()
    return pred == 1  # 1 = phishing, 0 = an toàn

# ==========================
# 6. Chạy liên tục
# ==========================
if __name__ == "__main__":
    print("[INFO] Bắt đầu quét email...")
    # Lấy 10 email mới nhất ban đầu
    emails = fetch_emails(limit=10)
    for i, (subject, body) in enumerate(emails):
        result = "⚠️ PHISHING" if is_phishing(subject, body) else "✔️ AN TOÀN"
        print(f"\nEmail #{i+1}")
        print(f"Tiêu đề: {subject}")
        print(f"Kết quả: {result}")
        save_log(subject, result)

    # Kiểm tra liên tục cho email mới
    while True:
        new_emails = fetch_emails(limit=1)  # Kiểm tra email mới nhất
        if new_emails:
            for subject, body in new_emails:
                result = "⚠️ PHISHING" if is_phishing(subject, body) else "✔️ AN TOÀN"
                print(f"\n[NEW EMAIL] Tiêu đề: {subject}")
                print(f"Kết quả: {result}")
                save_log(subject, result)
        time.sleep(CHECK_INTERVAL)
