import tomlkit
import click
from errantbot import extract, helper
from click.types import StringParamType
import psycopg2
import psycopg2.extras
from tabulate import tabulate
import itertools


class DownCaseType(click.ParamType):
    name = "case-insensitive text"

    def convert(self, value, param, ctx):
        s = StringParamType.convert(self, value, param, ctx)

        return s.lower()


DownCase = DownCaseType()


def connect_db():
    click.echo("Connecting to database...", err=True)

    db = None
    with open("secrets.toml") as secrets_file:
        secrets = tomlkit.parse(secrets_file.read())["database"]

        db = psycopg2.connect(
            user=secrets["user"],
            password=secrets["password"],
            dbname=secrets["name"],
            cursor_factory=psycopg2.extras.DictCursor,
        )
    return db


@click.group()
def cli():
    pass


@cli.command()
@click.argument("source-url", required=True)
@click.argument("subreddits", nargs=-1, type=DownCase)
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

    subs_to_tags = helper.parse_subreddits(subreddits)
    db = connect_db()

    if not series:
        helper.check_series(db, subs_to_tags)

    row_id = helper.save_work(
        db,
        work.title,
        work.series,
        work.artist,
        work.source_url,
        None,
        None,
        work.nsfw,
        work.image_url,
        subs_to_tags,
    )

    helper.upload_to_imgur(db, row_id)

    if len(subreddits) > 0:
        helper.post_to_all_subreddits(db, row_id)


@cli.command()
@click.argument("title")
@click.argument("artist")
@click.argument("source-url")
@click.argument("source-image-url")
@click.argument("subreddits", nargs=-1, type=DownCase)
@click.option("--series", "-s")
@click.option("--nsfw/--sfw")
def add_custom(title, artist, source_url, source_image_url, subreddits, series, nsfw):
    subs_to_tags = helper.parse_subreddits(subreddits)
    db = connect_db()

    if not series:
        helper.check_series(subs_to_tags)

    work_id = helper.save_work(
        db,
        title,
        series,
        artist,
        source_url,
        None,
        None,
        nsfw,
        source_image_url,
        subs_to_tags,
    )

    helper.upload_to_imgur(db, work_id)

    if len(subreddits) > 0:
        helper.post_to_all_subreddits(db, work_id)


@cli.command()
@click.argument("name", type=DownCase)
@click.option("--tag-series", "-t", is_flag=True)
@click.option("--flair-id", "-f")
@click.option("--rehost", "-r", is_flag=True)
def add_sub(name, tag_series, flair_id, rehost):
    db = connect_db()

    helper.add_subreddit(db, name, tag_series, flair_id, not rehost)


@cli.command()
@click.argument("work-id", type=int)
@click.argument("subreddits", nargs=-1, type=DownCase)
def crosspost(work_id, subreddits):
    db = connect_db()

    subs_to_tags = helper.parse_subreddits(subreddits)

    helper.add_work_to_subreddits(db, work_id, subs_to_tags)

    helper.post_to_all_subreddits(db, work_id)


@cli.command()
@click.argument("work-id", type=int)
def retry_post(work_id):
    db = connect_db()

    helper.post_to_all_subreddits(db, work_id)


@cli.command()
@click.argument("work-id", type=int)
def retry_upload(work_id):
    db = connect_db()

    helper.upload_to_imgur(db, work_id)


@cli.command()
@click.argument("subreddit-name", type=DownCase)
def list_flairs(subreddit_name):
    reddit = helper.connect_reddit()

    sub = reddit.subreddit(subreddit_name)

    for flair in sub.flair.link_templates:
        if not flair["mod_only"]:
            click.echo("{text}:\t{id}".format(**flair))


@cli.command("extract")
@click.argument("url")
def _extract(url):
    work = extract.auto(url)

    for field in work._fields:
        attr = getattr(work, field)

        attr = "'" + attr + "'" if type(attr) == str else attr
        click.echo("{}:\t{}".format(field, attr))


@cli.command()
@click.argument("names", nargs=-1)
@click.pass_context
def list_subs(ctx, names):
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


if __name__ == "__main__":
    cli()
