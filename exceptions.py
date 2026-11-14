class PodcastNotFoundError(Exception):
    pass


class EpisodeNotFoundError(Exception):
    pass


class FeedFetchError(Exception):
    pass


class LibraryCorruptedError(Exception):
    pass
