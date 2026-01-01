// Package config provides configuration management for the R2T4 server.
package config

import (
	"encoding/json"
	"flag"
	"fmt"
	"os"
	"path/filepath"
)

// Config holds all server configuration options.
type Config struct {
	// DataDir is the root directory for storing all uploaded data.
	// Structure: /data/devices/<device_id>/{ambient,prompts}/...
	DataDir string `json:"data_dir"`

	// ListenAddr is the address:port to listen on.
	// Example: ":8080" or "0.0.0.0:8080"
	ListenAddr string `json:"listen_addr"`

	// TLSCertFile is the path to the TLS certificate file (optional).
	// If empty, server runs in plaintext mode (for LAN).
	TLSCertFile string `json:"tls_cert_file"`

	// TLSKeyFile is the path to the TLS private key file (optional).
	TLSKeyFile string `json:"tls_key_file"`

	// ConfigFile is the path to a JSON config file (optional).
	// Command-line flags override config file values.
	ConfigFile string `json:"-"`
}

// DefaultConfig returns a Config with sensible defaults.
func DefaultConfig() *Config {
	return &Config{
		DataDir:    "./data",
		ListenAddr: ":8080",
	}
}

// Load parses configuration from command-line flags and optional config file.
// Priority: CLI flags > config file > defaults
func Load() (*Config, error) {
	cfg := DefaultConfig()

	// Define command-line flags
	flag.StringVar(&cfg.DataDir, "data-dir", cfg.DataDir, "Root directory for storing uploaded data")
	flag.StringVar(&cfg.ListenAddr, "listen", cfg.ListenAddr, "Address:port to listen on")
	flag.StringVar(&cfg.TLSCertFile, "tls-cert", "", "Path to TLS certificate file (optional)")
	flag.StringVar(&cfg.TLSKeyFile, "tls-key", "", "Path to TLS private key file (optional)")
	flag.StringVar(&cfg.ConfigFile, "config", "", "Path to JSON config file (optional)")

	flag.Parse()

	// Load config file if specified
	if cfg.ConfigFile != "" {
		fileCfg, err := loadFromFile(cfg.ConfigFile)
		if err != nil {
			return nil, fmt.Errorf("loading config file: %w", err)
		}
		// Merge file config with defaults (CLI flags will override via flag parsing)
		cfg = mergeConfig(cfg, fileCfg)
	}

	// Validate configuration
	if err := cfg.Validate(); err != nil {
		return nil, fmt.Errorf("invalid configuration: %w", err)
	}

	return cfg, nil
}

// loadFromFile reads configuration from a JSON file.
func loadFromFile(path string) (*Config, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}

	cfg := &Config{}
	if err := json.Unmarshal(data, cfg); err != nil {
		return nil, fmt.Errorf("parsing JSON: %w", err)
	}

	return cfg, nil
}

// mergeConfig merges two configs, preferring values from 'a' over 'b'.
// This allows CLI flags to override config file values.
func mergeConfig(a, b *Config) *Config {
	result := *a

	// Only use file values if CLI didn't override defaults
	if result.DataDir == DefaultConfig().DataDir && b.DataDir != "" {
		result.DataDir = b.DataDir
	}
	if result.ListenAddr == DefaultConfig().ListenAddr && b.ListenAddr != "" {
		result.ListenAddr = b.ListenAddr
	}
	if result.TLSCertFile == "" && b.TLSCertFile != "" {
		result.TLSCertFile = b.TLSCertFile
	}
	if result.TLSKeyFile == "" && b.TLSKeyFile != "" {
		result.TLSKeyFile = b.TLSKeyFile
	}

	return &result
}

// Validate checks that the configuration is valid.
func (c *Config) Validate() error {
	if c.DataDir == "" {
		return fmt.Errorf("data-dir is required")
	}

	// Ensure data directory can be created
	absPath, err := filepath.Abs(c.DataDir)
	if err != nil {
		return fmt.Errorf("invalid data-dir path: %w", err)
	}
	c.DataDir = absPath

	// Check TLS configuration consistency
	if (c.TLSCertFile != "") != (c.TLSKeyFile != "") {
		return fmt.Errorf("both tls-cert and tls-key must be specified together")
	}

	return nil
}

// IsTLSEnabled returns true if TLS is configured.
func (c *Config) IsTLSEnabled() bool {
	return c.TLSCertFile != "" && c.TLSKeyFile != ""
}
