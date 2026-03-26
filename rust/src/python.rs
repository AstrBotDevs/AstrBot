//! Python bindings for AstrBot Core

use pyo3::prelude::*;

/// Run the AstrBot Core CLI.
#[pyfunction]
pub fn cli(args: Vec<String>) -> PyResult<()> {
    crate::cli::cli_with_args(&args)
        .map_err(|e| PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(e.to_string()))
}

/// Python module for AstrBot Core.
#[pymodule]
pub fn _core(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(cli, m)?)?;
    Ok(())
}
