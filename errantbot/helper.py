import enum
from datetime import datetime, timedelta

import click
import praw
import tomlkit
from prawcore import exceptions
from psycopg2 import errorcodes
from sqlalchemy import MetaData, create_engine, exc, sql
from sqlalchemy.sql import bindparam as bp
from sqlalchemy.sql import select

from . import apis


def has_keys(dictionary, keys):
    for k in keys:
        if k not in dictionary:
            raise ValueError("Key {} not found in row".format(k))


class Submissions:
    def __len__(self):
        return self.length

    def __init__(self, tuples):
        self.n_f_t = tuple(tuples)

        self.names = tuple(map(lambda s: s[0], self.n_f_t))
        self.flairs = tuple(map(lambda s: s[1], self.n_f_t))
        self.tags = tuple(map(lambda s: s[2], self.n_f_t))

        self.length = len(self.n_f_t)


def errecho(*args, **kwargs):
    kwargs["err"] = True
    click.echo(*args, **kwargs)


def get_secrets():
    with open("secrets.toml") as secrets_file:
        return tomlkit.parse(secrets_file.read())


class Connections:
    def __getattr__(self, name):
        if name == "imgur":
            self.connect_imgur()
            return self.imgur
        elif name == "reddit":
            self.connect_reddit()
            return self.reddit
        elif name == "db" or name == "meta" or name == "engine":
            self.connect_db()
            return getattr(self, name)
        else:
            raise AttributeError("{} is not a valid connection name".format(name))

    def connect_imgur(self):
        click.echo("Connecting to Imgur...", err=True)
        secrets = get_secrets()["imgur"]

        self.imgur = apis.Imgur(secrets["client_id"], secrets["client_secret"])

        self.imgur.authenticate()

        errecho("\tAuthentication complete")

    def connect_reddit(self):
        errecho("Connecting to Reddit...")

        reddit = apis.Reddit(get_secrets()["reddit"])

        reddit.authenticate()

        self.reddit = reddit.reddit

    def connect_db(self):
        errecho("Connecting to database...")

        secrets = get_secrets()["database"]

        self.db = create_engine(
            "postgresql://{user}:{password}@{host}/{name}".format(**secrets)
        )

        self.meta = MetaData(bind=self.db)
        self.meta.reflect()

        errecho("\tConnected")


def get_last(con, table):

    return con.db.execute(
        con.meta.tables[table].select().order_by(sql.desc("id")).limit(1)
    ).first()["id"]


def do_post(con, row):
    has_keys(
        row,
        (
            "series",
            "title",
            "artist",
            "custom_tag",
            "imgur_url",
            "source_image_url",
            "source_image_urls",
            "flair_id",
            "nsfw",
            "source_url",
            "submission_id",
            "subreddit_id",
        ),
    )

    sr_row = con.db.execute(
        sql.text(
            """SELECT last_submission_on, space_out, name, tag_series,
        rehost, flair_id, disabled FROM subreddits WHERE id = :id"""
        ),
        id=row["subreddit_id"],
    ).first()

    if sr_row["disabled"]:
        errecho("\t/r/{} is disabled".format(sr_row["name"]))
        return False

    if sr_row["space_out"] and sr_row["last_submission_on"] is not None:
        since = datetime.utcnow() - sr_row["last_submission_on"]
        if since < timedelta(days=1):
            wait = timedelta(days=1) - since
            wait = timedelta(wait.days, wait.seconds)
            errecho(
                "\tSubmitted to /r/{} less than one day ago; "
                "you can try again in {}".format(sr_row["name"], wait)
            )

            return False

    sub = con.reddit.subreddit(sr_row["name"])

    if sr_row["tag_series"]:
        series_tag = " [" + (row["series"] or "Original") + "]"
    else:
        series_tag = ""

    title = "{title} ({artist}){series_tag}{tag}".format(
        series_tag=series_tag,
        tag=" " + row["custom_tag"] if row["custom_tag"] else "",
        **row
    )

    if sr_row["rehost"]:
        url = row["imgur_url"]
    else:
        if row["is_album"]:
            url = row["source_image_urls"][0]
        else:
            url = row["source_image_url"]

    try:
        submission = sub.submit(
            title, url=url, flair_id=row["flair_id"] or sr_row["flair_id"]
        )
    except praw.exceptions.APIException as e:
        errecho(
            "\tCouldn't submit to /r/{} - got error {}: '{}'".format(
                sr_row["name"], e.error_type, e.message
            )
        )

        return False
    else:
        errecho(
            "\tSubmitted to /r/{} at https://reddit.com{}".format(
                sr_row["name"], submission.permalink
            )
        )

        if row["nsfw"]:
            submission.mod.nsfw()

        submission.reply("[Source]({})".format(row["source_url"]))

        con.db.execute(
            sql.text(
                """UPDATE submissions SET reddit_id = :reddit_id,
            submitted_on = to_timestamp(:time) AT TIME ZONE 'utc'
            WHERE id = :id"""
            ),
            reddit_id=submission.id,
            time=int(submission.created_utc),
            id=row["submission_id"],
        )

        return True


