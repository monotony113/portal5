# bitmasklib.py
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

from functools import reduce


def bits_to_mask(bits):
    return reduce(lambda x, y: x | y, (2 ** b for b in bits), 0)


def mask_to_bits(mask):
    n = 0
    while 1 << n <= mask:
        n += 1
    return {d for d in range(0, n) if 2 ** d & mask}


def constrain_ones(mask, bit, ones):
    power = 2 ** bit
    sync = power | bits_to_mask(ones)
    return mask | sync if mask & power & sync else mask


def constrain_zeroes(mask, bit, zeroes):
    power = 2 ** bit
    sync = power | bits_to_mask(zeroes)
    return mask if mask & power & sync else mask & ~sync
