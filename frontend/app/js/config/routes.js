/**
 * config/routes.js — Every page: its address, title, who may open it, and where it sits in the navigation.
 *
 * `legacy` marks a page not rebuilt yet: it shows a placeholder that links to the same page in the current app.
 */
const placeholder = (legacy) => () => import('../pages/placeholder/placeholder.js').then((m) => ({ default: m.forLegacy(legacy) }));

export const ROUTES = [
    { name: 'dashboard', path: '/', title: 'Dashboard', nav: 'Dashboard', load: placeholder('/dashboard') },
    { name: 'periodic-reviews', path: '/periodic-reviews', title: 'Periodic Reviews', nav: 'Periodic Reviews',
        permission: ['customers.view_all'], load: placeholder('/periodic-reviews') },
    { name: 'cases', path: '/cases', title: 'Review Cases', nav: 'Review Cases', permission: ['cases.view'],
        load: () => import('../pages/cases/cases.js') },
    { name: 'case', path: '/cases/:id', title: 'Case', permission: ['cases.view'], navParent: 'cases',
        load: placeholder('/case') },
    { name: 'patterns', path: '/patterns', title: 'Patterns', nav: 'Patterns', permission: ['cases.view'], load: placeholder('/patterns') },
    { name: 'regulations', path: '/regulations', title: 'Regulations', nav: 'Regulations', load: placeholder('/regulations') },
    { name: 'rules', path: '/rules', title: 'Rules', nav: 'Rules', permission: ['rules.propose', 'rules.approve', 'alerts.baseline'],
        load: placeholder('/rules') },
    { name: 'feeds', path: '/feeds', title: 'Data Feeds', nav: 'Data Feeds', permission: ['feeds.load'], load: placeholder('/feeds') },
    { name: 'process', path: '/process', title: 'How KYRO works', nav: 'How it works', permission: ['users.manage'],
        load: placeholder('/process') },
    { name: 'admin', path: '/admin', title: 'Administration', nav: 'Administration',
        permission: ['users.manage', 'audit.read', 'sar.grant_access', 'assignment.manage'], load: placeholder('/admin') },
    { name: 'profile', path: '/profile', title: 'My profile', load: placeholder('/profile') },
];