def post_submissions(con, work_ids=None, submissions=None, do_all=False, last=False):
    if work_ids is None:
        work_ids = []

    if not isinstance(work_ids, list):
        if hasattr(work_ids, "__iter__"):
            work_ids = list(work_ids)
        else:
            work_ids = [work_ids]

    if last:
        work_ids.append(get_last(con, "works"))

    submissions = False if do_all else submissions

    query = sql.text(
        """SELECT title, series, artist, source_url, imgur_url, nsfw,
        source_image_url, custom_tag, submissions.id as submission_id,
        source_image_urls, subreddit_id, submissions.flair_id, reddit_id
        FROM works
        INNER JOIN submissions
        ON reddit_id IS NULL
        AND work_id = works.id"""
        + (" AND works.id = ANY(:work_ids)" if not do_all else "")
        + (
            " INNER JOIN subreddits ON subreddits.name = ANY(:names)"
            if submissions
            else ""
        )
    )

    rows = con.db.execute(
        query,
        work_ids=work_ids if not do_all else None,
        names=list(submissions.names) if submissions else None,
    ).fetchall()

    if len(rows) == 0:
        errecho("No works require posting")
        return

    errecho("Posting...")

    for row in rows:
        do_post(con, row)


def upload_to_imgur(con, work_ids=[], last=False, do_all=False):
    works = con.meta.tables["works"]

    if not do_all:
        if not isinstance(work_ids, list):
            if hasattr(work_ids, "__iter__"):
                work_ids = list(work_ids)
            else:
                work_ids = [work_ids]

        if last:
            work_ids.append(get_last(con, "works"))

    rows = con.db.execute(
        sql.text(
            """SELECT title, artist, source_image_url, source_image_urls,
        source_url, imgur_url, id, is_album
        FROM works WHERE imgur_id IS NULL"""
            + ("" if do_all else " AND id = ANY(:work_ids)")
        ),
        work_ids=None if do_all else work_ids,
    ).fetchall()

    if not rows:
        errecho("No works require uploading")
        return

    errecho("Uploading to Imgur...")

    for row in rows:
        title = "{title} ({artist})".format(**row)
        description = "Source: {source_url}".format(**row)

        if row["is_album"]:
            resp = con.imgur.session.post(
                "https://api.imgur.com/3/album",
                {"title": title, "description": description},
            )

            resp.raise_for_status()

            data = resp.json()["data"]

            album_id = data["id"]

            link = "https://imgur.com/a/{}".format(album_id)

            errecho("Created album at {}".format(link))

            con.db.execute(
                works.update()
                .values(imgur_id=album_id, imgur_url=link)
                .where(works["id"] == row["id"])
            )

            for index, image_url in enumerate(row["source_image_urls"]):
                resp = con.imgur.upload_url(image_url, album_id=album_id)

                resp.raise_for_status()

                data = resp.json()["data"]

                errecho("Uploaded image #{} to {}".format(index, data["link"]))

        else:
            resp = con.imgur.upload_url(row["source_image_url"], title, description)

            resp.raise_for_status()

            data = resp.json()["data"]

            con.db.execute(
                works.update()
                .values(imgur_id=data["id"], imgur_url=data["link"])
                .where(works.id == row["id"])
            )

            errecho("\tUploaded at {}".format(data["link"]))


