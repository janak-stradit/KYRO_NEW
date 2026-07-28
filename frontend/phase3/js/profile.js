/**
 * KYRO Profile - User Profile Management Implementation
 */

const Profile = {
    async init() {
        await this.loadProfile();
    },
    
    async loadProfile() {
        showLoading("#mainContent", "Retrieving profile details...");
        
        try {
            // Get logged-in user profile from FastAPI backend
            const user = await API.get("/auth/me");
            
            const joinDate = user.created_at ? formatDate(user.created_at) : "N/A";
            const lastLogin = user.last_login ? formatDateTime(user.last_login) : "N/A";
            
            // Format name for initials
            const name = user.full_name || user.username || "Analyst";
            const initials = name.split(" ").map(n => n[0]).join("").toUpperCase().substring(0, 2);
            
            const html = `
                <div class="dashboard-header mb-4">
                    <div class="container-fluid">
                        <h1 class="dashboard-title">User Account & Security</h1>
                        <p class="dashboard-subtitle">Manage your credentials, view assigned roles, and inspect recent login sessions</p>
                    </div>
                </div>
                
                <div class="row">
                    <!-- Left Column: User Card -->
                    <div class="col-lg-4 mb-4">
                        <div class="card border-0 shadow-sm text-center py-4 px-3" style="border-radius: 16px; background: linear-gradient(to bottom, #ffffff, #f9fafb);">
                            <div class="d-flex justify-content-center mb-3">
                                <div class="rounded-circle d-flex align-items-center justify-content-center text-white shadow-sm" style="width: 100px; height: 100px; font-size: 2.5rem; font-weight: 700; background: linear-gradient(135deg, #FF8C42, #ff6b35);">
                                    ${initials}
                                </div>
                            </div>
                            <h4 class="fw-bold mb-1 text-dark">${user.full_name || user.username}</h4>
                            <p class="text-muted mb-3">@${user.username}</p>
                            <div class="d-inline-block px-3 py-1 rounded-pill bg-light text-primary border mb-4" style="font-size: 0.85rem; font-weight: 600;">
                                <i class="fas fa-shield-alt me-1"></i> ${user.role}
                            </div>
                            
                            <div class="border-top pt-3 text-start small">
                                <div class="d-flex justify-content-between mb-2">
                                    <span class="text-muted">Account Status:</span>
                                    <span class="badge bg-success-subtle text-success border border-success-subtle">Active</span>
                                </div>
                                <div class="d-flex justify-content-between mb-2">
                                    <span class="text-muted">Member Since:</span>
                                    <span class="fw-semibold text-dark">${joinDate}</span>
                                </div>
                                <div class="d-flex justify-content-between">
                                    <span class="text-muted">Last Active:</span>
                                    <span class="fw-semibold text-dark">${formatRelativeTime(user.last_login) || 'Just now'}</span>
                                </div>
                            </div>
                        </div>
                    </div>
                    
                    <!-- Right Column: Profile details form -->
                    <div class="col-lg-8 mb-4">
                        <div class="card border-0 shadow-sm h-100" style="border-radius: 16px;">
                            <div class="card-header bg-white py-3 border-0">
                                <h5 class="card-title fw-bold mb-0 text-dark">Profile Details & Session Info</h5>
                            </div>
                            <div class="card-body">
                                <div class="row g-3">
                                    <div class="col-md-6">
                                        <label class="form-label fw-semibold text-muted small">Full Name</label>
                                        <div class="form-control bg-light border-0 py-2 fw-semibold text-dark">${user.full_name || 'N/A'}</div>
                                    </div>
                                    <div class="col-md-6">
                                        <label class="form-label fw-semibold text-muted small">Username</label>
                                        <div class="form-control bg-light border-0 py-2 font-monospace text-dark">${user.username}</div>
                                    </div>
                                    <div class="col-md-12">
                                        <label class="form-label fw-semibold text-muted small">Email Address</label>
                                        <div class="form-control bg-light border-0 py-2 text-dark">${user.email}</div>
                                    </div>
                                    <div class="col-md-6">
                                        <label class="form-label fw-semibold text-muted small">Security Role</label>
                                        <div class="form-control bg-light border-0 py-2 text-dark font-monospace">${user.role}</div>
                                    </div>
                                    <div class="col-md-6">
                                        <label class="form-label fw-semibold text-muted small">Last Login Timestamp</label>
                                        <div class="form-control bg-light border-0 py-2 text-dark font-monospace">${lastLogin}</div>
                                    </div>
                                </div>
                                
                                <div class="mt-5 border-top pt-4">
                                    <h6 class="fw-bold mb-3 text-dark"><i class="fas fa-lock me-2 text-warning"></i> Role Permissions Overview</h6>
                                    <div class="row g-2">
                                        <div class="col-md-6">
                                            <div class="p-2 border rounded bg-light d-flex align-items-center gap-2 small">
                                                <i class="fas fa-check-circle text-success"></i>
                                                <span>Audit Risk Stream Logs</span>
                                            </div>
                                        </div>
                                        <div class="col-md-6">
                                            <div class="p-2 border rounded bg-light d-flex align-items-center gap-2 small">
                                                <i class="fas fa-check-circle text-success"></i>
                                                <span>Preview Anomaly Models</span>
                                            </div>
                                        </div>
                                        <div class="col-md-6">
                                            <div class="p-2 border rounded bg-light d-flex align-items-center gap-2 small">
                                                ${user.role === 'COMPLIANCE_OFFICER' || user.role === 'ADMIN' ? 
                                                    '<i class="fas fa-check-circle text-success"></i>' : 
                                                    '<i class="fas fa-ban text-muted"></i>'}
                                                <span class="${user.role === 'COMPLIANCE_OFFICER' || user.role === 'ADMIN' ? 'text-dark' : 'text-muted text-decoration-line-through'}">Resolve Compliance Alerts</span>
                                            </div>
                                        </div>
                                        <div class="col-md-6">
                                            <div class="p-2 border rounded bg-light d-flex align-items-center gap-2 small">
                                                ${user.role === 'ADMIN' ? 
                                                    '<i class="fas fa-check-circle text-success"></i>' : 
                                                    '<i class="fas fa-ban text-muted"></i>'}
                                                <span class="${user.role === 'ADMIN' ? 'text-dark' : 'text-muted text-decoration-line-through'}">Trigger ML Retraining Pipeline</span>
                                            </div>
                                        </div>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            `;
            
            $("#mainContent").html(html);
            
        } catch (error) {
            console.error("Profile load error:", error);
            showToast("error", "Failed to retrieve user profile data.");
        }
    }
};

// Export to window
window.Profile = Profile;
