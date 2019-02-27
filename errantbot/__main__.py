import click
from . import extract, helper as h, paramtypes as types
import psycopg2
import psycopg2.extras
from tabulate import tabulate
import itertools
from collections import namedtuple


def connect_db():
    h.errecho("Connecting to database...")

    secrets = h.get_secrets()["database"]

    db = psycopg2.connect(
        user=secrets["user"],
        password=secrets["password"],
        dbname=secrets["name"],
        cursor_factory=psycopg2.extras.DictCursor,
    )

    h.errecho("\tConnected")

    return db


@click.group()
def cli():
    pass


@cli.command()
@click.argument("source-url", required=True, type=types.url)
@click.argument("submissions", nargs=-1, type=types.submission)
@click.option("--title", "-t")
@click.option("--artist", "-a")
@click.option("--series", "-s")
@click.option("--nsfw/--sfw", default=None)
def add(source_url, submissions, title, artist, series, nsfw):
    work = extract.auto(source_url)

    work = extract.Work(
        title or work.title,
        artist or work.artist,
        series or work.series,
        nsfw or work.nsfw,
        work.image_url,
        work.source_url,
    )

    submissions = h.Submissions(submissions)
    db = connect_db()

    work_id = h.save_work(
        db,
        work.title,
        work.series,
        work.artist,
        work.source_url,
        None,
        None,
        work.nsfw,
        work.image_url,
    )

    h.add_submissions(db, work_id, submissions)

    h.upload_to_imgur(db, work_id)

    h.post_submissions(db, work_id)


@cli.command()
@click.argument("title", required=True)
@click.argument("artist", required=True)
@click.argument("source-url", type=types.url, required=True)
@click.argument("source-image-url", type=types.url, required=True)
@click.argument("submissions", nargs=-1, type=types.submission)
@click.option("--series", "-s")
@click.option("--nsfw/--sfw")
def add_custom(title, artist, source_url, source_image_url, submissions, series, nsfw):
    submissions = h.Submissions(submissions)
    db = connect_db()

    work_id = h.save_work(
        db, title, series, artist, source_url, None, None, nsfw, source_image_url
    )

    h.add_submissions(db, work_id, submissions)

    h.upload_to_imgur(db, work_id)

    h.post_to_submissions(db, work_id)


@cli.command()
@click.argument("name", required=True, type=types.subreddit)
@click.option("--tag-series/--no-tag-series", "-s/-S", default=False)
@click.option("--flair-id", "-f", type=types.flair_id)
@click.option("--rehost/--no-rehost", "-r/-R", default=True)
@click.option("--require-flair/--no-require-flair", "-q/-Q", default=False)
@click.option("--require-tag/--no-require-tag", "-t/-T", default=False)
def add_sub(name, tag_series, flair_id, rehost, require_flair, require_tag):
    reddit = h.connect_reddit()

    status = h.subreddit_status(name, reddit)

    if not status:
        raise click.ClickException("/r/{} is {}".format(name, status.name.lower()))

    db = connect_db()

    h.add_subreddit(db, name, tag_series, flair_id, rehost, require_flair, require_tag)


@cli.command()
@click.argument("work-id", type=int, required=True)
@click.argument("submissions", nargs=-1, type=types.submission)
def crosspost(work_id, submissions):
    db = connect_db()

    submissions = h.Submissions(submissions)

    h.add_submissions(db, work_id, submissions)

    h.post_submissions(db, work_id, submissions)


@cli.command()
@click.argument("work-id", type=int, required=True)
def retry_post(work_id):
    db = connect_db()

    h.post_submissions(db, work_id)


@cli.command()
@click.argument("work-id", type=int, required=True)
def retry_upload(work_id):
    db = connect_db()

    h.upload_to_imgur(db, work_id)


@cli.command()
@click.argument("subreddit-name", type=types.subreddit, required=True)
def list_flairs(subreddit_name):
    reddit = h.connect_reddit()

    sub = h.subreddit_or_status(reddit, subreddit_name)

    if not sub:
        click.ClickException("/r/{} is {}".format(subreddit_name, sub.name.lower()))

    if not sub.can_assign_link_flair:
        click.echo(
            "/r/{} does not allow users to assign link flair".format(subreddit_name)
        )

    else:
        columns = map(
            lambda flair: (flair["text"], flair["id"]), sub.flair.link_templates
        )
        click.echo(tabulate(columns, headers=["Text", "ID"]))


@cli.command("extract")
@click.argument("url", required=True, type=types.url)
def _extract(url):
    work = extract.auto(url)

    for field in work._fields:
        attr = getattr(work, field)

        attr = "'" + attr + "'" if type(attr) == str else attr
        click.echo("{}:\t{}".format(field, attr))


@cli.command()
@click.argument("names", nargs=-1, type=types.subreddit)
@click.option("--ready/--not-ready", "-r/-R", default=None)
def list_subs(names, ready):
    db = connect_db()

    cursor = db.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    Opt = namedtuple("Opt", ("check", "cond"))

    opts = (
        Opt(len(names) > 0, "subreddits.name IN %s"),
        Opt(ready is True, "last_submission_on < NOW() - INTERVAL '1 day'"),
        Opt(ready is False, "last_submission_on > NOW() - INTERVAL '1 day'")
    )

    opts = tuple(filter(lambda opt: opt.check, opts))

    if len(opts) == 0:
        where = ""
    else:
        where = " WHERE " + " AND ".join(map(lambda opt: opt.cond, opts))

    query = """SELECT id, name, tag_series, flair_id, rehost, require_flair, require_tag,
    last_submission_on,
    (SELECT COUNT(*) FROM submissions WHERE subreddit_id = subreddits.id) post_count
    FROM subreddits{} ORDER BY id""".format(
        where
    )

    cursor.execute(query, (names,))
    rows = cursor.fetchall()

    click.echo(tabulate(rows, headers="keys"))


@cli.command()
def list_works():
    db = connect_db()

    cursor = db.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    cursor.execute(
        """SELECT id, artist, title, series, nsfw, source_url, imgur_image_url
        FROM works"""
    )

    rows = cursor.fetchall()

    click.echo(tabulate(rows, headers="keys"))


if __name__ == "__main__":
    cli()
