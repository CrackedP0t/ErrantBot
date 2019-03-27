import regex
from click import ParamType

import validators as val


class URL(ParamType):
    name = "URL"

    def convert(self, value, param, ctx):
        if val.url(value):
            return value
        else:
            self.fail("'{}' is not a valid URL".format(value), param, ctx)


class FlairID(ParamType):
    name = "flair ID"

    val_flair_id = regex.compile(r"([a-f0-9]){8}-(?1){4}-(?1){4}-(?1){4}-(?1){12}")

    @classmethod
    def process(cls, value, ctx=None):
        value = value.lower()

        if cls.val_flair_id.fullmatch(value):
            return value
        else:
            return False

    def convert(self, value, param, ctx):
        processed = self.process(value)
        if processed:
            return processed
        else:
            self.fail("'{}' is not a valid flair ID".format(value), param, ctx)


class Subreddit(ParamType):
    name = "subreddit"

    # Found in Reddit's old source code - RIP
    val_subreddit_name = regex.compile(r"[A-Za-z0-9][A-Za-z0-9_]{2,20}")

    @classmethod
    def process(cls, value):
        value = value.replace("/r/", "")

        if not cls.val_subreddit_name.fullmatch(value):
            return False
        else:
            return value.lower()

    def convert(self, value, param, ctx):
        processed = self.process(value)
        if processed:
            return processed
        else:
            self.fail("'{}' is not a valid subreddit name".format(value), param, ctx)


class Submission(ParamType):
    name = "submission specifier"

    find_name = regex.compile(r"^[^@+]*")
    find_flair_id = regex.compile(r"@((?:(?:%\+)|[^+])*)")
    find_tag = regex.compile(r"\+(.*)$")

    def convert(self, value, param, ctx):
        name = self.find_name.search(value)
        if not name:
            self.fail("Subreddit name not found in '{}'".format(value), param, ctx)

        name = Subreddit.process(name[0])
        if not name:
            self.fail("'{}' is not a valid subreddit name".format(name), param, ctx)

        flair_id = self.find_flair_id.search(value)

        if flair_id:
            flair_id = flair_id[1]

            flair_id.replace("%%", "%")
            flair_id.replace("%+", "+")

            if not FlairID.process(flair_id):
                sub = ctx.obj.reddit.subreddit(name)

                for flair in sub.flair.link_templates:
                    if flair_id in flair["text"]:
                        flair_id = flair["id"]
                        break
                else:
                    self.fail(
                        "'{}' is not a valid flair ID, "
                        "and does not match any flair text".format(flair_id),
                        param,
                        ctx,
                    )

        tag = self.find_tag.search(value)
        if tag:
            tag = tag[1]

        return (name, flair_id, tag)


url = URL()
flair_id = FlairID()
subreddit = Subreddit()
submission = Submission()
