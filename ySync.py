import argparse
import logging
import traceback
from pathlib import Path
import sqlite3
from sqlite3 import Error
from pytube import Playlist, YouTube
import pandas as pd
import urllib.parse as urlparse
from urllib.parse import parse_qs
import unicodedata
import re
from tqdm import tqdm
import sys

from assets.assets import *

logging.basicConfig(filename="app.log",
                    format="%(asctime)s: %(message)s", level=logging.INFO)
_db_path = Path('config/database.db')

available_res = ['720p', '480p', '360p', '240p', '144p']


def slugify(value, allow_unicode=False):
    value = str(value)
    if allow_unicode:
        value = unicodedata.normalize('NFKC', value)
    else:
        value = unicodedata.normalize('NFKD', value).encode(
            'ascii', 'ignore').decode('ascii')
    value = re.sub(r'[^\w\s-]', '', value.lower())
    return re.sub(r'[-\s]+', '-', value).strip('-_')


def init():
    conn = None
    try:
        Path('config').mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(_db_path))
        c = conn.cursor()
        c.execute(
            '''CREATE TABLE IF NOT EXISTS playlists(uuid TEXT PRIMARY KEY NOT NULL, alias TEXT NOT NULL, url TEXT NOT NULL, res INT NOT NULL, created_at Timestamp DEFAULT CURRENT_TIMESTAMP)''')
        c.execute('''CREATE TABLE IF NOT EXISTS videos(uuid TEXT PRIMARY KEY NOT NULL, pl_alias TEXT NOT NULL, res INT NOT NULL, status INTEGER NOT NULL DEFAULT 0, created_at Timestamp DEFAULT CURRENT_TIMESTAMP)''')
        conn.commit()
    except Error as e:
        raise Exception(e)
    finally:
        if conn:
            conn.close()


def get_playlists():
    conn = None
    try:
        conn = sqlite3.connect(str(_db_path))
        pls = pd.read_sql_query(
            "SELECT alias as Playlist_Name, uuid as Playlist_ID, res as Download_Quality FROM playlists", conn)
        if pls.empty:
            print('\n_> You are not subscribed to any playlists yet.')
        else:
            pls['Download_Quality'] = pls['Download_Quality'].apply(
                lambda x: available_res[x])
            print('\n_> Your subscribed playlists:\n')
            print(pls)
        # ToDo print full
    except Error as e:
        raise Exception(e)
    finally:
        if conn:
            conn.close()


def add_playlist():
    url = input("\n_> Please enter playlist url: ").strip()

    try:
        p = Playlist(url)
        _title = p.title
        if _title == 'null':
            raise Exception('Private Playlist')
        _pid = p.playlist_id
        _purl = p.playlist_url
    except Exception:
        raise Exception(
            '[ERROR]: Could not fecth playlist. This can happen due to invalid url or playlist being private')

    try:
        _dres = int(input(
            "\n_> Please select download resolution:\n1) 720p\n2) 480p\n3) 360p\n4) 240p\n5) 144p\n").strip())
        if _dres > 0 and _dres < 6:
            _dres -= 1
        else:
            raise Exception('Invalid Input')
    except Exception:
        print('_> Invalid selection. Taking default "480p"')
        _dres = 1

    conn = None
    try:
        conn = sqlite3.connect(str(_db_path))
        c = conn.cursor()
        c.execute("INSERT or IGNORE INTO playlists(uuid, alias, url, res) VALUES ('{}','{}','{}',{})".format(
            _pid, _title, _purl, _dres))
        conn.commit()

        print('\n_> Playlist "{}" registered successfully !!!'.format(_title))
    except Error as e:
        raise Exception(e)
    finally:
        if conn:
            conn.close()


def get_stream(yt, res):
    s = yt.streams.filter(file_extension='mp4', res=available_res[res]).first()
    if s is None:
        if res == len(available_res) - 1:
            return None
        else:
            return get_stream(yt, available_res[res + 1])
    else:
        return s


class TqdmUpdate(tqdm):
    def update_to(self, blocks_so_far=1, block_size=1, total=None):
        self.update(blocks_so_far * block_size - self.n)


