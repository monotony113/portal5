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
"""Utility functions for manipulating bitmasks."""

from functools import reduce


def bits_to_mask(bits):
    """Convert a set of integers specifying bits that are on to a bitmask as integer.

    For example, `bits_to_mask({1, 3, 5})` will return `42`, which equals `0b101010`
    (`1` on digit places 1, 3, and 5, and `0` on the rest).

    Digits are zero-based.

    :param bits: A collection of integers that specify which bits to turn **on**.
    :type bits: Collection[int]
    :return: The equivalent bitmask
    :rtype: int
    """
    return reduce(lambda x, y: x | y, (2 ** b for b in bits), 0)


def mask_to_bits(mask):
    """Convert a bitmask to a set of integers specifying bits that are on.

    For example, `mask_to_bits(42)`, which equals `0b101010`, will return `{1, 3, 5}`
    (`1` on digit places 1, 3, and 5, and `0` on the rest).

    Digits are zero-based.

    :param mask: A bitmask
    :type mask: int
    :return: A collection of integers specifying bits that are on.
    :rtype: Collection[int]
    """
    n = 0
    while 1 << n <= mask:
        n += 1
    return {d for d in range(0, n) if 2 ** d & mask}


def constrain_ones(mask, bit, ones):
    """Return a new bitmask based on :param mask:, such that if the bit specified by :param bit: is on, then all bits specified in :param ones: are also on.

    For example, `constrain_ones(0b101010, 1, {1, 2, 4})` will return `0b111110` because bit `1` of `0b101010`
    is on, while `constrain_ones(0b101010, 0, {1, 2, 4})` will return `0b101010` because bit `0` of `0b101010`
    is off.

    :param mask: The source bitmask
    :type mask: int
    :param bit: The bit to check
    :type bit: int
    :param ones: The bits to turn on if bit :param bit: in :param mask: is on
    :type ones: Collection[int]
    :return: The modified bitmask
    :rtype: int
    """
    power = 2 ** bit
    sync = power | bits_to_mask(ones)
    return mask | sync if mask & power & sync else mask


def constrain_zeroes(mask, bit, zeroes):
    """Return a new bitmask based on :param mask:, such that if the bit specified by :param bit: is off, then all bits specified in :param zeroes: are also off.

    For example, `constrain_zeroes(0b101010, 0, {1, 3, 5})` will return `0b000000` because bit `0` of `0b101010`
    is off, while `constrain_zeroes(0b101010, 1, {1, 3, 5})` will return `0b101010` because bit `1` of `0b101010`
    is on.

    :param mask: The source bitmask
    :type mask: int
    :param bit: The bit to check
    :type bit: int
    :param zeroes: The bits to turn on if bit :param bit: in :param mask: is on
    :type zeroes: Collection[int]
    :return: The modified bitmask
    :rtype: int
    """
    power = 2 ** bit
    sync = power | bits_to_mask(zeroes)
    return mask if mask & power & sync else mask & ~sync
