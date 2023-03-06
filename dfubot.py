import os
import openai
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler
from libgen_api import LibgenSearch
from slack_sdk import WebClient
import requests
from dotenv import load_dotenv
from flask import Flask
from threading import Thread

load_dotenv()
openai.api_key = os.environ["OPENAI_API_KEY"]

# Instantiate a Slackbot app with the Socket Mode handler
app = App(token=os.environ["SLACK_BOT_TOKEN"])
handler = SocketModeHandler(app, os.environ["SLACK_APP_TOKEN"])
client = WebClient(os.environ["SLACK_BOT_TOKEN"])
s = LibgenSearch()
flask_app = Flask(__name__)

def parse_title_from_message(message):
    messages = []
    messages.append({"role": "system", "content": "Parse the book title from the following text. Return only the title of the book as a string. If no book title can be found, return only the words 'not found'."})
    messages.append({"role": "user", "content": message})
    repsonse_api = openai.ChatCompletion.create(model="gpt-3.5-turbo", messages=messages)
    title = repsonse_api["choices"][0]["message"]["content"]
    return title

# Define a function to handle incoming messages
@app.event("app_mention")
def handle_message(event, say):
    print(event)
    channel_id = event["channel"]
    message_text = event["text"]
    title = parse_title_from_message(message_text)

    if not title or title == "not found":
        say('No title found')
        return

    results = s.search_title(title)
    if not results or len(results) == 0:
        say('No results found')
        return

    print(results)

    download_links = s.resolve_download_links(results[0])
    print(download_links)

    download_links = list(download_links.values())
    i = 0

    while i < len(download_links):
        try:
            download_link = download_links[i]
            print(f"Downloading {download_link}")
            res = requests.get(download_link, timeout=10)

            if not res.ok:
                i += 1
                continue

            filename = f"{results[0]['Title']}.{results[0]['Extension']}"
            with open(filename, 'wb') as f:
                f.write(res.content)

            print("Downloaded")
            
            client.files_upload(
                file=filename,
                channels=channel_id,
            )
            print("Uploaded")

            os.remove(filename)
            return
        except Exception as e:
            print(e)
            i += 1
            continue

def run_flask():
    flask_app.run(debug=True, port=os.environ['PORT'], host='0.0.0.0')

def run_slack():
    handler.start()

if __name__ == "__main__":
    t2 = Thread(target = run_slack)

    t2.start()
    run_flask()