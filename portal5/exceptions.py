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

from flask import Response, render_template
from flask_babel import _
from werkzeug.exceptions import HTTPException


class PortalException(Exception):
    pass


class PortalHTTPException(HTTPException, PortalException):
    def __init__(self, description=None, response=None, status=500, unsafe_markup=False, **kwargs):
        super().__init__(description=description, response=response, **kwargs)
        self.code = status
        self.unsafe_markup = unsafe_markup

    def get_response(self, environ=None):
        return Response(render_template('exceptions/error.html', statuscode=self.code, message=self.description or '', unsafe_markup=self.unsafe_markup), self.code)


class PortalBadRequest(PortalHTTPException):
    def __init__(self, description, response=None, **kwargs):
        super().__init__(description=description, response=response, **kwargs)
        self.code = 400


class PortalUnsupportedScheme(PortalBadRequest):
    def __init__(self, scheme, **kwargs):
        super().__init__(_('Unsupported URL scheme "%(scheme)s"', scheme=scheme), **kwargs)


class PortalMissingDomain(PortalBadRequest):
    def __init__(self, url, **kwargs):
        super().__init__(_('URL <code>%(url)s</code> missing website domain name or location.', url=url), **kwargs)


class PortalMissingProtocol(PortalBadRequest):
    def __init__(self, requested, **kwargs):
        super().__init__(None, **kwargs)
        self.requested = requested

    def get_response(self, environ=None):
        return Response(render_template('exceptions/missing-protocol.html', remote=self.requested), self.code)


class PortalSelfProtect(PortalHTTPException):
    def __init__(self, url, test, **kwargs):
        super().__init__(description=None, response=None, status=403, unsafe_markup=True, **kwargs)
        self.url = url
        self.test = test

    def get_response(self, environ=None):
        return Response(render_template('exceptions/server-protection.html', remote=self.url, test=self.test), 403)


class PortalSettingsNotSaved(PortalHTTPException):
    def __init__(self, **kwargs):
        desc = [
            '<p class="color-red-fg">' + _('Your preferences have not been saved.') + '</p>',
            '<a href="/settings">' + _('Click here to go back to Settings') + '</a>',
        ]
        super().__init__(description=''.join(desc), status=401, **kwargs)
