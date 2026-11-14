import json
from datetime import datetime
from pathlib import Path

from exceptions import EpisodeNotFoundError, LibraryCorruptedError, PodcastNotFoundError
from models import Episode, Podcast

DEFAULT_SETTINGS = {
    "download_dir": "episodes",
    "playback_speed": 1.0,
    "auto_delete_after_listen": False,
}


class Library:
    def __init__(self, library_path: Path, episodes_dir: Path):
        self.library_path = library_path
        self.episodes_dir = episodes_dir
        self.podcasts: list[Podcast] = []
        self.episodes: list[Episode] = []
        self.settings = dict(DEFAULT_SETTINGS)

    @classmethod
    def load(cls, library_path: Path, episodes_dir: Path) -> "Library":
        lib = cls(library_path, episodes_dir)

        if not library_path.exists():
            return lib

        text = library_path.read_text(encoding="utf-8")
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            timestamp = datetime.now().strftime("%Y-%m-%dT%H-%M-%S")
            backup_path = library_path.with_name(f"library-broken-{timestamp}.json")
            library_path.rename(backup_path)
            raise LibraryCorruptedError(backup_path)

        lib.podcasts = [Podcast.from_dict(p) for p in data.get("podcasts", [])]
        lib.episodes = [Episode.from_dict(e) for e in data.get("episodes", [])]
        lib.settings = data.get("settings", dict(DEFAULT_SETTINGS))

        return lib

    def save(self) -> None:

        data = {
            "podcasts": [p.to_dict() for p in self.podcasts],
            "episodes": [e.to_dict() for e in self.episodes],
            "settings": self.settings,
        }

        text = json.dumps(data, indent=2)

        tmp = self.library_path.with_suffix(".tmp.json")

        tmp.write_text(text, encoding="utf-8")

        tmp.replace(self.library_path)

    def add_podcast(self, podcast: Podcast) -> None:
        self.podcasts = [p for p in self.podcasts if podcast.id != p.id]
        self.podcasts.append(podcast)
        self.save()

    def add_episode(self, episode: Episode) -> None:
        self.episodes = [e for e in self.episodes if episode.id != e.id]
        self.episodes.append(episode)

    def mark_downloaded(self, episode_id: str, file_path: Path, file_size: int) -> None:
        for e in self.episodes:
            if e.id == episode_id:
                e.downloaded = True
                e.file_path = str(file_path)
                e.file_size_bytes = file_size
                self.save()
                return

    def remove_podcast(self, podcast_id: str) -> None:
        self.podcasts = [p for p in self.podcasts if podcast_id != p.id]
        self.episodes = [e for e in self.episodes if podcast_id != e.podcast_id]
        self.save()

    def find_podcast(self, identifier: str) -> Podcast:
        podcast = next(
            (
                p
                for p in self.podcasts
                if p.id == identifier
                or p.title.lower().strip() == identifier.lower().strip()
            ),
            None,
        )
        if not podcast:
            raise PodcastNotFoundError(identifier)
        return podcast

    def find_episode(self, episode_id: str) -> Episode:
        episode = next((e for e in self.episodes if e.id == episode_id), None)
        if not episode:
            raise EpisodeNotFoundError(episode_id)
        return episode

    def episodes_for(self, podcast_id: str) -> list[Episode]:
        episodes = [e for e in self.episodes if e.podcast_id == podcast_id]
        return episodes

    def known_guids_for(self, podcast_id: str) -> set[str]:
        guids = set(e.guid for e in self.episodes if e.podcast_id == podcast_id)
        return guids

    @property
    def total_podcasts(self) -> int:
        return len(self.podcasts)

    @property
    def total_episodes(self) -> int:
        return len(self.episodes)

    @property
    def downloaded_episodes(self) -> list[Episode]:
        episodes = [e for e in self.episodes if e.downloaded]
        return episodes
