import argparse
import re
from datetime import date, datetime
from pathlib import Path

import feedparser
import requests
from platformdirs import user_data_dir
from rich.progress import (
    BarColumn,
    DownloadColumn,
    Progress,
    TimeRemainingColumn,
    TransferSpeedColumn,
)

from exceptions import (
    EpisodeNotFoundError,
    FeedFetchError,
    LibraryCorruptedError,
    PodcastNotFoundError,
)
from library import Library
from models import Episode, Podcast


def main():

    data_dir = Path(user_data_dir("castor", appauthor=False))

    library_path = data_dir / "library.json"
    episodes_dir = data_dir / "episodes"

    episodes_dir.mkdir(parents=True, exist_ok=True)

    library = Library.load(library_path, episodes_dir)

    parser = argparse.ArgumentParser(
        description="Terminal-based podcast client with a modern Textual interface."
    )
    subparser = parser.add_subparsers(dest="command")

    search_parser = subparser.add_parser("search", help="Search podcasts by term")
    search_parser.add_argument("query", help="Search terms")

    subscribe_parser = subparser.add_parser("subscribe", help="Subscribe to a feed")
    subscribe_parser.add_argument("feed_url", help="Podcast RSS feed URL")

    subparser.add_parser("list", help="List your subscriptions")

    episodes_parser = subparser.add_parser(
        "episodes", help="List episodes of a podcast"
    )
    episodes_parser.add_argument("podcast_id", help="ID of the subscribed Podcast")

    download_parser = subparser.add_parser("download", help="Download an episode")
    download_parser.add_argument("episode_id", help="ID of the episode")

    subparser.add_parser("refresh", help="Refresh all feeds")

    args = parser.parse_args()
    command = args.command
    try:
        match command:
            case "search":
                results = search_podcasts(args.query)
                for r in results:
                    print(
                        f"{r.get('title')} - {r.get('author')} ({r.get('episode_count')} episodes)"
                    )
            case "subscribe":
                parsed_feed = parse_feed(args.feed_url)

                podcast = parsed_feed.get("podcast")
                podcast["subscribed_at"] = date.today().isoformat()
                podcast["last_refreshed"] = date.today().isoformat()
                episodes = parsed_feed.get("episodes")
                library.add_podcast(Podcast.from_dict(podcast))

                for i, e in enumerate(episodes):
                    e["id"] = f"{podcast['id']}-{i + 1}"
                    e["podcast_id"] = podcast["id"]

                    library.add_episode(Episode.from_dict(e))

                library.save()

            case "list":
                for podcast in library.podcasts:
                    total_episodes = len(library.episodes_for(podcast.id))
                    downloaded_episodes = sum(
                        1 for e in library.episodes_for(podcast.id) if e.downloaded
                    )
                    print(
                        f"{podcast.title}     {total_episodes} episodes   {downloaded_episodes} downloaded"
                    )

            case "episodes":
                podcast = library.find_podcast(args.podcast_id)
                episodes = library.episodes_for(podcast.id)

                for e in episodes:
                    episode_number = e.id.split("-")[-1]
                    print(
                        f"○ {e.id} #{episode_number} - {e.title}    {e.published} {format_duration(e.duration_seconds)}"
                    )

            case "download":
                episode = library.find_episode(args.episode_id)
                donwload_url = episode.audio_url
                filepath = episodes_dir / f"{args.episode_id}.mp3"

                response = requests.get(donwload_url, stream=True)
                response.raise_for_status()

                total = int(response.headers.get("Content-Length", 0))

                with Progress(
                    "[progress.description]{task.description}",
                    BarColumn(),
                    DownloadColumn(),
                    TimeRemainingColumn(),
                    TransferSpeedColumn(),
                ) as progress:
                    task = progress.add_task(
                        f"Descargando {args.episode_id}.mp3", total=total
                    )

                    with open(filepath, "wb") as f:
                        for chunk in response.iter_content(chunk_size=8192):
                            f.write(chunk)
                            progress.advance(task, advance=len(chunk))

                library.mark_downloaded(args.episode_id, Path(filepath), total)
            case "refresh":
                print(f"Refeshing {len(library.podcasts)} podcasts...")
                for p in library.podcasts:
                    new_episodes = 0
                    guids = library.known_guids_for(p.id)
                    episodes = parse_feed(p.feed_url).get("episodes", [])
                    for e in episodes:
                        if e["guid"] not in guids:
                            new_episodes += 1
                            e["id"] = (
                                f"{p.id}-{len(library.episodes_for(p.id)) + new_episodes}"
                            )
                            library.add_episode(Episode.from_dict(e))

                    print(f"{p.title}: {new_episodes} new episode")
                    new_episodes = 0
                library.save()
            case _:
                pass
    except PodcastNotFoundError as e:
        print(f"Podcast not found: {e}")
    except EpisodeNotFoundError as e:
        print(f"Episode not found: {e}")
    except FeedFetchError as e:
        print(f"Network error: {e}")
    except LibraryCorruptedError as e:
        print(f"Corrupt library, backup in: {e}")