def save_work(con, title, series, artist, source_url, nsfw, source_image_url):
    errecho("Saving to database...")
    works = con.meta.tables["works"]

    is_album = isinstance(source_image_url, list)

    values = {
        "title": title,
        "series": series,
        "artist": artist,
        "source_url": source_url,
        "nsfw": nsfw,
    }

    if is_album:
        values["source_image_urls"] = source_image_url
    else:
        values["source_image_url"] = source_image_url

    query = works.insert(values=values).returning(works.c.id)

    work_id = con.db.execute(query).first()["id"]

    errecho("\tSaved with id {}".format(work_id))

    return work_id


def edit_subreddits(
    con,
    names,
    tag_series,
    flair_id,
    rehost,
    require_flair,
    require_tag,
    require_series,
    space_out,
    disabled,
):
    for name in names:
        status = subreddit_status(name, con.reddit)

        if not status:
            errecho("\t/r/{} is {}".format(name, status.name.lower()))
        else:
            con.db.execute(
                sql.text(
                    """INSERT INTO subreddits (name, tag_series, flair_id,
                rehost, require_flair, require_tag, space_out, disabled)
                VALUES (:name, :tag_series, :flair_id, :rehost, :require_flair,
                :require_tag, :space_out, :disabled)
                ON CONFLICT (name) DO UPDATE SET
                tag_series = :tag_series, flair_id = :flair_id, rehost = :rehost,
                require_flair = :require_flair, require_tag = :require_tag,
                require_series = :require_series, space_out = :space_out,
                disabled = :disabled"""
                ),
                name=name,
                flair_id=flair_id,
                tag_series=tag_series,
                rehost=rehost,
                require_flair=require_flair,
                require_tag=require_tag,
                require_series=require_series,
                space_out=space_out,
                disabled=disabled,
            )


def add_submissions(con, work_id, specifiers):
    errecho("Adding submissions...")
    submissions = con.meta.tables["submissions"]
    subreddits = con.meta.tables["subreddits"]

    query = submissions.insert().values(
        work_id=work_id,
        subreddit_id=select([subreddits.c.id]).where(
            subreddits.c.name == bp("subreddit_name")
        ),
        flair_id=bp("flair_id"),
        custom_tag=bp("custom_tag"),
    )

    for triple in specifiers.n_f_t:
        try:
            con.db.execute(
                query,
                subreddit_name=triple[0],
                flair_id=triple[1],
                custom_tag=triple[2],
            )

        except exc.IntegrityError as e:
            msg = {
                "check_require_flair": "/r/{} requires a flair",
                "check_require_series": "/r/{} requires a series",
                "check_require_tag": "/r/{} requires a tag",
                "already_exists": "/r/{} already has this work",
            }.get(e.orig.diag.constraint_name, None)

            if (
                e.orig.pgcode == errorcodes.NOT_NULL_VIOLATION
                and e.orig.diag.column_name == "subreddit_id"
            ):
                msg = "/r/{} is unknown"

            if not msg:
                raise e

            errecho("\t" + msg.format(triple[0]))
        else:
            errecho("\tAdded to /r/{}".format(triple[0]))


class SubStatus(enum.Enum):
    OK = enum.auto()
    NONEXISTENT = enum.auto()
    BANNED = enum.auto()
    PRIVATE = enum.auto()

    def __bool__(self):
        return self is __class__.OK


def subreddit_or_status(reddit, name):
    subreddit = reddit.subreddit(name)

    status = subreddit_status(subreddit)

    if not status:
        return status

    return subreddit


def subreddit_status(subreddit, reddit=None):
    if not isinstance(subreddit, praw.models.Subreddit):
        subreddit = reddit.subreddit(subreddit)

    try:
        subreddit._fetch()
    except exceptions.PrawcoreException as exp:
        return subreddit_status_handle(exp)
    return SubStatus.OK


def subreddit_status_handle(exp):
    if isinstance(exp, exceptions.Redirect):
        return SubStatus.NONEXISTENT
    elif isinstance(exp, exceptions.NotFound):
        return SubStatus.BANNED
    elif isinstance(exp, exceptions.Forbidden):
        return SubStatus.PRIVATE

    raise exp
