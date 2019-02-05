import praw
from requests_oauthlib import OAuth2Session
import os
import json


class Reddit:
    def __init__(self, secrets):
        self.secrets = secrets

    def authenticate(self):
        self.reddit = praw.Reddit(
            client_id=self.secrets["client_id"],
            client_secret=self.secrets["client_secret"],
            password=self.secrets["password"],
            username=self.secrets["username"],
            user_agent="ErrantBot",
        )


class Imgur:
    auth_url = "https://api.imgur.com/oauth2/authorize"
    token_url = "https://api.imgur.com/oauth2/token"
    refresh_url = "https://api.imgur.com/oauth2/token"

    def __init__(self, client_id, client_secret):
        self.client_id = client_id
        self.client_secret = client_secret

    def authenticate(self):

        token = None

        if os.path.isfile("imgur_token.json"):
            with open("imgur_token.json") as token_file:
                token = json.load(token_file)
        else:
            initial_session = OAuth2Session(self.client_id)

            new_auth_url, state = initial_session.authorization_url(self.auth_url)

            print("Please go here to authorize: " + new_auth_url)

            callback_url = input("Paste the full redirect URL here: ")

            token = initial_session.fetch_token(
                self.token_url,
                client_secret=self.client_secret,
                authorization_response=callback_url,
            )

            Imgur.token_saver(token)

        client_data = {"client_id": self.client_id, "client_secret": self.client_secret}

        self.session = OAuth2Session(
            self.client_id,
            token=token,
            auto_refresh_url=self.refresh_url,
            auto_refresh_kwargs=client_data,
            token_updater=self.token_saver,
        )

    def token_saver(token):
        print("Refreshing!")
        with open("imgur_token.json", mode="w") as token_file:
            json.dump(token, token_file)

    def test(self):
        r = self.session.get("https://api.imgur.com/3/image/tJAaYoS")
        print(r.content)

    def upload_url(self, url, title, description):
        return self.session.post(
            "https://api.imgur.com/3/image",
            {"type": "URL", "image": url, "title": title, "description": description},
        )
