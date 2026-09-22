# ScrapeMaster 2000

Paste a web address, see every image on the page, and download the ones you want as full-size originals.

## Using the app (no Python needed)

**Windows:** double-click `ScrapeMaster2000.exe`.
**Mac / Linux:** unzip, then double-click `ScrapeMaster2000`.

A small black window opens and your browser shows ScrapeMaster 2000. Keep the small window open while you use it. Closing it quits the app.

### First-launch warnings (normal for free, unsigned apps)
- **Windows** may say *"Windows protected your PC"*. Click **More info → Run anyway**.
  Some antivirus tools also flag apps packaged this way by mistake. If yours does, you can allow the file.
- **Mac** may say the app *"cannot be opened because the developer cannot be verified"*.
  Right-click the file → **Open** → **Open**, or go to **System Settings → Privacy & Security → Open Anyway**.

## Building the app yourself

An app has to be built on the same kind of computer it will run on: a Windows computer for Windows, a Mac for Mac.

**Windows:** install [Python](https://www.python.org/downloads/) (tick *"Add python.exe to PATH"*), then double-click `build_windows.bat`.
The app appears in the `dist` folder as `ScrapeMaster2000.exe`.

**Mac / Linux:** install Python 3, then in Terminal run `bash build_mac_linux.sh`.
The app appears in `dist/ScrapeMaster2000`. A Mac build only runs on the same chip type (Apple Silicon or Intel) as the Mac that built it.

### Build every version automatically (optional)
If you put this folder in a GitHub repository, the included `.github/workflows/build.yml` builds the Windows, Mac and Linux versions on GitHub's computers, for free:
- **Actions** tab → *Build ScrapeMaster 2000* → **Run workflow**. The apps appear under that run's *Artifacts*.
- Or push a version tag (e.g. `git tag v1.0 && git push --tags`). The apps are then attached to a **Release** page you can share as one download link.

## Running from source

```
python scrapemaster2000.py
```

`scrapemaster2000.html` must stay in the same folder.

## Files

| File | What it is |
|---|---|
| `scrapemaster2000.html` | The interface |
| `scrapemaster2000.py` | Local helper that fetches pages and images for the interface |
| `scrapemaster2000.spec` | Packaging recipe used by the build scripts |
| `build_windows.bat`, `build_mac_linux.sh` | One-click builders |
| `assets/` | App icon |
