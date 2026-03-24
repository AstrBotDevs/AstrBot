//! Runtime statistics tracking

use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::Arc;

#[derive(Debug, Clone)]
pub struct RuntimeStats {
    pub message_count: Arc<AtomicU64>,
    pub start_time: f64,
    pub last_activity_time: Arc<AtomicU64>,
}

impl Default for RuntimeStats {
    fn default() -> Self {
        Self::new()
    }
}

impl RuntimeStats {
    #[must_use]
    pub fn new() -> Self {
        Self {
            message_count: Arc::new(AtomicU64::new(0)),
            start_time: std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .map(|d| d.as_secs_f64())
                .unwrap_or_default(),
            last_activity_time: Arc::new(AtomicU64::new(0)),
        }
    }

    pub fn record_message(&self) {
        self.message_count.fetch_add(1, Ordering::Relaxed);
        let now = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .map(|d| d.as_secs())
            .unwrap_or_default();
        self.last_activity_time.store(now, Ordering::Relaxed);
    }

    #[must_use]
    pub fn message_count(&self) -> u64 {
        self.message_count.load(Ordering::Relaxed)
    }

    #[must_use]
    pub fn last_activity_time(&self) -> Option<f64> {
        let ts = self.last_activity_time.load(Ordering::Relaxed);
        if ts == 0 {
            None
        } else {
            Some(ts as f64)
        }
    }

    #[must_use]
    pub fn uptime_seconds(&self) -> f64 {
        let now = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .map(|d| d.as_secs_f64())
            .unwrap_or_default();
        now - self.start_time
    }
}
