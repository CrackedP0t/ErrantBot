import praw
from requests_oauthlib import OAuth2Session
import os
import json
import socket
import secrets
import click
from errantbot import helper as h


def receive_connection():
    """Wait for and then return a connected socket..

    Opens a TCP connection on port 8080, and waits for a single client.

    """
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(("localhost", 8080))
    server.listen(1)
    client = server.accept()[0]
    server.close()
    return client


def send_message(client, message):
    """Send message to client and close the connection."""
    client.send("HTTP/1.1 200 OK\r\n\r\n{}".format(message).encode("utf-8"))
    client.close()


class Reddit:
    def __init__(self, secrets):
        self.secrets = secrets

    def authenticate(self):
        token = None

        if os.path.isfile("reddit_token.json"):
            with open("reddit_token.json") as token_file:
                token = json.load(token_file)["refresh_token"]

        self.reddit = praw.Reddit(
            client_id=self.secrets["client_id"],
            client_secret=self.secrets["client_secret"],
            redirect_uri="http://localhost:8080",
            refresh_token=token,
            user_agent="ErrantBot",
        )

        if not token:
            state = secrets.token_urlsafe()

            print(
                "Please go here to authorize: "
                + self.reddit.auth.url(
                    ["identity", "flair", "submit", "read", "modposts"], state
                )
            )

            client = receive_connection()
            data = client.recv(1024).decode("utf-8")
            param_tokens = data.split(" ", 2)[1].split("?", 1)[1].split("&")
            params = {
                key: value
                for (key, value) in [token.split("=") for token in param_tokens]
            }

            if state != params["state"]:
                send_message(client, "State mismatch")
                raise click.ClickException("State mismatch")
            elif "error" in params:
                send_message(client, params["error"])
                raise click.ClickException(
                    "Error authenticating with Reddit: " + params["error"]
                )

            refresh_token = self.reddit.auth.authorize(params["code"])

            with open("reddit_token.json", mode="w") as token_file:
                json.dump({"refresh_token": refresh_token}, token_file)

            send_message(client, "ErrantBot's authenticated!")

        h.errecho("\tAuthentication complete")

        return self.reddit


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
        with open("imgur_token.json", mode="w") as token_file:
            json.dump(token, token_file)

    def upload_url(self, url, title, description):
        return self.session.post(
            "https://api.imgur.com/3/image",
            {"type": "URL", "image": url, "title": title, "description": description},
        )
