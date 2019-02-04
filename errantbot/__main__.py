import MySQLdb
import tomlkit
import click

from errantbot import apis, extract, post


def connect_db():
    return MySQLdb.connect(user="root", passwd="", db="errant")


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

    work = extract.Work(title or work.title,
                        artist or work.artist,
                        series or work.series,
                        nsfw or work.nsfw,
                        work.image_url,
                        work.source_url)


    sublist = subreddits.split(",")

    db = connect_db()

    reddit = None
    imgur = None

    with open("secrets.toml") as secrets_file:
        secrets = tomlkit.parse(secrets_file.read())

        reddit = apis.Reddit(secrets["reddit"])

        imgur = apis.Imgur(secrets["imgur"]["client_id"],
                           secrets["imgur"]["client_secret"])

    npost = post.Post(work, sublist)

    click.echo("Uploading to Imgur... ", nl=False, err=True)

    imgur.authenticate()

    npost.upload(imgur)

    click.echo("done", nl=True, err=True)

    click.echo("Saving to database... ", nl=False, err=True)

    npost.save(db)

    click.echo("done", nl=True, err=True)

    click.echo("Posting to Reddit... ", nl=False, err=True)

    reddit.authenticate()

    npost.post(db, reddit.reddit)

    click.echo("done", nl=True, err=True)


@cli.command("add-sub")
@click.argument("name")
@click.option("--tag-series", "-t", is_flag=True)
@click.option("--flair-id")
def add_sub(name, tag_series, flair_id):
    db = connect_db()

    db.cursor().execute("""INSERT INTO subreddits (name, tag_series, flair_id) VALUES (%s, %s, %s)""",
                        (name, tag_series, flair_id))

    db.commit()


if __name__ == "__main__":
    cli()
