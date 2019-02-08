import click
from psycopg2.extensions import adapt, register_adapter, AsIs
import tomlkit
from errantbot import apis


def escape_values(db, seq):
    return (b",".join(map(db.literal, seq))).decode()


def parse_subreddits(sub_names):
    def splitter(name):
        pair = name.split("#")
        return (pair[0], pair[1] if len(pair) == 2 else None)

    subs_to_tags = tuple(map(splitter, sub_names))

    return subs_to_tags


def connect_imgur():
    click.echo("Connecting to Imgur...")
    imgur = None

    with open("secrets.toml") as secrets_file:
        secrets = tomlkit.parse(secrets_file.read())["imgur"]

        imgur = apis.Imgur(secrets["client_id"], secrets["client_secret"])

    imgur.authenticate()

    return imgur


def connect_reddit():
    click.echo("Connecting to Reddit...")

    reddit = None

    with open("secrets.toml") as secrets_file:
        secrets = tomlkit.parse(secrets_file.read())

        reddit = apis.Reddit(secrets["reddit"])

    reddit.authenticate()

    return reddit.reddit


def post_to_all_subreddits(db, work_id):
    reddit = connect_reddit()

    cursor = db.cursor()

    cursor.execute(
        """SELECT title, series, artist, source_url, imgur_image_url, nsfw,
        source_image_url, flair_id, tag_series, name, rehost, custom_tag,
        submissions.id FROM works
        INNER JOIN submissions ON submissions.reddit_id is NULL
        AND submissions.work_id = works.id INNER JOIN subreddits
        ON submissions.subreddit_id = subreddits.id AND works.id = %s""",
        (work_id,),
    )

    rows = cursor.fetchall()

    for row in rows:
        sub = reddit.subreddit(row["name"])

        title = "{title} ({artist}){series_tag}{tag}".format(
            series_tag=" [" + row["series"] + "]" if row["tag_series"] else "",
            tag=" [" + row["custom_tag"] + "]" if row["custom_tag"] else "",
            **row
        )

        url = row["imgur_image_url" if row["rehost"] else "source_image_url"]

        submission = sub.submit(title, url=url, flair_id=row["flair_id"])

        if row["nsfw"]:
            submission.mod.nsfw()

        submission.reply("[Source]({})".format(row["source_url"]))

        cursor.execute(
            "UPDATE submissions SET reddit_id = %s WHERE id = %s" "",
            (submission.id, row["id"]),
        )

        db.commit()


def upload_to_imgur(db, work_id):
    imgur = connect_imgur()

    click.echo("Uploading to Imgur...")

    cursor = db.cursor()

    cursor.execute(
        """SELECT title, artist, source_image_url, source_url
        FROM works WHERE id=%s""",
        (work_id,),
    )
    row = cursor.fetchone()

    resp = imgur.upload_url(
        row["source_image_url"],
        "{title} ({artist})".format(**row),
        "Source: {source_url}".format(**row),
    )

    resp.raise_for_status()

    data = resp.json()["data"]

    cursor.execute(
        """UPDATE works SET imgur_id=%s, imgur_image_url=%s WHERE id=%s""",
        (data["id"], data["link"], work_id),
    )
    db.commit()


def save_work(
    db,
    title,
    series,
    artist,
    source_url,
    imgur_id,
    imgur_image_url,
    nsfw,
    source_image_url,
    subs_to_tags,
):
    subreddits_exist(db, tuple(map(lambda sub: sub[0], subs_to_tags)))

    cursor = db.cursor()

    cursor.execute(
        """INSERT INTO works (title, series, artist, source_url,
            imgur_id, imgur_image_url, nsfw, source_image_url)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING id;""",
        (
            title,
            series,
            artist,
            source_url,
            imgur_id,
            imgur_image_url,
            nsfw,
            source_image_url,
        ),
    )
    db.commit()

    work_id = cursor.fetchone()[0]

    add_work_to_subreddits(db, work_id, subs_to_tags)

    return work_id


def add_subreddit(db, name, tag_series, flair_id, rehost):
    cursor = db.cursor()

    cursor.execute(
        """INSERT INTO subreddits (name, tag_series, flair_id, rehost)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (name) DO UPDATE SET tag_series = %s, flair_id = %s, rehost = %s""",
        (name, tag_series, flair_id, rehost, tag_series, flair_id, rehost),
    )
    db.commit()


def add_work_to_subreddits(db, work_id, subs_to_tags):
    subreddits_exist(db, tuple(map(lambda sub: sub[0], subs_to_tags)))

    class SubsToTags:
        def __init__(self, s2t):
            self.s2t = s2t

    def adapt_substotags(obj):
        return AsIs(
            ",".join(map(lambda pair: adapt(pair).getquoted().decode(), obj.s2t))
        )

    register_adapter(SubsToTags, adapt_substotags)

    cursor = db.cursor()

    cursor.execute(
        """INSERT INTO submissions
        (work_id, subreddit_id, custom_tag)
        SELECT %s, id, tag FROM subreddits INNER JOIN (VALUES %s) AS tags (subname, tag)
        ON subreddits.name = tags.subname
        ON CONFLICT ON CONSTRAINT submissions_work_id_subreddit_id_key DO NOTHING""",
        (work_id, SubsToTags(subs_to_tags)),
    )
    db.commit()


def subreddits_exist(db, subreddit_names):
    cursor = db.cursor()

    cursor.execute(
        """WITH prov (name) AS ( VALUES %s )
        SELECT name FROM prov EXCEPT select name from subreddits""",
        (subreddit_names,),
    )

    badsubs = cursor.fetchall()

    n_bad = len(badsubs)

    if n_bad > 0:
        raise click.ClickException(
            "Subreddit{} {} {} unknown. Use 'add-sub' to register {}.".format(
                "s" if n_bad > 1 else "",
                ", ".join(map(lambda sub: "'" + sub["name"] + "'", badsubs)),
                "are" if n_bad > 1 else "is",
                "them" if n_bad > 1 else "it",
            )
        )
