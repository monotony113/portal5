# jwtlib.py
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

import time
import uuid
from collections.abc import Hashable, Mapping, MutableSet
from contextlib import contextmanager
from datetime import datetime, timedelta
from typing import List, Dict

import jwt
import simplejson
from flask import Flask, _app_ctx_stack, current_app, request
from pytz import UTC


class JWTKit:
    JWT_OPTIONS = {k: True for k in {
        'require_iat',
        'require_nbf',
        'verify_iat',
        'verify_iss',
        'verify_aud',
        'verify_signature',
    }}

    def __init__(self, app=None, algorithm='HS256'):
        self._algorithm = algorithm
        self._key = None
        self._claims = {}
        if app:
            self.init_app(app)

    def init_app(self, app: Flask):
        conf = app.config.get_namespace('JWT_')
        self._key = conf.get('secret_key', None)

        default_claims = app.config.get_namespace('JWT_DEFAULT_')
        self._claims.update(default_claims)

        @app.before_first_request
        def get_iss():
            iss = f'{request.scheme}://{request.host}'
            self._iss = iss
            self._aud = iss
            self._claims['iss'] = iss
            self._claims['aud'] = iss

        @app.before_request
        def create_store():
            _app_ctx_stack.top.jwtstore = JWTStore()

        if not hasattr(app, 'extensions'):
            app.extensions = {}
        app.extensions['jwtkit'] = self

    @property
    def key(self):
        key = self._key
        if not key:
            raise ValueError('JWTKit has not been initialized with a key')
        return key

    @classmethod
    def _resolve_time(cls, value, base=None):
        base = base or datetime.now(tz=UTC)
        if isinstance(value, timedelta):
            return base + value
        elif isinstance(value, (int, float)):
            return datetime.fromtimestamp(value, tz=UTC)
        return value

    @contextmanager
    def encoder_context(self, **kwargs):
        _app_ctx_stack.top.jwt_context = kwargs
        try:
            yield
        finally:
            _app_ctx_stack.top.jwt_context = None

    def get_from_context(self, key):
        ctx = getattr(_app_ctx_stack.top, 'jwt_context', None)
        if not ctx:
            raise ValueError('Working outside of encoder context')
        return ctx.get(key, None)

    def _json_encoder_default(self, o):
        if isinstance(o, datetime):
            return int(o.timestamp())
        if isinstance(o, timedelta):
            iat = self.get_from_context('iat')
            return int((iat + o).timestamp())
        return str(o)

    def create_token(self, sub=None, aud=None, nbf=None, exp=None, **claims):
        iat = datetime.now(tz=UTC)
        aud = aud or self._aud
        jti = str(uuid.uuid4())

        if nbf:
            nbf = self._resolve_time(nbf, iat)
        if exp:
            exp = self._resolve_time(exp, iat)

        payload = {k: v for k, v in {
            **self._claims,
            'iat': iat,
            'nbf': nbf or iat,
            'exp': exp,
            'sub': sub,
            'aud': aud,
            'jti': jti,
        }.items() if v}

        with self.encoder_context(iat=iat):
            payload[aud] = simplejson.loads(simplejson.dumps(claims, ensure_ascii=False, default=self._json_encoder_default, encoding='utf8'))

        return self.encode_token(payload)

    def encode_token(self, token):
        return jwt.encode(token, self.key, self._algorithm).decode('utf8')

    def decode_token(self, token, iss=None, aud=None, allow_expired=False, leeway=0, **kwargs):
        iss = iss or self._iss
        aud = aud or self._aud
        exp = not allow_expired
        options = {**self.JWT_OPTIONS, **kwargs, 'require_exp': exp, 'verify_exp': exp}
        payload = jwt.decode(
            token, self.key, self._algorithm,
            options=options, audience=aud, issuer=iss, leeway=leeway,
        )
        payload[aud] = payload.get(aud, {})
        self.add(payload)
        return payload

    @classmethod
    def get_jwtkit(cls):
        jwtkit: cls = current_app.extensions.get('jwtkit')
        if not jwtkit:
            raise AttributeError('No JWTKit instance found in current app context')
        return jwtkit

    def add(self, jwt=None):
        _app_ctx_stack.top.jwtstore.add(jwt)


