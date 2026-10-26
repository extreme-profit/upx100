const {test} = require('node:test');
const assert = require('node:assert/strict');
const {readFileSync} = require('node:fs');
const {resolve} = require('node:path');
const vm = require('node:vm');
const code = readFileSync(resolve(__dirname, '../panel-navigation.js'), 'utf8');
const preferences = readFileSync(resolve(__dirname, '../../../templates/includes/panel_preferences.html'), 'utf8').replace(/<\/?script>/g, '');

function fixture({saved = null, isMobile = false, storageBlocked = false} = {}) {
    const document = {listeners: {}, addEventListener(type, cb) { this.listeners[type] = cb; }};
    class Element {
        constructor() {
            this.attrs = {};
            this.events = {};
            const values = new Set();
            this.classList = {
                toggle: (key, on) => on ? values.add(key) : values.delete(key),
                contains: key => values.has(key),
            };
        }
        setAttribute(key, value) { this.attrs[key] = value; }
        getAttribute(key) { return this.attrs[key]; }
        addEventListener(key, cb) { this.events[key] = cb; }
        focus() { document.activeElement = this; }
        click() { this.events.click(); }
    }
    const sidebar = new Element(), toggle = new Element(), mobileToggle = new Element();
    const backdrop = new Element(), lastLink = new Element();
    sidebar.querySelectorAll = () => [toggle, lastLink];
    sidebar.contains = element => [sidebar, toggle, lastLink].includes(element);
    document.body = new Element();
    document.documentElement = new Element();
    document.getElementById = key => ({'panel-sidebar': sidebar, 'panel-toggle': toggle,
        'panel-mobile-toggle': mobileToggle, 'panel-backdrop': backdrop})[key];
    const media = {matches: isMobile, addEventListener(_, cb) { this.change = cb; }};
    const window = {events: {}, matchMedia: () => media,
        addEventListener(type, cb) { this.events[type] = cb; }};
    const stored = new Map(saved === null ? [] : [['panel-collapsed', saved]]);
    const localStorage = {
        getItem(key) { if (storageBlocked) throw Error('blocked'); return stored.get(key); },
        setItem(key, value) { if (storageBlocked) throw Error('blocked'); stored.set(key, value); },
    };
    const context = vm.createContext({window, document, localStorage});
    vm.runInContext(preferences, context);
    const collapsedBeforeNavigationScript = document.documentElement.classList.contains('panel-collapsed');
    vm.runInContext(code, context);
    return {document, window, media, stored, sidebar, toggle, mobileToggle, backdrop, lastLink,
        collapsedBeforeNavigationScript,
        collapsed: () => document.documentElement.classList.contains('panel-collapsed')};
}

test('desktop collapse keeps links interactive and persists on a fresh page', () => {
    const page = fixture();
    page.toggle.click();
    assert.equal(page.collapsed(), true);
    assert.equal(page.sidebar.inert, false);
    assert.equal(page.toggle.getAttribute('aria-expanded'), 'false');
    assert.equal(page.stored.get('panel-collapsed'), 'true');
    const nextPage = fixture({saved: page.stored.get('panel-collapsed')});
    assert.equal(nextPage.collapsedBeforeNavigationScript, true);
    assert.equal(nextPage.collapsed(), true);
    assert.equal(nextPage.sidebar.inert, false);
    nextPage.toggle.click();
    assert.equal(nextPage.collapsed(), false);
    assert.equal(nextPage.stored.get('panel-collapsed'), 'false');
});

test('mobile drawer ignores compact preference without overwriting it', () => {
    const page = fixture({saved: 'true', isMobile: true});
    assert.equal(page.collapsed(), false);
    assert.equal(page.sidebar.inert, true);
    page.mobileToggle.click();
    assert.equal(page.sidebar.inert, false);
    assert.equal(page.backdrop.hidden, false);
    assert.equal(page.document.activeElement, page.toggle);
    page.toggle.click();
    assert.equal(page.sidebar.inert, true);
    assert.equal(page.document.activeElement, page.mobileToggle);
    assert.equal(page.stored.get('panel-collapsed'), 'true');
});

test('mobile Escape, backdrop and keyboard focus wrapping work', () => {
    const page = fixture({isMobile: true});
    page.mobileToggle.click();
    let prevented = false;
    page.document.listeners.keydown({key: 'Tab', shiftKey: true, preventDefault() { prevented = true; }});
    assert.equal(prevented, true);
    assert.equal(page.document.activeElement, page.lastLink);
    page.document.listeners.keydown({key: 'Tab', preventDefault() {}});
    assert.equal(page.document.activeElement, page.toggle);
    page.document.listeners.keydown({key: 'Escape', preventDefault() {}});
    assert.equal(page.sidebar.inert, true);
    page.mobileToggle.click();
    page.backdrop.click();
    assert.equal(page.sidebar.inert, true);
});

test('viewport changes preserve desktop preference and move focus out of hidden controls', () => {
    const page = fixture({saved: 'true'});
    page.toggle.focus();
    page.media.matches = true;
    page.media.change();
    assert.equal(page.collapsed(), false);
    assert.equal(page.document.activeElement, page.mobileToggle);
    page.media.matches = false;
    page.media.change();
    assert.equal(page.collapsed(), true);
    assert.equal(page.document.activeElement, page.toggle);
    assert.equal(page.sidebar.inert, false);
});

test('blocked browser storage does not break collapse', () => {
    const page = fixture({storageBlocked: true});
    page.toggle.click();
    assert.equal(page.collapsed(), true);
    page.toggle.click();
    assert.equal(page.collapsed(), false);
});

test('preference changes in another tab update current width', () => {
    const page = fixture();
    page.window.events.storage({key: 'panel-collapsed', newValue: 'true'});
    assert.equal(page.collapsed(), true);
    page.window.events.storage({key: null});
    assert.equal(page.collapsed(), false);
});
