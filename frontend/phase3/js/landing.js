/**
 * KYRO Landing Page - JavaScript
 * Handles animations, video controls, and interactions
 */

document.addEventListener('DOMContentLoaded', function() {
    // Initialize all features
    initVolumeControl();
    initScrollAnimations();
    initCardInteractions();
    
    console.log('✨ KYRO Landing Page initialized');
});

/**
 * Volume Control for Hero Video
 */
function initVolumeControl() {
    const volumeBtn = document.getElementById('volumeBtn');
    const heroVideo = document.getElementById('hero-video');
    
    if (!volumeBtn || !heroVideo) return;
    
    let isMuted = true;
    
    volumeBtn.addEventListener('click', function() {
        isMuted = !isMuted;
        heroVideo.muted = isMuted;
        
        // Toggle button style
        volumeBtn.classList.toggle('muted', isMuted);
        
        // Update icon
        if (isMuted) {
            volumeBtn.innerHTML = `
                <svg width="24" height="24" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5.586 15H4a1 1 0 01-1-1v-4a1 1 0 011-1h1.586l4.707-4.707C10.923 3.663 12 4.109 12 5v14c0 .891-1.077 1.337-1.707.707L5.586 15z" clip-rule="evenodd" />
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M17 14l2-2m0 0l2-2m-2 2l-2-2m2 2l2 2" />
                </svg>
            `;
        } else {
            volumeBtn.innerHTML = `
                <svg width="24" height="24" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15.536 8.464a5 5 0 010 7.072m2.828-9.9a9 9 0 010 12.728M5.586 15H4a1 1 0 01-1-1v-4a1 1 0 011-1h1.586l4.707-4.707C10.923 3.663 12 4.109 12 5v14c0 .891-1.077 1.337-1.707.707L5.586 15z" />
                </svg>
            `;
        }
    });
}

/**
 * Scroll Animations with Intersection Observer
 */
function initScrollAnimations() {
    const observerOptions = {
        threshold: 0.1,
        rootMargin: '0px 0px -100px 0px'
    };
    
    const observer = new IntersectionObserver(function(entries) {
        entries.forEach(function(entry) {
            if (entry.isIntersecting) {
                entry.target.classList.add('is-visible');
                // Optionally unobserve after animating once
                observer.unobserve(entry.target);
            }
        });
    }, observerOptions);
    
    // Observe all sections and cards
    const elements = document.querySelectorAll('.section-how, .section-capabilities, .section-products, .capability-card, .product-card');
    elements.forEach(function(el) {
        el.classList.add('fade-in-view');
        observer.observe(el);
    });
}

/**
 * Card Hover Interactions
 */
function initCardInteractions() {
    const capabilityCards = document.querySelectorAll('.capability-card');
    
    capabilityCards.forEach(function(card) {
        const video = card.querySelector('.card-video');
        
        if (video) {
            // Ensure video plays on hover
            card.addEventListener('mouseenter', function() {
                video.play().catch(function(error) {
                    console.log('Video play failed:', error);
                });
            });
            
            // Optional: pause when not hovering
            card.addEventListener('mouseleave', function() {
                // Keep playing for seamless experience
                // Uncomment below to pause on leave:
                // video.pause();
            });
        }
    });
}

/**
 * Smooth Scroll for Navigation Links
 */
function initSmoothScroll() {
    document.querySelectorAll('a[href^="#"]').forEach(function(anchor) {
        anchor.addEventListener('click', function(e) {
            e.preventDefault();
            const target = document.querySelector(this.getAttribute('href'));
            if (target) {
                target.scrollIntoView({
                    behavior: 'smooth',
                    block: 'start'
                });
            }
        });
    });
}

// Call smooth scroll init
initSmoothScroll();
