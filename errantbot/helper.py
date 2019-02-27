import click
import tomlkit
from . import apis
from datetime import timedelta, datetime
from prawcore import exceptions
import praw
import enum
import psycopg2


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


def connect_imgur():
    click.echo("Connecting to Imgur...", err=True)
    secrets = get_secrets()["imgur"]

    imgur = apis.Imgur(secrets["client_id"], secrets["client_secret"])

    imgur.authenticate()

    errecho("\tAuthentication complete")

    return imgur


def connect_reddit():
    errecho("Connecting to Reddit...")

    reddit = apis.Reddit(get_secrets()["reddit"])

    reddit.authenticate()

    return reddit.reddit


def post_submissions(db, work_id, submissions=None):
    cursor = db.cursor()

    cursor.execute(
        """SELECT title, series, artist, source_url, imgur_image_url, nsfw,
        source_image_url, name, tag_series, custom_tag, submissions.id,
        COALESCE(submissions.flair_id, subreddits.flair_id) AS flair_id,
        rehost, last_submission_on
        FROM works INNER JOIN submissions ON
        works.id = %s AND
        submissions.reddit_id IS NULL AND
        submissions.work_id = works.id
        INNER JOIN subreddits ON
        submissions.subreddit_id = subreddits.id"""
        + (" AND subreddits.name IN %s" if submissions else ""),
        (work_id, submissions.names) if submissions else (work_id,),
    )

    rows = cursor.fetchall()

    if len(rows) == 0:
        return

    reddit = connect_reddit()

    errecho("Posting...")

    for row in rows:
        if not row["series"] and row["tag_series"]:
            errecho("\t/r/{} requires a series".format(row["name"]))
            continue

        if row["last_submission_on"]:
            since = datetime.utcnow() - row["last_submission_on"]
            if since < timedelta(days=1):
                wait = timedelta(days=1) - since
                wait = timedelta(wait.days, wait.seconds)
                errecho(
                    "\tSubmitted to /r/{} less than one day ago; "
                    "you can try again in {}".format(row["name"], wait)
                )

                continue

        sub = reddit.subreddit(row["name"])

        title = "{title} ({artist}){series_tag}{tag}".format(
            series_tag=" [" + row["series"] + "]" if row["tag_series"] else "",
            tag=" " + row["custom_tag"] if row["custom_tag"] else "",
            **row
        )

        url = row["imgur_image_url" if row["rehost"] else "source_image_url"]

        submission = sub.submit(title, url=url, flair_id=row["flair_id"])

        errecho(
            "\tSubmitted to /r/{} at https://reddit.com{}".format(
                row["name"], submission.permalink
            )
        )

        if row["nsfw"]:
            submission.mod.nsfw()

        submission.reply("[Source]({})".format(row["source_url"]))

        cursor.execute(
            """UPDATE submissions SET reddit_id = %s, submitted_on = to_timestamp(%s)
            WHERE id = %s""",
            (submission.id, int(submission.created_utc), row["id"]),
        )

        db.commit()


def upload_to_imgur(db, work_id):
    imgur = connect_imgur()

    errecho("Uploading to Imgur...")

    cursor = db.cursor()

    cursor.execute(
        """SELECT title, artist, source_image_url, source_url, imgur_image_url
        FROM works WHERE id=%s""",
        (work_id,),
    )
    row = cursor.fetchone()

    if row is None:
        raise click.ClickException("Work id {} does not exist".format(work_id))

    if row["imgur_image_url"]:
        raise click.ClickException(
            "Work id {} has already been uploaded at {}".format(
                work_id, row["imgur_image_url"]
            )
        )

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

    errecho("\tUploaded at {}".format(data["link"]))


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
):
    errecho("Saving to database...")

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

    errecho("\tSaved with id {}".format(work_id))

    return work_id


def add_subreddit(db, name, tag_series, flair_id, rehost, require_flair, require_tag):
    cursor = db.cursor()

    cursor.execute(
        """INSERT INTO subreddits (name, tag_series, flair_id,
        rehost, require_flair, require_tag) VALUES (%s, %s, %s, %s, %s, %s)
        ON CONFLICT (name) DO UPDATE SET tag_series = %s, flair_id = %s, rehost = %s,
        require_flair = %s, require_tag = %s""",
        (name,) + (tag_series, flair_id, rehost, require_flair, require_tag) * 2
    )
    db.commit()


def add_submissions(db, work_id, submissions):
    errecho("Saving to database...")

    cursor = db.cursor()

    for triple in submissions.n_f_t:
        if not subreddit_known(db, triple[0]):
            errecho("\t/r/{} is unknown".format(triple[0]))
            continue
        try:
            cursor.execute(
                """INSERT INTO submissions (work_id, subreddit_id, flair_id, custom_tag)
                SELECT %s, id, data.flair_id, tag FROM subreddits
                INNER JOIN (VALUES %s) AS data (subname, flair_id, tag)
                ON subreddits.name = data.subname""",
                (work_id, triple),
            )
        except psycopg2.IntegrityError as e:
            msg = {
                "check_require_flair": "/r/{} requires a flair",
                "check_require_tag": "/r/{} requires a tag",
                "already_exists": "/r/{} already has this work",
            }.get(e.diag.constraint_name, None)

            if not msg:
                raise e

            errecho("\t" + msg.format(triple[0]))
            db.rollback()
        else:
            db.commit()


def subreddit_known(db, subreddit_name):
    cursor = db.cursor()

    cursor.execute(
        """SELECT id FROM subreddits WHERE name = %s""",
        (subreddit_name,),
    )

    row = cursor.fetchone()

    return bool(row)


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
