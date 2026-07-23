/**
 * KYRO Real-Time Updates System
 * Handles Server-Sent Events (SSE) for live alerts and data updates
 */

const RealTime = {
    eventSource: null,
    reconnectAttempts: 0,
    maxReconnectAttempts: 5,
    reconnectDelay: 5000,
    isConnected: false,
    
    init() {
        this.connect();
        this.setupHeartbeat();
        
        // Reconnect on page visibility change
        document.addEventListener('visibilitychange', () => {
            if (!document.hidden && !this.isConnected) {
                this.connect();
            }
        });
    },
    
    connect() {
        if (this.eventSource) {
            this.disconnect();
        }
        
        const token = Auth.getToken();
        if (!token) {
            console.warn("No auth token available for real-time connection");
            return;
        }
        
        try {
            console.log("🔄 Connecting to real-time updates...");
            
            const baseUrl = (window.API && API.baseUrl) 
                ? API.baseUrl 
                : (window.Auth && Auth.getApiUrl ? Auth.getApiUrl("/api/v1") : "/api/v1");
            const url = `${baseUrl}/alerts/stream?token=${encodeURIComponent(token)}`;
            this.eventSource = new EventSource(url);
            
            this.eventSource.onopen = (event) => {
                console.log("✅ Real-time connection established");
                this.isConnected = true;
                this.reconnectAttempts = 0;
                this.updateConnectionStatus("connected");
            };
            
            this.eventSource.onmessage = (event) => {
                try {
                    const data = JSON.parse(event.data);
                    this.handleMessage(data);
                } catch (error) {
                    console.error("Error parsing SSE message:", error);
                }
            };
            
            this.eventSource.onerror = (error) => {
                console.error("❌ Real-time connection error:", error);
                this.isConnected = false;
                this.updateConnectionStatus("disconnected");
                
                if (this.eventSource.readyState === EventSource.CLOSED) {
                    this.handleReconnect();
                }
            };
            
            // Handle different message types
            this.eventSource.addEventListener('alert', (event) => {
                const alert = JSON.parse(event.data);
                this.handleNewAlert(alert);
            });
            
            this.eventSource.addEventListener('alert_update', (event) => {
                const update = JSON.parse(event.data);
                this.handleAlertUpdate(update);
            });
            
            this.eventSource.addEventListener('system_status', (event) => {
                const status = JSON.parse(event.data);
                this.handleSystemStatus(status);
            });
            
            this.eventSource.addEventListener('heartbeat', (event) => {
                // Keep connection alive
                this.lastHeartbeat = Date.now();
            });
            
        } catch (error) {
            console.error("Failed to establish real-time connection:", error);
            this.handleReconnect();
        }
    },
    
    disconnect() {
        if (this.eventSource) {
            console.log("🔌 Disconnecting real-time updates");
            this.eventSource.close();
            this.eventSource = null;
            this.isConnected = false;
            this.updateConnectionStatus("disconnected");
        }
    },
    
    reconnect() {
        this.disconnect();
        this.connect();
    },
    
    handleReconnect() {
        if (this.reconnectAttempts >= this.maxReconnectAttempts) {
            console.error("Max reconnection attempts reached");
            this.updateConnectionStatus("failed");
            showToast("error", "Real-time connection failed", "Connection Error");
            return;
        }
        
        this.reconnectAttempts++;
        const delay = this.reconnectDelay * Math.pow(2, this.reconnectAttempts - 1); // Exponential backoff
        
        console.log(`🔄 Reconnecting in ${delay}ms (attempt ${this.reconnectAttempts}/${this.maxReconnectAttempts})`);
        
        setTimeout(() => {
            if (!this.isConnected) {
                this.connect();
            }
        }, delay);
    },
    
    handleMessage(data) {
        switch (data.type) {
            case 'NEW_ALERT':
                this.handleNewAlert(data.alert);
                break;
                
            case 'ALERT_RESOLVED':
                this.handleAlertUpdate(data);
                break;
                
            case 'ALERT_ASSIGNED':
                this.handleAlertUpdate(data);
                break;
                
            case 'SYSTEM_STATUS':
                this.handleSystemStatus(data.status);
                break;
                
            case 'KPI_UPDATE':
                this.handleKpiUpdate(data.kpis);
                break;
                
            default:
                console.log("Unknown message type:", data.type);
        }
    },
    
    handleNewAlert(alert) {
        console.log("🚨 New alert received:", alert);
        
        // Notify application
        if (window.App && App.showNotification) {
            App.showNotification(alert);
        }
        
        // Update current page if relevant
        const currentPage = App.getCurrentPage();
        
        if (currentPage === 'dashboard' && window.Dashboard) {
            Dashboard.handleNewAlert(alert);
        } else if (currentPage === 'alerts' && window.Alerts) {
            Alerts.handleNewAlert(alert);
        }
        
        // Show desktop notification if permission granted
        this.showDesktopNotification(alert);
    },
    
    handleAlertUpdate(update) {
        console.log("📝 Alert update received:", update);
        
        const currentPage = App.getCurrentPage();
        
        if (currentPage === 'alerts' && window.Alerts) {
            Alerts.handleAlertUpdate(update);
        } else if (currentPage === 'cases' && window.Cases) {
            Cases.handleAlertUpdate(update);
        }
        
        // Show toast for important updates
        if (update.type === 'ALERT_RESOLVED') {
            showToast("success", `Alert ${update.alert_id} has been resolved`, "Alert Resolved");
        } else if (update.type === 'ALERT_ASSIGNED') {
            showToast("info", `Alert ${update.alert_id} has been assigned`, "Alert Assigned");
        }
    },
    
    handleSystemStatus(status) {
        console.log("⚡ System status update:", status);
        
        // Update system health indicators
        if (status.api_status !== "healthy") {
            showToast("warning", "System performance issues detected", "System Warning");
        }
        
        if (status.queue_size > 1000) {
            showToast("warning", `Alert queue is growing: ${status.queue_size} pending`, "Queue Warning");
        }
        
        // Update dashboard if visible
        const currentPage = App.getCurrentPage();
        if (currentPage === 'dashboard' && window.Dashboard) {
            Dashboard.updateSystemHealth(status);
        }
    },
    
    handleKpiUpdate(kpis) {
        console.log("📊 KPI update received:", kpis);
        
        // Update dashboard KPIs if visible
        const currentPage = App.getCurrentPage();
        if (currentPage === 'dashboard' && window.Dashboard) {
            Dashboard.updateKpis(kpis);
        }
    },
    
    updateConnectionStatus(status) {
        // Update UI indicators
        const indicator = $(".real-time-indicator");
        const dot = indicator.find(".real-time-dot");
        
        switch (status) {
            case 'connected':
                indicator.removeClass("text-warning text-danger").addClass("text-success");
                indicator.find("span:last").text("Live Data");
                dot.css("background", "var(--kyro-success)");
                break;
                
            case 'disconnected':
                indicator.removeClass("text-success text-danger").addClass("text-warning");
                indicator.find("span:last").text("Reconnecting...");
                dot.css("background", "var(--kyro-warning)");
                break;
                
            case 'failed':
                indicator.removeClass("text-success text-warning").addClass("text-danger");
                indicator.find("span:last").text("Connection Failed");
                dot.css("background", "var(--kyro-danger)");
                break;
        }
    },
    
    setupHeartbeat() {
        // Check for missed heartbeats
        this.lastHeartbeat = Date.now();
        
        setInterval(() => {
            const timeSinceLastHeartbeat = Date.now() - this.lastHeartbeat;
            
            // If no heartbeat for 2 minutes, consider connection stale
            if (this.isConnected && timeSinceLastHeartbeat > 120000) {
                console.warn("No heartbeat received, reconnecting...");
                this.reconnect();
            }
        }, 30000); // Check every 30 seconds
    },
    
    async showDesktopNotification(alert) {
        // Request permission if not granted
        if (Notification.permission === "default") {
            await Notification.requestPermission();
        }
        
        if (Notification.permission === "granted") {
            const notification = new Notification(`KYRO Alert: ${alert.alert_type}`, {
                body: `${alert.customer_name} - Risk Score: ${alert.risk_score}`,
                icon: "/favicon.ico",
                badge: "/favicon.ico",
                tag: `alert-${alert.id}`,
                requireInteraction: alert.risk_score > 70, // Keep high-risk alerts visible
                data: {
                    alertId: alert.id,
                    url: `/alerts/${alert.id}`
                }
            });
            
            notification.onclick = function() {
                window.focus();
                window.location.href = this.data.url;
                this.close();
            };
            
            // Auto-close after 10 seconds for low/medium risk
            if (alert.risk_score <= 70) {
                setTimeout(() => notification.close(), 10000);
            }
        }
    },
    
    // Public methods for manual control
    pause() {
        this.disconnect();
        console.log("⏸️ Real-time updates paused");
    },
    
    resume() {
        this.connect();
        console.log("▶️ Real-time updates resumed");
    },
    
    getConnectionStatus() {
        return {
            connected: this.isConnected,
            attempts: this.reconnectAttempts,
            lastHeartbeat: this.lastHeartbeat
        };
    }
};

// Export for use in other modules
window.RealTime = RealTime;