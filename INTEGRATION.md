# Netease Cloud Music (singo) + Music Assistant Integration Guide

This guide explains how to integrate the [singo](https://github.com/unknown/singo) (Netease Cloud Music API in Go) project with [Music Assistant](https://github.com/music-assistant/server).

## Overview

*   **singo**: Acts as the backend API provider. It communicates with Netease Cloud Music servers and exposes a RESTful API.
*   **Music Assistant (MA)**: Acts as the central music server/player. It needs a "Provider" plugin to talk to `singo`.

## Integration Strategy

To combine these two projects, you need to create a **Custom Music Provider** within Music Assistant that queries the `singo` API.

### 1. Run `singo`

First, ensure `singo` is running and accessible.

```bash
# In the singo directory
go run main.go
# By default, it listens on port 3333
```

### 2. Create a Music Assistant Provider

In your Music Assistant installation, you need to add a new directory under `music_assistant/providers/`. Let's call it `netease`.

**Directory Structure:**
```
music_assistant/providers/netease/
├── __init__.py      # The main provider logic
├── manifest.json    # Metadata about the provider
└── icon.svg         # (Optional) Provider icon
```

#### `manifest.json`

```json
{
  "type": "music",
  "domain": "netease",
  "name": "Netease Cloud Music",
  "description": "Stream music from Netease via singo API",
  "codeowners": [],
  "requirements": [],
  "documentation": "https://github.com/your/docs",
  "multi_instance": true
}
```

#### `__init__.py` (Conceptual Implementation)

You need to subclass `MusicProvider` and implement key methods.

```python
from __future__ import annotations
from typing import AsyncGenerator
from music_assistant.models.music_provider import MusicProvider
from music_assistant_models.media_items import (
    Artist, Album, Track, Playlist, SearchResults,
    MediaType, StreamDetails, AudioFormat, ContentType
)
from music_assistant_models.config_entries import ConfigEntry

class NeteaseProvider(MusicProvider):
    """Provider for Netease Cloud Music (via singo)."""

    _singo_url: str = "http://localhost:3333" # Should be configurable via ConfigEntry

    async def setup(self) -> None:
        """Initialize."""
        # Check connection to singo
        pass

    async def search(self, search_query: str, media_types=list[MediaType], limit: int = 5) -> SearchResults:
        """Search for media."""
        # Call singo: GET /search?keywords={search_query}
        # Parse JSON response and map to MA objects (Artist, Album, Track)
        pass

    async def get_library_playlists(self) -> AsyncGenerator[Playlist, None]:
        """Retrieve user playlists."""
        # Call singo: GET /user/playlist?uid={user_id}
        pass

    async def get_playlist_tracks(self, prov_playlist_id: str, page: int = 0) -> list[Track]:
        """Get tracks in a playlist."""
        # Call singo: GET /playlist/detail?id={prov_playlist_id}
        # Map Netease songs to MA Track objects
        pass

    async def get_stream_details(self, item_id: str) -> StreamDetails:
        """Get stream URL."""
        # Call singo: GET /song/url?id={item_id}
        # Response usually contains a 'url' field

        # Example mapping
        return StreamDetails(
            provider=self.lookup_key,
            item_id=item_id,
            audio_format=AudioFormat(content_type=ContentType.MP3), # or detected type
            path=stream_url,
            stream_type=StreamType.HTTP
        )
```

## API Mapping Reference

| Music Assistant Action | singo API Endpoint | Notes |
|------------------------|--------------------|-------|
| **Search** | `GET /search` | `keywords` param. `type` param (1: song, 10: album, 100: artist, 1000: playlist) |
| **Get Artist** | `GET /artists` or `/artist/desc` | Requires Artist ID |
| **Get Album** | `GET /album` | Requires Album ID |
| **Get Stream URL** | `GET /song/url` | Requires Song ID. Check `data[0].url` in response. |
| **User Playlists** | `GET /user/playlist` | Requires User ID (uid) |
| **Playlist Details** | `GET /playlist/detail` | Requires Playlist ID |
| **Login** | `GET /login/cellphone` | Or `/login/email`. Needed for accessing user library. |

## Development Steps

1.  **Clone Music Assistant**: `git clone https://github.com/music-assistant/server`
2.  **Scaffold Provider**: Create the `netease` folder in `providers/`.
3.  **Implement Auth**: Add `ConfigEntry` for Username/Password or Phone/Captcha, and use `singo`'s `/login` endpoints to authenticate. Store the cookie.
4.  **Implement Search**: Map `search_query` to `singo`'s `/search`.
5.  **Implement Playback**: Use `/song/url` to get the actual audio link.

This architecture decouples the complex Netease encryption/API logic (handled by `singo` in Go) from the media management (handled by `Music Assistant` in Python).
