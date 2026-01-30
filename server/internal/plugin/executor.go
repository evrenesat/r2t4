package plugin

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"os/exec"
	"path/filepath"
	"time"
)

// Executor runs plugin binaries.
type Executor struct {
	baseDir string
	logger  *Logger
	timeout time.Duration
}

// NewExecutor creates a new plugin executor.
func NewExecutor(dataDir string, logger *Logger) *Executor {
	return &Executor{
		baseDir: filepath.Join(dataDir, "plugins"),
		logger:  logger,
		timeout: 60 * time.Second,
	}
}

// HandshakeResponse matches the JSON structure from the plugin during handshake.
type HandshakeResponse struct {
	Name            string   `json:"name"`
	Version         string   `json:"version"`
	ProtocolVersion int      `json:"protocol_version"`
	PluginType      string   `json:"plugin_type"`
	Capabilities    []string `json:"capabilities"`
	Description     string   `json:"description"`
}

// PluginRequest matches the JSON sent to plugin stdin.
type PluginRequest struct {
	RequestID string `json:"request_id"`
	Action    string `json:"action"`
	Params    any    `json:"params"`
}

// PluginResponse matches the JSON received from plugin stdout.
type PluginResponse struct {
	RequestID string `json:"request_id"`
	Success   bool   `json:"success"`
	Result    any    `json:"result,omitempty"`
	Error     any    `json:"error,omitempty"`
}

// Handshake runs the plugin with --handshake to get metadata.
func (e *Executor) Handshake(path string) (*HandshakeResponse, int64, error) {
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	cmd := exec.CommandContext(ctx, path, "--handshake")

	// Create plugin-specific output dir just in case, though handshake shouldn't need it
	// We don't have an ID yet, so we skip setting cwd specifically for handshake

	start := time.Now()
	output, err := cmd.Output()
	duration := time.Since(start).Milliseconds()

	if err != nil {
		if exitErr, ok := err.(*exec.ExitError); ok {
			return nil, duration, fmt.Errorf("plugin failed (stderr: %s): %w", string(exitErr.Stderr), err)
		}
		return nil, duration, fmt.Errorf("plugin execution failed: %w", err)
	}

	var resp HandshakeResponse
	if err := json.Unmarshal(output, &resp); err != nil {
		return nil, duration, fmt.Errorf("invalid handshake response: %w", err)
	}

	return &resp, duration, nil
}

// Execute runs the plugin with --execute and passes request via stdin.
func (e *Executor) Execute(path string, req PluginRequest) (*PluginResponse, int64, error) {
	ctx, cancel := context.WithTimeout(context.Background(), e.timeout)
	defer cancel()

	cmd := exec.CommandContext(ctx, path, "--execute")

	// Set working directory to <data_dir>/plugins/<plugin_name>/
	// Note: We need the plugin name/ID here ideally. For now we just use the base plugins dir.
	// In a real scenario we'd pass the ID and ensure the dir exists.
	cmd.Dir = e.baseDir

	var stdin bytes.Buffer
	if err := json.NewEncoder(&stdin).Encode(req); err != nil {
		return nil, 0, fmt.Errorf("encoding request: %w", err)
	}
	cmd.Stdin = &stdin

	start := time.Now()
	output, err := cmd.Output()
	duration := time.Since(start).Milliseconds()

	if err != nil {
		if exitErr, ok := err.(*exec.ExitError); ok {
			return nil, duration, fmt.Errorf("plugin failed (stderr: %s): %w", string(exitErr.Stderr), err)
		}
		return nil, duration, fmt.Errorf("plugin execution failed: %w", err)
	}

	var resp PluginResponse
	if err := json.Unmarshal(output, &resp); err != nil {
		return nil, duration, fmt.Errorf("invalid response json: %w", err)
	}

	return &resp, duration, nil
}
