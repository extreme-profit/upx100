(() => {
    const sidebar = document.getElementById('panel-sidebar');
    const toggle = document.getElementById('panel-toggle');
    const mobileToggle = document.getElementById('panel-mobile-toggle');
    const backdrop = document.getElementById('panel-backdrop');
    if (!sidebar || !toggle || !mobileToggle || !backdrop) return;
    const mobile = window.matchMedia('(max-width: 900px)');
    const root = document.documentElement;
    let collapsed = root.classList.contains('panel-collapsed');
    let open = false;
    try { collapsed = localStorage.getItem('panel-collapsed') === 'true'; } catch (_) {}

    function render() {
        root.classList.toggle('panel-collapsed', !mobile.matches && collapsed);
        document.body.classList.toggle('panel-open', mobile.matches && open);
        // A compact desktop rail remains interactive and keyboard accessible.
        sidebar.inert = mobile.matches && !open;
        toggle.setAttribute('aria-expanded', String(mobile.matches ? open : !collapsed));
        toggle.setAttribute('aria-label', mobile.matches ? 'Закрыть меню' : collapsed ? 'Развернуть меню' : 'Свернуть меню');
        toggle.title = toggle.getAttribute('aria-label');
        mobileToggle.setAttribute('aria-expanded', String(mobile.matches && open));
        backdrop.hidden = !(mobile.matches && open);
    }

    function close() {
        open = false;
        render();
        if (mobile.matches) mobileToggle.focus();
    }

    toggle.addEventListener('click', () => {
        if (mobile.matches) { close(); return; }
        collapsed = !collapsed;
        try { localStorage.setItem('panel-collapsed', String(collapsed)); } catch (_) {}
        render();
    });
    mobileToggle.addEventListener('click', () => {
        open = !open;
        render();
        if (open) toggle.focus();
    });
    backdrop.addEventListener('click', close);
    document.addEventListener('keydown', event => {
        if (!mobile.matches || !open) return;
        if (event.key === 'Escape') { event.preventDefault(); close(); }
        if (event.key === 'Tab') {
            const focusables = [...sidebar.querySelectorAll('a[href],button')];
            const first = focusables[0], last = focusables[focusables.length - 1];
            if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
            else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
        }
    });
    mobile.addEventListener('change', () => {
        const focusWasInside = sidebar.contains(document.activeElement);
        const focusWasMobileToggle = document.activeElement === mobileToggle;
        open = false;
        render();
        if (mobile.matches && focusWasInside) mobileToggle.focus();
        else if (!mobile.matches && focusWasMobileToggle) toggle.focus();
    });
    window.addEventListener('storage', event => {
        if (event.key === 'panel-collapsed' || event.key === null) {
            collapsed = event.key === null ? false : event.newValue === 'true';
            render();
        }
    });
    render();
})();
