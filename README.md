# ySync

Lightweight CLI interface for registering and downloading youtube playlists.

 - Allows partial playlist downloads. The application picks up the download queue from where it was terminated.
 - Allows resolution setting per playlist.

Built on **python3** using [pytube](https://pypi.org/project/pytube/) 

## Install

```bash
git clone https://github.com/AtomicSpider/ySync.git
pip3 install -r requirements.txt
```

## Usage

**A) Running the application:**
Run the application by executing `run_app.bat`
or
```bash
python3 ySync.py
```
**B) Registering & Downloading playlists:**

Every time the download option is selected, the application also queries for newly added videos in the registered playlists and adds them to the download queue.

![enter image description here](https://s8.gifyu.com/images/ezgif.com-gif-maker-3ebf379f634a0bcb8.gif)

Press **Ctrl+C** during download to exit. On the next sync, the application will automatically pick up the download queue.
Playlist downloads can also be started by executing `sync_playlists.bat` directly.
