// preferences.js
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

const pref2 = new (require('./utils').Preferences2)()

const dependencies = JSON.parse('{{ dep|default(dict({"":0}))|tojson }}')
const requirements = JSON.parse('{{ req|default(dict({"":0}))|tojson }}')

class Preferences {
    constructor() {
        this.pendingChanges = []
        this.ids = []
    }
    findAllOptions() {
        let optionElements = document.querySelectorAll('.form-option')
        for (let i = 0; i < optionElements.length; i++) {
            let elem = optionElements[i]
            let id = elem.id
            this[id] = new PreferenceOption(id)
            this.ids.push(id)
        }
    }
    /** @returns {PreferenceOption} */
    getOption(id) {
        return this[id]
    }
    getAllOptions() {
        return this.ids.map((id) => this.getOption(id))
    }
    syncOptions(id) {
        let option = this.getOption(id)
        let newValue = option.value ^ 1
        let associated = newValue ? option.dependsOn : option.requiredBy
        let syncRequired = false
        for (let i = 0; i < associated.length; i++) {
            let associatedOption = this.getOption(associated[i])
            if (associatedOption.value != newValue) {
                syncRequired = true
                associatedOption.setHighlight('on')
                this.pendingChanges.push(() => (associatedOption.value = newValue))
            }
        }
        if (syncRequired) {
            option.setHighlight('on')
            option.setMultiOptionConfirm('on', newValue)
            this.pendingChanges.push(() => (option.value = newValue))
        }
        return syncRequired
    }
    flushChange(commit) {
        if (commit) for (let i = 0; i < this.pendingChanges.length; i++) this.pendingChanges[i]()
        this.getAllOptions().forEach((opt) => {
            opt.setHighlight('off')
            opt.setMultiOptionConfirm('off')
        })
        this.pendingChanges = []
    }
    get hasPendingChanges() {
        return this.pendingChanges.length
    }
}

class PreferenceOption {
    constructor(id) {
        this.id = id
        this.container = document.getElementById(id)
        this.input = this.container.getElementsByTagName('input')[0]

        this.dependsOn = dependencies[this.id] || []
        this.requiredBy = requirements[this.id] || []

        this.multiOptionsHint = this.container.getElementsByClassName('multi-option-confirm')[0]

        this.button = this.container.getElementsByClassName('toggle-button')[0]
        this.accent = `color-${this.button.dataset.color}-bg`

        this.details = this.container.getElementsByClassName('option-description')[0]
        this.bullet = this.container.getElementsByClassName('option-bullet')[0]
    }
    get value() {
        return parseInt(this.input.value)
    }
    set value(val) {
        let value = val === undefined ? this.value ^ 1 : parseInt(val)
        this.input.value = value
        this.button.textContent = value ? 'on' : 'off'
        this.button.classList.remove(value ? 'color-gray-bg' : this.accent)
        this.button.classList.add(value ? this.accent : 'color-gray-bg')
        return value
    }
    toggleDescription() {
        this.details.classList.toggle('collapsed')
        this.bullet.classList.toggle('rotate-90d')
    }
    setMultiOptionConfirm(status, willEnable) {
        let hint = this.multiOptionsHint
        if (status === 'on') hint.classList.remove('hidden')
        else hint.classList.add('hidden')
        if (status === 'on') {
            hint.getElementsByTagName('span')[0].innerText = willEnable
                ? '{% trans %}Enabling{% endtrans %}'
                : '{% trans %}Disabling{% endtrans %}'
            hint.getElementsByTagName('mark')[0].innerText = willEnable
                ? '{% trans %}enable{% endtrans %}'
                : '{% trans %}disable{% endtrans %}'
        }
    }
    setHighlight(status) {
        let container = this.container
        if (status === 'on') container.classList.add('highlighted')
        else container.classList.remove('highlighted')
    }
}

class SecondaryOption {
    constructor(id) {
        this.id = id
        this.container = document.getElementById(id)
        this.input = this.container.getElementsByClassName('secondary-option-value')[0]

        this.key = this.container.dataset.key

        this.input.addEventListener('change', () => pref2.set(this.key, this.input.value))
        this.setDefaultValue()
    }
    get uiSetter() {
        switch (this.input.tagName) {
            case 'SELECT':
                return (value) => {
                    let options = this.input.getElementsByTagName('option')
                    for (let i = options.length - 1; i >= 0; i--) {
                        let opt = options[i]
                        if (opt.value === value) opt.selected = true
                        else opt.selected = false
                    }
                }
            default:
                return () => {}
        }
    }
    setDefaultValue() {
        this.uiSetter(pref2.get(this.key))
    }
}

const preferences = new Preferences()

window.addEventListener('DOMContentLoaded', () => {
    setTimeout(() => {
        history.pushState('', document.title, window.location.pathname + window.location.search)
    }, 5000)

    preferences.findAllOptions()

    document.querySelectorAll('.toggle-button').forEach((btn) => {
        btn.addEventListener('click', (ev) => {
            if (preferences.hasPendingChanges) return
            const container = ev.currentTarget.closest('.form-option')
            if (!preferences.syncOptions(container.id)) preferences.getOption(container.id).value = undefined
        })
    })

    document.querySelectorAll('.option-name').forEach((l) => {
        let toggleDescription = (ev) => {
            const option = ev.currentTarget.closest('.option-container')
            preferences.getOption(option.id).toggleDescription()
        }
        l.addEventListener('click', toggleDescription)
        l.addEventListener('keydown', (ev) => {
            if (ev.key === 'Enter' || ev.key === ' ') {
                ev.preventDefault()
                toggleDescription(ev)
            }
        })
    })
    ;[
        ['.flush-change-cancel', false],
        ['.flush-change-confirm', true],
    ].forEach((pair) =>
        document
            .querySelectorAll(pair[0])
            .forEach((btn) => btn.addEventListener('click', () => preferences.flushChange(pair[1])))
    )

    document.querySelectorAll('.secondary-option').forEach((opt) => new SecondaryOption(opt.id))
})
