//! Python bindings for AstrBot Core

use crate::orchestrator::Orchestrator;
use pyo3::prelude::*;
use pyo3::sync::GILOnceCell;
use pyo3::types::PyDict;

static ORCHESTRATOR: GILOnceCell<Py<PythonOrchestrator>> = GILOnceCell::new();

#[pyclass]
pub struct PythonOrchestrator {
    inner: Orchestrator,
}

#[pymethods]
impl PythonOrchestrator {
    #[new]
    pub fn new() -> Self {
        Self {
            inner: Orchestrator::new(),
        }
    }

    pub fn start(&self) -> PyResult<()> {
        self.inner.start().map_err(|e| PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(e.to_string()))
    }

    pub fn stop(&self) -> PyResult<()> {
        self.inner.stop().map_err(|e| PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(e.to_string()))
    }

    pub fn is_running(&self) -> bool {
        self.inner.is_running()
    }

    pub fn register_star(&self, name: &str, handler: &str) -> PyResult<()> {
        self.inner.register_star(name, handler).map_err(|e| PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(e.to_string()))
    }

    pub fn unregister_star(&self, name: &str) -> PyResult<()> {
        self.inner.unregister_star(name).map_err(|e| PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(e.to_string()))
    }

    pub fn list_stars(&self) -> Vec<String> {
        self.inner.list_stars()
    }

    pub fn record_activity(&self) {
        self.inner.record_activity()
    }

    #[allow(unsafe_code)]
    pub fn get_stats(&self) -> PyResult<Py<PyAny>> {
        let stats = self.inner.stats();
        let py = unsafe { Python::assume_gil_acquired() };
        let dict = PyDict::new(py);
        dict.set_item("message_count", stats.message_count())?;
        dict.set_item("uptime_seconds", stats.uptime_seconds())?;
        if let Some(last) = stats.last_activity_time() {
            dict.set_item("last_activity", last)?;
        }
        Ok(dict.into())
    }

    pub fn set_protocol_connected(&self, protocol: &str, connected: bool) -> PyResult<()> {
        self.inner.set_protocol_connected(protocol, connected).map_err(|e| PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(e.to_string()))
    }

    #[allow(unsafe_code)]
    pub fn get_protocol_status(&self, protocol: &str) -> Option<Py<PyAny>> {
        let status = self.inner.get_protocol_status(protocol)?;
        let py = unsafe { Python::assume_gil_acquired() };
        let dict = PyDict::new(py);
        dict.set_item("connected", status.connected).ok()?;
        dict.set_item("name", status.name).ok()?;
        Some(dict.into())
    }
}

#[pyfunction]
pub fn get_orchestrator(py: Python<'_>) -> PyResult<&'static Py<PythonOrchestrator>> {
    if ORCHESTRATOR.get(py).is_none() {
        let orchestrator = Py::new(py, PythonOrchestrator::new())
            .map_err(|e| PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(format!("Failed to create: {e}")))?;
        ORCHESTRATOR.set(py, orchestrator)
            .map_err(|_| PyErr::new::<pyo3::exceptions::PyRuntimeError, _>("Already initialized"))?;
    }
    Ok(ORCHESTRATOR.get(py).expect("orchestrator should be initialized"))
}

#[pymodule]
pub fn astrbot_core(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_class::<PythonOrchestrator>()?;
    m.add_function(wrap_pyfunction!(get_orchestrator, m)?)?;
    Ok(())
}
