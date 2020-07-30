# build.py
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

import asyncio
import logging
import os
import shutil
import subprocess
from itertools import chain
from pathlib import Path

logging.basicConfig(level=logging.INFO)
log = logging.getLogger()

CWD = Path(__file__).parents[1]
os.chdir(CWD)

SOURCE = Path('./src')
PUBLIC = Path('./public')
STATIC = Path('./static')
MISC = Path('./opt')

VENDORS = ['parse5']

PATH_STYLES = ('assets', 'styles')
PATH_WORKER_MAIN = ('main', 'index.js')

GITIGNORE = """*
!.gitignore"""

sem = asyncio.Semaphore(3)


def check_prerequisites():
    for tool in {'browserify', 'terser', 'sass', 'rsync'}:
        if not shutil.which(tool):
            raise AssertionError(f'Cannot find {tool} on PATH')


async def browserify_terser(src, dest, browserify_args=(), terser_args=()):
    log.info(f'Transforming {src} => {dest}')
    src = src and str(src)
    browserify_args = ['browserify', *browserify_args]
    if src:
        browserify_args.append(src)
    terser_args = ['terser', '--compress', '--mangle', *terser_args]

    with open(dest, 'w') as f:
        stdin, stdout = os.pipe()
        log.debug(f'browserify {src} => {dest}')
        browserify = await asyncio.create_subprocess_exec(
            *browserify_args,
            stdout=stdout, stderr=asyncio.subprocess.PIPE,
        )
        os.close(stdout)
        log.debug(f'terser {src} => {dest}')
        terser = await asyncio.create_subprocess_exec(
            *terser_args,
            stdin=stdin, stdout=f, stderr=asyncio.subprocess.PIPE,
        )
        os.close(stdin)
        await browserify.wait()
        await terser.wait()
        if browserify.returncode:
            raise AssertionError(f'browserify returned code {browserify.returncode}\nError:\n{(await browserify.stderr.read()).decode("utf8")}')
        if terser.returncode:
            raise AssertionError(f'terser returned code {terser.returncode}\nError:\n{(await terser.stderr.read()).decode("utf8")}')

    log.info(f'Done: {src} => {dest}')


async def transform(*args, **kwargs):
    async with sem:
        return await browserify_terser(*args, **kwargs)


def build():
    log.info('Cleaning up...')
    for directory in {PUBLIC, STATIC}:
        shutil.rmtree(str(directory), ignore_errors=True)
        os.makedirs(directory, exist_ok=True)
        with open(directory.joinpath('.gitignore'), 'w') as f:
            f.write(GITIGNORE)

    log.info('Compiling stylesheets using sass')
    subprocess.Popen(['sass', f'{SOURCE.joinpath(*PATH_STYLES)}:{STATIC.joinpath(*PATH_STYLES)}', '-s', 'compressed'], stdout=subprocess.DEVNULL)
    log.info('Copying static files')
    subprocess.Popen(['rsync', '-av', f'{MISC}/', str(STATIC)], stdout=subprocess.DEVNULL)

    loop = asyncio.get_event_loop()
    tasks = []
    tasks.extend([
        loop.create_task(transform(
            None,
            STATIC.joinpath('vendor.min.js'),
            list(chain(*[('-r', vendor) for vendor in VENDORS])),
        )),
        loop.create_task(transform(
            SOURCE.joinpath(*PATH_WORKER_MAIN),
            PUBLIC.joinpath('sw.js'),
            list(chain(*[('-x', vendor) for vendor in VENDORS])),
        )),
    ])

    os.makedirs(PUBLIC.joinpath('client'), exist_ok=True)
    for script in os.listdir(SOURCE.joinpath('client')):
        src = SOURCE.joinpath('client', script)
        dest = PUBLIC.joinpath('client', script)
        tasks.append(loop.create_task(transform(src, dest)))

    tasks = [asyncio.ensure_future(t) for t in tasks]

    loop.run_until_complete(asyncio.wait(tasks))
    loop.close()


if __name__ == '__main__':
    build()
