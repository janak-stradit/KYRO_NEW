// This code adds triggered rules to generateCustomerCaseDetail function
// Add this code after line 737 (after const statuses = ...)

        // Generate triggered rules (R001-R010)
        const allRules = [
            { id: 'R001', name: 'Amount Threshold', severity: 'MEDIUM', description: 'Transaction amount > $10,000' },
            { id: 'R002', name: 'Velocity Daily', severity: 'MEDIUM', description: 'More than 5 transactions in 24 hours' },
            { id: 'R003', name: 'Velocity Hourly', severity: 'LOW', description: 'More than 3 transactions in 1 hour' },
            { id: 'R004', name: 'High Risk Country', severity: 'HIGH', description: 'Transaction in sanctioned jurisdiction' },
            { id: 'R005', name: 'PEP Match', severity: 'HIGH', description: 'Politically Exposed Person identified' },
            { id: 'R006', name: 'Sanctions Match', severity: 'CRITICAL', description: 'Customer on sanctions list' },
            { id: 'R007', name: 'New Counterparty', severity: 'LOW', description: 'First-time transaction recipient' },
            { id: 'R008', name: 'Weekend Activity', severity: 'LOW', description: 'Transaction on Saturday/Sunday' },
            { id: 'R009', name: 'Round Amount', severity: 'MEDIUM', description: 'Suspicious round amount detected' },
            { id: 'R010', name: 'Rapid Succession', severity: 'HIGH', description: 'Multiple transactions within 60 seconds' }
        ];
        
        // Randomly select 2-4 triggered rules
        const triggeredCount = Math.floor(Math.random() * 3) + 2;
        const triggeredRules = [];
        const selectedIndices = new Set();
        
        while (triggeredRules.length < triggeredCount) {
            const idx = Math.floor(Math.random() * allRules.length);
            if (!selectedIndices.has(idx)) {
                selectedIndices.add(idx);
                triggeredRules.push(allRules[idx]);
            }
        }

// Then add triggeredRules: triggeredRules to the return object before the closing };


// Update formatCaseDetailsHTML function to add this section after Risk Flags:

                <div class="kc-case-section">
                    <div class="kc-case-label">🚨 Triggered Rules:</div>
                    ${caseDetails.triggeredRules && caseDetails.triggeredRules.length > 0 
                        ? caseDetails.triggeredRules.map(rule => {
                            const severityColors = {
                                'LOW': '#10b981',
                                'MEDIUM': '#f59e0b',
                                'HIGH': '#ef4444',
                                'CRITICAL': '#dc2626'
                            };
                            const color = severityColors[rule.severity] || '#6b7280';
                            return `
                                <div style="margin-bottom: 8px; padding: 6px; background: #f9fafb; border-left: 3px solid ${color}; border-radius: 4px;">
                                    <strong>${rule.id} - ${rule.name}</strong>
                                    <span style="float: right; font-size: 0.85em; color: ${color}; font-weight: 600;">${rule.severity}</span><br>
                                    <span style="font-size: 0.9em; color: #6b7280;">${rule.description}</span>
                                </div>
                            `;
                        }).join('')
                        : '- No rules triggered'
                    }
                </div>
