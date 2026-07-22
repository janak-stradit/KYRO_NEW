/**
 * KYRO Settings - Settings & Administration Page Implementation
 */

const Settings = {
    init() {
        this.loadSettings();
    },
    
    async loadSettings() {
        showLoading("#mainContent", "Connecting to ML registry...");
        
        try {
            // Fetch ML model registry status from FastAPI
            const models = await API.get("/ml/models");
            
            const html = `
                <div class="dashboard-header mb-4">
                    <div class="container-fluid d-flex justify-content-between align-items-center flex-wrap gap-2">
                        <div>
                            <h1 class="dashboard-title">System Settings & Registry</h1>
                            <p class="dashboard-subtitle">Monitor ML model versions, configure A/B challenger tests, and trigger training pipelines</p>
                        </div>
                    </div>
                </div>
                
                <div class="row">
                    <!-- ML Model Registry Panel -->
                    <div class="col-lg-8 mb-4">
                        <div class="card h-100">
                            <div class="card-header bg-white py-3 d-flex justify-content-between align-items-center">
                                <h5 class="card-title fw-bold mb-0">Machine Learning Model Directory</h5>
                                <button class="btn btn-sm btn-outline-primary" onclick="Settings.loadSettings()">
                                    <i class="fas fa-sync-alt me-1"></i>Refresh Registry
                                </button>
                            </div>
                            <div class="card-body">
                                <div class="table-responsive">
                                    <table class="table align-middle">
                                        <thead>
                                            <tr>
                                                <th>Model Name</th>
                                                <th>Active Version</th>
                                                <th>Candidate Version</th>
                                                <th>Candidate Traffic</th>
                                                <th>All Versions</th>
                                            </tr>
                                        </thead>
                                        <tbody>
                                            ${models.length === 0 ? `
                                                <tr><td colspan="5" class="text-center py-4 text-muted">No models cataloged in the registry.</td></tr>
                                            ` : models.map(m => `
                                                <tr>
                                                    <td><strong>${m.name}</strong></td>
                                                    <td><span class="badge bg-success">${m.active_version || 'None'}</span></td>
                                                    <td><span class="badge bg-warning text-dark">${m.candidate_version || 'None'}</span></td>
                                                    <td><strong>${m.candidate_traffic_pct}%</strong></td>
                                                    <td>
                                                        <small class="text-muted font-monospace">${(m.available_versions || []).join(', ') || 'None'}</small>
                                                    </td>
                                                </tr>
                                            `).join('')}
                                        </tbody>
                                    </table>
                                </div>
                            </div>
                        </div>
                    </div>
                    
                    <!-- Retraining Pipeline Config -->
                    <div class="col-lg-4 mb-4">
                        <div class="card h-100">
                            <div class="card-header bg-white py-3">
                                <h5 class="card-title fw-bold mb-0">Retraining Pipeline Launcher</h5>
                            </div>
                            <div class="card-body">
                                <p class="text-muted small">Launch a background pipeline job to train XGBoost/Random Forest models on recent ledgers.</p>
                                <form id="trainPipelineForm">
                                    <div class="mb-3">
                                        <label class="form-label fw-semibold">Register as Candidate Challenger</label>
                                        <div class="form-check form-switch">
                                            <input class="form-check-input" type="checkbox" id="trainAsCandidate" checked>
                                            <label class="form-check-label" for="trainAsCandidate">Deploy to challenger channel</label>
                                        </div>
                                    </div>
                                    <div class="mb-3">
                                        <label class="form-label fw-semibold">Challenger Traffic Allocation</label>
                                        <div class="input-group input-group-sm">
                                            <input type="number" class="form-control" id="trainTrafficPct" min="0" max="100" value="10">
                                            <span class="input-group-text">%</span>
                                        </div>
                                    </div>
                                    <div class="mb-3">
                                        <label class="form-label fw-semibold">Dataset Cap Limit</label>
                                        <input type="number" class="form-control form-control-sm" id="trainLimit" min="100" max="100000" value="5000">
                                    </div>
                                    <div class="d-grid mt-4">
                                        <button type="button" class="btn btn-warning" onclick="Settings.triggerRetraining()">
                                            <i class="fas fa-cog fa-spin me-2"></i>Launch Pipeline Job
                                        </button>
                                    </div>
                                </form>
                            </div>
                        </div>
                    </div>
                </div>
            `;
            
            $("#mainContent").html(html);
            
        } catch (error) {
            console.error("Settings load error:", error);
            showToast("error", "Failed to contact classifier registry services.");
        }
    },
    
    async triggerRetraining() {
        const asCandidate = $("#trainAsCandidate").is(":checked");
        const traffic = parseInt($("#trainTrafficPct").val()) || 10;
        const limit = parseInt($("#trainLimit").val()) || 5000;
        
        try {
            showGlobalLoading("Spawning training processes...");
            
            // Post train endpoint
            const res = await API.post("/ml/train", {
                as_candidate: asCandidate,
                candidate_traffic_pct: traffic,
                limit: limit,
                run_async: true // run in Celery background worker
            });
            
            showToast("success", `Training job successfully queued in backend. Task ID: ${res.task_id}`);
            
        } catch (error) {
            console.error("Retraining trigger error:", error);
            showToast("error", "Failed to invoke retraining pipeline.");
        } finally {
            hideLoading();
        }
    }
};

window.Settings = Settings;
