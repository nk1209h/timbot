import os
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

    # /help 指令 → Flex Message
    if user_text.lower() == "/help":
        flex_content = {
            "type": "bubble",
            "size": "mega",
            "body": {
                "type": "box",
                "layout": "vertical",
                "contents": [
                    {
                        "type": "text",
                        "text": "🌏 語言選單",
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
                        "contents": [
                            {
                                "type": "button",
                                "style": "primary",
                                "color": "#36C5F0",
                                "action": {"type": "message", "label": "繁體中文 (預設)", "text": "今天天氣如何？"}
                            },
                            {
                                "type": "button",
                                "style": "secondary",
                                "color": "#AAAAAA",
                                "action": {"type": "message", "label": "🇺🇸 English", "text": "/eng Hello!"}
                            },
                            {
                                "type": "button",
                                "style": "secondary",
                                "color": "#AAAAAA",
                                "action": {"type": "message", "label": "🇯🇵 日本語", "text": "/jp おはようございます"}
                            },
                            {
                                "type": "button",
                                "style": "secondary",
                                "color": "#AAAAAA",
                                "action": {"type": "message", "label": "🇻🇳 Tiếng Việt", "text": "/vn Xin chào"}
                            },
                            {
                                "type": "button",
                                "style": "secondary",
                                "color": "#AAAAAA",
                                "action": {"type": "message", "label": "🇮🇩 Bahasa Indonesia", "text": "/id Halo"}
                            },
                            {
                                "type": "button",
                                "style": "secondary",
                                "color": "#AAAAAA",
                                "action": {"type": "message", "label": "🇹🇭 ภาษาไทย", "text": "/th สวัสดี"}
                            }
                        ]
                    }
                ]
            }
        }

        line_bot_api.reply_message(
            event.reply_token,
            FlexSendMessage(alt_text="語言選單", contents=flex_content)
        )
        return

    # 判斷語言指令
    lang = "zh"
    prompt = user_text
    if user_text.startswith("/eng"):
        lang, prompt = "en", user_text.replace("/eng", "", 1).strip()
    elif user_text.startswith("/jp"):
        lang, prompt = "jp", user_text.replace("/jp", "", 1).strip()
    elif user_text.startswith("/vn"):
        lang, prompt = "vn", user_text.replace("/vn", "", 1).strip()
    elif user_text.startswith("/id"):
        lang, prompt = "id", user_text.replace("/id", "", 1).strip()
    elif user_text.startswith("/th"):
        lang, prompt = "th", user_text.replace("/th", "", 1).strip()

    gpt_reply = call_openai(prompt, lang=lang)
    line_bot_api.reply_message(event.reply_token, TextSendMessage(text=gpt_reply))


def call_openai(prompt: str, lang: str = "zh") -> str:
    try:
        url = "https://api.openai.com/v1/chat/completions"
        headers = {"Authorization": f"Bearer {OPENAI_API_KEY}"}

        # 各語言系統訊息
        system_prompts = {
            "zh": "你是一個助理，請一律使用繁體中文回答使用者。",
            "en": "You are an assistant. Always reply in English.",
            "jp": "あなたはアシスタントです。必ず日本語で回答してください。",
            "vn": "Bạn là một trợ lý. Hãy luôn trả lời bằng tiếng Việt.",
            "id": "Anda adalah asisten. Selalu jawab dalam bahasa Indonesia.",
            "th": "คุณคือผู้ช่วย กรุณาตอบเป็นภาษาไทยเสมอ"
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
