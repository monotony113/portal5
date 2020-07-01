# blacklist.py
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

from collections.abc import Hashable, Callable, MutableSet

import requests

from . import exceptions


class RequestTest(Hashable):
    def __init__(self, test: Callable, name=None, description=None):
        object.__setattr__(self, '_test', test)
        object.__setattr__(self, 'name', name or test.__name__)
        self.description = description

    def __setattr__(self, name, value):
        if name in {'_test', 'name'}:
            raise ValueError(f'Setting immutable attribute "{name}" is not allowed')
        return object.__setattr__(self, name, value)

    def __call__(self, req: requests.PreparedRequest) -> bool:
        return self._test(req)

    def __hash__(self):
        return hash(self.name) ^ hash(self._test)

    def __str__(self):
        return super().__str__()

    @classmethod
    def test(cls, name=None, description=None):
        def wrap(f):
            return cls(f, name, description)

        return wrap


class RequestFilter(MutableSet):
    def __init__(self, *iterable):
        iterable = iterable or set()
        self._tests = {*iterable}

    def __contains__(self, item):
        return item in self._tests

    def __iter__(self):
        return self._tests.__iter__()

    def __len__(self):
        return self._tests.__len__()

    def add(self, item):
        return self._tests.add(item)

    def discard(self, item):
        return self._tests.discard(item)

    def test(self, request: requests.PreparedRequest):
        for f in self._tests:
            should_abort = False
            try:
                should_abort = f(request)
            except Exception:
                pass
            if should_abort:
                return exceptions.PortalSelfProtect(request.url, f)
        return None


def setup_filters(app):
    filter_kwargs = app.config.get('PORTAL_URL_FILTERS', list())
    tests = RequestFilter()
    for kwargs in filter_kwargs:
        tests.add(RequestTest(**kwargs))
    app.config['PORTAL_URL_FILTERS'] = tests
