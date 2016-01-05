# coding=utf-8
# Author: Idan Gutman
# URL: http://code.google.com/p/sickbeard/
#
# This file is part of SickRage.
#
# SickRage is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# SickRage is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with SickRage.  If not, see <http://www.gnu.org/licenses/>.

import re
import urllib
import traceback

from sickbeard import logger
from sickbeard import tvcache
from sickbeard.bs4_parser import BS4Parser
from sickrage.providers.torrent.TorrentProvider import TorrentProvider

from sickrage.helper.common import try_int


class SceneTimeProvider(TorrentProvider):

    def __init__(self):

        TorrentProvider.__init__(self, "SceneTime")

        self.username = None
        self.password = None
        self.ratio = None
        self.minseed = None
        self.minleech = None

        self.cache = SceneTimeCache(self)

        self.urls = {'base_url': 'https://www.scenetime.com',
                     'login': 'https://www.scenetime.com/takelogin.php',
                     'detail': 'https://www.scenetime.com/details.php?id=%s',
                     'search': 'https://www.scenetime.com/browse.php?search=%s%s',
                     'download': 'https://www.scenetime.com/download.php/%s/%s'}

        self.url = self.urls['base_url']

        self.categories = "&c2=1&c43=13&c9=1&c63=1&c77=1&c79=1&c100=1&c101=1"

    def login(self):

        login_params = {'username': self.username,
                        'password': self.password}

        response = self.get_url(self.urls['login'], post_data=login_params, timeout=30)
        if not response:
            logger.log(u"Unable to connect to provider", logger.WARNING)
            return False

        if re.search('Username or password incorrect', response):
            logger.log(u"Invalid username or password. Check your settings", logger.WARNING)
            return False

        return True

    def search(self, search_params, age=0, ep_obj=None):

        results = []
        items = {'Season': [], 'Episode': [], 'RSS': []}

        if not self.login():
            return results

        for mode in search_params.keys():
            logger.log(u"Search Mode: %s" % mode, logger.DEBUG)
            for search_string in search_params[mode]:

                if mode != 'RSS':
                    logger.log(u"Search string: %s " % search_string, logger.DEBUG)

                searchURL = self.urls['search'] % (urllib.quote(search_string), self.categories)
                logger.log(u"Search URL: %s" % searchURL, logger.DEBUG)

                data = self.get_url(searchURL)
                if not data:
                    continue

                with BS4Parser(data, 'html5lib') as html:
                    torrent_table = html.find('div', id="torrenttable")
                    torrent_rows = []
                    if torrent_table:
                        torrent_rows = torrent_table.select("tr")

                    # Continue only if one Release is found
                    if len(torrent_rows) < 2:
                        logger.log(u"Data returned from provider does not contain any torrents", logger.DEBUG)
                        continue

                    # Scenetime apparently uses different number of cells in #torrenttable based
                    # on who you are. This works around that by extracting labels from the first
                    # <tr> and using their index to find the correct download/seeders/leechers td.
                    labels = [label.get_text(strip=True) for label in torrent_rows[0].find_all('td')]

                    for result in torrent_rows[1:]:
                        try:
                            cells = result.find_all('td')

                            link = cells[labels.index('Name')].find('a')
                            torrent_id = link['href'].replace('details.php?id=', '').split("&")[0]

                            title = link.get_text(strip=True)
                            download_url = self.urls['download'] % (torrent_id, "%s.torrent" % title.replace(" ", "."))

                            seeders = try_int(cells[labels.index('Seeders')].get_text(strip=True))
                            leechers = try_int(cells[labels.index('Leechers')].get_text(strip=True))
                            size = self._convertSize(cells[labels.index('Size')].get_text(strip=True))

                        except (AttributeError, TypeError, KeyError, ValueError):
                            continue

                        if not all([title, download_url]):
                            continue

                        # Filter unseeded torrent
                        if seeders < self.minseed or leechers < self.minleech:
                            if mode != 'RSS':
                                logger.log(u"Discarding torrent because it doesn't meet the minimum seeders or leechers: {0} (S:{1} L:{2})".format(title, seeders, leechers), logger.DEBUG)
                            continue

                        item = title, download_url, size, seeders, leechers
                        if mode != 'RSS':
                            logger.log(u"Found result: %s " % title, logger.DEBUG)

                        items[mode].append(item)

            # For each search mode sort all the items by seeders if available
            items[mode].sort(key=lambda tup: tup[3], reverse=True)

            results += items[mode]

        return results

    def seed_ratio(self):
        return self.ratio

    @staticmethod
    def _convertSize(size):
        modifier = size[-2:].upper()
        size = size[:-2].strip()
        try:
            size = float(size)
            if modifier in 'KB':
                size *= 1024 ** 1
            elif modifier in 'MB':
                size *= 1024 ** 2
            elif modifier in 'GB':
                size *= 1024 ** 3
            elif modifier in 'TB':
                size *= 1024 ** 4
            else:
                raise
        except Exception:
            size = -1

        return long(size)

class SceneTimeCache(tvcache.TVCache):
    def __init__(self, provider_obj):

        tvcache.TVCache.__init__(self, provider_obj)

        # only poll SceneTime every 20 minutes max
        self.minTime = 20

    def _getRSSData(self):
        search_params = {'RSS': ['']}
        return {'entries': self.provider.search(search_params)}


provider = SceneTimeProvider()
