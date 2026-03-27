//! Python bindings for AstrBot Core
//!
//! Exposes Rust core functionality to Python via PyO3.

use pyo3::prelude::*;
use pyo3::types::PyDict;
use std::sync::{Arc, RwLock};

/// Run the AstrBot Core CLI.
#[pyfunction]
pub fn cli(args: Vec<String>) -> PyResult<()> {
    crate::cli::cli_with_args(&args)
        .map_err(|e| PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(e.to_string()))
}

// ============================================================================
// Global singletons for Python access
// ============================================================================

lazy_static::lazy_static! {
    static ref ORCHESTRATOR: Arc<RwLock<crate::orchestrator::Orchestrator>> =
        Arc::new(RwLock::new(crate::orchestrator::Orchestrator::new()));
}

// ============================================================================
// ABP Client Python bindings
// ============================================================================

/// Python wrapper for AbpClient
#[pyclass]
pub struct PyAbpClient {
    inner: Arc<RwLock<crate::abp::AbpClient>>,
}

#[pymethods]
impl PyAbpClient {
    #[new]
    pub fn new() -> Self {
        Self {
            inner: Arc::new(RwLock::new(crate::abp::AbpClient::new())),
        }
    }

    pub fn is_connected(&self) -> bool {
        self.inner.read().map(|c| c.is_connected()).unwrap_or(false)
    }

    pub fn register_in_process_plugin(&self, name: &str, version: &str) -> PyResult<()> {
        let plugin_config = crate::abp::PluginConfig {
            name: name.to_string(),
            version: version.to_string(),
            load_mode: crate::abp::PluginLoadMode::InProcess,
            ..Default::default()
        };

        self.inner.write().map(|mut c| {
            c.register_in_process_plugin(plugin_config);
        }).map_err(|e| PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(format!("Lock error: {}", e)))
    }

    pub fn register_out_of_process_plugin(
        &self,
        name: &str,
        version: &str,
        command: Option<String>,
        transport: Option<String>,
    ) -> PyResult<()> {
        let transport = match transport.as_deref() {
            Some("unix_socket") => crate::abp::PluginTransport::UnixSocket,
            Some("http") => crate::abp::PluginTransport::Http,
            _ => crate::abp::PluginTransport::Stdio,
        };

        let plugin_config = crate::abp::PluginConfig {
            name: name.to_string(),
            version: version.to_string(),
            load_mode: crate::abp::PluginLoadMode::OutOfProcess,
            command,
            transport,
            ..Default::default()
        };

        self.inner.write().map(|mut c| {
            c.register_out_of_process_plugin(plugin_config);
        }).map_err(|e| PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(format!("Lock error: {}", e)))
    }

    pub fn unregister_plugin(&self, name: &str) -> PyResult<()> {
        self.inner.write().map(|mut c| {
            c.unregister_plugin(name);
        }).map_err(|e| PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(format!("Lock error: {}", e)))
    }

    pub fn list_plugins(&self) -> Vec<String> {
        self.inner.read().map(|c| c.list_plugins()).unwrap_or_default()
    }

    pub fn get_plugin_info(&self, name: &str, py: Python<'_>) -> Option<Py<PyDict>> {
        self.inner.read().ok().and_then(|c| {
            c.get_plugin_info(name).map(|info| {
                let dict = PyDict::new(py);
                dict.set_item("name", &info.name).ok();
                dict.set_item("version", &info.version).ok();
                dict.set_item("load_mode", format!("{}", info.load_mode)).ok();
                dict.set_item("tools_count", info.tools_count).ok();
                // Capabilities
                let caps = PyDict::new(py);
                caps.set_item("tools", info.capabilities.tools).ok();
                caps.set_item("handlers", info.capabilities.handlers).ok();
                caps.set_item("events", info.capabilities.events).ok();
                caps.set_item("resources", info.capabilities.resources).ok();
                dict.set_item("capabilities", caps).ok();
                // Metadata
                if let Some(ref meta) = info.metadata {
                    let meta_dict = PyDict::new(py);
                    meta_dict.set_item("display_name", meta.display_name.as_deref().unwrap_or("")).ok();
                    meta_dict.set_item("description", meta.description.as_deref().unwrap_or("")).ok();
                    meta_dict.set_item("author", meta.author.as_deref().unwrap_or("")).ok();
                    dict.set_item("metadata", meta_dict).ok();
                }
                dict.into()
            })
        })
    }

