(() => {
    const sidebar = document.getElementById('panel-sidebar');
    const toggle = document.getElementById('panel-toggle');
    const backdrop = document.getElementById('panel-backdrop');
    if (!sidebar || !toggle) return;
    const mobile = window.matchMedia('(max-width: 900px)');
    let collapsed = false;
    let open = false;
    try { collapsed = localStorage.getItem('panel-collapsed') === 'true'; } catch (_) {}
    function render() {
        const visible = mobile.matches ? open : !collapsed;
        document.body.classList.toggle('panel-collapsed', !mobile.matches && collapsed);
        document.body.classList.toggle('panel-open', mobile.matches && open);
        sidebar.inert = !visible;
        toggle.setAttribute('aria-expanded', String(visible));
        toggle.setAttribute('aria-label', visible ? 'Свернуть боковую панель' : 'Открыть боковую панель');
        backdrop.hidden = !(mobile.matches && open);
    }
    function close() { open = false; render(); toggle.focus(); }
    toggle.addEventListener('click', () => {
        if (mobile.matches) open = !open;
        else {
            collapsed = !collapsed;
            try { localStorage.setItem('panel-collapsed', String(collapsed)); } catch (_) {}
        }
        render();
        if (mobile.matches && open) sidebar.querySelector('button, a')?.focus();
    });
    backdrop.addEventListener('click', close);
    sidebar.querySelector('[data-panel-close]').addEventListener('click', close);
    document.addEventListener('keydown', event => {
        if (!mobile.matches || !open) return;
        if (event.key === 'Escape') close();
        if (event.key === 'Tab') {
            const focusables = [...sidebar.querySelectorAll('a[href],button')];
            const first = focusables[0], last = focusables[focusables.length - 1];
            if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
            else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
        }
    });
    mobile.addEventListener('change', () => { open = false; render(); });
    render();
})();
