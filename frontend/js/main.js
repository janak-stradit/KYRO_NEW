// KYRO AML Data Generator - Main JavaScript Application
// Orange-themed UI with modern dashboard functionality

class KyroAMLDashboard {
    constructor() {
        this.baseUrl = 'http://localhost:5050/api';
        this.currentSection = 'features';
        this.isLoading = false;
        this.init();
    }

    init() {
        this.setupEventListeners();
        this.setupScrollEffects();
        this.animateHeroStats();
        this.checkSystemHealth();
        this.updateEstimations();
        this.addToActivityLog('Dashboard initialized');
    }

    setupEventListeners() {
        // Navigation
        document.querySelectorAll('.nav-item').forEach(item => {
            item.addEventListener('click', (e) => {
                const section = e.target.dataset.section;
                if (section) {
                    this.switchSection(section);
                }
            });
        });

        // Hero actions
        document.getElementById('launch-dashboard')?.addEventListener('click', () => {
            this.switchSection('dashboard');
        });

        document.getElementById('view-demo')?.addEventListener('click', () => {
            this.switchSection('preview');
        });

        document.getElementById('header-demo')?.addEventListener('click', () => {
            this.switchSection('preview');
        });

        document.getElementById('header-launch')?.addEventListener('click', () => {
            this.switchSection('dashboard');
        });

        // Health Check
        const healthBtn = document.getElementById('check-health');
        healthBtn?.addEventListener('click', () => this.checkSystemHealth());

        // Generator Form
        const customerCountInput = document.getElementById('customer-count');
        customerCountInput?.addEventListener('input', () => this.updateEstimations());

        const generateJsonBtn = document.getElementById('generate-json');
        generateJsonBtn?.addEventListener('click', () => this.generateJsonData());

        const generateExcelBtn = document.getElementById('generate-excel');
        generateExcelBtn?.addEventListener('click', () => this.downloadExcelFile());

        // Preview
        const previewBtn = document.getElementById('preview-customer');
        previewBtn?.addEventListener('click', () => this.generatePreviewCustomer());

        // Feature cards animation
        this.setupFeatureCardsAnimation();
    }

    setupScrollEffects() {
        let lastScrollY = window.scrollY;
        const header = document.getElementById('main-header');

        window.addEventListener('scroll', () => {
            const scrollY = window.scrollY;
            
            // Show/hide floating header
            if (scrollY > 100) {
                header?.classList.add('floating');
            } else {
                header?.classList.remove('floating');
            }

            lastScrollY = scrollY;
        });
    }

    setupFeatureCardsAnimation() {
        const observer = new IntersectionObserver((entries) => {
            entries.forEach(entry => {
                if (entry.isIntersecting) {
                    const delay = parseInt(entry.target.dataset.delay) || 0;
                    setTimeout(() => {
                        entry.target.style.opacity = '1';
                        entry.target.style.transform = 'translateY(0)';
                    }, delay);
                }
            });
        }, {
            threshold: 0.1,
            rootMargin: '0px 0px -50px 0px'
        });

        document.querySelectorAll('.feature-card').forEach(card => {
            card.style.opacity = '0';
            card.style.transform = 'translateY(30px)';
            card.style.transition = 'all 0.6s ease';
            observer.observe(card);
        });
    }

    animateHeroStats() {
        const animateNumber = (element, targetValue, duration = 2000) => {
            if (!element) return;
            
            const startValue = 0;
            const startTime = performance.now();
            
            const updateNumber = (currentTime) => {
                const elapsed = currentTime - startTime;
                const progress = Math.min(elapsed / duration, 1);
                
                // Easing function
                const easeOut = 1 - Math.pow(1 - progress, 3);
                const currentValue = Math.floor(startValue + (targetValue * easeOut));
                
                if (element.id === 'hero-compliance') {
                    element.textContent = `${(currentValue / 10).toFixed(1)}%`;
                } else if (currentValue >= 1000000) {
                    element.textContent = `${(currentValue / 1000000).toFixed(1)}M+`;
                } else if (currentValue >= 1000) {
                    element.textContent = `${(currentValue / 1000).toFixed(0)}K+`;
                } else {
                    element.textContent = `${currentValue.toLocaleString()}+`;
                }
                
                if (progress < 1) {
                    requestAnimationFrame(updateNumber);
                }
            };
            
            requestAnimationFrame(updateNumber);
        };

        // Animate stats when hero is visible
        const heroObserver = new IntersectionObserver((entries) => {
            entries.forEach(entry => {
                if (entry.isIntersecting) {
                    setTimeout(() => {
                        animateNumber(document.getElementById('hero-customers'), 1200000);
                        animateNumber(document.getElementById('hero-transactions'), 50000000);
                        animateNumber(document.getElementById('hero-compliance'), 999);
                    }, 500);
                    heroObserver.disconnect();
                }
            });
        });

        const heroSection = document.querySelector('.hero-section');
        if (heroSection) {
            heroObserver.observe(heroSection);
        }
    }

