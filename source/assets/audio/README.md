# Audio Assets

Drop your game audio files into this folder before running the web build scripts.

Expected filenames:
- gun.ogg: fired when a plane shoots
- crash.ogg: played when a plane crashes into terrain, the roof, lightning, or another plane
- hit.ogg: played when a bullet hits a plane
- engine.ogg: looped independently for each plane while its thrust is above 0%
- menu.ogg: looped on the player-name entry screen and the top-scores screen
- theme.ogg: looping background music

Notes:
- Keep filenames lowercase.
- OGG is recommended for browser compatibility and smaller download size.
- The game will also work without these files; missing files fail silently.
- The web build scripts copy this folder into the Pygbag app bundle as `audio/` beside `main.py`.
