/**
 * KYRO Landing Page - JavaScript
 * Handles the hero video sound toggle, sticky header, mobile menu and
 * scroll-reveal animations.
 */

document.addEventListener('DOMContentLoaded', function() {
    initVolumeControl();
    initStickyHeader();
    initMobileMenu();
    initScrollAnimations();

    const year = document.getElementById('lpYear');
    if (year) year.textContent = new Date().getFullYear();
});

/**
 * Volume Control for Hero Video
 */
function initVolumeControl() {
    const volumeBtn = document.getElementById('volumeBtn');
    const heroVideo = document.getElementById('hero-video');

    if (!volumeBtn || !heroVideo) return;

    volumeBtn.addEventListener('click', function() {
        heroVideo.muted = !heroVideo.muted;
        if (!heroVideo.muted) {
            heroVideo.play().catch(function() {});
        }
        volumeBtn.setAttribute('aria-label', heroVideo.muted ? 'Unmute video' : 'Mute video');
        volumeBtn.innerHTML = heroVideo.muted
            ? '<i class="fas fa-volume-xmark" aria-hidden="true"></i>'
            : '<i class="fas fa-volume-high" aria-hidden="true"></i>';
    });
}

/**
 * Header shadow once the page scrolls
 */
function initStickyHeader() {
    const header = document.getElementById('lpHeader');
    if (!header) return;

    const update = function() {
        header.classList.toggle('is-scrolled', window.scrollY > 10);
    };
    window.addEventListener('scroll', update, { passive: true });
    update();
}

/**
 * Mobile navigation toggle
 */
function initMobileMenu() {
    const btn = document.getElementById('lpMenuBtn');
    const nav = document.getElementById('lpNav');
    if (!btn || !nav) return;

    const setOpen = function(open) {
        nav.classList.toggle('is-open', open);
        btn.setAttribute('aria-expanded', String(open));
        btn.setAttribute('aria-label', open ? 'Close menu' : 'Open menu');
        btn.innerHTML = open ? '<i class="fas fa-xmark"></i>' : '<i class="fas fa-bars"></i>';
    };

    btn.addEventListener('click', function() {
        setOpen(!nav.classList.contains('is-open'));
    });
    nav.querySelectorAll('a').forEach(function(link) {
        link.addEventListener('click', function() { setOpen(false); });
    });
}

/**
 * Scroll Animations with Intersection Observer
 */
function initScrollAnimations() {
    if (!('IntersectionObserver' in window)) return;
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;

    const observer = new IntersectionObserver(function(entries) {
        entries.forEach(function(entry) {
            if (entry.isIntersecting) {
                entry.target.classList.add('is-visible');
                observer.unobserve(entry.target);
            }
        });
    }, { threshold: 0.1, rootMargin: '0px 0px -60px 0px' });

    document.querySelectorAll('.lp-section__head, .lp-how__image, .lp-how__text, .lp-card, .lp-product').forEach(function(el) {
        el.classList.add('fade-in-view');
        observer.observe(el);
    });
}
