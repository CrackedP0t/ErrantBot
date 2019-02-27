import click
from . import extract, helper as h, paramtypes as types
import psycopg2
import psycopg2.extras
from tabulate import tabulate
import itertools


def connect_db():
    click.echo("Connecting to database...", err=True)

    secrets = h.get_secrets()["database"]

    return psycopg2.connect(
        user=secrets["user"],
        password=secrets["password"],
        dbname=secrets["name"],
        cursor_factory=psycopg2.extras.DictCursor,
    )


@click.group()
def cli():
    pass


@cli.command()
@click.argument("source-url", required=True, type=types.url)
@click.argument("subreddits", nargs=-1, type=types.submission)
@click.option("--title", "-t")
@click.option("--artist", "-a")
@click.option("--series", "-s")
@click.option("--nsfw/--sfw", default=None)
def add(source_url, subreddits, title, artist, series, nsfw):
    work = extract.auto(source_url)

    work = extract.Work(
        title or work.title,
        artist or work.artist,
        series or work.series,
        nsfw or work.nsfw,
        work.image_url,
        work.source_url,
    )

    subreddits = h.Subreddits(subreddits)
    db = connect_db()

    row_id = h.save_work(
        db,
        work.title,
        work.series,
        work.artist,
        work.source_url,
        None,
        None,
        work.nsfw,
        work.image_url,
        subreddits,
    )

    h.upload_to_imgur(db, row_id)

    h.post_to_all_subreddits(db, row_id)


@cli.command()
@click.argument("title", required=True)
@click.argument("artist", required=True)
@click.argument("source-url", type=types.url, required=True)
@click.argument("source-image-url", type=types.url, required=True)
@click.argument("subreddits", nargs=-1, type=types.submission)
@click.option("--series", "-s")
@click.option("--nsfw/--sfw")
def add_custom(title, artist, source_url, source_image_url, subreddits, series, nsfw):
    subreddits = h.Subreddits(subreddits)
    db = connect_db()

    work_id = h.save_work(
        db,
        title,
        series,
        artist,
        source_url,
        None,
        None,
        nsfw,
        source_image_url,
        subreddits,
    )

    h.upload_to_imgur(db, work_id)

    h.post_to_all_subreddits(db, work_id)


@cli.command()
@click.argument("name", required=True, type=types.subreddit)
@click.option("--tag-series/--no-tag-series", "-s/-S", default=False)
@click.option("--flair-id", "-f", type=types.flair_id)
@click.option("--rehost/--no-rehost", "-r/-R", default=True)
@click.option("--require-flair/--no-require-flair", "-r/-R", default=False)
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
@click.argument("subreddits", nargs=-1, type=types.submission)
def crosspost(work_id, subreddits):
    db = connect_db()

    subreddits = h.Subreddits(subreddits)

    h.add_submissions(db, work_id, subreddits)

    h.post_to_all_subreddits(db, work_id)


@cli.command()
@click.argument("work-id", type=int, required=True)
def retry_post(work_id):
    db = connect_db()

    h.post_to_all_subreddits(db, work_id, True)


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
def list_subs(names):
    db = connect_db()

    cursor = db.cursor(cursor_factory=psycopg2.extensions.cursor)

    if len(names) > 0:
        where = " WHERE subreddits.name IN %s"
    else:
        where = ""

    cursor.execute(
        """SELECT id, name, tag_series, flair_id, rehost, last_submission_on,
        (SELECT COUNT(*) FROM submissions WHERE subreddit_id = subreddits.id) post_count
        FROM subreddits{} ORDER BY id""".format(
            where
        ),
        (names,),
    )
    rows = cursor.fetchall()

    cursor.execute(
        """SELECT column_name FROM information_schema.columns WHERE
        table_name='subreddits' ORDER BY ordinal_position"""
    )
    columns = itertools.chain(
        map(lambda col: col[0], cursor.fetchall()), ("post_count",)
    )

    click.echo(tabulate(rows, headers=columns))


@cli.command()
def test():
    reddit = h.connect_reddit()
    h.subreddit_status("rule34", reddit)


if __name__ == "__main__":
    cli()
