/**
 * config/rules.js — Names of the detection rules, as shown to people.
 */
export const RULES = {
    R001: 'Amount threshold',
    R002: 'Velocity (daily)',
    R003: 'Velocity (hourly)',
    R004: 'High-risk country',
    R005: 'PEP match',
    R006: 'Sanctions match',
    R007: 'New counterparty',
    R008: 'Weekend activity',
    R009: 'Round amount',
    R010: 'Rapid succession',
    SANCTIONS_CUSTOMER: 'Sanctions case',
};

/** Rules worth noticing first: shown with a marker. */
export const MARKED_RULES = new Set(['R004', 'R005', 'R006', 'SANCTIONS_CUSTOMER']);

export const ruleName = (code) => RULES[code] || code;
