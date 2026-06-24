import os
import requests
from flask import Flask, request, abort
from linebot.v3 import WebhookHandler
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.messaging import (
    Configuration,
    ApiClient,
    MessagingApi,
    PushMessageRequest,
    TextMessage,
)
from linebot.v3.webhooks import MessageEvent, TextMessageContent
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

LINE_CHANNEL_SECRET = os.environ.get("LINE_CHANNEL_SECRET")
LINE_CHANNEL_ACCESS_TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN")
DIFY_API_KEY = os.environ.get("DIFY_API_KEY")
DIFY_BASE_URL = os.environ.get("DIFY_BASE_URL", "https://api.dify.ai/v1")

configuration = Configuration(access_token=LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)

conversation_ids = {}


def ask_dify(user_id: str, message: str) -> str:
    headers = {
        "Authorization": f"Bearer {DIFY_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "inputs": {},
        "query": message,
        "response_mode": "streaming",
        "user": user_id,
    }
    if user_id in conversation_ids:
        payload["conversation_id"] = conversation_ids[user_id]

    response = requests.post(
        f"{DIFY_BASE_URL}/chat-messages",
        headers=headers,
        json=payload,
        timeout=60,
        stream=True,
    )
    response.raise_for_status()

    import json
    answer = ""
    conv_id = ""
    for line in response.iter_lines():
        if line:
            line_str = line.decode("utf-8")
            print(f"Dify stream line: {line_str[:200]}")
            if line_str.startswith("data: "):
                try:
                    data = json.loads(line_str[6:])
                    event = data.get("event", "")
                    print(f"Dify event: {event}")
                    if event == "message":
                        answer += data.get("answer", "")
                    elif event == "agent_message":
                        answer += data.get("answer", "")
                    elif event == "text_chunk":
                        answer += data.get("data", {}).get("text", "")
                    elif event == "message_end":
                        conv_id = data.get("conversation_id", "")
                    elif event == "workflow_finished":
                        outputs = data.get("data", {}).get("outputs", {})
                        answer = outputs.get("answer", outputs.get("text", answer))
                except Exception as e:
                    print(f"Parse error: {e}")

    if conv_id:
        conversation_ids[user_id] = conv_id
    print(f"Final answer: {answer[:100]}")
    return answer or "うまく答えられませんでした。もう一度試してください。"


def send_dify_response(user_id: str, message: str):
    try:
        reply_text = ask_dify(user_id, message)
    except Exception as e:
        print(f"Dify error: {e}")
        reply_text = f"Difyエラー: {str(e)[:100]}"

    try:
        with ApiClient(configuration) as api_client:
            line_bot_api = MessagingApi(api_client)
            line_bot_api.push_message_with_http_info(
                PushMessageRequest(
                    to=user_id,
                    messages=[TextMessage(text=reply_text)],
                )
            )
    except Exception as e:
        print(f"Push message error: {e}")


@app.route("/webhook", methods=["POST"])
@app.route("/api/index", methods=["GET", "POST"])
@app.route("/", methods=["GET", "POST"])
def callback():
    if request.method == "GET":
        return "OK", 200
    signature = request.headers.get("X-Line-Signature", "")
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return "OK", 200


@handler.add(MessageEvent, message=TextMessageContent)
def handle_message(event):
    user_id = event.source.user_id
    user_message = event.message.text

    # Difyに問い合わせてpush_messageで返す
    send_dify_response(user_id, user_message)


if __name__ == "__main__":
    app.run(debug=True)
