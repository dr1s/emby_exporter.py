#!/usr/bin/env python3

#   MIT License
#
#   Copyright (c) 2018 Daniel Schmitz
#
#   Permission is hereby granted, free of charge, to any person obtaining a copy
#   of this software and associated documentation files (the "Software"), to deal
#   in the Software without restriction, including without limitation the rights
#   to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
#   copies of the Software, and to permit persons to whom the Software is
#   furnished to do so, subject to the following conditions:
#
#   The above copyright notice and this permission notice shall be included in all
#   copies or substantial portions of the Software.
#
#   THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
#   IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
#   FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
#   AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
#   LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
#   OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
#   SOFTWARE.

import time
import warnings
import argparse
import threading
from embypy import Emby
from prometheus_client import Gauge, make_wsgi_app
from wsgiref.simple_server import WSGIRequestHandler, WSGIServer, make_server

__VERSION__ = '0.1.dev0'


class emby_exporter:

    def __init__(self, url, api_key, user_id):
        self.emby = Emby(   url,
                            api_key=api_key,
                            device_id='emby_exporter',
                            userid=user_id,
                            pass_uid=True)
        self.emby.update_sync()
        self.metrics = dict()
        self.info = None
        self.metrics['info'] = Gauge(   'emby_info',
                                        'emby info', [
                                            'server_name',
                                            'version',
                                            'local_address',
                                            'wan_address',
                                            'id',
                                            'operating_system'
                                        ])
        self.metrics['size'] = Gauge(   'emby_library_size',
                                        'emby library size',
                                        [ 'type' ])
        self.metrics['devices'] = Gauge('emby_devices', 'emby devices',[
            'name',
            'id',
            'username',
            'user_id',
            'app_name',
            'app_version'
        ])

        self.metrics['genres'] = Gauge('emby_genres', 'emby genres', [
            'type',
            'genre'
        ])

        self.httpd = None


    def parse_genres(self, data):
        genres = list()
        genres_stats = dict()
        for m in data:
            for g in m.genres:
                if not g in genres:
                    genres.append(g)
                    genres_stats[g] = 1
                else:
                    genres_stats[g] += 1

        print(genres_stats)
        return genres_stats


    def update_metrics(self):

        self.emby.update_sync()
        self.info = self.emby.info_sync()
        self.metrics['info'].labels(
            self.info['ServerName'],
            self.info['Version'],
            self.info['LocalAddress'],
            self.info['WanAddress'],
            self.info['Id'],
            self.info['OperatingSystem']).set(1)

        data = dict()
        data['movies']      = self.emby.movies_sync
        data['series']      = self.emby.series_sync
        data['episodes']    = self.emby.episodes_sync
        data['albums']      = self.emby.albums_sync
        data['artists']     = self.emby.artists_sync
        data['songs']       = self.emby.songs_sync

        devices   = self.emby.devices_sync
        for d in devices:
            self.metrics['devices'].labels(
                d.name,
                d.id,
                d.last_user_name,
                d.last_user_id,
                d.app_name,
                d.app_version
            ).set(1)
        for i in data:
            self.metrics['size'].labels(i).set(len(data[i]))

        genres = dict()
        for i in data:
            genres[i] = self.parse_genres(data[i])
        for t in genres:
            if isinstance(genres[t], dict):
                for g in genres[t]:
                    self.metrics['genres'].labels(t, g).set(genres[t][g])


    class _SilentHandler(WSGIRequestHandler):
        """WSGI handler that does not log requests."""

        def log_message(self, format, *args):
            """Log nothing."""


    def make_server(self, interface, port):
        server_class = WSGIServer

        if ':' in interface:
            if getattr(server_class, 'address_family') == socket.AF_INET:
                    server_class.address_family = socket.AF_INET6

        print("* Listening on %s:%s" % (interface, port))
        self.httpd = make_server(   interface,
                                    port,
                                    make_wsgi_app(),
                                    server_class,
                                    self._SilentHandler)
        t = threading.Thread(target=self.httpd.serve_forever)
        t.start()


def main():
    # Ignore warnings becasue of asyncio
    warnings.filterwarnings("ignore")

    parser = argparse.ArgumentParser(
        description='emby_exporter')
    parser.add_argument('-e', '--emby',
        help='emby adress',
        default='localhost:8096')
    parser.add_argument('-p', '--port',
        help='port emby_exporter is listening on',
        default=9123,
        type=int)
    parser.add_argument('-i', '--interface',
        help='interface emby_exporter will listen on',
        default='0.0.0.0')
    parser.add_argument('-a', '--auth',
        help='emby api token')
    parser.add_argument('-u', '--userid',
        help='emby user id')
    parser.add_argument('-s', '--interval',
        help='scraping interval in seconds',
        default=15,
        type=int)
    args = parser.parse_args()

    print('Connecting to emby: %s' % args.emby)
    emby_ex = emby_exporter('http://%s' % args.emby, args.auth, args.userid)
    print('Updating metrics...')
    emby_ex.update_metrics()
    emby_ex.make_server(args.interface, args.port)
    while True:
        time.sleep(args.interval)
        emby_ex.update_metrics()

if __name__ == '__main__':
    main()
