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
from werkzeug.exceptions import HTTPException


class PortalException(Exception):
    pass


class PortalHTTPException(HTTPException, PortalException):
    def __init__(self, description=None, response=None, status=500, unsafe_markup=False, **kwargs):
        super().__init__(description=description, response=response, **kwargs)
        self.code = status
        self.unsafe_markup = unsafe_markup

    def get_response(self, environ=None):
        return Response(render_template('error.html', statuscode=self.code, message=self.description or '', unsafe_markup=self.unsafe_markup), self.code)


class PortalBadRequest(PortalHTTPException):
    def __init__(self, description, response=None, **kwargs):
        super().__init__(description=description, response=response, **kwargs)
        self.code = 400


class PortalUnsupportedScheme(PortalBadRequest):
    def __init__(self, scheme, **kwargs):
        super().__init__(f'Unsupported URL scheme "{scheme}"', **kwargs)


class PortalMissingDomain(PortalBadRequest):
    def __init__(self, url, **kwargs):
        super().__init__(f'URL <code>{url}</code> missing website domain name or location.', **kwargs)


class PortalMissingProtocol(PortalBadRequest):
    def __init__(self, requested, **kwargs):
        super().__init__(None, **kwargs)
        self.requested = requested

    def get_response(self, environ=None):
        return Response(render_template('missing-protocol.html', remote=self.requested), self.code)


class PortalSelfProtect(PortalHTTPException):
    def __init__(self, url, test, **kwargs):
        super().__init__(description=None, response=None, status=403, unsafe_markup=True, **kwargs)
        self.url = url
        self.test = test

    def get_response(self, environ=None):
        return Response(render_template('server-protection.html', remote=self.url, test=self.test), 403)