    switchSection(sectionName) {
        // Update navigation
        document.querySelectorAll('.nav-item').forEach(item => {
            item.classList.remove('active');
        });
        document.querySelector(`[data-section="${sectionName}"]`)?.classList.add('active');

        // Update sections
        document.querySelectorAll('.section').forEach(section => {
            section.classList.remove('active');
        });
        document.getElementById(sectionName)?.classList.add('active');

        this.currentSection = sectionName;
        this.addToActivityLog(`Switched to ${sectionName} section`);
    }

    async checkSystemHealth() {
        const statusDot = document.getElementById('status-dot');
        const statusText = document.getElementById('status-text');
        
        if (!statusDot || !statusText) return;

        statusText.textContent = 'Checking...';
        statusDot.className = 'status-dot';

        try {
            const response = await fetch(`${this.baseUrl}/health`);
            const data = await response.json();

            if (data.status === 'ok') {
                statusDot.classList.add('online');
                statusText.textContent = 'System Online';
                this.showToast('System is healthy and running', 'success');
                this.addToActivityLog('Health check passed');
            } else {
                throw new Error('Unexpected status');
            }
        } catch (error) {
            statusDot.classList.add('offline');
            statusText.textContent = 'System Offline';
            this.showToast('Failed to connect to backend service', 'error');
            this.addToActivityLog('Health check failed');
        }
    }

    async updateEstimations() {
        const customerCount = this.getCustomerCount();
        
        try {
            const response = await fetch(`${this.baseUrl}/stats?customers=${customerCount}`);
            const data = await response.json();

            this.updateElement('est-customers', customerCount.toLocaleString());
            this.updateElement('est-accounts', data.estimated_accounts.toLocaleString());
            this.updateElement('est-transactions', data.estimated_transactions.toLocaleString());
        } catch (error) {
            console.error('Failed to fetch estimations:', error);
        }
    }

