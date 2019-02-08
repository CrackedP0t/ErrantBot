import regex
import requests
import tldextract
from urllib.parse import urlparse, parse_qs
from collections import namedtuple
from pixivpy3 import AppPixivAPI
import tomlkit
from bs4 import BeautifulSoup

Work = namedtuple(
    "Work", ["title", "artist", "series", "nsfw", "image_url", "source_url"]
)


def artstation(page_url):
    parsed = urlparse(page_url)

    ident = regex.search(r"([^/]*)\/?$", parsed.path)[0]

    json_url = "https://artstation.com/projects/{}.json".format(ident)

    res = requests.get(json_url)

    json = res.json()

    title = json["title"]
    artist = json["user"]["full_name"]
    nsfw = json["adult_content"]
    image_url = json["assets"][0]["image_url"]

    antifun = regex.compile(
        "([\u2600-\u26ff])|"  # Miscellaneous symbols
        "([\ufe0e-\ufe0f])|"  # Variation selectors
        "(\ud83d[\ude00-\ude4f])|"  # emoticons
        "(\ud83c[\udf00-\uffff])|"  # symbols & pictographs (1 of 2)
        "(\ud83d[\u0000-\uddff])|"  # symbols & pictographs (2 of 2)
        "(\ud83d[\ude80-\udeff])|"  # transport & map symbols
        "(\ud83c[\udde0-\uddff])"  # flags (iOS)
        "+",
        flags=regex.UNICODE,
    )

    clean_artist = antifun.sub("", artist).strip()

    return Work(title, clean_artist, None, nsfw, image_url, page_url)


def pixiv(page_url):
    parsed = urlparse(page_url)
    query = parse_qs(parsed.query)

    id = int(query["illust_id"][0])

    api = AppPixivAPI()

    with open("secrets.toml") as secrets_file:
        secrets = tomlkit.parse(secrets_file.read())["pixiv"]
        api.login(secrets["username"], secrets["password"])

    data = api.illust_detail(id)["illust"]

    return Work(
        data["title"],
        data["user"]["name"],
        data["series"],
        data["x_restrict"] > 0,
        data["meta_single_page"]["original_image_url"],
        page_url,
    )


def hentai_foundry(page_url):
    res = requests.get(page_url + "?enterAgree=1")

    res.raise_for_status()

    soup = BeautifulSoup(res.text, features="html.parser")

    image_url = "https:" + soup.find(id="picBox").find(class_="boxbody").img["src"]

    title = soup.main.find(class_="titleSemantic").text

    artist = soup.find(id="page").find_all("a")[1].text

    category = soup.find(class_="categoryBreadcrumbs").find_all("a")

    series = None

    if category[0].text != "Original":
        series = category[1].text

    ratings = soup.find(class_="ratings_box")

    nsfw = bool(ratings.find(title="Nudity") or ratings.find(title="Sexual content"))

    return Work(title, artist, series, nsfw, image_url, page_url)


def auto(page_url):
    domains = {
        "artstation": artstation,
        "pixiv": pixiv,
        "hentai-foundry": hentai_foundry,
    }

    no_fetch_extract = tldextract.TLDExtract(suffix_list_urls=None)

    domain = no_fetch_extract(page_url).domain

    if domain in domains:
        return domains[domain](page_url)
