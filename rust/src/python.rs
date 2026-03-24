//! Python bindings for AstrBot Core

use pyo3::prelude::*;
use pyo3::types::PyList;

/// Run the AstrBot Core CLI.
#[pyfunction]
pub fn cli(py: Python<'_>) -> PyResult<()> {
    let sys = py.import("sys")?;
    let argv: Bound<'_, PyAny> = sys.getattr("argv")?;
    let argv_list = argv.downcast::<PyList>()?;
    let args: Vec<String> = argv_list.iter()
        .skip(1)
        .filter_map(|item| item.extract::<String>().ok())
        .collect();
    crate::cli::cli_with_args(&args)
        .map_err(|e| PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(e.to_string()))
}

/// Python module for AstrBot Core.
#[pymodule]
pub fn _core(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(cli, m)?)?;
    Ok(())
}
