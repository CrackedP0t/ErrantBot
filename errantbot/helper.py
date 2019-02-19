import click
import tomlkit
from errantbot import apis
from datetime import timedelta, datetime
import regex


class Subreddits:
    find_name = regex.compile(r"^[^@#]*")
    find_flair_id = regex.compile(r"@([^#]*)")
    find_tag = regex.compile(r"#(.*)$")

    val_name = regex.compile(r"[a-zA-Z0-9_]+")
    val_flair_id = regex.compile(r"([a-f0-9-]){8}-(?1){4}-(?1){4}-(?1){4}-(?1){12}")

    def __len__(self):
        return self.length

    def __init__(self, list_of_text):
        self.names = []
        self.flairs = []
        self.tags = []

        self.length = len(list_of_text)

        for text in list_of_text:
            name = self.find_name.search(text)
            if not name:
                raise click.ClickException(
                    "Subreddit name required in argument '{}'".format(text)
                )
            name = name[0]
            if not self.val_name.fullmatch(name):
                raise click.ClickException("Invalid name '{}'".format(name))

            flair_id = self.find_flair_id.search(text)
            if flair_id:
                flair_id = flair_id[1]
                if not self.val_flair_id.fullmatch(flair_id):
                    raise click.ClickException("Invalid flair id '{}'".format(flair_id))

            tag = self.find_tag.search(text)
            if tag:
                tag = tag[1]

            self.names.append(name)
            self.flairs.append(flair_id)
            self.tags.append(tag)

        # Tuple for Psycopg's adaptation

        self.names = tuple(self.names)
        self.flairs = tuple(self.flairs)
        self.tags = tuple(self.tags)

        self.n_f_t = tuple(
            (self.names[i], self.flairs[i], self.tags[i]) for i in range(self.length)
        )


def errecho(*args, **kwargs):
    kwargs["err"] = True
    click.echo(*args, **kwargs)


# def escape_values(db, seq):
# return (b",".join(map(db.literal, seq))).decode()


def connect_imgur():
    click.echo("Connecting to Imgur...", err=True)
    imgur = None

    with open("secrets.toml") as secrets_file:
        secrets = tomlkit.parse(secrets_file.read())["imgur"]

        imgur = apis.Imgur(secrets["client_id"], secrets["client_secret"])

    imgur.authenticate()

    return imgur


def connect_reddit():
    errecho("Connecting to Reddit...")

    reddit = None

    with open("secrets.toml") as secrets_file:
        secrets = tomlkit.parse(secrets_file.read())

        reddit = apis.Reddit(secrets["reddit"])

    reddit.authenticate()

    return reddit.reddit


def post_to_all_subreddits(db, work_id):
    reddit = connect_reddit()

    errecho("Posting...")

    cursor = db.cursor()

    cursor.execute(
        """SELECT title, series, artist, source_url, imgur_image_url, nsfw,
        source_image_url, name, tag_series, custom_tag, submissions.id,
        COALESCE(submissions.flair_id, subreddits.flair_id) AS flair_id,
        rehost, last_submission_on
        FROM works
        INNER JOIN submissions ON
        submissions.reddit_id is NULL AND
        submissions.work_id = works.id AND works.id = %s
        INNER JOIN subreddits
        ON submissions.subreddit_id = subreddits.id""",
        (work_id,),
    )

    rows = cursor.fetchall()

    for row in rows:
        if not row["series"] and row["tag_series"]:
            errecho("\tSubreddit '{}' requires a series; skipped".format(row["name"]))
            continue

        if row["last_submission_on"]:
            since = datetime.utcnow() - row["last_submission_on"]
            if since < timedelta(days=1):
                wait = timedelta(days=1) - since
                wait = timedelta(wait.days, wait.seconds)
                errecho(
                    "\tSubmitted to '{}' less than one day ago; you can try again in {}".format(
                        row["name"], wait
                    )
                )

                continue

        sub = reddit.subreddit(row["name"])

        title = "{title} ({artist}){series_tag}{tag}".format(
            series_tag=" [" + row["series"] + "]" if row["tag_series"] else "",
            tag=" [" + row["custom_tag"] + "]" if row["custom_tag"] else "",
            **row
        )

        url = row["imgur_image_url" if row["rehost"] else "source_image_url"]

        submission = sub.submit(title, url=url, flair_id=row["flair_id"])

        errecho("\tSubmitted to '{}' at {}".format(row["name"], submission.permalink))

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
    subreddits,
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

    add_submissions(db, work_id, subreddits)

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


def add_submissions(db, work_id, subreddits):
    subreddits_exist(db, subreddits.names)

    cursor = db.cursor()

    # Fairly jank, but works
    cursor.execute(
        """INSERT INTO submissions (work_id, subreddit_id, flair_id, custom_tag)
        SELECT %s, id, data.flair_id, tag FROM subreddits
        INNER JOIN (VALUES {}) AS data (subname, flair_id, tag)
        ON subreddits.name = data.subname
        ON CONFLICT ON CONSTRAINT submissions_work_id_subreddit_id_key DO NOTHING""".format(
            ", ".join(["%s"] * len(subreddits.n_f_t))
        ),
        (work_id, *subreddits.n_f_t),
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
