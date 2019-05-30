import logging
import warnings

import click
import validators as val
from praw.models import Submission
from sqlalchemy import sql
from tabulate import tabulate

from . import extract
from . import helper as h
from . import paramtypes as types


class EBFormatter(logging.Formatter):
    def format(self, record):
        if record.levelname == "INFO":
            return record.getMessage()
        else:
            return record.levelname.title() + ": " + record.getMessage()


eb_log = logging.getLogger("errantbot")
eb_log.propagate = False
eb_log.setLevel(logging.INFO)
eb_handler = logging.StreamHandler()
eb_handler.setFormatter(EBFormatter())
eb_log.addHandler(eb_handler)

logging.basicConfig()

log = logging.getLogger("errantbot.cli")


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
@click.option("--no-post", "-P", is_flag=True)
@click.option("--add-sr", "-r", is_flag=True)
@click.option("--username", "-u", is_flag=True)
@click.option("--wait", "-w", type=int, default=18)
def add(
    con,
    source_url,
    submissions,
    title,
    artist,
    series,
    nsfw,
    index,
    album,
    no_post,
    add_sr,
    username,
    wait,
):
    submissions = h.Submissions(submissions)

    if add_sr:
        h.edit_subreddits(
            con, tuple(n_f_t.name for n_f_t in submissions.n_f_t), upsert=False
        )

    work = extract.auto(source_url, index=index, album=album, username=username)

    work_id = h.save_work(
        con,
        title or work.title,
        series or work.series,
        (artist,) + work.artists if artist else work.artists,
        work.source_url,
        nsfw or work.nsfw,
        work.image_url,
    )

    if work_id:
        h.add_submissions(con, work_id, submissions)

        h.upload_to_imgur(con, work_id)

        if not no_post:
            h.post_submissions(con, work_id, wait=wait)


@cli.command()
@click.pass_obj
@click.argument("title", required=True)
@click.argument("artist", required=True)
@click.argument("source-url", type=types.url, required=True)
@click.argument("source-image-url", type=types.url, required=True)
@click.argument("submissions", nargs=-1, type=types.submission)
@click.option("--no-post", "-P", is_flag=True)
@click.option("--nsfw/--sfw", "-n/-N")
@click.option("--series", "-s")
@click.option("--wait", "-w", type=int, default=18)
def add_custom(
    con,
    title,
    artist,
    source_url,
    source_image_url,
    submissions,
    no_post,
    nsfw,
    series,
    wait,
):
    submissions = h.Submissions(submissions)

    work_id = h.save_work(
        con, title, series, (artist,), source_url, nsfw, source_image_url
    )

    h.add_submissions(con, work_id, submissions)

    h.upload_to_imgur(con, work_id)

    if not no_post:
        h.post_submissions(con, work_id, wait=wait)


@cli.command()
@click.pass_obj
@click.argument("names", type=types.subreddit, nargs=-1)
@click.option("--disabled", "-d", is_flag=True)
@click.option("--flair-id", "-l", type=types.flair_id)
@click.option("--force", "-f", is_flag=True)
@click.option("--no-space-out", "-O", is_flag=True)
@click.option("--require-flair/--no-require-flair", "-q/-Q", is_flag=True)
@click.option("--require-series", "-e", is_flag=True)
@click.option("--require-tag", "-t", is_flag=True)
@click.option("--sfw-only", "-N", is_flag=True)
@click.option("--tag-series", "-s", is_flag=True)
def sr(
    con,
    names,
    disabled,
    flair_id,
    force,
    require_flair,
    require_series,
    require_tag,
    sfw_only,
    no_space_out,
    tag_series,
):
    h.edit_subreddits(
        con,
        names,
        disabled,
        flair_id,
        force,
        require_flair,
        require_series,
        require_tag,
        sfw_only,
        not no_space_out,
        tag_series,
    )


@cli.command()
@click.pass_obj
@click.argument("work-id", type=int, required=True)
@click.argument("submissions", nargs=-1, type=types.submission)
@click.option("--add-sr", "-r", is_flag=True)
@click.option("--no-post", "-P", is_flag=True)
@click.option("--wait", "-w", type=int, default=18)
def crosspost(con, work_id, submissions, no_post, add_sr, wait):
    submissions = h.Submissions(submissions)

    if add_sr:
        h.edit_subreddits(
            con, tuple(n_f_t.name for n_f_t in submissions.n_f_t), upsert=False
        )

    h.add_submissions(con, work_id, submissions)

    if not no_post:
        h.post_submissions(con, work_id, submissions, wait=wait)


@cli.command()
@click.pass_obj
@click.argument("submissions", nargs=-1, type=types.submission)
@click.option("--add-sr", "-r", is_flag=True)
@click.option("--no-post", "-P", is_flag=True)
@click.option("--wait", "-w", type=int, default=18)
def crosspost_last(con, submissions, no_post, add_sr, wait):
    submissions = h.Submissions(submissions)

    if add_sr:
        h.edit_subreddits(
            con, tuple(n_f_t.name for n_f_t in submissions.n_f_t), upsert=False
        )

    work_id = h.get_last(con, "works")

    h.add_submissions(con, work_id, submissions)

    if not no_post:
        h.post_submissions(con, work_id, submissions, wait=wait)


@cli.command()
@click.pass_obj
@click.argument("work-ids", type=int, nargs=-1)
@click.option("--last", "-l", is_flag=True)
@click.option("--wait", "-w", type=int, default=18)
def retry(con, work_ids, last, wait):
    h.post_submissions(con, work_ids, last=last, wait=wait)


@cli.command()
@click.pass_obj
@click.option("--wait", "-w", type=int, default=18)
def retry_all(con, wait):
    h.post_submissions(con, do_all=True, wait=wait)


@cli.command()
@click.pass_obj
def retry_all_uploads(con, no_wait):
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
def flairs(con, subreddit_name):
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
@click.option("--username", "-u", is_flag=True)
def _extract(url, index, album, username):
    work = extract.auto(url, index=index, album=album, username=username)

    for field in work._fields:
        attr = getattr(work, field)

        attr = "'" + attr + "'" if type(attr) == str else attr
        click.echo("{}:\t{}".format(field, attr))


@cli.command()
@click.pass_obj
@click.argument("names", nargs=-1, type=types.subreddit)
@click.option("--ready/--not-ready", "-r/-R", default=None)
def list_srs(con, names, ready):
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
    query = sql.text(
        """SELECT title, artists.name as artist, series, imgur_url, source_url
        FROM works INNER JOIN artists ON artist_id = artists.id"""
    )

    result = con.db.execute(query)

    click.echo(tabulate(result.fetchall(), headers=result.keys()))


@cli.command()
@click.pass_obj
@click.option("--reddit-id", "-r", "id_type", flag_value="reddit", default=True)
@click.option("--submission-id", "-s", "id_type", flag_value="submission")
@click.option("--from-reddit", "-r", is_flag=True)
@click.argument("post-id", type=int)
def delete_post(con, id_type, from_reddit, post_id):
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
            return

        reddit_id = row["reddit_id"]
    else:
        reddit_id = post_id

        if val.url(reddit_id):
            reddit_id = Submission.id_from_url(reddit_id)

    if from_reddit and reddit_id:
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


@cli.command()
@click.pass_obj
@click.argument("artists", nargs=-1)
def artists(con, artists):
    if val.url(artists[0]):
        artists = artists[1:] + extract.auto(artists[0])

    h.do_artists(con, artists)


if __name__ == "__main__":
    cli()
