import MySQLdb
from MySQLdb import cursors
import tomlkit
import click
from errantbot import apis, extract, helper


def connect_reddit():
    reddit = None

    with open("secrets.toml") as secrets_file:
        secrets = tomlkit.parse(secrets_file.read())

        reddit = apis.Reddit(secrets["reddit"])

    reddit.authenticate()

    return reddit.reddit


def connect_imgur():
    imgur = None

    with open("secrets.toml") as secrets_file:
        secrets = tomlkit.parse(secrets_file.read())

        imgur = apis.Imgur(
            secrets["imgur"]["client_id"], secrets["imgur"]["client_secret"]
        )

    imgur.authenticate()

    return imgur


def connect_db():
    return MySQLdb.connect(
        user="root", passwd="", db="errant", cursorclass=cursors.DictCursor
    )


@click.group()
def cli():
    pass


@cli.command()
@click.option("--title", "-t")
@click.argument("source-url", nargs=1)
@click.option("--artist", "-a")
@click.option("--series", "-s")
@click.option("--nsfw/--sfw", default=None)
@click.option("--subreddits", "-r", default="")
def add(source_url, title, artist, series, nsfw, subreddits):
    work = extract.auto(source_url)

    work = extract.Work(
        title or work.title,
        artist or work.artist,
        series or work.series,
        nsfw or work.nsfw,
        work.image_url,
        work.source_url,
    )

    sublist = subreddits.split(",")

    db = connect_db()

    cursor = db.cursor()

    if not series:

        cursor.execute(
            """SELECT name FROM subreddits WHERE name IN ({})
            AND tag_series = 1""".format(
                ", ".join(map(lambda sub: "'" + sub + "'", sublist))
            )
        )

        tagged_subs = cursor.fetchall()

        length = len(tagged_subs)

        if length > 0:
            raise click.UsageError(
                "Subreddit{} {} require{} a series".format(
                    "s" if length > 1 else "",
                    ", ".join(map(lambda sub: "'" + sub["name"] + "'", tagged_subs)),
                    "" if length > 1 else "s",
                )
            )

    imgur = None

    click.echo("Saving to database... ", nl=False, err=True)
    row_id = helper.save_post(
        db,
        work.title,
        work.series,
        work.artist,
        work.source_url,
        None,
        None,
        work.nsfw,
        work.image_url,
        sublist,
    )
    click.echo("done", nl=True, err=True)

    click.echo("Uploading to Imgur... ", nl=False, err=True)
    imgur = connect_imgur()
    helper.upload_to_imgur(db, row_id, imgur)
    click.echo("done", nl=True, err=True)

    click.echo("Posting to Reddit... ", nl=False, err=True)
    reddit = connect_reddit()
    helper.post_to_all(db, row_id, reddit)
    click.echo("done", nl=True, err=True)


@cli.command()
@click.argument("name")
@click.option("--tag-series", "-t", is_flag=True)
@click.option("--flair-id", "-f")
def add_sub(name, tag_series, flair_id):
    db = connect_db()

    helper.add_subreddit(db, name, tag_series, flair_id)


@cli.command()
@click.argument("post-id", type=int)
@click.argument("subreddits")
def crosspost(post_id, subreddits):
    db = connect_db()

    helper.add_post_to_subreddits(db, post_id, subreddits)

    helper.post_to_all(db, post_id, connect_reddit())


@cli.command()
@click.argument("post-id", type=int)
def retry(post_id):
    db = connect_db()

    helper.post_to_all(db, post_id, connect_reddit())


@cli.command()
@click.argument("subreddit-name")
def list_flairs(subreddit_name):
    reddit = connect_reddit()

    sub = reddit.subreddit(subreddit_name)

    for flair in sub.flair.link_templates:
        if not flair["mod_only"]:
            click.echo("{text}:\t{id}".format(**flair))


if __name__ == "__main__":
    cli()
