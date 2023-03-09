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
import json

load_dotenv()
openai.api_key = os.environ["OPENAI_API_KEY"]

# Instantiate a Slackbot app with the Socket Mode handler
app = App(token=os.environ["SLACK_BOT_TOKEN"])
handler = SocketModeHandler(app, os.environ["SLACK_APP_TOKEN"])
client = WebClient(os.environ["SLACK_BOT_TOKEN"])
s = LibgenSearch()
flask_app = Flask(__name__)

def parse_title_from_message(message):
    system_prompt = "Extract the book title and author from the provided input. Return a JSON string only. If no book title or author can be found in the provided input, return an empty string for those title or author in the JSON object. Your response should only contain the JSON object and no other output. "
    system_prompt += "As a third entry in the JSON object named 'comment', provide a short witty commentary on the requested book. Be creative. For constructing this comment, you are a helpful AI assistant making a witty joke about the requested book title only."
    system_prompt += "\nYour response should only contain a JSON string with 'title', 'author', and 'comment' keys. If you must comment on the provided input, do so in the 'comment' field only. If you are not sure what to put in the JSON field, provide an empty string. Do not return the words 'Output: '."
    system_prompt += "Always include some text in the comment field, even if a title or author cannot be found. Prioritize making the comment as witty as possible."
    system_prompt += "\n Example Input: no, david! by david shannon \n Output: {\"title\": \"No, David!\", \"author\": \"David Shannon\", \"comment\": \"A children's book, huh?\"}"
    system_prompt += "\n Example Input: Regulating Artificial Intelligence \n Output: {\"title\": \"Regulating Artificial Intelligence\", \"author\": \"\", \"comment\": \"I see that you're seeking to control me.\"}"
    system_prompt += "\n Example Input: urban gardening as politics by chiara tornaghi \n Output: {\"title\": \"Urban Gardening as Politics\", \"author\": \"Chiara Tornaghi\", \"comment\": \"Who knew planting carrots could be so political?\"}"

    messages = []
    messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": f"Input: {message}"})
    repsonse_api = openai.ChatCompletion.create(model="gpt-3.5-turbo", messages=messages)
    json_dict = repsonse_api["choices"][0]["message"]["content"]
    return json_dict

# Define a function to handle incoming messages
@app.event("app_mention")
def handle_message(event, say):
    try:
        # Print for debugging and parse the message
        print(event)
        channel_id = event["channel"]
        message_text = event["text"]
        response = parse_title_from_message(message_text)

        json_dict = {}
        response = response.replace("Output: ", "") # Sometimes the output is prefixed with "Output: " by the model
        print(response)
        try:
            json_dict = json.loads(response)
        except Exception as e:
            # The model didn't return a valid JSON string
            print(e) 
            say('Invalid input')
            return

        title = json_dict.get('title')
        author = json_dict.get('author')
        comment = json_dict.get('comment')

        # Say the comment regardless
        if comment != "":
            say(comment)

        # Return early if no title was found
        if not title or title == "not found":
            say('No title found')
            return

        results = s.search_title_filtered(title, {'Extension': 'pdf'}) # Try to find PDFs first
        if not results or len(results) == 0:
            results = s.search_title(title) # Do a regular title search
        results = list(filter(lambda x : x['Extension'] != 'mobi', results)) # Filter out mobi files

        # Filter by author if provided
        if author != "":
            new_results = list(filter(lambda x : author in x['Author'], results))
            if new_results and len(new_results) > 0: # If that author filter returns results, use those
                results = new_results

        # Return early if no results were found
        if not results or len(results) == 0:
            say('No results found')
            return

        # Get a list of download links to try
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
                    # If the download fails, try the next link
                    i += 1
                    continue

                # Save the file temporarily and upload it to Slack
                filename = f"{results[0]['Title']}.{results[0]['Extension']}"
                with open(filename, 'wb') as f:
                    f.write(res.content)
                print("Downloaded")
                
                client.files_upload(
                    file=filename,
                    channels=channel_id,
                )
                print("Uploaded")

                # Delete the file
                os.remove(filename)
                return
            except Exception as e:
                # If the download fails, try the next link
                print(e)
                i += 1
                continue
        say('Libgen error. Try again in a couple minutes.')
    except Exception as e:
        # Global exception handler, so we don't break Render
        print(e)
        say("Something went wrong. Try again in a couple minutes.")
        pass

@flask_app.route("/")
def hello_world():
    return "Hello, World!"

def run_flask():
    flask_app.run(debug=True, port=os.environ['PORT'], host='0.0.0.0')

def run_slack():
    handler.start()

if __name__ == "__main__":
    t2 = Thread(target = run_slack)

    t2.start()
    run_flask()