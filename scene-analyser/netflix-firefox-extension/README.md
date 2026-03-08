# Netflix Firefox Extension POC

This Firefox extension passively captures Netflix BIF thumbnail files and TTML subtitle XML files from the live network stream on Netflix watch pages.

## Load In Firefox

1. Open `about:debugging#/runtime/this-firefox`.
2. Click `Load Temporary Add-on...`.
3. Select [`manifest.json`](/Users/evren/code/r2t4/scene-analyser/netflix-firefox-extension/manifest.json).

## Behavior

- The toolbar button toggles capture for the active Netflix tab.
- Once enabled, capture stays on for that tab until you click the toolbar button again.
- On first enable, Firefox prompts for Netflix/CDN host permissions.
- Captures are saved to `Netflix_Captures/<title-slug>/`.
- A manifest JSON file is rewritten as new unique assets are captured.
- Each title folder also gets a `<title-slug>__debug.json` file, and a global request log is written to `Netflix_Captures/_debug/netflix_capture__global_debug.json`.

## Verify

```bash
node --test tests/*.test.js
```
