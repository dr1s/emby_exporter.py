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

__VERSION__ = '0.1.2'


class metric:
    def __init__(self, name, value):
        self.name = name
        self.value = value
        self.metric = Gauge('%s' % name.lower(), name.replace('_', ' '))
        self.metric.set(value)

    def update_value(self, value):
        self.value = value
        self.metric.set(value)


class metric_label:
    def __init__(self, name, value, label=None):
        self.name = name
        if not label:
            label = [*value.keys()][0]
        self.values = dict()
        self.label_values = list()
        self.label_values.append(label)
        self.metric = Gauge('%s' % name.lower(), name.replace('_', ' '),
                            [label])
        self.update_value(value)

    def update_value(self, value):
        for label in value:
            self.values[label] = value[label]
            self.metric.labels(label).set(value[label])
            if label not in self.label_values:
                self.label_values.append(label)
        for label in self.label_values:
            if not label in value:
                self.metric.labels(label).set(0)


class metric_labels:
    def __init__(self, name, labels, values):
        self.name = name
        self.values = dict()
        self.labels = labels
        self.metric = Gauge('%s' % name.lower(), name.replace('_', ' '),
                            labels)
        self.update_value(values)

    def zero_missing_value(self, values, key):
        if isinstance(values, dict):
            for label in values:
                values[label] = self.zero_missing_value(values[label], label)
        else:
            values = 0
        return values

    def update_old_values(self, old_values, values):

        for label in old_values:
            if not label in values:
                old_values[label] = self.zero_missing_value(
                    old_values[label], label)
            else:
                if isinstance(old_values[label], dict):
                    old_values[label] = self.update_old_values(
                        old_values[label], values[label])
        return old_values

    def add_new_values(self, old_values, values):

        for label in values:
            if not isinstance(values[label], dict):
                old_values[label] = values[label]
            else:
                if label in old_values:
                    old_values[label] = self.add_new_values(
                        old_values[label], values[label])
                else:
                    old_values[label] = values[label]

        return old_values

    def update_metrics(self, values, labels=[]):

        for label in values:
            labels_tmp = list()
            for i in labels:
                labels_tmp.append(i)
            labels_tmp.append(label)

            if not isinstance(values[label], dict):
                self.metric.labels(*labels_tmp).set(values[label])
                labels_tmp.pop()
            else:
                self.update_metrics(values[label], labels_tmp)

    def __add_value_dict(self, d, items, value):
        if len(items) > 1:
            if not items[0] in d:
                d[items[0]] = dict()
            current = items[0]
            items.pop(0)
            d[current] = self.__add_value_dict(d[current], items, value)
        else:
            d[items[0]] = value
        return d

    def update_value(self, values):
        values_tmp = self.values
        if isinstance(values, list):
            values_new = dict()
            for v in values:
                v_temp = v[:len(v) - 1]
                metric_value = v[len(v) - 1]
                values_new = self.__add_value_dict(values_new, v_temp,
                                                   metric_value)
                values = values_new
        values_tmp = self.add_new_values(values_tmp, values)
        values_tmp = self.update_old_values(values_tmp, values)

        self.update_metrics(values_tmp)


class emby_exporter:
    def __init__(self, url, api_key, user_id):
        self.emby = Emby(
            url,
            api_key=api_key,
            device_id='emby_exporter',
            userid=user_id,
            pass_uid=True)
        self.emby.update_sync()
        self.metrics = dict()
        self.info = None
        self.count_lists = ['Genres', 'ProductionYear']
        self.count_user_data = ['Played', 'IsFavorite']
        self.metrics['info'] = Gauge('emby_info', 'emby info', [
            'server_name', 'version', 'local_address', 'wan_address', 'id',
            'operating_system'
        ])

        self.httpd = None

    def add_update_metric(self, name, value):
        if not name in self.metrics:
            self.metrics[name] = metric(name, value)
        self.metrics[name].update_value(value)

    def add_update_metric_label(self, name, value, label=None):
        if not name in self.metrics:
            self.metrics[name] = metric_label(name, value, label)
        self.metrics[name].update_value(value)

    def add_update_metric_labels(self, name, labels, value):
        if not name in self.metrics:
            self.metrics[name] = metric_labels(name, labels, value)
        self.metrics[name].update_value(value)

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
                self.metrics[i] = self.add_update_metric_labels(
                    'emby_%s' % i.lower(), ['type', i.lower()], stats[i])

        user_data = self.count_userdata(data)
        for t in user_data:
            self.metrics[i] = self.add_update_metric_label(
                'emby_%s' % t.lower(), user_data[t], 'type')

        for t in stats:
            for i in stats[t]:
                if i == 'user_data':
                    if 'played' in stats[t]['user_data']:
                        self.metrics['played'].labels(t).set(
                            stats[t]['user_data']['played'])
                    if 'isfavourite' in stats[t]['user_data']:
                        self.metrics['favourite'].labels(t).set(
                            stats[t]['user_data']['isfavourite'])

    def update_metrics(self):

        self.emby.update_sync()
        self.info = self.emby.info_sync()
        self.metrics['info'].labels(
            self.info['ServerName'], self.info['Version'],
            self.info['LocalAddress'], self.info['WanAddress'],
            self.info['Id'], self.info['OperatingSystem']).set(1)

        data = dict()
        data['movies'] = self.emby.movies_sync
        data['series'] = self.emby.series_sync
        data['albums'] = self.emby.albums_sync
        data['artists'] = self.emby.artists_sync
        #data['episodes']    = self.emby.episodes_sync
        #data['songs']       = self.emby.songs_sync

        devices = self.emby.devices_sync
        device_data = list()
        for d in devices:
            device_data.append([
                d.name, d.id, d.last_user_name, d.last_user_id, d.app_name,
                d.app_version, 1
            ])
        self.add_update_metric_labels('devices', [
            'name', 'id', 'last_user_name', 'last_user_id', 'app_name',
            'app_version'
        ], device_data)

        size_tmp = dict()
        for i in data:
            size_tmp[i] = len(data[i])
        if not 'size' in self.metrics:
            self.metrics['size'] = metric_label('emby_library_size', size_tmp,
                                                'type')
        self.metrics['size'].update_value(size_tmp)

        self.update_stats(data)

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
        self.httpd = make_server(interface, port, make_wsgi_app(),
                                 server_class, self._SilentHandler)
        t = threading.Thread(target=self.httpd.serve_forever)
        t.start()


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
