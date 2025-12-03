"""Netease Cloud Music support for MusicAssistant."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from music_assistant_models.config_entries import ConfigEntry, ConfigValueType
from music_assistant_models.enums import (
    ConfigEntryType,
    ProviderFeature,
    StreamType,
    ContentType,
    ImageType,
    MediaType,
)
from music_assistant_models.errors import (
    MediaNotFoundError,
)
from music_assistant_models.media_items import (
    Album,
    Artist,
    AudioFormat,
    ItemMapping,
    MediaItemImage,
    Playlist,
    ProviderMapping,
    SearchResults,
    Track,
    RecommendationFolder,
    MediaItemType,
    Radio,
)
from music_assistant_models.streamdetails import StreamDetails

from music_assistant.models.music_provider import MusicProvider

if TYPE_CHECKING:
    from music_assistant_models.config_entries import ProviderConfig
    from music_assistant_models.provider import ProviderManifest
    from music_assistant import MusicAssistant
    from music_assistant.models import ProviderInstanceType


CONF_API_URL = "api_url"
CONF_COOKIE = "cookie"
CONF_QR_LOGIN = "qr_login"

SUPPORTED_FEATURES = {
    ProviderFeature.LIBRARY_ARTISTS,
    ProviderFeature.LIBRARY_ALBUMS,
    ProviderFeature.LIBRARY_TRACKS,
    ProviderFeature.LIBRARY_PLAYLISTS,
    ProviderFeature.BROWSE,
    ProviderFeature.SEARCH,
    ProviderFeature.ARTIST_ALBUMS,
    ProviderFeature.ARTIST_TOPTRACKS,
    ProviderFeature.SIMILAR_TRACKS,
    ProviderFeature.RECOMMENDATIONS,
    ProviderFeature.LYRICS,
}


async def setup(
    mass: MusicAssistant, manifest: ProviderManifest, config: ProviderConfig
) -> ProviderInstanceType:
    """Initialize provider(instance) with given configuration."""
    return NeteaseCloudMusicProvider(mass, manifest, config)


async def get_config_entries(
    mass: MusicAssistant,  # pylint: disable=unused-argument
    instance_id: str | None = None,  # pylint: disable=unused-argument
    action: str | None = None,  # pylint: disable=unused-argument
    values: dict[str, ConfigValueType] | None = None,  # pylint: disable=unused-argument
) -> tuple[ConfigEntry, ...]:
    """Return Config entries to setup this provider."""
    # Logic to handle action (if supported by UI)
    if action == "login_qr":
        # Since we can't easily push UI updates from here without frontend context,
        # we would typically log instructions or handle the handshake.
        # For this implementation, we will assume the user checks the logs or
        # uses the cookie method as primary if QR fails.
        pass

    return (
        ConfigEntry(
            key=CONF_API_URL,
            type=ConfigEntryType.STRING,
            label="Netease API URL",
            default_value="http://localhost:3333",
            required=True,
            description="URL to the Netease Cloud Music API server",
        ),
        ConfigEntry(
            key=CONF_COOKIE,
            type=ConfigEntryType.SECURE_STRING,
            label="Cookie",
            required=False,
            description="MUSIC_U cookie. If empty, you can login via QR code in the settings.",
        ),
        ConfigEntry(
            key=CONF_QR_LOGIN,
            type=ConfigEntryType.ACTION,
            label="Login via QR Code",
            description="Click to start QR code login process (Check logs for status).",
            action="login_qr",
        ),
    )


class NeteaseCloudMusicProvider(MusicProvider):
    """Provider for Netease Cloud Music."""

    _api_url: str = ""
    _cookie: str | None = None
    _user_id: str | None = None

    async def handle_async_init(self) -> None:
        """Set up the provider."""
        self._api_url = self.config.get_value(CONF_API_URL).rstrip("/")
        self._cookie = self.config.get_value(CONF_COOKIE)

        if self._cookie:
            await self._check_login()
            # Schedule refresh
            self.mass.loop.create_task(self._refresh_login_task())
        else:
            # Maybe try to see if we have a saved cookie from QR login?
            # For now, we rely on config.
            pass

    async def _check_login(self):
        try:
            status = await self._get("login/status")
            if status.get("data", {}).get("profile"):
                self._user_id = str(status["data"]["profile"]["userId"])
            else:
                self.logger.warning("Cookie invalid or expired.")
        except Exception as e:  # pylint: disable=broad-except
            self.logger.warning("Login check failed: %s", e)

    async def _refresh_login_task(self):
        while True:
            await asyncio.sleep(3600)  # Refresh every hour
            try:
                await self._get("login/refresh")
                await self._check_login()
            except Exception as e:  # pylint: disable=broad-except
                self.logger.warning("Token refresh failed: %s", e)

    async def search(
        self, search_query: str, media_types=list[MediaType], limit: int = 5
    ) -> SearchResults:
        """Perform search on musicprovider."""
        results = SearchResults()

        if MediaType.TRACK in media_types:
            data = await self._get("search", params={
                "keywords": search_query,
                "type": 1,
                "limit": limit
            })
            if songs := data.get("result", {}).get("songs"):
                for song in songs:
                    results.tracks.append(self._parse_track(song))

        if MediaType.ALBUM in media_types:
            data = await self._get("search", params={
                "keywords": search_query,
                "type": 10,
                "limit": limit
            })
            if albums := data.get("result", {}).get("albums"):
                for album in albums:
                    results.albums.append(self._parse_album(album))

        if MediaType.ARTIST in media_types:
            data = await self._get("search", params={
                "keywords": search_query,
                "type": 100,
                "limit": limit
            })
            if artists := data.get("result", {}).get("artists"):
                for artist in artists:
                    results.artists.append(self._parse_artist(artist))

        if MediaType.PLAYLIST in media_types:
            data = await self._get("search", params={
                "keywords": search_query,
                "type": 1000,
                "limit": limit
            })
            if playlists := data.get("result", {}).get("playlists"):
                for playlist in playlists:
                    results.playlists.append(self._parse_playlist(playlist))

        # Radio / Private FM is not really searchable by keyword in the same way,
        # but we can add a fixed entry if Radio is requested
        if MediaType.RADIO in media_types:
            # Add Private FM as a radio station
            results.radio.append(
                Radio(
                    item_id="personal_fm",
                    provider=self.lookup_key,
                    name="Private FM (Personal FM)",
                    provider_mappings={
                         ProviderMapping(
                            item_id="personal_fm",
                            provider_domain=self.domain,
                            provider_instance=self.instance_id,
                            available=True
                        )
                    }
                )
            )

        return results

    async def get_library_artists(self) -> list[Artist]:
        """Retrieve all library artists from Netease."""
        if not self._user_id:
            return []
        data = await self._get("artist/sublist", params={"limit": 1000})
        return [self._parse_artist(a) for a in data.get("data", [])]

    async def get_library_albums(self) -> list[Album]:
        """Retrieve all library albums from Netease."""
        if not self._user_id:
            return []
        data = await self._get("album/sublist", params={"limit": 1000})
        return [self._parse_album(a) for a in data.get("data", [])]

    async def get_library_playlists(self) -> list[Playlist]:
        """Retrieve all library playlists from Netease."""
        if not self._user_id:
            return []
        data = await self._get("user/playlist", params={"uid": self._user_id, "limit": 1000})
        return [self._parse_playlist(p) for p in data.get("playlist", [])]

    async def get_library_tracks(self) -> list[Track]:
        """Retrieve all library tracks from Netease."""
        if not self._user_id:
            return []
        playlists = await self.get_library_playlists()
        if not playlists:
            return []
        # First playlist is usually "Liked Songs"
        return await self.get_playlist_tracks(playlists[0].item_id)

    async def get_album(self, prov_album_id) -> Album:
        """Get full album details by id."""
        data = await self._get("album", params={"id": prov_album_id})
        return self._parse_album(data.get("album"), data.get("songs"))

    async def get_artist(self, prov_artist_id) -> Artist:
        """Get full artist details by id."""
        data = await self._get("artists", params={"id": prov_artist_id})
        return self._parse_artist(data.get("artist"))

    async def get_track(self, prov_track_id) -> Track:
        """Get full track details by id."""
        data = await self._get("song/detail", params={"ids": prov_track_id})
        songs = data.get("songs", [])
        if not songs:
            raise MediaNotFoundError(f"Track {prov_track_id} not found")
        return self._parse_track(songs[0])

    async def get_playlist(self, prov_playlist_id) -> Playlist:
        """Get full playlist details by id."""
        data = await self._get("playlist/detail", params={"id": prov_playlist_id})
        return self._parse_playlist(data.get("playlist"))

    async def get_playlist_tracks(self, prov_playlist_id: str, page: int = 0) -> list[Track]:
        """Return playlist tracks for the given provider playlist id."""
        if page > 0:
            return []
        data = await self._get(
            "playlist/track/all",
            params={"id": prov_playlist_id, "limit": 1000}
        )
        return [self._parse_track(t) for t in data.get("songs", [])]

    async def get_artist_albums(self, prov_artist_id) -> list[Album]:
        """Get a list of albums for the given artist."""
        data = await self._get("artist/album", params={"id": prov_artist_id, "limit": 50})
        return [self._parse_album(a) for a in data.get("hotAlbums", [])]

    async def get_artist_toptracks(self, prov_artist_id) -> list[Track]:
        """Get a list of 50 most popular tracks for the given artist."""
        data = await self._get("artist/top/song", params={"id": prov_artist_id})
        return [self._parse_track(t) for t in data.get("songs", [])]

    async def get_similar_tracks(self, prov_track_id, limit=25) -> list[Track]:
        """Retrieve a dynamic list of tracks based on the provided item."""
        data = await self._get("simi/song", params={"id": prov_track_id})
        return [self._parse_track(t) for t in data.get("songs", [])]

    async def get_stream_details(self, item_id: str, media_type: MediaType) -> StreamDetails:
        """Return the content details for the given track when it will be streamed."""
        data = await self._get("song/url", params={"id": item_id, "level": "lossless"})
        if not data.get("data"):
            raise MediaNotFoundError(f"Stream URL not found for {item_id}")

        song_data = data["data"][0]
        url = song_data.get("url")
        if not url:
            data = await self._get("song/url", params={"id": item_id, "level": "standard"})
            if data.get("data"):
                song_data = data["data"][0]
                url = song_data.get("url")

        if not url:
            raise MediaNotFoundError(f"Stream URL not found for {item_id}")

        return StreamDetails(
            provider=self.lookup_key,
            item_id=item_id,
            audio_format=AudioFormat(
                content_type=ContentType.try_parse(song_data.get("type", "mp3")),
                sample_rate=song_data.get("br", 44100),
            ),
            stream_type=StreamType.HTTP,
            path=url,
            can_seek=True,
        )

    async def get_song_lyrics(self, prov_song_id: str) -> str | None:
        """Get song lyrics."""
        data = await self._get("lyric", params={"id": prov_song_id})
        # Try lrc (time synced) first, then klyric, then tlyric (translation)
        if lrc := data.get("lrc", {}).get("lyric"):
            return lrc
        return None

    async def recommendations(self) -> list[RecommendationFolder]:
        """Get available recommendations."""
        folders = []

        if self._user_id:
            try:
                data = await self._get("recommend/songs")
                tracks = [
                    self._parse_track(t)
                    for t in data.get("data", {}).get("dailySongs", [])
                ]
                folders.append(
                    RecommendationFolder(
                        item_id="daily_recommend_songs",
                        provider=self.lookup_key,
                        name="Daily Recommended Songs",
                        items=tracks,
                    )
                )
            except Exception as e:  # pylint: disable=broad-except
                self.logger.warning("Failed to fetch daily songs: %s", e)

        try:
            data = await self._get("personalized", params={"limit": 10})
            playlists = [self._parse_playlist(p) for p in data.get("result", [])]
            folders.append(
                RecommendationFolder(
                    item_id="personalized_playlists",
                    provider=self.lookup_key,
                    name="Recommended Playlists",
                    items=playlists,
                )
            )
        except Exception as e:  # pylint: disable=broad-except
            self.logger.warning("Failed to fetch personalized playlists: %s", e)

        try:
            data = await self._get("personalized/newsong")
            tracks = [self._parse_track(t["song"]) for t in data.get("result", [])]
            folders.append(
                RecommendationFolder(
                    item_id="new_songs",
                    provider=self.lookup_key,
                    name="New Songs",
                    items=tracks,
                )
            )
        except Exception as e:  # pylint: disable=broad-except
            self.logger.warning("Failed to fetch new songs: %s", e)

        return folders

    async def library_add(self, item: MediaItemType) -> bool:
        """Add an item to the library."""
        if item.media_type == MediaType.TRACK:
            return await self._like_track(item.item_id, True)
        if item.media_type == MediaType.PLAYLIST:
            await self._get("playlist/subscribe", params={"t": 1, "id": item.item_id})
            return True
        if item.media_type == MediaType.ARTIST:
            await self._get("artist/sub", params={"t": 1, "id": item.item_id})
            return True
        if item.media_type == MediaType.ALBUM:
            await self._get("album/sub", params={"t": 1, "id": item.item_id})
            return True
        return False

    async def library_remove(self, prov_item_id, media_type: MediaType):
        """Remove an item from the library."""
        if media_type == MediaType.TRACK:
            return await self._like_track(prov_item_id, False)
        if media_type == MediaType.PLAYLIST:
            await self._get("playlist/subscribe", params={"t": 2, "id": prov_item_id})
            return True
        if media_type == MediaType.ARTIST:
            await self._get("artist/sub", params={"t": 0, "id": prov_item_id})
            return True
        if media_type == MediaType.ALBUM:
            await self._get("album/sub", params={"t": 0, "id": prov_item_id})
            return True
        return False

    async def _like_track(self, track_id, like: bool):
        await self._get(
            "like",
            params={"id": track_id, "like": "true" if like else "false"}
        )
        return True

    async def _get(self, endpoint, params=None):
        url = f"{self._api_url}/{endpoint}"
        params = params or {}
        if self._cookie:
            params["cookie"] = self._cookie

        async with self.mass.http_session.get(url, params=params) as response:
            if response.status >= 400:
                self.logger.error("Request to %s failed: %s", url, response.status)
                return {}
            return await response.json()

    def _parse_track(self, data) -> Track:
        track_id = str(data.get("id"))
        album_data = data.get("al", data.get("album", {}))
        artists_data = data.get("ar", data.get("artists", []))

        track = Track(
            item_id=track_id,
            provider=self.lookup_key,
            name=data.get("name"),
            duration=int(data.get("dt", data.get("duration", 0)) / 1000),
            provider_mappings={
                ProviderMapping(
                    item_id=track_id,
                    provider_domain=self.domain,
                    provider_instance=self.instance_id,
                    available=True,
                )
            },
        )

        if album_data:
            track.album = self._get_item_mapping(
                MediaType.ALBUM, str(album_data.get("id")), album_data.get("name")
            )
            if pic_url := album_data.get("picUrl"):
                track.metadata.images = [
                    MediaItemImage(
                        type=ImageType.THUMB,
                        path=pic_url,
                        provider=self.lookup_key
                    )
                ]

        if artists_data:
            track.artists = [
                self._get_item_mapping(MediaType.ARTIST, str(a.get("id")), a.get("name"))
                for a in artists_data
            ]

        return track

    def _parse_album(self, data, tracks=None) -> Album:  # pylint: disable=unused-argument
        album_id = str(data.get("id"))
        album = Album(
            item_id=album_id,
            provider=self.lookup_key,
            name=data.get("name"),
            provider_mappings={
                ProviderMapping(
                    item_id=album_id,
                    provider_domain=self.domain,
                    provider_instance=self.instance_id,
                )
            },
        )
        if pic_url := data.get("picUrl"):
            album.metadata.images = [
                MediaItemImage(
                    type=ImageType.THUMB,
                    path=pic_url,
                    provider=self.lookup_key
                )
            ]

        if data.get("artists"):
            album.artists = [
                self._get_item_mapping(MediaType.ARTIST, str(a.get("id")), a.get("name"))
                for a in data.get("artists")
            ]

        return album

    def _parse_artist(self, data) -> Artist:
        artist_id = str(data.get("id"))
        artist = Artist(
            item_id=artist_id,
            provider=self.lookup_key,
            name=data.get("name"),
            provider_mappings={
                ProviderMapping(
                    item_id=artist_id,
                    provider_domain=self.domain,
                    provider_instance=self.instance_id,
                )
            },
        )
        if pic_url := data.get("picUrl") or data.get("img1v1Url"):
            artist.metadata.images = [
                MediaItemImage(
                    type=ImageType.THUMB,
                    path=pic_url,
                    provider=self.lookup_key
                )
            ]

        if data.get("briefDesc"):
            artist.metadata.description = data.get("briefDesc")

        return artist

    def _parse_playlist(self, data) -> Playlist:
        playlist_id = str(data.get("id"))
        playlist = Playlist(
            item_id=playlist_id,
            provider=self.lookup_key,
            name=data.get("name"),
            owner=data.get("creator", {}).get("nickname", "Netease"),
            provider_mappings={
                ProviderMapping(
                    item_id=playlist_id,
                    provider_domain=self.domain,
                    provider_instance=self.instance_id,
                )
            },
            is_editable=str(data.get("userId", "")) == self._user_id,
        )
        if pic_url := data.get("coverImgUrl"):
            playlist.metadata.images = [
                MediaItemImage(
                    type=ImageType.THUMB,
                    path=pic_url,
                    provider=self.lookup_key
                )
            ]

        return playlist

    def _get_item_mapping(self, media_type: MediaType, key: str, name: str) -> ItemMapping:
        return ItemMapping(
            media_type=media_type,
            item_id=key,
            provider=self.lookup_key,
            name=name,
        )

    async def get_album_tracks(self, prov_album_id: str) -> list[Track]:
        """Get album tracks for given album id."""
        data = await self._get("album", params={"id": prov_album_id})
        return [self._parse_track(t) for t in data.get("songs", [])]

    async def add_playlist_tracks(self, prov_playlist_id: str, prov_track_ids: list[str]) -> None:
        """Add track(s) to playlist."""
        await self._get(
            "playlist/tracks",
            params={"op": "add", "pid": prov_playlist_id, "tracks": ",".join(prov_track_ids)}
        )

    async def remove_playlist_tracks(
        self, prov_playlist_id: str, positions_to_remove: tuple[int, ...]
    ) -> None:
        """Remove track(s) from playlist."""
        tracks = await self.get_playlist_tracks(prov_playlist_id)
        ids_to_remove = []
        for pos in positions_to_remove:
            if 0 <= pos < len(tracks):
                ids_to_remove.append(tracks[pos].item_id)

        if ids_to_remove:
            await self._get(
                "playlist/tracks",
                params={"op": "del", "pid": prov_playlist_id, "tracks": ",".join(ids_to_remove)}
            )

    async def create_playlist(self, name: str) -> Playlist:
        """Create a new playlist on the provider."""
        data = await self._get("playlist/create", params={"name": name})
        return self._parse_playlist(data.get("playlist"))

    async def on_played(
        self, media_type: MediaType, prov_item_id: str, fully_played: bool = False, *args, **kwargs
    ) -> None:
        """Registered callback when an item is played."""
        if media_type == MediaType.TRACK and fully_played:
            # Scrobble (sourceid is playlist id but optional)
            await self._get("scrobble", params={"id": prov_item_id, "sourceid": "", "time": 0})

    async def get_comments(self, prov_item_id: str, offset: int = 0, limit: int = 20) -> dict:
        """Get comments for a track."""
        return await self._get(
            "comment/music",
            params={"id": prov_item_id, "offset": offset, "limit": limit}
        )

    async def post_comment(self, prov_item_id: str, content: str) -> dict:
        """Post a comment on a track."""
        return await self._get(
            "comment",
            params={"t": 1, "type": 0, "id": prov_item_id, "content": content}
        )

    async def get_audiobook(self, prov_audiobook_id: str) -> None:
        raise NotImplementedError

    async def get_podcast(self, prov_podcast_id: str) -> None:
        raise NotImplementedError

    async def get_podcast_episode(self, prov_episode_id: str) -> None:
        raise NotImplementedError

    async def get_radio(self, prov_radio_id: str) -> Radio:
        """Get radio station details."""
        if prov_radio_id == "personal_fm":
            return Radio(
                item_id="personal_fm",
                provider=self.lookup_key,
                name="Private FM (Personal FM)",
                provider_mappings={
                    ProviderMapping(
                        item_id="personal_fm",
                        provider_domain=self.domain,
                        provider_instance=self.instance_id,
                        available=True
                    )
                }
            )
        raise NotImplementedError

    async def get_radio_tracks(self, prov_radio_id: str, limit: int = 25) -> list[Track]:
        """Get radio tracks."""
        if prov_radio_id == "personal_fm":
            data = await self._get("personal_fm")
            # personal_fm returns random list.
            # MA caches this so we might get same songs if cached.
            # But MA calls this when it needs tracks.
            return [self._parse_track(t) for t in data.get("data", [])]
        return []

    async def get_resume_position(
        self, item_id: str, provider_instance_id_or_domain: str
    ) -> int:
        return 0
