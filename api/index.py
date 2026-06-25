import os
from openai import OpenAI
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
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")

configuration = Configuration(access_token=LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)

client = OpenAI(api_key=OPENAI_API_KEY)

conversation_histories = {}

SYSTEM_PROMPT = """あなたは「料理レシピ相談Bot」です。ユーザーが持っている食材や食べたい料理を教えてもらい、具体的なレシピを提案します。

【返答のルール】
- 材料と分量を明確に書く
- 調理手順を番号付きでわかりやすく説明する
- 初心者でも作れるよう丁寧に説明する
- 代替食材や保存方法も必要に応じてアドバイスする
- 親しみやすい日本語で答える
- 絵文字を適度に使って親しみやすくする
- MarkdownやHTMLは使わず、プレーンテキストで返答する"""


def ask_openai(user_id: str, message: str) -> str:
    if user_id not in conversation_histories:
        conversation_histories[user_id] = []

    conversation_histories[user_id].append({"role": "user", "content": message})

    # 会話履歴が長くなりすぎないよう直近10件に制限
    history = conversation_histories[user_id][-10:]

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "system", "content": SYSTEM_PROMPT}] + history,
    )

    answer = response.choices[0].message.content
    conversation_histories[user_id].append({"role": "assistant", "content": answer})
    return answer


def send_line_message(user_id: str, message: str):
    try:
        reply_text = ask_openai(user_id, message)
    except Exception as e:
        print(f"OpenAI error: {e}")
        reply_text = f"エラーが発生しました。もう一度試してください。"

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
    send_line_message(user_id, user_message)


if __name__ == "__main__":
    app.run(debug=True)
