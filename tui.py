import subprocess
import sys
from datetime import date
from pathlib import Path

import requests
from platformdirs import user_data_dir
from textual import work
from textual.app import App, ComposeResult
from textual.containers import Vertical
from textual.screen import ModalScreen, Screen
from textual.widgets import (
    DataTable,
    Footer,
    Header,
    Input,
    Label,
    ListItem,
    ListView,
    ProgressBar,
)

from exceptions import (
    EpisodeNotFoundError,
    FeedFetchError,
    LibraryCorruptedError,
)
from library import Library
from models import Episode, Podcast
from project import format_duration, parse_feed, search_podcasts


class EpisodesScreen(Screen):
    def __init__(self, podcast_id):
        super().__init__()
        self.dato = podcast_id

    BINDINGS = [
        ("escape", "app.pop_screen", "Back"),
        ("d", "download", "Download"),
        ("p", "play", "Play"),
    ]

    DEFAULT_CSS = """
            DataTable {
                height: 1fr;
            }
            ProgressBar {
                height: 3;
                width: 1fr;
                dock: bottom;
            }
            ProgressBar Bar {
                width: 1fr;
            }
        """

    @property
    def podcast(self) -> Podcast:
        library = self.app.library
        podcast = library.find_podcast(self.dato)
        return podcast

    def compose(self) -> ComposeResult:
        yield Header()
        yield DataTable()
        yield Footer()
        yield ProgressBar(total=100, show_eta=False)

    def on_mount(self) -> None:
        podcast = self.podcast
        library = self.app.library
        episodes = library.episodes_for(podcast.id)
        self.title = podcast.title
        self.sub_title = f"{len(episodes)} episodes · {sum(1 for e in episodes if e.downloaded)} downloaded"
        table = self.query_one(DataTable)
        self.query_one(ProgressBar).display = False
        table.cursor_type = "row"
        self.status_col, *_ = table.add_columns(
            "STATUS", "TITLE", "PUBLISHED", "DURATION"
        )

        for e in episodes:
            status = "✓" if e.downloaded else "○"
            table.add_row(
                status,
                e.title,
                e.published.split("T")[0],
                format_duration(e.duration_seconds),
                key=e.id,
            )

    @work(thread=True)
    def download_worker(self, episode_id) -> None:

        library = self.app.library
        episode_id = episode_id.value
        try:
            episode = library.find_episode(episode_id)
            audio_url = episode.audio_url
            filepath = library.episodes_dir / f"{episode.id}.mp3"

            response = requests.get(audio_url, stream=True)

            self.app.call_from_thread(self.notify, "Downloading...")

            file_size = int(response.headers.get("Content-Length", 0))
            response.raise_for_status()

            self.app.call_from_thread(self._start_progress_bar, file_size)

            with open(filepath, "wb") as file:
                for chunk in response.iter_content(chunk_size=8192):
                    file.write(chunk)
                    self.app.call_from_thread(self._advance_progress_bar, len(chunk))

            library.mark_downloaded(episode_id, filepath, file_size)

            self.app.call_from_thread(self._update_ui, episode_id)
            self.app.call_from_thread(self.notify, "Download completed")
        except EpisodeNotFoundError:
            self.app.call_from_thread(
                self.notify, "Episode not found", severity="error"
            )
        except Exception:
            self.app.call_from_thread(self.notify, "Download failed", severity="error")

    def _advance_progress_bar(self, quantity) -> None:
        progress_bar = self.query_one(ProgressBar)
        progress_bar.advance(quantity)

    def _start_progress_bar(self, file_size) -> None:
        progress_bar = self.query_one(ProgressBar)
        progress_bar.display = True
        progress_bar.total = file_size

    def _update_ui(self, episode_id) -> None:
        table = self.query_one(DataTable)
        table.update_cell(column_key=self.status_col, row_key=episode_id, value="✓")
        library = self.app.library
        episodes = library.episodes_for(self.podcast.id)
        self.query_one(ProgressBar).display = False
        self.sub_title = f"{len(episodes)} episodes · {sum(1 for e in episodes if e.downloaded)} downloaded"

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        self.refresh_bindings()

    def check_action(self, action, parameters) -> bool | None:
        try:
            table = self.query_one(DataTable)
            episode_id, _ = table.coordinate_to_cell_key(table.cursor_coordinate)
            library = self.app.library
            episode = library.find_episode(episode_id.value)

            if action == "download":
                return not episode.downloaded
            if action == "play":
                return episode.downloaded

        except Exception:
            return False
        return True

    def action_download(self) -> None:
        table = self.query_one(DataTable)
        episode_id, _ = table.coordinate_to_cell_key(table.cursor_coordinate)
        self.download_worker(episode_id)

    def action_play(self) -> None:
        table = self.query_one(DataTable)
        episode_id, _ = table.coordinate_to_cell_key(table.cursor_coordinate)
        episode = self.app.library.find_episode(episode_id.value)

        if not episode.downloaded:
            self.notify("Download the episode first", severity="warning")
            return

        filepath = self.app.library.episodes_dir / f"{episode_id.value}.mp3"

        if not filepath.exists():
            self.notify("File not found on disk", severity="error")
            return

        if sys.platform == "darwin":
            subprocess.run(["open", str(filepath.resolve())])
        elif sys.platform == "win32":
            subprocess.run(["start", "", str(filepath.resolve())], shell=True)
        else:
            subprocess.run(["xdg-open", str(filepath.resolve())])


