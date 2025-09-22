import os, requests, json

API_KEY = "OLD_SECRET"  #os.getenv("OPENAI_API_KEY")
if not API_KEY:
    raise Exception("⚠️ 請先設定 OPENAI_API_KEY 環境變數")

headers = {"Authorization": f"Bearer {API_KEY}"}

# 1️⃣ 列出所有可用模型
print("=== 可用模型 ===")
resp = requests.get("https://api.openai.com/v1/models", headers=headers)
if resp.status_code == 200:
    models = [m["id"] for m in resp.json().get("data", [])]
    for m in models:
        if "gpt" in m.lower():
            print("-", m)
else:
    print("列模型失敗:", resp.status_code, resp.text)

# 2️⃣ 測試 GPT-5 是否可用
print("\n=== 測試 GPT-5 ===")
payload = {
    "model": "gpt-5",  # 你可以改成 gpt-5-mini, gpt-5o 之類的名稱
    "messages": [
        {"role":"system","content":"請用繁體中文回答"},
        {"role":"user","content":"你好，請回覆『測試成功』"}
    ]
}
resp = requests.post("https://api.openai.com/v1/chat/completions",
                     headers={**headers, "Content-Type": "application/json"},
                     json=payload)

print("狀態碼:", resp.status_code)
print("回應:", resp.text[:500])  # 只印前 500 字避免太長
