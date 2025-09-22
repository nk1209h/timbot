import os
import json
import requests
from fastapi import FastAPI, Request, HTTPException
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import (
    MessageEvent, TextMessage, TextSendMessage, FlexSendMessage
)

# ------------------------------
#   基本設定
# ------------------------------
app = FastAPI()

LINE_CHANNEL_SECRET = os.getenv("LINE_CHANNEL_SECRET")
LINE_ACCESS_TOKEN = os.getenv("LINE_ACCESS_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

line_bot_api = LineBotApi(LINE_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)

DATA_PATH = "qa_data"  # JSON & TXT 存放資料夾

# ------------------------------
#   載入 role.json
# ------------------------------
with open("role.json", "r", encoding="utf-8") as f:
    role_data = json.load(f)

# ------------------------------
#   Webhook
# ------------------------------
@app.post("/webhook")
async def callback(request: Request):
    signature = request.headers.get("X-Line-Signature")
    body = await request.body()
    body_text = body.decode("utf-8")

    try:
        handler.handle(body_text, signature)
    except InvalidSignatureError:
        raise HTTPException(status_code=400, detail="Invalid signature")
    return "OK"

# ------------------------------
#   處理使用者訊息
# ------------------------------
@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    user_text = event.message.text.strip()

    # ✅ QA 指令
    if user_text.startswith("/qa"):
        parts = user_text.split()
        filename = parts[1] if len(parts) > 1 else "main"
        if not filename.endswith(".json"):
            filename += ".json"
        success = handle_qa(event, filename, user_text)
        if not success:
            role = choose_role(user_text)
            gpt_reply = call_openai(user_text, role=role)
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=gpt_reply))
        return

    # ✅ 一般情況 → 自動選角色後丟 GPT
    role = choose_role(user_text)
    gpt_reply = call_openai(user_text, role=role)
    line_bot_api.reply_message(event.reply_token, TextSendMessage(text=gpt_reply))

# ------------------------------
#   QA 功能
# ------------------------------
def handle_qa(event, filename: str, user_text: str) -> bool:
    filepath = os.path.join(DATA_PATH, filename)

    if not os.path.exists(filepath):
        warning_msg = TextSendMessage(text="⚠️ 資訊建構中，為您呼叫 GPT 來補充回答…")

        parent = guess_parent(filename)
        parent_file = os.path.join(DATA_PATH, parent) if parent else None

        reply_msgs = [warning_msg]

        if parent_file and os.path.exists(parent_file):
            with open(parent_file, "r", encoding="utf-8") as f:
                parent_data = json.load(f)
            flex = build_flex_menu(parent_data)
            reply_msgs.append(FlexSendMessage(alt_text="返回上一頁", contents=flex))
        else:
            main_file = os.path.join(DATA_PATH, "main.json")
            if os.path.exists(main_file):
                with open(main_file, "r", encoding="utf-8") as f:
                    main_data = json.load(f)
                flex = build_flex_menu(main_data)
                reply_msgs.append(FlexSendMessage(alt_text="主選單", contents=flex))

        line_bot_api.reply_message(event.reply_token, reply_msgs)
        return False

    # ✅ 檔案存在 → 照常處理
    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)

    if data["type"] == "menu":
        flex = build_flex_menu(data)
        line_bot_api.reply_message(
            event.reply_token,
            FlexSendMessage(alt_text=data.get("title", "選單"), contents=flex)
        )
        return True

    elif data["type"] == "text":
        text_content = data.get("text", "")

        if isinstance(text_content, list):
            text_content = "\n".join(text_content)
        elif isinstance(text_content, str) and text_content.startswith("@"):
            filename = text_content[1:] + ".txt"
            txt_path = os.path.join(DATA_PATH, filename)
            if os.path.exists(txt_path):
                with open(txt_path, "r", encoding="utf-8") as tf:
                    text_content = tf.read()
            else:
                text_content = f"⚠️ 找不到外部檔案 {filename}"
        elif isinstance(text_content, str):
            text_content = text_content.strip()

        if not text_content:
            text_content = "⚠️ 資訊建構中"

        reply_msgs = []
        reverse_order = data.get("reverse_order", False)

        if reverse_order and "options" in data:
            extra_menu = {
                "type": "menu",
                "title": data.get("title", "選單"),
                "options": data["options"]
            }
            flex = build_flex_menu(extra_menu)
            reply_msgs.append(FlexSendMessage(alt_text="返回選單", contents=flex))
            reply_msgs.append(TextSendMessage(text=text_content))
        else:
            reply_msgs.append(TextSendMessage(text=text_content))
            if "options" in data:
                extra_menu = {
                    "type": "menu",
                    "title": data.get("title", "選單"),
                    "options": data["options"]
                }
                flex = build_flex_menu(extra_menu)
                reply_msgs.append(FlexSendMessage(alt_text="返回選單", contents=flex))

        line_bot_api.reply_message(event.reply_token, reply_msgs)
        return True

# ------------------------------
#   Flex Menu Builder
# ------------------------------
def build_flex_menu(data: dict) -> dict:
    contents = [
        {
            "type": "text",
            "text": f"📌 {data.get('title', '選單')}",
            "weight": "bold",
            "size": "xl",
            "align": "center"
        },
        {"type": "separator", "margin": "md"},
        {
            "type": "box",
            "layout": "vertical",
            "spacing": "sm",
            "margin": "md",
            "contents": []
        }
    ]

    for option in data.get("options", []):
        contents[2]["contents"].append({
            "type": "button",
            "style": "primary" if "⬅️" not in option["label"] and "🏠" not in option["label"] else "secondary",
            "color": "#36C5F0" if "⬅️" not in option["label"] and "🏠" not in option["label"] else "#AAAAAA",
            "action": {
                "type": "message",
                "label": option["label"],
                "text": f"/qa {option['next']}"
            }
        })

    return {"type": "bubble", "size": "mega", "body": {"type": "box", "layout": "vertical", "contents": contents}}

# ------------------------------
#   QA 父層猜測
# ------------------------------
def guess_parent(filename: str) -> str:
    name = filename.replace(".json", "")
    if "_說明" in name or "_成分" in name:
        return f"{name.split('_')[0]}.json"
    if name.startswith("產品一"):
        return "prod.json"
    if name.startswith("prod"):
        return "main.json"
    return "main.json"

# ------------------------------
#   角色判斷
# ------------------------------
def choose_role(user_text: str) -> str:
    text = user_text.lower()
    for role, config in role_data.items():
        keywords = config.get("keywords", [])
        if any(k in text for k in keywords):
            return role
    return "default"

# ------------------------------
#   OpenAI API 呼叫
# ------------------------------
def call_openai(prompt: str, role: str = "default") -> str:
    system_prompt = role_data.get(role, role_data["default"])["prompt"]

    try:
        url = "https://api.openai.com/v1/chat/completions"
        headers = {"Authorization": f"Bearer {OPENAI_API_KEY}"}

        payload = {
            "model": "gpt-5-chat-latest",
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt}
            ]
        }

        response = requests.post(url, headers=headers, json=payload)
        response.raise_for_status()
        data = response.json()
        return data["choices"][0]["message"]["content"].strip()
    except Exception as e:
        print("OpenAI API error:", e)
        return "⚠️ 抱歉，GPT 回覆時發生錯誤。"