class LibraryScreen(Screen):
    BINDINGS = [
        ("r", "refresh", "Refresh"),
        ("s", "search", "Search"),
        ("d", "unsubscribe", "Unsubscribe"),
    ]

    def compose(self) -> ComposeResult:
        yield Header()
        yield DataTable()
        yield Label("No podcasts yet - press s to search", id="no_podcasts")
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one(DataTable)
        table.add_columns("TITLE", "AUTHOR", "EPISODES", "DOWNLOADED", "UPDATED")
        self._load_table()

    def on_screen_resume(self) -> None:
        self.app.sub_title = ""
        self._load_table()

    def _load_table(self) -> None:
        table = self.query_one(DataTable)
        no_podcasts_label = self.query_one("#no_podcasts", Label)
        table.clear()
        table.cursor_type = "row"
        library = self.app.library
        if len(library.podcasts) != 0:
            no_podcasts_label.display = False
        else:
            no_podcasts_label.display = True
        for podcast in library.podcasts:
            num_episodes = sum(
                1 for e in library.episodes if podcast.id == e.podcast_id
            )
            num_downloaded = sum(
                1
                for e in library.episodes
                if podcast.id == e.podcast_id and e.downloaded
            )
            table.add_row(
                podcast.title,
                podcast.author,
                num_episodes,
                num_downloaded,
                podcast.last_refreshed,
                key=podcast.id,
            )

    @work(thread=True)
    def refresh_worker(self) -> None:

        library = self.app.library
        podcasts = library.podcasts
        self.app.call_from_thread(self.notify, "Refreshing...")
        try:
            total_episodes = 0
            for p in podcasts:
                new_episodes = 0
                data = parse_feed(p.feed_url)
                episodes = data.get("episodes")
                known_guids = library.known_guids_for(p.id)
                p.last_refreshed = date.today().isoformat()
                for e in episodes:
                    if e["guid"] not in known_guids:
                        new_episodes += 1
                        e["podcast_id"] = p.id
                        e["id"] = (
                            f"{p.id}-{len(library.episodes_for(p.id)) + new_episodes}"
                        )
                        library.add_episode(Episode.from_dict(e))

                total_episodes += new_episodes

            library.save()

            self.app.call_from_thread(self._load_table)

            self.app.call_from_thread(
                self.notify,
                f"{total_episodes} new episodes across {len(podcasts)} podcasts",
            )
        except FeedFetchError:
            self.app.call_from_thread(self.notify, "Fetch Failed", severity="error")
        except Exception:
            self.app.call_from_thread(self.notify, "Refresh failed", severity="error")

    def action_search(self) -> None:
        self.app.push_screen(SearchModal())

    def action_refresh(self) -> None:
        self.refresh_worker()

    def action_unsubscribe(self) -> None:
        table = self.query_one(DataTable)
        library = self.app.library
        podcast_id, _ = table.coordinate_to_cell_key(table.cursor_coordinate)
        podcast = library.find_podcast(podcast_id.value)

        def confirm():
            library.remove_podcast(podcast.id)
            self.notify("Podcast Removed")
            self._load_table()

        self.app.push_screen(
            ConfirmModal(f"Unsubscribe from {podcast.title}?", confirm)
        )

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        key = event.row_key.value
        self.app.push_screen(EpisodesScreen(key))


