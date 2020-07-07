# config.py
# Copyright (C) 2020  Tony Wu <tony[dot]wu(at)nyu[dot]edu>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

# PORTAL_URL_FILTERS = [
#     dict(name='*', description='all URLs', test=lambda r: True),
#     dict(name='http://*', description='No plain-text HTTP', test=lambda r: urlsplit(r.url).scheme == 'http'),
# ]

# PORTAL5_PASSTHRU_DOMAINS = {'fonts.googleapis.com', 'fonts.gstatic.com'}
# PORTAL5_PASSTHRU_URLS = {}

LANGUAGES = ['en', 'zh_cn']

# JWT_SECRET_KEY = None

JWT_IDENTITY_CLAIM = 'sub'
