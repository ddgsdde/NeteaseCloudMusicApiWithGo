# Netease Cloud Music Provider for Music Assistant

This provider allows Music Assistant to play music from Netease Cloud Music (网易云音乐).

## Prerequisites

This provider relies on the [NeteaseCloudMusicApiWithGo](https://github.com/Singo/NeteaseCloudMusicApiWithGo) (or the original Node.js version) running as a service. You must have this API server running and accessible from your Music Assistant instance.

## Installation

1.  Copy the `mass_netease_provider` folder to the `music_assistant/providers` directory of your Music Assistant installation (or `custom_providers` if supported).
2.  Restart Music Assistant.
3.  Go to **Settings** -> **Music Providers**.
4.  Add **Netease Cloud Music**.
5.  Configure the **API Server URL** (e.g., `http://localhost:3333` or `http://192.168.1.x:3333`).
6.  (Optional) Enter your Phone/Email and Password to access your personal playlists.

## Features

*   **Search**: Search for songs and playlists.
*   **Library**: Access your personal Netease playlists.
*   **Playback**: Stream songs directly from Netease.

## Notes

*   This provider is a client for the Netease Cloud Music API. It does not contain the API logic itself.
*   Ensure the API server is reachable.
*   If you have login issues, try logging in on the API server directly or check the logs.
