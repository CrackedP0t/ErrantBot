import logging
import warnings

import click
import validators as val
from praw.models import Submission
from sqlalchemy import sql
from tabulate import tabulate

eb_log = logging.getLogger("errantbot")

log = logging.getLogger("errantbot.cli")


from . import extract
from . import helper as h
from . import paramtypes as types


@click.group()
@click.pass_context
def cli(ctx):
    warnings.filterwarnings("ignore", r"Could not parse CHECK constraint text")
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
        con,
        work.title,
        work.series,
        work.artist,
        work.source_url,
        work.nsfw,
        work.image_url,
    )

    h.add_submissions(con, work_id, submissions)

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
        con, title, series, artist, source_url, nsfw, source_image_url
    )

    h.add_submissions(con, work_id, submissions)

    h.upload_to_imgur(con, work_id)

    h.post_submissions(con, work_id)


@cli.command()
@click.pass_obj
@click.argument("names", type=types.subreddit, nargs=-1)
@click.option("--tag-series/--no-tag-series", "-s/-S", default=False)
@click.option("--flair-id", "-f", type=types.flair_id)
@click.option("--rehost/--no-rehost", "-r/-R", default=True)
@click.option("--require-flair/--no-require-flair", "-q/-Q", default=False)
@click.option("--require-tag/--no-require-tag", "-t/-T", default=False)
@click.option("--require-series/--no-require-series", "-e/-E", default=False)
@click.option("--space-out/--no-space-out", "-o/-O", default=True)
@click.option("--disabled/--enabled", "-d/-D", default=False)
def sr(
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
    h.edit_subreddits(
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
    )


@cli.command()
@click.pass_obj
@click.argument("work-id", type=int, required=True)
@click.argument("submissions", nargs=-1, type=types.submission)
def crosspost(con, work_id, submissions):
    submissions = h.Submissions(submissions)

    h.add_submissions(con, work_id, submissions)

    h.post_submissions(con, work_id, submissions)


@cli.command()
@click.pass_obj
@click.argument("submissions", nargs=-1, type=types.submission)
def crosspost_last(con, submissions):
    submissions = h.Submissions(submissions)

    work_id = h.get_last(con, "works")

    h.add_submissions(con, work_id, submissions)

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
    h.post_submissions(con, do_all=True)


@cli.command()
@click.pass_obj
def retry_all_uploads(con):
    h.upload_to_imgur(con, do_all=True)


@cli.command()
@click.pass_obj
@click.argument("work-ids", type=int, nargs=-1)
@click.option("--last", "-l", is_flag=True)
def retry_upload(con, work_ids, last):
    h.upload_to_imgur(con, work_ids, last=last)


@cli.command()
@click.pass_obj
@click.argument("subreddit-name", type=types.subreddit, required=True)
def list_flairs(con, subreddit_name):
    sub = h.subreddit_or_status(con.reddit, subreddit_name)

    if not sub:
        log.warning("/r/%s is %s", subreddit_name, sub.name.lower())

    if not sub.can_assign_link_flair:
        log.warning("/r/%s does not allow users to assign link flair", subreddit_name)

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
    sr_table = con.meta.tables["subreddits"]
    sub_table = con.meta.tables["submissions"]

    query = (
        sql.select(
            sr_table.c
            + [
                sql.select([sql.func.count()])
                .select_from(sub_table)
                .where(sub_table.c.subreddit_id == sr_table.c.id)
                .label("post_count")
            ]
        )
        .select_from(sr_table)
        .order_by("id")
    )

    if len(names) > 0:
        query = query.where(sr_table.c.name.in_(names))
    if ready is True:
        query = query.where(
            sr_table.c.last_submission_on
            < sql.func.now() - sql.text("INTERVAL '1 day'")
        )
    if ready is False:
        query = query.where(
            sr_table.c.last_submission_on
            > sql.func.now() - sql.text("INTERVAL '1 day'")
        )

    result = con.db.execute(query)

    click.echo(tabulate(result.fetchall(), headers=result.keys()))


@cli.command()
@click.pass_obj
def list_works(con):
    query = con.meta.tables["works"].select()

    result = con.db.execute(query)

    click.echo(tabulate(result.fetchall(), headers=result.keys()))


@cli.command()
@click.pass_obj
@click.option("--reddit-id", "-r", "id_type", flag_value="reddit", default=True)
@click.option("--submission-id", "-s", "id_type", flag_value="submission")
@click.option("--delete/--no-delete", "-d/-D", default=True)
@click.argument("post-id")
def delete_post(con, id_type, delete, post_id):
    submissions = con.meta.tables["submissions"]

    use_reddit = id_type == "submission"

    if not use_reddit:
        submission_id = post_id

        query = sql.select([submissions.c.reddit_id]).where(
            submissions.c.id == submission_id
        )
        row = con.db.execute(query).first()

        if row is None:
            log.error("Submission %s does not exist", submission_id)

        reddit_id = row["reddit_id"]
    else:
        reddit_id = post_id

        if val.url(reddit_id):
            reddit_id = Submission.id_from_url(reddit_id)

    if delete and reddit_id:
        sub = con.reddit.submission(reddit_id)

        sub.delete()

        sub.comments.replace_more(limit=None)

        for comment in sub.comments.list():
            if comment.author == con.reddit.user.me():
                comment.delete()

    query = submissions.update().values(reddit_id=None, submitted_on=None)
    if use_reddit:
        query = query.where(submissions.c.reddit_id == reddit_id)
    else:
        query = query.where(submissions.c.id == submission_id)

    con.db.execute(query)


if __name__ == "__main__":
    cli()
