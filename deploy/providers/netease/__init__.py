"""Netease Cloud Music Provider for Music Assistant."""
from __future__ import annotations

from typing import TYPE_CHECKING

from music_assistant_models.config_entries import ConfigEntry, ConfigValueType
from music_assistant_models.enums import (
    ConfigEntryType,
    ContentType,
    MediaType,
    StreamType,
    ProviderFeature,
    ImageType
)
from music_assistant_models.errors import MediaNotFoundError, LoginFailed
from music_assistant_models.media_items import (
    Artist,
    Album,
    Track,
    Playlist,
    SearchResults,
    AudioFormat,
    ProviderMapping,
    ItemMapping,
    MediaItemImage,
)
from music_assistant_models.streamdetails import StreamDetails

# Based on local file structure analysis, this path appears correct for the cloned version.
from music_assistant.server.models.music_provider import MusicProvider

if TYPE_CHECKING:
    from music_assistant_models.config_entries import ProviderConfig
    from music_assistant_models.provider import ProviderManifest
    from music_assistant import MusicAssistant

CONF_API_URL = "api_url"
CONF_PHONE = "phone"
CONF_PASSWORD = "password"

class NeteaseProvider(MusicProvider):
    """Provider for Netease Cloud Music (via singo)."""

    _api_url: str = ""
    _user_id: str | None = None

    async def setup(self) -> None:
        """Initialize."""
        self._api_url = self.config.get_value(CONF_API_URL).rstrip("/")
        phone = self.config.get_value(CONF_PHONE)
        password = self.config.get_value(CONF_PASSWORD)

        if phone and password:
            await self._login(phone, password)

    async def _login(self, phone, password):
        """Login to Netease."""
        url = f"{self._api_url}/login/cellphone"
        async with self.mass.http_session.get(url, params={"phone": phone, "password": password}) as resp:
            if resp.status != 200:
                raise LoginFailed("Could not login to Netease API")
            data = await resp.json()
            if data.get("code") != 200:
                raise LoginFailed(data.get("msg", "Login failed"))

            if "account" in data and "id" in data["account"]:
                self._user_id = str(data["account"]["id"])

    def get_supported_features(self) -> set[ProviderFeature]:
        """Return features supported by this Provider."""
        return {
            ProviderFeature.SEARCH,
            ProviderFeature.BROWSE,
            ProviderFeature.LIBRARY_PLAYLISTS,
        }

    async def search(
        self, search_query: str, media_types=list[MediaType], limit: int = 5
    ) -> SearchResults:
        """Perform search on musicprovider."""
        result = SearchResults()

        if MediaType.TRACK in media_types:
            await self._search_and_parse(search_query, 1, result.tracks, self._parse_track, limit)

        if MediaType.ALBUM in media_types:
            await self._search_and_parse(search_query, 10, result.albums, self._parse_album, limit)

        if MediaType.ARTIST in media_types:
            await self._search_and_parse(search_query, 100, result.artists, self._parse_artist, limit)

        if MediaType.PLAYLIST in media_types:
            await self._search_and_parse(search_query, 1000, result.playlists, self._parse_playlist, limit)

        return result

    async def _search_and_parse(self, query, type_code, target_list, parser, limit):
        url = f"{self._api_url}/search"
        params = {"keywords": query, "type": type_code, "limit": limit}
        async with self.mass.http_session.get(url, params=params) as resp:
            data = await resp.json()
            if data.get("code") != 200:
                return

            res_data = data.get("result", {})
            items = []
            if type_code == 1: # songs
                items = res_data.get("songs", [])
            elif type_code == 10: # albums
                items = res_data.get("albums", [])
            elif type_code == 100: # artists
                items = res_data.get("artists", [])
            elif type_code == 1000: # playlists
                items = res_data.get("playlists", [])

            for item in items:
                try:
                    parsed = parser(item)
                    if parsed:
                        target_list.append(parsed)
                except Exception as e:
                    self.logger.warning("Error parsing item: %s", e)

    async def get_library_playlists(self) -> list[Playlist]:
        """Retrieve library playlists from the provider."""
        if not self._user_id:
            return []

        url = f"{self._api_url}/user/playlist"
        async with self.mass.http_session.get(url, params={"uid": self._user_id}) as resp:
            data = await resp.json()
            if data.get("code") != 200:
                return []

            playlists = []
            for item in data.get("playlist", []):
                try:
                    playlists.append(self._parse_playlist(item))
                except Exception:
                    pass
            return playlists

    async def get_playlist_tracks(self, prov_playlist_id: str) -> list[Track]:
        """Return playlist tracks for the given provider playlist id."""
        url = f"{self._api_url}/playlist/detail"
        async with self.mass.http_session.get(url, params={"id": prov_playlist_id}) as resp:
            data = await resp.json()
            if data.get("code") != 200 or "playlist" not in data:
                 return []

            tracks = []
            # 'tracks' field usually contains brief info, 'trackIds' contains all ids.
            # Depending on singo implementation, 'tracks' might be populated.
            # Singo calls Netease /playlist/detail which usually returns full details for first N tracks.
            # For this MVP, we parse what is available in 'tracks'.
            for item in data["playlist"].get("tracks", []):
                try:
                     tracks.append(self._parse_track(item))
                except Exception:
                     pass
            return tracks

    async def get_stream_details(self, item_id: str) -> StreamDetails:
        """Return the content details for the given track when it will be streamed."""
        url = f"{self._api_url}/song/url"
        async with self.mass.http_session.get(url, params={"id": item_id}) as resp:
            data = await resp.json()
            if data.get("code") != 200 or not data.get("data"):
                raise MediaNotFoundError(f"Song {item_id} not found")

            song_info = data["data"][0]
            stream_url = song_info.get("url")
            if not stream_url:
                 raise MediaNotFoundError(f"No stream URL for {item_id}")

            content_type = ContentType.MP3
            if stream_url.endswith(".flac"):
                content_type = ContentType.FLAC
            elif stream_url.endswith(".m4a"):
                content_type = ContentType.M4A

            return StreamDetails(
                provider=self.lookup_key,
                item_id=item_id,
                audio_format=AudioFormat(content_type=content_type),
                stream_type=StreamType.HTTP,
                path=stream_url
            )

    def _parse_track(self, data: dict) -> Track:
        track_id = str(data["id"])
        name = data["name"]
        track = Track(
            item_id=track_id,
            provider=self.lookup_key,
            name=name,
            provider_mappings={
                ProviderMapping(
                    item_id=track_id,
                    provider_domain=self.domain,
                    provider_instance=self.instance_id,
                )
            }
        )
        if "ar" in data: # standardized netease structure often uses 'ar' for artist, 'al' for album in lists
             for ar in data["ar"]:
                track.artists.append(self._get_item_mapping(MediaType.ARTIST, str(ar["id"]), ar["name"]))
        elif "artists" in data: # sometimes it's full word
            for ar in data["artists"]:
                track.artists.append(self._get_item_mapping(MediaType.ARTIST, str(ar["id"]), ar["name"]))

        if "al" in data:
            al = data["al"]
            track.album = self._get_item_mapping(MediaType.ALBUM, str(al["id"]), al["name"])
            if "picUrl" in al:
                track.metadata.images = [MediaItemImage(ImageType.THUMB, al["picUrl"], self.lookup_key, True)]
        elif "album" in data:
            al = data["album"]
            track.album = self._get_item_mapping(MediaType.ALBUM, str(al["id"]), al["name"])
            if "picUrl" in al:
                track.metadata.images = [MediaItemImage(ImageType.THUMB, al["picUrl"], self.lookup_key, True)]

        return track

    def _parse_album(self, data: dict) -> Album:
        item_id = str(data["id"])
        album = Album(
            item_id=item_id,
            provider=self.lookup_key,
            name=data["name"],
            provider_mappings={
                ProviderMapping(
                    item_id=item_id,
                    provider_domain=self.domain,
                    provider_instance=self.instance_id,
                )
            }
        )
        if "picUrl" in data:
            album.metadata.images = [MediaItemImage(ImageType.THUMB, data["picUrl"], self.lookup_key, True)]
        return album

    def _parse_artist(self, data: dict) -> Artist:
        item_id = str(data["id"])
        artist = Artist(
            item_id=item_id,
            provider=self.lookup_key,
            name=data["name"],
            provider_mappings={
                ProviderMapping(
                    item_id=item_id,
                    provider_domain=self.domain,
                    provider_instance=self.instance_id,
                )
            }
        )
        if "picUrl" in data:
             artist.metadata.images = [MediaItemImage(ImageType.THUMB, data["picUrl"], self.lookup_key, True)]
        elif "img1v1Url" in data:
             artist.metadata.images = [MediaItemImage(ImageType.THUMB, data["img1v1Url"], self.lookup_key, True)]
        return artist

    def _parse_playlist(self, data: dict) -> Playlist:
        item_id = str(data["id"])
        playlist = Playlist(
            item_id=item_id,
            provider=self.lookup_key,
            name=data["name"],
            owner=data.get("creator", {}).get("nickname", "Netease"),
            provider_mappings={
                ProviderMapping(
                    item_id=item_id,
                    provider_domain=self.domain,
                    provider_instance=self.instance_id,
                )
            },
            is_editable=False
        )
        if "coverImgUrl" in data:
            playlist.metadata.images = [MediaItemImage(ImageType.THUMB, data["coverImgUrl"], self.lookup_key, True)]
        return playlist

    def _get_item_mapping(self, media_type, key, name):
        return ItemMapping(
            media_type=media_type,
            item_id=key,
            provider=self.lookup_key,
            name=name
        )

async def get_config_entries(
    mass: MusicAssistant,
    instance_id: str | None = None,
    action: str | None = None,
    values: dict[str, ConfigValueType] | None = None,
) -> tuple[ConfigEntry, ...]:
    """Return Config entries to setup this provider."""
    return (
        ConfigEntry(
            key=CONF_API_URL,
            type=ConfigEntryType.STRING,
            label="Singo API URL",
            default_value="http://127.0.0.1:3333",
            required=True,
        ),
        ConfigEntry(
            key=CONF_PHONE,
            type=ConfigEntryType.STRING,
            label="Phone Number",
            required=False,
        ),
        ConfigEntry(
            key=CONF_PASSWORD,
            type=ConfigEntryType.SECURE_STRING,
            label="Password",
            required=False,
        ),
    )
