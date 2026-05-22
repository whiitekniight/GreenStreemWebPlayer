# GreenStreem Web Player

Standalone web-player prototype for `greenstreemlabs.com/player`.

This project is intentionally separate from the Android TV app in `GreenStreem`.
It starts as a static browser app so the layout and flow can be shaped before a
backend is added.

## Current Build

- GreenStreem branded login screen
- Xtream and M3U login modes
- Main menu for Live Channels, Movies, TV Series, and Account Info
- Live player layout with preview video, channel list, category drawer, search,
  and favorites
- Local M3U parser for simple browser-loadable playlists
- Demo channel data for layout testing

## Open Locally

Open `index.html` in a browser.

## Next Backend Pass

The real hosted player should add a backend service before public use:

- Store IPTV credentials server-side, not in frontend JavaScript
- Proxy playlist, EPG, logo, and stream requests when browser CORS blocks them
- Normalize Xtream live URLs to browser-friendly HLS/M3U8 when available
- Add short-lived sessions for users
- Add HTTPS deployment under `greenstreemlabs.com/player`

## Notes

Browsers can usually play HLS streams more reliably than raw transport streams.
Some IPTV streams will need backend proxying or transmuxing before playback works
well in Chrome, Brave, Edge, or Safari.
