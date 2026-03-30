//! AstrBot Core CLI

use anyhow::Result;
use clap::{CommandFactory, Parser, Subcommand};

#[derive(Parser)]
#[command(name = "astrbot-rs")]
#[command(version = "0.1.0")]
pub struct Cli {
    #[command(subcommand)]
    pub command: Commands,
}

#[derive(Subcommand)]
pub enum Commands {
    /// Start the AstrBot Core runtime
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
    // Handle --help and --version explicitly
    if args.iter().any(|a| a == "--help" || a == "-h") {
        let mut cmd = Cli::command();
        cmd.print_help()?;
        println!();
        return Ok(());
    }
    if args.iter().any(|a| a == "--version" || a == "-V") {
        println!("astrbot-rs {}", env!("CARGO_PKG_VERSION"));
        return Ok(());
    }

    // Handle empty args - show help
    if args.is_empty() {
        let mut cmd = Cli::command();
        cmd.print_help()?;
        println!();
        return Ok(());
    }

    // When called from Python with sys.argv, clap treats the first element as bin_name.
    // We need to handle two cases:
    // 1. Single element that's a known subcommand (e.g., ['stats']) - prepend bin_name
    // 2. Multiple elements where first is program name (e.g., ['/path/astrbot-rs', 'stats']) - prepend bin_name
    let known_subcommands = ["start", "stats", "health", "help"];
    let first_is_subcommand = args.len() == 1 && known_subcommands.contains(&args[0].as_str());
    let first_is_program_name = !args[0].starts_with('-');

    let parse_args: Vec<&str> = if first_is_subcommand {
        // Case 1: ['stats'] -> prepend bin_name
        vec!["astrbot-rs", args[0].as_str()]
    } else if first_is_program_name {
        // Case 2: ['/path/astrbot-rs', 'stats', ...] -> strip first, prepend bin_name
        if args.len() > 1 {
            let mut prefixed = vec!["astrbot-rs"];
            prefixed.extend(args[1..].iter().map(|s| s.as_str()));
            prefixed
        } else {
            // Only program name, no subcommand - show help
            let mut cmd = Cli::command();
            cmd.print_help()?;
            println!();
            return Ok(());
        }
    } else {
        // Normal case: args start with flags
        args.iter().map(|s| s.as_str()).collect()
    };

    // If all args consumed, show help
    if parse_args.is_empty() {
        let mut cmd = Cli::command();
        cmd.print_help()?;
        println!();
        return Ok(());
    }

    let cli = Cli::try_parse_from(parse_args).map_err(|e| anyhow::anyhow!("{e}"))?;

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
