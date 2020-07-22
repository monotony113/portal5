// injector.js
// Copyright (C) 2020  Tony Wu <tony[dot]wu(at)nyu[dot]edu>
// 
// This program is free software: you can redistribute it and/or modify
// it under the terms of the GNU Affero General Public License as published
// the Free Software Foundation, either version 3 of the License, or
// (at your option) any later version.
//
// This program is distributed in the hope that it will be useful,
// but WITHOUT ANY WARRANTY; without even the implied warranty of
// MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
// GNU General Public License for more details.
//
// You should have received a copy of the GNU Affero General Public License
// along with this program.  If not, see <https://www.gnu.org/licenses/>.

class Injector {
    static mapTree(tree, transform, childContainer) {
        transform(tree)
        if (tree[childContainer])
            tree[childContainer].forEach((branch) => this.mapTree(branch, transform, childContainer))
    }
    static dfsFirstInTree(tree, test, childContainer) {
        if (test(tree)) return tree
        if (tree[childContainer])
            for (let branch of tree[childContainer]) {
                let found = this.dfsFirstInTree(branch, test, childContainer)
                if (found) return found
            }
    }
    static makeElementNode(name, attributes = {}, text = null) {
        let node = {
            nodeName: name,
            tagName: name,
            namespaceURI: 'http://www.w3.org/1999/xhtml',
            attrs: Object.entries(attributes).map((p) => {
                return { name: p[0], value: p[1] }
            }),
            parentNode: undefined,
            childNodes: [],
        }
        if (text) this.append(node, this.makeTextNode(text))
        return node
    }
    static makeTextNode(text) {
        return {
            nodeName: '#text',
            parentNode: undefined,
            value: text,
        }
    }
    static append(parent, ...children) {
        for (let child of children) {
            child.parentNode = parent
        }
        parent.childNodes.push(...children)
    }
    static prepend(parent, ...children) {
        for (let child of children) {
            child.parentNode = parent
        }
        parent.childNodes.unshift(...children)
    }
}

module.exports = { Injector }
