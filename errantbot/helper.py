import click


def post_to_all(db, post_id, reddit):
    cursor = db.cursor()

    cursor.execute(
        """SELECT title, series, artist, source_url, imgur_image_url, nsfw,
        source_image_url, flair_id, tag_series, name, rehost,
        posts_to_subreddits.id FROM posts
        INNER JOIN (posts_to_subreddits, subreddits)
        ON posts_to_subreddits.did_submit=0
        AND posts_to_subreddits.post_id=posts.id
        AND posts_to_subreddits.subreddit_id=subreddits.id AND posts.id={}""".
        format(post_id))

    rows = cursor.fetchall()

    for row in rows:
        sub = reddit.subreddit(row["name"])

        title = row["title"] + " "

        if row["tag_series"]:
            title += "[" + row["series"] + "] "

        title += "(" + row["artist"] + ")"

        url = row["imgur_image_url" if row["rehost"] else "source_image_url"]

        submission = sub.submit(title, url=url, flair_id=row["flair_id"])

        if row["nsfw"]:
            submission.mod.nsfw()

        submission.reply("[Source]({})".format(row["source_url"]))

        cursor.execute(
            "UPDATE posts_to_subreddits SET submission_id = %s, \
                did_submit = 1 WHERE id = %s"
            "", (submission.id, row["id"]))

        db.commit()


def upload_to_imgur(db, post_id, imgur):
    cursor = db.cursor()

    cursor.execute("""SELECT title, artist, source_image_url, source_url
        FROM posts WHERE id={}""".format(post_id))
    row = cursor.fetchone()

    resp = imgur.upload_url(row["source_image_url"],
                            "{title} ({artist})".format(**row),
                            "Source: {}".format(row["source_url"]))

    resp.raise_for_status()

    data = resp.json()["data"]

    cursor.execute("""UPDATE posts
        SET imgur_post_url='https://imgur.com/{id}', imgur_image_url='{link}'
        WHERE id={}""".format(post_id, **data))
    db.commit()


def save_post(db, title, series, artist, source_url, imgur_post_url,
              imgur_image_url, nsfw, source_image_url, subreddits):
    cursor = db.cursor()

    cursor.execute(
        """INSERT INTO posts (title, series, artist, source_url,
            imgur_post_url, imgur_image_url, nsfw, source_image_url)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s);""",
        (title, series, artist, source_url, imgur_post_url, imgur_image_url,
         nsfw, source_image_url))
    db.commit()

    cursor.execute("SELECT LAST_INSERT_ID()")
    post_id = cursor.fetchall()[0]["LAST_INSERT_ID()"]

    add_post_to_subreddits(db, post_id, subreddits)

    return post_id


def add_subreddit(db, name, tag_series, flair_id):
    cursor = db.cursor()

    cursor.execute(
        """INSERT INTO subreddits (name, tag_series, flair_id)
        VALUES (%s, %s, %s)
        ON DUPLICATE KEY UPDATE tag_series=%s, flair_id=%s""",
        (name, tag_series, flair_id, tag_series, flair_id))
    db.commit()


def add_post_to_subreddits(db, post_id, subreddit_names):
    check_subreddits(db, subreddit_names)

    cursor = db.cursor()

    cursor.execute(
        """INSERT INTO posts_to_subreddits
        (post_id, subreddit_id, submission_id, did_submit)
        SELECT %s, id, NULL, 0 FROM subreddits WHERE name IN ({})""",
        (post_id, ", ".join(
            map(lambda name: "'" + name + "'", subreddit_names))))
    db.commit()


def check_subreddits(db, subreddit_names):
    cursor = db.cursor()

    cursor.execute(
        """WITH prov (name) AS ( VALUES %s )
        SELECT name FROM prov EXCEPT select name from subreddits""",
        (",".join(map(lambda name: "('" + name + "')", subreddit_names)), ))

    badsubs = cursor.fetchall()

    n_bad = len(badsubs)

    if n_bad > 0:
        raise click.UsageError(
            "Subreddit{} {} {} unknown. Use 'add-sub' to register {}.".format(
                "s" if n_bad > 1 else "", ", ".join(
                    map(lambda sub: "'" + sub["name"] + "'", badsubs)),
                "are" if n_bad > 1 else "is", "them" if n_bad > 1 else "it"))
