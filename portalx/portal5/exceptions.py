# exceptions.py
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

from ..exceptions import PortalHTTPException


class Portal5SettingsNotSaved(PortalHTTPException):
    def __init__(self, **kwargs):
        desc = [
            '<p class="color-red-fg">Your preferences have not been saved.</p>',
            '<a href="/settings">Click here to go back to Settings</a>',
        ]
        super().__init__(description=''.join(desc), status=401, **kwargs)
