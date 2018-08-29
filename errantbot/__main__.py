import praw
import tomlkit

reddit = None

with open("secrets.toml") as secrets_file:
    secrets = tomlkit.parse(secrets_file.read())["reddit"]
    reddit = praw.Reddit(client_id=secrets["client_id"],
                         client_secret=secrets["client_secret"],
                         password=secrets["password"],
                         username=secrets["username"],
                         user_agent="ErrantBot")



sub = praw.models.Submission(reddit, "9b3qlr")

for choice in sub.flair.choices():
    print(choice)
