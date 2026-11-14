from dataclasses import asdict, dataclass


@dataclass
class Podcast:
    id: str
    title: str
    author: str
    feed_url: str
    description: str
    subscribed_at: str
    last_refreshed: str

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Podcast":
        return cls(**data)


@dataclass
class Episode:
    id: str
    podcast_id: str
    guid: str
    title: str
    audio_url: str
    published: str
    description: str
    downloaded: bool = False
    completed: bool = False
    file_size_bytes: int | None = None
    position_seconds: int = 0
    file_path: str | None = None
    duration_seconds: int | None = None

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Episode":
        return cls(**data)