def search_podcasts(query: str) -> list[dict]:
    try:
        response = requests.get(
            f"https://itunes.apple.com/search?term={query}&media=podcast"
        )
    except requests.exceptions.RequestException:
        raise FeedFetchError("Unable to connect to iTunes")
    data = response.json()
    results = []

    for result in data["results"]:
        normalized_result = {
            "title": result.get("collectionName", ""),
            "author": result.get("artistName", ""),
            "feed_url": result.get("feedUrl", ""),
            "episode_count": result.get("trackCount", ""),
        }

        results.append(normalized_result)

    return results


def parse_feed(feed_url: str) -> dict:
    try:
        response = feedparser.parse(feed_url)
        data = response.get("feed")
        podcast_id = re.sub(r"[^\w]+", "-", data.get("title", "")).strip("-").lower()
        podcast = {
            "id": podcast_id,
            "title": data.get("title", ""),
            "author": data.get("author", ""),
            "feed_url": feed_url,
            "description": data.get("summary", ""),
        }
        episodes = response.get("entries", [])
        mapped_episodes = []

        for e in episodes:
            audio_url = next(
                (
                    link["href"]
                    for link in e.get("links", [])
                    if link["rel"] == "enclosure"
                ),
                None,
            )
            parsed = e.get("published_parsed")
            episode = {
                "guid": e.get("id"),
                "title": e.get("title", ""),
                "audio_url": audio_url,
                "duration_seconds": parse_duration(e.get("itunes_duration")),
                "published": datetime(*parsed[:6]).isoformat() if parsed else None,
                "description": e.get("summary", ""),
            }

            mapped_episodes.append(episode)

        mapped_episodes.sort(key=lambda e: e["published"] or "")
    except Exception as e:
        raise FeedFetchError
    return {"podcast": podcast, "episodes": mapped_episodes}


def parse_duration(duration: str) -> int:

    try:
        if duration.count(":") == 2:
            parts = duration.split(":")
            hours, minutes, seconds = int(parts[0]), int(parts[1]), int(parts[2])

        elif duration.count(":") == 1:
            parts = duration.split(":")
            hours, minutes, seconds = 0, int(parts[0]), int(parts[1])
        else:
            hours, minutes, seconds = 0, 0, int(duration)

        seconds = seconds + minutes * 60 + hours * 3600

        return seconds

    except (AttributeError, ValueError):
        return None


def format_duration(seconds: int) -> str:

    if seconds is None or seconds == 0:
        return "-"

    minutes, final_seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    parts = []

    if hours != 0:
        parts.append(f"{hours}h")

    if minutes != 0:
        parts.append(f"{minutes}m")

    if final_seconds != 0 and hours == 0:
        parts.append(f"{final_seconds}s")

    return " ".join(parts)


if __name__ == "__main__":
    main()