def sync_playlists():
    conn = None
    try:
        conn = sqlite3.connect(str(_db_path))
        c = conn.cursor()
        c.execute("SELECT uuid, alias, url, res FROM playlists")
        pls = c.fetchall()

        if len(pls) == 0:
            raise Exception(
                '[ERROR]: You are not subscribed to any playlists yet.')

        pls_obj = list()
        for pl in pls:
            try:
                pl_obj = Playlist(pl[2])
                if pl_obj.title == 'null':
                    raise Exception('Private Playlist')
                pls_obj.append((pl_obj, pl[3]))
            except Exception:
                print('\n[ERROR]: Could not conncet to playlist {}'.format(pl[1]))

        if len(pls_obj) == 0:
            raise Exception(
                '[ERROR]: Could not connect to any valid playlists')

        videos = list()
        print('')
        for pl_obj, _res in pls_obj:
            pl_obj_title_slug = slugify(pl_obj.title)

            p_dir = Path('downloads/{}'.format(pl_obj_title_slug))
            p_dir.mkdir(parents=True, exist_ok=True)

            print('_> Refreshing "{}" ...'.format(pl_obj.title))

            video_urls = pl_obj.video_urls
            videos.extend([(parse_qs(urlparse.urlparse(e).query)[
                          'v'][0], pl_obj_title_slug, _res) for e in video_urls])

        print('_> Updateing sync database ...')
        for video in videos:
            c.execute(
                "INSERT OR IGNORE INTO videos(uuid, pl_alias, res) VALUES('{}','{}',{})".format(video[0], video[1], _res))
        conn.commit()

        c.execute("SELECT uuid, pl_alias, res FROM videos where status=0")
        down_vids = c.fetchall()

        _num_vids = len(down_vids)
        print('\n_> Downloading {} videos ...'.format(_num_vids))

        print('')
        try:
            for i, down_vid in enumerate(down_vids):
                try:
                    yt = YouTube(
                        'https://www.youtube.com/watch?v={}'.format(down_vid[0]))
                    _title = yt.title
                    if _title == 'null':
                        raise Exception('Private Video')
                except Exception as e:
                    logging.error(e)
                    print('_> [ERROR]: Could not parse video with ID: {}. Video is private or not available.'.format(
                        down_vid[0]))
                    c.execute(
                        "UPDATE videos SET status=2 WHERE uuid='{}'".format(down_vid[0]))
                    conn.commit()
                    continue

                try:
                    print('_> Downloading "{}" to folder "{}"...'.format(
                        _title, down_vid[1]))

                    with TqdmUpdate(unit=' %', miniters=1, total=100, leave=False, desc='   Progress: {}/{} videos'.format(i + 1, _num_vids)) as t:
                        yt.register_on_progress_callback(lambda s, c, b: t.update_to(
                            blocks_so_far=int((s.filesize - b) * 100 / s.filesize), total=100))
                        s = get_stream(yt, down_vid[2])
                        if s is None:
                            raise Exception('No streams available')
                        s.download('downloads/{}'.format(down_vid[1]))
                        c.execute(
                            "UPDATE videos SET status=1 WHERE uuid='{}'".format(down_vid[0]))
                        conn.commit()
                except Exception as e:
                    logging.error(e)
                    print('_> [FAILED]')
                    c.execute(
                        "UPDATE videos SET status=2 WHERE uuid='{}'".format(down_vid[0]))
                    conn.commit()
        except KeyboardInterrupt:
            print('_> [EXIT]')
            sys.exit(0)

    except Exception as e:
        raise Exception(e)
    finally:
        if conn:
            conn.close()


def get_args():
    parser = argparse.ArgumentParser()
    parser.add_argument('-t', '--task', type=str, choices=['main', 'download'],
                        default='main', help='Task to perform ("main" or "download")',
                        metavar='Task')
    args = parser.parse_args()
    return args


def show_main():
    print('\n_> What would you like to do?\n')
    print('1) Show subscribed playlists')
    print('2) Subscribe to a new playlist')
    print('3) Sync subscribed playlists')
    print('e) Exit')

    task = input("\nInput: ").lower()

    if task == '1':
        try:
            get_playlists()
        except Exception as e:
            print('\n', e)
        show_main()
    elif task == '2':
        try:
            add_playlist()
        except Exception as e:
            print('\n', e)
        show_main()
    elif task == '3':
        try:
            sync_playlists()
        except Exception as e:
            print('\n', e)
        show_main()
    elif task == 'e':
        pass
    else:
        print('[ERROR]: Invalid input')
        show_main()


if __name__ == '__main__':
    try:
        print(welcome_text)
        init()
        args = get_args()
        if args.task == 'main':
            show_main()
        else:
            sync_playlists()
    except Exception as e:
        print('[ERROR]: {}, See app.log for details'.format(e))
        logging.error(traceback.format_exc())
