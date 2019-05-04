class EBException(Exception):
    pass


class UnsupportedSite(EBException):
    def __init__(self, page):
        self.page = page

        self.args = ("The page '{}' is not from a supported site".format(page),)
