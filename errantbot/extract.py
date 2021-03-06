from collections import namedtuple
from urllib.parse import parse_qs, quote, urlparse

import click
import regex
import requests

import tldextract
from bs4 import BeautifulSoup

from . import exceptions as exc
from . import helper as h

Work = namedtuple(
    "Work", ["title", "artists", "series", "nsfw", "image_url", "source_url"]
)


def artstation(page_url, options):
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

    return Work(title, (clean_artist,), None, nsfw, image_url, page_url)


def pixiv(page_url, options):
    from pixivpy3 import AppPixivAPI

    parsed = urlparse(page_url)

    id = int(parsed.path.split("/")[-1])

    api = AppPixivAPI()

    secrets = h.get_secrets()["pixiv"]
    api.login(secrets["username"], secrets["password"])

    data = api.illust_detail(id)["illust"]

    if len(data["meta_pages"]) == 0:
        image_url = data["meta_single_page"]["original_image_url"]
    elif options["album"]:
        image_url = [image["image_urls"]["original"] for image in data["meta_pages"]]
    else:
        image_url = data["meta_pages"][options["index"]]["image_urls"]["original"]

    return Work(
        data["title"],
        (
            data["user"]["account" if options["username"] else "name"],
            data["user"]["name" if options["username"] else "account"],
        ),
        None,
        data["x_restrict"] > 0,
        image_url,
        page_url,
    )


def hentai_foundry(page_url, options):
    res = requests.get(page_url + "?enterAgree=1")

    res.raise_for_status()

    soup = BeautifulSoup(res.text, features="html.parser")

    image_url = "https:" + soup.find(id="picBox").find(class_="boxbody").img["src"]

    title = soup.main.find(class_="titleSemantic").text

    artist = soup.find(id="page").find_all("a")[1].text

    category = soup.find(class_="categoryBreadcrumbs").find_all("a")

    series = None

    if len(category) > 1:
        if category[0].text != "Original":
            series = category[1].text

    ratings = soup.find(class_="ratings_box")

    nsfw = bool(ratings.find(title="Nudity") or ratings.find(title="Sexual content"))

    return Work(title, (artist,), series, nsfw, image_url, page_url)


def deviantart(page_url, options):
    oe_req = requests.get(
        "https://backend.deviantart.com/oembed?url={}".format(quote(page_url))
    )

    oe_req.raise_for_status()

    data = oe_req.json()

    url = regex.match(r".*?\.(?:jpg|png)", data["url"])[0]
    url = regex.sub(r"(.*?\.com)", r"\1/intermediary", url)

    return Work(
        data["title"],
        (data["author_name"],),
        None,
        data["safety"] != "nonadult",
        url,
        page_url,
    )


# Note: Due to FurAffinity's system, in order to access NSFW images we need to use
# the user's cookies taken from their browser.
# Therefore, FurAffinity integration will probably break a lot.
def furaffinity(page_url, options):
    cookies = h.get_secrets()["furaffinity"]["cookies"]

    res = requests.get(page_url, cookies=cookies)

    res.raise_for_status()

    soup = BeautifulSoup(res.text, features="html.parser")

    body_id = soup.body["id"]

    if body_id == "pageid-matureimage-error":
        raise click.ClickException(
            "Page blocked by content filter settings; check your cookies"
        )

    if body_id != "pageid-submission":
        raise click.ClickException("Page does not appear to be a submission")

    cat = soup.find(class_="maintable").find(class_="maintable").find(class_="cat")

    title = cat.b.text
    artist = cat.a.text

    nsfw = bool(
        soup.find(class_="stats-container").find(
            name="img", alt=regex.compile(r"(?:Mature|Adult)")
        )
    )

    image_url = "https:" + soup.find(name="a", text="Download")["href"]

    return Work(title, (artist,), None, nsfw, image_url, page_url)


def auto(page_url, **kwargs):
    default_options = {"index": 0, "album": False, "username": False}

    for k, v in default_options.items():
        if k not in kwargs:
            kwargs[k] = v

    domains = {
        "artstation": artstation,
        "pixiv": pixiv,
        "hentai-foundry": hentai_foundry,
        "deviantart": deviantart,
        "furaffinity": furaffinity,
    }

    no_fetch_extract = tldextract.TLDExtract(suffix_list_urls=None)

    domain = no_fetch_extract(page_url).domain

    if domain in domains:
        return domains[domain](page_url, kwargs)

    raise exc.UnsupportedSite(page_url)
