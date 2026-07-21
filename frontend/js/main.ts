// KYRO AML Data Generator - Main TypeScript Application
 functionality

interface Customer {
    customer_id: string;
    full_name: string;
    email: string;
    phone: string;
    date_of_birth: string;
    country: string;
    residency_country: string;
    kyc_status: string;
    kyc_last_review: string;
    pep_flag: boolean;
    sanctions_flag: boolean;
    adverse_media_flag: boolean;
    risk_level: string;
    risk_score: number;
    customer_type: string;
    customer_metadata: string;
}

interface Account {
    account_id: string;
    customer_id: string;
    account_type: string;
    account_status: string;
    currency: string;
    balance: number;
    opened_date: string;
    account_metadata: string;
}

interface Transaction {
    transaction_id: string;
    customer_id: string;
    account_id: string;
    transaction_date: string;
    transaction_type: string;
    amount: number;
    currency: string;
    risk_flags: string | null;
    source_system: string;
    meta_counterparty: string | null;
    meta_counterparty_type: string | null;
 n: string | null;
    meta_country: string | null;
    meta_country_code: string;
    meta_destination_country: string | null;
    meta_origin_country: string | null;
    meta_source: string;
}

interface ApiResponse<T> {
    meta?: {
        num_customers: number;
        num_accounts: number;
        num_transactions: number;
        generation_time_seconds: number;
        generated_at: string;
    };
    data?: T;
    customer?: Customer;
    accounts?: Account[];
    transactions?: Transaction[];
    summary?: {
        num_accounts: number;
        num_transactions: number;
    };
    error?: string;
}

class KyroAMLDashboard {
    private baseUrl: string = 'http://localhost:5050/api';
    private currentSection: string = 'dashboard';
    private isLoading: boolean = false;

    constructor() {
        this.init();
    }

    private init(): void {
        this.setupEventListeners();
        this.checkSystemHealth();
        this.updateEstimations();
        this.addToActivityLog('Dashboard initialized');
    }

    private setupEventListeners(): void {
        // Navigation
        document.querySelectorAll('.nav-item').forEach(item => {
            item.addEventListener('click', (e) => {
                const target = e.target as HTMLElement;
                const section = target.dataset.section;
                if (section) {
                    this.switchSection(section);
                }
            });
        });

        // Health Check
        const healthBtn = document.getElementById('check-health');
        healthBtn?.addEventListener('click', () => this.checkSystemHealth());

        // Generator Form
        const customerCountInput = document.getElementById('customer-count') as HTMLInputElement;
        customerCountInput?.addEventListener('input', () => this.updateEstimations());

        const generateJsonBtn = document.getElementById('generate-json');
        generateJsonBtn?.addEventListener('click', () => this.generateJsonData());

        const generateExcelBtn = document.getElementById('generate-excel');
     ner('click', () => this.downloadExcelFile());

        // Preview
        const previewBtn = document.getElementById('preview-customer');
        previewBtn?.addEventListener('click', () => this.generatePreviewCustomer());
    }

    private switchSection(sectionName: string): void {
        // Update navigation
        document.querySelectorAll('.nav-item').forEach(item => {
            item.classList.remove('active');
        });
        documective');

        // Update sections
        document.querySelectorAll('.section').forEach(section => {
            section.classList.remove('active');
        });
        document.getElementById(sectionName)?.classList.add('active');

        this.currentSection = sectionName;
        this.addToActivityLog(`Switched to ${sectionName} section`);
    }

