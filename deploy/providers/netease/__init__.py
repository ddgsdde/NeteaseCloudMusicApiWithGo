"""Netease Cloud Music support for MusicAssistant."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any
from urllib.parse import urljoin

from music_assistant_models.config_entries import ConfigEntry, ConfigValueType
from music_assistant_models.enums import (
    ConfigEntryType,
    ProviderFeature,
    StreamType,
)
from music_assistant_models.errors import (
    LoginFailed,
    MediaNotFoundError,
)
from music_assistant_models.media_items import (
    Album,
    Artist,
    AudioFormat,
    ContentType,
    MediaItemImage,
    MediaType,
    Playlist,
    ProviderMapping,
    SearchResults,
    StreamDetails,
    Track,
    UniqueList,
    ImageType,
    RecommendationFolder,
)
from music_assistant.models.music_provider import MusicProvider

if TYPE_CHECKING:
    from music_assistant_models.config_entries import ProviderConfig
    from music_assistant_models.provider import ProviderManifest

    from music_assistant import MusicAssistant
    from music_assistant.models import ProviderInstanceType


CONF_BASE_URL = "base_url"
CONF_PHONE = "phone"
CONF_PASSWORD = "password"
CONF_EMAIL = "email"


async def setup(
    mass: MusicAssistant, manifest: ProviderManifest, config: ProviderConfig
) -> ProviderInstanceType:
    """Initialize provider(instance) with given configuration."""
    return NeteaseCloudMusicProvider(mass, manifest, config)


async def get_config_entries(
    mass: MusicAssistant,
    instance_id: str | None = None,
    action: str | None = None,
    values: dict[str, ConfigValueType] | None = None,
) -> tuple[ConfigEntry, ...]:
    """
    Return Config entries to setup this provider.
    """
    return (
        ConfigEntry(
            key=CONF_BASE_URL,
            type=ConfigEntryType.STRING,
            label="API Base URL",
            default_value="http://localhost:3333",
            required=True,
        ),
        # Login is handled via QR code flow in 'action' or just assumed logged in for now if using local API
        # But we can add Phone/Password if needed.
        # For this implementation we will rely on QR code auth logic which might need a specialized config flow
        # or we just point to the API which should be authenticated.
    )


class NeteaseCloudMusicProvider(MusicProvider):
    """Provider for Netease Cloud Music."""

    _base_url: str = ""

    async def handle_async_init(self) -> None:
        """Set up the Netease provider."""
        self._base_url = self.config.get_value(CONF_BASE_URL)
        # Verify connection
        try:
            await self._get_data("check/music", {"id": "33894312"}) # Just a check
        except Exception as err:
             self.logger.warning(f"Connection to Netease API failed: {err}")
             # We don't raise here to allow startup if API is temporarily down, or maybe we should?

        # We assume the API server handles auth state (cookies).
        # We should check login status.
        login_status = await self._get_data("login/status")
        if not login_status.get("data", {}).get("profile"):
             self.logger.warning("Netease API not logged in. Please login via the API server directly or implement QR flow.")

    @property
    def supported_features(self) -> set[ProviderFeature]:
        """Return the features supported by this Provider."""
        return {
            ProviderFeature.SEARCH,
            ProviderFeature.LIBRARY_ARTISTS,
            ProviderFeature.LIBRARY_ALBUMS,
            ProviderFeature.LIBRARY_TRACKS,
            ProviderFeature.LIBRARY_PLAYLISTS,
            ProviderFeature.BROWSE,
            ProviderFeature.RECOMMENDATIONS,
            ProviderFeature.ARTIST_ALBUMS,
            ProviderFeature.ARTIST_TOPTRACKS,
            ProviderFeature.SIMILAR_TRACKS,
            ProviderFeature.LYRICS,
        }

    async def search(
        self, search_query: str, media_types=list[MediaType], limit: int = 5
    ) -> SearchResults:
        """Perform search on musicprovider."""
        parsed_results = SearchResults()

        # Netease search type: 1: song, 10: album, 100: artist, 1000: playlist
        # 1014: video, 1009: radio station.

        if MediaType.TRACK in media_types:
             res = await self._get_data("search", {"keywords": search_query, "type": 1, "limit": limit})
             if res and "result" in res and "songs" in res["result"]:
                 for item in res["result"]["songs"]:
                     parsed_results.tracks.append(self._parse_track(item))

        if MediaType.ALBUM in media_types:
             res = await self._get_data("search", {"keywords": search_query, "type": 10, "limit": limit})
             if res and "result" in res and "albums" in res["result"]:
                 for item in res["result"]["albums"]:
                     parsed_results.albums.append(self._parse_album(item))

        if MediaType.ARTIST in media_types:
             res = await self._get_data("search", {"keywords": search_query, "type": 100, "limit": limit})
             if res and "result" in res and "artists" in res["result"]:
                 for item in res["result"]["artists"]:
                     parsed_results.artists.append(self._parse_artist(item))

        if MediaType.PLAYLIST in media_types:
             res = await self._get_data("search", {"keywords": search_query, "type": 1000, "limit": limit})
             if res and "result" in res and "playlists" in res["result"]:
                 for item in res["result"]["playlists"]:
                     parsed_results.playlists.append(self._parse_playlist(item))

        return parsed_results

    async def get_library_artists(self) -> Any:
        """Retrieve all library artists from Netease."""
        # /artist/sublist
        res = await self._get_data("artist/sublist")
        if res and "data" in res:
            for item in res["data"]:
                yield self._parse_artist(item)

    async def get_library_albums(self) -> Any:
        """Retrieve all library albums from Netease."""
        # /album/sublist
        res = await self._get_data("album/sublist")
        if res and "data" in res:
             for item in res["data"]:
                yield self._parse_album(item)

    async def get_library_playlists(self) -> Any:
        """Retrieve all library playlists from the provider."""
        # /user/playlist requires uid.
        # First get user profile
        status = await self._get_data("login/status")
        if not status or "data" not in status or "profile" not in status["data"] or not status["data"]["profile"]:
            return

        uid = status["data"]["profile"]["userId"]
        res = await self._get_data("user/playlist", {"uid": uid})
        if res and "playlist" in res:
             for item in res["playlist"]:
                 yield self._parse_playlist(item)

    async def get_library_tracks(self) -> Any:
        """Retrieve library tracks from Netease."""
        # Netease doesn't have a simple "all songs" library endpoint except "Cloud Disk" or the "ILike" playlist.
        # The user's "I Like" playlist usually contains their library tracks.
        status = await self._get_data("login/status")
        if not status or "data" not in status or "profile" not in status["data"] or not status["data"]["profile"]:
            return

        uid = status["data"]["profile"]["userId"]
        res = await self._get_data("user/playlist", {"uid": uid})
        if res and "playlist" in res:
             # usually the first playlist is the "I Like" playlist
             first_playlist = res["playlist"][0]
             playlist_id = first_playlist["id"]
             # Fetch tracks for this playlist
             tracks = await self.get_playlist_tracks(str(playlist_id))
             for track in tracks:
                 yield track

    async def get_album(self, prov_album_id) -> Album:
        """Get full album details by id."""
        res = await self._get_data("album", {"id": prov_album_id})
        if res and "album" in res:
            return self._parse_album(res["album"])
        raise MediaNotFoundError(f"Album {prov_album_id} not found")

    async def get_artist(self, prov_artist_id) -> Artist:
        """Get full artist details by id."""
        res = await self._get_data("artist/detail", {"id": prov_artist_id})
        if res and "data" in res and "artist" in res["data"]:
             return self._parse_artist(res["data"]["artist"])
        raise MediaNotFoundError(f"Artist {prov_artist_id} not found")

    async def get_track(self, prov_track_id) -> Track:
        """Get full track details by id."""
        res = await self._get_data("song/detail", {"ids": prov_track_id})
        if res and "songs" in res and len(res["songs"]) > 0:
            return self._parse_track(res["songs"][0])
        raise MediaNotFoundError(f"Track {prov_track_id} not found")

    async def get_playlist(self, prov_playlist_id) -> Playlist:
        """Get full playlist details by id."""
        res = await self._get_data("playlist/detail", {"id": prov_playlist_id})
        if res and "playlist" in res:
             return self._parse_playlist(res["playlist"])
        raise MediaNotFoundError(f"Playlist {prov_playlist_id} not found")

    async def get_album_tracks(self, prov_album_id: str) -> list[Track]:
        """Get album tracks for given album id."""
        res = await self._get_data("album", {"id": prov_album_id})
        tracks = []
        if res and "songs" in res:
            for item in res["songs"]:
                tracks.append(self._parse_track(item))
        return tracks

    async def get_playlist_tracks(self, prov_playlist_id: str) -> list[Track]:
        """Return playlist tracks for the given provider playlist id."""
        res = await self._get_data("playlist/track/all", {"id": prov_playlist_id}) # limit default to all? or need limit=1000
        tracks = []
        if res and "songs" in res:
             for item in res["songs"]:
                 tracks.append(self._parse_track(item))
        return tracks

    async def get_artist_albums(self, prov_artist_id) -> list[Album]:
        """Get a list of albums for the given artist."""
        res = await self._get_data("artist/album", {"id": prov_artist_id})
        albums = []
        if res and "hotAlbums" in res:
            for item in res["hotAlbums"]:
                albums.append(self._parse_album(item))
        return albums

    async def get_artist_toptracks(self, prov_artist_id) -> list[Track]:
        """Get a list of 25 most popular tracks for the given artist."""
        res = await self._get_data("artist/top/song", {"id": prov_artist_id})
        tracks = []
        if res and "songs" in res:
            for item in res["songs"][:25]:
                tracks.append(self._parse_track(item))
        return tracks

    async def get_similar_tracks(self, prov_track_id, limit=25) -> list[Track]:
        """Retrieve a dynamic list of tracks based on the provided item."""
        res = await self._get_data("simi/song", {"id": prov_track_id})
        tracks = []
        if res and "songs" in res:
             for item in res["songs"]:
                 tracks.append(self._parse_track(item))
        return tracks[:limit]

    async def recommendations(self) -> list[RecommendationFolder]:
        """Get available recommendations."""
        from music_assistant_models.media_items import RecommendationFolder
        folders = []

        # Daily Songs
        res = await self._get_data("recommend/songs")
        if res and "data" in res and "dailySongs" in res["data"]:
             daily_songs = []
             for item in res["data"]["dailySongs"]:
                 daily_songs.append(self._parse_track(item))

             if daily_songs:
                 folders.append(RecommendationFolder(
                     item_id="daily_songs",
                     provider=self.lookup_key,
                     name="Daily Recommend Songs",
                     items=daily_songs,
                     icon="calendar"
                 ))

        # Daily Playlists
        res = await self._get_data("recommend/resource")
        if res and "recommend" in res:
             daily_playlists = []
             for item in res["recommend"]:
                 daily_playlists.append(self._parse_playlist(item))

             if daily_playlists:
                 folders.append(RecommendationFolder(
                     item_id="daily_playlists",
                     provider=self.lookup_key,
                     name="Daily Recommend Playlists",
                     items=daily_playlists,
                     icon="playlist-music"
                 ))

        return folders

    async def library_add(self, item: Any) -> bool:
        """Add an item to the library."""
        # For Songs: like?id=xxx&like=true
        # For Playlists: playlist/subscribe?t=1&id=xxx
        if item.media_type == MediaType.TRACK:
             res = await self._get_data("like", {"id": item.item_id, "like": "true"})
             return res and res.get("code") == 200
        if item.media_type == MediaType.PLAYLIST:
             res = await self._get_data("playlist/subscribe", {"id": item.item_id, "t": 1})
             return res and res.get("code") == 200
        return False

    async def library_remove(self, prov_item_id, media_type: MediaType):
        """Remove an item from the library."""
        if media_type == MediaType.TRACK:
             res = await self._get_data("like", {"id": prov_item_id, "like": "false"})
             return res and res.get("code") == 200
        if media_type == MediaType.PLAYLIST:
             res = await self._get_data("playlist/subscribe", {"id": prov_item_id, "t": 2})
             return res and res.get("code") == 200
        return False

    async def on_played(self, media_item: Any) -> None:
        """Handle media item played."""
        # Scrobble (scrobble endpoint: id, sourceid, time)
        # Netease scrobble: /scrobble?id=xxx&sourceid=xxx&time=xxx
        if media_item.media_type == MediaType.TRACK:
            try:
                # We assume the song was fully played or at least significantly.
                # sourceid is playlist id, but optional.
                await self._get_data("scrobble", {
                    "id": media_item.item_id,
                    "sourceid": "0",
                    "time": str(int(media_item.duration)) if media_item.duration else "180"
                })
            except Exception as err:
                self.logger.warning(f"Failed to scrobble track {media_item.name}: {err}")

    async def get_track_lyrics(self, prov_track_id: str) -> Any:
        """Get track lyrics."""
        res = await self._get_data("lyric", {"id": prov_track_id})
        if not res:
            return None

        lyrics = ""
        if "lrc" in res and "lyric" in res["lrc"]:
            lyrics = res["lrc"]["lyric"]

        return lyrics

    async def get_stream_details(self, item_id: str) -> StreamDetails:
        """Return the content details for the given track when it will be streamed."""
        # Get song url
        # song/url/v1 seems not available in Go API yet, fallback to song/url
        # level: standard, higher, exhigh, lossless, hires
        res = await self._get_data("song/url", {"id": item_id})
        if not res or "data" not in res or not res["data"]:
             raise MediaNotFoundError(f"Stream URL for {item_id} not found")

        data = res["data"][0]
        url = data.get("url")
        if not url:
             raise MediaNotFoundError(f"Stream URL for {item_id} is empty (Copyright or VIP restricted?)")

        return StreamDetails(
            provider=self.lookup_key,
            item_id=item_id,
            audio_format=AudioFormat(
                content_type=ContentType.try_parse(data.get("type", "mp3")),
            ),
            stream_type=StreamType.HTTP,
            path=url,
            can_seek=True,
        )

    async def _get_data(self, endpoint: str, params: dict | None = None) -> dict:
        """Get data from the API."""
        url = urljoin(self._base_url, endpoint)
        async with self.mass.http_session.get(url, params=params) as response:
            return await response.json()

    def _parse_track(self, item: dict) -> Track:
        """Parse Netease track."""
        track_id = str(item["id"])
        name = item["name"]

        album = None
        if "al" in item and item["al"]:
            album = self._get_item_mapping(MediaType.ALBUM, str(item["al"]["id"]), item["al"]["name"])
        elif "album" in item and item["album"]:
             album = self._get_item_mapping(MediaType.ALBUM, str(item["album"]["id"]), item["album"]["name"])

        artists = []
        ar_list = item.get("ar") or item.get("artists") or []
        for ar in ar_list:
            artists.append(self._get_item_mapping(MediaType.ARTIST, str(ar["id"]), ar["name"]))

        track = Track(
            item_id=track_id,
            provider=self.lookup_key,
            name=name,
            provider_mappings={
                ProviderMapping(
                    item_id=track_id,
                    provider_domain=self.domain,
                    provider_instance=self.instance_id,
                    available=True,
                )
            },
            album=album,
            artists=UniqueList(artists),
        )

        # Duration
        dt = item.get("dt") or item.get("duration")
        if dt:
            track.duration = int(dt) / 1000

        # Images
        img_url = None
        if "al" in item and "picUrl" in item["al"]:
             img_url = item["al"]["picUrl"]
        elif "album" in item and "picUrl" in item["album"]:
             img_url = item["album"]["picUrl"]

        if img_url:
             track.metadata.images = UniqueList([MediaItemImage(ImageType.THUMB, img_url, self.lookup_key, True)])

        return track

    def _parse_album(self, item: dict) -> Album:
        album_id = str(item["id"])
        name = item["name"]

        album = Album(
            item_id=album_id,
            provider=self.lookup_key,
            name=name,
            provider_mappings={
                ProviderMapping(
                    item_id=album_id,
                    provider_domain=self.domain,
                    provider_instance=self.instance_id,
                )
            }
        )
        if "picUrl" in item:
             album.metadata.images = UniqueList([MediaItemImage(ImageType.THUMB, item["picUrl"], self.lookup_key, True)])

        artists = []
        ar_list = item.get("artists") or []
        for ar in ar_list:
             artists.append(self._get_item_mapping(MediaType.ARTIST, str(ar["id"]), ar["name"]))
        album.artists = UniqueList(artists)

        return album

    def _parse_artist(self, item: dict) -> Artist:
        artist_id = str(item["id"])
        name = item["name"]

        artist = Artist(
            item_id=artist_id,
            provider=self.lookup_key,
            name=name,
            provider_mappings={
                ProviderMapping(
                    item_id=artist_id,
                    provider_domain=self.domain,
                    provider_instance=self.instance_id,
                )
            }
        )

        if "picUrl" in item:
             artist.metadata.images = UniqueList([MediaItemImage(ImageType.THUMB, item["picUrl"], self.lookup_key, True)])
        elif "img1v1Url" in item:
             artist.metadata.images = UniqueList([MediaItemImage(ImageType.THUMB, item["img1v1Url"], self.lookup_key, True)])

        return artist

    def _parse_playlist(self, item: dict) -> Playlist:
        playlist_id = str(item["id"])
        name = item["name"]

        playlist = Playlist(
            item_id=playlist_id,
            provider=self.lookup_key,
            name=name,
            provider_mappings={
                ProviderMapping(
                    item_id=playlist_id,
                    provider_domain=self.domain,
                    provider_instance=self.instance_id,
                )
            },
            is_editable=True # Assume editable if owned?
        )

        if "coverImgUrl" in item:
             playlist.metadata.images = UniqueList([MediaItemImage(ImageType.THUMB, item["coverImgUrl"], self.lookup_key, True)])

        if "creator" in item:
             playlist.owner = item["creator"]["nickname"]

        return playlist

    def _get_item_mapping(self, media_type: MediaType, key: str, name: str) -> Any:
        from music_assistant_models.media_items import ItemMapping
        return ItemMapping(
            media_type=media_type,
            item_id=key,
            provider=self.lookup_key,
            name=name,
        )