class SearchModal(ModalScreen):
    BINDINGS = [("escape", "app.pop_screen", "Back")]

    DEFAULT_CSS = """
        SearchModal {
            align: center middle;
        }
        #panel {
            width: 64;
            height: auto;
            max-height: 80%;
            border: round $primary;
            background: $surface;
            padding: 1 2;
        }
        #title {
            text-style: bold;
            margin-bottom: 1;
        }
        Input {
            margin-bottom: 1;
        }
        #status {
            color: $text-muted;
            margin-bottom: 1;
        }
        ListView {
            height: auto;
            max-height: 12;
            background: transparent;
        }
        ListItem {
            padding: 0 1;
            height: auto;
        }
        ListItem > Vertical {
            height: auto;
            padding-bottom: 1;
        }
        #author {
            color: $text-muted;
        }
        #footer {
            color: $text-muted;
            margin-top: 1;
        }
        """

    def compose(self) -> ComposeResult:
        with Vertical(id="panel"):
            yield Label("Search podcast", id="title")
            yield Input(placeholder="Search...")
            yield Label("", id="status")
            yield ListView()
            yield Label("Enter Subscribe  Esc Close", id="footer")

    @work(thread=True)
    def search_worker(self, query) -> None:
        try:
            results = search_podcasts(query)
            self.app.call_from_thread(self._update_modal, results)
        except FeedFetchError:
            self.app.call_from_thread(self.notify, "Search failed", severity="error")

    @work(thread=True)
    def subscribe_worker(self, podcast_data) -> None:

        if not podcast_data["subscribed"]:
            try:
                data = parse_feed(podcast_data.get("feed_url", ""))

                library = self.app.library
                podcast = data.get("podcast", {})
                podcast["subscribed_at"] = date.today().isoformat()
                podcast["last_refreshed"] = date.today().isoformat()
                episodes = data.get("episodes")
                library.add_podcast(Podcast.from_dict(podcast))

                for i, e in enumerate(episodes):
                    e["id"] = f"{podcast['id']}-{i + 1}"
                    e["podcast_id"] = podcast["id"]

                    library.add_episode(Episode.from_dict(e))

                library.save()

                self.app.call_from_thread(self.notify, "Subscribed")
                self.app.call_from_thread(self.app.pop_screen)
            except FeedFetchError:
                self.app.call_from_thread(self.notify, "Fetch Failed", severity="error")
            except Exception:
                self.app.call_from_thread(
                    self.notify, "Subscription Error", severity="error"
                )
        else:
            self.app.call_from_thread(
                self.notify, "Already Subscribed", severity="warning"
            )

    def _update_modal(self, results) -> None:
        list_view = self.query_one(ListView)
        input = self.query_one(Input)
        list_view.clear()
        input.clear()

        for result in results:
            already_subscribed = any(
                result["title"] == p.title for p in self.app.library.podcasts
            )
            result["subscribed"] = bool(already_subscribed)
            item = ListItem(
                Vertical(
                    Label(
                        f"{result['title']} {'(Subscribed)' if already_subscribed else ''}"
                    ),
                    Label(
                        f"{result.get('author', '')} · {result.get('episode_count', '')} episodes",
                        id="author",
                    ),
                )
            )
            item.podcast_data = result
            list_view.append(item)

        self.query_one("#status", Label).update(f"{len(results)} results")
        list_view.focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        query = event.value
        self.search_worker(query)
        self.query_one("#status", Label).update("Searching...")

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        podcast_data = event.item.podcast_data
        self.subscribe_worker(podcast_data)


class ConfirmModal(ModalScreen):
    def __init__(self, message, on_confirm):
        super().__init__()
        self.message = message
        self.on_confirm = on_confirm

    DEFAULT_CSS = """
        ConfirmModal {
            align: center middle;
        }
        #panel {
            width: 50;
            height: auto;
            border: round $primary;
            background: $surface;
            padding: 1 2;
        }
        #title {
            text-style: bold;
            margin-bottom: 1;
        }
        #footer {
            color: $text-muted;
            margin-top: 1;
        }
        """

    BINDINGS = [("y", "confirm", "Yes"), ("n", "app.pop_screen", "No")]

    def compose(self) -> ComposeResult:
        with Vertical(id="panel"):
            yield Label("Confirm", id="title")
            yield Label(self.message)
            yield Label("Y Yes  N No", id="footer")

    def action_confirm(self) -> None:
        self.app.pop_screen()
        self.on_confirm()


class CastorApp(App):
    TITLE = "Castor"
    SCREENS = {"main": LibraryScreen, "episodes": EpisodesScreen}
    BINDINGS = [("q", "quit", "Quit")]

    def on_mount(self) -> None:
        self.theme = "tokyo-night"
        try:
            data_dir = Path(user_data_dir("castor", appauthor=False))
            self.library_path = data_dir / "library.json"
            self.episodes_dir = data_dir / "episodes"
            self.episodes_dir.mkdir(parents=True, exist_ok=True)
            self.library = Library.load(self.library_path, self.episodes_dir)

        except LibraryCorruptedError as e:
            self.notify(f"Corrupt library, backup in: {e}")
            self.library = Library(self.library_path, self.episodes_dir)
        finally:
            self.push_screen("main")


if __name__ == "__main__":
    CastorApp().run()
