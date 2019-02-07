import tomlkit
import click
from errantbot import apis, extract, helper
from click.types import StringParamType
import psycopg2
import psycopg2.extras


class DownCaseType(click.ParamType):
    name = "case-insensitive text"

    def convert(self, value, param, ctx):
        s = StringParamType.convert(self, value, param, ctx)

        return s.lower()


DownCase = DownCaseType()


def connect_reddit():
    click.echo("Connecting to Reddit...")

    reddit = None

    with open("secrets.toml") as secrets_file:
        secrets = tomlkit.parse(secrets_file.read())

        reddit = apis.Reddit(secrets["reddit"])

    reddit.authenticate()

    return reddit.reddit


def connect_imgur():
    click.echo("Connecting to Imgur...")
    imgur = None

    with open("secrets.toml") as secrets_file:
        secrets = tomlkit.parse(secrets_file.read())["imgur"]

        imgur = apis.Imgur(secrets["client_id"], secrets["client_secret"])

    imgur.authenticate()

    return imgur


def connect_db():
    click.echo("Connecting to database...")

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

    cursor = db.cursor()

    if not series:

        cursor.execute(
            """SELECT name FROM subreddits WHERE name IN %s
            AND tag_series = true""",
            (tuple(map(lambda sub: sub[0], subs_to_tags)),),
        )

        tagged_subs = cursor.fetchall()

        length = len(tagged_subs)

        if length > 0:
            raise click.ClickException(
                "Subreddit{} {} require{} a series".format(
                    "s" if length > 1 else "",
                    ", ".join(map(lambda sub: "'" + sub["name"] + "'", tagged_subs)),
                    "" if length > 1 else "s",
                )
            )

    imgur = None

    click.echo("Saving to database... ")
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

    click.echo("Uploading to Imgur... ")
    imgur = connect_imgur()
    helper.upload_to_imgur(db, row_id, imgur)

    if len(subreddits) > 0:
        reddit = connect_reddit()
        helper.post_work_to_all(db, row_id, reddit)


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

    cursor = db.cursor()

    if not series:

        cursor.execute(
            """SELECT name FROM subreddits WHERE name IN %s
            AND tag_series = true""",
            (tuple(map(lambda sub: sub[0], subs_to_tags)),),
        )

        tagged_subs = cursor.fetchall()

        length = len(tagged_subs)

        if length > 0:
            raise click.ClickException(
                "Subreddit{} {} require{} a series".format(
                    "s" if length > 1 else "",
                    ", ".join(map(lambda sub: "'" + sub["name"] + "'", tagged_subs)),
                    "" if length > 1 else "s",
                )
            )

    imgur = None

    click.echo("Saving to database... ")
    row_id = helper.save_work(
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

    click.echo("Uploading to Imgur... ")
    imgur = connect_imgur()
    helper.upload_to_imgur(db, row_id, imgur)

    if len(subreddits) > 0:
        reddit = connect_reddit()
        helper.post_work_to_all(db, row_id, reddit)


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

    helper.post_work_to_all(db, work_id, connect_reddit())


@cli.command()
@click.argument("work-id", type=int)
def retry(work_id):
    db = connect_db()

    helper.post_work_to_all(db, work_id, connect_reddit())


@cli.command()
@click.argument("subreddit-name", type=DownCase)
def list_flairs(subreddit_name):
    reddit = connect_reddit()

    sub = reddit.subreddit(subreddit_name)

    for flair in sub.flair.link_templates:
        if not flair["mod_only"]:
            click.echo("{text}:\t{id}".format(**flair))


@cli.command("extract")
@click.argument("url")
def _extract(url):
    work = extract.auto(url)

    for field in work._fields:
        click.echo("{}\t{}".format(field, getattr(work, field)))


if __name__ == "__main__":
    cli()
