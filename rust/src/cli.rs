//! AstrBot Core CLI

use anyhow::Result;
use clap::{Parser, Subcommand};

#[derive(Parser)]
#[command(name = "astrbot-rs")]
#[command(version = "0.1.0")]
pub struct Cli {
    #[command(subcommand)]
    pub command: Commands,
}

#[derive(Subcommand)]
pub enum Commands {
    /// Start the AstrBot core runtime
    Start {
        /// Host to bind to
        #[arg(long, default_value = "127.0.0.1")]
        host: String,
        /// Port to listen on
        #[arg(long, default_value_t = 8765)]
        port: u16,
    },
    /// Show runtime statistics
    Stats,
    /// Run health check
    Health,
}

pub fn cli() -> Result<()> {
    let args: Vec<String> = std::env::args().collect();
    cli_with_args(&args[1..])
}

pub fn cli_with_args(args: &[String]) -> Result<()> {
    let cli = Cli::try_parse_from(args).map_err(|e| anyhow::anyhow!("{e}"))?;

    match cli.command {
        Commands::Start { host, port } => {
            start_runtime(&host, port)?;
        }
        Commands::Stats => {
            show_stats()?;
        }
        Commands::Health => {
            health_check()?;
        }
    }

    Ok(())
}

pub fn start_runtime(host: &str, port: u16) -> Result<()> {
    println!("Starting AstrBot Core runtime on {host}:{port}");
    println!("AstrBot Core v{} is running", env!("CARGO_PKG_VERSION"));
    Ok(())
}

pub fn show_stats() -> Result<()> {
    println!("AstrBot Core Statistics");
    println!("========================");
    println!("Version: {}", env!("CARGO_PKG_VERSION"));
    Ok(())
}

pub fn health_check() -> Result<()> {
    println!("OK");
    Ok(())
}