    private async checkSystemHealth(): Promise<void> {
        const statusDot = document.getElementById('status-dot');
        const statusText = mentById('status-text');
        
        if (!statusDot || !statusText) return;

        statusText.textContent = 'Checking...';
        statusDot.className = 'status-dot';

        try {
            const response = await fetch(`${this.baseUrl}/health`);
            const data = await response.json();

            if (data.status === 'ok') {
                statusDot.classList.add('online');
                statusText.textContent = 'System Online';
        success');
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

    private async updateEstimations(): Promise<void> {
        const omerCount = this.getCustomerCount();
        
        try {
            const response = await fetch(`${this.baseUrl}/stats?customers=${customerCount}`);
            const data = await response.json();

            this.updateElement('est-customers', customerCount.toLocaleString());
            this.updateElement('est-accounts', data.estimated_accounts.toLocaleString());
            this.updateElement('est-transactions', data.estimated_transactions.toLocaleString());
        } catch (error) {
    ole.error('Failed to fetch estimations:', error);
        }
    }

    private async generateJsonData(): Promise<void> {
        const customerCount = this.getCustomerCount();
        
        if (!this.validateCustomerCount(customerCount)) return;

        this.showLoading(true);
        this.showProgress(true);
        this.addToActivityLog(`Generating JSON data for ${customerCount} customers`);

        try {
            const response = await fetch(`${this.baseUrl}/generate`, {
         OST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ num_customers: customerCount })
            });

            if (!response.ok) {
                throw new Error('Generation failed');
            }

            const data: ApiResponse<{customers: Customer[], accounts: Account[], transactions: Transaction[]}> = await response.json();
            
            if (data.meta) {
     s(data.meta);
                this.showToast(`Generated ${data.meta.num_customers} customers successfully!`, 'success');
                this.addToActivityLog(`Generated ${data.meta.num_customers} customers, ${data.meta.num_accounts} accounts, ${data.meta.num_transactions} transactions`);
                
                // Switch to dashboard to show results
                this.switchSection('dashboard');
            }

        } catch (error) {
            this.showToast('Failed to generate data.heck the system status.', 'error');
            this.addToActivityLog('Data generation failed');
        } finally {
            this.showLoading(false);
            this.showProgress(false);
        }
    }

    private async downloadExcelFile(): Promise<void> {
        const customerCount = this.getCustomerCount();
        const saveToDisc = (document.getElementById('save-to-disk') as HTMLInputElement)?.checked ?? true;
        
        if (!this.validateCustomerCount(customerCount)) return;

        thiowLoading(true);
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

    private async generatePreviewCustomer(): Promise<void> {
        const customerIndex = parseInt((document.getElementById('customer-index') as HTMLInputElement)?.value || '1');
        
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

            const data: ApiResponse<any> = await response.json();
            this.displayPreviewData(data);
            this.showToast('Customer preview generated successfully!', 'success');
            this.addToActivityLog('Customer preview generated');

        } catch (error) {
            this.showToast('Failed to r preview', 'error');
            this.addToActivityLog('Customer preview generation failed');
        } finally {
            this.showLoading(false);
        }
    }

    private displayPreviewData(data: ApiResponse<any>): void {
        const container = document.getElementById('preview-content');
        if (!container || !data.customer) return;

        const html = `
            <div class="preview-section">
                <h4>Customer Information</h4>
                ${this.cre, 'customer')}
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

    private createDataTable(data: any[], type: string): string {
        if (!data || data.length === 0) return '<p>No data available</p>';

        const keys = Object.keys(data[0]);
        const displayKeys = type === 'customer' ? keys.slice(0, 6) : 
                          type === 'account' ? keys.slice(0, 6) : 
                          keys.slice(0, 7);

        let html = '<table class="data-table"><thead><tr>';
        displayKeys.forEach(key => {
        place(/_/g, ' ').toUpperCase()}</th>`;
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

    private getCustomerCount(): number {
        const input = document.getElementById('customer-count') as HTMLInputElement;
        return parseInt(input?.value || '100');
    }

    private validateCustomerCount(count: number): boolean {
        if (count < 1 || count > 10000) {
            this.showToast('Customer count must be between 1 and 10,000', 'warning');
            return false;
        }
        return true;
    }

    private updateDashboardStats(meta: any): void {
        this.updateElement('total-customers', meta.num_customers.toLocaleString());
        this.updateElement('total-accounts', meta.num_accounts.toLocaleString());
        this.updateElement('total-transactions', meta.num_transactions.toLocaleString());
        this.updateElement('generation-time', `${meta.generation_time_seconds}s`);
    }

    private updateElement(id: string, value: string): void {
        const element = document.getElementById(id);
        if (element) {
            element.textContent = value;
        }
    }

    private showLoading(show: boolean): void {
        const overlay = document.getElementById('loading-overlay');
        if (overlay) {
            overlay.classList.toggle('hidden', !show);
        }
        this.isLoading = show;
    }

    private showProgress(show: boolean): void {
        const container = document.getElementById('progress-container');
        const fill = document.getElementById('progress-fill');
        
        if (container && fill) {
            container.classList.toggle('hidden', !show);
            if (show) {
                // Simulate progress
                let progress = 0;
                const interval = setInterval(() => {
                    progress += Math.random() * 20;
                    if (pprogress = 90;
                    fill.style.width = `${progress}%`;
                    
                    if (!this.isLoading) {
                        fill.style.width = '100%';
                        setTimeout(() => clearInterval(interval), 500);
                    }
                }, 200);
            }
        }
    }

    private showToast(message: string, type: 'success' | 'error' | 'warning' = 'success'): void {
        const container = document.getElementById('toast-container');
        if (!container) return;

        const toast = document.createElement('div');
        toast.className = `toast ${type}`;
        toast.innerHTML = `
            <p>${message}</p>
        `;

        container.appendChild(toast);

        // Auto remove after 5 seconds
        setTimeout(() => {
            toast.style.opacity = '0';
            setTimeout(() => {
                if (container.contains(toast)) {
                    container.removeChild(toast);
                }
            }, 300);
        00);
    }

    private addToActivityLog(message: string): void {
        const log = document.getElementById('activity-log');
        if (!log) return;

        const timestamp = new Date().toLocaleTimeString();
        const item = document.createElement('p');
        item.className = 'activity-item';
        item.textContent = `${timestamp}: ${message}`;

        log.insertBefore(item, log.firstChild);

        // Keep only last 10 items
        while (log.children.length > 10) {
        d(log.lastChild!);
        }
    }
}

// Initialize the dashboard when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    new KyroAMLDashboard();
});

// Export for potential external use
export default KyroAMLDashboard;