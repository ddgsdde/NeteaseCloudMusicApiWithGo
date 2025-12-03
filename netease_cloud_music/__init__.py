"""Netease Cloud Music Provider for Music Assistant."""
from __future__ import annotations

from typing import TYPE_CHECKING, List, Optional

import aiohttp

from music_assistant_models.enums import (
    ProviderFeature,
    StreamType,
    ImageType,
    MediaType,
    ContentType,
)
from music_assistant_models.media_items import (
    Artist,
    Album,
    Track,
    Playlist,
    MediaItemImage,
    SearchResults,
    StreamDetails,
    AudioFormat,
)
from music_assistant_models.errors import LoginFailed, MediaNotFoundError

if TYPE_CHECKING:
    from music_assistant_models.config_entries import ProviderConfig
    from music_assistant.server import MusicAssistant
    from music_assistant.server.models import ProviderData

from music_assistant.server.models.music_provider import MusicProvider


class NeteaseProvider(MusicProvider):
    """Provider for Netease Cloud Music."""

    _api_url: str = ""
    _cookie: str = ""
    _user_id: str = ""

    async def setup(self) -> None:
        """Handle async initialization of the provider."""
        self._api_url = self.config.get_value("api_url").rstrip("/")

        # Try to login
        await self._login()

    @property
    def supported_features(self) -> tuple[ProviderFeature, ...]:
        """Return the features supported by this Provider."""
        return (
            ProviderFeature.SEARCH,
            ProviderFeature.LIBRARY_PLAYLISTS,
        )

    async def _login(self) -> None:
        """Login to Netease Cloud Music."""
        phone = self.config.get_value("phone")
        email = self.config.get_value("email")
        password = self.config.get_value("password")

        if not password:
            # Maybe already logged in or guest mode?
            # But the requirement implies accessing personal playlists.
            pass

        url = ""
        params = {}

        if phone and password:
            url = f"{self._api_url}/login/cellphone"
            params = {"phone": phone, "password": password}
        elif email and password:
            url = f"{self._api_url}/login"
            params = {"email": email, "password": password}
        else:
            # Attempt to use without login (might work for search/public)
            return

        async with self.mass.http_session.get(url, params=params) as response:
            if response.status != 200:
                raise LoginFailed(f"Login failed: {response.status}")

            data = await response.json()
            if data.get("code") != 200:
                raise LoginFailed(f"Login failed: {data.get('msg') or data.get('message')}")

            # Store cookie if needed, but the Go server handles session via cookies usually.
            # However, since we are a client to the Go server, the Go server maintains the session *for itself*?
            # Wait, the Go server likely sets a cookie on the client (us).
            # We need to pass that cookie back in subsequent requests.
            # aiohttp session might handle this automatically if we use the same session?
            # But `self.mass.http_session` is shared.
            # We should probably check if we need to manually handle the cookie.

            # The Go implementation (singo) uses `middleware.Session` and stores session in cookie/file.
            # When we call /login, it sets a cookie.
            # We need to make sure we send that cookie back.

            # Since `self.mass.http_session` is shared, we might want to use a separate session or manage headers.
            # But for now let's assume we might need to capture the cookie from the response headers.

            cookies = response.cookies
            # We can construct a cookie string or use a CookieJar.
            # For simplicity, let's extract the cookies and send them in headers manually if needed.
            # However, the user ID is also in the response body.
            if "profile" in data:
                self._user_id = str(data["profile"]["userId"])

            # Note: The Go server likely expects the cookies "MUSIC_U", "__csrf", etc.
            # We will rely on aiohttp's cookie jar if we used a dedicated session,
            # but since we use mass.http_session, we might need to be careful.
            # Let's create a local `self._cookies` dict to pass in requests.
            self._cookies = {}
            for cookie in cookies.values():
                self._cookies[cookie.key] = cookie.value

    async def _get_data(self, endpoint: str, params: dict = None) -> dict:
        """Helper to get data from API."""
        url = f"{self._api_url}/{endpoint}"
        async with self.mass.http_session.get(
            url, params=params, cookies=self._cookies if hasattr(self, "_cookies") else None
        ) as response:
            if response.status != 200:
                # Handle error
                return None
            return await response.json()

    async def get_library_playlists(self) -> List[Playlist]:
        """Retrieve all library playlists from the provider."""
        if not self._user_id:
            return []

        endpoint = "user/playlist"
        limit = 30
        offset = 0
        playlists = []

        while True:
            data = await self._get_data(endpoint, {"uid": self._user_id, "limit": limit, "offset": offset})

            if not data or data.get("code") != 200:
                break

            items = data.get("playlist", [])
            if not items:
                break

            for item in items:
                playlist = Playlist(
                    item_id=str(item["id"]),
                    provider=self.domain,
                    name=item["name"],
                    uri=f"netease://playlist/{item['id']}",
                )
                playlist.is_editable = (str(item.get("creator", {}).get("userId")) == self._user_id)
                if item.get("coverImgUrl"):
                    playlist.metadata.images = [MediaItemImage(type=ImageType.THUMBNAIL, path=item["coverImgUrl"])]

                playlists.append(playlist)

            if len(items) < limit:
                break

            offset += limit

        return playlists

    async def get_playlist_tracks(self, playlist_id: str) -> List[Track]:
        """Retrieve all playlist tracks from the provider."""
        # /playlist/track/all or /playlist/detail
        # Use /playlist/detail to get ids then /song/detail? But /playlist/track/all is better if available (Binaryify api has it)
        # Looking at router.go, it has `v1.GET("playlist/tracks", api.PlaylistTracks)`
        # Let's try `playlist/tracks`.

        endpoint = "playlist/tracks"
        # router.go: v1.GET("playlist/tracks", api.PlaylistTracks)
        # Note: In the original Node API, /playlist/track/all gets all tracks.
        # Check what api.PlaylistTracks does. It might be add/remove tracks?
        # Let's check router.go again.
        # v1.GET("playlist/tracks", api.PlaylistTracks)
        # v1.GET("playlist/detail", api.PlaylistDetail)

        # If I can't be sure, `playlist/detail` usually returns tracks (at least the first few or all ids).

        data = await self._get_data("playlist/detail", {"id": playlist_id})
        if not data or data.get("code") != 200:
            return []

        track_ids = [str(t["id"]) for t in data.get("playlist", {}).get("trackIds", [])]

        # Now we need details for these tracks.
        # /song/detail takes ids separated by comma.
        tracks = []

        # Batch requests if necessary (e.g. 50 at a time)
        chunk_size = 50
        for i in range(0, len(track_ids), chunk_size):
            chunk = track_ids[i:i + chunk_size]
            ids_str = ",".join(chunk)

            song_data = await self._get_data("song/detail", {"ids": ids_str})
            if not song_data or song_data.get("code") != 200:
                continue

            for song in song_data.get("songs", []):
                track = await self._parse_track(song)
                tracks.append(track)

        return tracks

    async def _parse_track(self, song_data: dict) -> Track:
        """Parse a track from Netease data."""
        track_id = str(song_data["id"])
        track = Track(
            item_id=track_id,
            provider=self.domain,
            name=song_data["name"],
            uri=f"netease://track/{track_id}",
            duration=song_data.get("dt", 0) / 1000,
        )

        # Album
        if "al" in song_data:
            album = song_data["al"]
            track.album = Album(
                item_id=str(album["id"]),
                provider=self.domain,
                name=album["name"],
                uri=f"netease://album/{album['id']}",
            )
            if album.get("picUrl"):
                track.metadata.images = [MediaItemImage(type=ImageType.THUMBNAIL, path=album["picUrl"])]

        # Artists
        for ar in song_data.get("ar", []):
            track.artists.append(
                Artist(
                    item_id=str(ar["id"]),
                    provider=self.domain,
                    name=ar["name"],
                    uri=f"netease://artist/{ar['id']}",
                )
            )

        return track

    async def get_track(self, prov_track_id: str) -> Track:
        """Get full track details by id."""
        data = await self._get_data("song/detail", {"ids": prov_track_id})
        if not data or data.get("code") != 200 or not data.get("songs"):
             raise MediaNotFoundError(f"Track {prov_track_id} not found")
        return await self._parse_track(data["songs"][0])

    async def get_artist(self, prov_artist_id: str) -> Artist:
        """Get full artist details by id."""
        # /artist/detail or /artists
        data = await self._get_data("artists", {"id": prov_artist_id})
        if not data or data.get("code") != 200:
             raise MediaNotFoundError(f"Artist {prov_artist_id} not found")

        artist_data = data.get("artist", {})
        artist = Artist(
            item_id=prov_artist_id,
            provider=self.domain,
            name=artist_data.get("name"),
            uri=f"netease://artist/{prov_artist_id}",
            sort_name=artist_data.get("name"),
        )
        if artist_data.get("picUrl"):
             artist.metadata.images = [MediaItemImage(type=ImageType.THUMBNAIL, path=artist_data["picUrl"])]
        if artist_data.get("briefDesc"):
             artist.metadata.description = artist_data["briefDesc"]

        return artist

    async def get_album(self, prov_album_id: str) -> Album:
        """Get full album details by id."""
        # /album
        data = await self._get_data("album", {"id": prov_album_id})
        if not data or data.get("code") != 200:
             raise MediaNotFoundError(f"Album {prov_album_id} not found")

        album_data = data.get("album", {})
        album = Album(
            item_id=prov_album_id,
            provider=self.domain,
            name=album_data.get("name"),
            uri=f"netease://album/{prov_album_id}",
            year=int(album_data.get("publishTime", 0) / 1000 / 3600 / 24 / 365) + 1970 if album_data.get("publishTime") else None
        )
        if album_data.get("picUrl"):
             album.metadata.images = [MediaItemImage(type=ImageType.THUMBNAIL, path=album_data["picUrl"])]
        if album_data.get("description"):
             album.metadata.description = album_data["description"]

        # Artist
        if album_data.get("artist"):
             ar = album_data["artist"]
             album.artists.append(
                 Artist(
                     item_id=str(ar["id"]),
                     provider=self.domain,
                     name=ar["name"],
                     uri=f"netease://artist/{ar['id']}",
                 )
             )

        return album

    async def get_playlist(self, prov_playlist_id: str) -> Playlist:
        """Get full playlist details by id."""
        data = await self._get_data("playlist/detail", {"id": prov_playlist_id})
        if not data or data.get("code") != 200:
             raise MediaNotFoundError(f"Playlist {prov_playlist_id} not found")

        pl_data = data.get("playlist", {})
        playlist = Playlist(
            item_id=prov_playlist_id,
            provider=self.domain,
            name=pl_data.get("name"),
            uri=f"netease://playlist/{prov_playlist_id}",
        )
        playlist.is_editable = (str(pl_data.get("creator", {}).get("userId")) == self._user_id)
        if pl_data.get("coverImgUrl"):
            playlist.metadata.images = [MediaItemImage(type=ImageType.THUMBNAIL, path=pl_data["coverImgUrl"])]
        if pl_data.get("description"):
             playlist.metadata.description = pl_data["description"]

        return playlist

    async def get_stream_details(self, item_id: str) -> StreamDetails:
        """Get stream details for a track."""
        # /song/url
        data = await self._get_data("song/url", {"id": item_id})
        if not data or data.get("code") != 200:
            raise MediaNotFoundError(f"Song {item_id} not found")

        data_arr = data.get("data", [])
        if not data_arr:
             raise MediaNotFoundError(f"Song {item_id} not found")

        song_info = data_arr[0]
        url = song_info.get("url")
        if not url:
             raise MediaNotFoundError(f"Song {item_id} has no URL (possibly paid or copyright restriction)")

        # Check type
        content_type = ContentType.UNKNOWN

        # Try to guess from 'type' or 'encodeType' field in API response
        # type usually maps to format (e.g. mp3, flac)
        encode_type = song_info.get("type", "").lower()
        if not encode_type:
            encode_type = song_info.get("encodeType", "").lower()

        if "mp3" in encode_type:
            content_type = ContentType.MP3
        elif "flac" in encode_type:
            content_type = ContentType.FLAC
        elif "m4a" in encode_type or "aac" in encode_type:
            content_type = ContentType.M4A

        # Fallback to extension check if still unknown
        if content_type == ContentType.UNKNOWN:
            if url.endswith(".mp3"):
                content_type = ContentType.MP3
            elif url.endswith(".flac"):
                content_type = ContentType.FLAC
            elif url.endswith(".m4a"):
                content_type = ContentType.M4A

        return StreamDetails(
            provider=self.domain,
            item_id=item_id,
            content_type=content_type,
            direct_url=url,
        )

    async def search(
        self, search_query: str, media_types: Optional[List[MediaType]] = None, limit: int = 5
    ) -> SearchResults:
        """Perform search on musicprovider."""
        results = SearchResults()

        if not media_types:
            media_types = [MediaType.TRACK, MediaType.PLAYLIST, MediaType.ARTIST, MediaType.ALBUM]

        # Search types: 1: song, 10: album, 100: artist, 1000: playlist
        # We can implement multiple calls if needed.

        # Search Songs
        if MediaType.TRACK in media_types:
            data = await self._get_data("search", {"keywords": search_query, "type": 1, "limit": limit})
            if data and data.get("code") == 200:
                for song in data.get("result", {}).get("songs", []):
                    results.tracks.append(await self._parse_track(song))

        # Search Playlists
        if MediaType.PLAYLIST in media_types:
            data = await self._get_data("search", {"keywords": search_query, "type": 1000, "limit": limit})
            if data and data.get("code") == 200:
                for item in data.get("result", {}).get("playlists", []):
                    playlist = Playlist(
                        item_id=str(item["id"]),
                        provider=self.domain,
                        name=item["name"],
                        uri=f"netease://playlist/{item['id']}",
                    )
                    if item.get("coverImgUrl"):
                        playlist.metadata.images = [MediaItemImage(type=ImageType.THUMBNAIL, path=item["coverImgUrl"])]
                    results.playlists.append(playlist)

        return results
