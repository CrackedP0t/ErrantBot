import MySQLdb

class Post:
    def __init__(self, source, subreddits=[]):
        self.source = source
        self.subreddits = subreddits

    def upload(self, imgur):
        resp = imgur.upload_url(self.source.image_url,
                                "{} ({})".format(self.source.title,
                                                 self.source.artist),
                                "Source: {}".format(self.source.source_url))

        resp = resp.json()["data"]

        self.imgur_url = "https://imgur.com/".format(resp["id"])
        self.imgur_image = resp["link"]

    def save(self, db):
        cursor = db.cursor()

        cursor.execute("""INSERT INTO posts (title, series, artist, source_url, imgur_post_url, imgur_image_url, nsfw) VALUES (%s, %s, %s, %s, %s, %s, %s);""",
                       (self.source.title, self.source.series, self.source.artist, self.source.source_url, self.imgur_url, self.imgur_image, self.source.nsfw))

        db.commit()

        cursor.execute("SELECT LAST_INSERT_ID()")

        self.row_id = cursor.fetchall()[0][0]

        cursor.execute("""SELECT id FROM subreddits WHERE name IN ({})"""
                       .format(", ".join(map(lambda sub: "'" + sub + "'",
                                             self.subreddits))))

        sub_ids = list(map(lambda row: row[0], cursor.fetchall()))

        for sub_id in sub_ids:
            cursor.execute("""INSERT INTO posts_to_subreddits (post_id, subreddit_id) VALUES (%s, %s)""", (self.row_id, sub_id))

        db.commit()

    def post(self, db, reddit):
        cursor = db.cursor()

        cursor.execute("""SELECT title, series, artist, source_url, imgur_image_url, nsfw FROM posts WHERE id = %s""", (self.row_id,))

        row = cursor.fetchall()[0]

        cursor.execute("""SELECT id, name, tag_series, flair_id FROM subreddits WHERE id in (SELECT subreddit_id FROM posts_to_subreddits WHERE post_id = %s)""", (self.row_id,))

        sub_rows = cursor.fetchall()

        for sub_row in sub_rows:
            sub = reddit.subreddit(sub_row[1])

            title = row[0] + " "

            if sub_row[2]:
                title += "[" + row[1] + "] "

            title += "(" + row[2] + ")"

            submission = None

            if sub_row[3]:
                submission = sub.submit(title, url=row[4], flair_id=sub_row[3])
            else:
                submission = sub.submit(title, url=row[4])

            if row[5]:
                submission.mod.nsfw()

            submission.reply("[Source]({})".format(row[3]))

            cursor.execute("UPDATE posts_to_subreddits SET submission_id = %s, did_submit = 1 WHERE post_id = %s AND subreddit_id = %s""",
                           (submission.id, self.row_id, sub_row[0]))

            db.commit()