    pub fn health_check(&self, name: &str) -> bool {
        self.inner.read().map(|c| c.health_check(name)).unwrap_or(false)
    }
}

impl Default for PyAbpClient {
    fn default() -> Self {
        Self::new()
    }
}

// ============================================================================
// Orchestrator Python bindings
// ============================================================================

/// Python wrapper for Orchestrator
#[pyclass]
pub struct PyOrchestrator {
    inner: Arc<RwLock<crate::orchestrator::Orchestrator>>,
}

#[pymethods]
impl PyOrchestrator {
    #[new]
    pub fn new() -> Self {
        Self {
            inner: ORCHESTRATOR.clone(),
        }
    }

    /// Start the orchestrator
    pub fn start(&self) -> PyResult<()> {
        self.inner.write().map(|o| {
            o.start_sync()
        }).map_err(|e| PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(e.to_string()))?
        .map_err(|e| PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(e.to_string()))
    }

    /// Stop the orchestrator
    pub fn stop(&self) -> PyResult<()> {
        self.inner.write().map(|o| {
            o.stop_sync()
        }).map_err(|e| PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(e.to_string()))?
        .map_err(|e| PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(e.to_string()))
    }

    pub fn is_running(&self) -> bool {
        self.inner.read().map(|o| o.is_running()).unwrap_or(false)
    }

    pub fn register_star(&self, name: &str, handler: &str) -> PyResult<()> {
        self.inner.write().map(|o| {
            o.register_star(name, handler)
        }).map_err(|e| PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(e.to_string()))?
        .map_err(|e| PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(e.to_string()))
    }

    pub fn unregister_star(&self, name: &str) -> PyResult<()> {
        self.inner.write().map(|o| {
            o.unregister_star(name)
        }).map_err(|e| PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(e.to_string()))?
        .map_err(|e| PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(e.to_string()))
    }

    pub fn list_stars(&self) -> Vec<String> {
        self.inner.read().map(|o| o.list_stars()).unwrap_or_default()
    }

    pub fn record_activity(&self) {
        if let Ok(o) = self.inner.read() { o.record_activity() }
    }

    pub fn get_stats(&self, py: Python<'_>) -> Py<PyDict> {
        let dict = PyDict::new(py);
        if let Ok(o) = self.inner.read() {
            let stats = o.stats();
            dict.set_item("message_count", stats.message_count()).ok();
            dict.set_item("uptime_seconds", stats.uptime_seconds()).ok();
            dict.set_item("last_activity_time", stats.last_activity_time()).ok();
        }
        dict.into()
    }

    pub fn set_protocol_connected(&self, protocol: &str, connected: bool) -> PyResult<()> {
        self.inner.write().map(|o| {
            o.set_protocol_connected(protocol, connected)
        }).map_err(|e| PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(e.to_string()))?
        .map_err(|e| PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(e.to_string()))
    }

    pub fn get_protocol_status(&self, protocol: &str, py: Python<'_>) -> Option<Py<PyDict>> {
        self.inner.read().ok().and_then(|o| {
            o.get_protocol_status(protocol).map(|status| {
                let dict = PyDict::new(py);
                dict.set_item("connected", status.connected).ok();
                dict.set_item("name", &status.name).ok();
                dict.into()
            })
        })
    }
}

impl Default for PyOrchestrator {
    fn default() -> Self {
        Self::new()
    }
}

// ============================================================================
// Module exports
// ============================================================================

/// Get the global orchestrator instance
#[pyfunction]
pub fn get_orchestrator() -> PyOrchestrator {
    PyOrchestrator::new()
}

/// Get a new ABP client instance
#[pyfunction]
pub fn get_abp_client() -> PyAbpClient {
    PyAbpClient::new()
}

/// Python module for AstrBot Core.
#[pymodule(module = "_core")]
pub fn _core(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(cli, m)?)?;
    m.add_function(wrap_pyfunction!(get_orchestrator, m)?)?;
    m.add_function(wrap_pyfunction!(get_abp_client, m)?)?;
    m.add_class::<PyOrchestrator>()?;
    m.add_class::<PyAbpClient>()?;
    Ok(())
}
