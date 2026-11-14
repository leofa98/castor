from library import Library
from project import format_duration, search_podcasts, parse_feed
from  models import Episode, Podcast
from exceptions import LibraryCorruptedError
from unittest.mock import patch, Mock

import pytest

def test_format_duration_none():
    assert format_duration(None) == "-"

def test_format_duration_zero():
    assert format_duration(0) == "-"

def test_format_duration_seconds():
    assert format_duration(34) == "34s"

def test_format_duration_minutes():
    assert format_duration(120) == "2m"

def test_format_duration_hours():
    assert format_duration(10800) == "3h"

def test_format_duration_minutes_seconds():
    assert format_duration(90) == "1m 30s"

def test_format_duration_hours_minutes_seconds():
    assert format_duration(3725) == "1h 2m"

def test_podcast_round_trip():
    p = Podcast(
        id="lex-fridman-podcast",
        title="Lex Fridman Podcast",
        author="Lex Fridman",
        feed_url="https://lexfridman.com/feed/podcast/",
        description="Conversations about life and meaning",
        subscribed_at="2026-04-25",
        last_refreshed="2026-04-25",
    )
    assert Podcast.from_dict(p.to_dict()) == p

def test_episode_round_trip():
    e = Episode(
        id="lex-495",
        podcast_id="lex-fridman-podcast",
        guid="lex-fridman-podcast-495",
        title="Vikings, Ragnar, Berserkers, Valhalla & the Warriors of the Viking Age",
        audio_url="https://lexfridman.com/lars-brownworth/#038;utm_medium=rss&#038;utm_campaign=lars-brownworth",
        duration_seconds=7796,
        published="2026-05-09",
        description="Lars Brownworth is a historian, teacher, podcaster, and author specializing in Viking history, medieval Europe, and the Byzantine Empire.",
        file_path="https://media.blubrry.com/takeituneasy/ins.blubrry.com/takeituneasy/lex_ai_lars_brownworth.mp3",
        file_size_bytes=189853118,
        downloaded=False,
        position_seconds=343,
        completed=False,
    )

    assert Episode.from_dict(e.to_dict()) == e

def test_episode_defaults():
    e = Episode(
        id="lex-495",
        podcast_id="lex-fridman-podcast",
        guid="lex-fridman-podcast-495",
        title="Vikings, Ragnar, Berserkers, Valhalla & the Warriors of the Viking Age",
        audio_url="https://lexfridman.com/lars-brownworth/#038;utm_medium=rss&#038;utm_campaign=lars-brownworth",
        published="2026-05-09",
        description="Lars Brownworth is a historian, teacher, podcaster, and author specializing in Viking history, medieval Europe, and the Byzantine Empire.",

    )
    assert e.downloaded is False
    assert e.completed is False
    assert e.file_size_bytes is None
    assert e.file_path is None
    assert e.position_seconds == 0
    assert e.duration_seconds is None

def test_library_round_trip(tmp_path):

    library_path= tmp_path / "library.json"
    episode_dir= tmp_path / "episodes"

    lib= Library.load(library_path, episode_dir) 

    lib.podcasts.append(Podcast(
        id="lex", title="Lex", author="Lex",
        feed_url="https://x.com/feed", description="d",
        subscribed_at="2026-01-01", last_refreshed="2026-01-01",
    ))

    lib.save()

    lib2=Library.load(library_path, episode_dir)

    assert len(lib2.podcasts) == 1
    assert lib2.podcasts[0].title == "Lex"

def test_library_load_nonexistent(tmp_path):
    library_path= tmp_path / "library.json"
    episodes_dir = tmp_path / "episodes"

    lib=Library.load(library_path,episodes_dir)

    assert len(lib.podcasts) == 0
    assert lib.podcasts == []

def test_library_load_corrupted(tmp_path):
    library_path = tmp_path / "library.json"
    library_path.write_text("{ not valid json")   

    with pytest.raises(LibraryCorruptedError):
        Library.load(library_path, tmp_path / "episodes")

def test_search_podcasts():
    fake_result={

        "results": [
            {'collectionName': 'Hard Fork', 
            'artistName': 'The New York Times', 
            'feedUrl': 'https://feeds.simplecast.com/6HKOhNgS', 
            'trackCount': 196,
            }
        ]
    }

    fake_response=Mock()
    fake_response.json.return_value=fake_result

    with patch("project.requests.get",return_value=fake_response):
        results=search_podcasts("hard fork")

    assert len(results) == 1
    assert results[0]["title"] == "Hard Fork"
    assert results[0]["author"]  == 'The New York Times'
    assert results[0]["feed_url"]  == 'https://feeds.simplecast.com/6HKOhNgS'
    assert results[0]["episode_count"] == 196

def test_feed_parser():

    parsed_feed=parse_feed("tests/fixtures/hard-fork.xml")

    assert len(parsed_feed)==2
    assert len(parsed_feed["episodes"])==3
    assert parsed_feed["podcast"].get("title") == "Hard Fork"
    assert parsed_feed["podcast"].get("author") == "The New York Times"
    assert parsed_feed["podcast"]["id"] == "hard-fork"
    



