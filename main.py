import os
import json
import requests
from fastapi import FastAPI, Request, HTTPException
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import (
    MessageEvent, TextMessage, TextSendMessage, FlexSendMessage
)

app = FastAPI()

LINE_CHANNEL_SECRET = os.getenv("LINE_CHANNEL_SECRET")
LINE_ACCESS_TOKEN = os.getenv("LINE_ACCESS_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

line_bot_api = LineBotApi(LINE_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)

DATA_PATH = "qa_data"  # JSON & TXT 存放資料夾


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


@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    user_text = event.message.text.strip()

    # ✅ /qa 指令
    if user_text.startswith("/qa"):
        parts = user_text.split()
        filename = parts[1] if len(parts) > 1 else "main"
        if not filename.endswith(".json"):
            filename += ".json"
        handle_qa(event, filename)
        return

    # ✅ 預設走 GPT
    gpt_reply = call_openai(user_text, lang="zh")
    line_bot_api.reply_message(event.reply_token, TextSendMessage(text=gpt_reply))


# ------------------------------
#   QA 功能處理
# ------------------------------
def handle_qa(event, filename: str):
    filepath = os.path.join(DATA_PATH, filename)

    if not os.path.exists(filepath):
        # ⚠️ 智慧 fallback → 回到上一層
        warning_msg = TextSendMessage(text="⚠️ 資訊建構中，請稍後再試")

        parent = guess_parent(filename)
        parent_file = os.path.join(DATA_PATH, parent) if parent else None

        if parent_file and os.path.exists(parent_file):
            with open(parent_file, "r", encoding="utf-8") as f:
                parent_data = json.load(f)
            flex = build_flex_menu(parent_data)
            reply_msgs = [warning_msg, FlexSendMessage(alt_text="返回上一頁", contents=flex)]
        else:
            # 如果找不到上一層，就回主選單
            main_file = os.path.join(DATA_PATH, "main.json")
            if os.path.exists(main_file):
                with open(main_file, "r", encoding="utf-8") as f:
                    main_data = json.load(f)
                flex = build_flex_menu(main_data)
                reply_msgs = [warning_msg, FlexSendMessage(alt_text="主選單", contents=flex)]
            else:
                reply_msgs = [warning_msg]

        line_bot_api.reply_message(event.reply_token, reply_msgs)
        return

    # ✅ 檔案存在 → 照常處理
    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)

    if data["type"] == "menu":
        flex = build_flex_menu(data)
        line_bot_api.reply_message(
            event.reply_token,
            FlexSendMessage(alt_text=data.get("title", "選單"), contents=flex)
        )

    elif data["type"] == "text":
        text_content = data.get("text", "")

        # ✅ 如果 text 指向 txt 檔
        txt_path = os.path.join(DATA_PATH, f"{text_content}.txt")
        if isinstance(text_content, str) and os.path.exists(txt_path):
            with open(txt_path, "r", encoding="utf-8") as tf:
                text_content = tf.read()

        # ✅ 如果是 list → 轉換成多行
        if isinstance(text_content, list):
            text_content = "\n".join(text_content)

        reply_msgs = [TextSendMessage(text=text_content)]

        if "options" in data:
            extra_menu = {
                "type": "menu",
                "title": data.get("title", "選單"),
                "options": data["options"]
            }
            flex = build_flex_menu(extra_menu)
            reply_msgs.append(FlexSendMessage(alt_text="返回選單", contents=flex))

        line_bot_api.reply_message(event.reply_token, reply_msgs)


def build_flex_menu(data: dict) -> dict:
    """把 JSON 轉成 LINE Flex Message"""
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


def guess_parent(filename: str) -> str:
    """
    根據命名規則推測上一層檔案
    ex: 產品一_說明.json → 產品一.json
        產品一.json     → prod.json
        prod.json      → main.json
    """
    name = filename.replace(".json", "")
    if "_說明" in name or "_成分" in name:
        return f"{name.split('_')[0]}.json"
    if name.startswith("產品一"):
        return "prod.json"
    if name.startswith("prod"):
        return "main.json"
    return "main.json"  # 預設回主選單


# ------------------------------
#   OpenAI API 呼叫
# ------------------------------
def call_openai(prompt: str, lang: str = "zh") -> str:
    try:
        url = "https://api.openai.com/v1/chat/completions"
        headers = {"Authorization": f"Bearer {OPENAI_API_KEY}"}

        system_prompts = {
            "zh": "你是一個助理，請一律使用繁體中文回答使用者。"
        }

        payload = {
            "model": "gpt-4o-mini",
            "messages": [
                {"role": "system", "content": system_prompts.get(lang, system_prompts["zh"])},
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
