import click
from . import extract, helper as h, paramtypes as types
import psycopg2
import psycopg2.extras
from tabulate import tabulate
from collections import namedtuple
import validators as val
from praw.models import Submission


@click.group()
@click.pass_context
def cli(ctx):
    ctx.obj = h.Connections()


@cli.command()
@click.pass_obj
@click.argument("source-url", required=True, type=types.url)
@click.argument("submissions", nargs=-1, type=types.submission)
@click.option("--title", "-t")
@click.option("--artist", "-a")
@click.option("--series", "-s")
@click.option("--nsfw/--sfw", "-n/-N", default=None)
@click.option("--index", "-i", default=0, type=int)
@click.option("--album", "-l", is_flag=True)
@click.option("--post/--no-post", "-p/-P", default=True)
def add(con, source_url, submissions, title, artist, series, nsfw, index, album, post):
    work = extract.auto(source_url, {"index": index, "album": album})

    work = extract.Work(
        title or work.title,
        artist or work.artist,
        series or work.series,
        nsfw or work.nsfw,
        work.image_url,
        work.source_url,
    )

    submissions = h.Submissions(submissions)

    work_id = h.save_work(
        con.db,
        work.title,
        work.series,
        work.artist,
        work.source_url,
        work.nsfw,
        work.image_url,
    )

    h.add_submissions(con.db, work_id, submissions)

    h.upload_to_imgur(con, work_id)

    if post:
        h.post_submissions(con, work_id)


@cli.command()
@click.pass_obj
@click.argument("title", required=True)
@click.argument("artist", required=True)
@click.argument("source-url", type=types.url, required=True)
@click.argument("source-image-url", type=types.url, required=True)
@click.argument("submissions", nargs=-1, type=types.submission)
@click.option("--series", "-s")
@click.option("--nsfw/--sfw", "-n/-N")
def add_custom(
    con, title, artist, source_url, source_image_url, submissions, series, nsfw
):
    submissions = h.Submissions(submissions)

    work_id = h.save_work(
        con.db, title, series, artist, source_url, nsfw, source_image_url
    )

    h.add_submissions(con.db, work_id, submissions)

    h.upload_to_imgur(con.db, work_id)

    h.post_submissions(con, work_id)


@cli.command()
@click.pass_obj
@click.argument("name", required=True, type=types.subreddit)
@click.option("--tag-series/--no-tag-series", "-s/-S", default=False)
@click.option("--flair-id", "-f", type=types.flair_id)
@click.option("--rehost/--no-rehost", "-r/-R", default=True)
@click.option("--require-flair/--no-require-flair", "-q/-Q", default=False)
@click.option("--require-tag/--no-require-tag", "-t/-T", default=False)
@click.option("--space-out/--no-space-out", "-o/-O", default=True)
def add_sub(
    con, name, tag_series, flair_id, rehost, require_flair, require_tag, space_out
):
    status = h.subreddit_status(name, con.reddit)

    if not status:
        raise click.ClickException("/r/{} is {}".format(name, status.name.lower()))

    h.add_subreddit(
        con.db,
        name,
        tag_series,
        flair_id,
        rehost,
        require_flair,
        require_tag,
        space_out,
    )


@cli.command()
@click.pass_obj
@click.argument("work-id", type=int, required=True)
@click.argument("submissions", nargs=-1, type=types.submission)
def crosspost(con, work_id, submissions):
    submissions = h.Submissions(submissions)

    h.add_submissions(con.db, work_id, submissions)

    h.post_submissions(con, work_id, submissions)


@cli.command()
@click.pass_obj
@click.argument("submissions", nargs=-1, type=types.submission)
def crosspost_last(con, submissions):
    submissions = h.Submissions(submissions)

    work_id = h.get_last(con.db, "works")

    h.add_submissions(con.db, work_id, submissions)

    h.post_submissions(con, work_id, submissions)


@cli.command()
@click.pass_obj
@click.argument("work-ids", type=int, nargs=-1)
@click.option("--last", "-l", is_flag=True)
def retry_post(con, work_ids, last):
    h.post_submissions(con, work_ids, last=last)


@cli.command()
@click.pass_obj
def retry_all_posts(con):
    h.post_submissions(con, all=True)


@cli.command()
@click.pass_obj
def retry_all_uploads(con):
    h.upload_to_imgur(con.db, all=True)


@cli.command()
@click.pass_obj
@click.argument("work-ids", type=int, nargs=-1)
@click.option("--last", "-l", is_flag=True)
def retry_upload(con, work_ids, last):
    h.upload_to_imgur(con.db, work_ids, last=last)


@cli.command()
@click.pass_obj
@click.argument("subreddit-name", type=types.subreddit, required=True)
def list_flairs(con, subreddit_name):
    sub = h.subreddit_or_status(con.reddit, subreddit_name)

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
@click.option("--index", "-i", default=0, type=int)
@click.option("--album", "-l", is_flag=True)
def _extract(url, index, album):
    work = extract.auto(url, {"index": index, "album": album})

    for field in work._fields:
        attr = getattr(work, field)

        attr = "'" + attr + "'" if type(attr) == str else attr
        click.echo("{}:\t{}".format(field, attr))


@cli.command()
@click.pass_obj
@click.argument("names", nargs=-1, type=types.subreddit)
@click.option("--ready/--not-ready", "-r/-R", default=None)
def list_subs(con, names, ready):
    cursor = con.db.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    Opt = namedtuple("Opt", ("check", "cond"))

    opts = (
        Opt(len(names) > 0, "subreddits.name IN %s"),
        Opt(ready is True, "last_submission_on < NOW() - INTERVAL '1 day'"),
        Opt(ready is False, "last_submission_on > NOW() - INTERVAL '1 day'"),
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
@click.pass_obj
def list_works(con):
    cursor = con.db.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    cursor.execute(
        """SELECT id, artist, title, series, nsfw, source_url, imgur_url
        FROM works"""
    )

    rows = cursor.fetchall()

    click.echo(tabulate(rows, headers="keys"))


@cli.command()
@click.pass_obj
@click.option("--reddit-id", "-r", "id_type", flag_value="reddit", default=True)
@click.option("--submission-id", "-s", "id_type", flag_value="submission")
@click.option("--delete/--no-delete", "-d/-D", default=True)
@click.argument("post-id")
def delete_post(con, id_type, delete, post_id):
    cursor = con.db.cursor()

    if id_type == "submission":
        submission_id = post_id

        cursor.execute(
            "SELECT reddit_id FROM submissions WHERE id = %s", (submission_id,)
        )
        row = cursor.fetchone()

        if row is None:
            raise click.ClickException(
                "Submission #{} does not exist".format(submission_id)
            )

        reddit_id = row["reddit_id"]

        if reddit_id is None:
            raise click.ClickException(
                "Submission #{} has no reddit post".format(submission_id)
            )
    else:
        reddit_id = post_id

        if val.url(reddit_id):
            reddit_id = Submission.id_from_url(reddit_id)

    if delete:
        sub = con.reddit.submission(reddit_id)

        sub.delete()

        sub.comments.replace_more(limit=None)

        for comment in sub.comments.list():
            if comment.author == con.reddit.user.me():
                comment.delete()

    if submission_id:
        where = "id = %s"
    else:
        where = "reddit_id = %s"

    cursor.execute(
        "UPDATE submissions SET reddit_id = NULL, submitted_on = NULL WHERE " + where,
        (submission_id or reddit_id,),
    )
    con.db.commit()


if __name__ == "__main__":
    cli()
