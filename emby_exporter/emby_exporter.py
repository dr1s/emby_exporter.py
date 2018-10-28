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
from prometheus_metrics import exporter
from embypy import Emby

class emby_exporter(exporter):
    def __init__(self, url, api_key, user_id, extended=False):
        super().__init__()
        self.emby = Emby(
            url,
            api_key=api_key,
            device_id='emby_exporter',
            userid=user_id,
            pass_uid=True)
        self.emby.update_sync()
        self.count_lists = ['Genres', 'ProductionYear']
        self.count_user_data = ['Played', 'IsFavorite']
        self.metrics_handler.add_metric_labels('emby_info', [
            'server_name', 'version', 'local_address', 'wan_address', 'id',
            'operating_system'
        ], description='information about the emby server')
        self.metrics_handler.add_metric_labels('emby_devices', [
            'name', 'id', 'last_user_name', 'last_user_id', 'app_name',
            'app_version'
        ])
        self.extended = extended

    def count_userdata(self, data, current_data={}):

        for item_type in data:
            for item in data[item_type]:
                for i in self.count_user_data:
                    if not i in current_data:
                        current_data[i] = dict()
                    if item.object_dict['UserData'][i]:
                        if not item_type in current_data[i]:
                            current_data[i][item_type] = 1
                        else:
                            current_data[i][item_type] += 1
        return current_data

    @classmethod
    def update_list(self, data, current_data={}):
        if isinstance(data, list):
            for i in data:
                if not i in current_data:
                    current_data[i] = 1
                else:
                    current_data[i] += 1
        else:
            if not data in current_data:
                current_data[data] = 1
            else:
                current_data[data] += 1
        return current_data

    def count_stats(self, data):
        stats = dict()

        for s in self.count_lists:
            stats[s] = dict()
        for item_type in data:
            for i in self.count_lists:
                if not item_type in stats[i]:
                    stats[i][item_type] = dict()
                for m in data[item_type]:
                    if i in m.object_dict:
                        content = m.object_dict[i]
                        stats[i][item_type] = self.update_list(
                            content, stats[i][item_type])
        return stats

    def update_stats(self, data):
        stats = dict()

        stats = self.count_stats(data)
        for t in stats:
            for i in self.count_lists:
                self.metrics_handler.add_update_metric_labels(
                    'emby_%s' % i.lower(), ['type', i.lower()], stats[i])

        user_data = self.count_userdata(data)
        for t in user_data:
            self.metrics_handler.add_update_metric_label(
                'emby_%s' % t.lower(), 'type', user_data[t])

    def update_info(self):
        info = self.emby.info_sync()
        info_data = [[
            info['ServerName'], info['Version'], info['LocalAddress'],
            info['WanAddress'], info['Id'], info['OperatingSystem'], 1
        ]]
        self.metrics_handler.update_metric('emby_info', info_data)

    def update_library(self):
        data = dict()
        data['movies'] = self.emby.movies_sync
        data['series'] = self.emby.series_sync
        data['albums'] = self.emby.albums_sync
        data['artists'] = self.emby.artists_sync

        if self.extended:
            data['episodes'] = self.emby.episodes_sync
            data['songs'] = self.emby.songs_sync

        size_tmp = dict()
        for i in data:
            size_tmp[i] = len(data[i])
        self.metrics_handler.add_update_metric_label('emby_library_size',
                                                     'type', size_tmp)
        self.update_stats(data)

    def update_devices(self):
        devices = self.emby.devices_sync
        device_data = list()
        for d in devices:
            device_data.append([
                d.name, d.id, d.last_user_name, d.last_user_id, d.app_name,
                d.app_version, 1
            ])
        self.metrics_handler.add_update_metric('emby_devices', device_data)

    def update_metrics(self):
        self.emby.update_sync()
        self.update_info()
        self.update_library()
        self.update_devices()

def main():
    # Ignore warnings becasue of asyncio
    warnings.filterwarnings("ignore")

    parser = argparse.ArgumentParser(description='emby_exporter')
    parser.add_argument(
        '-e', '--emby', help='emby adress', default='localhost:8096')
    parser.add_argument(
        '-p',
        '--port',
        help='port emby_exporter is listening on',
        default=9123,
        type=int)
    parser.add_argument(
        '-i',
        '--interface',
        help='interface emby_exporter will listen on',
        default='0.0.0.0')
    parser.add_argument('-a', '--auth', help='emby api token')
    parser.add_argument('-u', '--userid', help='emby user id')
    parser.add_argument(
        '-s',
        '--interval',
        help='scraping interval in seconds',
        default=15,
        type=int)
    parser.add_argument(
        '-x', '--extended', help='allow processing of episodes and song data')
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
