import os
import re
import asyncio
import requests
from flask import Flask
from threading import Thread
from telethon import TelegramClient, events
from telethon.sessions import StringSession
from telethon.tl.functions.channels import JoinChannelRequest, LeaveChannelRequest
from PIL import Image
from pyzbar.pyzbar import decode
import io

# --- ⚙️ การตั้งค่าผ่าน Environment Variables ---
API_ID = int(os.environ.get("API_ID", 0))
API_HASH = os.environ.get("API_HASH", "")
SESSION_STRING = os.environ.get("SESSION_STRING", "")
PHONE_VOUCHER = os.environ.get("PHONE_VOUCHER", "")
DISCORD_WEBHOOK = os.environ.get("DISCORD_WEBHOOK", "")

client = TelegramClient(StringSession(SESSION_STRING), API_ID, API_HASH)
seen_vouchers = set() # ป้องกันการยิงซ้ำ

# --- 🛠️ ฟังก์ชันเสริม ---

def send_log(msg):
    print(msg)
    if DISCORD_WEBHOOK:
        try: requests.post(DISCORD_WEBHOOK, json={"content": msg})
        except: pass

def extract_codes(text):
    """ ดึงโค้ดซองจากข้อความ """
    if not text: return []
    # หาจาก URL และโค้ดดิบที่ขึ้นต้นด้วย 019
    patterns = [
        r'gift\.truemoney\.com/campaign/\?v=([a-zA-Z0-9]+)',
        r'\b(019[a-zA-Z0-9]{10,})\b'
    ]
    codes = []
    for p in patterns:
        codes.extend(re.findall(p, text))
    return list(set(codes))

async def shoot_voucher(code):
    """ ส่งคำขอแลกเงิน """
    if code in seen_vouchers: return
    seen_vouchers.add(code)
    
    send_log(f"🎯 เจอโค้ด: {code} | กำลังพยายามแลกรับ...")
    
    # ตรงนี้ให้เชื่อมต่อกับ API TrueMoney ที่คุณใช้ (เช่น wrapper ของ twapi)
    # สมมติการส่ง API:
    # response = requests.post(f"YOUR_API_ENDPOINT", data={"code": code, "phone": PHONE_VOUCHER})
    # if response.ok: send_log(f"✅ สำเร็จ! รับเงินจากซอง {code}")

# --- ⚡ โหมด 1: Real-time Listener (ยิงทันทีที่เห็น) ---

@client.on(events.NewMessage(incoming=True))
async def msg_handler(event):
    # 1. เช็คจากข้อความ
    for code in extract_codes(event.raw_text):
        await shoot_voucher(code)
    
    # 2. เช็คจากรูปภาพ QR Code
    if event.photo:
        try:
            photo_bytes = await event.download_media(file=bytes)
            img = Image.open(io.BytesIO(photo_bytes))
            for qr in decode(img):
                data = qr.data.decode('utf-8')
                for code in extract_codes(data):
                    await shoot_voucher(code)
        except Exception as e:
            print(f"QR Error: {e}")

# --- 🔍 โหมด 2: Hunter Loop (สแกนย้อนหลัง + ล่ากลุ่มใหม่) ---

async def hunter_task():
    await asyncio.sleep(10) # รอให้ Client ต่อติดก่อน
    while True:
        send_log("🔄 รอบการสแกน Hunter เริ่มทำงาน...")
        async for dialog in client.iter_dialogs():
            if dialog.is_group or dialog.is_channel:
                try:
                    # สแกนข้อความเก่า 100 ข้อความ
                    async for msg in client.iter_messages(dialog, limit=100):
                        for code in extract_codes(msg.text):
                            await shoot_voucher(code)
                        
                        # หาลิงก์กลุ่มใหม่เพื่อเข้า
                        links = re.findall(r't\.me/(\w+)', msg.text or "")
                        for link in links:
                            try:
                                await client(JoinChannelRequest(link))
                                send_log(f"✈️ เข้ากลุ่มใหม่สำเร็จ: {link}")
                                await asyncio.sleep(300) # Cooldown 5 นาที
                            except: continue
                except: continue
        
        await asyncio.sleep(3600) # สแกนรอบใหญ่ทุก 1 ชม.

# --- 🌐 Web Server สำหรับ Render & UptimeRobot ---

app = Flask('')
@app.route('/')
def home(): return "Bot Status: Online ✅"

def run_web_server():
    # Render มักจะใช้ PORT 10000 เป็นค่าเริ่มต้น
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

# --- 🚀 เริ่มต้นการทำงาน ---

async def main():
    send_log("🚀 กำลังเริ่มระบบ Hybrid Bot (Python Version)...")
    await client.start()
    
    # รันงานพร้อมกัน (Listener + Hunter)
    await asyncio.gather(
        client.run_until_disconnected(),
        hunter_task()
    )

if __name__ == "__main__":
    # รัน Web Server แยก Thread เพื่อไม่ให้ขัดจังหวะบอท
    Thread(target=run_web_server).start()
    # รันบอทหลัก
    asyncio.run(main())
    