    async generateJsonData() {
        const customerCount = this.getCustomerCount();
        
        if (!this.validateCustomerCount(customerCount)) return;

        this.showLoading(true);
        this.showProgress(true);
        this.addToActivityLog(`Generating JSON data for ${customerCount} customers`);

        try {
            const response = await fetch(`${this.baseUrl}/generate`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ num_customers: customerCount })
            });

            if (!response.ok) {
                throw new Error('Generation failed');
            }

            const data = await response.json();
            
            if (data.meta) {
                this.updateDashboardStats(data.meta);
                this.showToast(`Generated ${data.meta.num_customers} customers successfully!`, 'success');
                this.addToActivityLog(`Generated ${data.meta.num_customers} customers, ${data.meta.num_accounts} accounts, ${data.meta.num_transactions} transactions`);
                
                // Switch to dashboard to show results
                this.switchSection('dashboard');
            }

        } catch (error) {
            this.showToast('Failed to generate data. Please check the system status.', 'error');
            this.addToActivityLog('Data generation failed');
        } finally {
            this.showLoading(false);
            this.showProgress(false);
        }
    }

    async downloadExcelFile() {
        const customerCount = this.getCustomerCount();
        const saveToDisc = document.getElementById('save-to-disk')?.checked ?? true;
        
        if (!this.validateCustomerCount(customerCount)) return;

        this.showLoading(true);
        this.addToActivityLog(`Downloading Excel file for ${customerCount} customers`);

        try {
            const response = await fetch(`${this.baseUrl}/generate/download`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ 
                    num_customers: customerCount,
                    save_to_disk: saveToDisc 
                })
            });

            if (!response.ok) {
                throw new Error('Download failed');
            }

            // Create download link
            const blob = await response.blob();
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            const timestamp = new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19);
            a.href = url;
            a.download = `aml_dataset_${customerCount}c_${timestamp}.xlsx`;
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            window.URL.revokeObjectURL(url);

            this.showToast('Excel file downloaded successfully!', 'success');
            this.addToActivityLog('Excel file downloaded');

        } catch (error) {
            this.showToast('Failed to download Excel file', 'error');
            this.addToActivityLog('Excel download failed');
        } finally {
            this.showLoading(false);
        }
    }

    async generatePreviewCustomer() {
        const customerIndex = parseInt(document.getElementById('customer-index')?.value || '1');
        
        this.showLoading(true);
        this.addToActivityLog(`Generating preview for customer ${customerIndex}`);

        try {
            const response = await fetch(`${this.baseUrl}/generate/single-customer`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ customer_index: customerIndex })
            });

            if (!response.ok) {
                throw new Error('Preview generation failed');
            }

            const data = await response.json();
            this.displayPreviewData(data);
            this.showToast('Customer preview generated successfully!', 'success');
            this.addToActivityLog('Customer preview generated');

        } catch (error) {
            this.showToast('Failed to generate customer preview', 'error');
            this.addToActivityLog('Customer preview generation failed');
        } finally {
            this.showLoading(false);
        }
    }

    displayPreviewData(data) {
        const container = document.getElementById('preview-content');
        if (!container || !data.customer) return;

        const html = `
            <div class="preview-section">
                <h4>Customer Information</h4>
                ${this.createDataTable([data.customer], 'customer')}
            </div>
            
            <div class="preview-section">
                <h4>Accounts (${data.accounts?.length || 0})</h4>
                ${data.accounts ? this.createDataTable(data.accounts.slice(0, 3), 'account') : '<p>No accounts found</p>'}
                ${(data.accounts?.length || 0) > 3 ? `<p class="text-center" style="margin-top: 1rem; color: var(--medium-gray);">... and ${(data.accounts?.length || 0) - 3} more accounts</p>` : ''}
            </div>
            
            <div class="preview-section">
                <h4>Recent Transactions (${data.transactions?.length || 0})</h4>
                ${data.transactions ? this.createDataTable(data.transactions.slice(0, 5), 'transaction') : '<p>No transactions found</p>'}
                ${(data.transactions?.length || 0) > 5 ? `<p class="text-center" style="margin-top: 1rem; color: var(--medium-gray);">... and ${(data.transactions?.length || 0) - 5} more transactions</p>` : ''}
            </div>
        `;

        container.innerHTML = html;
    }

    createDataTable(data, type) {
        if (!data || data.length === 0) return '<p>No data available</p>';

        const keys = Object.keys(data[0]);
        const displayKeys = type === 'customer' ? keys.slice(0, 6) : 
                          type === 'account' ? keys.slice(0, 6) : 
                          keys.slice(0, 7);

        let html = '<table class="data-table"><thead><tr>';
        displayKeys.forEach(key => {
            html += `<th>${key.replace(/_/g, ' ').toUpperCase()}</th>`;
        });
        html += '</tr></thead><tbody>';

        data.forEach(row => {
            html += '<tr>';
            displayKeys.forEach(key => {
                let value = row[key];
                if (typeof value === 'boolean') {
                    value = value ? '✓' : '✗';
                } else if (typeof value === 'number') {
                    value = value.toLocaleString();
                } else if (value === null || value === undefined) {
                    value = '-';
                }
                html += `<td>${String(value).length > 30 ? String(value).substring(0, 30) + '...' : value}</td>`;
            });
            html += '</tr>';
        });

        html += '</tbody></table>';
        return html;
    }

    getCustomerCount() {
        const input = document.getElementById('customer-count');
        return parseInt(input?.value || '100');
    }

    validateCustomerCount(count) {
        if (count < 1 || count > 10000) {
            this.showToast('Customer count must be between 1 and 10,000', 'warning');
            return false;
        }
        return true;
    }

    updateDashboardStats(meta) {
        this.updateElement('total-customers', meta.num_customers.toLocaleString());
        this.updateElement('total-accounts', meta.num_accounts.toLocaleString());
        this.updateElement('total-transactions', meta.num_transactions.toLocaleString());
        this.updateElement('generation-time', `${meta.generation_time_seconds}s`);
    }

    updateElement(id, value) {
        const element = document.getElementById(id);
        if (element) {
            element.textContent = value;
        }
    }

    showLoading(show) {
        const overlay = document.getElementById('loading-overlay');
        if (overlay) {
            overlay.classList.toggle('hidden', !show);
        }
        this.isLoading = show;
    }

    showProgress(show) {
        const container = document.getElementById('progress-container');
        const fill = document.getElementById('progress-fill');
        
        if (container && fill) {
            container.classList.toggle('hidden', !show);
            if (show) {
                // Simulate progress
                let progress = 0;
                const interval = setInterval(() => {
                    progress += Math.random() * 20;
                    if (progress > 90) progress = 90;
                    fill.style.width = `${progress}%`;
                    
                    if (!this.isLoading) {
                        fill.style.width = '100%';
                        setTimeout(() => clearInterval(interval), 500);
                    }
                }, 200);
            }
        }
    }

    showToast(message, type = 'success') {
        const container = document.getElementById('toast-container');
        if (!container) return;

        const toast = document.createElement('div');
        toast.className = `toast ${type}`;
        toast.innerHTML = `<p>${message}</p>`;

        container.appendChild(toast);

        // Auto remove after 5 seconds
        setTimeout(() => {
            toast.style.opacity = '0';
            setTimeout(() => {
                if (container.contains(toast)) {
                    container.removeChild(toast);
                }
            }, 300);
        }, 5000);
    }

    addToActivityLog(message) {
        const log = document.getElementById('activity-log');
        if (!log) return;

        const timestamp = new Date().toLocaleTimeString();
        const item = document.createElement('p');
        item.className = 'activity-item';
        item.textContent = `${timestamp}: ${message}`;

        log.insertBefore(item, log.firstChild);

        // Keep only last 10 items
        while (log.children.length > 10) {
            log.removeChild(log.lastChild);
        }
    }
}

// Initialize the dashboard when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    new KyroAMLDashboard();
});