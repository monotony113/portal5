# portal3.py
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

from urllib.parse import urlparse

import requests
from flask import stream_with_context, Blueprint, Flask, Request, Response
from flask import request as req

current_app: Flask
req: Request
portal3 = Blueprint('portal3', __name__)


@portal3.route('/<path:url>', methods=('GET', 'POST'))
def forward(url):
    urlp = urlparse(url)
    if urlp.scheme not in ('http', 'https'):
        return f'Unsupported URL scheme "{urlp.scheme}"', 400
    if not urlp.netloc:
        return 'Bad URL: no domain or location provided', 400

    req_headers = {**req.headers}
    del req_headers['Host']

    res = requests.request(
        method=req.method,
        url=url,
        params=req.args,
        data=req.data,
        headers=req_headers,
        cookies=req.cookies,
        stream=True
    )

    def pipe(response: requests.Response):
        while True:
            chunk = response.raw.read(128)
            if not chunk:
                break
            yield chunk

    return Response(stream_with_context(pipe(res)), status=res.status_code, headers=dict(**res.headers))