class JWTStore(MutableSet):
    def __init__(self):
        self._tokens = {}
        self._indices = {}

    def __contains__(self, token):
        try:
            if isinstance(token, str):
                jti = token
            else:
                jti = self._guard(token)
            return hash(jti) in self._tokens
        except (TypeError, KeyError, ValueError):
            return False

    def __iter__(self):
        return iter(self._tokens.values())

    def __len__(self):
        return len(self._tokens)

    def _guard(self, token):
        if not isinstance(token, Mapping):
            raise ValueError('Token is not an instance of a Mapping')
        if 'jti' not in token:
            raise ValueError('Token does not contain a valid "jti" claim')
        return token['jti']

    def _collect_key_value_pairs(self, token):
        reserved_claims = {'iss', 'sub', 'aud', 'iat', 'nbf', 'exp'} & token.keys()
        reserved_claims = {(k, token[k]) for k in reserved_claims}

        private_claims = set()
        aud = token.get('aud')
        if aud:
            claims = token.get(aud, {})
            if isinstance(claims, Mapping):
                private_claims = {(f'_{k}', v) for k, v in claims.items() if isinstance(v, Hashable)}

        return reserved_claims | private_claims

    def add(self, token):
        jti = self._guard(token)
        existing = self._tokens.get(jti)
        if existing:
            self.discard(existing)

        jti_hash = hash(jti)
        items = self._collect_key_value_pairs(token)
        for k, v in items:
            index: dict = self._indices.setdefault(k, {})
            identifiers: dict = index.setdefault(v, {})
            identifiers[jti_hash] = True

        self._tokens[jti_hash] = token

    def discard(self, token):
        if isinstance(token, str):
            jti = token
        else:
            jti = self._guard(token)

        jti_hash = hash(jti)
        token = self._tokens[jti_hash]
        items = self._collect_key_value_pairs(token)
        for k, v in items:
            index: dict = self._indices[k]
            identifiers: dict = index[v]
            del identifiers[jti_hash]
            if not identifiers:
                del index[v]
            if not index:
                del self._indices[k]

        del self._tokens[jti_hash]
        return token

    def _get_jti_hashes(self, **claims):
        if not claims:
            return self._tokens.keys()
        jti = claims.get('jti')
        jti_hash = hash(jti)
        if jti:
            return {jti_hash} if jti_hash in self._tokens else set()
        jtis: set = None
        for k, v in claims.items():
            index: dict = self._indices.get(k, {})
            identifiers: dict = index.get(v, {})
            jtis = identifiers.keys() if jtis is None else jtis & identifiers.keys()
            if not jtis:
                return set()
        return jtis or set()

    def get(self, **claims):
        jtis = self._get_jti_hashes(**claims)
        return self._tokens[list(jtis)[0]] if jtis else {}

    def get_all(self, **claims):
        return [self._tokens[jti] for jti in self._get_jti_hashes(**claims)]


def get_jwtstore() -> JWTStore:
    return getattr(_app_ctx_stack.top, 'jwtstore', JWTStore())


def get_jwt(**query) -> Dict:
    return get_jwtstore().get(**query)


def get_all_jwts(**query) -> List[Dict]:
    return get_jwtstore().get_all(**query)


def get_private_claims(jwt):
    aud = jwt.get('aud')
    if aud:
        return jwt.get(aud, {})
    return {}


def verify_exp(jwt):
    exp = jwt.get('exp')
    return not exp or time.time() < exp


def verify_claims(jwt, **claims):
    private_claims = get_private_claims(jwt)
    for k, v in claims.items():
        if k[0] == '_':
            match = private_claims.get(k[1:]) == v
        else:
            match = jwt.get(k) == v
        if not match:
            return False
    return True
